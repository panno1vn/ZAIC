"""N111. Side tables the README's conventions name, for a mapping that lacks them.

A shop whose README lists its files without describing each column (train: a POS database of 17 tables, an export of
13 files) is mapped from an example; the example's shop may keep no stock, receipts or expenses, and the side tables the
shop does keep are left out (train 10/11: two pharmacies, 46 + 14 questions blank). The README's conventions still name
one column of each such table, in fixed words every README uses:

- "**Tồn kho**: **<X>** là tồn cuối ngày cuối có dữ liệu, theo đơn vị cơ bản" (a stock list), or "mỗi dòng `<t>.<X>` là
  tồn sau lần nhập/bán/trả đó" (a stock card: each row the stock after one movement);
- "**Sổ chi phí**: các khoản chi vận hành theo tháng (tiền **<X>**)";
- "**Nhập hàng**: **<X>** là giá nhập một đơn vị, theo đơn vị nhập của dòng; **<A>** là tiền nhập của cả dòng" (or
  "`<h>.<Z>` là tổng tiền của cả phiếu nhập", the receipt's total in its own table);
- "**Thuốc**: **<X>** đúng (TRUE/1) là thuốc kê đơn. Hoạt chất ghi không kèm hàm lượng…".

The table holding the named column is the side table; its other columns are read from their values, never from their
names alone: the product is the column whose values are the products the lines sell (or their names, translated into
the lines' key through the catalogue), a receipt's quantity is the number that times the unit price gives the line's
money (or, summed over the receipt, the receipt's total), its day the one date column (or the receipt table's). Each
table is kept only when no check of the mapping newly fails. Nothing here looks at a business id.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from datamate.contracts import ColumnMap, Mapping, RawBusiness, TableMap
from datamate.loader.parse import parse_date, parse_money, parse_number

from . import transfer as T
from .build import build_canonical

_ITEM = re.compile(r"^\s*-\s*\*\*([^*]+)\*\*\s*:\s*(.+)$")  # "- **Tồn kho**: …"
_REF = re.compile(r"\*\*([^*]+)\*\*|`(?:([^`.]+)\.)?([^`]+)`")  # **Cột** or `bang.Cot`
KEY_SHARE = 0.9  # share of a column's distinct values that are the lines' products (or the catalogue's names)
QTY_SHARE = 0.98  # share of rows (or receipts) where unit price × the quantity column gives the money
CATEGORY_MAX = 30  # distinct values of an expense category column


def named(readme: str) -> dict[str, tuple[str, list[tuple[str | None, str, str]]]]:
    """Convention title (folded) -> (its folded text, [(table or None, column, the folded words after the column)])."""
    out = {}
    for line in readme.splitlines():
        m = _ITEM.match(line)
        if not m:
            continue
        refs = []
        for seg in m.group(2).split(";"):
            for r in _REF.finditer(seg):
                refs.append((r.group(2), (r.group(1) or r.group(3)).strip(), T._fold(seg[r.end():])))
        out[T._fold(m.group(1))] = (T._fold(m.group(2)), refs)
    return out


_CONVERSIONS = re.compile(r"\*\*quy doi don vi\*\*:.*?he so quy doi o (?:bang |file )?`([^`]+)`")  # folded line
FACTOR_MAX = 1000  # base units in one larger unit (from_readme.FACTOR_MAX)


def conversions(shop: _Shop) -> TableMap | None:
    """§10 unit conversions in the table the README names ("hệ số quy đổi ở bảng `don_vi_sp`"): its product, its unit
    (a unit the lines write) and its factor: the number column that times a line's quantity gives the line's base
    quantity on (nearly) every line sold in a unit of the table; lines without a base quantity: the one column of
    whole numbers from 1 to FACTOR_MAX."""
    m = next((m for m in map(_CONVERSIONS.search, map(T._fold, shop.raw.readme.splitlines())) if m), None)
    if m is None:
        return None
    name = m.group(1)
    hits = [t for t in shop.raw.tables
            if name in {T._fold(x) for x in (t.sheet, t.file, Path(t.file).stem, t.table_id) if x}]
    ids = [t.table_id for t in hits]
    if not ids or set(ids) & shop.used or len({frozenset(map(str, t.frame.columns)) for t in hits}) != 1:
        return None
    frames = shop.frames(ids)
    key = product_key(shop, ids, set())
    if key is None or key.transform is not None:
        return None
    units = [c for c in _columns(frames) if c != key.source and _share_in(_folded(frames, c), shop.units) >= 0.95]
    if len(units) != 1:
        return None
    table = pd.DataFrame({"k": [T._fold(v) for v in _values(frames, key.source)],
                          "u": [T._fold(v) for v in _values(frames, units[0])]})
    lines = shop.db.table("lines")
    sold = None
    if lines is not None and {"qty", "unit", "base_qty"} <= set(lines.columns):
        sold = pd.DataFrame({"k": lines["product_key"].astype(str).map(T._fold), "u": lines["unit"].astype(str).map(
            T._fold), "q": lines["qty"].astype(float), "b": lines["base_qty"].astype(float)}).dropna()
    found = []
    for c in _columns(frames):
        if c in (key.source, units[0]):
            continue
        f = table.assign(f=_numbers(frames, c, parse_number).values)
        if f["f"].isna().any() or not f["f"].between(1, FACTOR_MAX).all() or not (f["f"] % 1 == 0).all():
            continue
        if sold is not None:
            hit = sold.merge(f, on=["k", "u"])
            if hit.empty or float(((hit["q"] * hit["f"] - hit["b"]).abs() < 1e-6).mean()) < QTY_SHARE:
                continue
        found.append(c)
    if len(found) != 1:
        return None
    return TableMap(target="unit_conversions", sources=ids, columns=[
        key, ColumnMap(target="unit", source=units[0]), ColumnMap(target="factor", source=found[0], parse="number")])


def customer_names(shop: _Shop) -> list[ColumnMap]:
    """The customers' name, for a customer list mapped without one: its column named as the catalogue's product name
    column (one export names every list's name column alike: "TenGoi" in the products, staff and customers of a POS
    database), its values other than the customer codes."""
    cust, cat = shop.table("customers"), shop.table("products")
    name, key = _plain(cat, "product_name"), _plain(cust, "customer_key")
    if cust is None or key is None or name is None or "customer_name" in {c.target for c in cust.columns}:
        return []
    frames = shop.frames(cust.sources)
    if name not in _columns(frames) or name == key or _share_in(_folded(frames, name), _folded(frames, key)) > 0:
        return []
    return [ColumnMap(target="customer_name", source=name)]


def _ref(conv: dict, title: str, meaning: str) -> tuple[str | None, str] | None:
    """The one column the convention `title` names with words starting `meaning`."""
    hits = [(t, c) for t, c, w in conv.get(title, ("", []))[1] if w.startswith(meaning)]
    return hits[0] if len(hits) == 1 else None


def _holders(raw: RawBusiness, column: str, table: str | None, used: set[str]) -> list[str]:
    """The tables holding `column` (in the README's `table` when it names one), all of one layout and none read by
    the mapping yet; else none."""
    hits = [t for t in raw.tables if column in map(str, t.frame.columns)
            and (table is None or table in (t.sheet, t.file, Path(t.file).stem))]
    if not hits or {t.table_id for t in hits} & used or len({frozenset(map(str, t.frame.columns)) for t in hits}) != 1:
        return []
    return [t.table_id for t in hits]


class _Shop:
    """What the side tables are matched against: the mapping's own tables, built once."""

    def __init__(self, mapping: Mapping, raw: RawBusiness):
        self.mapping, self.raw = mapping, raw
        self.db = build_canonical(raw, mapping)
        lines = self.db.table("lines")
        self.keys = {T._fold(v) for v in lines["product_key"].dropna().astype(str)} if lines is not None else set()
        units = set(lines["unit"].dropna().astype(str)) if lines is not None and "unit" in lines.columns else set()
        conv = self.db.table("unit_conversions")
        if conv is not None and "unit" in conv.columns:
            units |= set(conv["unit"].dropna().astype(str))
        self.units = {T._fold(u) for u in units} - {""}
        orders = self.db.table("orders")
        times = orders["order_time"].dropna() if orders is not None else pd.Series(dtype="datetime64[ns]")
        self.last_day = times.max().date() if len(times) else None
        self.used = {s for tm in mapping.tables for s in tm.sources} | {
            c.args.get("table") for tm in mapping.tables for c in tm.columns if c.transform == "lookup"}

    def frames(self, ids: list[str]) -> list[pd.DataFrame]:
        return [t.frame for t in self.raw.tables if t.table_id in ids]

    def table(self, target: str) -> TableMap | None:
        return next((tm for tm in self.mapping.tables if tm.target == target), None)


def _values(frames: list[pd.DataFrame], column: str) -> list:
    return [v for f in frames if column in f.columns for v in f[column].tolist()]


def _folded(frames: list[pd.DataFrame], column: str) -> set[str]:
    return {T._fold(v) for f in frames if column in f.columns for v in f[column].dropna().unique()} - {""}


def _columns(frames: list[pd.DataFrame]) -> list[str]:
    return list(dict.fromkeys(str(c) for f in frames for c in f.columns))


def _plain(tm: TableMap | None, target: str) -> str | None:
    c = next((c for c in tm.columns if c.target == target), None) if tm is not None else None
    return c.source if c is not None and c.transform is None and c.source else None


def _share_in(values: set[str], known: set[str]) -> float:
    return len(values & known) / len(values) if values else 0.0


def product_key(shop: _Shop, ids: list[str], skip: set[str]) -> ColumnMap | None:
    """The column of these tables naming the product as the lines key it; else the one holding the catalogue's names,
    translated into the lines' key through the catalogue (a notebook "nối qua tên hàng" beside sales lines keyed by
    code). Two columns that fit: no guess."""
    frames = shop.frames(ids)
    cols = [c for c in _columns(frames) if c not in skip]
    direct = [c for c in cols if _share_in(_folded(frames, c), shop.keys) >= KEY_SHARE]
    if direct:
        return ColumnMap(target="product_key", source=direct[0]) if len(direct) == 1 else None
    cat = shop.table("products")
    key, name = _plain(cat, "product_key"), _plain(cat, "product_name")
    if cat is None or len(cat.sources) != 1 or not key or not name or key == name:
        return None
    names = _folded(shop.frames(cat.sources), name)
    by_name = [c for c in cols if _share_in(_folded(frames, c), names) >= KEY_SHARE]
    if len(by_name) != 1 or _share_in(_folded(shop.frames(cat.sources), key), shop.keys) < KEY_SHARE:
        return None
    return ColumnMap(target="product_key", source=by_name[0], transform="lookup",
                     args={"table": cat.sources[0], "key": name, "value": key, "keep_missing": False, "fold": True})


def _date_columns(frames: list[pd.DataFrame], skip: set[str]) -> list[str]:
    return [c for c in _columns(frames) if c not in skip and T._dates(frames, c)]


def inventory(shop: _Shop, conv: dict) -> TableMap | None:
    """The stock list ("tồn cuối ngày cuối có dữ liệu": dated the last day by transfer._settle_constants) or the stock
    card ("tồn sau lần nhập/bán/trả đó": dated by its one date column, the stock at a time its last row by then)."""
    snap, card = _ref(conv, "ton kho", "la ton cuoi ngay cuoi co du lieu"), _ref(conv, "ton kho", "la ton sau lan")
    if (snap is None) == (card is None):
        return None
    table, qty = snap or card
    ids = _holders(shop.raw, qty, table, shop.used)
    key = product_key(shop, ids, {qty}) if ids else None
    if key is None:
        return None
    if snap is not None:
        as_of = ColumnMap(target="as_of", parse="date", const="2000-01-01")  # the last day, or dropped
    else:
        dates = _date_columns(shop.frames(ids), {qty, key.source})
        if len(dates) != 1:
            return None
        as_of = ColumnMap(target="as_of", source=dates[0], parse="date")
    return TableMap(target="inventory", sources=ids, columns=[key, as_of, ColumnMap(target="base_qty", source=qty,
                                                                                    parse="qty")])


def expenses(shop: _Shop, conv: dict) -> TableMap | None:
    """The expense book: its amount the column the README names, its day its one date column, its category the one
    text column every row fills with few values."""
    text, refs = conv.get("so chi phi", ("", []))
    if not text.startswith("cac khoan chi") or len(refs) != 1:
        return None
    table, amount = refs[0][:2]
    ids = _holders(shop.raw, amount, table, shop.used)
    frames = shop.frames(ids)
    dates = _date_columns(frames, {amount}) if ids else []
    if len(dates) != 1:
        return None
    cols = [ColumnMap(target="expense_date", source=dates[0], parse="date"),
            ColumnMap(target="amount", source=amount, parse="money")]
    kinds = []
    for c in _columns(frames):
        values = [str(v).strip() for v in _values(frames, c) if v is not None and not pd.isna(v)]
        filled = [v for v in values if v]
        if c not in (amount, dates[0]) and filled and len(filled) >= 0.9 * len(_values(frames, c)) \
                and len(set(filled)) <= CATEGORY_MAX and sum(parse_number(v) is not None for v in filled) == 0:
            kinds.append(c)
    if len(kinds) == 1:
        cols.append(ColumnMap(target="category", source=kinds[0]))
    return TableMap(target="expenses", sources=ids, columns=cols)


def drugs(shop: _Shop, conv: dict) -> list[ColumnMap]:
    """§6 pharmacy attributes looked up in the drug list the README names, by the catalogue's product code: the
    prescription flag the README names, the active ingredient the one other column writing several substances with
    " + " (as the README says they are written)."""
    text, _ = conv.get("thuoc", ("", []))
    flag = _ref(conv, "thuoc", "dung (true/1) la thuoc ke don")
    cat = shop.table("products")
    key = _plain(cat, "product_key")
    have = {c.target for c in cat.columns} if cat is not None else set()
    if flag is None or key is None or "is_prescription" in have:
        return []
    ids = _holders(shop.raw, flag[1], flag[0], shop.used - set(cat.sources))
    if len(ids) != 1:
        return []
    frames = shop.frames(ids)
    codes = _folded(shop.frames(cat.sources), key)
    keys = [c for c in _columns(frames) if c != flag[1] and _share_in(_folded(frames, c), codes) >= KEY_SHARE
            and _share_in(codes, _folded(frames, c)) >= KEY_SHARE]
    if len(keys) != 1:
        return []

    def look(target: str, value: str, parse: str = "text") -> ColumnMap:
        return ColumnMap(target=target, source=key, parse=parse, transform="lookup",
                         args={"table": ids[0], "key": keys[0], "value": value, "keep_missing": False})
    out = [look("is_prescription", flag[1], "bool")]
    plus = [c for c in _columns(frames) if c not in (keys[0], flag[1])
            and any(" + " in str(v) for v in _values(frames, c))]
    if "hoat chat" in text and "active_ingredient" not in have and len(plus) == 1:
        out.append(look("active_ingredient", plus[0]))
    return out


def _numbers(frames: list[pd.DataFrame], column: str, parse) -> pd.Series:
    return pd.Series([parse(v) for v in _values(frames, column)], dtype="float64")


def _supplier(frames: list[pd.DataFrame], skip: set[str]) -> str | None:
    """The supplier column: named so ("Nhà cung cấp", "NCC", "MaNhaCungCap")."""
    hits = [c for c in _columns(frames) if c not in skip
            and re.search(r"nhacungcap|(^|[^a-z])ncc([^a-z]|$)|supplier", T._fold(c).replace(" ", ""))]
    return hits[0] if len(hits) == 1 else None


def purchases(shop: _Shop, conv: dict) -> TableMap | None:
    """§5 receipt lines: the table holding the README's unit purchase price. Its quantity: the number column that
    times the price gives the README's line money on (nearly) every row, else whose products with the price sum to
    the README's receipt total on (nearly) every receipt, the receipt then the column naming a row of the receipts'
    table, its day and supplier read there."""
    price = _ref(conv, "nhap hang", "la gia nhap mot don vi")
    if price is None:
        return None
    line_money, total = _ref(conv, "nhap hang", "la tien nhap cua ca dong"), _ref(conv, "nhap hang",
                                                                                   "la tong tien cua ca phieu nhap")
    ids = _holders(shop.raw, price[1], price[0], shop.used)
    if not ids:
        return None
    frames = shop.frames(ids)
    cols = _columns(frames)
    skip = {price[1]} | ({line_money[1]} if line_money else set())
    key = product_key(shop, ids, skip)
    if key is None:
        return None
    skip.add(key.source)
    unit_price = _numbers(frames, price[1], parse_money)
    head = rid = None
    if line_money is not None and line_money[1] in cols:
        money = _numbers(frames, line_money[1], parse_money)
        qty = [c for c in cols if c not in skip and _fits(_numbers(frames, c, parse_number) * unit_price, money)]
    elif total is not None:
        head = _holders(shop.raw, total[1], total[0], shop.used | set(ids))
        hframes = shop.frames(head)
        # the receipt number: a column of both tables, one row of the receipts' table each (a shop id written on
        # every row of both is not)
        rids = [c for c in cols if c not in skip and c in _columns(hframes) and _unique(hframes, c)
                and _share_in(_folded(frames, c), _folded(hframes, c)) >= QTY_SHARE] if head else []
        if len(rids) != 1:
            return None
        rid = rids[0]
        totals = dict(zip((T._fold(v) for v in _values(hframes, rid)), _numbers(hframes, total[1], parse_money)))
        receipts = pd.Series([T._fold(v) for v in _values(frames, rid)])
        qty = []
        for c in cols:
            if c in skip or c == rid:
                continue
            summed = (_numbers(frames, c, parse_number) * unit_price).groupby(receipts).sum()
            if _fits(summed, summed.index.map(totals).astype("float64").to_series(index=summed.index), QTY_SHARE):
                qty.append(c)
    else:
        return None
    if len(qty) != 1:
        return None
    skip |= {qty[0]}
    out = [key, ColumnMap(target="qty", source=qty[0], parse="qty"),
           ColumnMap(target="unit_cost", source=price[1], parse="money")]
    if line_money is not None and line_money[1] in cols:
        out.append(ColumnMap(target="amount", source=line_money[1], parse="money"))
    units = [c for c in cols if c not in skip and _share_in(_folded(frames, c), shop.units) >= 0.95]
    if len(units) == 1:
        out.append(ColumnMap(target="unit", source=units[0]))
        skip.add(units[0])
    if head:
        hframes = shop.frames(head)
        dates = _date_columns(hframes, {rid, total[1]})
        status = [c for c in _columns(hframes) if re.search(r"tinhtrang|trangthai|status", T._fold(c).replace(" ", ""))]
        if len(dates) != 1 or len(head) != 1 or any(len(_folded(hframes, c)) > 1 for c in status):
            return None  # no day, or receipts of several statuses (a cancelled one would count): no guess

        def look(target: str, value: str, parse: str = "text") -> ColumnMap:
            return ColumnMap(target=target, source=rid, parse=parse, transform="lookup",
                             args={"table": head[0], "key": rid, "value": value, "keep_missing": False})
        out += [ColumnMap(target="receipt_id", source=rid), look("receipt_time", dates[0], "datetime")]
        if (s := _supplier(hframes, {rid, total[1], dates[0]})) is not None:
            out.append(look("supplier", s))
    else:
        dates = _earliest([c for c in _date_columns(frames, skip) if _before_end(frames, c, shop.last_day)], frames)
        if len(dates) != 1:
            return None
        rid = _receipt_column(frames, skip | {dates[0]}, dates[0])
        if rid is None:
            return None
        out += [ColumnMap(target="receipt_id", source=rid), ColumnMap(target="receipt_time", source=dates[0],
                                                                      parse="datetime")]
        if (s := _supplier(frames, skip | {rid, dates[0]})) is not None:
            out.append(ColumnMap(target="supplier", source=s))
    return TableMap(target="purchases", sources=ids, columns=out)


def _unique(frames: list[pd.DataFrame], column: str) -> bool:
    values = [str(v).strip() for v in _values(frames, column)]
    return len(values) > 1 and len(set(values)) == len(values)


def _fits(got: pd.Series, want: pd.Series, share: float = QTY_SHARE) -> bool:
    ok = (got - want).abs() <= (want.abs() * 0.005).clip(lower=1.0)
    return bool(len(ok)) and got.notna().mean() >= share and float(ok.mean()) >= share


def _before_end(frames: list[pd.DataFrame], column: str, last_day) -> bool:
    """A receipt day: (nearly) every value on or before the shop's last day (an expiry date is mostly after)."""
    days = [d for d in (parse_date(v) for v in _values(frames, column)) if d is not None]
    return last_day is not None and bool(days) and sum(d <= last_day for d in days) >= QTY_SHARE * len(days)


def _earliest(dates: list[str], frames: list[pd.DataFrame]) -> list[str]:
    """Of several date columns of a receipt ledger, the receipt's day: the one on or before every other on (nearly)
    every row (a lot's expiry, short-dated ones included, comes after the day it was received)."""
    if len(dates) < 2:
        return dates
    days = {c: [parse_date(v) for v in _values(frames, c)] for c in dates}

    def before(a: str, b: str) -> bool:
        pairs = [(x, y) for x, y in zip(days[a], days[b]) if x is not None and y is not None]
        return bool(pairs) and sum(x <= y for x, y in pairs) >= QTY_SHARE * len(pairs)
    return [c for c in dates if all(before(c, o) for o in dates if o != c)][:2]


def _receipt_column(frames: list[pd.DataFrame], skip: set[str], day: str) -> str | None:
    """The receipt number of a receipt ledger: a column grouping rows (fewer values than rows, some written on several
    rows), each of its values on one day only; a lot number (one per row) or a note (on many days) is not."""
    rows = pd.concat([f for f in frames], ignore_index=True)
    hits = []
    for c in _columns(frames):
        if c in skip or c not in rows.columns:
            continue
        v = rows[c].astype(str).str.strip()
        v = v[(v != "") & (v != "nan") & (v != "None")]
        if len(v) < QTY_SHARE * len(rows) or v.nunique() >= len(v):
            continue  # a receipt number is on every row (a note "nhập đầu kỳ" on a few is not)
        # the day as read, not as written: a notebook writes one day "01/01/2025" and "2025-01-01"
        days = rows.loc[v.index, day].map(parse_date).astype(str).groupby(v).nunique()
        if float((days == 1).mean()) >= QTY_SHARE:
            hits.append(c)
    return hits[0] if len(hits) == 1 else None


def with_named_sides(mapping: Mapping, raw: RawBusiness) -> Mapping:
    """The side tables (stock, expenses, receipts, unit conversions), drug attributes and customer names the README's
    conventions name, where the mapping has none; each kept only when no check newly fails (from_readme._failed_checks).
    Receipts already mapped whose products are not the lines' (a notebook "nối qua tên hàng" moved from an example as
    keyed by code: every receipt found no product, train 10/11) are read again from their own table."""
    from .from_readme import _failed_checks
    have = {tm.target for tm in mapping.tables}
    conv = named(raw.readme)
    if not {"orders", "lines"} <= have or not conv:
        return mapping
    try:
        shop = _Shop(mapping, raw)
    except Exception:
        return mapping
    old = shop.table("purchases")
    if old is not None and (p := shop.db.table("purchases")) is not None and _share_in(
            {T._fold(v) for v in p["product_key"].dropna().astype(str)}, shop.keys) < KEY_SHARE:
        shop.used -= set(old.sources)
        have.discard("purchases")
    builds = (("inventory", lambda: inventory(shop, conv)), ("expenses", lambda: expenses(shop, conv)),
              ("purchases", lambda: purchases(shop, conv)), ("unit_conversions", lambda: conversions(shop)))
    found: list[TableMap] = []
    for target, build in builds:
        if target not in have:
            try:
                tm = build()
            except Exception:
                tm = None
            if tm is not None:
                found.append(tm)
    extra = {"products": drugs(shop, conv) if "products" in have else [], "customers": customer_names(shop)}
    if not found and not any(extra.values()):
        return mapping
    before = _failed_checks(T._settle_constants(mapping, raw), raw)
    if before is None:
        return mapping
    kept, out = [], mapping
    for tm in found:
        cand = out.model_copy(update={"tables": [t for t in out.tables if t.target != tm.target] + [tm]})
        if _failed_checks(T._settle_constants(cand, raw), raw) == before:
            out, kept = cand, kept + [tm.target]
    for target, cols in extra.items():
        if not cols:
            continue
        cand = out.model_copy(update={"tables": [
            tm.model_copy(update={"columns": list(tm.columns) + cols}) if tm.target == target else tm
            for tm in out.tables]})
        if _failed_checks(T._settle_constants(cand, raw), raw) == before:
            out, kept = cand, kept + [f"{target}.{c.target}" for c in cols]
    if not kept:
        return mapping
    return T._settle_constants(out.model_copy(update={"notes": list(out.notes) + [
        "bảng phụ theo quy ước README: " + ", ".join(kept)]}), raw)
