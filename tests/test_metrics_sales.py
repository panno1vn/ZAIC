"""Sales metrics (T3) on a tiny shop built by hand; each expected figure is worked out by hand from the rulebook row
the test names."""
from datetime import date, datetime

import pandas as pd
import pytest

from datamate import metrics
from datamate.contracts import CanonicalDB, QueryPlan, ResolvedPeriod, ResolvedPlan
from datamate.formatter import format_value
from datamate.mapping.build import blank_walk_ins
from datamate.nlu import grounding

JUNE = ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30))
MAY = ResolvedPeriod(start=date(2026, 5, 1), end=date(2026, 5, 31))


def shop() -> CanonicalDB:
    t = lambda d, h=9: datetime(2026, d[0], d[1], h)  # noqa: E731
    orders = pd.DataFrame([
        # id, time, status, customer, group, payment, channel
        ("o1", t((6, 1), 9), "completed", "KH1", "thân thiết", "cash", "store"),
        ("o2", t((6, 1), 15), "completed", "KH2", "sỉ", "Tiền mặt", "zalo_oa"),
        ("o3", t((6, 2), 10), "delivering", None, "lẻ", "transfer", "store"),   # walk-in, group "lẻ" written
        ("o4", t((6, 2), 16), "cancelled", "KH1", "thân thiết", "cash", "store"),
        ("o5", t((6, 3), 11), "returned", "KH2", "sỉ", "cod", "phone"),          # partial return: whole order out
        ("o6", t((5, 20), 9), "completed", "KH1", "thân thiết", "cash", "store"),
        ("o7", t((6, 3), 23), "completed", "KH2", "sỉ", "cash", "store"),       # 23:00: neither shift
    ], columns=["order_id", "order_time", "status", "customer_key", "customer_group", "payment_method", "channel"])
    orders["customer_name"] = orders["customer_key"].map({"KH1": "Chị Lan", "KH2": "Anh Minh"})
    orders["has_time"] = True
    orders["employee"] = ["NV1", "NV2", "NV1", "NV1", "NV2", "NV2", "NV2"]
    lines = pd.DataFrame([
        # order, key, name, qty, unit, base_qty, amount, is_item
        ("o1", "SP1", "Cà phê đen (M)", 2, "ly", 2, 50_000, True),
        ("o1", "SP3", "Bia Tiger lon", 1, "thùng", 24, 300_000, True),
        ("o1", "FEE", "Phí phục vụ", 1, None, None, 5_000, False),
        ("o2", "SP2", "Cà phê đen (L)", 3, "ly", 3, 105_000, True),
        ("o3", "SP1", "Cà phê đen (M)", 1, "ly", 1, 25_001, True),
        ("o4", "SP2", "Cà phê đen (L)", 5, "ly", 5, 175_000, True),
        ("o5", "SP3", "Bia Tiger lon", 6, "lon", 6, 90_000, True),
        ("o6", "SP4", "Bánh flan", 1, "cái", 1, 15_000, True),
        ("o6", "SP1", "Cà phê đen (M)", 1, "ly", 1, 25_000, True),
        ("o7", "SP3", "Bia Tiger lon", 2, "lon", 2, 30_000, True),
    ], columns=["order_id", "product_key", "product_name", "qty", "unit", "base_qty", "line_amount", "is_item"])
    products = pd.DataFrame({"product_key": ["SP1", "SP2", "SP3", "SP4"],
                             "product_group": ["cà phê", "cà phê", "bia", "bánh"],
                             "base_unit": ["ly", "ly", "lon", "cái"]})
    return CanonicalDB(tables={"orders": orders, "lines": lines, "products": products})


def run(raw: dict, period=JUNE, linked=None, **extra):
    plan = ResolvedPlan(plan=QueryPlan.model_validate(raw), as_of=date(2026, 6, 30), period=period,
                        linked=linked or {}, **extra)
    r = metrics.execute(plan, shop())
    return None if r is None else format_value(r.answer_type, r.value)


