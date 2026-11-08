"""N74: lots, expiry and products out of stock (§5, §6 Nhà thuốc) on a tiny pharmacy built by hand. Each expected
figure is worked out by hand below; the formulas were first checked on the train pharmacies (datamate/metrics/lots.py).

What is left at the end of 30/06/2026 (D):
  L1 (SP1, hạn 10/07): 10 in − 4 (O1) − 2 (O3, sold 10/06) + 2 (O3 returned 12/06) − 4 (O4) = 2; O2 cancelled takes nothing
  L2 (SP1, hạn 01/09): 10
  L3 (SP2, hạn 05/07): 5 in (receipt 15/06) − 1 (O4) = 4
  L4 (SP3, hạn 20/06): 3, already expired at D
"""
from datetime import date, datetime

import pandas as pd

from datamate import metrics
from datamate.contracts import CanonicalDB, QueryPlan, ResolvedPeriod, ResolvedPlan
from datamate.formatter import format_value

D = date(2026, 6, 30)


def shop() -> CanonicalDB:
    orders = pd.DataFrame({"order_id": ["O1", "O2", "O3", "O4"],
                           "order_time": [datetime(2026, 6, 1, 9), datetime(2026, 6, 5, 9), datetime(2026, 6, 10, 9),
                                          datetime(2026, 6, 20, 9)],
                           "status": ["completed", "cancelled", "returned", "completed"]})
    returns = pd.DataFrame({"order_id": ["O3"], "return_time": [datetime(2026, 6, 12, 10)]})
    purchases = pd.DataFrame({"receipt_id": ["R1", "R1", "R1", "R2"], "product_key": ["SP1", "SP1", "SP3", "SP2"],
                              "receipt_time": [datetime(2026, 5, 1)] * 3 + [datetime(2026, 6, 15)]})
    lots = pd.DataFrame({"lot_id": ["L1", "L2", "L3", "L4"], "product_key": ["SP1", "SP1", "SP2", "SP3"],
                         "expiry_date": ["2026-07-10", "2026-09-01", "2026-07-05", "2026-06-20"],
                         "base_qty_in": [10.0, 10.0, 5.0, 3.0], "unit_cost": [1000.0, 1200.0, 500.0, 100.0],
                         "receipt_id": ["R1", "R1", "R2", "R1"]})
    lot_sales = pd.DataFrame({"order_id": ["O1", "O2", "O3", "O4", "O4"], "lot_id": ["L1", "L1", "L1", "L1", "L3"],
                              "base_qty": [4.0, 6.0, 2.0, 4.0, 1.0], "returned_base_qty": [0.0, 0.0, 2.0, 0.0, 0.0]})
    products = pd.DataFrame({"product_key": ["SP1", "SP2", "SP3"], "product_name": ["Thuốc A", "Siro B", "Kem C"]})
    inventory = pd.DataFrame({"product_key": ["SP1", "SP1", "SP2", "SP2"],
                              "as_of": [datetime(2026, 6, 1), datetime(2026, 6, 20), datetime(2026, 6, 15),
                                        datetime(2026, 6, 20)],
                              "base_qty": [5.0, 0.0, 5.0, 4.0]})
    return CanonicalDB(tables={"orders": orders, "returns": returns, "purchases": purchases, "lots": lots,
                               "lot_sales": lot_sales, "products": products, "inventory": inventory})


def ask(raw: dict, linked=None, day: date = D):
    plan = ResolvedPlan(plan=QueryPlan.model_validate(raw), as_of=D, linked=linked or {},
                        period=ResolvedPeriod(start=date(2000, 1, 1), end=day, mode="stock"))
    r = metrics.execute(plan, shop())
    return None if r is None else format_value(r.answer_type, r.value)


def nearest(product: str, day: date = D):
    return ask({"intent": "value", "measures": [{"metric": "nearest_expiry", "filters": [
        {"field": "product", "op": "eq", "value": product}]}], "period": {"kind": "until", "date": day.isoformat()}},
        linked={product: product}, day=day)


def test_the_nearest_expiry_is_the_earliest_lot_still_holding_goods_and_not_past():
    assert nearest("SP1") == "2026-07-10"  # L1 still holds 2
    assert nearest("SP3") is None  # its only lot expired on 20/06
    assert nearest("SP2", date(2026, 6, 11)) is None  # L3 is received on 15/06


