"""N44: industry figures of the public rulebook §6 (repair shop, mother-and-baby shop, phone shop), on tiny shops built
by hand; each expected figure is worked out by hand from the rule the test names."""
from datetime import date, datetime

import pandas as pd

from datamate import metrics
from datamate.contracts import CanonicalDB, QueryPlan, ResolvedPeriod, ResolvedPlan
from datamate.formatter import format_value

JUNE = ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30))


def repair() -> CanonicalDB:
    t = lambda d: datetime(2026, 6, d)  # noqa: E731
    o = pd.DataFrame([
        # id, day, employee, model, plate, money, warranty
        ("r1", t(1), "Đoàn Bảo Phúc", "Wave alpha", "59B6-219.16", 120_000, False),
        ("r2", t(2), "Đoàn Bảo Phúc", "Vision", "72L7-223.37", 300_000, False),
        ("r3", t(3), "Lương Chi Đức", "Wave alpha", "59B6-219.16", 0, True),    # warranty of r1's job
        ("r4", t(4), "Lương Chi Đức", "wave alpha", "50K2-994.07", 180_000, False),
        ("r5", datetime(2026, 5, 30), "Lương Chi Đức", "Vision", "72L7-223.37", 90_000, False),
    ], columns=["order_id", "order_time", "employee", "vehicle_model", "vehicle_plate", "goods_amount", "is_warranty"])
    o["status"], o["has_time"] = "completed", False
    return CanonicalDB(tables={"orders": o})


def run(db, measures, period=JUNE, linked=None, intent="value"):
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"intent": intent, "measures": measures,
                                                       "period": {"kind": "this_month"}}),
                        as_of=date(2026, 6, 30), period=period, linked=linked or {})
    r = metrics.execute(plan, db)
    return None if r is None else format_value(r.answer_type, r.value)


def test_tickets_count_warranty_tickets_too():
    """§6 Sửa xe "lượt xe, phiếu": each row a ticket, warranty tickets included."""
    assert run(repair(), [{"metric": "ticket_count"}]) == 4
    assert run(repair(), [{"metric": "ticket_count", "filters": [{"field": "employee", "value": "Phúc"}]}],
               linked={"Phúc": "Đoàn Bảo Phúc"}) == 2


def test_the_average_ticket_is_over_the_tickets_with_money():
    """§6 "tiền trung bình một phiếu chia cho số phiếu có thu tiền (không tính phiếu bảo hành)": (120+300+180)/3."""
    assert run(repair(), [{"metric": "avg_ticket_value"}]) == 200_000


def test_vehicles_are_distinct_plates_warranty_visits_included():
    """§6 "số chiếc xe mang tới = số biển số khác nhau, tính cả xe chỉ tới bảo hành"; a model whatever its case."""
    assert run(repair(), [{"metric": "vehicle_count"}]) == 3
    assert run(repair(), [{"metric": "vehicle_count", "filters": [{"field": "vehicle_model", "value": "Wave Alpha"}]}],
               linked={"Wave Alpha": "Wave alpha"}) == 2


def test_warranty_rate_is_warranty_tickets_over_tickets_with_money():
    """§6 "tỉ lệ bảo hành = số phiếu bảo hành có ngày trong kỳ / số phiếu có thu tiền trong cùng kỳ": 1/3."""
    assert run(repair(), [{"metric": "warranty_count"}]) == 1
    assert run(repair(), [{"metric": "warranty_rate"}]) == 33.33


def test_voucher_points_and_shipping_are_positive_sums_of_valid_orders():
    """§6 Mẹ và bé: "trả số dương; cộng theo ngày của hoá đơn; chỉ tính hoá đơn không huỷ, không trả"."""
    o = pd.DataFrame([("m1", datetime(2026, 6, 2), "completed", 10_000, 3_000, 25_000),
                      ("m2", datetime(2026, 6, 3), "cancelled", 20_000, None, 25_000),
                      ("m3", datetime(2026, 6, 4), "completed", None, None, 15_000)],
                     columns=["order_id", "order_time", "status", "voucher_discount", "points_discount", "shipping_fee"])
    o["has_time"] = False
    lines = pd.DataFrame({"order_id": ["m1", "m2", "m3"], "product_key": ["S", "S", "S"], "line_amount": [1, 1, 1],
                          "qty": [1, 1, 1], "is_item": [True, True, True]})
    db = CanonicalDB(tables={"orders": o, "lines": lines})
    assert run(db, [{"metric": "voucher_discount"}]) == 10_000
    assert run(db, [{"metric": "points_discount"}]) == 3_000
    assert run(db, [{"metric": "shipping_fee_total"}]) == 40_000


