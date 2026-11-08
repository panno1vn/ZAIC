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


def test_an_output_no_repair_knows_is_asked_again_with_its_error():
    """N78: run11 07/11, "mấy đơn" written with a shift filter "store"; the second call, shown the error, drops it."""
    bad = {"intent": "value", "period": {"kind": "this_week"},
           "measures": [{"metric": "order_count", "filters": [{"field": "shift", "value": "store"}]}]}
    good = {"intent": "value", "period": {"kind": "this_week"}, "measures": [{"metric": "order_count"}]}
    llm, trace = MockLLM([bad, good]), {}
    plan = llm_plan("Tuan nay quan ban duoc may don roi?", AS_OF, DataCard(), llm, trace=trace)
    assert plan is not None and plan.measures[0].filters == [] and trace["retry"] == "ok"
    assert "không hợp lệ" in llm.calls[1][0][-1]["content"]  # the error is shown
    trace = {}
    assert llm_plan("Tuan nay quan ban duoc may don roi?", AS_OF, DataCard(), MockLLM([bad, bad]), trace=trace) is None
    assert trace["retry"] == "failed"


def test_a_plan_the_gates_refuse_is_asked_again_with_the_parts_they_refused():
    """N79: a shift filter the question never states (run11 07/11, "tuần này quán bán được mấy đơn" read with
    shift = afternoon); the second call, shown "shift=afternoon", drops it. A second plan refused too stays refused."""
    import datamate.nlu as nlu_module
    old, nlu_module.GROUND_RETRY = nlu_module.GROUND_RETRY, True  # on by default since 08/11; set here all the same
    shifted = {"intent": "value", "period": {"kind": "this_week"},
               "measures": [{"metric": "order_count", "filters": [{"field": "shift", "value": "afternoon"}]}]}
    plain = {"intent": "value", "period": {"kind": "this_week"}, "measures": [{"metric": "order_count"}]}
    q = "Tuan nay quan ban duoc may don roi?"
    llm, trace = MockLLM([shifted, plain]), {}
    plan = llm_plan(q, AS_OF, DataCard(), llm, trace=trace)
    assert plan is not None and plan.measures[0].filters == [] and trace["retry"] == "ok"
    assert "shift=afternoon" in llm.calls[1][0][-1]["content"] and trace["rejected_first"] == ["shift=afternoon"]
    trace = {}
    assert llm_plan(q, AS_OF, DataCard(), MockLLM([shifted, shifted]), trace=trace) is None
    assert trace["retry"] == "failed" and trace["rejected"] == ["shift=afternoon"]
    nlu_module.GROUND_RETRY = old
