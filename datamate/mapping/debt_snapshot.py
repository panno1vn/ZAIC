"""N100: debts a shop records only as the state at the end of its data (README: "… tính đến hết ngày cuối dữ liệu").

The mapping reads that state as orders.debt_left (an amount column), or as orders.note (words: "khách đưa trước 87k,
còn thiếu 73 nghìn"), which this step reads into debt_left. The day it holds is the README's last day of data; the
debt functions answer on that day only (metrics/debt.open_orders), and never "paid / added in a period": the payments
themselves are not recorded.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

import pandas as pd

from datamate.contracts import CanonicalDB, RawBusiness

_LAST_DAY = re.compile(r"dữ liệu có đến hết (?:ngày )?(\d{1,2})/(\d{1,2})/(\d{4})")
_NOTE_SENTENCE = "là tình trạng của đơn tính đến hết ngày cuối dữ liệu"
_AMOUNT = r"(\d[\d.,]*\s*(?:k|nghìn|ngàn|tr|triệu|đ|đồng|d)?)"
_OWED = re.compile(rf"(?:còn thiếu|thiếu lại|thiếu|ghi nợ|ghi sổ|nợ)\s*{_AMOUNT}")
_PAID = re.compile(rf"(?:đưa trước|trả trước|đưa|trả|ck|chuyển khoản)\s*{_AMOUNT}")
_SETTLED = re.compile(r"đủ|trả hết|hết rồi|xong")
_OPEN = re.compile(r"còn|thiếu|chưa")


def amount(text: str) -> float | None:
    """"73 nghìn", "79k", "449.500đ", "1tr219" as đồng; None when unread."""
    from datamate.loader.parse import parse_money
    t = text.strip().lower()
    t = re.sub(r"\s*(?:nghìn|ngàn)$", "k", t)
    t = re.sub(r"\s*(?:triệu)$", "tr", t)
    t = re.sub(r"\s+", "", t)
    v = parse_money(t)
    return None if v is None else float(v)


def owed_from_note(note, total: float | None) -> float | None:
    """What a debt order still owes at the end of the data, read from its note; None when the words are not read
    (an unread note makes the shop's debts unknown, never a guess)."""
    n = unicodedata.normalize("NFC", str(note or "")).lower().strip()
    if not n or n == "nan":
        return None  # a debt order with no word on it: unknown, not settled
    if _SETTLED.search(n) and not _OPEN.search(n):
        return 0.0
    if "nợ cả đơn" in n or "chưa trả gì" in n:
        return total
    owed = [amount(m.group(1)) for m in _OWED.finditer(n)]
    owed = [v for v in owed if v]
    paid = [amount(m.group(1)) for m in _PAID.finditer(n)]
    paid = [v for v in paid if v]
    if owed:
        left = owed[-1]
        if paid and total is not None and abs(paid[0] + left - total) > 1:
            return None  # "trả X, nợ Y" that does not add up to the order: not read
        return left if total is None or left <= total + 1 else None
    if paid and "còn lại" in n and total is not None:  # "đưa trước 236k, còn lại ghi sổ"
        return max(total - paid[0], 0.0)
    return None


def last_day(readme: str) -> date | None:
    m = _LAST_DAY.search(unicodedata.normalize("NFC", readme or "").lower())
    if m is None:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def debt_snapshot(db: CanonicalDB, raw: RawBusiness) -> None:
    """Set db.debt_snapshot_day when the orders hold the end-of-data debt, reading notes into debt_left first."""
    orders = db.tables.get("orders")
    if orders is None or db.tables.get("payments") is not None:
        return
    readme = unicodedata.normalize("NFC", raw.readme or "")
    if "debt_left" not in orders.columns and "note" in orders.columns and _NOTE_SENTENCE in readme \
            and "payment_method" in orders.columns:
        from datamate.metrics.debt import DEBT_CODES
        from datamate.nlu import linking
        codes = orders["payment_method"].astype(str).map(lambda v: linking.concept("payment_method", v))
        debt = codes.isin(DEBT_CODES) & orders.get("status", pd.Series("", index=orders.index)).ne("cancelled")
        total = orders["total_due"] if "total_due" in orders.columns else pd.Series(None, index=orders.index)
        left = pd.Series(0.0, index=orders.index)
        for i in orders.index[debt]:
            v = owed_from_note(orders.at[i, "note"], None if pd.isna(total.at[i]) else float(total.at[i]))
            if v is None:
                db.warnings.append(f"orders.note: ghi chú nợ không đọc được ({orders.at[i, 'note']!r}): bỏ nợ cuối kỳ")
                return
            left.at[i] = v
        db.tables["orders"] = orders.assign(debt_left=left)
    if "debt_left" in db.tables["orders"].columns:
        db.debt_snapshot_day = last_day(readme)