def plan_run(db, raw: dict, period=JUNE, linked=None):
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"period": {"kind": "this_month"}, **raw}),
                        as_of=date(2026, 6, 30), period=period, linked=linked or {})
    r = metrics.execute(plan, db)
    return None if r is None else format_value(r.answer_type, r.value)


def test_an_average_per_weekday_is_over_every_such_day_of_the_period():
    """§2 "trung bình mỗi ngày thứ X của kỳ: chia cho số ngày thứ X trong kỳ, kể cả ngày không có đơn, phiếu".
    01/06/2026 is a Monday: June has 5 Mondays, 5 Tuesdays, 4 Wednesdays. One ticket on Monday 1st: 1/5; the Tuesday
    ticket of 300 000: 300 000/5 = 60 000 đồng; every day: 600 000 / 30 = 20 000. Without the weekday: no answer."""
    on = lambda day: [{"field": "weekday", "value": day}]  # noqa: E731
    assert run(repair(), [{"metric": "ticket_count", "filters": on("mon"), "aggregate": "avg_per_weekday"}]) == 0.2
    assert run(repair(), [{"metric": "ticket_count", "filters": on("wed"), "aggregate": "avg_per_weekday"}]) == 0.25
    assert run(repair(), [{"metric": "revenue", "filters": on("tue"), "aggregate": "avg_per_weekday"}]) == 60_000
    assert run(repair(), [{"metric": "revenue", "aggregate": "avg_per_day"}]) == 20_000
    assert run(repair(), [{"metric": "ticket_count", "aggregate": "avg_per_weekday"}]) is None
    assert run(repair(), [{"metric": "avg_ticket_value", "aggregate": "avg_per_day"}]) is None  # no daily sum


def mechanics() -> CanonicalDB:
    """A: three tickets on one day (one a warranty ticket); B: two tickets on two days. Plates P1 twice with money,
    P2 once with money and once under warranty, P3 twice written in two cases."""
    t = lambda d: datetime(2026, 6, d)  # noqa: E731
    o = pd.DataFrame([
        ("a1", t(1), "A", "P1", 100_000, False), ("a2", t(1), "A", "P2", 100_000, False),
        ("a3", t(1), "A", "P2", 0, True), ("b1", t(2), "B", "59b6-219.16", 100_000, False),
        ("b2", t(3), "B", "59B6-219.16", 100_000, False), ("a4", datetime(2026, 5, 2), "A", "P1", 100_000, False),
        ("c1", t(5), "C", "P1", 50_000, False),
    ], columns=["order_id", "order_time", "employee", "vehicle_plate", "goods_amount", "is_warranty"])
    o["status"], o["has_time"] = "completed", False
    return CanonicalDB(tables={"orders": o})


def test_the_mechanic_who_did_most_counts_tickets_and_the_hardest_working_counts_days():
    """§6 "thợ làm nhiều nhất: theo số lượt xe, kể cả phiếu bảo hành": A has 3 tickets in June, B 2, C 1.
    §3 "thợ chăm chỉ nhất: nhiều ngày làm việc nhất; ngày có ít nhất một đơn, kể cả phiếu bảo hành": A 1 day, B 2."""
    rank = lambda by: plan_run(mechanics(), {"intent": "rank", "rank": {"entity": "employee", "by": by, "k": 1}})  # noqa: E731
    assert rank("ticket_count") == "A" and rank("order_count") == "A"
    assert rank("work_days") == "B"


def test_returning_vehicles_count_only_tickets_with_money():
    """§6 "xe khách quen = xe có từ 2 phiếu có thu tiền trong kỳ; phiếu bảo hành không tính là một lần tới", a vehicle
    by its plate: in June P1 has 2 (a1, c1; a4 is May), P2 1 with money + 1 warranty, 59B6-219.16 2 in two cases."""
    raw = {"intent": "count_where", "threshold": {"entity": "vehicle", "metric": "ticket_count", "op": "gte", "value": 2}}
    assert plan_run(mechanics(), raw) == 2


