"""Readings of the public repair shop's questions (06/11) that the LLM wrote wrong in a way with one meaning, each
rewritten into that meaning before the gates; and the shapes the gates still refuse."""
from datetime import date

from datamate import nlu
from datamate.contracts import QueryPlan
from datamate.nlu import grounding, repair

AS_OF = date(2026, 8, 31)


def plan(raw: dict) -> QueryPlan:
    return QueryPlan.model_validate(raw)


def test_a_table_of_every_one_is_every_one():
    raw = {"intent": "rank", "period": {"kind": "month", "year": 2026, "month": 7},
           "rank": {"entity": "employee", "by": "commission", "k": 1, "with_values": True}}
    q = "Bảng hoa hồng thợ th7/2026, ai nhiều tiền thì xếp lên trên nghe."
    assert grounding.widen_each_table(q, plan(raw)).rank.k is None
    assert grounding.widen_each_table("Hoa hồng từng thợ th 3/26", plan(raw)).rank.k is None
    assert grounding.widen_each_table("thợ nào hoa hồng cao nhất th7, bao nhiêu", plan(raw)).rank.k == 1
    assert grounding.widen_each_table("bảng 3 thợ hoa hồng cao nhất", plan(raw)).rank.k == 1  # the stated 3 decides


def test_month_slash_short_year_is_a_month():
    raw = {"intent": "rank", "period": {"kind": "day", "date": "2026-03-26"},
           "rank": {"entity": "employee", "by": "revenue", "k": 1}}
    p = grounding.month_of_short_year("3/26 thợ mô làm ra nhiều tiền nhất rứa?", plan(raw)).period
    assert (p.kind, p.year, p.month) == ("month", 2026, 3)
    assert grounding.month_of_short_year("ngày 26/03/2026 thợ nào làm nhiều nhất", plan(raw)).period.kind == "day"


def test_a_quarter_without_its_number_takes_the_questions():
    raw = {"intent": "value", "period": {"kind": "quarter", "year": 2025}, "measures": [{"metric": "warranty_rate"}]}
    q = "Quý 4/2025 phiếu bảo hành chiếm bnhiu % số phiếu thu tiền rứa?"
    fixed = repair.repair(raw, q, "period quarter thiếu ['quarter']")
    assert fixed["period"] == {"kind": "quarter", "year": 2025, "quarter": 4}
    assert repair.repair(raw, "quý 2 và quý 3 năm 2025", "period quarter thiếu ['quarter']") is None


def test_a_warranty_filter_that_restates_the_metric_is_dropped():
    raw = {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 8},
           "measures": [{"metric": "avg_ticket_value", "filters": [{"field": "is_warranty", "value": False}]}]}
    kept, problems = nlu.plan_problems("Phiếu có thu tiền tháng 8 năm 2025 trung bình 1 phiếu bao nhiêu tiền hè?",
                                       plan(raw), AS_OF)
    assert not problems and kept.measures[0].filters == []
    counted = {**raw, "measures": [{"metric": "ticket_count", "filters": [{"field": "is_warranty", "value": False}]}]}
    assert nlu.plan_problems("Th2/2026 tiệm lên bnhiu phiếu sửa xe?", plan(counted), AS_OF)[1]  # nothing says so


def test_orders_with_at_least_one_order_are_the_orders():
    raw = {"intent": "count_where", "period": {"kind": "this_month"},
           "measures": [{"metric": "ticket_count", "filters": [{"field": "service", "value": "vá ruột"}]}],
           "threshold": {"entity": "order", "metric": "ticket_count", "op": "gte", "value": 1}}
    p = grounding.count_as_value(plan(raw))
    assert p.intent == "value" and p.measures[0].metric == "ticket_count" and p.measures[0].filters[0].value == "vá ruột"
    other = {**raw, "threshold": {**raw["threshold"], "value": 2}}  # a real bound stays a count
    assert grounding.count_as_value(plan(other)).intent == "count_where"


