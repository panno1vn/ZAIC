"""Cell parsers for the messy formats seen in the data (docs/research/entities.md). Work package G1 extends them.

Every parser returns None for a value it cannot read, never raises, so one odd cell cannot stop a business.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta

_EXCEL_EPOCH = datetime(1899, 12, 30)
_THOUSANDS = re.compile(r"^-?\d{1,3}([.,])\d{3}(\1\d{3})*$")
_CURRENCY = re.compile(r"(?i)\s*(vnđ|vnd|đồng|dong|đ|d)\s*$")
_LEADING_NUMBER = re.compile(r"^\s*(-?\d[\d.,]*)")
_TR_SPLIT = re.compile(r"(?i)^(-?\d+)tr(\d{1,3})$")  # '1tr440' = 1.440.000, '409tr663', '1tr5' = 1.500.000


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and not v.strip())


def _to_float(s: str) -> float | None:
    """A number written with Vietnamese or English separators: '1.048.000', '560,000', '1,5', '45,000.0000', '1.234,50'."""
    if "," in s and "." in s:  # both: the last one is the decimal mark
        dec, thou = (".", ",") if s.rfind(".") > s.rfind(",") else (",", ".")
        s = s.replace(thou, "").replace(dec, ".")
    elif _THOUSANDS.match(s):
        s = s.replace(",", "").replace(".", "")
    elif s.count(",") == 1:
        s = s.replace(",", ".")  # decimal comma: '1,5'
    try:
        return float(s)
    except ValueError:
        return None


def parse_money(v) -> float | None:
    """'560,000' · '30.500đ' · '-30.500đ' · '25k' · '1,5tr' · '1tr440' · '45,000.0000' · 560000 → amount in đồng."""
    if _blank(v):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = _CURRENCY.sub("", str(v).strip()).replace(" ", "")
    m = _TR_SPLIT.match(s)
    if m:
        millions, rest = int(m.group(1)), int(m.group(2).ljust(3, "0")) * 1000
        return float(millions * 1_000_000 + (rest if millions >= 0 else -rest))
    mult = 1.0
    if s.lower().endswith("k"):
        s, mult = s[:-1], 1000.0
    elif s.lower().endswith("tr"):
        s, mult = s[:-2], 1_000_000.0
    if mult != 1.0 and s.count(",") + s.count(".") == 1:  # with a k / tr suffix one separator is the decimal mark
        try:  # '41,785tr' = 41,785 triệu, not 41.785 triệu × 1000
            return float(s.replace(",", ".")) * mult
        except ValueError:
            return None
    x = _to_float(s)
    return None if x is None else x * mult


def parse_number(v) -> float | None:
    """'3' · '2.5' · '1,5' · '1.500' · '5 chai' (leading number) · 3 → number. Separators read as in parse_money."""
    if _blank(v):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    m = _LEADING_NUMBER.match(str(v))
    return _to_float(m.group(1).rstrip(".,")) if m else None


_PATTERNS = [
    (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?"), "ymd"),
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$"), "dmy"),
    (re.compile(r"^(\d{1,2})\s*thg\s*(\d{1,2})\s*,?\s*(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$", re.I), "dmy"),
    (re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$"), "dmy"),
]
_DAY_MONTH = re.compile(r"^(\d{1,2})/(\d{1,2})$")


def parse_datetime(v, year_hint: int | None = None) -> datetime | None:
    """Excel serial · '2026-01-01 14:58:08' · '01/06/2026' · '1 thg 12 2025' · '1/6' (+ year_hint, §8) → datetime."""
    if _blank(v):
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return _EXCEL_EPOCH + timedelta(days=float(v)) if 20000 <= v <= 80000 else None
    s = str(v).strip()
    if re.fullmatch(r"\d{5}(\.\d+)?", s):
        return parse_datetime(float(s))
    for rx, order in _PATTERNS:
        m = rx.match(s)
        if m:
            g = [int(x) if x else 0 for x in m.groups()]
            y, mo, d = (g[0], g[1], g[2]) if order == "ymd" else (g[2], g[1], g[0])
            try:
                return datetime(y, mo, d, g[3], g[4], g[5])
            except ValueError:
                return None
    m = _DAY_MONTH.match(s)
    if m and year_hint:
        try:
            return datetime(year_hint, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def parse_date(v, year_hint: int | None = None) -> date | None:
    dt = parse_datetime(v, year_hint)
    return dt.date() if dt else None


def parse_bool(v) -> bool | None:
    if _blank(v):
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "x", "có", "co", "yes", "y", "đúng"):
        return True
    if s in ("0", "false", "không", "khong", "no", "n", "sai"):
        return False
    return None
