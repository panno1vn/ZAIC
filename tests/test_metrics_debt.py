"""Debt added and debt paid (§4, v2) on a tiny shop built by hand; each expected figure is worked out by hand from the
rulebook row the test names."""
from datetime import date, datetime

import pandas as pd

from datamate import metrics
from datamate.contracts import CanonicalDB, QueryPlan, ResolvedPeriod, ResolvedPlan
from datamate.formatter import format_value

JUNE = ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30))


def shop() -> CanonicalDB:
    orders = pd.DataFrame([
        # id, time, status, customer, method, total due
        ("o1", datetime(2026, 5, 28, 9), "completed", "KH1", "Ghi nợ", 500_000),   # May debt, paid in June
        ("o2", datetime(2026, 6, 3, 9), "completed", "KH1", "Ghi nợ", 300_000),    # 100 000 paid the same day
        ("o3", datetime(2026, 6, 5, 9), "returned", "KH2", "Ghi nợ", 200_000),     # a returned debt order still counts
        ("o4", datetime(2026, 6, 6, 9), "cancelled", "KH2", "Ghi nợ", 900_000),    # cancelled: never a debt
        ("o5", datetime(2026, 6, 7, 9), "completed", "KH2", "Thu hộ (COD)", 400_000),  # COD is not debt
        ("o6", datetime(2026, 6, 8, 9), "completed", "KH1", "Tiền mặt", 50_000),
    ], columns=["order_id", "order_time", "status", "customer_key", "payment_method", "total_due"])
    lines = pd.DataFrame({"order_id": orders["order_id"], "product_key": "SP1", "qty": 1,
                          "line_amount": orders["total_due"]})
    payments = pd.DataFrame([
        ("o1", datetime(2026, 6, 2, 10), 200_000),
        ("o2", datetime(2026, 6, 3, 18), 100_000),    # same day as the purchase: paid at purchase
        ("o2", datetime(2026, 6, 20, 10), 50_000),
        ("o3", datetime(2026, 7, 1, 10), 200_000),    # July: not in June
        ("o3", datetime(2026, 6, 9, 10), -30_000),    # a refund: not subtracted
        ("o4", datetime(2026, 6, 10, 10), 900_000),   # cancelled order
        ("o5", datetime(2026, 6, 12, 10), 400_000),   # COD collected later: not a debt payment
        ("o6", datetime(2026, 6, 8, 9), 50_000),
    ], columns=["order_id", "paid_time", "amount"])
    return CanonicalDB(tables={"orders": orders, "lines": lines, "payments": payments})


def run(measures, linked=None):
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"intent": "value", "measures": measures,
                                                       "period": {"kind": "this_month"}}),
                        as_of=date(2026, 6, 30), period=JUNE, linked=linked or {})
    r = metrics.execute(plan, shop())
    return None if r is None else format_value(r.answer_type, r.value)


def test_debt_paid_counts_later_payments_of_every_debt_order_in_the_period():
    # §4: o1 200 000 (a May order) + o2 50 000 (after the day of purchase); not o2's same-day 100 000, o3's July
    # payment, o3's refund, cancelled o4, COD o5
    assert run([{"metric": "debt_paid"}]) == 250_000


def test_debt_added_is_what_debt_orders_of_the_period_left_unpaid_on_their_day():
    # §4: o2 300 000 − 100 000 + o3 200 000 (returned, still a debt order); o1 is May, o4 cancelled, o5 COD
    assert run([{"metric": "debt_added"}]) == 400_000


def owed(raw, day=date(2026, 6, 30), db=None):
    plan = ResolvedPlan(plan=QueryPlan.model_validate({**raw, "period": {"kind": "until", "date": day.isoformat()}}),
                        as_of=date(2026, 6, 30), linked={"chị lan": "KH1"},
                        period=ResolvedPeriod(start=date(2000, 1, 1), end=day, mode="stock"))
    r = metrics.execute(plan, db or shop())
    return None if r is None else format_value(r.answer_type, r.value)


def test_what_is_still_owed_at_the_end_of_a_day():
    # §4 at 30/06: o1 500 000 − 200 000 = 300 000; o2 300 000 − 150 000 = 150 000; o3 (returned, still owing; the
    # July payment and the refund do not count) 200 000. Not cancelled o4, not COD o5, o6 paid.
    assert owed({"intent": "value", "measures": [{"metric": "debt_total"}]}) == 650_000
    assert owed({"intent": "value", "measures": [{"metric": "debtor_count"}]}) == 2
    customer = [{"field": "customer", "value": "chị lan"}]
    assert owed({"intent": "value", "measures": [{"metric": "debt_amount", "filters": customer}]}) == 450_000
    # at 01/06 only o1 is placed and nothing paid yet
    assert owed({"intent": "value", "measures": [{"metric": "debt_total"}]}, day=date(2026, 6, 1)) == 500_000
    top = {"intent": "rank", "rank": {"entity": "customer", "by": "debt_amount", "k": 2, "with_values": True}}
    assert owed(top) == {"columns": ["khach_hang", "so_tien_no"], "rows": [["KH1", 450_000], ["KH2", 200_000]]}


def test_an_unpaid_order_of_another_method_makes_the_debt_unreadable():
    db = shop()
    db.tables["payments"] = db.tables["payments"][db.tables["payments"]["order_id"] != "o6"]  # cash order unpaid
    assert owed({"intent": "value", "measures": [{"metric": "debt_total"}]}, db=db) is None


def test_one_customers_added_and_paid_debt_in_the_order_asked():
    customer = [{"field": "customer", "value": "chị lan"}]
    assert run([{"metric": "debt_added", "filters": customer}, {"metric": "debt_paid", "filters": customer}],
               linked={"chị lan": "KH1"}) == [200_000, 250_000]
    assert run([{"metric": "debt_paid", "filters": customer}]) is None  # name not linked: no answer


def test_what_the_orders_older_than_n_days_still_owe():
    """N163 / N164: "tổng số tiền khách còn nợ ở các đơn đã đặt quá N ngày" without a customer is the balances of the
    orders of that age (§4 "tuổi nợ" from the day of the order); "quá / hơn 27 ngày" is older than 27, also when the
    plan writes ≥ 27."""
    from datamate import nlu
    # at 30/06: o1 (28/05, 33 days) 300 000, o2 (03/06, 27 days) 150 000, o3 (05/06, 25 days) 200 000
    older = lambda op: {"intent": "value", "measures": [  # noqa: E731
        {"metric": "debt_amount", "filters": [{"field": "debt_age_days", "op": op, "value": 27}]}]}
    assert owed(older("gt")) == 300_000
    assert owed(older("gte")) == 450_000
    q = "Tính đến hết ngày 30/06/2026, các đơn đặt đã hơn 27 ngày mà khách chưa trả hết còn nợ bao nhiêu tiền?"
    raw = {**older("gte"), "period": {"kind": "until", "date": "2026-06-30"}}
    p = nlu.accept_plan(q, QueryPlan.model_validate(raw), date(2026, 6, 30))
    assert p is not None and p.measures[0].filters[0].op == "gt"
    # a bound the question does not write as "quá / hơn / trên N ngày" stays
    p = nlu.accept_plan("nợ của các đơn từ 27 ngày trở lên", QueryPlan.model_validate(raw), date(2026, 6, 30))
    assert p is None or p.measures[0].filters[0].op == "gte"
