"""Turn a raw grid of cells (one sheet or csv) into a table: cells as text, header row found, summary rows dropped.

Seen in the data (docs/research/entities.md, scan of 02/11): title rows above the header, two-row headers whose top
row only names column groups ("Hàng | Tiền | Đơn"), "Cộng" summary rows at the end of monthly sheets, Excel
dates, Excel serial numbers and text dates mixed in one column, integral numbers stored as floats (1001.0).
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time

import pandas as pd

HEADER_SCAN = 10  # rows searched for the header
WIDTH_SCAN = 40  # rows used to measure how wide the data is
_DATA_LIKE = re.compile(
    r"^-?[\d.,\s]+(?:đ|d|vnđ|vnd|k|tr\d*)?$"  # numbers and money: 25.000đ, 1tr440, 25k, -3
    r"|^\d{1,4}[/-]\d{1,2}(?:[/-]\d{1,4})?(?:\s.*)?$"  # dates: 01/02/2025, 1/1, 2025-02-01 06:00:25
    r"|^\d{1,2}\s*thg\s*\d{1,2}", re.I)
# "Cộng", "Tổng cộng", "Tổng tháng", "Total"…; only on sparse rows, so a customer "Tống Văn An" on a full row stays
_SUMMARY = re.compile(r"^(?:cong|tong|total|grand total|sum|subtotal)\b")
# a total of a day or month ("tổng 01/05", "Tổng ngày 01/03", "Cộng tháng 3"): a summary on a full row too, its
# numbers in every column; a name "Tống Văn An" has no number after it
_DATED_SUMMARY = re.compile(r"^(?:cong|tong|total)(?: cong)?(?: ngay| thang)? ?\d{1,2}(?:[/.-]\d{1,4})*$")


def cell_text(v) -> str:
    """One cell as text, the way the parsers expect it: '' for empty, integral floats without '.0', ISO dates."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d") if v.time() == time(0) else v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, (date, time)):
        return v.isoformat()
    return unicodedata.normalize("NFC", str(v).strip())  # one form, so "Huỷ" in a mapping matches "Huỷ" in the file


def fold(s: str) -> str:
    t = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def _filled(row: list[str]) -> int:
    return sum(1 for c in row if c)


def _texty(row: list[str]) -> float:
    cells = [c for c in row if c]
    return sum(1 for c in cells if not _DATA_LIKE.match(c)) / len(cells) if cells else 0.0


def _is_group_row(row: list[str]) -> bool:
    """Labels of merged column groups: ≥ 2 names, each followed by a blank cell, no "label: value" pairs."""
    cells = [j for j, c in enumerate(row) if c]
    return (len(cells) >= 2 and _texty(row) == 1.0 and not any(":" in row[j] for j in cells)
            and all(b - a >= 2 for a, b in zip(cells, cells[1:])))


@dataclass
class Table:
    frame: pd.DataFrame
    header_rows: int  # rows above the data: title rows + header (+ group row)
    notes: list[str] = field(default_factory=list)


def find_header(rows: list[list[str]]) -> tuple[int, list[str]]:
    """(index of the header row, notes). The header is the first row nearly as wide as the data and made of names."""
    width = max((_filled(r) for r in rows[:WIDTH_SCAN]), default=0)
    for i, r in enumerate(rows[:HEADER_SCAN]):
        if width and _filled(r) >= max(2, 0.6 * width) and _texty(r) >= 0.8:
            return i, []
    return 0, ["không thấy dòng header rõ ràng: lấy dòng đầu"]


def to_table(grid: list[list]) -> Table:
    """A sheet or csv as a DataFrame of text cells with named columns."""
    grid_rows = [[cell_text(c) for c in r] for r in grid]
    if not any(any(r) for r in grid_rows):
        return Table(pd.DataFrame(), 0, ["sheet trống"])
    ncol = max(len(r) for r in grid_rows)
    grid_rows = [r + [""] * (ncol - len(r)) for r in grid_rows]
    used = [j for j in range(ncol) if any(r[j] for r in grid_rows)]  # drop empty columns (empty area left of the data)
    grid_rows = [[r[j] for j in used] for r in grid_rows]
    filled_idx = [i for i, r in enumerate(grid_rows) if any(r)]
    rows = [grid_rows[i] for i in filled_idx]
    h, notes = find_header(rows)
    header = rows[h]
    above = grid_rows[filled_idx[h] - 1] if filled_idx[h] > 0 else []
    if _is_group_row(above):  # right above the header: "Hàng | | | Tiền | | | Đơn"
        groups, current = [], ""
        for c in above:
            current = c or current
            groups.append(current)
        spans = {}
        for g, name in zip(groups, header):
            if g and name:
                spans.setdefault(g, []).append(name)
        notes.append("header 2 dòng, nhóm cột: " + "; ".join(f"{g}: {', '.join(n)}" for g, n in spans.items()))
    if h > 0:
        notes.append(f"bỏ {h} dòng phía trên header: " + " | ".join(" ".join(c for c in r if c)[:60] for r in rows[:h]))
    names, seen = [], {}
    for j, c in enumerate(header):
        name = c or f"cot_{j + 1}"
        seen[name] = seen.get(name, 0) + 1
        names.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    if any(v > 1 for v in seen.values()):
        notes.append("tên cột trùng, đã thêm hậu tố _2, _3…")
    body = rows[h + 1:]
    min_filled = max(2, _filled(header) // 2)
    keep, dropped, repeated = [], [], 0
    for r in body:
        # "Cộng" + a total; a customer "Tống…" is a full row. The label may sit after the total: columns come in any
        # order ("3,411,000 | Tổng ngày 01/03", daily totals inside a hand-kept ledger sheet)
        if (_filled(r) < min_filled and any(c and _SUMMARY.match(fold(c)) for c in r)) or any(
                c and _DATED_SUMMARY.match(fold(c)) for c in r):  # "tổng 01/05" in the order id column, sums beside
            dropped.append(" ".join(c for c in r if c)[:60])
        elif _filled(r) and sum(bool(c) and c == n for c, n in zip(r, header)) * 2 > _filled(r):
            repeated += 1  # the header written again inside the data (files pasted together): no record
        else:
            keep.append(r)
    if dropped:
        notes.append(f"bỏ {len(dropped)} dòng tổng: {dropped[0]}")
    if repeated:
        notes.append(f"bỏ {repeated} dòng lặp lại header")
    footer = []
    while keep and len(names) >= 4 and _filled(keep[-1]) <= 1:  # "Ghi chú: tiền tính bằng đồng" under the data
        footer.insert(0, " ".join(c for c in keep.pop() if c)[:60])
    if footer:
        notes.append(f"bỏ {len(footer)} dòng chú thích cuối sheet: " + " | ".join(footer))
    frame = pd.DataFrame(keep, columns=names, dtype=str) if keep else pd.DataFrame(columns=names, dtype=str)
    return Table(frame, h + 1, notes)


_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def year_hint(*names: str | None) -> int | None:
    """Year written in a sheet name ('Thang 06 2026', 'T7-2025') or else in the file name ('BanHang_T11_2025')."""
    for n in names:
        m = _YEAR.search(n or "")
        if m:
            return int(m.group(1))
    return None
