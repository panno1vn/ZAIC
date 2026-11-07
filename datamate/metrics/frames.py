"""What the sales metrics share, built once per business: orders with their revenue, lines with their product's
attributes, and the masks that apply a plan's filters (rulebook §1–§3, §6).

A filter the frames cannot apply exactly (a field the shop does not record, a name [C3] did not link, a product
attribute left blank for some lines) makes the mask None, and the metric returns None: the question abstains rather
than being answered without its filter.
"""
from __future__ import annotations

import re
import weakref

import pandas as pd

from datamate.contracts import CanonicalDB, Filter, ResolvedPeriod
from datamate.nlu import jobs, linking

VALID_STATUSES = ("completed", "delivering")  # §1: not cancelled, not returned; orders in delivery count
ORDER_FILTERS = frozenset({"channel", "payment_method", "customer_group", "customer", "employee", "shift", "weekday",
                           "vehicle_model", "is_warranty", "service"})  # N44: a repair shop's tickets (§6 Sửa xe)
LINE_FILTERS = frozenset({"product", "product_group", "active_ingredient", "prescription", "size", "category", "brand",
                          "product_line", "stage"})  # §6 điện thoại: dòng máy; mẹ và bé: số sữa
FILTERS = ORDER_FILTERS | LINE_FILTERS
ORDER_COLUMN = {"channel": "channel", "payment_method": "payment_method", "customer_group": "customer_group",
                "customer": "customer_key", "employee": "employee", "vehicle_model": "vehicle_model"}
LINE_COLUMN = {"product": "product_key", "product_group": "product_group", "active_ingredient": "active_ingredient",
               "category": "category", "brand": "brand", "product_line": "product_line"}
SHIFT_HOURS = {"morning": range(6, 14), "afternoon": range(14, 22)}  # §2: 06:00–13:59, 14:00–21:59
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_SIZE = {"M": re.compile(r"\(\s*m\s*\)\s*$", re.I), "L": re.compile(r"\(\s*l\s*\)\s*$", re.I)}  # §6: name ends (M)

_CACHE: dict[int, tuple[weakref.ref, dict]] = {}


def _cache(db: CanonicalDB) -> dict:
    ref, store = _CACHE.get(id(db), (None, None))
    if ref is None or ref() is not db:
        store = {}
        _CACHE[id(db)] = (weakref.ref(db), store)
    return store


def orders(db: CanonicalDB) -> pd.DataFrame | None:
    """Every order with its day, revenue (§1: sum of its lines' amounts, fee lines included) and whether that revenue
    is complete (no line with an unread amount). A shop that records orders only (no lines) gives each order's revenue
    in orders.goods_amount, the README's "tiền hàng của đơn: cộng thành tiền các mặt hàng" (N26)."""
    store = _cache(db)
    if "orders" not in store:
        o, lines = db.table("orders"), db.table("lines")
        if o is None:
            store["orders"] = None
        elif lines is not None and "line_amount" in lines.columns:
            o = o.copy()
            o["day"] = o["order_time"].dt.date
            o["revenue"] = o["order_id"].map(lines.groupby("order_id")["line_amount"].sum()).fillna(0.0)
            unread = set(lines.loc[lines["line_amount"].isna(), "order_id"])
            o["revenue_ok"] = ~o["order_id"].isin(unread)
            store["orders"] = o
        elif orders_only(db):
            o = o.copy()
            o["day"] = o["order_time"].dt.date
            o["revenue"] = o["goods_amount"].fillna(0.0)
            o["revenue_ok"] = o["goods_amount"].notna()
            store["orders"] = o
        else:
            store["orders"] = None
    return store["orders"]


def orders_only(db: CanonicalDB) -> bool:
    """The shop records orders without their lines, each with its goods amount (§1 revenue of the order)."""
    return db.table("lines") is None and db.has("orders", "goods_amount")


def requires(db: CanonicalDB, columns) -> list[str]:
    """The canonical columns a figure reads in this shop: an orders-only shop reads the order's goods amount where
    others read the lines' amounts."""
    if not orders_only(db):
        return list(columns)
    return sorted({"orders.goods_amount" if c == "lines.line_amount" else c for c in columns})


