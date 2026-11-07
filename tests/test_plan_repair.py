"""N32: invalid LLM outputs of the shapes seen on train are rewritten into the plan they mean; others stay invalid."""
from datetime import date

from datamate.contracts import DataCard
from datamate.llm import MockLLM
from datamate.nlu import llm_plan
from datamate.nlu.repair import repair

AS_OF = date(2026, 8, 5)


def _read(question: str, output: dict):
    return llm_plan(question, AS_OF, DataCard(), MockLLM([output]))


def test_two_filtered_measures_become_a_comparison_of_filters():
    out = {"intent": "compare", "period": {"kind": "month", "year": 2025, "month": 5},
           "measures": [{"metric": "revenue", "filters": [{"field": "shift", "value": "afternoon"}]},
                        {"metric": "revenue", "filters": [{"field": "shift", "value": "morning"}]}],
           "compare": {"kind": "filter", "output": "pct_change"}}
    plan = _read("Trong tháng 5/2025, doanh thu ca chiều hơn hay kém ca sáng bao nhiêu phần trăm vậy?", out)
    assert plan is not None
    assert [f.value for f in plan.measures[0].filters] == ["afternoon"] and len(plan.measures) == 1
    assert [f.value for f in plan.compare.filters] == ["morning"]


def test_a_months_series_written_as_a_range_gets_its_length():
    out = {"intent": "series", "period": {"kind": "months", "start": "2025-02", "end": "2025-04"},
           "measures": [{"metric": "revenue"}]}
    plan = _read("Liệt kê doanh thu 3 tháng liên tiếp từ tháng 2/2025 đến tháng 4/2025, theo thứ tự thời gian.", out)
    assert plan is not None and plan.period.end == "2025-04" and plan.period.n == 3


def test_a_count_typed_percent_is_a_count_only_when_the_question_asks_no_percent():
    out = {"intent": "value", "period": {"kind": "this_month"},
           "measures": [{"metric": "quantity", "filters": [{"field": "size", "value": "M"}], "unit": "ly"}],
           "answer_type": "percent"}
    plan = _read("trong thang nay, so ly size m ban dc la bao nhieu, tinh moi loai do uong", out)
    assert plan is not None and plan.answer_type == "number"
    assert _read("trong thang nay, ly size m chiem bao nhieu phan tram", out) is None  # asks a percent: no guess


def test_other_errors_are_not_repaired():
    assert repair({"intent": "compare", "compare": {"kind": "period"}}, "q", "compare period cần trường period") is None
    two_same = {"compare": {"kind": "filter"}, "measures": [{"metric": "revenue", "filters": [{"field": "shift",
                "value": "morning"}]}] * 2}
    assert repair(two_same, "q", "compare filter cần trường filters") is None  # nothing to compare with



def test_a_series_across_a_year_written_as_its_first_month_takes_the_months_the_question_writes():
    """run11 07/11: "th 12/25, th 1/26, th 2/26" read as December 2025 alone (the same-year repair did not apply)."""
    march = date(2026, 3, 10)
    out = {"intent": "series", "measures": [{"metric": "revenue"}], "period": {"kind": "month", "year": 2025, "month": 12}}
    q = "Doanh thu th 12/25, th 1/26, th 2/26 mỗi tháng bao nhiêu, ghi theo thứ tự đó nha?"
    plan = llm_plan(q, march, DataCard(), MockLLM([out]))
    assert plan is not None and plan.period.months == ["2025-12", "2026-01", "2026-02"]
    gap = "Doanh thu th 12/25, th 2/26 mỗi tháng bao nhiêu?"  # not consecutive: no series to guess
    assert llm_plan(gap, march, DataCard(), MockLLM([out])) is None
