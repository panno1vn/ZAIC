"""Purchases, selling prices and stock, exact to rulebook §5 (with §2 "đến hết ngày X" and §10 units). Work package G5,
v2 metrics in the order of their number of train questions (docs/research/templates.md).

Each formula was checked against the train answers of the businesses with a hand mapping before it was written
(probe 04/11): average purchase cost 28/28, purchase amount 20/20, selling price 13/13, stock every probed question.
A figure the data cannot give exactly (two units in one month's receipts, two prices in one day, movements after the
last stock record) is None: the question abstains.
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd

from datamate.contracts import CanonicalDB, ExecResult, Filter, Measure, ResolvedPlan
from datamate.contracts.plan import expected_answer_type
from datamate.formatter import money
from datamate.nlu import linking

from . import frames as F
from .registry import metric
from .sales import R_VALID, TIE, _lines, _ordered, _tied  # one tie rule for every ranking (§9)

R_TODAY = ("§0.p_hom_nay_cua_moi_cau_la",)
R_PURCHASE = ("§5.tien_nhap_hang_trong_ky",) + R_TODAY
R_MAIN_SUPPLIER = ("§5.nha_cung_cap_chinh",) + R_TODAY  # a public rulebook row: [R] blocks it where the row is absent
R_AVG_COST = ("§5.gia_nhap_binh_quan_mot_mat_hang_trong_thang",) + R_TODAY
R_PRICE = ("§5.gia_ban_x_ngay_d", "§2.ngay_x_hom_nay_hom_qua", "§10.don_vi_co_ban_don_vi_lon") + R_TODAY
R_STOCK = ("§2.den_het_ngay_x_tinh_den_hom_nay", "§10.don_vi_co_ban_don_vi_lon") + R_TODAY
R_UNIT_SPLIT = ("§5.ton_theo_don_vi_lon",)  # N166: cited only by a stock written in a larger unit, then the base unit
R_NAMES = ("§8.ten_goi_nhan",)
R_TIES = ("§9.p_bang_nhau_hai_doi_tuong_bang",)
R_IN_MINUS_OUT = ("§5.nhap_tru_ban_chenh_nhap_va_ban", "§5.tien_nhap_hang_trong_ky", "§10.don_vi_co_ban_don_vi_lon") \
    + R_VALID

GENERIC_UNITS = {"don vi"}  # "một <tên hàng>": the LLM writes a unit the question does not state


# ---------------------------------------------------------------- shared
def _one_product(m: Measure, linked: dict[str, str]) -> str | None:
    """The data key of the measure's only filter, a single linked product; None for any other filter set."""
    if len(m.filters) != 1:
        return None
    f = m.filters[0]
    if f.field != "product" or f.op != "eq" or isinstance(f.value, list):
        return None
    return linked.get(str(f.value))


def _same_unit(asked: str | None, recorded: str) -> bool:
    """The asked unit names the recorded one: same folded words, or the same first word ("xe" for "xe 4m3")."""
    if not asked:
        return True
    a, r = linking.norm(asked), linking.norm(recorded)
    return a == r or a.split()[:1] == r.split()[:1]


def _is_base(db: CanonicalDB, product: str, unit: str) -> bool:
    """`unit` is the product's base unit: the known one, else the unit of its lines whose base quantity is their
    quantity (a shop that records base quantities without naming the base unit)."""
    base = F.base_units(db).get(product)
    if base is not None:
        return _same_unit(unit, base)
    ln = F.lines(db)
    if ln is None or "unit" not in ln.columns or "base_qty" not in ln.columns:
        return False
    rows = ln[(ln["product_key"] == product) & ln["unit"].notna()]
    rows = rows[[_same_unit(unit, str(u)) for u in rows["unit"]]]
    return not rows.empty and bool((rows["qty"] == rows["base_qty"]).all())


def _factor(db: CanonicalDB, product: str, unit: str) -> float | None:
    """Base units in one `unit` of the product (§10: a unit with no conversion row is the base unit, factor 1)."""
    if _is_base(db, product, unit):
        return 1.0
    conv = db.table("unit_conversions")
    if conv is None:
        return None
    rows = conv[conv["product_key"].astype(str) == product]
    hits = {float(f) for u, f in zip(rows["unit"], rows["factor"]) if pd.notna(f) and _same_unit(unit, str(u))}
    return hits.pop() if len(hits) == 1 else None