def value(metric, filters=(), unit=None, **kw):
    m = {"metric": metric, "filters": list(filters)}
    if unit:
        m["unit"] = unit
    return run({"intent": "value", "measures": [m], "period": {"kind": "this_month"}}, **kw)


def test_revenue_counts_valid_orders_their_fee_lines_and_not_cancelled_or_returned():
    # §1: o1 355 000 (fee line included) + o2 105 000 + o3 25 001 (in delivery) + o7 30 000; o4 cancelled, o5 returned
    assert value("revenue") == 515_001
    assert value("order_count") == 4


def test_filters_on_products_and_orders():
    assert value("revenue", [{"field": "product_group", "value": "cà phê"}], linked={"cà phê": "cà phê"}) == 180_001
    # §1 "số đơn có một mặt hàng": valid orders with the product
    assert value("order_count", [{"field": "product", "value": "bia"}], linked={"bia": "SP3"}) == 2
    # §1 payment: the method written on the order, codes and words alike
    assert value("revenue", [{"field": "payment_method", "value": "tiền mặt"}], linked={"tiền mặt": "cash"}) == 490_000
    # §6 size: names ending in (M)
    assert value("quantity", [{"field": "size", "value": "M"}], unit="ly") == 3
    # an unlinked name: no answer
    assert value("revenue", [{"field": "product", "value": "trà"}]) is None


def test_customer_group_excludes_walk_in_orders_even_group_le():
    # §1: o3 is a walk-in order written in group "lẻ": it belongs to no group
    assert value("revenue", [{"field": "customer_group", "value": "lẻ"}], linked={"lẻ": "lẻ"}) == 0
    assert value("revenue", [{"field": "customer_group", "value": "sỉ"}], linked={"sỉ": "sỉ"}) == 135_000


def test_cancel_rate_over_every_order_of_the_period_and_cancel_count():
    assert value("cancel_rate") == pytest.approx(16.67)  # §1: 1 cancelled of 6 June orders, every status
    assert value("cancel_count") == 1


def test_average_order_value_in_whole_dong_half_up():
    assert value("avg_order_value") == 128_750  # §3: 515 001 / 4 = 128 750.25


def test_quantity_counts_products_whose_base_unit_is_the_unit_asked():
    assert value("quantity", unit="ly") == 6  # §3: o1 2 + o2 3 + o3 1; beer is counted in lon
    assert value("quantity", unit="lon") == 26  # a thùng sold counts as 24 lon (base units)
    assert value("quantity", [{"field": "product", "value": "bia"}], unit="lon", linked={"bia": "SP3"}) == 26
    # a product asked in a unit that is not its base unit: no rule, no answer
    assert value("quantity", [{"field": "product", "value": "bia"}], unit="thùng", linked={"bia": "SP3"}) is None
    # N34: a unit the shop never writes ("ly ta": "ta" a particle read as a unit) is no unit of this shop: no answer,
    # not 0 (train 05/11, [214, 0] for "mấy ly ... tính theo ly ta"); a unit it writes but did not sell is 0
    assert value("quantity", unit="ly ta") is None
    assert value("quantity", unit="cái", period=ResolvedPeriod(start=date(2026, 4, 1), end=date(2026, 4, 30))) == 0


def test_shift_by_order_hour():
    # §2: ca sáng 06:00–13:59 (o1, o3), ca chiều 14:00–21:59 (o2); o7 at 23:00 is in neither
    assert value("revenue", [{"field": "shift", "value": "morning"}]) == 380_001
    assert value("revenue", [{"field": "shift", "value": "afternoon"}]) == 105_000


