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
import unicodedata

import pandas as pd

from datamate.contracts import ColumnMap, Mapping, RawBusiness, TableMap

from . import transfer as T
from .build import build_canonical

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
    ("tong tien hang cua don", "goods_amount", "money"),  # "cộng thành tiền các dòng": checked against the lines
    ("tien hang cua don", "goods_amount", "money"),
    ("so khach phai tra cho ca don", "total_due", "money"),
)
# N40, public READMEs (06/11): phrases train never used, each for one meaning the lists above know (a phrase starting
# with one: "số hoá đơn, ghi ở mọi dòng của hoá đơn…"); the order's note stands for the status in a ledger without a
# status column (public rulebook §8)
PHRASE_ALIASES = (
    ("ma don", ("so hoa don", "so thu tu don")),
    ("thanh tien sau giam", ("thanh tien cua dong",)),
    ("ten hang", ("hang ban",)),
    ("don gia", ("don gia mot",)),  # "đơn giá một máy / một cái"
    ("tien hang cua don", ("tong tien ca phieu",)),  # N42: a repair ticket's money
    ("ngay ban", ("ngay sua",)),
    ("ma nhan vien ban", ("tho lam phieu",)),
    ("cac viec da lam", ("cac viec da lam",)),
    ("dong xe va bien so", ("dong xe va bien so",)),
    ("ho ten", ("ho ten tho", "ho ten nhan vien")),
    ("phan tram hoa hong", ("phan tram hoa hong",)),  # "phần trăm hoa hồng của thợ, tính trên tổng Tiền…"
    ("tien thu may cu", ("tien thu may cu",)),
    ("tien bot cho ca don", ("tien bot cho ca don",)),
    ("so tien khach tra cho ca don", ("so tien khach tra cho ca don",)),
    ("ghi chu cua don", ("ghi chu cua don", "ghi chu")),
)
FLAT_ORDER_COLUMNS = (  # the order's cells in a flat ledger (lines and orders one table)
    ("kenh ban", "channel", "text"),
    ("tien bot cho ca don", "order_discount", "money"),  # a public phone ledger's "Bớt" (N44)
    ("tien thu may cu", "trade_in_amount", "money"),  # "tiền thu máy cũ của khách, trừ vào tiền đơn"
    ("so tien khach tra cho ca don", "total_due", "money"),  # "số tiền khách trả cho cả đơn, đã trừ bớt…"
)
GOODS = ("tien hang cua don", "tong tien hang cua don")  # §1 revenue of an order, in a shop without lines


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
        for canonical, aliases in PHRASE_ALIASES:  # N40: the same meanings in words train never used
            if canonical not in self.by_phrase:
                hits = [c for c, p in phrases.items() if any(p == a or p.startswith((a + " ", a + ","))
                                                              for a in aliases)]
                if hits:
                    self.by_phrase[canonical] = hits

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


def _has_status(t: _Table) -> bool:
    return t.has("trang thai don") or t.has("ghi chu cua don")


def _status_column(t: _Table) -> tuple[str | None, bool]:
    """The order status column, and whether it is the order's note (N40: §8 of the public rulebook, a ledger without
    a status column writes the status in its note)."""
    if t.has("trang thai don"):
        return t.col("trang thai don"), False
    return t.col("ghi chu cua don"), True


def _status_map(raw: RawBusiness, ids: list[str], column: str) -> dict[str, str]:
    words = {w: T.read_word("orders", "status", w) for w in T._raw_values(raw, ids, column)}
    return {w: v for w, v in words.items() if v is not None}


