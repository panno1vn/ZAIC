"""Sales metrics, exact to rulebook §1–§3 (with §5 "hàng ế", price effect, §6 size and pharmacy rows). Work package
G5 / T3, ordered by the number of train questions each template carries (docs/research/templates.md).

A measure function gives one figure for a period under some filters, or None when it cannot be exact. The intent
functions build on them: value (one figure or several), compare (two periods, or two filters), share, rank, count
over a threshold, trend, series and unsold products. Every one returns None rather than a guess.
"""
from __future__ import annotations

import operator
from collections.abc import Callable

import pandas as pd

from datamate.contracts import CanonicalDB, ExecResult, Filter, Measure, ResolvedPeriod, ResolvedPlan
from datamate.contracts.plan import expected_answer_type
from datamate.formatter import money
from datamate.nlu import linking

from . import frames as F
from .registry import metric

# ---------------------------------------------------------------- rule ids (assets/rules/reference_rules.json)
R_TODAY = ("§0.p_hom_nay_cua_moi_cau_la",)
R_VALID = ("§1.don_tinh_vao_doanh_thu", "§1.don_thuoc_ky_nao") + R_TODAY
R_REVENUE = R_VALID + ("§1.doanh_thu_mot_don", "§1.ban_duoc_bao_nhieu_tien_thu_ve_bao_nhieu_tien", "§3.mat_hang")
R_FILTERS = ("§1.doanh_thu_theo_hinh_thuc_thanh_toan", "§1.doanh_thu_theo_nhom_khach", "§2.ca_sang_ca_chieu",
             "§3.nhom_hang", "§3.xac_dinh_khach", "§6.ca_phe.size_m_size_l", "§6.nha_thuoc.doanh_thu_theo_hoat_chat",
             "§6.nha_thuoc.thuoc_ke_don", "§8.ten_goi_nhan")
R_METRIC = {
    "revenue": R_REVENUE,
    "order_count": R_VALID + ("§1.so_don",),
    "cancel_count": ("§1.don_bi_huy", "§1.don_thuoc_ky_nao") + R_TODAY,
    "cancel_rate": ("§1.ti_le_don_huy_trong_ky", "§1.don_bi_huy", "§1.don_thuoc_ky_nao") + R_TODAY,
    "avg_order_value": R_REVENUE + ("§1.so_don", "§3.gia_tri_trung_binh_mot_don"),
    "quantity": R_VALID + ("§3.mat_hang", "§3.ban_duoc_bao_nhieu_don_vi", "§10.don_vi_co_ban_don_vi_lon"),
    "customer_count": R_VALID + ("§1.so_don", "§3.xac_dinh_khach"),
    "gross_profit": R_REVENUE + ("§5.lai_gop", "§3.hang_loi_nhat"),
    "net_profit": R_REVENUE + ("§5.lai_gop", "§5.lai_rong_mot_thang"),
}
R_COMPARE = ("§1.phan_tram_thay_doi_tang_truong", "§1.chenh_lech_hon_kem_tang_giam_bao_nhieu_so_khong_",
             "§2.thang_nay", "§2.tet_nam_y_dip_tet_mua_tet", "§5.hieu_ung_tang_gia")
R_TIES = ("§9.p_bang_nhau_hai_doi_tuong_bang",)
R_RANK = R_TIES + ("§3.ban_chay", "§3.xac_dinh_khach", "§3.nhan_vien_ban_gioi_nhat")
R_COUNT = ("§2.qua_n_hon_n_tren_n_duoi_n", "§1.so_don", "§3.xac_dinh_khach")
R_UNSOLD = R_VALID + ("§5.mat_hang_khong_ban_duoc_trong_ky_e", "§3.mat_hang")

