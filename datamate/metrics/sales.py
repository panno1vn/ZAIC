"""Sales metrics on orders + lines, exact to rulebook §1 and §3. Work package G5 adds the rest of the library.

Valid order (§1 "Đơn tính vào doanh thu"): not cancelled and not returned (a partial return drops the whole order);
orders in delivery count. An order belongs to the period of its order date (§1 "Đơn thuộc kỳ nào").
"""
from __future__ import annotations

import pandas as pd

from datamate.contracts import CanonicalDB, ExecResult, ResolvedPlan
from datamate.formatter import money

from .registry import metric

VALID_STATUSES = ("completed", "delivering")
R_VALID = ("§1.don_tinh_vao_doanh_thu", "§1.don_thuoc_ky_nao", "§0.p_hom_nay_cua_moi_cau_la")
R_REVENUE = R_VALID + ("§1.doanh_thu_mot_don", "§1.ban_duoc_bao_nhieu_tien_thu_ve_bao_nhieu_tien", "§3.mat_hang")
R_TIES = ("§9.p_bang_nhau_hai_doi_tuong_bang",)


def valid_orders(plan: ResolvedPlan, db: CanonicalDB) -> pd.DataFrame | None:
    """Orders counted in revenue (§1) whose order date lies in the plan's period."""
    orders = db.table("orders")
    if orders is None or plan.period is None:
        return None
    day = orders["order_time"].dt.date
    keep = orders["status"].isin(VALID_STATUSES) & (day >= plan.period.start) & (day <= plan.period.end)
    return orders[keep]


def valid_lines(plan: ResolvedPlan, db: CanonicalDB) -> pd.DataFrame | None:
    orders, lines = valid_orders(plan, db), db.table("lines")
    if orders is None or lines is None:
        return None
    return lines.merge(orders[["order_id", "order_time"]], on="order_id", how="inner")


@metric("value", "revenue", requires=("orders.order_time", "orders.status", "lines.line_amount"), rules=R_REVENUE)
def revenue(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    if any(m.filters for m in plan.plan.measures) or len(plan.plan.measures) != 1:
        return None  # filters come with G5/G6
    lines = valid_lines(plan, db)
    if lines is None or lines["line_amount"].isna().any():
        return None
    return ExecResult(value=money(float(lines["line_amount"].sum())), answer_type="number", source="D1",
                      function="sales.revenue", rule_ids=list(R_REVENUE),
                      requires=["orders.order_time", "orders.status", "lines.line_amount"])


@metric("value", "order_count", requires=("orders.order_time", "orders.status"), rules=R_VALID + ("§1.so_don",))
def order_count(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    if any(m.filters for m in plan.plan.measures) or len(plan.plan.measures) != 1:
        return None
    orders = valid_orders(plan, db)
    if orders is None:
        return None
    return ExecResult(value=int(orders["order_id"].nunique()), answer_type="number", source="D1",
                      function="sales.order_count", rule_ids=list(R_VALID + ("§1.so_don",)),
                      requires=["orders.order_time", "orders.status"])


@metric("rank", "quantity", requires=("orders.order_time", "orders.status", "lines.base_qty"),
        rules=R_VALID + ("§3.ban_chay", "§3.mat_hang") + R_TIES, entity="product")
def top_products(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """Best sellers by quantity in base units (§3 "Bán chạy"); ties by product key ascending (§9)."""
    r = plan.plan.rank
    if r.entity != "product" or r.order != "desc" or r.with_values or plan.plan.measures and plan.plan.measures[0].filters:
        return None
    lines = valid_lines(plan, db)
    if lines is None or "base_qty" not in lines.columns:
        return None
    items = lines[lines["is_item"].ne(False)] if "is_item" in lines.columns else lines  # not marked as fee or voucher
    if items.empty or items["base_qty"].isna().any():
        return None  # a line without base quantity cannot be ranked safely
    totals = items.groupby("product_key").agg(qty=("base_qty", "sum"), name=("product_name", "first")).reset_index()
    totals = totals.sort_values(["qty", "product_key"], ascending=[False, True])
    names = totals["name"].head(r.k or len(totals)).tolist()
    value = names[0] if r.k == 1 else names
    return ExecResult(value=value, answer_type="string" if r.k == 1 else "list", source="D1",
                      function="sales.top_products", rule_ids=list(R_VALID + ("§3.ban_chay", "§3.mat_hang") + R_TIES),
                      requires=["orders.order_time", "orders.status", "lines.base_qty"])


@metric("rank", "revenue", requires=("orders.order_time", "orders.status", "lines.line_amount"),
        rules=R_REVENUE + R_TIES, entity="day")
def top_days_by_revenue(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """Day with the highest revenue in the period; ties by the earlier date."""
    r = plan.plan.rank
    if r.entity != "day" or r.k != 1 or r.order != "desc" or plan.plan.measures and plan.plan.measures[0].filters:
        return None
    lines = valid_lines(plan, db)
    if lines is None or lines.empty or lines["line_amount"].isna().any():
        return None
    by_day = lines.groupby(lines["order_time"].dt.date)["line_amount"].sum().reset_index()
    by_day.columns = ["day", "revenue"]
    best = by_day.sort_values(["revenue", "day"], ascending=[False, True]).iloc[0]
    return ExecResult(value=best["day"].isoformat(), answer_type="date", source="D1",
                      function="sales.top_days_by_revenue", rule_ids=list(R_REVENUE + R_TIES),
                      requires=["orders.order_time", "orders.status", "lines.line_amount"])
