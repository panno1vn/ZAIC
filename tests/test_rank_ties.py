"""N25: a ranking with equal values where the answer depends on the tie rule abstains. The train question generator
leaves such rankings out (0 of 281 rank answers, while a month's top customer by order count ties 39% of the time), so
a tie in our figures means they differ from the generator's somewhere."""
from datetime import date

import pandas as pd

from datamate import metrics
from datamate.contracts import ExecResult, Mapping, QueryPlan, ResolvedPlan, Signals
from datamate.decide import decide
from datamate.metrics.sales import TIE, _tied
from datamate.verify import collect_signals

from test_metrics_sales import JUNE, shop


def test_tied_at_the_boundary_or_inside_an_ordered_top_k():
    s = pd.Series({"a": 5, "b": 5, "c": 3})
    assert _tied(s, 1)                          # who is first depends on the tie rule
    assert not _tied(s, 2, order_matters=False)  # {a, b} either way: a table's row order is not scored
    assert _tied(s, 2)                          # an ordered list: a, b or b, a
    assert not _tied(s, 3, order_matters=False)
    assert not _tied(pd.Series({"a": 5, "b": 4, "c": 4}), 1)  # ties below the answer do not matter
    assert _tied(pd.Series({"a": 5, "b": 4, "c": 4}), 2)
    assert not _tied(pd.Series({"a": 5.0}), 1)
    assert _tied(pd.Series({"a": 0.1 + 0.2, "b": 0.3}), 1)  # floating sums equal to the cent


def _rank(entity, by, k=1):
    plan = ResolvedPlan(plan=QueryPlan.model_validate(
        {"intent": "rank", "period": {"kind": "this_month"}, "rank": {"entity": entity, "by": by, "k": k}}),
        as_of=date(2026, 6, 30), period=JUNE, linked={})
    return metrics.execute(plan, shop())


def test_rank_notes_a_tie_and_only_then():
    # shop(): June base quantities SP3 26, SP1 3, SP2 3 (tie at places 2 and 3)
    assert TIE not in _rank("product", "quantity", 1).notes
    assert TIE in _rank("product", "quantity", 2).notes
    assert TIE not in _rank("customer", "revenue", 2).notes
    assert TIE in _rank("day", "order_count", 2).notes  # 06-02 and 06-03: one valid order each


def test_a_tie_closes_the_gate():
    res = ExecResult(value="x", answer_type="string", source="D1", notes=[TIE])
    plan = ResolvedPlan(plan=QueryPlan.model_validate(
        {"intent": "rank", "period": {"kind": "this_month"}, "rank": {"entity": "day", "by": "revenue"}}),
        as_of=date(2026, 6, 30), period=JUNE, linked={})
    assert collect_signals(plan, res, shop(), Mapping(), {}).ranking_clear is False
    signals = Signals(intent_known=True, mapping_ok=True, entities_ok=True, required_fields_present=True, sane=True,
                      rules_unchanged=True, period_coverage="full", ranking_clear=False)
    d = decide(signals, res)
    assert d.kind == "abstain" and "tie" in d.reason
    signals.ranking_clear = None
    assert decide(signals, res).kind == "answer"
