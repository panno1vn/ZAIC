"""Purchases, selling prices and stock (§5, v2) on a tiny shop built by hand; each expected figure is worked out by
hand from the rulebook row the test names."""
from datetime import date, datetime

import pandas as pd

from datamate import metrics
from datamate.contracts import CanonicalDB, QueryPlan, ResolvedPeriod, ResolvedPlan
from datamate.formatter import format_value

TODAY = date(2026, 6, 30)
JUNE = ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30))


def shop(ledger: bool = False) -> CanonicalDB:
    orders = pd.DataFrame([
        ("o1", datetime(2026, 6, 10, 9), "completed"),
        ("o2", datetime(2026, 6, 10, 15), "cancelled"),  # §5 price of day D: cancelled orders' lines count too
        ("o3", datetime(2026, 6, 11, 9), "completed"),
        ("o4", datetime(2026, 6, 12, 9), "completed"),
    ], columns=["order_id", "order_time", "status"])
    lines = pd.DataFrame([
        # order, key, qty, unit, base_qty, unit_price, amount
        ("o1", "SP1", 2, "hộp", 12, 60_000, 120_000),     # a box of 6 at 60 000: 10 000 a piece
        ("o2", "SP1", 3, "cái", 3, 10_000, 30_000),
        ("o3", "SP1", 1, "cái", 1, 11_000, 11_000),
        ("o3", "SP1", 1, "hộp", 6, 60_000, 60_000),       # two prices that day: no single price
        ("o4", "SP2", 4, "chai", 4, 15_000, 60_000),
    ], columns=["order_id", "product_key", "qty", "unit", "base_qty", "unit_price", "line_amount"])
    lines["product_name"] = lines["product_key"]
    products = pd.DataFrame({"product_key": ["SP1", "SP2"], "product_name": ["Bánh", "Nước"],
                             "base_unit": ["cái", "chai"]})
    conversions = pd.DataFrame({"product_key": ["SP1"], "unit": ["hộp"], "factor": [6.0]})
    purchases = pd.DataFrame([
        # receipt, day, supplier, key, qty, unit, cost
        ("PN1", datetime(2026, 6, 2), "Cty A", "SP1", 10, "hộp", 50_000),
        ("PN2", datetime(2026, 6, 20), "Cty B", "SP1", 30, "hộp", 54_000),
        ("PN3", datetime(2026, 6, 21), "Cty A", "SP2", 100, "chai", 9_000),
        ("PN4", datetime(2026, 5, 30), "Cty A", "SP1", 99, "hộp", 1),           # May: not in June
        ("PN5", datetime(2026, 6, 22), "Cty A", "SP1", 50, "hộp", 1),           # cancelled receipt
    ], columns=["receipt_id", "receipt_time", "supplier", "product_key", "qty", "unit", "unit_cost"])
    purchases["cancelled"] = [False, False, False, False, True]
    if ledger:  # a stock card: one record after every movement
        inventory = pd.DataFrame({"product_key": ["SP1", "SP1", "SP1", "SP2"],
                                  "as_of": [date(2026, 6, 2), date(2026, 6, 10), date(2026, 6, 10), date(2026, 6, 21)],
                                  "base_qty": [60.0, 55.0, 48.0, 100.0]})
    else:  # one snapshot at the end of the data
        inventory = pd.DataFrame({"product_key": ["SP1", "SP2"], "as_of": [TODAY, TODAY], "base_qty": [97.0, 96.0]})
    return CanonicalDB(tables={"orders": orders, "lines": lines, "products": products,
                               "unit_conversions": conversions, "purchases": purchases, "inventory": inventory})


def run(measures, period=JUNE, linked=None, db=None, as_of=TODAY):
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"intent": "value", "measures": measures,
                                                       "period": {"kind": "this_month"}}),
                        as_of=as_of, period=period, linked=linked or {})
    r = metrics.execute(plan, db or shop())
    return None if r is None else format_value(r.answer_type, r.value)


def product(name="bánh"):
    return [{"field": "product", "value": name}]


BANH = {"bánh": "SP1"}
NUOC = {"nước": "SP2"}


def test_purchase_amount_counts_receipts_dated_in_the_period_without_cancelled_ones():
    # §5: 10 × 50 000 + 30 × 54 000 + 100 × 9 000; PN4 is May, PN5 cancelled
    assert run([{"metric": "purchase_amount"}]) == 3_020_000
    assert run([{"metric": "purchase_amount", "filters": [{"field": "supplier", "value": "a"}]}],
               linked={"a": "Cty A"}) == 1_400_000
    assert run([{"metric": "purchase_amount"}], period=ResolvedPeriod(start=date(2026, 4, 1),
                                                                      end=date(2026, 4, 30))) is None  # nothing: §7


def test_supplier_bought_from_most_is_by_money_of_receipts():
    plan = lambda k: ResolvedPlan(plan=QueryPlan.model_validate(  # noqa: E731
        {"intent": "rank", "period": {"kind": "this_month"}, "rank": {"entity": "supplier", "by": "purchase_amount",
                                                                      "k": k}}), as_of=TODAY, period=JUNE)
    # §5: Cty B 1 620 000 > Cty A 1 400 000 (PN5 of Cty A is cancelled), though Cty A has more receipts
    assert metrics.execute(plan(1), shop()).value == "Cty B"
    assert metrics.execute(plan(2), shop()).value == ["Cty B", "Cty A"]
    # public rulebook §5 "nhà cung cấp chính": most receipts, PN1 and PN3 of Cty A (not May's PN4, cancelled PN5)
    main = ResolvedPlan(plan=QueryPlan.model_validate({"intent": "rank", "period": {"kind": "this_month"},
                                                       "rank": {"entity": "supplier", "by": "receipt_count"}}),
                        as_of=TODAY, period=JUNE)
    result = metrics.execute(main, shop())
    assert result.value == "Cty A" and "§5.nha_cung_cap_chinh" in result.rule_ids  # [R] blocks it on train
    from datamate.nlu import grounding
    assert grounding.ungrounded_measures("Nhà cung cấp chính tháng 6 là ai?", plan(1).plan) == [
        "metric=purchase_amount"]
    assert grounding.ungrounded_measures("Nhà cung cấp chính tháng 6 là ai?", main.plan) == []


