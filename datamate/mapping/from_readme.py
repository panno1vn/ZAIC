"""Mapping built from the README (N23, work package G2): for a shop no hand mapping moves onto.

Every README describes each column of each file in one line, "- **<column>**: <meaning>", and the meanings come from
a fixed list of phrases ("mã đơn", "thành tiền sau giảm", "số lượng đã đổi ra đơn vị cơ bản"…): 74 phrases in the 30
train READMEs, the column names around them different in every shop. The phrases below are those of the sales tables,
each with the canonical column every hand mapping of train gives it (tabulated 04/11: e.g. "thành tiền sau giảm" →
lines.line_amount 70 times of 70, "trạng thái đơn" → orders.status 87 of 87).

1. tables play a part by the phrases of their columns: the sales lines hold "số lượng", "thành tiền sau giảm" and a
   product ("tên hàng" or "mã hàng"); the orders hold "mã đơn", the order's time and "trạng thái đơn"; a catalogue
   holds "mã hàng" with "tên"… Two tables that could play one part: no guess.
2. lines with "mã đơn" are grouped into orders by it (in their own file, or in the lines' file for a flat export);
   lines without, in a ledger where no column groups rows, are each an order (§8, record_grain line_is_record).
3. status words are read like those of a moved mapping (transfer.read_word); a word still unknown stops the shop.

The ten checks of build.py then decide, as for every mapping. Nothing here looks at a business id.
"""
from __future__ import annotations

import re

import pandas as pd

from datamate.contracts import ColumnMap, Mapping, RawBusiness, TableMap

from . import transfer as T

# phrases naming the time of an order, the first found wins: the hand mappings read the column with the hour ("thời
# điểm đặt đơn" of a pharmacy export; "giờ đặt đơn" of two ledgers, a full date and time there), else "ngày bán"
ORDER_TIME = ("thoi diem dat don", "gio dat don", "ngay ban")
RECEIPT_DONE = re.compile(r"^da nhap( hang)?$|^hoan thanh$")  # receipt statuses read as received (train: "Đã nhập hàng")
PRODUCT = ("ma hang", "ten hang")
LINE_COLUMNS = (  # lines: phrase -> canonical column, parse
    ("so thu tu dong trong don", "line_no", "number"),
    ("so luong", "qty", "qty"),
    ("don vi tinh", "unit", "text"),
    ("so luong da doi ra don vi co ban", "base_qty", "qty"),
    ("don gia", "unit_price", "money"),
    ("giam gia", "line_discount", "money"),
    ("thanh tien sau giam", "line_amount", "money"),
)
ORDER_COLUMNS = (  # orders in their own table
    ("kenh ban", "channel", "text"),
    ("giam gia", "order_discount", "money"),
    ("tong tien don", "total_due", "money"),
    ("hinh thuc thanh toan cua don", "payment_method", "text"),
)


def groups(raw: RawBusiness) -> list[list[str]]:
    """The shop's tables the README describes, grouped as one table: a sheet the README names on its own, else the
    file's stem (its months, its parts _1 / _2026 even when the README gives each part a section), split again by
    layout. 04/11: by file name only, one workbook of four sheets described one by one made one group of four
    layouts; by README section only, the two parts of one ledger made two sales tables."""
    readme = T.readme_columns(raw.readme)
    out: dict[str, list[tuple[set, list[str]]]] = {}
    for t in raw.tables:
        section = T.readme_section(readme, t.table_id)
        if section is None:
            continue
        sheet = t.table_id.partition("::")[2]
        key = "sheet:" + section if section == sheet else "file:" + T.stem(t.table_id)
        cols = {str(c) for c in t.frame.columns}
        clusters = out.setdefault(key, [])
        home = next((c for c in clusters if T._jaccard(c[0], cols) >= T.SAME_TABLE), None)
        if home is None:
            clusters.append((cols, [t.table_id]))
        else:
            home[1].append(t.table_id)
    return [ids for clusters in out.values() for _, ids in clusters]


def phrases_of(raw: RawBusiness, ids: list[str]) -> dict[str, str]:
    """Raw column -> the folded first clause of its README meaning, for one group of alike tables (each table read
    with its own section); a column two sections describe differently has none."""
    readme = T.readme_columns(raw.readme)
    columns = {str(c) for t in raw.tables if t.table_id in ids for c in t.frame.columns}
    seen: dict[str, set[str]] = {}
    for i in ids:
        for c, m in T.column_notes(readme, i).items():
            if c in columns:
                seen.setdefault(c, set()).add(T._fold(re.split(r"[:;(]", m)[0]))
    return {c: ps.pop() for c, ps in seen.items() if len(ps) == 1}