def _receipts(db: CanonicalDB, start, end) -> pd.DataFrame | None:
    """Receipt lines dated in [start, end], cancelled receipts left out (§5)."""
    p = db.table("purchases")
    if p is None:
        return None
    day = p["receipt_time"].dt.date
    keep = (day >= start) & (day <= end)
    if "cancelled" in p.columns:
        keep &= p["cancelled"].ne(True)
    return p[keep]


def _cost(rows: pd.DataFrame) -> pd.Series | None:
    """Money of each receipt line: quantity × purchase price (probe 04/11: equals the recorded amount wherever a shop
    records both); the recorded amount where the price is missing. None when neither is readable."""
    cost = rows["qty"] * rows["unit_cost"] if {"qty", "unit_cost"} <= set(rows.columns) else None
    if "amount" in rows.columns:
        cost = rows["amount"] if cost is None else cost.fillna(rows["amount"])
    return None if cost is None or cost.isna().any() else cost


# ---------------------------------------------------------------- one figure
def purchase_amount(db: CanonicalDB, plan: ResolvedPlan, m: Measure):
    """§5: money of the receipts dated in the period, cancelled ones left out; a product or supplier filter keeps its
    lines only. An empty period is None, not 0: the shop may not record purchases then (§7)."""
    if plan.period is None:
        return None
    rows = _receipts(db, plan.period.start, plan.period.end)
    if rows is None:
        return None
    for f in m.filters:
        column = {"product": "product_key", "supplier": "supplier"}.get(f.field)
        keys = [plan.linked.get(str(v)) for v in (f.value if isinstance(f.value, list) else [f.value])]
        if column is None or f.op not in ("eq", "in") or None in keys or column not in rows.columns:
            return None
        rows = rows[rows[column].astype(str).isin(keys)]
    cost = _cost(rows)
    return None if cost is None or rows.empty else money(float(cost.sum()))


def purchase_avg_cost(db: CanonicalDB, plan: ResolvedPlan, m: Measure):
    """§5: a product's purchase price averaged by quantity over the period's receipts (not the mean of the prices),
    per purchase unit. Receipts in two units, or a question asking another unit, have no rule here: None."""
    product = _one_product(m, plan.linked)
    if product is None or plan.period is None:
        return None
    rows = _receipts(db, plan.period.start, plan.period.end)
    if rows is None:
        return None
    rows = rows[rows["product_key"].astype(str) == product]
    units = set(rows["unit"].dropna().map(linking.norm)) if "unit" in rows.columns else set()
    if rows.empty or rows["qty"].isna().any() or len(units) > 1:
        return None
    if units and linking.norm(m.unit or "") not in GENERIC_UNITS and not _same_unit(m.unit, units.pop()):
        return None
    cost, qty = _cost(rows), float(rows["qty"].sum())
    return None if cost is None or qty <= 0 else money(float(cost.sum()) / qty)


def unit_price(db: CanonicalDB, plan: ResolvedPlan, m: Measure):
    """§5 "giá bán X ngày D": the price on X's lines of the orders placed on day D, every status included, per base
    unit (line price × quantity / base quantity), before the line discount. Two prices that day: None."""
    product = _one_product(m, plan.linked)
    p = plan.period
    if product is None or p is None or p.start != p.end:
        return None
    ln = F.lines(db)
    if ln is None or not {"unit_price", "qty", "base_qty"} <= set(ln.columns):
        return None
    rows = ln[(ln["product_key"] == product) & (ln["day"] == p.start)]
    rows = rows[rows["base_qty"].ne(0)]
    if rows.empty or rows[["unit_price", "qty", "base_qty"]].isna().any().any():
        return None
    if m.unit and linking.norm(m.unit) not in GENERIC_UNITS and not _is_base(db, product, m.unit):
        return None
    prices = {round(float(v), 6) for v in rows["unit_price"] * rows["qty"] / rows["base_qty"]}
    return money(prices.pop()) if len(prices) == 1 else None