def with_staff(pcts: dict[str, float | None]) -> CanonicalDB:
    db = mechanics()
    db.tables["employees"] = pd.DataFrame({"employee_key": list(pcts), "employee_name": list(pcts),
                                           "commission_pct": list(pcts.values())})
    return db


def test_commission_is_the_percent_of_the_money_of_the_month_tickets():
    """A repair shop's README: "phần trăm hoa hồng của thợ, tính trên tổng Tiền các phiếu thợ làm trong tháng".
    June: A 200 000 (a1, a2; a3 warranty 0) × 30% = 60 000; B 200 000 × 25% = 50 000; C 50 000 × 33% = 16 500."""
    db = with_staff({"A": 30, "B": 25, "C": 33})
    one = lambda who: [{"metric": "commission", "filters": [{"field": "employee", "value": who}]}]  # noqa: E731
    assert run(db, one("A"), linked={"A": "A"}) == 60_000
    assert run(db, one("C"), linked={"C": "C"}) == 16_500
    assert plan_run(db, {"intent": "rank", "rank": {"entity": "employee", "by": "commission", "k": 1}}) == "A"
    table = plan_run(db, {"intent": "rank", "rank": {"entity": "employee", "by": "commission", "k": None,
                                                     "with_values": True}})
    assert table == {"columns": ["nhan_vien", "hoa_hong"], "rows": [["A", 60_000], ["B", 50_000], ["C", 16_500]]}


def test_no_commission_without_every_percent_or_over_more_than_a_month():
    """Someone of the period without a percent, or a period over two months (the base is a month's money): no answer."""
    assert run(with_staff({"A": 30, "B": 25}), [{"metric": "commission"}]) is None  # C has no percent
    assert run(with_staff({"A": 30, "B": 25, "C": None}), [{"metric": "commission"}]) is None
    two_months = ResolvedPeriod(start=date(2026, 5, 1), end=date(2026, 6, 30))
    assert run(with_staff({"A": 30, "B": 25, "C": 33}), [{"metric": "commission"}], period=two_months) is None
    assert run(mechanics(), [{"metric": "commission"}]) is None  # no staff list


def test_a_shop_without_the_columns_has_no_industry_figure():
    o = pd.DataFrame([("m1", datetime(2026, 6, 2), "completed")], columns=["order_id", "order_time", "status"])
    db = CanonicalDB(tables={"orders": o})
    assert run(db, [{"metric": "voucher_discount"}]) is None
    assert run(db, [{"metric": "vehicle_count"}]) is None
    assert run(db, [{"metric": "warranty_rate"}]) is None


def test_orders_delivered_in_two_batches_or_more_by_today():
    """§6 Vật liệu xây dựng "giao nhiều đợt: tính đến hết hôm nay … đợt đã chở vẫn tính dù đơn sau đó trả hàng".
    Orders of June: A 2 batches, B 1 batch by 20/06 and its 2nd on 25/06 (after today 20/06), C returned with 2
    batches, D none. ≥ 2 batches by today: A and C."""
    o = pd.DataFrame({"order_id": ["A", "B", "C", "D", "E"], "status": ["completed", "completed", "returned",
                                                                         "completed", "completed"],
                      "order_time": [datetime(2026, 6, d) for d in (1, 2, 3, 4)] + [datetime(2026, 5, 30)]})
    d = pd.DataFrame({"order_id": ["A", "A", "B", "B", "C", "C", "E", "E"], "batch_no": [1, 2, 1, 2, 1, 2, 1, 2],
                      "delivery_time": [datetime(2026, 6, x) for x in (2, 5, 3, 25, 4, 6, 1, 2)]})
    db = CanonicalDB(tables={"orders": o, "deliveries": d})
    plan = ResolvedPlan(plan=QueryPlan.model_validate({
        "intent": "count_where", "period": {"kind": "month", "year": 2026, "month": 6},
        "threshold": {"entity": "order", "metric": "delivery_count", "op": "gte", "value": 2}}),
        as_of=date(2026, 6, 20), period=ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 20)))
    assert metrics.execute(plan, db).value == 2
