"""Lots and their expiry (§6 Nhà thuốc) and products out of stock at the end of a day (§5). N74.

What is left of a lot at the end of day D: what it received (its receipt dated D or earlier), less the sales from it
of orders placed by D (cancelled orders take nothing), plus what customers brought back to it by D (by the return's
day: "hàng khách trả về lại lô đã bán"). Checked on a train pharmacy before writing (07/11): the lots of each product
add up to the stock card for 80/80 products at three days; by the order's day instead of the return's, 78/80. Then
the train answers: the nearest expiry of 3/3 products, the cost value of the lots expiring in a window (7 899 400),
the products expiring in 120 days in their order, the number of products out of stock at the end of a day.

A lot whose receipt or return day is unknown counts only at the end of the data (when every receipt and return has
happened); before it, no figure.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from datamate.contracts import CanonicalDB, ExecResult, ResolvedPlan
from datamate.contracts.plan import expected_answer_type
from datamate.formatter import money

from . import frames as F
from .registry import metric
from .sales import _first_name
from .stock import R_NAMES, R_TODAY, _one_product, stock_base_qty

R_EXPIRING = ("§6.nha_thuoc.hang_het_han_trong_n_ngay_toi",) + R_TODAY
R_NEAREST = ("§6.nha_thuoc.lo_gan_het_han_nhat_cua_mot_thuoc",) + R_TODAY
R_OUT = ("§5.mat_hang_het_hang_cuoi_ngay", "§2.den_het_ngay_x_tinh_den_hom_nay") + R_TODAY
R_STOCK_VALUE = ("§5.gia_tri_hang_ton_kho", "§2.den_het_ngay_x_tinh_den_hom_nay") + R_TODAY
REQ_LOTS = ("lots.lot_id", "lots.product_key", "lots.expiry_date", "lots.base_qty_in", "lot_sales.lot_id",
            "lot_sales.base_qty", "orders.order_time")


def _day(v) -> date | None:
    t = pd.to_datetime(v, errors="coerce")
    return None if pd.isna(t) else t.date()


def lots_left(db: CanonicalDB, day: date) -> pd.DataFrame | None:
    """Every lot received by the end of `day`, with `left` (base units still in it) and `expiry` (a date); None when
    the tables cannot tell exactly."""
    lots, sold, orders = db.table("lots"), db.table("lot_sales"), db.table("orders")
    if lots is None or sold is None or orders is None or lots.empty or "order_time" not in orders.columns:
        return None
    need = ["lot_id", "product_key", "expiry_date", "base_qty_in"]
    if any(c not in lots.columns for c in need) or lots[need].isna().any().any() or not lots["lot_id"].is_unique:
        return None
    if sold[["lot_id", "base_qty"]].isna().any().any() or not sold["lot_id"].isin(lots["lot_id"]).all():
        return None
    o = orders.dropna(subset=["order_time"]).drop_duplicates("order_id").set_index("order_id")
    last = o["order_time"].max().date()
    placed = sold["order_id"].map(o["order_time"]).dt.date
    if placed.isna().any():
        return None  # a sale from a lot of an order the orders do not know
    status = sold["order_id"].map(o["status"]) if "status" in o.columns else pd.Series(None, index=sold.index)
    taken = sold[(placed <= day) & status.ne("cancelled")]
    lots = lots.assign(expiry=lots["expiry_date"].map(_day))
    if lots["expiry"].isna().any():
        return None
    received = _receipt_days(db, lots)
    if received.isna().any() and day < last:
        return None
    lots = lots[received.isna() | (received <= day)]
    back = sold[sold["returned_base_qty"].fillna(0) > 0] if "returned_base_qty" in sold.columns else sold.iloc[:0]
    if not back.empty:
        ret = db.table("returns")
        when = back["order_id"].map(ret.dropna(subset=["return_time"]).drop_duplicates("order_id")
                                    .set_index("order_id")["return_time"]).dt.date \
            if ret is not None and "return_time" in ret.columns else pd.Series(None, index=back.index, dtype=object)
        if when.isna().any() and day < last:
            return None
        back = back[when.isna() | (when <= day)]
    left = (lots.set_index("lot_id")["base_qty_in"].astype(float)
            .sub(taken.groupby("lot_id")["base_qty"].sum(), fill_value=0)
            .add(back.groupby("lot_id")["returned_base_qty"].sum(), fill_value=0))
    lots = lots.assign(left=lots["lot_id"].map(left))
    if (lots["left"] < -1e-9).any():
        return None
    return lots


def _receipt_days(db: CanonicalDB, lots: pd.DataFrame) -> pd.Series:
    """The day each lot was received, from its receipt's day in the purchases; None where unknown."""
    pur = db.table("purchases")
    if pur is None or "receipt_id" not in lots.columns or "receipt_time" not in pur.columns:
        return pd.Series(None, index=lots.index, dtype=object)
    days = pur.dropna(subset=["receipt_time"]).drop_duplicates("receipt_id").set_index("receipt_id")["receipt_time"]
    return lots["receipt_id"].map(days).map(lambda t: None if pd.isna(t) else t.date())