def test_compare_periods_and_filters():
    raw = {"intent": "compare", "measures": [{"metric": "revenue"}], "period": {"kind": "month", "month": 6},
           "compare": {"kind": "previous"}}
    may = ResolvedPeriod(start=date(2026, 5, 1), end=date(2026, 5, 31))
    assert run(raw, compare_period=may) == pytest.approx((515_001 - 40_000) / 40_000 * 100, abs=0.01)
    assert run({**raw, "compare": {"kind": "previous", "output": "diff"}}, compare_period=may) == 475_001
    # §2: ca chiều vs ca sáng, the base is ca sáng
    shifts = {"intent": "compare", "period": {"kind": "this_month"},
              "measures": [{"metric": "revenue", "filters": [{"field": "shift", "value": "afternoon"}]}],
              "compare": {"kind": "filter", "filters": [{"field": "shift", "value": "morning"}]}}
    assert run(shifts, compare_period=JUNE) == pytest.approx((105_000 - 380_001) / 380_001 * 100, abs=0.01)


def test_share_divides_by_the_whole_shop_walk_ins_and_fees_included():
    raw = {"intent": "share", "period": {"kind": "this_month"},
           "measures": [{"metric": "revenue", "filters": [{"field": "product_group", "value": "bia"}]}]}
    assert run(raw, linked={"bia": "bia"}) == pytest.approx(330_000 / 515_001 * 100, abs=0.01)


def rank(entity, by, k=1):
    return run({"intent": "rank", "period": {"kind": "this_month"}, "rank": {"entity": entity, "by": by, "k": k}})


def test_rankings_ties_by_code_walk_ins_not_ranked():
    # §3 bán chạy in base units: SP3 26 lon; SP1 and SP2 3 ly each, tie by code (§9): SP1 first; fee line not ranked
    assert rank("product", "quantity", 2) == ["Bia Tiger lon", "Cà phê đen (M)"]
    # §3 xác định khách: KH1 355 000, KH2 135 000; the walk-in order o3 is no customer
    assert rank("customer", "revenue", 2) == ["Chị Lan", "Anh Minh"]
    assert rank("employee", "revenue") == "NV1"  # §3 nhân viên bán giỏi nhất: NV1 380 001 > NV2 135 000
    assert rank("day", "revenue") == "2026-06-01"
    assert rank("day", "order_count", 2) == ["2026-06-01", "2026-06-02"]  # 06-02 and 06-03 tie: earlier first


def count(entity, metric, op, v, as_share=False, filters=()):
    raw = {"intent": "count_where", "period": {"kind": "this_month"},
           "threshold": {"entity": entity, "metric": metric, "op": op, "value": v, "as_share": as_share}}
    return run(raw)


def test_count_over_a_threshold():
    assert count("order", "revenue", "gte", 105_000) == 2  # §2 "từ N trở lên" includes N: o1, o2
    assert count("order", "revenue", "gt", 105_000) == 1  # "quá N" does not
    assert count("day", "revenue", "gte", 30_000) == 2  # 06-01 460 000, 06-03 30 000; 06-02 25 001
    assert count("customer", "order_count", "gte", 2, as_share=True) == 50.0  # KH2 2 orders of 2 customers who bought
    assert count("product", "order_presence", "gte", 2) == 2  # SP1 in o1, o3; SP3 in o1, o7


def test_unsold_products_were_sold_before_the_period():
    raw = {"intent": "list_items", "period": {"kind": "this_month"},
           "list_spec": {"entity": "product", "condition": "unsold_in_period", "count": True}}
    assert run(raw) == 1  # §5: sold in May (SP4, SP1), SP1 sold again in June: only SP4 is "ế"
    assert run({**raw, "list_spec": {**raw["list_spec"], "count": False}}) == ["Bánh flan"]


def test_trend_and_series_by_month():
    raw = {"intent": "trend", "measures": [{"metric": "revenue"}],
           "period": {"kind": "months", "months": ["2026-05", "2026-06"]}}
    assert run(raw, series=[MAY, JUNE]) is True  # 40 000 then 515 001
    assert run({**raw, "intent": "series"}, series=[MAY, JUNE]) == [40_000, 515_001]