REQ_ORDERS = ("orders.order_time", "orders.status")
REQ_METRIC = {
    "revenue": REQ_ORDERS + ("lines.line_amount",),
    "order_count": REQ_ORDERS,
    "cancel_count": REQ_ORDERS,
    "cancel_rate": REQ_ORDERS,
    "avg_order_value": REQ_ORDERS + ("lines.line_amount",),
    "quantity": REQ_ORDERS + ("lines.base_qty",),
    "customer_count": REQ_ORDERS + ("orders.customer_key",),
    "gross_profit": REQ_ORDERS + ("lines.line_amount", "lines.unit_cost"),
    "net_profit": REQ_ORDERS + ("lines.line_amount", "lines.unit_cost", "expenses.amount"),
}


# ---------------------------------------------------------------- one figure for a period
def _line_filtered(filters: list[Filter]) -> bool:
    return any(f.field in F.LINE_FILTERS for f in filters)


def _orders(db: CanonicalDB, period: ResolvedPeriod, filters: list[Filter], linked: dict[str, str],
            statuses: tuple[str, ...] | None = F.VALID_STATUSES) -> pd.DataFrame | None:
    """Orders of the period (by order date, §1) passing the order-level filters; `statuses` None = every status."""
    o = F.orders(db)
    if o is None:
        return None
    mask = F.order_mask(o, filters, linked)
    if mask is None:
        return None
    mask &= F.in_period(o, period)
    if F.unknown_status(o[mask]):
        return None
    if statuses is not None:
        mask &= o["status"].isin(statuses)
    return o[mask]


def _lines(db: CanonicalDB, period: ResolvedPeriod, filters: list[Filter], linked: dict[str, str],
           items_only: bool = False) -> pd.DataFrame | None:
    """Lines of the period's valid orders passing every filter; `items_only` drops fee lines (§3 "Phí phục vụ")."""
    o, ln = _orders(db, period, filters, linked), F.lines(db)
    if o is None or ln is None:
        return None
    mask = F.line_mask(ln, filters, linked)
    if mask is None:
        return None
    mask &= ln["order_id"].isin(set(o["order_id"]))
    if items_only and "is_item" in ln.columns:
        mask &= ln["is_item"].ne(False)
    return ln[mask]


def revenue(db, period, filters, linked, m=None, strict_unit=True):
    if _line_filtered(filters):  # revenue of the matching lines only (a product, a group)
        ln = _lines(db, period, filters, linked)
        if ln is None or ln["line_amount"].isna().any():
            return None
        return money(float(ln["line_amount"].sum()))
    o = _orders(db, period, filters, linked)
    if o is None or not o["revenue_ok"].all():
        return None
    return money(float(o["revenue"].sum()))


def order_count(db, period, filters, linked, m=None, strict_unit=True):
    if _line_filtered(filters):  # §1 "số đơn có một mặt hàng": valid orders with at least one matching line
        ln = _lines(db, period, filters, linked)
        return None if ln is None else int(ln["order_id"].nunique())
    o = _orders(db, period, filters, linked)
    return None if o is None else int(o["order_id"].nunique())


def cancel_count(db, period, filters, linked, m=None, strict_unit=True):
    if _line_filtered(filters):
        return None
    o = _orders(db, period, filters, linked, statuses=("cancelled",))
    return None if o is None else int(o["order_id"].nunique())


def cancel_rate(db, period, filters, linked, m=None, strict_unit=True):
    """§1: cancelled orders over every order placed in the period, whatever its status."""
    if _line_filtered(filters):
        return None
    every = _orders(db, period, filters, linked, statuses=None)
    if every is None or every.empty:
        return None
    return float((every["status"] == "cancelled").sum() / every["order_id"].nunique() * 100)


def avg_order_value(db, period, filters, linked, m=None, strict_unit=True):
    """§3: revenue / number of valid orders, in whole đồng (half up)."""
    if _line_filtered(filters):
        return None
    o = _orders(db, period, filters, linked)
    if o is None or o.empty or not o["revenue_ok"].all():
        return None
    return money(float(o["revenue"].sum()) / o["order_id"].nunique())


