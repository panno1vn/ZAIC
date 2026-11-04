"""Industry rules of rulebook §6 that need their own function. Work package G5, v2 metrics in the order of their number
of train questions (docs/research/templates.md).

Probe 04/11 against the train answers of the mapped building-materials shop: delivery batches 9/9.
"""
from __future__ import annotations

from datamate.contracts import CanonicalDB, ExecResult, ResolvedPlan
from datamate.contracts.plan import expected_answer_type

from .registry import metric

R_DELIVERIES = ("§6.vat_lieu_xay_dung.giao_nhieu_dot", "§6.p_luat_rieng_cua_tung_nganh_dung", "§0.p_hom_nay_cua_moi_cau_la")


def delivery_count(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """§6 "số đợt giao trong tháng X": the batches with a delivery day in the period, each batch of each order once
    (the file writes a row per product of a batch), batches of orders later returned included. A batch of a cancelled
    order has no rule: None."""
    ms = plan.plan.measures
    if plan.period is None or len(ms) != 1 or ms[0].filters:
        return None
    d, o = db.table("deliveries"), db.table("orders")
    if d is None or d["delivery_time"].isna().any():
        return None
    day = d["delivery_time"].dt.date
    batches = d[(day >= plan.period.start) & (day <= plan.period.end)]
    unclear = o["status"].eq("cancelled") | o["status"].isna() if o is not None else None
    if unclear is not None and batches["order_id"].isin(set(o.loc[unclear, "order_id"])).any():
        return None
    if "batch_no" in batches.columns and batches["batch_no"].notna().all():
        n = batches[["order_id", "batch_no"]].drop_duplicates().shape[0]
    else:
        n = batches.assign(day=day)[["order_id", "day"]].drop_duplicates().shape[0]
    return ExecResult(value=int(n), answer_type=expected_answer_type(plan.plan), source="D1",
                      function="industry.delivery_count", rule_ids=sorted(R_DELIVERIES),
                      requires=["deliveries.delivery_time", "deliveries.order_id"])


metric("value", "delivery_count", requires=("deliveries.delivery_time",), rules=tuple(sorted(R_DELIVERIES)))(
    delivery_count)