def test_walk_in_spellings_have_no_customer_key():
    db = CanonicalDB(tables={"orders": pd.DataFrame({"customer_key": ["KH1", "kl", "Khách lẻ", " ", None, "Lan"]})})
    blank_walk_ins(db)
    assert db.tables["orders"]["customer_key"].tolist() == ["KH1", None, None, None, None, "Lan"]


def test_days_and_years_of_a_plan_must_be_in_the_question():
    """T3 run 03/11: with no date in the question the LLM wrote today as the day of a price rise."""
    rise = QueryPlan.model_validate({"intent": "compare", "measures": [{"metric": "quantity"}],
                                     "period": {"kind": "days_from", "date": "2026-05-25", "n": 7},
                                     "compare": {"kind": "before_days_from"}})
    q = "Acemuc Kids tăng giá lên 3.200đ: so 7 ngày kể từ ngày tăng với 7 ngày ngay trước"
    assert grounding.ungrounded_dates(q, rise, date(2026, 5, 25)) == ["date=2026-05-25"]
    assert grounding.ungrounded_dates("từ ngày 25/05/2026, so 7 ngày", rise, date(2026, 5, 25)) == []
    # 04/11: the question writes the year, the plan another one
    assert grounding.ungrounded_dates("lên giá từ ngày 25/05/2025, so 7 ngày", rise, date(2026, 9, 20)) == [
        "date=2026-05-25"]
    assert grounding.ungrounded_dates("lên giá từ ngày 25/5, so 7 ngày", rise, date(2026, 9, 20)) == []  # no year
    february = QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "order_count"}],
                                         "period": {"kind": "month", "month": 2, "year": 2025}})
    assert grounding.ungrounded_dates("so don quy 2/2025 la bn", february) == ["kind=month"]  # 04/11
    assert grounding.ungrounded_dates("so don thang 2/2025 la bn", february) == []
    until = QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "revenue"}],
                                      "period": {"kind": "range", "start": "2026-01-01", "end": "2026-05-25"}})
    assert grounding.ungrounded_dates("từ 1/1 đến hết hôm nay", until, date(2026, 5, 25)) == []
    months = QueryPlan.model_validate({"intent": "series", "measures": [{"metric": "revenue"}],
                                       "period": {"kind": "months", "months": ["2025-08", "2025-09", "2025-10"]}})
    assert grounding.ungrounded_dates("từ tháng 8/2025 đến tháng 10/2025", months) == []  # September implied
    june = QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "revenue"}],
                                     "period": {"kind": "month", "month": 6, "year": 2026}})
    assert grounding.drop_ungrounded_years("doanh thu tháng 6", june, date(2026, 5, 25)).period.year is None
    assert grounding.drop_ungrounded_years("doanh thu tháng 6/2026", june, date(2026, 5, 25)).period.year == 2026


def test_what_a_plan_measures_must_be_asked_by_the_question():
    """Oracle run 03/11 with the LLM: the 2 wrong answers of 790 were misread questions."""
    shifts = QueryPlan.model_validate({"intent": "compare", "period": {"kind": "last_week"},
                                       "measures": [{"metric": "revenue", "filters": [{"field": "shift", "value": "afternoon"}]}],
                                       "compare": {"kind": "filter", "filters": [{"field": "shift", "value": "morning"}]}})
    assert grounding.ungrounded_measures("tuần rồi, số ddown ca chiều tăng hay giảm bao nhiu % so vs ca sáng",
                                         shifts) == ["metric=revenue"]
    assert grounding.ungrounded_measures("tuần rồi doanh thu ca chiều tăng hay giảm bao nhiu % so với ca sáng",
                                         shifts) == []
    unsold = QueryPlan.model_validate({"intent": "list_items", "period": {"kind": "last_n_days", "n": 7},
                                       "list_spec": {"entity": "product", "condition": "unsold_in_period"}})
    q = "trong 7 ngay gan nhat co bao nhieu mat hang ko ban duoc cai nao"
    assert grounding.ungrounded_measures(q, unsold) == ["count=false"]
    assert grounding.ungrounded_measures("liệt kê những mặt hàng 7 ngày gần nhất không bán được", unsold) == []
    best = QueryPlan.model_validate({"intent": "rank", "period": {"kind": "month", "month": 12},
                                     "rank": {"entity": "employee", "by": "revenue"}})
    assert grounding.ungrounded_measures("Nhân viên bán giỏi nhất tháng 12/2025 là ai?", best) == []  # §3: by revenue


