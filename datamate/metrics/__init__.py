"""[D1] Metric library: rulebook-exact functions over the canonical schema. Work package G5.

execute() returns None (the question abstains) when no function is registered for the plan, or when the plan has a
filter the function does not declare: a filter must never be dropped silently.
"""
from __future__ import annotations

from datamate import diagnose
from datamate.contracts import CanonicalDB, ExecResult, ResolvedPlan

from . import frames
from .registry import REGISTRY, MetricSpec, lookup, metric
from . import sales  # noqa: F401,E402  registers the sales metrics
from . import stock  # noqa: F401,E402  registers purchases, prices and stock (§5)
from . import debt  # noqa: F401,E402  registers debts (§4)
from . import industry  # noqa: F401,E402  registers industry rules (§6)
from . import lots  # noqa: F401,E402  registers lots, expiry and out of stock (§5, §6 Nhà thuốc)


# N166: the §2 rows a function reads by the kind of period, cited whatever the function (F006: the rows for week, last
# N days and year-to-date were cited by none, so a rulebook that changed them still got the old formula)
PERIOD_RULES = {
    "day": ("§2.ngay_x_hom_nay_hom_qua",), "today": ("§2.ngay_x_hom_nay_hom_qua",),
    "yesterday": ("§2.ngay_x_hom_nay_hom_qua",),
    "this_week": ("§2.tuan",), "last_week": ("§2.tuan",),
    "this_month": ("§2.thang_nay",), "month": ("§2.thang_m_y",),
    "ytd": ("§2.tu_dau_nam_tu_dau_nam_toi_nay",), "last_n_days": ("§2.n_ngay_gan_nhat",),
    "range": ("§2.tu_x_den_y_nhom_x_y",), "tet": ("§2.tet_nam_y_dip_tet_mua_tet",),
    "until": ("§2.den_het_ngay_x_tinh_den_hom_nay",),
}
YEARLESS = ("§2.thang_m_quy_q_khong_ghi_nam",)  # a month or quarter written without its year


def period_rules(plan: ResolvedPlan) -> tuple[str, ...]:
    out: tuple[str, ...] = ()
    c = plan.plan.compare
    for pe in (plan.plan.period, c.period if c is not None else None):
        if pe is None:
            continue
        out += PERIOD_RULES.get(pe.kind, ())
        if pe.kind in ("month", "quarter") and pe.year is None:
            out += YEARLESS
    return out


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


def execute(plan: ResolvedPlan, db: CanonicalDB, trace: dict | None = None) -> ExecResult | None:
    """Run the registered function for the plan's intent, metric and entity; None when none fits.
    `trace`: filled with why there is no result (the question's log, N72); with diagnose.ENABLED, also where inside
    the function it stopped."""
    name = metric_name(plan)
    entity = metric_entity(plan)
    spec = lookup(plan.plan.intent, name, entity) if name else None
    extra = plan_filter_fields(plan) - set(spec.filters) if spec is not None else set()
    if spec is None or extra:
        if trace is not None:
            trace.update({"why": "no_function", "key": [plan.plan.intent, name, entity]} if spec is None else
                         {"why": "filter_not_taken", "function": spec.fn.__name__, "fields": sorted(extra)})
        return None
    result = spec.fn(plan, db)
    if result is not None:  # what the figure read in this shop (an orders-only shop: the order's goods amount)
        result.requires = frames.requires(db, result.requires)
        result.rule_ids = sorted(set(result.rule_ids) | set(period_rules(plan)))
    elif trace is not None:
        trace.update({"why": "function_none", "function": spec.fn.__name__})
        if diagnose.ENABLED:
            trace["at"] = diagnose.none_chain(spec.fn, plan, db)
    return result


__all__ = ["PERIOD_RULES", "YEARLESS", "period_rules", "REGISTRY", "MetricSpec", "execute", "lookup", "metric", "metric_entity", "metric_name",
           "plan_filter_fields"]