def purchase_minus_sales(db: CanonicalDB, plan: ResolvedPlan, m: Measure):
    """§5 "nhập trừ bán, chênh nhập và bán" of one product over the period, in the unit asked: the receipts dated in it
    (cancelled ones left out), each line turned into base units by its own unit, minus the base quantity of the
    period's orders counted in revenue (§1: not cancelled, not returned). Train, the three questions of shops with a
    hand mapping (probe 08/11): 10, −28, 41, all exact; counting the returned orders as sold gave −38 and 39. None
    when the question names no unit, a unit has no factor, or the figure is not a whole number of that unit."""
    product = _one_product(m, plan.linked)
    if product is None or any(f.field != "product" for f in m.filters) or plan.period is None or not m.unit:
        return None
    period = plan.period
    every = db.table("purchases")
    if every is None or not (every["product_key"].astype(str) == product).any():
        return None  # a product never received: the receipts may be keyed otherwise (N94), never "0 bought"
    rows = _receipts(db, period.start, period.end)
    if rows is None or "qty" not in rows.columns or "unit" not in rows.columns:
        return None
    rows = rows[rows["product_key"].astype(str) == product]
    factors = [_factor(db, product, str(u)) for u in rows["unit"]]
    if any(f is None for f in factors) or rows["qty"].isna().any():
        return None
    bought = float((rows["qty"].astype(float) * pd.Series(factors, index=rows.index, dtype=float)).sum())
    ln = _lines(db, period, list(m.filters), plan.linked, items_only=True)
    unit = _factor(db, product, m.unit)
    if ln is None or "base_qty" not in ln.columns or ln["base_qty"].isna().any() or not unit:
        return None
    value = (bought - float(ln["base_qty"].sum())) / unit
    return int(value) if float(value).is_integer() else None


def stock_base_qty(db: CanonicalDB, product: str, day) -> float | None:
    """§2 "đến hết ngày X": the product's stock (base units) in the last stock record dated on or before the day,
    provided nothing moved after it up to that day (no receipt, no order line). A shop's stock file is either one
    snapshot at the end of its data or a stock card with a record after every movement; both read the same way."""
    inv = db.table("inventory")
    if inv is None:
        # N116: a shop that keeps its stock by lot (§6 Nhà thuốc) and no stock file: the base units left in the
        # product's lots at the end of the day (lots_left, checked against the stock cards: 80 / 80, N74)
        from .lots import lots_left  # late import: lots imports this module
        lots = lots_left(db, day)
        if lots is None:
            return None
        mine = lots[lots["product_key"].astype(str) == product]
        return float(mine["left"].sum()) if not mine.empty else None
    as_of = pd.to_datetime(inv["as_of"]).dt.date
    rows = inv.assign(day=as_of)[(inv["product_key"].astype(str) == product) & (as_of <= day)]
    rows = rows.sort_values("day", kind="stable")  # records of one day keep their file order: the last is its end
    if rows.empty or pd.isna(rows["base_qty"].iloc[-1]):
        return None
    last = rows["day"].iloc[-1]
    receipts = _receipts(db, last + timedelta(days=1), day)
    if receipts is not None and (receipts["product_key"].astype(str) == product).any():
        return None
    ln = F.lines(db)
    if ln is not None and ((ln["product_key"] == product) & (ln["day"] > last) & (ln["day"] <= day)).any():
        return None
    return float(rows["base_qty"].iloc[-1])


def _whole(q: float):
    return int(q) if float(q).is_integer() else q