class _Table:
    """A group of alike raw tables (one file, its months or parts) and what its README says of its columns."""

    def __init__(self, ids: list[str], phrases: dict[str, str]):
        self.ids, self.phrases = ids, phrases
        self.by_phrase: dict[str, list[str]] = {}
        for column, p in phrases.items():
            self.by_phrase.setdefault(p, []).append(column)

    def has(self, *phrases: str) -> bool:
        return all(p in self.by_phrase for p in phrases)

    def col(self, phrase: str) -> str | None:
        """The one column with this meaning; None when none, or two (no guess)."""
        cols = self.by_phrase.get(phrase, [])
        return cols[0] if len(cols) == 1 else None

    def first(self, phrases: tuple[str, ...]) -> str | None:
        return next((self.col(p) for p in phrases if p in self.by_phrase), None)

    def frames(self, raw: RawBusiness) -> list[pd.DataFrame]:
        return [t.frame for t in raw.tables if t.table_id in self.ids]


def _order_time(t: _Table, raw: RawBusiness) -> str | None:
    """The column of the order's time (ORDER_TIME); an hour column whose cells are no full dates is passed over."""
    for p in ORDER_TIME:
        if p not in t.by_phrase:
            continue
        c = t.col(p)
        if c is None or p != "gio dat don" or T._dates(t.frames(raw), c):
            return c
    return None


def _one(tables: list[_Table], test) -> _Table | None:
    hits = [t for t in tables if test(t)]
    return hits[0] if len(hits) == 1 else None


def _cm(target: str, source: str, parse: str = "text", **kw) -> ColumnMap:
    return ColumnMap(target=target, source=source, parse=parse, **kw)


def _lookup(target: str, source: str, table: _Table | None, key: str, value: str) -> ColumnMap | None:
    """A column read from another table by code (product name by product code…): one table, both columns named."""
    if table is None or len(table.ids) != 1 or table.col(key) is None or table.col(value) is None:
        return None
    return _cm(target, source, transform="lookup", args={"table": table.ids[0], "key": table.col(key),
                                                          "value": table.col(value), "keep_missing": False})


def _status_map(raw: RawBusiness, ids: list[str], column: str) -> dict[str, str]:
    words = {w: T.read_word("orders", "status", w) for w in T._raw_values(raw, ids, column)}
    return {w: v for w, v in words.items() if v is not None}


