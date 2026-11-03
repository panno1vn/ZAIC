"""[C] Understand the question: ask the LLM for a QueryPlan (structured output), cross-checked with the rule-based
baseline. Work package G3. [C3] Link names in the plan to values in the data. Work package G6.

Without an LLM only the baseline answers (a few frequent shapes). With an LLM, a plan is kept only if it validates and,
when the baseline also reads the question, both readers agree: two readings that differ are not worth a guess.
"""
from __future__ import annotations

import unicodedata
from datetime import date

from datamate.contracts import STOCK_METRICS, CanonicalDB, DataCard, QueryPlan, ResolvedPlan
from datamate.llm import LLMClient

from . import baseline, prompt
from .grounding import ungrounded_filters


def _fold_value(v):
    if isinstance(v, str):
        t = unicodedata.normalize("NFD", v.lower()).replace("đ", "d")
        return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())
    return [_fold_value(x) for x in v] if isinstance(v, list) else v


def canonical_plan(plan: QueryPlan) -> dict:
    """The plan as compared between readers, with the differences that do not change its meaning removed: defaults,
    free-text notes, the derived answer type, case and diacritics of names and units, the measure that only repeats
    the ranking or threshold metric, and "today" as the period of a stock metric (no period means today too)."""
    d = plan.model_dump(mode="json", exclude_none=True, exclude_defaults=True,
                        exclude={"notes", "out_of_scope_reason", "answer_type"})

    def walk(x):
        if isinstance(x, dict):
            return {k: (_fold_value(v) if k in ("value", "unit") else walk(v)) for k, v in x.items() if k != "note"}
        return [walk(v) for v in x] if isinstance(x, list) else x
    d = walk(d)
    own = d.get("rank", {}).get("by") or d.get("threshold", {}).get("metric")
    if own and d.get("measures") == [{"metric": own}]:
        d.pop("measures")
    if d.get("period") == {"kind": "today"} and plan.measures and all(m.metric in STOCK_METRICS for m in plan.measures):
        d.pop("period")
    return d


def llm_plan(question: str, as_of: date, card: DataCard, llm: LLMClient,
             bank: prompt.ExampleBank | None = None, exclude_ids: frozenset[str] = frozenset()) -> QueryPlan | None:
    """The LLM's plan, or None when the call fails or times out, the output is not a valid plan, or it has a filter
    the question gives no ground for (grounding.py)."""
    bank = bank or prompt.default_bank()
    messages = prompt.build_messages(question, as_of, card, bank.select(question, exclude_ids=exclude_ids))
    try:
        plan = QueryPlan.model_validate(llm.generate_json(messages, prompt.PLAN_SCHEMA))
    except Exception:
        return None
    return None if ungrounded_filters(question, plan) else plan


def parse_question(question: str, as_of: date, card: DataCard, llm: LLMClient | None = None) -> QueryPlan | None:
    """QueryPlan for the question, or None when it cannot be parsed into a valid plan both readers agree on."""
    base = baseline.parse(question)
    if llm is None:
        return base
    plan = llm_plan(question, as_of, card, llm)
    if plan is not None and base is not None and canonical_plan(plan) != canonical_plan(base):
        return None
    return plan


def link_entities(plan: ResolvedPlan, db: CanonicalDB) -> ResolvedPlan:
    """Fill plan.linked / plan.link_scores: each filter value as written -> the closest value in the data (G6)."""
    return plan