def test_the_cost_of_the_lots_expiring_in_the_window():
    window = {"intent": "value", "measures": [{"metric": "stock_value"}], "answer_type": "number",
              "period": {"kind": "range", "start": "2026-06-30", "end": "2026-07-30"}}
    assert ask(window) == 4000  # L1 2 × 1000 + L3 4 × 500; L2 expires later, L4 is past
    days = {"intent": "value", "answer_type": "number", "period": {"kind": "today"},
            "measures": [{"metric": "expiring_value", "filters": [{"field": "expiry_within_days", "op": "eq",
                                                                    "value": 90}]}]}
    assert ask(days) == 16000  # + L2 10 × 1200


def test_a_window_written_two_ways_that_disagree_gives_no_figure():
    """Public 07/11: "hạn dùng từ 08/08 tới hết 06/12" (120 days) read with a filter of 365 days."""
    both = {"intent": "value", "answer_type": "number",
            "measures": [{"metric": "stock_value", "filters": [{"field": "expiry_within_days", "op": "eq",
                                                                 "value": 365}]}],
            "period": {"kind": "range", "start": "2026-06-30", "end": "2026-07-30"}}
    assert ask(both) is None
    alone = {"intent": "value", "answer_type": "number", "period": {"kind": "today"},
             "measures": [{"metric": "stock_value", "filters": [{"field": "expiry_within_days", "op": "gte",
                                                                  "value": 30}]}]}
    assert ask(alone) is None  # "≥ 30 days" with nothing to confirm it is no window
    confirmed = dict(both, measures=[{"metric": "stock_value", "filters": [
        {"field": "expiry_within_days", "op": "gte", "value": 30}]}])
    assert ask(confirmed) == 4000  # the train bank's "gte 90" beside the range D..D + 90


def test_products_expiring_listed_by_their_earliest_expiry():
    lst = {"intent": "list_items", "list_spec": {"entity": "product", "condition": "expiring_within", "n": 30},
           "period": {"kind": "today"}}
    assert ask(lst) == ["Siro B", "Thuốc A"]  # 05/07 before 10/07
    assert ask(dict(lst, list_spec=dict(lst["list_spec"], count=True))) == 2


def test_products_out_of_stock_at_the_end_of_the_day():
    q = {"intent": "list_items", "list_spec": {"entity": "product", "condition": "out_of_stock_end_of_day",
                                                "count": True}}
    assert ask(q) == 1  # SP1 at 0 since 20/06; SP2 holds 4; SP3 has no stock record (not followed)


def test_the_stock_value_by_the_catalogue_cost():
    """§5 "giá trị hàng tồn kho": stock at the end of the day × the catalogue's cost of one base unit, goods in stock
    only (train: the two shops whose mapping has the catalogue and the stock, both answers to the đồng)."""
    db = shop()
    db.tables["products"] = db.tables["products"].assign(unit_cost=[1000.0, 500.0, 100.0])

    def value(day: date, period: dict):
        plan = ResolvedPlan(plan=QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "stock_value"}],
                                                           "answer_type": "number", "period": period}),
                            as_of=D, period=ResolvedPeriod(start=date(2000, 1, 1), end=day, mode="stock"))
        r = metrics.execute(plan, db)
        return None if r is None else format_value(r.answer_type, r.value)
    assert value(D, {"kind": "today"}) == 2000  # SP1 at 0 left out, SP2 4 × 500; SP3 has no stock record
    assert value(date(2026, 6, 10), {"kind": "until", "date": "2026-06-10"}) == 5000  # SP1 5 × 1000, SP2 not yet
    db.tables["products"].loc[1, "unit_cost"] = None
    assert value(D, {"kind": "today"}) is None  # a product in stock with no cost


def test_the_stock_value_rule_is_checked_by_the_rule_gate():
    """[R] checks only the rulebook rows the registry declares; a cited row it does not know fails rules_unchanged
    (08/11: the right train answer was refused that way)."""
    from datamate.pipeline import rule_ids
    assert "§5.gia_tri_hang_ton_kho" in rule_ids()