def map_from_readme(raw: RawBusiness) -> tuple[Mapping | None, str]:
    """The mapping the README's column meanings give, or None and why not."""
    tables = [_Table(ids, phrases_of(raw, ids)) for ids in groups(raw)]
    tables = [t for t in tables if t.phrases]
    lines = _one(tables, lambda t: t.has("so luong", "thanh tien sau giam") and any(p in t.by_phrase for p in PRODUCT))
    if lines is None:
        return None, "README không mô tả đúng một bảng dòng hàng"
    others = [t for t in tables if t is not lines]
    catalogue = _one(others, lambda t: t.has("ma hang", "ten") and not t.has("ma don"))
    clients = _one(others, lambda t: t.has("ma khach", "ten") and not t.has("ma don"))

    # ---- lines
    key = lines.first(PRODUCT)
    if key is None:
        return None, "bảng dòng hàng có hai cột cùng nghĩa mặt hàng"
    name = lines.col("ten hang")
    cols = [_cm("product_key", key), _cm("is_item", None, const=True)]
    if name is not None:
        cols.append(_cm("product_name", name))
    elif (looked := _lookup("product_name", key, catalogue, "ma hang", "ten")) is not None:
        cols.append(looked)
    else:
        return None, "dòng hàng chỉ có mã hàng, không tra được tên"
    for phrase, target, parse in LINE_COLUMNS:
        if (c := lines.col(phrase)) is not None:
            cols.append(_cm(target, c, parse))
    if not {"qty", "line_amount"} <= {c.target for c in cols}:
        return None, "bảng dòng hàng có hai cột cùng nghĩa số lượng hoặc thành tiền"

    # ---- orders
    order_id = lines.col("ma don")
    if order_id is not None:
        grain = "order"
        orders = _one(others, lambda t: t.has("ma don", "trang thai don") and any(p in t.by_phrase for p in ORDER_TIME))
        flat = orders is None
        if flat:
            if not (lines.has("trang thai don") and any(p in lines.by_phrase for p in ORDER_TIME)):
                return None, "không thấy bảng đơn (mã đơn, ngày, trạng thái)"
            orders = lines
        if not T._groups_rows(pd.concat([t.frame[order_id] for t in raw.tables if t.table_id in lines.ids],
                                        ignore_index=True)):
            return None, "cột mã đơn của dòng hàng không gom dòng thành đơn"
        oid = orders.col("ma don")
    else:
        if not (lines.has("trang thai don") and any(p in lines.by_phrase for p in ORDER_TIME)):
            return None, "sổ không mã đơn mà không có ngày và trạng thái"
        if T._has_order_ids(raw, lines.ids):
            return None, "README không ghi mã đơn nhưng có cột gom dòng thành đơn"
        grain, orders, flat, oid, order_id = "line_is_record", lines, False, "_row", "_row"
    time, status = _order_time(orders, raw), orders.col("trang thai don")
    if oid is None or time is None or status is None:
        return None, "bảng đơn có hai cột cùng nghĩa mã đơn, ngày hoặc trạng thái"
    cols.insert(0, _cm("order_id", order_id))
    # a flat export's one discount column is the lines' (LINE_COLUMNS); the amount check tells if it is not
    ocols =[_cm("order_id", oid), _cm("order_time", time, "datetime"), _cm("has_time", None, const=False),
             _cm("status", status, transform="order_status_from_lines") if flat else _cm("status", status)]
    if (c := orders.col("ma khach")) is not None:
        ocols.append(_cm("customer_key", c))
        if (n := orders.col("ten khach")) is not None:
            ocols.append(_cm("customer_name", n))
        elif (looked := _lookup("customer_name", c, clients, "ma khach", "ten")) is not None:
            ocols.append(looked)
    elif (n := orders.col("ten khach")) is not None:
        ocols += [_cm("customer_key", n), _cm("customer_name", n)]
    if not flat and orders is not lines:
        for phrase, target, parse in ORDER_COLUMNS:
            if (c := orders.col(phrase)) is not None:
                ocols.append(_cm(target, c, parse))
    elif (c := orders.col("kenh ban")) is not None:
        ocols.append(_cm("channel", c))
    out = [TableMap(target="orders", sources=orders.ids, columns=ocols,
                    value_maps={"status": _status_map(raw, orders.ids, status)}),
           TableMap(target="lines", sources=lines.ids, columns=cols)]

    # ---- the tables around them, each only when one table plays the part and its key is the lines' key
    by_code = key == lines.col("ma hang")
    if by_code and catalogue is not None and (k := catalogue.col("ma hang")) and (n := catalogue.col("ten")):
        pc = [_cm("product_key", k), _cm("product_name", n)]
        pc += [_cm(t, c) for p, t in (("nhom hang", "product_group"), ("don vi co ban", "base_unit"))
               if (c := catalogue.col(p)) is not None]
        out.append(TableMap(target="products", sources=catalogue.ids, columns=pc))
    customer_key = next((c.source for c in ocols if c.target == "customer_key"), None)
    if clients is not None and customer_key == orders.col("ma khach") and customer_key is not None:
        cc = [_cm("customer_key", clients.col("ma khach")), _cm("customer_name", clients.col("ten"))]
        cc += [_cm(t, c) for p, t in (("nhom khach", "customer_group"), ("so dien thoai", "phone"),
                                       ("dia chi", "address")) if (c := clients.col(p)) is not None]
        if all(c.source for c in cc):
            out.append(TableMap(target="customers", sources=clients.ids, columns=cc))
    paid = _one(others, lambda t: t.has("ma don", "thoi diem thu", "so tien"))
    if grain == "order" and paid is not None and all(paid.col(p) for p in ("ma don", "thoi diem thu", "so tien")):
        pay = [_cm("order_id", paid.col("ma don")), _cm("paid_time", paid.col("thoi diem thu"), "datetime"),
               _cm("amount", paid.col("so tien"), "money")]
        if (c := paid.col("hinh thuc thanh toan")) is not None:
            pay.append(_cm("method", c))
        out.append(TableMap(target="payments", sources=paid.ids, columns=pay))
    key_phrase = lines.phrases[key]
    stock = _one(others, lambda t: t.has("ton kho", key_phrase) and not t.has("ma don"))
    if stock is not None and stock.col(key_phrase) and stock.col("ton kho"):
        out.append(TableMap(target="inventory", sources=stock.ids, columns=[
            _cm("product_key", stock.col(key_phrase)), _cm("base_qty", stock.col("ton kho"), "qty"),
            _cm("as_of", None, "date", const="2000-01-01")]))  # dated by transfer._settle_constants, or dropped
    if (bought := _purchases(raw, others, key_phrase)) is not None:
        out.append(bought)
    shipped = _one(others, lambda t: t.has("ma don", "ngay giao") and t is not orders)
    if grain == "order" and shipped is not None and shipped.col("ma don") and shipped.col("ngay giao"):
        dc = [_cm("order_id", shipped.col("ma don")), _cm("delivery_time", shipped.col("ngay giao"), "datetime")]
        if (c := shipped.col("dot giao")) is not None:
            dc.append(_cm("batch_no", c, "number"))
        out.append(TableMap(target="deliveries", sources=shipped.ids, columns=dc))
    return Mapping(record_grain=grain, tables=out, notes=["dựng từ mô tả cột trong README"]), ""