def test_gross_profit_takes_the_cost_written_on_each_sale_line():
    def costed(beer_cost=200_000) -> CanonicalDB:
        db = shop()
        db.tables["lines"]["unit_cost"] = [20_000, beer_cost, None, 30_000, 20_000, 30_000, 10_000, 8_000, 20_000,
                                           10_000]
        db.tables["expenses"] = pd.DataFrame({"expense_date": [date(2026, 6, 5), date(2026, 5, 5)],
                                              "amount": [100_000, 999]})
        return db
    db = costed()
    plan = lambda raw: ResolvedPlan(plan=QueryPlan.model_validate(raw), as_of=date(2026, 6, 30),  # noqa: E731
                                    period=JUNE)
    # §5: revenue 515 001 (fee line included, it costs nothing) − cost of the valid orders' items:
    # o1 2 × 20 000 + 1 × 200 000, o2 3 × 30 000, o3 1 × 20 000, o7 2 × 10 000 = 370 000
    total = plan({"intent": "value", "measures": [{"metric": "gross_profit"}], "period": {"kind": "this_month"}})
    assert metrics.execute(total, db).value == 145_001
    # §3 "hàng lời nhất": by total gross profit — beer 300 000 − 200 000 + 30 000 − 20 000 = 110 000,
    # coffee (M) 50 000 − 40 000 + 25 001 − 20 000 = 15 001, coffee (L) 105 000 − 90 000 = 15 000
    best = plan({"intent": "rank", "rank": {"entity": "product", "by": "gross_profit", "k": 2},
                 "period": {"kind": "this_month"}})
    assert metrics.execute(best, db).value == ["Bia Tiger lon", "Cà phê đen (M)"]
    # §5 "lãi ròng": gross profit − June's expenses (not May's)
    net = plan({"intent": "value", "measures": [{"metric": "net_profit"}], "period": {"kind": "this_month"}})
    assert metrics.execute(net, db).value == 45_001
    assert metrics.execute(total, costed(beer_cost=None)) is None  # an item line with no cost: no profit to tell
    # check_plans 04/11: "lợi nhuận ròng" read as gross profit
    assert grounding.ungrounded_measures("Lợi nhuận ròng tháng 6 năm 2025 là bao nhiêu?", total.plan) == [
        "asks=net_profit"]


def test_an_order_without_status_withholds_only_the_figures_it_could_change():
    db = shop()
    db.tables["orders"].loc[db.tables["orders"]["order_id"] == "o6", "status"] = None  # a May order
    may = ResolvedPeriod(start=date(2026, 5, 1), end=date(2026, 5, 31))
    revenue = {"intent": "value", "measures": [{"metric": "revenue"}], "period": {"kind": "this_month"}}
    ask = lambda period: metrics.execute(ResolvedPlan(plan=QueryPlan.model_validate(revenue),  # noqa: E731
                                                      as_of=date(2026, 6, 30), period=period), db)
    assert ask(JUNE).value == 515_001  # June does not hold it
    assert ask(may) is None  # May does: completed or cancelled, nobody knows


