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

from datamate.verify import LINKED_FIELDS, filter_keys

from . import baseline, linking, prompt
from .grounding import drop_ungrounded_years, ungrounded_dates, ungrounded_filters, ungrounded_measures


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
    or a day the question gives no ground for (grounding.py). A year the question does not state is dropped, so §2
    decides it."""
    bank = bank or prompt.default_bank()
    messages = prompt.build_messages(question, as_of, card, bank.select(question, exclude_ids=exclude_ids))
    try:
        plan = QueryPlan.model_validate(llm.generate_json(messages, prompt.PLAN_SCHEMA))
    except Exception:
        return None
    return accept_plan(question, plan, as_of)


def accept_plan(question: str, plan: QueryPlan, as_of: date | None = None) -> QueryPlan | None:
    """An LLM plan as the pipeline may use it: years the question does not state dropped, None when a filter or a
    day has no ground in the question (grounding.py)."""
    plan = drop_implied_filters(drop_ungrounded_years(question, plan, as_of))
    if ungrounded_filters(question, plan) or ungrounded_dates(question, plan, as_of):
        return None
    return None if ungrounded_measures(question, plan) else plan


def drop_implied_filters(plan: QueryPlan) -> QueryPlan:
    """cancel_count / cancel_rate count cancelled orders already: an order_status = cancelled filter on them only
    restates the metric (12 of 2895 build_bank plans, 04/11), and on cancel_rate would make every rate 100%."""
    def fix(m):
        kept = [f for f in m.filters if not (f.field == "order_status" and f.value == "cancelled")]
        return m.model_copy(update={"filters": kept}) if len(kept) < len(m.filters) else m
    measures = [fix(m) if m.metric in ("cancel_count", "cancel_rate") else m for m in plan.measures]
    return plan.model_copy(update={"measures": measures}) if measures != list(plan.measures) else plan


def parse_question(question: str, as_of: date, card: DataCard, llm: LLMClient | None = None,
                   exclude_ids: frozenset[str] = frozenset()) -> QueryPlan | None:
    """QueryPlan for the question, or None when it cannot be parsed into a valid plan both readers agree on.
    `exclude_ids`: examples the LLM may not see (development runs on train leave out the business's own questions)."""
    base = baseline.parse(question)
    if llm is None:
        return base
    plan = llm_plan(question, as_of, card, llm, exclude_ids=exclude_ids)
    if plan is None:
        return base  # the LLM failed or its plan had no ground: the baseline's reading, if it has one
    if base is not None and canonical_plan(plan) != canonical_plan(base):
        return None
    return plan


def link_entities(plan: ResolvedPlan, db: CanonicalDB, question: str = "") -> ResolvedPlan:
    """Fill plan.linked / plan.link_scores: each name a filter carries, as written -> the data value it names
    (linking.py, G6). A name is left out when no value is clearly meant; [V] then makes the question abstain.
    `link_scores` keeps the best score of every name tried, linked or not, for the logs."""
    p = plan.plan
    measures = list(p.measures) + ([p.share_of] if p.share_of else [])
    filters = [f for m in measures for f in m.filters] + list((p.compare.filters or []) if p.compare else [])
    linked, scores = dict(plan.linked), dict(plan.link_scores)
    for f in filters:
        if f.field not in LINKED_FIELDS:
            continue
        cands = linking.candidates(f.field, db)
        units = linking.units(db) if f.field == "product" else ()
        for key in filter_keys(f):
            got = linking.link_value(f.field, key, question, cands, units)
            scores[key] = got.score
            if got.value is not None:
                linked[key] = got.value
    return plan.model_copy(update={"linked": linked, "link_scores": scores})
