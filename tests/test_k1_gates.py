"""K1 (Kaggle, 06/11): with Qwen3-14B's plans the train run had 10 wrong answers, each through every gate. Each kind
is a reading 8B may make on a shop it has not seen; the gates below turn them into blanks."""
from datetime import date, datetime

import pandas as pd

from datamate import metrics
from datamate.contracts import CanonicalDB, QueryPlan, ResolvedPeriod, ResolvedPlan
from datamate.nlu import grounding


def bad(question: str, raw: dict) -> list[str]:
    return grounding.ungrounded_measures(question, QueryPlan.model_validate(raw))


def test_a_part_with_its_whole_needs_two_figures_asked():
    """"tổng cộng mấy ly size M, cộng tất cả các món" read as [size M, every cup]: one figure asked."""
    month = {"kind": "month", "year": 2025, "month": 11}
    part_whole = {"intent": "value", "period": month, "measures": [
        {"metric": "quantity", "filters": [{"field": "size", "value": "M"}], "unit": "ly"}, {"metric": "quantity"}]}
    assert "measures=2" in bad("Tháng 11/2025 quán bán ra tổng cộng mấy ly size M, cộng tất cả các món nhỉ?", part_whole)
    assert "measures=2" not in bad("Tháng 11/2025 bán mấy ly size M, tổng tất cả bao nhiêu ly?", part_whole)
    two_channels = {"intent": "value", "period": month, "measures": [
        {"metric": "revenue", "filters": [{"field": "channel", "value": "điện thoại"}]},
        {"metric": "revenue", "filters": [{"field": "channel", "value": "zalo oa"}]}]}
    assert not bad("Cho tôi doanh thu các đơn bán qua điện thoại và doanh thu các đơn bán qua Zalo OA tháng 11/2025.",
                   two_channels)


def test_a_count_the_question_states_is_the_k():
    rank = lambda k: {"intent": "rank", "period": {"kind": "until", "date": "2025-10-27"},  # noqa: E731
                      "rank": {"entity": "customer", "by": "debt_amount", "k": k, "with_values": True}}
    q = "tính đến hết ngày 27/10/2025, 3 khách nào đang nợ nhiều nhất, mỗi người còn nợ bao nhiêu"
    assert "k=1" in bad(q, rank(1)) and not [b for b in bad(q, rank(3)) if b.startswith("k=")]
    assert grounding.stated_k("top 5 món bán chạy tháng này") == 5
    assert grounding.stated_k("tháng 3 khách nào mua nhiều nhất") is None  # the month, not a count
    assert grounding.stated_k("27/10 khách nào nợ nhiều nhất") is None  # a date
    assert grounding.stated_k("trong 30 ngày gần nhất món nào bán chạy") is None


def test_last_year_needs_its_words_or_two_years():
    plan = {"intent": "compare", "period": {"kind": "month", "year": 2025, "month": 5},
            "measures": [{"metric": "revenue", "filters": [{"field": "shift", "value": "afternoon"}]}],
            "compare": {"kind": "same_period_last_year"}}
    assert "compare=same_period_last_year" in bad(
        "Trong tháng 5/2025, doanh thu ca chiều hơn hay kém ca sáng bao nhiêu phần trăm vậy?", plan)
    plain = {**plan, "measures": [{"metric": "revenue"}]}
    assert not bad("Doanh thu tháng 8/2026 so với tháng 8/2025 tăng hay giảm bao nhiêu %?", plain)
    assert not bad("dthu tết năm nay so vs tết năm trc thay đổi mấy phần trăm", plain)


def test_a_bound_that_zero_passes_is_not_counted():
    """"không bán được lần nào" read as order_presence = 0: the products of the period's lines never show it."""
    o = pd.DataFrame({"order_id": ["1"], "order_time": [datetime(2026, 6, 1)], "status": ["completed"]})
    lines = pd.DataFrame({"order_id": ["1"], "product_key": ["A"], "line_amount": [1.0], "qty": [1], "is_item": [True]})
    db = CanonicalDB(tables={"orders": o, "lines": lines})
    def count(op, value):
        plan = ResolvedPlan(plan=QueryPlan.model_validate({
            "intent": "count_where", "period": {"kind": "this_month"},
            "threshold": {"entity": "product", "metric": "order_presence", "op": op, "value": value}}),
            as_of=date(2026, 6, 30), period=ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30)))
        r = metrics.execute(plan, db)
        return None if r is None else r.value

    assert count("eq", 0) is None and count("lt", 1) is None and count("lte", 0) is None
    assert count("lt", 2) == 1  # "dưới 2 đơn": the products sold, as before