def _product_measure(metric: str, period: dict) -> QueryPlan:
    return QueryPlan.model_validate({"intent": "value", "period": period, "measures": [
        {"metric": metric, "unit": "viên", "filters": [{"field": "product", "value": "Fugacar 500mg hộp 1 viên"}]}]})


def test_questions_the_sales_metrics_do_not_measure_are_not_read_as_sales():
    """Oracle run 04/11 (790 questions, examples of other businesses only): its 7 wrong answers."""
    until = _product_measure("quantity", {"kind": "until", "date": "2026-06-12"})
    for q in ("Cuối ngày hôm nay Fugacar 500mg hộp 1 viên còn bao nhiêu viên?",
              "hết hnay, Fugacar 500mg hộp 1 viên còn lại mấy viên trong kho",
              "Hôm nay kho còn tồn bao nhiêu viên Fugacar 500mg hộp 1 viên lúc cuối ngày nhỉ?"):
        assert "asks=stock" in grounding.ungrounded_measures(q, until)
        assert "metric=quantity" in grounding.ungrounded_measures(q, until)  # no word for selling either
    day = _product_measure("revenue", {"kind": "day", "date": "2026-03-19"})
    assert grounding.ungrounded_measures("hôm 19/03/2026, Fugacar 500mg hộp 1 viên bán ra với đơn giá bao nhiêu tiền "
                                         "một viên?", day) == ["asks=unit_price"]
    month = _product_measure("quantity", {"kind": "month", "month": 3, "year": 2025})
    assert grounding.ungrounded_measures("Tháng 3/2025, số nhập trừ số bán của Fugacar 500mg hộp 1 viên là bao nhiêu "
                                         "viên?", month) == ["asks=purchase"]
    unsold = QueryPlan.model_validate({"intent": "list_items", "period": {"kind": "range", "start": "2026-06-25",
                                                                          "end": "2026-07-01"},
                                       "list_spec": {"entity": "product", "condition": "unsold_in_period"}})
    q = "giai đoạn từ 25/06/2026 đến heets 01/07/2026 có tổng cộng mấy mặt hàng ees, bán ko dc món nào hả"
    assert grounding.ungrounded_measures(q, unsold) == ["count=false"]
    # the same words in questions that do ask about sales
    assert grounding.ungrounded_measures("Tháng 8/2025 bán ra bao nhiêu viên Fugacar 500mg hộp 1 viên?", month) == []
    other = _product_measure("revenue", {"kind": "month", "month": 8, "year": 2026})
    assert grounding.ungrounded_measures("Trừ thuốc kê đơn ra, tháng 8/2026 các mặt hàng còn lại bán được bao nhiêu "
                                         "tiền?", other) == []
    assert grounding.ungrounded_measures("Doanh thu của Tôn lạnh Hoa Sen 0.4mm trong tháng 7 năm 2025?", other) == []


def test_misreadings_found_on_the_shops_mapped_automatically():
    """04/11, the export family mapped by transfer: three questions the LLM misread."""
    week = QueryPlan.model_validate({"intent": "value", "period": {"kind": "this_week"}, "measures": [
        {"metric": "revenue", "filters": [{"field": "weekday", "op": "in", "value": "mon"}]}]})
    assert grounding.ungrounded_filters("tuần nayf dthu đươc bao nhiêu", week) == ["weekday=mon"]  # "thu" of "doanh thu"
    assert grounding.ungrounded_filters("doanh thu các thứ 2 tuần này", week) == []
    unsold = QueryPlan.model_validate({"intent": "list_items", "period": {"kind": "range", "start": "2025-10-07",
                                                                          "end": "2025-10-13"},
                                       "list_spec": {"entity": "product", "condition": "unsold_in_period"}})
    assert grounding.ungrounded_measures("từ 07/10/2025 đến hết 13/10/2025, bao nhiu mặt hàng bị ế", unsold) == [
        "count=false"]
    cups = QueryPlan.model_validate({"intent": "value", "period": {"kind": "month", "month": 4, "year": 2025},
                                     "measures": [{"metric": "quantity", "unit": "ly",
                                                   "filters": [{"field": "size", "value": "L"}]},
                                                  {"metric": "revenue", "filters": [{"field": "size", "value": "L"}]}]})
    assert "metric=revenue" in grounding.ungrounded_measures("quan ban duoc bn ly size l trong thang 4/2025", cups)
    assert grounding.ungrounded_measures("thang 4/2025 ban duoc bn ly size l va bao nhieu tien", cups) == []