def test_average_purchase_cost_is_weighted_by_quantity():
    # §5: (10 × 50 000 + 30 × 54 000) / 40 = 53 000, not the mean of the prices (52 000)
    assert run([{"metric": "purchase_avg_cost", "filters": product(), "unit": "hộp"}], linked=BANH) == 53_000
    assert run([{"metric": "purchase_avg_cost", "filters": product()}], linked=BANH) == 53_000
    # asked per piece while the shop buys by the box: no rule here
    assert run([{"metric": "purchase_avg_cost", "filters": product(), "unit": "cái"}], linked=BANH) is None


def test_selling_price_of_a_day_is_per_base_unit_and_counts_cancelled_orders():
    day10 = ResolvedPeriod(start=date(2026, 6, 10), end=date(2026, 6, 10))
    day11 = ResolvedPeriod(start=date(2026, 6, 11), end=date(2026, 6, 11))
    price = [{"metric": "unit_price", "filters": product(), "unit": "cái"}]
    assert run(price, period=day10, linked=BANH) == 10_000  # 60 000 a box of 6, and 10 000 on a cancelled order
    assert run(price, period=day11, linked=BANH) is None  # 11 000 and 10 000 the same day: no single price
    assert run([{"metric": "unit_price", "filters": product(), "unit": "hộp"}], period=day10, linked=BANH) is None
    assert run(price, linked=BANH) is None  # a price is of one day


def test_stock_reads_the_last_record_up_to_the_day():
    stock = [{"metric": "stock_qty", "filters": product(), "unit": "cái"}]
    assert run(stock, linked=BANH) == 97
    # §5 "tồn theo đơn vị lớn": [whole boxes, pieces left], also asked as two measures
    assert run([{"metric": "stock_qty", "filters": product(), "unit": "hộp", "unit_split": True}], linked=BANH) == [16, 1]
    assert run([{"metric": "stock_qty", "filters": product(), "unit": "hộp"},
                {"metric": "stock_qty", "filters": product(), "unit": "cái"}], linked=BANH) == [16, 1]
    # a day before the only snapshot: the movements between are not undone, no answer
    assert run(stock, linked=BANH, period=ResolvedPeriod(start=date(2000, 1, 1), end=date(2026, 6, 15),
                                                         mode="stock")) is None


def test_stock_card_takes_the_last_record_of_the_day_and_needs_no_later_movement():
    card = shop(ledger=True)
    until = lambda d: ResolvedPeriod(start=date(2000, 1, 1), end=d, mode="stock")  # noqa: E731
    stock = [{"metric": "stock_qty", "filters": product(), "unit": "cái"}]
    assert run(stock, linked=BANH, db=card, period=until(date(2026, 6, 10))) == 48  # the day's last record
    assert run(stock, linked=BANH, db=card, period=until(date(2026, 6, 9))) == 60
    # sold on 11/06 and bought on 20/06 after the last record: the card is not up to date
    assert run(stock, linked=BANH, db=card, period=until(date(2026, 6, 30))) is None
    assert run([{"metric": "stock_qty", "filters": product("nước"), "unit": "chai"}], linked=NUOC, db=card,
               period=until(date(2026, 6, 30))) == 100


def test_a_stock_plan_needs_a_stock_word():
    """check_plans 04/11: "số nhập trừ số bán" read as the stock at the end of the month."""
    from datamate.nlu import grounding
    plan = QueryPlan.model_validate({"intent": "value", "period": {"kind": "month", "month": 3, "year": 2025},
                                     "measures": [{"metric": "stock_qty", "unit": "viên",
                                                   "filters": [{"field": "product", "value": "Telfast"}]}]})
    assert "metric=stock_qty" in grounding.ungrounded_measures(
        "Tháng 3/2025, số nhập trừ số bán của Telfast là bao nhiêu viên?", plan)
    assert grounding.ungrounded_measures("Hết hôm nay, Telfast còn lại mấy viên trong kho?", plan) == []


def test_purchase_minus_sales_in_the_unit_asked():
    """§5 "nhập trừ bán" (N86): receipts of the period (PN4 is May, PN5 cancelled) in base units, minus the base
    quantity of the orders counted in revenue (o2 cancelled). SP1: 10 + 30 boxes of 6 = 240 pieces − (12 + 1 + 6) = 221."""
    def pms(name, unit, linked):
        m = {"metric": "purchase_minus_sales", "filters": product(name)}
        if unit:
            m["unit"] = unit
        return run([m], linked=linked)
    assert pms("bánh", "cái", BANH) == 221
    assert pms("nước", "chai", NUOC) == 96  # 100 bought − 4 sold
    assert pms("bánh", "hộp", BANH) is None  # 221 pieces is no whole number of boxes
    assert pms("bánh", None, BANH) is None  # the unit must be asked


def test_purchase_minus_sales_of_a_product_never_received_is_none():
    """N94: receipts keyed otherwise (or borrowed without products) must not read as "nothing bought"."""
    m = {"metric": "purchase_minus_sales", "filters": product("bánh"), "unit": "cái"}
    assert run([m], linked={"bánh": "SP9"}) is None