def stock_qty(db: CanonicalDB, plan: ResolvedPlan, ms: list[Measure]):
    """Stock of one product at the end of the period's last day. In its base unit a number; in a larger unit the list
    [whole larger units, base units left] (§5 "tồn theo đơn vị lớn"), also when the question asks the two parts as
    two measures ("bao nhiêu hộp chẵn, bao nhiêu viên lẻ")."""
    product = _one_product(ms[0], plan.linked)
    if product is None or any(_one_product(m, plan.linked) != product for m in ms) or len(ms) > 2:
        return None
    day = plan.period.end if plan.period is not None else plan.as_of
    q = stock_base_qty(db, product, day)
    unit = ms[0].unit
    if q is None or q < 0:
        return None
    factor = _factor(db, product, unit) if unit and linking.norm(unit) not in GENERIC_UNITS else 1.0
    if factor is None:
        return None
    if len(ms) == 2 and (factor == 1 or _factor(db, product, ms[1].unit or "") != 1):
        return None  # the two parts must be a larger unit, then the base unit
    if factor == 1:
        return None if ms[0].unit_split else _whole(q)
    return [int(q // factor), _whole(q - (q // factor) * factor)]


def rank_suppliers(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """Suppliers ranked over the period's receipts (cancelled ones left out), ties by code / name ascending (§9):
    - by purchase_amount, §5 "nhà cung cấp nhập nhiều nhất": the money of their receipts;
    - by receipt_count, §5 "nhà cung cấp chính" (public rulebook only): their number of receipts.
    The supplier as the file writes it: a name, or a code §9 accepts."""
    r = plan.plan.rank
    filtered = any(m.filters for m in plan.plan.measures)
    if r.order != "desc" or r.with_values or r.min_orders or plan.period is None or filtered:
        return None
    rows = _receipts(db, plan.period.start, plan.period.end)
    if rows is None or rows.empty or "supplier" not in rows.columns or rows["supplier"].isna().any():
        return None
    supplier = rows["supplier"].astype(str)
    if r.by == "receipt_count":
        totals, rules = rows.groupby(supplier)["receipt_id"].nunique(), R_MAIN_SUPPLIER
    else:
        cost = _cost(rows)
        if cost is None:
            return None
        totals, rules = cost.groupby(supplier).sum(), R_PURCHASE
    keys = _ordered(totals, r.k)
    return ExecResult(value=keys[0] if r.k == 1 else keys, answer_type=expected_answer_type(plan.plan), source="D1",
                      function="stock.rank_suppliers", rule_ids=sorted(set(rules + R_NAMES + R_TIES)),
                      requires=["purchases.receipt_time", "purchases.supplier", "purchases.receipt_id"],
                      notes=[TIE] if _tied(totals, r.k) else [])


# ---------------------------------------------------------------- registry
FLOWS = {"purchase_amount": (purchase_amount, R_PURCHASE, ("purchases.receipt_time", "purchases.qty")),
         "purchase_avg_cost": (purchase_avg_cost, R_AVG_COST, ("purchases.receipt_time", "purchases.qty",
                                                                "purchases.unit_cost")),
         "unit_price": (unit_price, R_PRICE, ("orders.order_time", "lines.unit_price", "lines.base_qty")),
         "purchase_minus_sales": (purchase_minus_sales, R_IN_MINUS_OUT,
                                  ("purchases.receipt_time", "purchases.qty", "purchases.unit", "lines.base_qty"))}


def value_of(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    ms = plan.plan.measures
    name = ms[0].metric if ms else None
    if name == "stock_qty":
        value = stock_qty(db, plan, list(ms))
        rules = R_STOCK + (R_UNIT_SPLIT if ms[0].unit_split else ())
        requires = ("inventory.base_qty", "inventory.as_of") if db.has("inventory") else \
            ("lots.lot_id", "lots.base_qty_in", "lot_sales.lot_id", "lot_sales.base_qty")  # N116: by lot
        answer_type = "list" if isinstance(value, list) else expected_answer_type(plan.plan)
    elif name in FLOWS and len(ms) == 1:
        fn, rules, requires = FLOWS[name]
        value, answer_type = fn(db, plan, ms[0]), expected_answer_type(plan.plan)
    else:
        return None
    if value is None or answer_type is None:
        return None
    return ExecResult(value=value, answer_type=answer_type, source="D1", function=f"stock.{name}",
                      rule_ids=sorted(set(rules + R_NAMES)), requires=list(requires))


for _name, (_fn, _rules, _requires) in FLOWS.items():
    metric("value", _name, requires=_requires, rules=tuple(sorted(set(_rules + R_NAMES))),
           filters=("product", "supplier") if _name == "purchase_amount" else ("product",))(value_of)
metric("value", "stock_qty", requires=("inventory.base_qty", "inventory.as_of"),
       rules=tuple(sorted(set(R_STOCK + R_UNIT_SPLIT + R_NAMES))), filters=("product",))(value_of)
for _by, _rules in (("purchase_amount", R_PURCHASE), ("receipt_count", R_MAIN_SUPPLIER)):
    metric("rank", _by, entity="supplier", requires=("purchases.receipt_time", "purchases.supplier"),
           rules=tuple(sorted(set(_rules + R_NAMES + R_TIES))))(rank_suppliers)