def test_two_short_years_are_last_year_and_never_the_month_before():
    """run10 (06/11): "Dthu tháng 7/26 so với tháng 7/25" refused by a gate that only knew 4-digit years; "Th 6/26 so
    với th 6/25" read as June against May."""
    period = {"kind": "month", "year": 2026, "month": 7}
    last_year = {"intent": "compare", "period": period, "measures": [{"metric": "revenue"}],
                 "compare": {"kind": "same_period_last_year"}}
    q = "Dthu tháng 7/26 so với tháng 7/25 tăng hay giảm bnhiu %?"
    assert not grounding.ungrounded_measures(q, plan(last_year))
    previous = {**last_year, "compare": {"kind": "previous"}}
    assert "compare=previous" in grounding.ungrounded_measures("Th 6/26 dthu so với th 6/25 tăng hay giảm mấy %?",
                                                               plan(previous))
    assert not grounding.ungrounded_measures("Dthu tháng 1/2026 so với tháng 12/2025 tăng hay giảm mấy %?",
                                             plan(previous))  # the month before, across the new year


def test_a_debt_code_on_a_debt_metric_restates_it():
    raw = {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 12},
           "measures": [{"metric": "debt_paid", "filters": [{"field": "payment_method", "value": "debt"}]}]}
    kept, problems = nlu.plan_problems("Tổng tiền khách trả nợ 12-2025?", plan(raw), AS_OF)
    assert not problems and kept.measures[0].filters == []


def test_a_money_bound_takes_the_unit_the_question_writes():
    raw = {"intent": "count_where", "period": {"kind": "month", "year": 2025, "month": 8},
           "threshold": {"entity": "day", "metric": "revenue", "op": "gte", "value": 10}}
    q = "Tháng 8/2025 có mấy bữa tiệm bán được từ 10 củ trở lên?"
    assert grounding.scale_money(q, plan(raw)).threshold.value == 10_000_000
    assert grounding.scale_money("đơn trên 500k", plan({**raw, "threshold": {**raw["threshold"], "value": 500}})
                                 ).threshold.value == 500_000
    already = {**raw, "threshold": {**raw["threshold"], "value": 10_000_000}}
    assert grounding.scale_money(q, plan(already)).threshold.value == 10_000_000


def test_order_and_money_words_the_public_questions_write():
    """run10 (06/11): "đh" for "đơn hàng" (14 questions refused), "doanhthu" in one word, "từ 40tr trở lên"."""
    month = {"kind": "this_month"}
    orders = {"intent": "value", "period": month, "measures": [{"metric": "order_count"}]}
    assert not grounding.ungrounded_measures("Hqua có bnhiu đh z?", plan(orders))
    assert "metric=order_count" in grounding.ungrounded_measures("iPhone 13 th này bán đc mấy chiếc rồi?", plan(orders))
    revenue = {"intent": "value", "period": month, "measures": [{"metric": "revenue"}]}
    assert not grounding.ungrounded_measures("30 ngay gan nhat doanhthu duoc bao nhieu?", plan(revenue))
    days = {"intent": "count_where", "period": month,
            "threshold": {"entity": "day", "metric": "revenue", "op": "gte", "value": 40_000_000}}
    assert not grounding.ungrounded_measures("thang nay bn ngay wan mik ban tu 40tr tro len", plan(days))
    assert "metric=revenue" in grounding.ungrounded_measures("Hnay tổng bnhiu đh z?", plan(revenue))