def _today(plan: ResolvedPlan) -> date:
    """The day the stock is read at: the end of the plan's period ("tính đến hết ngày X"), never after today."""
    return min(plan.period.end, plan.as_of) if plan.period is not None else plan.as_of


def expiry_window(plan: ResolvedPlan, day: date, n: int | float | None = None) -> tuple[date, date] | None:
    """§6 "hết hạn trong N ngày tới": expiry dates from day D to the end of D + N. The window comes from N (the list's
    n or the plan's expiry_within_days filter) or from the plan's own period as the question wrote it (a range "hạn
    dùng từ 08/08 tới hết 06/12", "trong 90 ngày tới"): two that disagree (public 07/11: a range of 120 days beside a
    filter of 365) or none at all, no window. A plan period that only restates today is no window."""
    windows = set()
    if n is not None:
        windows.add((day, day + timedelta(days=int(n))))
    p = plan.plan.period
    if p is not None:
        if p.kind == "range" and p.start and p.end and len(p.start) == 10 and len(p.end) == 10:
            windows.add((date.fromisoformat(p.start), date.fromisoformat(p.end)))
        elif p.kind == "next_n_days" and p.n:
            windows.add((day, day + timedelta(days=p.n)))
        elif p.kind == "last_n_days" and p.n and n is not None and p.n == n:
            pass  # "hết hạn trong N ngày tới" with the N days also written as a past period: the same N
        elif not (p.kind == "today" or (p.kind == "until" and p.date == day.isoformat())):
            return None
    if len(windows) != 1:
        return None
    start, end = windows.pop()
    return (start, end) if start == day and end >= start else None


def _within_days(plan: ResolvedPlan) -> tuple[bool, float | None, bool]:
    """(the measures' filters are only expiry_within_days, its N or None, whether the plan's period must confirm it).
    "Trong 90 ngày tới" comes with any comparison (train bank: gte 90 beside the range D..D + 90); a bound other than
    "within" (eq, lte, lt) counts only when the period writes the same window."""
    fs = [f for m in plan.plan.measures for f in m.filters]
    if any(f.field != "expiry_within_days" for f in fs):
        return False, None, False
    try:
        ns = {float(f.value) for f in fs}
    except (TypeError, ValueError):
        return False, None, False
    if len(ns) > 1 or any(v <= 0 or not v.is_integer() for v in ns):
        return False, None, False
    return True, (ns.pop() if ns else None), any(f.op not in ("eq", "lte", "lt") for f in fs)


def _result(plan: ResolvedPlan, value, rules: tuple[str, ...], requires: tuple[str, ...], fn: str,
            answer_type: str | None = None) -> ExecResult | None:
    answer_type = answer_type or expected_answer_type(plan.plan)
    if value is None or answer_type is None:
        return None
    return ExecResult(value=value, answer_type=answer_type, source="D1", function=f"lots.{fn}",
                      rule_ids=sorted(set(rules + R_NAMES)), requires=sorted(set(requires)))


