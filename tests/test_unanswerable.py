"""N28: a question whose period (or compared period) lies wholly outside the shop's data is unanswerable (§7 "kỳ nằm
hoàn toàn ngoài khoảng ngày có dữ liệu của shop … không trả lời được, không phải 0"); train 16 of 16 (05/11)."""
from datetime import date

import pandas as pd

from datamate.contracts import CanonicalDB, ExecResult, Mapping, QueryPlan, ResolvedPeriod, ResolvedPlan, Signals
from datamate.decide import decide
from datamate.formatter import to_line
from datamate.verify import R_OUTSIDE, collect_signals

SPAN = (date(2025, 5, 1), date(2026, 6, 30))
RULES = {r: True for r in R_OUTSIDE}


def _plan(period, compare=None, kind="month"):
    raw = {"intent": "value", "measures": [{"metric": "revenue"}], "period": {"kind": kind, "year": 2025, "month": 3}}
    if compare is not None:
        raw = {"intent": "compare", "measures": [{"metric": "revenue"}], "period": raw["period"],
               "compare": {"kind": "previous"}}
    return ResolvedPlan(plan=QueryPlan.model_validate(raw), as_of=date(2026, 6, 30),
                        period=ResolvedPeriod(start=period[0], end=period[1]),
                        compare_period=None if compare is None else ResolvedPeriod(start=compare[0], end=compare[1]),
                        linked={})


DB = CanonicalDB(tables={"orders": pd.DataFrame({"order_id": ["1"]})}, date_ranges={"orders": SPAN})


def test_a_period_before_the_data_or_a_compared_one_is_outside():
    march = (date(2025, 3, 1), date(2025, 3, 31))
    assert collect_signals(_plan(march), None, DB, Mapping(), RULES).outside_data is True
    may, april = (date(2025, 5, 1), date(2025, 5, 31)), (date(2025, 4, 1), date(2025, 4, 30))
    assert collect_signals(_plan(may, april), None, DB, Mapping(), RULES).outside_data is True  # "so với tháng trước"
    assert collect_signals(_plan(may), None, DB, Mapping(), RULES).outside_data is False
    partly = (date(2025, 4, 15), date(2025, 5, 15))  # §7: a period partly inside is worked out on what is inside
    assert collect_signals(_plan(partly), None, DB, Mapping(), RULES).outside_data is False
    # the rulebook row changed or missing: no decision rests on it
    assert collect_signals(_plan(march), None, DB, Mapping(), {}).outside_data is None


def _signals(**kw):
    base = dict(intent_known=True, mapping_ok=True, entities_ok=True, outside_data=True)
    return Signals(**{**base, **kw})


def test_unanswerable_only_when_the_question_was_read_and_its_data_is_usable():
    d = decide(_signals(), None)
    assert d.kind == "unanswerable"
    line = to_line("q1", d, None).to_dict()
    assert line["type"] == "unanswerable" and isinstance(line.get("reason", ""), str)
    for bad in (dict(mapping_ok=False), dict(entities_ok=False), dict(twin_ok=False), dict(terms_known=False),
                dict(out_of_scope=True), dict(outside_data=None)):
        assert decide(_signals(**bad), None).kind == "abstain", bad
    res = ExecResult(value=0, answer_type="number", source="D1")  # §7: no data is not 0
    assert decide(_signals(), res).kind == "unanswerable"
