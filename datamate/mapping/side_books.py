"""Side ledgers a shop keeps beside its sales ledger, recognised by the columns its README names in its conventions
(public phone shop, 06/11: "sổ thu máy cũ một file; sổ nợ, sổ góp, sổ bảo hành chung một file, mỗi sổ một sheet. Các
sổ nối với nhau qua số thứ tự đơn trong sổ bán, IMEI…"). Each book is read only when exactly its columns are there,
and only where the canonical tables lack what it gives:
- trade-in book ("Giá thu" … "Trừ vào (STT sổ bán)"): orders.trade_in_amount, the sum taken off each order;
- warranty book ("Ngày nhận", "IMEI", "Máy"): warranty_visits, one row a visit, its order found by the IMEI the sales
  ledger writes for the phone sold (§6 Cửa hàng điện thoại "Bảo hành").
"""
from __future__ import annotations

import re

import pandas as pd

from datamate.contracts import CanonicalDB, Mapping, RawBusiness
from datamate.loader.parse import parse_datetime, parse_money

from .build import _fold, source_ids

TRADE_IN = ("gia thu", "tru vao stt so ban")
WARRANTY = ("ngay nhan", "imei", "may")


def _cols(frame: pd.DataFrame) -> dict[str, str]:
    """Column names folded to words: "Trừ vào (STT sổ bán)" is "tru vao stt so ban"."""
    return {" ".join(re.findall(r"[a-z0-9]+", _fold(str(c)))): str(c) for c in frame.columns}


def _book(raw: RawBusiness, needed: tuple[str, ...]) -> list[tuple[pd.DataFrame, dict[str, str]]]:
    out = []
    for t in raw.tables:
        cols = _cols(t.frame)
        if all(n in cols for n in needed):
            out.append((t.frame, cols))
    return out