def _no_window(plan: ResolvedPlan) -> bool:
    """A period that only names the day the stock is read at (today, "đến hết ngày X"): no expiry window."""
    p = plan.plan.period
    return p is None or p.kind in ("today", "until")


def stock_value_by_catalogue(db: CanonicalDB, day: date) -> float | None:
    """§5 "giá trị hàng tồn kho": each product's stock at the end of the day (stock_base_qty, base units) times the
    cost of one base unit the catalogue writes; goods still in stock only. Train: both answers of the shops whose
    mapping has the catalogue and the stock, to the đồng (one mapped by transfer, one by hand). None when a product in
    stock has no cost, or a stock cannot be read or is negative."""
    inv, products = db.table("inventory"), db.table("products")
    if inv is None or products is None or "unit_cost" not in products.columns:
        return None
    seen = inv[pd.to_datetime(inv["as_of"], errors="coerce").dt.date <= day]
    keys = sorted(seen["product_key"].dropna().astype(str).unique())
    left = {k: stock_base_qty(db, k, day) for k in keys}
    if not keys or any(v is None or v < 0 for v in left.values()):
        return None
    catalogue = products.dropna(subset=["product_key"]).assign(key=lambda d: d["product_key"].astype(str))
    cost = catalogue.drop_duplicates("key").set_index("key")["unit_cost"]
    held = {k: v for k, v in left.items() if v > 0}
    if any(k not in cost.index or pd.isna(cost[k]) for k in held):
        return None
    return money(float(sum(v * float(cost[k]) for k, v in held.items())))