def quantity(db, period, filters, linked, m: Measure | None = None, strict_unit=True):
    """§3: quantity in base units. "Bao nhiêu <đơn vị>" counts the products whose base unit is that unit; a product
    asked in a unit that is not its base unit has no rule here, so None. With `strict_unit` False (a percent change,
    where the unit cancels out) the base units are compared as they are."""
    ln = _lines(db, period, filters, linked, items_only=True)
    if ln is None:
        return None
    if m is not None and m.unit and strict_unit:
        unit = linking.norm(m.unit)
        if ln["base_unit"].isna().any():
            return None
        if any(f.field == "product" for f in filters):
            if (ln["base_unit"] != unit).any():
                return None
        else:
            ln = ln[ln["base_unit"] == unit]
    if ln["base_qty"].isna().any():
        return None
    q = float(ln["base_qty"].sum())
    return int(q) if q.is_integer() else q


def customer_count(db, period, filters, linked, m=None, strict_unit=True):
    """§1 "khách đã mua": customers with at least one valid order in the period; walk-ins are not customers (§3)."""
    if _line_filtered(filters):
        ln = _lines(db, period, filters, linked)
        return None if ln is None or "customer_key" not in ln.columns else int(ln["customer_key"].dropna().nunique())
    o = _orders(db, period, filters, linked)
    return None if o is None or "customer_key" not in o.columns else int(o["customer_key"].dropna().nunique())


def _line_profit(ln: pd.DataFrame) -> pd.Series | None:
    """§5 "lãi gộp" of each line: its amount − quantity × the cost written on the sale line (per unit sold), never a
    cost worked out from receipts or lots. Lines that are not items (a service fee) cost nothing; an item line with no
    cost has no profit to tell: None."""
    if "unit_cost" not in ln.columns or ln["line_amount"].isna().any():
        return None
    item = ln["is_item"].ne(False) if "is_item" in ln.columns else pd.Series(True, index=ln.index)
    if ln.loc[item, "unit_cost"].isna().any() or ln.loc[item, "qty"].isna().any():
        return None
    return ln["line_amount"] - (ln["qty"] * ln["unit_cost"]).where(item, 0.0)


def gross_profit(db, period, filters, linked, m=None, strict_unit=True):
    """§5: revenue (§1, fee lines included) − cost of the goods sold, over the period's valid orders."""
    ln = _lines(db, period, filters, linked)
    profit = None if ln is None else _line_profit(ln)
    return None if profit is None else money(float(profit.sum()))


def net_profit(db, period, filters, linked, m=None, strict_unit=True):
    """§5 "lãi ròng một tháng": gross profit of the period − every expense dated in it (repairs, equipment too)."""
    expenses = db.table("expenses")
    if filters or expenses is None or expenses["amount"].isna().any() or expenses["expense_date"].isna().any():
        return None
    day = pd.to_datetime(expenses["expense_date"]).dt.date
    gp = gross_profit(db, period, filters, linked)
    spent = expenses.loc[(day >= period.start) & (day <= period.end), "amount"].sum()
    return None if gp is None else money(gp - float(spent))


MEASURES: dict[str, Callable] = {
    "revenue": revenue, "order_count": order_count, "cancel_count": cancel_count, "cancel_rate": cancel_rate,
    "avg_order_value": avg_order_value, "quantity": quantity, "customer_count": customer_count,
    "gross_profit": gross_profit, "net_profit": net_profit,
}


def figure(db: CanonicalDB, m: Measure, period: ResolvedPeriod | None, plan: ResolvedPlan,
           filters: list[Filter] | None = None, strict_unit: bool = True):
    """One measure over one period (the measure's own filters unless `filters` is given); None when not exact."""
    fn = MEASURES.get(m.metric)
    if fn is None or period is None or m.aggregate != "total" or m.unit_split:
        return None
    return fn(db, period, m.filters if filters is None else filters, plan.linked, m, strict_unit)