def map_from_readme(raw: RawBusiness) -> tuple[Mapping | None, str]:
    """The mapping the README's column meanings give, or None and why not."""
    tables = [_Table(ids, phrases_of(raw, ids)) for ids in groups(raw)]
    tables = [t for t in tables if t.phrases]
    lines = _one(tables, lambda t: t.has("so luong", "thanh tien sau giam") and any(p in t.by_phrase for p in PRODUCT))
    if lines is None:
        if not any(t.has("so luong") or t.has("thanh tien sau giam") for t in tables):
            return _orders_only(raw, tables)
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
        orders = _one(others, lambda t: t.has("ma don") and _has_status(t) and any(p in t.by_phrase for p in ORDER_TIME))
        flat = orders is None
        if flat:
            if not (_has_status(lines) and any(p in lines.by_phrase for p in ORDER_TIME)):
                return None, "không thấy bảng đơn (mã đơn, ngày, trạng thái)"
            orders = lines
        if not T._groups_rows(pd.concat([t.frame[order_id] for t in raw.tables if t.table_id in lines.ids],
                                        ignore_index=True)):
            return None, "cột mã đơn của dòng hàng không gom dòng thành đơn"
        oid = orders.col("ma don")
    else:
        if not (_has_status(lines) and any(p in lines.by_phrase for p in ORDER_TIME)):
            return None, "sổ không mã đơn mà không có ngày và trạng thái"
        if T._has_order_ids(raw, lines.ids):
            return None, "README không ghi mã đơn nhưng có cột gom dòng thành đơn"
        grain, orders, flat, oid, order_id = "line_is_record", lines, False, "_row", "_row"
    time, (status, in_note) = _order_time(orders, raw), _status_column(orders)
    if oid is None or time is None or status is None:
        return None, "bảng đơn có hai cột cùng nghĩa mã đơn, ngày hoặc trạng thái"
    cols.insert(0, _cm("order_id", order_id))
    # a flat export's one discount column is the lines' (LINE_COLUMNS); the amount check tells if it is not
    ocols =[_cm("order_id", oid), _cm("order_time", time, "datetime"), _cm("has_time", None, const=False),
             _cm("status", status, transform="status_from_note") if in_note else
             _cm("status", status, transform="order_status_from_lines") if flat else _cm("status", status)]
    ocols += _customer_columns(orders, clients)
    if not flat and orders is not lines:
        for phrase, target, parse in ORDER_COLUMNS:
            if (c := orders.col(phrase)) is not None and target not in {x.target for x in ocols}:
                ocols.append(_cm(target, c, parse))
    else:  # a flat ledger: the order's cells on its rows (N44, public phone ledgers)
        for phrase, target, parse in FLAT_ORDER_COLUMNS:
            if (c := orders.col(phrase)) is not None and target not in {x.target for x in ocols}:
                ocols.append(_cm(target, c, parse))
    out = [TableMap(target="orders", sources=orders.ids, columns=ocols,
                    value_maps={} if in_note else {"status": _status_map(raw, orders.ids, status)}),
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


def _customer_columns(orders: _Table, clients: _Table | None) -> list[ColumnMap]:
    """§3: the customer's code when the shop has one (its name from the orders or the customer list), else the name."""
    if (c := orders.col("ma khach")) is not None:
        out = [_cm("customer_key", c)]
        if (n := orders.col("ten khach")) is not None:
            out.append(_cm("customer_name", n))
        elif (looked := _lookup("customer_name", c, clients, "ma khach", "ten")) is not None:
            out.append(looked)
        return out
    if (n := orders.col("ten khach")) is not None:
        return [_cm("customer_key", n), _cm("customer_name", n)]
    return []


def _orders_only(raw: RawBusiness, tables: list[_Table]) -> tuple[Mapping | None, str]:
    """A shop that records orders without their lines (a train README: "mỗi dòng một đơn hàng, không có chi tiết mặt
    hàng"): one row per order with its code, day, status and goods amount, the §1 revenue of the order. Revenue, order
    counts, customers and days are answered from it; every figure that needs the lines finds none and abstains.
    N42: a ledger of tickets with no code (a repair shop's, public 06/11: "mỗi dòng một lượt xe vào sửa, không ghi mã
    phiếu") has one order per row (§8 "bảng không ghi theo đơn: mỗi dòng là một lần ghi"); its status is in its note
    (N40), its warranty tickets are those whose note says "bảo hành", its jobs and its vehicle (model and plate in one
    cell) are read too."""
    orders = _one(tables, lambda t: _has_status(t) and any(p in t.by_phrase for p in ORDER_TIME)
                  and any(p in t.by_phrase for p in GOODS))
    if orders is None:
        return None, "README không mô tả đúng một bảng dòng hàng, cũng không mô tả bảng đơn có tiền hàng"
    oid, time, goods = orders.col("ma don"), _order_time(orders, raw), orders.first(GOODS)
    status, in_note = _status_column(orders)
    if time is None or status is None or goods is None:
        return None, "bảng đơn có hai cột cùng nghĩa ngày, trạng thái hoặc tiền hàng"
    grain = "order"
    if oid is None:
        # the README describes every column and none is a code: each row is one record (§8). The row-grouping test of
        # sales ledgers does not apply: tickets of one day or one price follow each other
        if orders.has("ma don"):
            return None, "bảng đơn có hai cột cùng nghĩa mã đơn"
        grain, oid = "line_is_record", "_row"
    else:
        # §8 "hai dòng của cùng một đơn giống nhau ở mọi ô: tính một lần" (a public shop: 308 invoices written twice,
        # alike in every cell); two rows of one id that differ are no orders-only table
        rows = pd.concat(orders.frames(raw), ignore_index=True).drop_duplicates()
        if not rows[oid].dropna().is_unique:
            return None, "bảng đơn không có dòng hàng mà mã đơn lặp lại"
    clients = _one([t for t in tables if t is not orders], lambda t: t.has("ma khach", "ten") and not t.has("ma don"))
    ocols = [_cm("order_id", oid), _cm("order_time", time, "datetime"), _cm("has_time", None, const=False),
             _cm("status", status, transform="status_from_note") if in_note else _cm("status", status)]
    ocols += _customer_columns(orders, clients)
    for phrase, target, parse in ORDER_COLUMNS:
        if (c := orders.col(phrase)) is not None and target not in {x.target for x in ocols}:
            ocols.append(_cm(target, c, parse))
    if goods not in {x.source for x in ocols if x.target == "goods_amount"}:
        ocols = [x for x in ocols if x.target != "goods_amount"] + [_cm("goods_amount", goods, "money")]
    for phrase, target in ORDER_ATTRIBUTES:
        if (c := orders.col(phrase)) is not None and target not in {x.target for x in ocols}:
            ocols.append(_cm(target, c))
    ocols += _repair_columns(orders, raw, status if in_note else None)
    out = [TableMap(target="orders", sources=orders.ids, columns=ocols,
                    value_maps={} if in_note else {"status": _status_map(raw, orders.ids, status)})]
    # N42: the staff list ("họ tên thợ"): the ledger's nicknames become its full names (build.full_employee_names)
    staff = _one([t for t in tables if t is not orders], lambda t: t.has("ho ten"))
    if staff is not None and (name := staff.col("ho ten")) is not None:
        sc = [_cm("employee_key", name), _cm("employee_name", name)]
        if (c := staff.col("ngay vao lam")) is not None:
            sc.append(_cm("start_date", c, "date"))
        if (c := staff.col("phan tram hoa hong")) is not None:  # "phần trăm hoa hồng của thợ, tính trên…"
            sc.append(_cm("commission_pct", c, "number"))
        out.append(TableMap(target="employees", sources=staff.ids, columns=sc))
    return Mapping(record_grain=grain, tables=out, notes=["dựng từ mô tả cột trong README (chỉ có bảng đơn)"]), ""


PLATE = r"\d{2}[A-Z]{1,2}\d?-\d{3}\.?\d{2}"  # Vietnamese plates: 59B6-219.16, 51L3-168.55, 29A-123.45


def _repair_columns(orders: _Table, raw: RawBusiness, note: str | None) -> list[ColumnMap]:
    """N42: a repair ledger's jobs ("các việc đã làm"), vehicle model and plate ("dòng xe và biển số" in one cell) and
    warranty tickets (a note saying "bảo hành")."""
    out = []
    if (c := orders.col("cac viec da lam")) is not None:
        out.append(_cm("services", c))
    if (c := orders.col("dong xe va bien so")) is not None:
        out.append(_cm("vehicle_plate", c, transform="regex_extract", args={"pattern": f"({PLATE})", "group": 1}))
        out.append(_cm("vehicle_model", c, transform="regex_extract",
                       args={"pattern": rf"^\s*(.*?)\s*{PLATE}", "group": 1}))
    if note is not None and any("bao hanh" in T._fold(v) for v in T._raw_values(raw, orders.ids, note)):
        out.append(_cm("is_warranty", note, "bool", transform="note_contains",
                       args={"map": {"bảo hành": True}, "default": False}))
    return out


# ---------------------------------------------------------------- attributes the README names (N29)
ORDER_ATTRIBUTES = (("ma nhan vien ban", "employee"), ("hinh thuc thanh toan cua don", "payment_method"),
                    ("kenh ban", "channel"), ("nhom khach", "customer_group"))
DRUG_ATTRIBUTES = (("hoat chat", "active_ingredient", "text"), ("thuoc ke don", "is_prescription", "bool"))


# N100: debts a shop records only as the state at the end of its data, said so in the README's conventions:
#   "**Còn nợ**: **Còn nợ** là số khách còn nợ của đơn, tính đến hết ngày cuối dữ liệu."   (an amount per order)
#   "**Còn nợ**: ghi chú nợ ở **Note** là tình trạng của đơn tính đến hết ngày cuối dữ liệu." (words per order)
_LEFT_AMOUNT = re.compile(r"\*\*([^*]+)\*\*\s+là số khách còn nợ của đơn,?\s+tính đến hết ngày cuối dữ liệu")
_LEFT_NOTE = re.compile(r"ghi chú nợ ở \*\*([^*]+)\*\* là tình trạng của đơn tính đến hết ngày cuối dữ liệu")
_COLUMN_LINE = re.compile(r"^\s*-\s*\*\*([^*]+)\*\*:\s*(.+)$")


def with_debt_snapshot(mapping: Mapping, raw: RawBusiness) -> Mapping:
    """N100. The orders' debt at the end of the data, where the README says the shop records only that: the amount
    column as orders.debt_left; or the note column as orders.note (read into debt_left when the data is built,
    build.debt_snapshot), with the order's amount due (the column the README calls "khách cần trả cho cả đơn") as
    orders.total_due. Only columns of the orders' own files, and never over a column the mapping already has."""
    readme = unicodedata.normalize("NFC", raw.readme or "")
    amount, note = _LEFT_AMOUNT.search(readme), _LEFT_NOTE.search(readme)
    orders = next((tm for tm in mapping.tables if tm.target == "orders"), None)
    if orders is None or not (amount or note) or "payments" in {tm.target for tm in mapping.tables}:
        return mapping
    cols = {str(c) for f in _frames_of(raw, orders) for c in f.columns}
    have = {c.target for c in orders.columns}
    added = []
    if amount and amount.group(1).strip() in cols and "debt_left" not in have:
        added.append(_cm("debt_left", amount.group(1).strip(), "money"))
    if note and note.group(1).strip() in cols and "note" not in have:
        added.append(_cm("note", note.group(1).strip()))
        if "total_due" not in have:
            due = [m.group(1).strip() for line in readme.splitlines() if (m := _COLUMN_LINE.match(line))
                   and T._fold(m.group(2)).startswith("khach can tra cho ca don") and m.group(1).strip() in cols]
            if len(set(due)) == 1:
                added.append(_cm("total_due", due[0], "money"))
    if not added:
        return mapping
    tables = [tm.model_copy(update={"columns": list(tm.columns) + added}) if tm is orders else tm for tm in mapping.tables]
    return mapping.model_copy(update={"tables": tables, "notes": list(mapping.notes) + [
        "nợ tình trạng cuối dữ liệu (README): " + ", ".join(f"orders.{c.target}" for c in added)]})


FACTOR_MAX = 1000  # base units in one larger unit: a box of 6, a crate of 24, a roll of 100 m; never a price


def factor_not_price(mapping: Mapping, raw: RawBusiness) -> Mapping:
    """N90. A conversion factor read from a price column (public 08/11: "Giá bán theo đơn vị quy đổi" 210 000 beside
    "Bằng" 6 for a box of 6 croissants; every line sold by the box counted 210 000 pieces): when every factor the
    mapping reads is above FACTOR_MAX and exactly one other column of that sheet holds whole numbers from 2 to
    FACTOR_MAX on every row, that column is the factor."""
    tm = next((t for t in mapping.tables if t.target == "unit_conversions"), None)
    col = next((c for c in tm.columns if c.target == "factor"), None) if tm is not None else None
    if col is None or col.transform is not None or not col.source or len(tm.sources) != 1:
        return mapping
    frame = next((t.frame for t in raw.tables if t.table_id == tm.sources[0]), None)
    if frame is None or col.source not in frame.columns:
        return mapping
    values = pd.to_numeric(frame[col.source], errors="coerce").dropna()
    if values.empty or not (values > FACTOR_MAX).all():
        return mapping
    used = {c.source for c in tm.columns}

    def factor_like(name) -> bool:
        v = pd.to_numeric(frame[name], errors="coerce")
        return name not in used and v.notna().all() and ((v % 1 == 0) & (v >= 2) & (v <= FACTOR_MAX)).all()
    others = [name for name in frame.columns if factor_like(name)]
    if len(others) != 1:
        return mapping
    cols = [c.model_copy(update={"source": others[0]}) if c is col else c for c in tm.columns]
    tables = [t.model_copy(update={"columns": cols}) if t is tm else t for t in mapping.tables]
    return mapping.model_copy(update={"tables": tables, "notes": list(mapping.notes) + [
        f"hệ số quy đổi: cột {others[0]!r} thay cho {col.source!r} (giá trị > {FACTOR_MAX})"]})


def enrich(mapping: Mapping, raw: RawBusiness) -> Mapping:
    """The attribute columns the README names that a mapping leaves out: a mapping moved from an example has only the
    columns of the example's shop (04/11: a shop moved from a pharmacy without customer groups lost its "nhóm khách",
    and 32 train questions by customer group abstained). Added only where the mapping has no column for them:
    - on the orders: seller ("mã nhân viên bán"), payment method of the order, channel, customer group, else the
      customer group read from the customer list by the customer code the orders already carry (as the hand mappings
      do);
    - on the catalogue: product group, active ingredient and prescription flag, from the catalogue itself or from a
      drug list by the product code the catalogue already carries;
    - a mapping with no catalogue at all gets the README's, when the lines' product column is the README's "mã hàng".
    A filter on an attribute the shop does not record still abstains (the frames find no column).
    Then what the README's conventions name for debts and cost (N35, `with_conventions`), and the order's hour from
    the README's "thời điểm đặt đơn" when the mapping read only its day (N73, `with_order_hour`)."""
    from .named_sides import with_named_sides  # N111: side tables the conventions name, columns read from values
    mapping = with_side_tables(with_order_hour(drop_amount_as_method(with_conventions(mapping, raw), raw), raw), raw)
    mapping = with_debt_snapshot(factor_not_price(with_named_sides(mapping, raw), raw), raw)
    tables = [t for t in (_Table(ids, phrases_of(raw, ids)) for ids in groups(raw)) if t.phrases]
    if not tables:
        return mapping

    def home(tm: TableMap) -> _Table | None:
        return _one(tables, lambda t: bool(set(t.ids) & set(tm.sources)))

    def plain_source(tm: TableMap, target: str) -> str | None:
        c = next((c for c in tm.columns if c.target == target), None)
        return c.source if c is not None and c.transform is None else None

    out, added = [], []
    for tm in mapping.tables:
        t, have, add = home(tm), {c.target for c in tm.columns}, []
        others = [x for x in tables if x is not t]
        if t is not None and tm.target == "orders":
            for phrase, target in ORDER_ATTRIBUTES:
                if target not in have and (c := t.col(phrase)) is not None:
                    add.append(_cm(target, c))
            key = plain_source(tm, "customer_key")
            code = t.col("ma khach")
            if key is not None and code is not None and key != code and key == t.col("ten khach"):
                # N105. §3 "Shop có mã khách: mỗi mã khách là một khách": a mapping keyed on the name where the orders
                # carry the code too (a public restaurant: 210 codes written under 1223 spellings of names, with and
                # without the phone number, so each customer counted 4 times): the code is the key, the name its name
                tm = tm.model_copy(update={"columns": [c for c in tm.columns if c.target not in (
                    "customer_key", "customer_name")] + [_cm("customer_key", code), _cm("customer_name", key)]})
                have, key = {c.target for c in tm.columns}, code
                added.append("orders.customer_key")
            oid = plain_source(tm, "order_id")
            dues = _one(others, lambda x: x.has("ma don", "han thanh toan") and not x.has("so luong"))
            if "due_date" not in have and oid is not None and oid == t.col("ma don") \
                    and (looked := _lookup("due_date", oid, dues, "ma don", "han thanh toan")) is not None:
                # N113: the due day of a credit sale, from the README's due-date book ("Ngày phải trả: hạn thanh
                # toán", by "Mã đơn hàng: mã đơn"; a public building-materials shop, 6 questions)
                add.append(looked.model_copy(update={"parse": "date"}))
            if "customer_group" not in have | {a.target for a in add} and key is not None and key == t.col("ma khach"):
                clients = _one(others, lambda x: x.has("ma khach", "nhom khach") and not x.has("ma don"))
                if (looked := _lookup("customer_group", key, clients, "ma khach", "nhom khach")) is not None:
                    add.append(looked)
        elif t is not None and tm.target == "products":
            if "product_group" not in have and (c := t.col("nhom hang")) is not None:
                add.append(_cm("product_group", c))
            add += _drug_columns(t, others, plain_source(tm, "product_key"), have)
        elif t is not None and tm.target == "lines" and (base := t.col("so luong da doi ra don vi co ban")) is not None:
            # the README's base quantity column (a train shop moved from an example, 06/11: "Quy ra ĐV lẻ" read as the
            # line's quantity beside the line's unit "thùng"; once README conversions existed it was counted 24 times)
            fixed = []
            if plain_source(tm, "qty") == base and (q := t.col("so luong")) is not None and q != base:
                fixed.append("qty")
                tm = tm.model_copy(update={"columns": [c.model_copy(update={"source": q}) if c.target == "qty" else c
                                                       for c in tm.columns]})
                have = {c.target for c in tm.columns}
            if "base_qty" not in have:
                add.append(_cm("base_qty", base, "qty"))
            added += [f"lines.{x}" for x in fixed]
        if add:
            added += [f"{tm.target}.{a.target}" for a in add]
            tm = tm.model_copy(update={"columns": list(tm.columns) + add})
        out.append(tm)
    # no catalogue at all (the example's shop had none): the README's, when the lines carry its product code
    lines = next((tm for tm in out if tm.target == "lines"), None)
    if lines is not None and not any(tm.target == "products" for tm in out):
        lt, key = home(lines), plain_source(lines, "product_key")
        catalogue = _one(tables, lambda x: x.has("ma hang", "ten") and not x.has("ma don"))
        if lt is not None and key is not None and lt.phrases.get(key) == "ma hang" and catalogue is not None \
                and (k := catalogue.col("ma hang")) is not None and (n := catalogue.col("ten")) is not None:
            pc = [_cm("product_key", k), _cm("product_name", n)]
            pc += [_cm(t, c) for p, t in (("nhom hang", "product_group"), ("don vi co ban", "base_unit"))
                   if (c := catalogue.col(p)) is not None]
            pc += _drug_columns(catalogue, [x for x in tables if x is not catalogue], k, set())
            out.append(TableMap(target="products", sources=catalogue.ids, columns=pc))
            added += [f"products.{c.target}" for c in pc]
        elif key is not None and catalogue is not None and (k := catalogue.col("ma hang")) is not None \
                and (n := catalogue.col("ten")) is not None \
                and ((lt is not None and lt.phrases.get(key) in ("ten hang", "ten")) or n == key):
            # the lines carry the product NAME (public 06/11: a pharmacy whose drug list, keyed by SKU, says which
            # drugs need a prescription; 5 questions by prescription abstained): a catalogue keyed by that name,
            # with only what the drug list adds, read by the catalogue's own SKU (no base unit: quantities keep
            # the conversions they had)
            drugs = _drug_columns(catalogue, [x for x in tables if x is not catalogue], k, set())
            if drugs:
                pc = [_cm("product_key", n), _cm("product_name", n)] + drugs
                out.append(TableMap(target="products", sources=catalogue.ids, columns=pc))
                added += [f"products.{c.target}" for c in pc]
    # a catalogue keyed by product name with attributes of its own (public mẹ-và-bé shop, 06/11: "Hãng", "Số / Size:
    # số của sữa (theo tuổi) hoặc size (bỉm, núm ti)"; §6 "số sữa, size bỉm lấy theo cột Số / Size của danh mục")
    if lines is not None and not any(tm.target == "products" for tm in out):
        lt, key = home(lines), plain_source(lines, "product_key")
        cat = _one(tables, lambda x: (x.has("ten hang") or x.has("ten")) and (x.has("hang") or x.has("so cua sua"))
                   and not x.has("ma don") and not x.has("ma hang"))
        n = (cat.col("ten hang") or cat.col("ten")) if cat is not None else None
        if n is not None and key is not None and len(cat.ids) == 1 \
                and ((lt is not None and lt.phrases.get(key) in ("ten hang", "ten")) or n == key):
            pc = [_cm("product_key", n), _cm("product_name", n)]
            if (c := cat.col("hang")) is not None:
                pc.append(_cm("brand", c))
            if (c := cat.col("so cua sua")) is not None:
                pc += [_cm("stage", c), _cm("size", c)]
            if (c := cat.col("nhom hang")) is not None:
                pc.append(_cm("product_group", c))
            out.append(TableMap(target="products", sources=cat.ids, columns=pc))
            added += [f"products.{c.target}" for c in pc]
    # a member list with the day each member registered (public mẹ-và-bé shop, 06/11: "Ngày đăng ký: ngày đăng ký
    # thành viên"; §6 "khách thành viên mới trong tháng: số khách có Ngày đăng ký trong tháng đó")
    if not any(tm.target == "customers" for tm in out):
        members = _one(tables, lambda x: x.has("ngay dang ky thanh vien") and (x.has("ten khach") or x.has("ten")))
        if members is not None:
            name = members.col("ten khach") or members.col("ten")
            phone = members.col("so dien thoai")
            # keyed by the name, as the orders know their customers ("nối qua tên khách"); a phone key would link a
            # customer filter to no order at all
            mc = [_cm("customer_key", name), _cm("customer_name", name),
                  _cm("registered_date", members.col("ngay dang ky thanh vien"), "date")]
            if phone:
                mc.append(_cm("phone", phone))
            out.append(TableMap(target="customers", sources=members.ids, columns=mc))
            added.append("customers.registered_date")
    # still no product group: the lines' own, or a left-out catalogue's by product code or name
    if lines is not None and not any(c.target == "product_group" for tm in out for c in tm.columns):
        lt = home(lines)
        if group := _line_group(lt, [x for x in tables if x is not lt], plain_source(lines, "product_key"),
                                plain_source(lines, "product_name")):
            out = [tm.model_copy(update={"columns": list(tm.columns) + group}) if tm is lines else tm for tm in out]
            added.append("lines.product_group")
    if not added:
        return mapping
    return mapping.model_copy(update={"tables": out, "notes": list(mapping.notes) + ["bổ sung từ README: " + ", ".join(added)]})


UNKEYED = "?"  # N94: the product key of receipts borrowed without their products
SIDE_TABLES = {"purchases": ("product_key", "lines", 0.8), "inventory": ("product_key", "lines", 0.8),
               "deliveries": ("order_id", "orders", 0.95), "payments": ("order_id", "orders", 0.95)}


def with_side_tables(mapping: Mapping, raw: RawBusiness) -> Mapping:
    """N77. The side tables a mapping moved from an example lacks (its example's shop kept no receipts, stock or
    deliveries), taken from the mapping the README alone builds, when the README describes them (public 07/11: two
    shops moved from a one-file example lost their receipts and stock; 5 purchase questions abstained; train: a shop
    lost its deliveries, 9 questions). Only a table no table of the mapping already reads, and only when its keys are
    the mapping's own: most of its products are products the lines sell, most of its orders are orders the mapping
    has; else the two mappings name things differently and the table stays out. Stock dates are then settled as for
    any mapping (transfer._settle_constants: dated the last day only where the README says so)."""
    have = {tm.target for tm in mapping.tables}
    if not {"orders", "lines"} <= have or set(SIDE_TABLES) <= have:
        return mapping
    try:
        readme_mapping, _ = map_from_readme(raw)
    except Exception:
        return mapping
    if readme_mapping is None:
        return mapping
    used = {s for tm in mapping.tables for s in tm.sources}
    wanted = [tm for tm in readme_mapping.tables
              if tm.target in SIDE_TABLES and tm.target not in have and not set(tm.sources) & used]
    catalogue = None if "products" in have else _catalogue_by_name(raw, used)
    if not wanted and catalogue is None:
        return mapping
    core = [tm for tm in mapping.tables if tm.target in ("orders", "lines")]
    borrowed = []
    if catalogue is not None and _keys_match(catalogue, core, mapping, raw, "product_key", "lines", REKEY_SHARE):
        borrowed.append(catalogue)
    for tm in wanted:
        key, home, share = SIDE_TABLES[tm.target]
        if _keys_match(tm, core, mapping, raw, key, home, share):
            borrowed.append(tm)
        elif key == "product_key" and (named := _keyed_by_name(tm, raw)) is not None \
                and _keys_match(named, core, mapping, raw, key, home, REKEY_SHARE):
            borrowed.append(named)
        elif key == "product_key" and (rekeyed := _rekey_products(tm, mapping, readme_mapping)) is not None \
                and _keys_match(rekeyed, core, mapping, raw, key, home, REKEY_SHARE):
            borrowed.append(rekeyed)
        elif tm.target == "purchases" and not have & {"inventory", "lots"}:
            # N94: receipts whose product codes cannot be told in the lines' names (public 08/11: sales lines in two
            # files, no code beside the name in either) still give the money, receipts and suppliers of a period;
            # with no product key every question by product finds no receipt and abstains. Not beside stock or lots,
            # whose figures read the receipts of each product.
            cols = [c for c in tm.columns if c.target != "product_key"] + [ColumnMap(target="product_key",
                                                                                     const=UNKEYED)]
            borrowed.append(tm.model_copy(update={"columns": cols}))
    # a borrowed table must not break the mapping (public 07/11: a stock list with 1 blank cell of 61 failed the
    # required-cells check and every question of the shop abstained): each one kept only if no check newly fails
    before = _failed_checks(T._settle_constants(mapping, raw), raw)
    kept = [tm for tm in borrowed if before is not None and _failed_checks(T._settle_constants(
        mapping.model_copy(update={"tables": list(mapping.tables) + [tm]}), raw), raw) == before]
    if not kept:
        return mapping
    out = mapping.model_copy(update={"tables": list(mapping.tables) + kept, "notes": list(mapping.notes) + [
        "bảng phụ từ README: " + ", ".join(tm.target for tm in kept)]})
    return T._settle_constants(out, raw)


_NAME_PHRASES = ("ten hang", "ten")


def _keyed_by_name(tm: TableMap, raw: RawBusiness) -> TableMap | None:
    """N107. A side table the README keys by the product code that writes the product's name too, where the mapping
    keys the lines by the name (two public shops: stock list "Mã SKU: mã hàng" beside "Hàng bán: tên hàng",
    receipts "Mã vạch" beside "Tên mặt hàng", sales lines read by "Mặt hàng: tên hàng"): keyed by its own name column,
    which the run merges with the lines' spellings of that name (build.unify_keys). The caller keeps it only when
    nearly every name is a product the lines sell (REKEY_SHARE)."""
    t = _one([_Table(ids, phrases_of(raw, ids)) for ids in groups(raw)], lambda x: set(x.ids) == set(tm.sources))
    key = next((c for c in tm.columns if c.target == "product_key"), None)
    name = t.first(_NAME_PHRASES) if t is not None else None
    if name is None or key is None or key.source == name:
        return None
    cols = [c.model_copy(update={"source": name, "transform": None, "args": {}}) if c.target == "product_key" else c
            for c in tm.columns]
    return tm.model_copy(update={"columns": cols})


def _catalogue_by_name(raw: RawBusiness, used: set[str]) -> TableMap | None:
    """N107. The README's catalogue as the products, keyed by the product's name, for a mapping without one (two
    public restaurants: "danh mục hàng kèm tồn kho" with "ĐVT: đơn vị cơ bản", "Giá vốn: giá vốn", "Tồn cuối"; "hôm
    qua bán được mấy lon" and "hàng còn dư trong kho tính theo giá vốn" abstained). Only a list of products (a name, no
    order code) with their cost or stock; the caller keeps it only when nearly every name is a product the lines
    sell."""
    tables = [t for t in (_Table(ids, phrases_of(raw, ids)) for ids in groups(raw)) if not set(t.ids) & used]
    # a list of every product with its cost or stock, not the conversion list ("Tên sản phẩm: tên hàng (file chỉ có
    # mặt hàng có đơn vị lớn)", "Đơn vị cơ bản" beside the factor: train pharmacies, 34 questions lost when it was
    # read as the catalogue)
    cat = _one(tables, lambda t: t.first(_NAME_PHRASES) is not None and not t.has("ma don")
               and (t.has("gia von") or t.has("ton kho")) and not t.has("ngay nhap")
               and not any(p.startswith(("he so", "ty le quy doi", "ti le quy doi", "don vi lon", "don vi quy doi"))
                           for p in t.by_phrase))
    if cat is None:
        return None
    name = cat.first(_NAME_PHRASES)
    cols = [_cm("product_key", name), _cm("product_name", name)]
    cols += [_cm(target, c, parse) for phrase, target, parse in (
        ("nhom hang", "product_group", "text"), ("don vi co ban", "base_unit", "text"), ("gia von", "unit_cost", "money"))
        if (c := cat.col(phrase)) is not None]
    return TableMap(target="products", sources=cat.ids, columns=cols)


def _failed_checks(mapping: Mapping, raw: RawBusiness) -> set[str] | None:
    """Names of the checks the mapping fails (build.run_checks); None when it cannot be built."""
    try:
        return {c.name for c in T.run_checks(build_canonical(raw, mapping), raw.readme) if not c.passed}
    except Exception:
        return None


REKEY_SHARE = 0.98  # a product key translated through the sales file must name the lines' products almost all


def _keys_match(tm: TableMap, core: list[TableMap], mapping: Mapping, raw: RawBusiness, key: str, home: str,
                share: float) -> bool:
    """Built together with the mapping's orders and lines, as the run builds them (the spellings of one name are merged
    across tables there), the share of the table's keys that are keys of `home` is at least `share`."""
    try:
        db = build_canonical(raw, Mapping(record_grain=mapping.record_grain, tables=core + [tm]))
    except Exception:
        return False
    new, ref = db.table(tm.target), db.table(home)
    if new is None or ref is None or new.empty or key not in new.columns or key not in ref.columns:
        return False
    if new[key].isna().mean() > 1 - share:
        return False
    values, known = set(new[key].dropna().astype(str)), set(ref[key].dropna().astype(str))
    return bool(values) and len(values & known) / len(values) >= share


def _rekey_products(tm: TableMap, mapping: Mapping, readme_mapping: Mapping) -> TableMap | None:
    """The side table keyed by the product code where the mapping keys its lines by the product name (public 07/11:
    receipts by "SP0001", sales lines by "7Up lon"): the code translated into the name through the one sales file both
    mappings read, where each row carries both. Kept only when that translation names the lines' own products for
    nearly every code (REKEY_SHARE, checked by the caller): a wrong key would put receipts on the wrong product."""
    def plain(m: Mapping, target: str) -> tuple[list[str], str | None]:
        lt = next((t for t in m.tables if t.target == "lines"), None)
        c = next((c for c in lt.columns if c.target == target), None) if lt is not None else None
        return (list(lt.sources) if lt is not None else []), (c.source if c is not None and c.transform is None else None)
    r_src, code = plain(readme_mapping, "product_key")
    m_src, name = plain(mapping, "product_key")
    if len(r_src) != 1 or r_src != m_src or not code or not name or code == name:
        return None
    cols = [c.model_copy(update={"transform": "lookup", "args": {"table": r_src[0], "key": code, "value": name,
                                                                 "keep_missing": False, "fold": True}})
            if c.target == "product_key" else c for c in tm.columns]
    return tm.model_copy(update={"columns": cols})


ORDER_MOMENT = "thoi diem dat don"  # "Giờ bán: thời điểm đặt đơn (ngày giờ)"


def with_order_hour(mapping: Mapping, raw: RawBusiness) -> Mapping:
    """N73. The order's time from the column the README calls "thời điểm đặt đơn", when the mapping reads the order's
    day from another column and so has no hour (public 07/11: two shops moved from a one-file example read "Ngày giao
    dịch: ngày bán" / "Ngày xuất: ngày bán" beside "Giờ bán: thời điểm đặt đơn (ngày giờ)"; 9 questions by shift
    abstained, §2 "ca sáng, ca chiều theo giờ tạo đơn"). Only when every order keeps its day, so no figure by day
    changes: the column must read as a date and time on every order, with some hour not midnight."""
    orders = next((tm for tm in mapping.tables if tm.target == "orders"), None)
    if orders is None:
        return mapping
    has = next((c for c in orders.columns if c.target == "has_time"), None)
    now = next((c for c in orders.columns if c.target == "order_time"), None)
    if has is None or has.const is not False or now is None or now.transform is not None or not now.source:
        return mapping
    t = _one([x for x in (_Table(ids, phrases_of(raw, ids)) for ids in groups(raw)) if x.phrases],
             lambda x: bool(set(x.ids) & set(orders.sources)))
    moment = t.col(ORDER_MOMENT) if t is not None else None
    if moment is None or moment == now.source:
        return mapping
    cols = [c.model_copy(update={"source": moment, "parse": "datetime"}) if c is now else
            c.model_copy(update={"const": True}) if c is has else c for c in orders.columns]
    timed = orders.model_copy(update={"columns": cols})
    try:
        a = build_canonical(raw, Mapping(record_grain=mapping.record_grain, tables=[orders])).table("orders")
        b = build_canonical(raw, Mapping(record_grain=mapping.record_grain, tables=[timed])).table("orders")
    except Exception:
        return mapping
    if a is None or b is None or len(a) != len(b) or a["order_time"].isna().any() or b["order_time"].isna().any():
        return mapping
    days = a.set_index("order_id")["order_time"].dt.normalize()
    new = b.set_index("order_id")["order_time"]
    if not days.index.is_unique or not new.index.is_unique or set(days.index) != set(new.index):
        return mapping
    if not (new.dt.normalize().reindex(days.index) == days).all() or not (new.dt.normalize() != new).any():
        return mapping
    tables = [timed if tm is orders else tm for tm in mapping.tables]
    return mapping.model_copy(update={"tables": tables,
                                      "notes": list(mapping.notes) + ["bổ sung từ README: orders.order_time có giờ"]})


AMOUNT_SHARE = 0.9  # share of a payment-method column's values that read as money amounts: it holds no method


def drop_amount_as_method(mapping: Mapping, raw: RawBusiness) -> Mapping:
    """A payment-method column whose cells are amounts ("20.100.000đ", "19300k": a public phone ledger's "Khách trả",
    taken for the method by a mapping moved from an example, 06/11) names no method: dropped, so the debt figures do
    not read every order as an unknown method."""
    from datamate.loader.parse import parse_money
    out = []
    for tm in mapping.tables:
        src = next((c.source for c in tm.columns if c.target == "payment_method" and c.transform is None), None)
        if tm.target == "orders" and src:
            values = [v for f in _frames_of(raw, tm) if src in f.columns for v in f[src].dropna().astype(str)
                      if v.strip()]
            if values and sum(parse_money(v) is not None for v in values) >= AMOUNT_SHARE * len(values):
                tm = tm.model_copy(update={"columns": [c for c in tm.columns if c.target != "payment_method"]})
        out.append(tm)
    return mapping.model_copy(update={"tables": out}) if out != list(mapping.tables) else mapping


def _line_group(lines: _Table | None, others: list[_Table], key: str | None, name: str | None) -> list[ColumnMap]:
    """The product group of a shop whose mapping has none (public, 06/11: four shops whose README names "nhóm hàng",
    30 questions by group abstained): the lines' own "nhóm hàng" column, else the group of a catalogue the mapping
    left out, read by the lines' product code, or by the product name when the shop keeps no codes ("nối qua tên
    hàng"), names compared however written (§8)."""
    if lines is not None and (c := lines.col("nhom hang")) is not None:
        return [_cm("product_group", c)]
    catalogue = _one(others, lambda x: x.has("nhom hang") and not x.has("ma don"))
    if catalogue is None or len(catalogue.ids) != 1:
        return []
    said = lines.phrases if lines is not None else {}
    for source, phrase, fold in ((key, "ma hang", False), (name, "ten hang", True), (key, "ten hang", True)):
        if source is not None and said.get(source) == phrase and catalogue.col(phrase) is not None:
            looked = _lookup("product_group", source, catalogue, phrase, "nhom hang")
            if looked is not None:
                return [looked.model_copy(update={"args": {**looked.args, "fold": fold}})]
    # the lines' file has no README section: a catalogue column of the very same header that the README calls the
    # product's code or name
    for source in dict.fromkeys(s for s in (key, name) if s is not None):
        phrase = catalogue.phrases.get(source)
        if phrase in ("ma hang", "ten hang", "ten") and catalogue.col(phrase) == source:
            looked = _lookup("product_group", source, catalogue, phrase, "nhom hang")
            if looked is not None:
                return [looked.model_copy(update={"args": {**looked.args, "fold": phrase != "ma hang"}})]
    return []


# N35: the conventions of a README name the columns of debts and cost in a fixed form (train, 05/11: 7 READMEs with
# a payment ledger, 4 with the cost of a sale), whether or not the README describes each column:
#   "**Công nợ**: mỗi lần khách trả tiền cho một đơn là một dòng, **Giá trị** là số tiền trả lần đó; **Tổng sau giảm
#   giá** là số khách phải trả cho cả đơn."   "**Giá vốn**: **Giá vốn** là giá vốn một đơn vị bán."
# (a database writes `thanh_toan.SoTienThu`). A mapping moved from an example without them had none: two train shops
# moved from a pharmacy export lost every debt and gross-profit question (44 questions, 05/11).
CONVENTIONS = (("so tien tra lan do", "paid_amount"), ("so khach phai tra cho ca don", "total_due"),
               ("gia von mot don vi ban", "line_cost"),
               # a public phone ledger (06/11): "**Khách trả** là số tiền khách trả cho cả đơn (không phải của dòng)"
               ("so tien khach tra cho ca don", "total_due"))
_NAMED = re.compile(r"(?:\*\*([^*]+)\*\*|`(?:[^`.]+\.)?([^`]+)`) là ([^;]+)")
PAYMENT_WORDS_MIN = 0.9  # share of a column's distinct values read as payment methods (cash, transfer, debt, cod…)
ORDER_IDS_MIN = 0.95  # share of a payment table's order ids found among the orders


def conventions(readme: str) -> dict[str, str]:
    """Role (paid_amount, total_due, line_cost) -> the column the README's conventions name for it; a role named
    twice with two columns has none."""
    seen: dict[str, set[str]] = {}
    for line in readme.splitlines():
        if not line.lstrip().startswith("- **"):
            continue
        for m in _NAMED.finditer(line):
            meaning = T._fold(m.group(3))
            for phrase, role in CONVENTIONS:
                if meaning.startswith(phrase):
                    seen.setdefault(role, set()).add((m.group(1) or m.group(2)).strip())
    return {role: names.pop() for role, names in seen.items() if len(names) == 1}


def _frames_of(raw: RawBusiness, tm: TableMap) -> list[pd.DataFrame]:
    from .build import source_ids
    ids = set(source_ids(tm, [t.table_id for t in raw.tables]))
    return [t.frame for t in raw.tables if t.table_id in ids]


def _payment_column(frames: list[pd.DataFrame], exclude: set[str] = frozenset()) -> str | None:
    """The one column whose values are payment methods ("Tiền mặt", "Ghi nợ", "Thu hộ (COD)"…), read with the
    linking vocabulary; none, or two: None."""
    from datamate.nlu import linking
    found = []
    for c in dict.fromkeys(str(c) for f in frames for c in f.columns):
        if c in exclude:
            continue
        values = {str(v).strip() for f in frames if c in f.columns for v in f[c].dropna().unique()[:200]} - {""}
        read = {v: linking.concept("payment_method", v) for v in values}
        if values and sum(x is not None for x in read.values()) >= PAYMENT_WORDS_MIN * len(values) \
                and len({x for x in read.values() if x}) >= 2:
            found.append(c)
    return found[0] if len(found) == 1 else None


def with_conventions(mapping: Mapping, raw: RawBusiness) -> Mapping:
    """What the README's conventions name, where the mapping has none: the amount due of an order, the cost of a sale
    on the lines, and the payments (the table holding the README's paid amount, with one column of order ids all
    found among the orders' and one date column). Debts also need the payment method of the orders: the one orders
    column whose values read as payment methods."""
    named = conventions(raw.readme)
    tables = {tm.target: tm for tm in mapping.tables}
    orders, lines = tables.get("orders"), tables.get("lines")
    if not named or orders is None:
        return mapping
    added: dict[str, list[ColumnMap]] = {}
    o_frames = _frames_of(raw, orders)
    o_cols = {str(c) for f in o_frames for c in f.columns}
    have = {c.target for c in orders.columns}
    line_level = {c.source for c in (lines.columns if lines is not None else []) if c.target == "line_amount"}
    due = next((c for c in orders.columns if c.target == "total_due"), None)
    if due is not None and due.source != named.get("total_due") and named.get("total_due") in o_cols - line_level:
        # the order's amount due read from another column while the README names the order's own: the README's (a
        # public phone ledger moved from an example, 06/11: the lines' amount column; N111, train 10/11: a POS moved
        # from an example by meaning read the goods total "TongTienHang" beside the README's "don_hang.TongThanhToan",
        # after discount and shipping, and every order paid in full looked owing: 14 debt questions blank)
        orders = orders.model_copy(update={"columns": [c for c in orders.columns if c.target != "total_due"]})
        mapping = mapping.model_copy(update={"tables": [orders if tm.target == "orders" else tm for tm in mapping.tables]})
        have.discard("total_due")
    if "total_due" not in have and named.get("total_due") in o_cols:
        added.setdefault("orders", []).append(_cm("total_due", named["total_due"], "money"))
    if "payment_method" not in have and "paid_amount" in named:
        used = {s for c in orders.columns for s in [c.source, *c.sources] if s}
        if (c := _payment_column(o_frames, used)) is not None:
            added.setdefault("orders", []).append(_cm("payment_method", c))
    if lines is not None and "unit_cost" not in {c.target for c in lines.columns} \
            and named.get("line_cost") in {str(c) for f in _frames_of(raw, lines) for c in f.columns}:
        added.setdefault("lines", []).append(_cm("unit_cost", named["line_cost"], "money"))
    out = [tm.model_copy(update={"columns": list(tm.columns) + added[tm.target]}) if tm.target in added else tm
           for tm in mapping.tables]
    notes = [f"{t}.{c.target}" for t, cs in added.items() for c in cs]
    if "payments" not in tables and (pay := _payments_table(raw, orders, named.get("paid_amount"))) is not None:
        out.append(pay)
        notes.append("payments")
    if not notes:
        return mapping
    return mapping.model_copy(update={"tables": out, "notes": list(mapping.notes) + [
        "bổ sung từ quy ước README: " + ", ".join(notes)]})


def _payments_table(raw: RawBusiness, orders: TableMap, amount: str | None) -> TableMap | None:
    from .build import source_ids
    if amount is None:
        return None
    oid = next((c.source for c in orders.columns if c.target == "order_id" and c.transform is None), None)
    o_ids = set(source_ids(orders, [t.table_id for t in raw.tables]))
    if oid is None:
        return None
    known = {str(v).strip() for t in raw.tables if t.table_id in o_ids and oid in t.frame.columns
             for v in t.frame[oid].dropna()}
    holders = [t for t in raw.tables if t.table_id not in o_ids and amount in map(str, t.frame.columns)]
    layouts = {tuple(sorted(map(str, t.frame.columns))) for t in holders}
    if not holders or len(layouts) != 1 or not known:
        return None  # no table, or two layouts naming the amount: no guess
    frames = [t.frame for t in holders]
    ids_cols, dates = [], []
    for c in (str(c) for c in frames[0].columns if str(c) != amount):
        values = [str(v).strip() for f in frames for v in f[c].dropna()]
        if values and sum(v in known for v in values) >= ORDER_IDS_MIN * len(values):
            ids_cols.append(c)
        elif T._dates(frames, c):
            dates.append(c)
    if len(ids_cols) != 1 or len(dates) != 1:
        return None
    columns = [_cm("order_id", ids_cols[0]), _cm("paid_time", dates[0], "datetime"), _cm("amount", amount, "money")]
    if (m := _payment_column(frames, {ids_cols[0], dates[0], amount})) is not None:
        columns.append(_cm("method", m))
    return TableMap(target="payments", sources=[t.table_id for t in holders], columns=columns)


def _drug_columns(catalogue: _Table, others: list[_Table], key: str | None, have: set[str]) -> list[ColumnMap]:
    """§6 pharmacy attributes of the catalogue: its own columns, else looked up in a drug list by the product code the
    catalogue is keyed by."""
    drugs = _one(others, lambda x: x.has("ma hang") and not x.has("ma don")
                 and any(x.has(p) for p, _, _ in DRUG_ATTRIBUTES))
    out = []
    for phrase, target, parse in DRUG_ATTRIBUTES:
        if target in have:
            continue
        if (c := catalogue.col(phrase)) is not None:
            out.append(_cm(target, c, parse))
        elif key is not None and key == catalogue.col("ma hang") and \
                (looked := _lookup(target, key, drugs, "ma hang", phrase)) is not None:
            out.append(looked.model_copy(update={"parse": parse}))
    return out


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
