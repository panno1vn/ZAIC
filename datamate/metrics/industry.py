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


def delivered_qty(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """N130. "Các đơn đặt tháng 3/2026, tới hôm nay đã chở đi bao nhiêu thùng Sơn Dulux …" (public, a building-materials
    shop): of the orders placed in the period (§1 "đơn thuộc kỳ theo ngày đặt"), the base quantity of one product the
    delivery book records delivered by the end of today (§6 "giao nhiều đợt: tính đến hết hôm nay … đợt đã chở vẫn tính
    dù đơn sau đó trả hàng"). Only in the product's base unit (the README's "số lượng giao" is in base units, no
    conversion guessed); a batch of a cancelled order has no rule: None."""
    from datamate.metrics import frames as F
    from datamate.nlu import linking
    ms = plan.plan.measures
    if plan.period is None or len(ms) != 1:
        return None
    m = ms[0]
    products = [f for f in m.filters if f.field == "product"]
    if len(products) != 1 or len(m.filters) != 1 or products[0].op != "eq":
        return None
    key = plan.linked.get(str(products[0].value))
    d, o = db.table("deliveries"), F.orders(db)
    if key is None or d is None or o is None or not {"product_key", "base_qty"} <= set(d.columns) \
            or d["delivery_time"].isna().any():
        return None
    base = F.base_units(db).get(str(key))
    if m.unit and (base is None or linking.norm(m.unit) != linking.norm(base)):
        return None
    placed = o[(o["day"] >= plan.period.start) & (o["day"] <= plan.period.end)]
    if placed["status"].eq("cancelled").any() and d["order_id"].isin(set(placed.loc[placed["status"].eq("cancelled"),
                                                                                     "order_id"])).any():
        return None
    rows = d[d["order_id"].isin(set(placed["order_id"])) & (d["product_key"].astype(str) == str(key))
             & (d["delivery_time"].dt.date <= plan.as_of)]
    if rows["base_qty"].isna().any():
        return None
    q = float(rows["base_qty"].sum())
    return ExecResult(value=int(q) if q.is_integer() else q, answer_type="number", source="D1",
                      function="industry.delivered_qty", rule_ids=sorted(R_DELIVERIES),
                      requires=["deliveries.delivery_time", "deliveries.order_id", "deliveries.product_key",
                                "deliveries.base_qty"])


metric("value", "delivered_qty", requires=("deliveries.product_key", "deliveries.base_qty"),
       rules=tuple(sorted(R_DELIVERIES)), filters=("product",))(delivered_qty)


def orders_by_batches(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """"Đơn đặt tháng 6/2025, tới hôm nay có mấy đơn đã giao từ 2 đợt trở lên" (public 06/11, 3 questions): the orders
    placed in the period (by order day, §1) with at least / more than N batches delivered by the end of today (§6
    "giao nhiều đợt: tính đến hết hôm nay"); a batch of an order later returned counts ("đợt đã chở vẫn tính"). An
    order of the period with no status, or a cancelled one with a batch: no rule, None."""
    t = plan.plan.threshold
    if t is None or t.entity != "order" or t.op not in ("gte", "gt") or plan.period is None \
            or any(m.filters for m in plan.plan.measures):
        return None
    d, o = db.table("deliveries"), db.table("orders")
    if d is None or o is None or d["delivery_time"].isna().any() or o["order_time"].isna().any():
        return None
    day = o["order_time"].dt.date
    placed = o[(day >= plan.period.start) & (day <= plan.period.end)]
    if placed["status"].isna().any():
        return None
    upto = d[d["delivery_time"].dt.date <= plan.as_of]
    batch = "batch_no" if "batch_no" in upto.columns and upto["batch_no"].notna().all() else None
    upto = upto.assign(_b=upto[batch] if batch else upto["delivery_time"].dt.date)
    per = upto.groupby("order_id")["_b"].nunique()
    cancelled = placed.loc[placed["status"].eq("cancelled"), "order_id"]
    if cancelled.isin(per.index).any():
        return None
    counts = placed["order_id"].map(per).fillna(0)
    hits = int((counts >= t.value).sum() if t.op == "gte" else (counts > t.value).sum())
    return ExecResult(value=hits, answer_type=expected_answer_type(plan.plan), source="D1",
                      function="industry.orders_by_batches", rule_ids=sorted(R_DELIVERIES + ("§1.don_thuoc_ky_nao",)),
                      requires=["deliveries.delivery_time", "deliveries.order_id", "orders.order_time"])


metric("count_where", "delivery_count", entity="order", requires=("deliveries.delivery_time",),
       rules=tuple(sorted(R_DELIVERIES + ("§1.don_thuoc_ky_nao",))))(orders_by_batches)