def base_units(db: CanonicalDB) -> dict[str, str]:
    """Base unit of each product (folded): the conversion table's or catalogue's, else the one unit its lines use
    that has no conversion row (§10: a unit without a conversion row is the base unit)."""
    store = _cache(db)
    if "base_units" not in store:
        out: dict[str, str] = {}
        conv, products, lines = db.table("unit_conversions"), db.table("products"), db.table("lines")
        converted: dict[str, set[str]] = {}
        if conv is not None:
            for row in conv.itertuples(index=False):
                converted.setdefault(str(row.product_key), set()).add(linking.norm(row.unit))
                if "base_unit" in conv.columns and isinstance(row.base_unit, str) and row.base_unit.strip():
                    out.setdefault(str(row.product_key), linking.norm(row.base_unit))
        if products is not None and "base_unit" in products.columns:
            for k, u in zip(products["product_key"].astype(str), products["base_unit"]):
                if isinstance(u, str) and u.strip():
                    out.setdefault(k, linking.norm(u))
        if lines is not None and "unit" in lines.columns:
            used = lines.dropna(subset=["unit"]).groupby(lines["product_key"].astype(str))["unit"].unique()
            for k, us in used.items():
                plain = {linking.norm(u) for u in us} - converted.get(k, set())
                if k not in out and len(plain) == 1:
                    out[k] = plain.pop()
        store["base_units"] = out
    return store["base_units"]


def lines(db: CanonicalDB) -> pd.DataFrame | None:
    """Every line with its order's day, status, time and customer, and its product's group, ingredient, prescription
    flag, category, brand and base unit (from the catalogue when the line does not carry them)."""
    store = _cache(db)
    if "lines" not in store:
        o, ln = orders(db), db.table("lines")
        if o is None or ln is None:
            store["lines"] = None
        else:
            keep = [c for c in ("order_id", "day", "status", "order_time", "has_time", "customer_key") if c in o.columns]
            df = ln.merge(o[keep], on="order_id", how="inner")
            df["product_key"] = df["product_key"].astype(str)
            products = db.table("products")
            if products is not None:
                attrs = products.drop_duplicates("product_key").assign(product_key=lambda p: p["product_key"].astype(str))
                for col in ("product_group", "active_ingredient", "is_prescription", "category", "brand", "product_line",
                            "stage", "size"):
                    if col in attrs.columns and attrs[col].notna().any():
                        from_catalogue = df["product_key"].map(attrs.set_index("product_key")[col])
                        df[col] = df[col].fillna(from_catalogue) if col in df.columns else from_catalogue
                        if col == "brand":  # a catalogue product with its brand cell blank has no brand, not an
                            # unknown one (public mẹ-và-bé catalogue, 06/11: towels, toys with no "Hãng")
                            listed = df["product_key"].isin(set(attrs["product_key"]))
                            df.loc[listed & df[col].isna(), col] = ""
            df["base_unit"] = df["product_key"].map(base_units(db))
            store["lines"] = df
    return store["lines"]


def in_period(frame: pd.DataFrame, period: ResolvedPeriod) -> pd.Series:
    return (frame["day"] >= period.start) & (frame["day"] <= period.end)


def valid(frame: pd.DataFrame) -> pd.Series:
    return frame["status"].isin(VALID_STATUSES)


def unknown_status(frame: pd.DataFrame) -> bool:
    """Some order of the frame has no status. The checks let a shop through with a few such orders (a ledger row left
    blank, in a public shop 1 order of 820), and a figure they could change is not given: whether they count is unknown."""
    return "status" in frame.columns and bool(frame["status"].isna().any())


def _values(f: Filter) -> list:
    return f.value if isinstance(f.value, list) else [f.value]


def _linked(f: Filter, linked: dict[str, str]) -> list[str] | None:
    out = [linked.get(str(v)) for v in _values(f)]
    return None if any(v is None for v in out) else out


def _apply(mask: pd.Series, sel: pd.Series, f: Filter) -> pd.Series | None:
    if f.op in ("eq", "in"):
        return mask & sel
    if f.op in ("ne", "not_in"):
        return mask & ~sel
    return None  # gte / contains on a name: not a filter these frames know


