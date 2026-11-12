"""N193 (HAN_CHE N11): the trend function answers whether each month is above the one before; a trend question about
a fall must not get that answer (abstain), a question about a discount ("giảm giá") is not about a fall."""
import json
from pathlib import Path

from datamate.verify import asks_fall

ROOT = Path(__file__).resolve().parents[1]


def test_fall_words():
    assert asks_fall("Doanh thu từ tháng 3 đến tháng 6/2026 có giảm liên tục không?")
    assert asks_fall("doanh thu co di xuong lien tuc ko")
    assert asks_fall("số đơn tháng sau có luôn thấp hơn tháng trước không")
    assert not asks_fall("Tháng sau có luôn cao hơn tháng trước không?")
    assert not asks_fall("doanh thu tăng liên tục từ tháng 1 đến tháng 4 phải không")
    assert not asks_fall("tiền giảm giá có tăng liên tục qua các tháng?")


def test_no_train_trend_question_is_a_fall():
    qs = {q["id"]: q["question"] for q in map(json.loads, (ROOT / "data/train/questions.jsonl").open(encoding="utf-8"))}
    bank = ROOT / "outputs/bank/llm_plans.jsonl"
    if not bank.exists():
        return
    trend = [qs[e["id"]] for e in map(json.loads, bank.open(encoding="utf-8"))
             if (e.get("plan") or {}).get("intent") == "trend"]
    assert trend and not [q for q in trend if asks_fall(q)]


def test_trend_on_a_fall_is_not_sane():
    from datamate.contracts import ExecResult, Mapping, QueryPlan, ResolvedPlan
    from datamate.verify import collect_signals
    plan = QueryPlan.model_validate({"intent": "trend", "measures": [{"metric": "revenue"}],
                                     "period": {"kind": "months", "months": ["2026-03", "2026-04", "2026-05"]},
                                     "answer_type": "boolean"})
    from datetime import date
    resolved = ResolvedPlan(plan=plan, period=None, as_of=date(2026, 6, 30))
    result = ExecResult(function="trend", value=True, answer_type="boolean", source="D1")

    class _DB:
        date_ranges, conventions, readme, values = {}, None, "", set()

        def has(self, *a):
            return True
    for q, sane in (("doanh thu tháng 3 đến tháng 5 có giảm liên tục không", False),
                    ("doanh thu tháng 3 đến tháng 5 có tăng liên tục không", True)):
        s = collect_signals(resolved, result, _DB(), Mapping(), {}, q)
        assert s.sane is sane