def test_a_two_digit_year_is_the_year_the_question_states():
    """run10 (06/11): "Th 6/25 lãi gộp được nhiêu" with the LLM's year 2025 dropped as unstated, so §2 put June in
    this year (2026): 14 answers a year off. "th 12/25, th 1/26" months refused for the same reason."""
    as_of = date(2026, 8, 8)
    kept = nlu.accept_plan("Th 6/25 lãi gộp được nhiêu vậy?", plan({
        "intent": "value", "period": {"kind": "month", "year": 2025, "month": 6},
        "measures": [{"metric": "gross_profit"}]}), as_of)
    assert kept is not None and kept.period.year == 2025
    filled = nlu.accept_plan("5/25 quan thu ve bao nhieu doanh thu?", plan({
        "intent": "value", "period": {"kind": "month", "month": 5}, "measures": [{"metric": "revenue"}]}), as_of)
    assert filled.period.year == 2025
    series = {"intent": "series", "period": {"kind": "months", "months": ["2025-12", "2026-01", "2026-02"]},
              "measures": [{"metric": "revenue"}]}
    assert not grounding.ungrounded_dates("Doanh thu th 12/25, th 1/26, th 2/26 mỗi tháng bao nhiêu", plan(series))
    assert grounding.stated_months("ngày 6/12 bán bao nhiêu") == []  # day 6 of December, not 2012


def test_three_shapes_of_invalid_output_repaired():
    """run10 (06/11), 32 invalid outputs: the cancel share as two measures, a one-figure plan typed list, a series
    over one month."""
    share = {"intent": "value", "period": {"kind": "month", "year": 2026, "month": 6}, "answer_type": "percent",
             "measures": [{"metric": "cancel_count", "filters": [{"field": "order_status", "value": "cancelled"}]},
                          {"metric": "order_count", "filters": []}]}
    q = "Th6/2026 đơn bị huỷ chiếm mấy % z?"
    fixed = repair.repair(share, q, "answer_type=percent mâu thuẫn với plan (suy ra list)")
    assert fixed["measures"] == [{"metric": "cancel_rate", "filters": []}]
    assert nlu.accept_plan(q, QueryPlan.model_validate(fixed), AS_OF) is not None
    one = {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 5}, "answer_type": "list",
           "measures": [{"metric": "quantity", "filters": [{"field": "size", "value": "L"}], "unit": "ly"}]}
    assert "answer_type" not in repair.repair(one, "5-2025 quan ban ra bao nhieu ly size L, cong het cac mon?",
                                              "answer_type=list mâu thuẫn với plan (suy ra number)")
    series = {"intent": "series", "period": {"kind": "month", "year": 2025, "month": 7},
              "measures": [{"metric": "revenue", "filters": []}]}
    q = "Dthu th7, th8, th9/2025 lan luot moi thang bao nhieu?"
    fixed = repair.repair(series, q, "intent series cần period kind months")
    assert fixed["period"] == {"kind": "months", "months": ["2025-07", "2025-08", "2025-09"]}
    assert nlu.accept_plan(q, QueryPlan.model_validate(fixed), AS_OF) is not None


def test_the_day_of_a_price_rise_is_named_by_the_price():
    raw = {"intent": "compare", "period": {"kind": "days_from", "date": "2026-05-24", "n": 30},
           "measures": [{"metric": "quantity", "filters": [{"field": "product", "value": "Trà vải (L)"}]}],
           "compare": {"kind": "before_days_from"}}
    q = "Từ hồi Trà vải (L) lên giá 47.000đ, so 30 ngày kể từ ngày đổi giá với 30 ngày trước đó, bán nhiều hơn mấy %?"
    p = grounding.anchor_by_price(q, plan(raw), AS_OF).period
    assert p.date is None and p.anchor_price == 47_000
    dated = "Từ ngày 24/05/2026 Trà vải (L) lên giá 47.000đ, so 30 ngày kể từ ngày đó với 30 ngày trước"
    assert grounding.anchor_by_price(dated, plan(raw), AS_OF).period.date == "2026-05-24"  # the question's own day


def test_a_month_written_t5_slash_year_is_no_weekday():
    raw = {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 5},
           "measures": [{"metric": "avg_order_value", "filters": [{"field": "weekday", "value": "fri"}]}]}
    kept = grounding.drop_month_as_weekday("Trong T5/2025, trung bình một đơn có doanh thu bao nhiêu?", plan(raw))
    assert kept.measures[0].filters == []
    asked = grounding.drop_month_as_weekday("T5/2025 các ngày thứ 6 bán bao nhiêu", plan(raw))
    assert asked.measures[0].filters[0].value == "fri"


