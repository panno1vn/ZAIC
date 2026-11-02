"""[V] signals and [E] gates."""
from datetime import date

import pandas as pd

from datamate.contracts import (CanonicalDB, CheckResult, ExecResult, Mapping, QueryPlan, ResolvedPeriod,
                                ResolvedPlan, TableMap)
from datamate.decide import decide
from datamate.verify import collect_signals, coverage

SPAN = (date(2025, 3, 1), date(2026, 6, 30))


def test_coverage():
    flow = lambda a, b: ResolvedPeriod(start=a, end=b)
    assert coverage(flow(date(2025, 4, 1), date(2025, 4, 30)), SPAN) == "full"
    assert coverage(flow(date(2025, 2, 1), date(2025, 2, 28)), SPAN) == "none"
    assert coverage(flow(date(2025, 2, 15), date(2025, 3, 15)), SPAN) == "partial"
    assert coverage(ResolvedPeriod(start=date(2020, 1, 1), end=date(2025, 5, 1), mode="stock"), SPAN) == "full"
    assert coverage(ResolvedPeriod(start=date(2020, 1, 1), end=date(2025, 1, 1), mode="stock"), SPAN) == "none"
    assert coverage(None, SPAN) == "full"


def make(plan: dict, linked=None, period=(date(2025, 4, 1), date(2025, 4, 30))):
    return ResolvedPlan(plan=QueryPlan.model_validate(plan), as_of=date(2026, 6, 30),
                        period=ResolvedPeriod(start=period[0], end=period[1]), linked=linked or {})


def good_world():
    db = CanonicalDB(tables={"orders": pd.DataFrame({"order_id": ["1"]}), "lines": pd.DataFrame({"line_amount": [1.0]})},
                     date_ranges={"lines": SPAN, "orders": SPAN})
    m = Mapping(tables=[TableMap(target="orders", sources=["a"], columns=[]),
                        TableMap(target="lines", sources=["a"], columns=[])],
                checks=[CheckResult(name="tổng dòng = tổng đơn", passed=True)])
    res = ExecResult(value=1000, answer_type="number", source="D1", requires=["lines.line_amount"], rule_ids=["r1"])
    return db, m, res


REVENUE = {"intent": "value", "measures": [{"metric": "revenue"}], "period": {"kind": "month", "year": 2025, "month": 4}}


def test_all_gates_pass_then_answer():
    db, m, res = good_world()
    s = collect_signals(make(REVENUE), res, db, m, {"r1": True})
    assert s.entities_ok  # no filter to link
    assert decide(s, res).kind == "answer"


def test_each_failed_gate_abstains():
    db, m, res = good_world()
    assert decide(collect_signals(make(REVENUE), res, db, m, {"r1": False}), res).kind == "abstain"  # rule changed
    assert decide(collect_signals(make(REVENUE), res, db, Mapping(), {"r1": True}), res).kind == "abstain"  # mapping
    out = make(REVENUE, period=(date(2025, 1, 1), date(2025, 1, 31)))
    assert decide(collect_signals(out, res, db, m, {"r1": True}), res).kind == "abstain"  # period outside data
    missing = res.model_copy(update={"requires": ["payments.amount"]})
    assert decide(collect_signals(make(REVENUE), missing, db, m, {"r1": True}), missing).kind == "abstain"
    with_filter = {**REVENUE, "measures": [{"metric": "revenue", "filters": [{"field": "product", "value": "Latte"}]}]}
    assert decide(collect_signals(make(with_filter), res, db, m, {"r1": True}), res).kind == "abstain"  # not linked
    assert decide(collect_signals(make(with_filter, linked={"Latte": "Latte (L)"}), res, db, m, {"r1": True}),
                  res).kind == "answer"
    assert decide(collect_signals(make(REVENUE), None, db, m, {}), None).kind == "abstain"  # no result


def test_out_of_scope_abstains_until_enabled():
    db, m, _ = good_world()
    oos = {"intent": "out_of_scope", "out_of_scope_reason": "chủ quan"}
    plan = ResolvedPlan(plan=QueryPlan.model_validate(oos), as_of=date(2026, 6, 30))
    d = decide(collect_signals(plan, None, db, m, {}), None)
    assert d.kind == "abstain" and "chưa bật" in d.reason