def order_mask(o: pd.DataFrame, filters: list[Filter], linked: dict[str, str]) -> pd.Series | None:
    """Orders passing the order-level filters (channel, payment, customer group, customer, employee, shift, weekday)."""
    mask = pd.Series(True, index=o.index)
    for f in filters:
        if f.field not in ORDER_FILTERS:
            continue
        if f.field == "shift":
            if "has_time" not in o.columns or not o["has_time"].eq(True).all():
                return None  # §2 shifts need the time of each order
            hours = o["order_time"].dt.hour
            sel = pd.Series(False, index=o.index)
            for v in _values(f):
                sel |= hours.isin(SHIFT_HOURS[v])
        elif f.field == "weekday":
            sel = o["order_time"].dt.dayofweek.isin([WEEKDAYS.index(v) for v in _values(f)])
        elif f.field == "is_warranty":
            if "is_warranty" not in o.columns:
                return None
            sel = o["is_warranty"].eq(True) == bool(_values(f)[0])
        elif f.field == "service":
            sel = _job_mask(o, _linked(f, linked))
            if sel is None:
                return None
        else:
            col, values = ORDER_COLUMN[f.field], _linked(f, linked)
            if values is None or col not in o.columns or o[col].isna().all():
                return None
            if f.field == "vehicle_model" and (linking.ledger_lines(o[col]).isna() & o[col].notna()).any():
                return None  # a spelling that may name two lines ("Wave" beside Wave Alpha and Wave RSX)
            sel = pd.Series(False, index=o.index)
            for v in values:
                sel |= linking.matches(f.field, o[col], v)
            if f.field == "customer_group" and "customer_key" in o.columns:
                sel &= o["customer_key"].notna()  # §1: walk-in orders belong to no group, not even "lẻ"
        mask = _apply(mask, sel, f)
        if mask is None:
            return None
    return mask


def _job_mask(o: pd.DataFrame, codes: list[str] | None) -> pd.Series | None:
    """Tickets that did one of the jobs (§6 Sửa xe "lượt xe có làm một việc = phiếu có việc đó, tính một lượt"),
    warranty tickets left out ("phiếu bảo hành không tính là lượt làm việc đó"); None when a ledger cell holds a job
    jobs.py does not read, which might be the one asked."""
    if codes is None or "services" not in o.columns:
        return None
    cells = o["services"].map(lambda c: jobs.cell_jobs(c) if isinstance(c, str) else frozenset())
    if cells.isna().any():
        return None
    sel = cells.map(lambda done: any(c in done for c in codes)).astype(bool)
    if "is_warranty" in o.columns:
        sel &= o["is_warranty"].ne(True)
    return sel


def _stage_core(v) -> str:
    """"Số 2", "số 2", "2" → "2"; "Size XL", "size xl", "XL" → "xl"."""
    t = linking.norm(str(v))
    return re.sub(r"^(?:so|size|sz)\s+", "", t).strip()


def line_mask(ln: pd.DataFrame, filters: list[Filter], linked: dict[str, str]) -> pd.Series | None:
    """Lines passing the product-level filters (product, group, ingredient, prescription, size, category, brand)."""
    mask = pd.Series(True, index=ln.index)
    items = ln["is_item"].ne(False) if "is_item" in ln.columns else pd.Series(True, index=ln.index)
    for f in filters:
        if f.field not in LINE_FILTERS:
            continue
        if f.field in ("size", "stage") and f.field in ln.columns and ln[f.field].notna().any():
            # §6 Mẹ và bé: "số sữa, size bỉm lấy theo cột Số / Size của danh mục: hàng để trống cột Số / Size thì không
            # xếp vào số, size nào, dù tên hàng có số" — a blank is no size, not an unknown one
            if f.op not in ("eq", "in"):
                return None
            want = {_stage_core(v) for v in _values(f)}
            sel = ln[f.field].map(lambda v: isinstance(v, str) and _stage_core(v) in want)
        elif f.field == "stage":
            return None
        elif f.field == "size":
            pats = [_SIZE.get(str(v).upper()) for v in _values(f)]
            if None in pats:
                return None
            names = ln["product_name"].astype(str)
            sel = pd.Series(False, index=ln.index)
            for p in pats:
                sel |= names.str.contains(p)
        elif f.field == "prescription":
            if "is_prescription" not in ln.columns or (ln["is_prescription"].isna() & items).any():
                return None
            sel = ln["is_prescription"].fillna(False).astype(bool).isin([bool(v) for v in _values(f)]) & items
        else:
            col, values = LINE_COLUMN[f.field], _linked(f, linked)
            if values is None or col not in ln.columns:
                return None
            if f.field != "product" and (ln[col].isna() & items).any():
                return None  # an item line without the attribute could belong to the asked group (fee lines cannot)
            sel = ln[col].astype(str).isin(values) & ln[col].notna()
        mask = _apply(mask, sel, f)
        if mask is None:
            return None
    return mask


def filter_columns(filters: list[Filter]) -> list[str]:
    """Canonical columns a set of filters reads, for ExecResult.requires."""
    out = []
    for f in filters:
        if f.field in ORDER_COLUMN:
            out.append(f"orders.{ORDER_COLUMN[f.field]}")
        elif f.field == "shift":
            out.append("orders.has_time")
        elif f.field == "service":
            out.append("orders.services")
        elif f.field == "stage":
            out.append("products.stage")
        elif f.field in ("product", "size"):
            out.append("lines.product_key")
    return out