def test_the_day_of_a_rise_comes_from_the_price_list():
    """§5 "lần tăng giá = ngày D giá mới cao hơn giá liền trước (theo bảng giá); tăng lên cùng một giá nhiều lần thì
    lấy lần đầu": 40 000 → 47 000 on 01/03, down to 45 000, up to 47 000 again on 01/05: the first rise, 01/03."""
    import pandas as pd
    from datamate import temporal
    from datamate.contracts import CanonicalDB
    ph = pd.DataFrame({"product_key": ["TV"] * 4, "price": [40_000.0, 47_000.0, 45_000.0, 47_000.0],
                       "effective_date": ["2026-01-01", "2026-03-01", "2026-04-01", "2026-05-01"]})
    lines = pd.DataFrame({"order_id": ["1"], "product_key": ["TV"], "product_name": ["Trà vải (L)"]})
    db = CanonicalDB(tables={"price_history": ph, "lines": lines})
    raw = {"intent": "compare", "period": {"kind": "days_from", "anchor_price": 47_000, "n": 30},
           "measures": [{"metric": "quantity", "filters": [{"field": "product", "value": "Trà vải (L)"}]}],
           "compare": {"kind": "before_days_from"}}
    assert temporal.price_rise_day(plan(raw), db) == date(2026, 3, 1)
    r = temporal.resolve(plan(raw), date(2026, 8, 1), None, db)
    assert (r.period.start, r.period.end) == (date(2026, 3, 1), date(2026, 3, 30))
    assert (r.compare_period.start, r.compare_period.end) == (date(2026, 1, 30), date(2026, 2, 28))
    assert temporal.price_rise_day(plan({**raw, "period": {**raw["period"], "anchor_price": 40_000}}), db) is None


def test_debt_by_age_groups_is_one_figure_per_group():
    """§4 "tuổi nợ: số ngày tính từ ngày đặt; đơn đặt hôm nay có tuổi nợ 0 ngày". At the end of 30/06: orders of 28/06
    (age 2, owes 100), 20/06 (age 10, owes 200), 01/06 (age 29, owes 50, after paying 50). Groups 0–7, 8–15, > 15."""
    import pandas as pd
    from datetime import datetime
    from datamate import metrics, temporal
    from datamate.contracts import CanonicalDB
    o = pd.DataFrame({"order_id": ["a", "b", "c"], "status": "completed", "payment_method": "Ghi nợ",
                      "order_time": [datetime(2026, 6, 28), datetime(2026, 6, 20), datetime(2026, 6, 1)],
                      "total_due": [100.0, 200.0, 100.0], "goods_amount": [100.0, 200.0, 100.0], "has_time": False})
    pay = pd.DataFrame({"order_id": ["c"], "amount": [50.0], "paid_time": [datetime(2026, 6, 10)]})
    db = CanonicalDB(tables={"orders": o, "payments": pay})
    raw = {"intent": "value", "period": {"kind": "until", "date": "2026-06-30"},
           "measures": [{"metric": "debt_total", "filters": [
               {"field": "debt_age_days", "value": "0–7 ngày"}, {"field": "debt_age_days", "value": "8–15 ngày"},
               {"field": "debt_age_days", "value": "trên 15 ngày"}]}]}
    q = "Đến hết 30/06/2026, nợ còn lại chia theo tuổi nợ 0–7 ngày, 8–15 ngày và trên 15 ngày là bao nhiêu?"
    p = nlu.accept_plan(q, plan(raw), date(2026, 6, 30))
    assert p is not None and len(p.measures) == 3
    r = metrics.execute(temporal.resolve(p, date(2026, 6, 30), None, db), db)
    assert r.value == [100, 200, 50] and "§4.tuoi_no" in r.rule_ids