def test_a_shift_filter_needs_the_shift_word():
    """Run 04/11: "bán Chả cá chiên được bao nhiêu tiền" read as the afternoon shift ("ca" is also "cá")."""
    plan = QueryPlan.model_validate({"intent": "value", "period": {"kind": "month", "month": 8, "year": 2025},
                                     "measures": [{"metric": "revenue",
                                                   "filters": [{"field": "shift", "value": "afternoon"}]}]})
    assert grounding.ungrounded_filters("thang 8/2025 ban Cha ca chien dc bao nhieu tien", plan) == [
        "shift=afternoon"]
    assert grounding.ungrounded_filters("Tháng 4/2026 ca chiều bán được bao nhiêu tiền?", plan) == []


def test_an_order_status_filter_on_a_cancel_metric_is_dropped():
    from datamate.nlu import accept_plan
    plan = QueryPlan.model_validate({"intent": "value", "period": {"kind": "month", "month": 3, "year": 2026},
                                     "measures": [{"metric": "cancel_rate",
                                                   "filters": [{"field": "order_status", "value": "cancelled"}]}]})
    kept = accept_plan("trong tháng 3/2026, tỉ lệ đơn huỷ là nhiêu %", plan, date(2026, 5, 1))
    assert kept is not None and kept.measures[0].filters == []


def test_a_walk_in_spelling_never_met_is_known_by_its_share_of_orders():
    """N33: walk-ins are 39-41% of the orders of every train shop that records customers, the most frequent real
    customer 0.6% at most (05/11). A spelling of "khách lẻ" no train file used would otherwise be the best customer
    by orders and by revenue, and one customer too many in every count."""
    keys = ["Khách hàng lẻ"] * 40 + [f"KH{i:02d}" for i in range(50) for _ in range(1)] + ["KH01"] * 4 + ["KH02"] * 6
    db = CanonicalDB(tables={"orders": pd.DataFrame({"customer_key": keys})})
    blank_walk_ins(db)
    o = db.tables["orders"]["customer_key"]
    assert o.isna().sum() == 40 and o.notna().sum() == 60
    assert "Khách hàng lẻ" in " ".join(db.warnings)
    # a shop of real customers, one buying often: nobody is taken for a walk-in
    few = ["KH1"] * 6 + ["KH2"] * 5 + ["KH3"] * 5 + ["KH4"] * 4
    db = CanonicalDB(tables={"orders": pd.DataFrame({"customer_key": few})})
    blank_walk_ins(db)
    assert db.tables["orders"]["customer_key"].notna().all()


def test_a_shop_without_base_quantities_gives_no_quantity_rather_than_an_error():
    """05/11: a mapping without lines.base_qty (an unfamiliar shop) made quantity and ranking raise KeyError."""
    db = shop()
    db.tables["lines"] = db.tables["lines"].drop(columns=["base_qty"])
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "quantity"}],
                                                       "period": {"kind": "this_month"}}),
                        as_of=date(2026, 6, 30), period=JUNE)
    assert metrics.execute(plan, db) is None
    top = ResolvedPlan(plan=QueryPlan.model_validate({"intent": "rank", "measures": [{"metric": "quantity"}],
                                                      "period": {"kind": "this_month"},
                                                      "rank": {"entity": "product", "by": "quantity", "k": 1}}),
                       as_of=date(2026, 6, 30), period=JUNE)
    assert metrics.execute(top, db) is None