def _result(plan: ResolvedPlan, value, rules: tuple[str, ...], requires: tuple[str, ...], fn: str,
            answer_type: str | None = None) -> ExecResult | None:
    answer_type = answer_type or expected_answer_type(plan.plan)
    if value is None or answer_type is None:
        return None
    filters = [f for m in plan.plan.measures for f in m.filters]
    return ExecResult(value=value, answer_type=answer_type, source="D1", function=f"sales.{fn}",
                      rule_ids=sorted(set(rules)), requires=sorted(set(requires) | set(F.filter_columns(filters))))


# ---------------------------------------------------------------- value, compare, share, trend, series
def value_of(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """One figure, or several in the order the question asks ("lần lượt", "mỗi bên"): a list."""
    ms = plan.plan.measures
    values = [figure(db, m, plan.period, plan) for m in ms]
    if not ms or any(v is None for v in values):
        return None
    rules = sum((R_METRIC[m.metric] for m in ms), R_FILTERS)
    requires = sum((REQ_METRIC[m.metric] for m in ms), ())
    return _result(plan, values[0] if len(values) == 1 else values, rules, requires, "value_of")


def compare(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """The asked figure against the compared one (§1): the previous / same / given period, or the same period under
    the compared filters (ca chiều vs ca sáng: the base is ca sáng). pct_change = (a − b) / b × 100; diff = a − b."""
    p, c = plan.plan, plan.plan.compare
    if len(p.measures) != 1 or c.output == "which_more":
        return None
    m = p.measures[0]
    strict = c.output != "pct_change"
    a = figure(db, m, plan.period, plan, strict_unit=strict)
    if c.kind == "filter":
        replaced = {f.field for f in c.filters}
        b = figure(db, m, plan.period, plan, [f for f in m.filters if f.field not in replaced] + list(c.filters), strict)
    else:
        b = figure(db, m, plan.compare_period, plan, strict_unit=strict)
    if a is None or b is None:
        return None
    if c.output == "pct_change":
        value = None if b == 0 else (a - b) / b * 100
    else:
        value = a - b
    rules = R_METRIC[m.metric] + R_FILTERS + R_COMPARE
    return _result(plan, value, rules, REQ_METRIC[m.metric], "compare")


def share(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """Part over whole, in percent: the whole is `share_of`, else the same metric for the whole shop (§1: walk-in
    orders and fee lines included)."""
    p = plan.plan
    if len(p.measures) != 1:
        return None
    m = p.measures[0]
    whole = p.share_of or Measure(metric=m.metric)
    part, total = figure(db, m, plan.period, plan), figure(db, whole, plan.period, plan)
    if part is None or not total:
        return None
    rules = R_METRIC[m.metric] + R_METRIC[whole.metric] + R_FILTERS
    return _result(plan, part / total * 100, rules, REQ_METRIC[m.metric], "share")


def _series_values(plan: ResolvedPlan, db: CanonicalDB) -> list | None:
    p = plan.plan
    if len(p.measures) != 1 or not plan.series:
        return None
    values = [figure(db, p.measures[0], s, plan) for s in plan.series]
    return None if any(v is None for v in values) else values


def trend(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """True when each month is above the one before. Every train trend question asks about a rise ("tăng liên tục",
    "tháng sau luôn cao hơn tháng trước"); the contract has no way to ask about a fall (docs/HAN_CHE N11)."""
    values = _series_values(plan, db)
    if values is None or len(values) < 2:
        return None
    rising = all(b > a for a, b in zip(values, values[1:]))
    m = plan.plan.measures[0]
    return _result(plan, rising, R_METRIC[m.metric] + R_FILTERS, REQ_METRIC[m.metric], "trend")


def series(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    values = _series_values(plan, db)
    m = plan.plan.measures[0] if plan.plan.measures else None
    if values is None or m is None:
        return None
    return _result(plan, values, R_METRIC[m.metric] + R_FILTERS, REQ_METRIC[m.metric], "series")


# ---------------------------------------------------------------- rank
def _first_name(keys: pd.Series, names: pd.Series) -> dict[str, str]:
    """A name for each key: the most frequent one in the data (§9 accepts every spelling the file has, or the code)."""
    frame = pd.DataFrame({"k": keys.astype(str), "n": names}).dropna()
    if frame.empty:
        return {}
    return frame.groupby("k")["n"].agg(lambda s: s.value_counts().index[0]).to_dict()


def _ordered(totals: pd.Series, k: int | None) -> list:
    """Keys by value descending, ties by key ascending (§9 "Bằng nhau"), the first k."""
    frame = totals.rename("v").reset_index()
    frame.columns = ["key", "v"]
    frame = frame.sort_values(["v", "key"], ascending=[False, True], kind="mergesort")
    return frame["key"].head(k if k is not None else len(frame)).tolist()


def rank(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """Products, customers, employees, days or months ranked by a sales metric; ties by code ascending (§9)."""
    p, r = plan.plan, plan.plan.rank
    if r.order != "desc" or r.with_values or r.min_orders or plan.period is None:
        return None
    filters = p.measures[0].filters if p.measures else []
    if r.entity == "product":
        ln = _lines(db, plan.period, filters, plan.linked, items_only=True)
        if ln is None or ln.empty:
            return None
        if r.by == "gross_profit":  # §3 "hàng lời nhất": by total gross profit (§5)
            profit = _line_profit(ln)
            ln, col = (None if profit is None else ln.assign(_profit=profit)), "_profit"
        else:
            col = {"quantity": "base_qty", "revenue": "line_amount"}.get(r.by)
        if ln is None or col is None or ln[col].isna().any():
            return None
        keys = _ordered(ln.groupby("product_key")[col].sum(), r.k)
        names = _first_name(F.lines(db)["product_key"], F.lines(db)["product_name"])
        labels = [names.get(k, k) for k in keys]
    else:
        if _line_filtered(filters):
            return None
        o = _orders(db, plan.period, filters, plan.linked)
        if o is None or o.empty or not o["revenue_ok"].all():
            return None
        if r.entity in ("day", "month"):
            key = o["day"].map(lambda d: d.isoformat() if r.entity == "day" else d.strftime("%Y-%m"))
        elif r.entity == "customer" and "customer_key" in o.columns:
            key = o["customer_key"]  # §3: walk-in orders have no key and are not ranked
        elif r.entity == "employee" and "employee" in o.columns:
            key = o["employee"]
        else:
            return None
        o = o.assign(_key=key.astype("string")).dropna(subset=["_key"])
        if o.empty:
            return None
        if r.by == "revenue":
            totals = o.groupby("_key")["revenue"].sum()
        elif r.by == "order_count":
            totals = o.groupby("_key")["order_id"].nunique()
        else:
            return None
        keys = _ordered(totals, r.k)
        if r.entity == "customer":
            every = F.orders(db)
            names = _first_name(every["customer_key"], every.get("customer_name", every["customer_key"]))
            customers = db.table("customers")
            if customers is not None and "customer_name" in customers.columns:
                names = {**names, **_first_name(customers["customer_key"], customers["customer_name"])}
            labels = [names.get(k, k) for k in keys]
        else:
            labels = keys
    value = labels[0] if r.k == 1 else labels
    rules = R_RANK + R_METRIC.get(r.by, ()) + R_FILTERS
    return _result(plan, value, rules, REQ_METRIC.get(r.by, REQ_ORDERS), "rank")


# ---------------------------------------------------------------- count over a threshold, unsold products
OPS = {"gte": operator.ge, "gt": operator.gt, "lte": operator.le, "lt": operator.lt, "eq": operator.eq}


def count_where(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """How many orders / days / customers / products pass a bound (§2: "từ N trở lên" includes N, "quá N" does
    not); as a share of the customers who bought (§1) when asked in percent."""
    p, t = plan.plan, plan.plan.threshold
    filters = p.measures[0].filters if p.measures else []
    if plan.period is None or _line_filtered(filters):
        return None
    o = _orders(db, plan.period, filters, plan.linked)
    if o is None:
        return None
    cmp = OPS[t.op]
    if t.entity == "order" and t.metric == "revenue":
        if not o["revenue_ok"].all():
            return None
        per = o.groupby("order_id")["revenue"].sum()
    elif t.entity == "day" and t.metric == "revenue":
        if t.op not in ("gte", "gt") or t.value <= 0 or not o["revenue_ok"].all():
            return None  # a day without orders has revenue 0: only bounds above 0 can skip such days
        per = o.groupby("day")["revenue"].sum()
    elif t.entity == "customer" and t.metric == "order_count":
        if "customer_key" not in o.columns:
            return None  # a shop that does not record its customers
        per = o.dropna(subset=["customer_key"]).groupby("customer_key")["order_id"].nunique()
    elif t.entity == "product" and t.metric in ("order_presence", "order_count"):
        ln = _lines(db, plan.period, filters, plan.linked, items_only=True)
        if ln is None:
            return None
        per = ln.groupby("product_key")["order_id"].nunique()
    else:
        return None
    hits = int(cmp(per, t.value).sum())
    if t.as_share:
        if t.entity != "customer" or per.empty:
            return None
        value = hits / len(per) * 100
    else:
        value = hits
    rules = R_COUNT + R_VALID + R_METRIC.get(t.metric, ()) + R_FILTERS
    return _result(plan, value, rules, REQ_METRIC.get(t.metric, REQ_ORDERS), "count_where")


def unsold(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """§5 "hàng ế": products sold before the period (valid orders) and in no valid order of the period."""
    p, ls = plan.plan, plan.plan.list_spec
    if plan.period is None or ls.entity != "product" or any(m.filters for m in p.measures):
        return None
    ln = F.lines(db)
    if ln is None or F.unknown_status(ln[ln["day"] <= plan.period.end]):
        return None
    items = ln[F.valid(ln) & (ln["is_item"].ne(False) if "is_item" in ln.columns else True)]
    before = set(items.loc[items["day"] < plan.period.start, "product_key"])
    during = set(items.loc[F.in_period(items, plan.period), "product_key"])
    keys = sorted(before - during)
    if ls.count:
        value = len(keys)
    else:
        names = _first_name(ln["product_key"], ln["product_name"])
        value = [names.get(k, k) for k in keys]
        if not value:
            return None
    return _result(plan, value, R_UNSOLD + R_TIES, REQ_METRIC["order_count"] + ("lines.product_key",), "unsold")


# ---------------------------------------------------------------- registry
def _register(intent: str, names, fn, entity: str = "", rules: tuple[str, ...] = ()) -> None:
    for name in names:
        metric(intent, name, requires=REQ_METRIC.get(name, REQ_ORDERS),
               rules=tuple(sorted(set(R_METRIC.get(name, ()) + R_FILTERS + rules))), entity=entity,
               filters=tuple(sorted(F.FILTERS)))(fn)


_register("value", MEASURES, value_of)
_register("compare", MEASURES, compare, rules=R_COMPARE)
_register("share", ("revenue", "order_count", "quantity", "customer_count"), share)
_register("trend", ("revenue", "order_count", "avg_order_value", "quantity", "cancel_count"), trend)
_register("series", ("revenue", "order_count", "avg_order_value", "quantity", "cancel_count"), series)
_register("rank", ("quantity", "revenue", "gross_profit"), rank, entity="product", rules=R_RANK)
for _entity in ("customer", "employee", "day", "month"):
    _register("rank", ("revenue", "order_count"), rank, entity=_entity, rules=R_RANK)
_register("count_where", ("revenue",), count_where, entity="order", rules=R_COUNT)
_register("count_where", ("revenue",), count_where, entity="day", rules=R_COUNT)
_register("count_where", ("order_count",), count_where, entity="customer", rules=R_COUNT)
_register("count_where", ("order_presence", "order_count"), count_where, entity="product", rules=R_COUNT)
_register("list_items", ("unsold_in_period",), unsold, entity="product", rules=R_UNSOLD + R_TIES)