def test_a_share_whose_whole_is_its_part_is_a_share_of_the_shop():
    """run10 (06/11): "dthu đơn bán tại quầy chiếm bn % tổng dthu của shop" with share_of = the counter's revenue gave
    100% (the right answer 89.26%): the whole becomes the shop's."""
    part = {"metric": "revenue", "filters": [{"field": "channel", "value": "tại quầy"}]}
    raw = {"intent": "share", "period": {"kind": "month", "year": 2026, "month": 5}, "measures": [part], "share_of": part}
    assert grounding.whole_not_part(plan(raw)).share_of is None
    other = {**raw, "share_of": {"metric": "revenue"}}
    assert grounding.whole_not_part(plan(other)).share_of is not None


def test_a_written_month_of_last_year_is_the_period_compared_with():
    raw = {"intent": "compare", "period": {"kind": "month", "year": 2026, "month": 3}, "measures": [{"metric": "revenue"}],
           "compare": {"kind": "previous", "period": {"kind": "month", "year": 2025, "month": 3}}}
    kept = nlu.accept_plan("Dthu th 3/26 tang truong bnhiu % so th 3/25?", plan(raw), AS_OF)
    assert kept is not None and kept.compare.kind == "period" and kept.compare.period.year == 2025
    same_year = {**raw, "compare": {"kind": "previous", "period": {"kind": "month", "year": 2026, "month": 2}}}
    assert grounding.written_last_year(plan(same_year)).compare.kind == "previous"


def test_a_share_of_the_cancel_rate_is_the_cancel_rate():
    """run11 07/11: "đơn huỷ chiếm bao nhiêu % toàn bộ đơn" read as a share of cancel_rate (no function): the rate is
    that percent already (§1). With a denominator of its own, the share stays."""
    raw = {"intent": "share", "measures": [{"metric": "cancel_rate"}], "period": {"kind": "this_month"}}
    q = "Tháng này đơn huỷ chiếm nhiêu % toàn bộ đơn z?"
    read = nlu.accept_plan(q, plan(raw), AS_OF)
    assert read is not None and read.intent == "value" and read.measures[0].metric == "cancel_rate"
    revenue = {"intent": "share", "measures": [{"metric": "revenue", "filters": [{"field": "channel", "value": "store"}]}],
               "period": {"kind": "this_month"}}
    assert grounding.rate_as_value(plan(revenue)).intent == "share"


def test_a_unit_written_as_a_filter_is_the_unit_and_without_money_words_a_quantity():
    """N76, run11 07/11: "quán bán dc bnhiu đĩa" read as revenue filtered by unit = đĩa."""
    raw = {"intent": "value", "period": {"kind": "this_week"},
           "measures": [{"metric": "revenue", "filters": [{"field": "unit", "value": "đĩa"}]}]}
    read = nlu.accept_plan("Tuan nay quan ban dc bnhiu dia?", plan(raw), AS_OF)
    assert read is not None and read.measures[0].metric == "quantity" and read.measures[0].unit == "đĩa"
    assert read.measures[0].filters == []
    money = grounding.unit_filter_as_unit("Tuần này bán bao nhiêu tiền đĩa cơm?", plan(raw))
    assert money == plan(raw)  # a money word: left to the gates (run11: "doanh thu … bao nhiêu hỉ", a particle as unit)


def test_orders_counted_with_dh_and_no_money_word_are_the_number_of_orders():
    """N76, run11 07/11: "30 ngày gần nhất được bnhiu đh" read as revenue (completed orders)."""
    raw = {"intent": "value", "period": {"kind": "last_n_days", "n": 30},
           "measures": [{"metric": "revenue", "filters": [{"field": "order_status", "value": "completed"}]}]}
    read = nlu.accept_plan("30 ngày gần nhất được bnhiu đh nhỉ?", plan(raw), AS_OF)
    assert read is not None and read.measures[0].metric == "order_count" and read.measures[0].filters == []
    money = "30 ngày gần nhất các đơn thu được bao nhiêu tiền?"
    assert grounding.orders_not_money(money, plan(raw)).measures[0].metric == "revenue"
