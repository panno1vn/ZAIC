"""N72: a plan with no result says why in its log: no function for the plan, a filter the function does not take, the
function gave None (and, in a replay, the return line where it stopped), or a period that does not resolve."""
from datetime import date

import pytest

from datamate import diagnose, metrics, pipeline
from datamate.contracts import QueryPlan, ResolvedPlan
from test_metrics_sales import JUNE, shop


def resolved(raw: dict) -> ResolvedPlan:
    return ResolvedPlan(plan=QueryPlan.model_validate(raw), as_of=date(2026, 6, 30), period=JUNE)


QUANTITY = {"intent": "value", "measures": [{"metric": "quantity"}], "period": {"kind": "this_month"}}


@pytest.fixture
def traced():
    old = diagnose.ENABLED
    diagnose.ENABLED = True
    yield
    diagnose.ENABLED = old


def test_a_function_that_gives_none_is_named_and_off_by_default_without_the_return_line():
    db = shop()
    db.tables["lines"] = db.tables["lines"].drop(columns=["base_qty"])
    why: dict = {}
    assert metrics.execute(resolved(QUANTITY), db, why) is None
    assert why["why"] == "function_none" and why["function"]
    assert "at" not in why  # predict never traces


def test_a_replay_logs_the_return_line_where_the_function_stopped(traced):
    db = shop()
    db.tables["lines"] = db.tables["lines"].drop(columns=["base_qty"])
    why: dict = {}
    assert metrics.execute(resolved(QUANTITY), db, why) is None
    assert why["at"] and why["at"][0].startswith("metrics.") and "return" in why["at"][0]
    # figure() is called inside a list comprehension and `any(...)` runs a generator: neither hides the cause
    assert [w.split(":")[0] for w in why["at"]] == ["metrics.sales.value_of", "metrics.sales.figure",
                                                     "metrics.sales.quantity"]


def test_an_answer_leaves_the_trace_empty(traced):
    why: dict = {}
    assert metrics.execute(resolved(QUANTITY), shop(), why) is not None
    assert why == {}


def test_no_function_for_the_plan_names_the_key():
    why: dict = {}
    plan = resolved({"intent": "value", "measures": [{"metric": "other"}], "answer_type": "number",
                     "period": {"kind": "this_month"}})
    assert metrics.execute(plan, shop(), why) is None
    assert why == {"why": "no_function", "key": ["value", "other", ""]}


def test_none_chain_follows_the_call_that_gave_none():
    def inner(x):
        return None if x else 1

    def outer(x):
        y = inner(x)
        if y is None:
            return None
        return y

    # functions of this test file are not in the datamate package: nothing traced, no chain
    assert diagnose.none_chain(outer, True) == []
    chain = diagnose.none_chain(metrics.frames.requires, shop(), ())
    assert chain == []  # not None: no chain


def test_none_chain_reports_a_crash():
    def boom(_):
        raise KeyError("base_qty")
    assert diagnose.none_chain(boom, 1) == ["raised KeyError: 'base_qty'"]


def test_a_period_that_does_not_resolve_is_logged_as_such(tmp_path, monkeypatch, traced):
    """Days counted from a price rise the shop has no price list for: the plan exists, the period does not."""
    plan = QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "revenue", "filters": [
        {"field": "product", "op": "eq", "value": "Bia Tiger lon"}]}],
        "period": {"kind": "days_from", "anchor_price": 47000, "n": 30}})
    monkeypatch.setattr(pipeline.nlu, "parse_question", lambda *a, **k: plan)
    ctx = pipeline.BusinessContext(None, None, pipeline.Mapping(), shop(), pipeline.DataCard())
    q = {"id": "q", "business_id": "b", "question": "x", "as_of_date": "2026-06-30"}
    line, log = pipeline.answer_question(q, ctx, tmp_path / "calendar.csv", {}, "", None)
    assert line.type == "abstain" and "error" not in log
    assert log["no_result"]["why"] == "period_unresolved"
    assert log["no_result"]["at"][0].startswith("temporal.resolve:")
    assert any(w.startswith("temporal.price_rise_day:") for w in log["no_result"]["at"])
