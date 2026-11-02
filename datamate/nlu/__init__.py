"""[C] Understand the question: normalise Vietnamese, ask the LLM for a QueryPlan (structured output). Work package G3.
[C3] Link names in the plan to values in the data. Work package G6.

Skeleton (05/11): without an LLM, the rule-based parser (nlu/baseline.py) handles a few frequent shapes; linking
is not done yet, so plans with name filters stay unlinked and abstain.
"""
from __future__ import annotations

from datetime import date

from datamate.contracts import CanonicalDB, DataCard, QueryPlan, ResolvedPlan
from datamate.llm import LLMClient

from . import baseline


def parse_question(question: str, as_of: date, card: DataCard, llm: LLMClient | None = None) -> QueryPlan | None:
    """QueryPlan for the question, or None when it cannot be parsed into a valid plan."""
    if llm is None:
        return baseline.parse(question)
    return None  # G3: LLM with structured output, baseline as cross-check


def link_entities(plan: ResolvedPlan, db: CanonicalDB) -> ResolvedPlan:
    """Fill plan.linked / plan.link_scores: each filter value as written -> the closest value in the data (G6)."""
    return plan