# ---------------------------------------------------------------- one figure
def value_of(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    ms = plan.plan.measures
    if len(ms) != 1:
        return None
    m, day = ms[0], _today(plan)
    if m.metric == "stock_value" and not m.filters and _no_window(plan):
        value = stock_value_by_catalogue(db, day)
        return _result(plan, value, R_STOCK_VALUE, ("inventory.base_qty", "inventory.as_of", "products.unit_cost"),
                       "stock_value_by_catalogue")
    if m.metric == "nearest_expiry":
        # §6 "lô gần hết hạn nhất của một thuốc: trong các lô còn tồn chưa quá hạn tại hôm nay, lô có hạn sớm nhất"
        product = _one_product(m, plan.linked)
        if product is None or any(f.field != "product" for f in m.filters):
            return None
        lots = lots_left(db, day)
        if lots is None:
            return None
        live = lots[(lots["product_key"].astype(str) == product) & (lots["left"] > 0) & (lots["expiry"] >= day)]
        if live.empty:
            return None
        return _result(plan, min(live["expiry"]), R_NEAREST, REQ_LOTS, "nearest_expiry", "date")
    # §6 "Tiền vốn là giá trị phần còn tồn của lô, theo giá nhập của chính lô đó quy về đơn vị cơ bản": the lots
    # still holding goods whose expiry falls in the window ("đang đọng bao nhiêu tiền vốn")
    ok, n, confirm = _within_days(plan)
    window = expiry_window(plan, day, n) if ok else None
    if window is not None and confirm and expiry_window(plan, day) != window:
        window = None  # "gte 90" alone is no window; with the range D..D + 90 written beside it, it is that range
    lots = lots_left(db, day) if window is not None else None
    if lots is None or "unit_cost" not in lots.columns:
        return None
    live = lots[(lots["left"] > 0) & (lots["expiry"] >= window[0]) & (lots["expiry"] <= window[1])]
    if live["unit_cost"].isna().any():
        return None
    value = money(float((live["left"] * live["unit_cost"].astype(float)).sum()))
    return _result(plan, value, R_EXPIRING, REQ_LOTS + ("lots.unit_cost",), "expiring_value")


# ---------------------------------------------------------------- lists
def expiring(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """§6 "hàng hết hạn trong N ngày tới": the products with a lot still holding goods whose expiry falls in the
    window, listed by their earliest such expiry, then by code (§9 "liệt kê hàng theo hạn dùng"); or how many."""
    ls, day = plan.plan.list_spec, _today(plan)
    if ls.entity not in ("product", "lot") or any(m.filters for m in plan.plan.measures):
        return None
    window = expiry_window(plan, day, ls.n)
    lots = lots_left(db, day) if window is not None else None
    if lots is None:
        return None
    live = lots[(lots["left"] > 0) & (lots["expiry"] >= window[0]) & (lots["expiry"] <= window[1])]
    if ls.entity == "lot":  # N99 "mấy lô còn tồn sẽ hết hạn …": the lots themselves, how many
        return _result(plan, int(live["lot_id"].nunique()), R_EXPIRING, REQ_LOTS, "expiring") if ls.count else None
    first = live.assign(key=live["product_key"].astype(str)).groupby("key")["expiry"].min()
    keys = sorted(first.index, key=lambda k: (first[k], k))
    if ls.count:
        return _result(plan, len(keys), R_EXPIRING, REQ_LOTS, "expiring")
    if not keys:
        return None
    return _result(plan, [_names(db).get(k, k) for k in keys], R_EXPIRING, REQ_LOTS, "expiring")


def out_of_stock(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """§5 "mặt hàng hết hàng cuối ngày": goods bought to be sold (those the stock records follow; a drink made on the
    spot has none) whose stock at the end of the day is 0; how many, or which by code (§9)."""
    ls, day = plan.plan.list_spec, _today(plan)
    inv = db.table("inventory")
    if ls.entity != "product" or any(m.filters for m in plan.plan.measures) or inv is None:
        return None
    seen = inv[pd.to_datetime(inv["as_of"], errors="coerce").dt.date <= day]
    keys = sorted(seen["product_key"].dropna().astype(str).unique())
    left = {k: stock_base_qty(db, k, day) for k in keys}
    if not keys or any(v is None or v < 0 for v in left.values()):
        return None
    out = [k for k in keys if left[k] == 0]
    requires = ("inventory.base_qty", "inventory.as_of", "inventory.product_key")
    if ls.count:
        return _result(plan, len(out), R_OUT, requires, "out_of_stock")
    if not out:
        return None
    return _result(plan, [_names(db).get(k, k) for k in out], R_OUT, requires, "out_of_stock")


def _names(db: CanonicalDB) -> dict[str, str]:
    """A name for each product code: the catalogue's, else the most frequent on the sales lines."""
    pr = db.table("products")
    if pr is not None and "product_name" in pr.columns:
        names = pr.dropna(subset=["product_name"]).drop_duplicates("product_key")
        out = dict(zip(names["product_key"].astype(str), names["product_name"]))
        if out:
            return out
    ln = F.lines(db)
    return _first_name(ln["product_key"], ln["product_name"]) if ln is not None and "product_name" in ln.columns else {}


# ---------------------------------------------------------------- registry
metric("value", "nearest_expiry", requires=REQ_LOTS, rules=tuple(sorted(set(R_NEAREST + R_NAMES))),
       filters=("product",))(value_of)
for _name in ("expiring_value", "stock_value"):
    # stock_value: the LLM's word for "tiền vốn của các lô hết hạn từ … đến …"; with no filter and no window, §5 "giá
    # trị hàng tồn kho" by the catalogue's cost (stock_value_by_catalogue, any shop with stock records)
    extra = R_STOCK_VALUE if _name == "stock_value" else ()  # [R] checks the rows a function may cite (08/11: the
    # catalogue value cited §5 "giá trị hàng tồn kho" while no registered metric did, so the rule gate refused it)
    metric("value", _name, requires=REQ_LOTS + ("lots.unit_cost",),
           rules=tuple(sorted(set(R_EXPIRING + R_NAMES + extra))), filters=("expiry_within_days",))(value_of)
for _entity in ("product", "lot"):
    metric("list_items", "expiring_within", entity=_entity, requires=REQ_LOTS,
           rules=tuple(sorted(set(R_EXPIRING + R_NAMES))))(expiring)
metric("list_items", "out_of_stock_end_of_day", entity="product", requires=("inventory.base_qty", "inventory.as_of"),
       rules=tuple(sorted(set(R_OUT + R_NAMES))))(out_of_stock)
