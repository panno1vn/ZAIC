"""[D1] Metric library: rulebook-exact functions over the canonical schema. Work package G5.

execute() returns None (the question abstains) when no function is registered for the plan, or when the plan has a
filter the function does not declare: a filter must never be dropped silently.
"""
from __future__ import annotations

from datamate.contracts import CanonicalDB, ExecResult, ResolvedPlan

from .registry import REGISTRY, MetricSpec, lookup, metric
from . import sales  # noqa: F401,E402  registers the sales metrics
from . import stock  # noqa: F401,E402  registers purchases, prices and stock (§5)
from . import debt  # noqa: F401,E402  registers debts (§4)
from . import industry  # noqa: F401,E402  registers industry rules (§6)


def metric_name(plan: ResolvedPlan) -> str | None:
    """Registry key of a plan: rank.by for rankings, the threshold's metric for counts (v1.1: no measures needed),
    the condition for lists, else the first measure's metric."""
    p = plan.plan
    if p.intent == "rank" and p.rank is not None:
        return p.rank.by
    if p.intent == "count_where" and p.threshold is not None:
        return p.threshold.metric
    if p.intent == "list_items" and p.list_spec is not None:
        return p.list_spec.condition
    return p.measures[0].metric if p.measures else None


def metric_entity(plan: ResolvedPlan) -> str:
    """The object a ranking, count or list is about ("" for other intents)."""
    p = plan.plan
    if p.intent == "rank" and p.rank is not None:
        return p.rank.entity
    if p.intent == "count_where" and p.threshold is not None:
        return p.threshold.entity
    if p.intent == "list_items" and p.list_spec is not None:
        return p.list_spec.entity
    return ""


def plan_filter_fields(plan: ResolvedPlan) -> set[str]:
    """Every filter field of the plan: measures, share denominator and compared filters."""
    p = plan.plan
    measures = list(p.measures) + ([p.share_of] if p.share_of else [])
    filters = [f for m in measures for f in m.filters] + list((p.compare.filters or []) if p.compare else [])
    return {f.field for f in filters}


def execute(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """Run the registered function for the plan's intent, metric and entity; None when none fits."""
    name = metric_name(plan)
    spec = lookup(plan.plan.intent, name, metric_entity(plan)) if name else None
    if spec is None or not plan_filter_fields(plan) <= set(spec.filters):
        return None
    return spec.fn(plan, db)


__all__ = ["REGISTRY", "MetricSpec", "execute", "lookup", "metric", "metric_entity", "metric_name",
           "plan_filter_fields"]