PURCHASE_COLUMNS = (  # purchases: phrases -> canonical column, parse (the first phrase found)
    (("so luong nhap", "so luong"), "qty", "qty"),
    (("don vi nhap", "don vi tinh"), "unit", "text"),
    (("gia nhap mot don vi",), "unit_cost", "money"),
    (("tien nhap cua ca dong",), "amount", "money"),
    (("so lo",), "lot_id", "text"),
    (("han su dung",), "expiry_date", "date"),
    (("ghi chu",), "note", "text"),
)


def _purchases(raw: RawBusiness, tables: list[_Table], key_phrase: str) -> TableMap | None:
    """§5 receipts: the receipt lines (receipt code, the product as the sales lines key it, a quantity and money: a
    table of lots has no money), with their day and supplier written on them (a ledger) or looked up in the
    receipts' own table by code (an export). A receipt status other than received ("Đã nhập hàng"), which could be
    a cancelled receipt: no purchases."""
    detail = _one(tables, lambda t: t.has("ma phieu nhap", key_phrase) and not t.has("ma don")
                  and any(p in t.by_phrase for p in ("so luong nhap", "so luong"))
                  and any(p in t.by_phrase for p in ("gia nhap mot don vi", "tien nhap cua ca dong")))
    if detail is None or detail.col("ma phieu nhap") is None or detail.col(key_phrase) is None:
        return None
    receipt = detail.col("ma phieu nhap")
    head = detail if detail.has("ngay nhap") else _one(
        [t for t in tables if t is not detail], lambda t: t.has("ma phieu nhap", "ngay nhap"))
    if head is None or head.col("ngay nhap") is None or head.col("ma phieu nhap") is None:
        return None
    status = head.col("trang thai phieu nhap")
    if status is not None and not all(RECEIPT_DONE.match(T._fold(w)) for w in T._raw_values(raw, head.ids, status)):
        return None
    cols = [_cm("receipt_id", receipt), _cm("product_key", detail.col(key_phrase))]
    supplier = head.first(("nha cung cap", "ma nha cung cap"))
    if head is detail:
        cols.append(_cm("receipt_time", head.col("ngay nhap"), "datetime"))
        if supplier is not None:
            cols.append(_cm("supplier", supplier))
    else:
        time = _lookup("receipt_time", receipt, head, "ma phieu nhap", "ngay nhap")
        if time is None:
            return None
        cols.append(time.model_copy(update={"parse": "datetime"}))
        if supplier is not None:
            phrase = head.phrases[supplier]
            if (looked := _lookup("supplier", receipt, head, "ma phieu nhap", phrase)) is not None:
                cols.append(looked)
    for phrases, target, parse in PURCHASE_COLUMNS:
        if (c := detail.first(phrases)) is not None:
            cols.append(_cm(target, c, parse))
    if not {"qty", "amount"} & {c.target for c in cols}:
        return None
    return TableMap(target="purchases", sources=detail.ids, columns=cols)
