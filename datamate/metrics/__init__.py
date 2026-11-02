"""[D1] Metric library: rulebook-exact functions over the canonical schema. Work package G5.

No metric is registered yet, so execute() returns None and the question abstains.
"""
from __future__ import annotations

from datamate.contracts import CanonicalDB, ExecResult, ResolvedPlan

from .registry import REGISTRY, MetricSpec, lookup, metric
from . import sales  # noqa: F401,E402  registers the sales metrics


def metric_name(plan: ResolvedPlan) -> str | None:
    """Registry key of a plan: rank.by for rankings, the condition for lists, else the first measure's metric."""
    p = plan.plan
    if p.intent == "rank" and p.rank is not None:
        return p.rank.by
    if p.intent == "list_items" and p.list_spec is not None:
        return p.list_spec.condition
    return p.measures[0].metric if p.measures else None


def execute(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """Run the registered function for the plan's intent and metric; None when none is registered."""
    name = metric_name(plan)
    spec = lookup(plan.plan.intent, name) if name else None
    return spec.fn(plan, db) if spec else None


__all__ = ["REGISTRY", "MetricSpec", "execute", "lookup", "metric", "metric_name"]