def _order_key(v) -> str | None:
    """An order number as the orders hold it ("33", "33.0", " 33 " → "33")."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    m = re.fullmatch(r"(\d+)(?:\.0+)?", s)
    return m[1] if m else (s or None)


def trade_ins(db: CanonicalDB, raw: RawBusiness) -> None:
    """§6 "Thu máy cũ": each phone taken back is written once, its price taken off the order it names."""
    o = db.tables.get("orders")
    books = _book(raw, TRADE_IN)
    if o is None or len(books) != 1 or ("trade_in_amount" in o.columns and o["trade_in_amount"].notna().any()):
        return
    frame, cols = books[0]
    amount = frame[cols["gia thu"]].map(parse_money)
    order = frame[cols["tru vao stt so ban"]].map(_order_key)
    per = pd.Series(amount.values, index=order.values).dropna().groupby(level=0).sum()
    ids = o["order_id"].map(_order_key)
    if per.empty or not set(per.index) <= set(ids):
        return  # a trade-in naming an order the sales ledger does not have: the book is not read as it says
    db.tables["orders"] = o.assign(trade_in_amount=ids.map(per))
    db.warnings.append(f"orders.trade_in_amount: {len(per)} đơn có thu máy cũ (sổ thu máy cũ)")


def warranty_visits(db: CanonicalDB, raw: RawBusiness, mapping: Mapping) -> None:
    """One row a visit ("mỗi lần khách mang máy tới bảo hành một dòng (Ngày nhận), máy nhận theo IMEI; Máy ghi dòng
    máy"). The order of the phone: the sales row writing that IMEI (two phones of a row written "a / b")."""
    books = _book(raw, WARRANTY)
    if len(books) != 1 or "warranty_visits" in db.tables:
        return
    frame, cols = books[0]
    lines = next((tm for tm in mapping.tables if tm.target == "lines"), None)
    oid = next((c.source for c in lines.columns if c.target == "order_id"), None) if lines is not None else None
    by_imei: dict[str, str] = {}
    if oid is not None:
        for t in raw.tables:
            if t.table_id in set(source_ids(lines, [x.table_id for x in raw.tables])):
                c = _cols(t.frame)
                if "imei" in c and oid in t.frame.columns:
                    for cell, order in zip(t.frame[c["imei"]], t.frame[oid]):
                        for imei in re.split(r"\s*/\s*", str(cell)):
                            if imei.strip() and imei.strip().lower() != "nan":
                                by_imei[imei.strip()] = _order_key(order)
    visits = pd.DataFrame({
        "visit_time": frame[cols["ngay nhan"]].map(parse_datetime),
        "product_line": frame[cols["may"]].astype(str).str.strip(),
        "imei": frame[cols["imei"]].astype(str).str.strip(),
    })
    visits["order_id"] = visits["imei"].map(by_imei)
    visits = visits.dropna(subset=["visit_time"])
    if visits.empty:
        return
    db.tables["warranty_visits"] = visits.assign(visit_time=pd.to_datetime(visits["visit_time"]))
    db.warnings.append(f"warranty_visits: {len(visits)} lượt bảo hành (sổ bảo hành)")


DEBT = ("no", "da tra", "ngay tra", "ghi chu")
INSTALLMENT = ("tra truoc", "so ky", "gop thang", "han gop ngay", "ngay gop", "da gop")
DEBT_METHOD, INSTALLMENT_METHOD = "Ghi nợ", "Trả góp"  # read by the payment synonyms as debt / installment


def _money(v) -> float | None:
    if isinstance(v, str):
        return parse_money(v) if v.strip() else None
    return None if v is None or pd.isna(v) else float(v)


def _day(v):
    d = parse_datetime(v) if v is not None and str(v).strip() else None
    return pd.Timestamp(d) if d is not None else None


def _add_months(day, k: int, on: int):
    y, m = divmod(day.month - 1 + k, 12)
    first = pd.Timestamp(day.year + y, m + 1, 1)
    return first + pd.Timedelta(days=min(on, first.days_in_month) - 1)


def debts(db: CanonicalDB, raw: RawBusiness) -> None:
    """The debt book and the installment book of a public phone shop (06/11, README: "Sổ nợ: chỉ đơn khách còn nợ sau
    lúc mua, trừ đơn trả góp. Dòng đầu mỗi đơn ghi ngày mua, khách, Nợ là số còn nợ sau khi trả lúc mua. Các lần khách
    trả sau đó ghi ở Đã trả, Ngày trả … Ghi chú ghi số thứ tự đơn" and "Sổ góp: … Giá là tiền cả đơn, Trả trước là tiền
    trả lúc mua, còn lại chia đều Số kỳ kỳ, mỗi kỳ Góp/tháng. Kỳ thứ nhất có hạn vào ngày Hạn góp của tháng ngay sau
    tháng mua … Mỗi lần khách góp ghi Ngày góp, Đã góp"), as §4 reads debts (§6 "đơn trả góp là đơn ghi nợ"):
    - orders.payment_method: debt or installment for the orders of the books;
    - payments: what was paid at purchase (the order total less the debt left, or the down payment), every later
      payment, and for every other order its whole total at purchase (it owes nothing);
    - installments: the schedule, period k due on the given day of the k-th month after the purchase.
    Read only when both books are there with an order named on every row, all named orders being sales orders."""
    o = db.tables.get("orders")
    dbk, ibk = _book(raw, DEBT), _book(raw, INSTALLMENT)
    if o is None or len(dbk) != 1 or len(ibk) != 1 or "total_due" not in o.columns or "payments" in db.tables:
        return
    ids = o["order_id"].map(_order_key)
    total = pd.Series(o["total_due"].values, index=ids.values)
    day = pd.Series(o["order_time"].values, index=ids.values)
    pays, method, schedule = [], {}, []
    f, c = dbk[0]
    stt = f[c["ghi chu"]].astype(str).str.extract(r"STT\s*(\d+)", expand=False)
    for key, rows in f.assign(_o=stt).dropna(subset=["_o"]).groupby("_o", sort=False):
        left = _money(rows[c["no"]].iloc[0])
        if key not in total.index or left is None or pd.isna(total[key]):
            return
        method[key] = DEBT_METHOD
        pays.append((key, day[key], float(total[key]) - left, "at_purchase"))
        pays += [(key, d, a, "debt_payment") for d, a in zip(rows[c["ngay tra"]].map(_day), rows[c["da tra"]].map(_money))
                 if d is not None and a]
    f, c = ibk[0]
    stt = f[c["stt"]].map(_order_key) if "stt" in c else None
    if stt is None:
        return
    for key, rows in f.assign(_o=stt).dropna(subset=["_o"]).groupby("_o", sort=False):
        first = rows.iloc[0]
        down, n, each, on = (_money(first[c["tra truoc"]]), _money(first[c["so ky"]]), _money(first[c["gop thang"]]),
                             _money(first[c["han gop ngay"]]))
        if key not in total.index or None in (down, n, each, on):
            return
        method[key] = INSTALLMENT_METHOD
        pays.append((key, day[key], down, "at_purchase"))
        pays += [(key, d, a, "installment") for d, a in zip(rows[c["ngay gop"]].map(_day), rows[c["da gop"]].map(_money))
                 if d is not None and a]
        schedule += [(key, k, _add_months(pd.Timestamp(day[key]), k, int(on)).date(), each) for k in range(1, int(n) + 1)]
    for key in total.index:
        if key not in method and pd.notna(total[key]):
            pays.append((key, day[key], float(total[key]), "at_purchase"))
    db.tables["orders"] = o.assign(payment_method=ids.map(method))
    db.tables["payments"] = pd.DataFrame(pays, columns=["order_id", "paid_time", "amount", "kind"]).assign(
        paid_time=lambda p: pd.to_datetime(p["paid_time"]))
    db.tables["installments"] = pd.DataFrame(schedule, columns=["order_id", "period_no", "due_date", "amount_due"])
    db.warnings.append(f"payments: sổ nợ {sum(v == DEBT_METHOD for v in method.values())} đơn, "
                       f"sổ góp {sum(v == INSTALLMENT_METHOD for v in method.values())} đơn")


_PHONE = re.compile(r"(0\d(?:[\s.]?\d){8,9})")
WALK_IN = {"le", "khach le", "kl", "khach vang lai", ""}


def customers(db: CanonicalDB, raw: RawBusiness, mapping: Mapping) -> None:
    """A sales ledger writing the customer as a name with a phone number, however spelt ("Triệu Linh An 0327988481",
    "Triệu Linh An - 0327 988 481", "Châu Hằng Hùng (0932225622)"; "lẻ" for a walk-in): the customer is the phone
    number (§3: a shop with no customer code knows the customer by what the order writes; two spellings of one name
    are one customer, and the number is how the shop tells them apart), the name the words before it. Only for orders
    with no customer of their own, and only when most named customers carry a number."""
    o = db.tables.get("orders")
    lines = next((tm for tm in mapping.tables if tm.target == "lines"), None)
    oid = next((c.source for c in lines.columns if c.target == "order_id"), None) if lines is not None else None
    if o is None or oid is None or ("customer_key" in o.columns and o["customer_key"].notna().any()):
        return
    cells: dict[str, str] = {}
    for t in raw.tables:
        if t.table_id in set(source_ids(lines, [x.table_id for x in raw.tables])):
            c = _cols(t.frame)
            if "khach" in c and oid in t.frame.columns:
                for cell, order in zip(t.frame[c["khach"]], t.frame[oid]):
                    k = _order_key(order)
                    if k and k not in cells and isinstance(cell, str) and cell.strip():
                        cells[k] = cell
    named = {k: v for k, v in cells.items() if _fold(v).strip() not in WALK_IN}
    if not named or sum(bool(_PHONE.search(v)) for v in named.values()) < 0.8 * len(named):
        return
    keys, names = {}, {}
    for k, v in named.items():
        m = _PHONE.search(v)
        if m:
            keys[k] = re.sub(r"\D", "", m[1])
            names[k] = re.sub(r"[\s\-–(),:]+$", "", v[:m.start()]).strip(" -–(")
    ids = o["order_id"].map(_order_key)
    db.tables["orders"] = o.assign(customer_key=ids.map(keys), customer_name=ids.map(names))


def side_books(db: CanonicalDB, raw: RawBusiness, mapping: Mapping) -> None:
    """Each book on its own: a book that cannot be read leaves its tables out (a warning), never the shop."""
    for step in (lambda: customers(db, raw, mapping), lambda: trade_ins(db, raw),
                 lambda: warranty_visits(db, raw, mapping), lambda: debts(db, raw)):
        try:
            step()
        except Exception as e:  # noqa: BLE001  a side book is optional; the sales ledger must still answer
            db.warnings.append(f"sổ phụ không đọc được: {type(e).__name__}: {str(e)[:80]}")
