"""[A] Read and clean every file of a business; [A2] profile the resulting tables. Work package G1.

csv, every sheet of every xlsx (python-calamine) and every sqlite table become RawTables of text cells with the header
found (grid.to_table: title rows, two-row headers, "Cộng" summary rows). Cells stay as text here; [B] parses them per
the mapping. Files are opened read-only and nothing is written next to them.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
import time
from pathlib import Path

import pandas as pd
from python_calamine import CalamineWorkbook

from datamate.contracts import BusinessProfile, ColumnProfile, RawBusiness, RawTable, TableProfile

from .grid import cell_text, to_table, year_hint
from .parse import parse_datetime, parse_money, parse_number, strip_weekday

BUDGET_S = 300.0  # reading one business may take this long; the rest of its files are skipped (H12)


def _decode(data: bytes) -> tuple[str, str | None]:
    # N160: Excel's "Unicode text" is UTF-16; cp1258 decodes it into text with a NUL every other character, the shop
    # then has no table (robust test 09/11: a CSV shop saved as UTF-16 mapped nothing). A BOM, or NULs in half the
    # bytes, is UTF-16.
    head = data[:4096]
    if head[:2] in (b"\xff\xfe", b"\xfe\xff") or (head and head.count(0) * 3 > len(head)):
        enc = "utf-16" if head[:2] in (b"\xff\xfe", b"\xfe\xff") else (
            "utf-16-le" if head[1::2].count(0) > head[0::2].count(0) else "utf-16-be")
        try:
            return data.decode(enc), f"đọc bằng bảng mã {enc}"
        except UnicodeDecodeError:
            pass
    for enc in ("utf-8-sig", "cp1258"):
        try:
            return data.decode(enc), None if enc == "utf-8-sig" else f"đọc bằng bảng mã {enc}"
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "lỗi bảng mã, ký tự hỏng đã thay bằng �"


DELIMITER_SCAN = 10  # lines read for the delimiter: the header is looked for in the first rows too (grid.HEADER_SCAN)


def _delimiter(text: str) -> str:
    """The delimiter of a csv: the most frequent of ',', ';' and tab on its first line, when the line after it holds
    that delimiter too (a header and its rows do). N195: a first line that holds none of them, or one the next line
    does not hold, is a title above the header ("SỔ BÁN HÀNG", "Sổ bán hàng, năm 2025") and the lines after it decide
    the same way: read by its first line alone, such a file written with ';' or tabs was cut at its commas (a train
    ledger rewritten so: 5 columns for 10, no mapping, every question of the shop blank). A line with none of the
    three and a '|' is cut at '|'. Blank lines are passed over; no delimiter in the first lines: one column, ','."""
    lines = [line for line in text.split("\n", DELIMITER_SCAN + 1)[:DELIMITER_SCAN + 1] if line.strip()]
    for i, line in enumerate(lines[:DELIMITER_SCAN]):
        best = max([",", ";", "\t"], key=line.count)
        if not line.count(best):
            best = "|" if "|" in line else None
        if best is not None and (i + 1 == len(lines) or best in lines[i + 1]):
            return best
    return ","


def _read_csv(f: Path) -> list[RawTable]:
    text, note = _decode(f.read_bytes())
    delim = _delimiter(text)
    t = to_table(list(csv.reader(io.StringIO(text), delimiter=delim)))
    notes = t.notes + ([note] if note else []) + ([f"dấu phân cách {delim!r}"] if delim != "," else [])
    return [RawTable(table_id=f.name, file=f.name, sheet=None, frame=t.frame, header_rows=t.header_rows,
                     year_hint=year_hint(f.stem), notes=notes)]


def _read_xlsx(f: Path) -> list[RawTable]:
    wb = CalamineWorkbook.from_path(str(f))
    out = []
    for sheet in wb.sheet_names:
        t = to_table(wb.get_sheet_by_name(sheet).to_python(skip_empty_area=False))
        out.append(RawTable(table_id=f"{f.name}::{sheet}", file=f.name, sheet=sheet, frame=t.frame,
                            header_rows=t.header_rows, year_hint=year_hint(sheet, f.stem), notes=t.notes))
    return out


def _read_sqlite(f: Path) -> list[RawTable]:
    con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        out = []
        for t in names:
            df = pd.read_sql_query(f'select * from "{t}"', con)
            df = df.astype(object).where(df.notna(), None).map(cell_text)  # NULL is blank, as in csv, not "None"
            out.append(RawTable(table_id=f"{f.name}::{t}", file=f.name, sheet=t, frame=df.astype(str)))
        return out
    finally:
        con.close()


READERS = {".csv": _read_csv, ".xlsx": _read_xlsx, ".xlsm": _read_xlsx, ".xls": _read_xlsx, ".sqlite": _read_sqlite,
           ".db": _read_sqlite, ".sqlite3": _read_sqlite}


def load_business(root: Path, budget_s: float = BUDGET_S) -> RawBusiness:
    """Read every data file under `root` (read-only) into RawTables of text cells."""
    # N160: README in any case ("readme.md") and any encoding the data files may have (BOM, UTF-16)
    readmes = sorted(p for p in root.iterdir() if p.is_file() and p.name.lower() == "readme.md") if root.exists() else []
    raw = RawBusiness(root=root, readme=_decode(readmes[0].read_bytes())[0].lstrip("﻿") if readmes else "")
    start = time.monotonic()
    files = sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []
    for f in files:
        reader = READERS.get(f.suffix.lower())
        if reader is None:
            if f.name.lower() != "readme.md":
                raw.warnings.append(f"{f.relative_to(root)}: bỏ qua, không đọc kiểu file {f.suffix or '(không đuôi)'}")
            continue
        if time.monotonic() - start > budget_s:
            raw.warnings.append(f"{f.name}: bỏ qua, hết {budget_s:.0f}s đọc file của cửa hàng")
            continue
        try:
            raw.tables.extend(reader(f))
        except Exception as e:  # one unreadable file must not stop the business
            raw.warnings.append(f"{f.name}: lỗi đọc {type(e).__name__}: {e}")
    for t in raw.tables:
        raw.warnings.extend(f"{t.table_id}: {n}" for n in t.notes if n.startswith(("không thấy", "lỗi")))
    return raw


_DATE_HINT = re.compile(r"\d{1,4}[/-]\d{1,2}|thg|^\d{4}-\d{2}-\d{2}", re.I)
_MONEY_HINT = re.compile(r"\d\s*(?:đ|vnđ|vnd|k|tr)\b|\d(?:tr)\d|^-?\d{1,3}(?:[.,]\d{3})+$"
                         r"|\d\s*(?:triệu|trieu|nghìn|nghin|ngàn|ngan)\b", re.I)


def guess_type(values: list[str], year: int | None = None) -> tuple[str, str | None, str | None]:
    """(dtype, min, max) of a column from its non-empty text values: date, money, number, text or empty."""
    if not values:
        return "empty", None, None
    n = len(values)
    if sum(bool(_DATE_HINT.search(strip_weekday(v))) for v in values) >= 0.8 * n:
        dates = [d for d in (parse_datetime(v, year) for v in values) if d is not None]
        if len(dates) >= 0.8 * n:
            return "date", str(min(dates)), str(max(dates))
    if sum(bool(_MONEY_HINT.search(v)) for v in values) >= 0.5 * n:
        amounts = [a for a in (parse_money(v) for v in values) if a is not None]
        if len(amounts) >= 0.8 * n:
            return "money", f"{min(amounts):g}", f"{max(amounts):g}"
    numbers = [x for x in (parse_number(v) for v in values) if x is not None]
    if len(numbers) >= 0.9 * n and all(re.fullmatch(r"-?[\d.,]+", v) for v in values[:50]):
        return "number", f"{min(numbers):g}", f"{max(numbers):g}"
    return "text", None, None


def profile_business(raw: RawBusiness, n_samples: int = 5, n_typed: int = 300) -> BusinessProfile:
    """Describe each raw table (columns, guessed type, range, a few distinct values) for the mapping step."""
    tables = []
    for t in raw.tables:
        cols = []
        for c in t.frame.columns:
            s = t.frame[c].astype(str)
            filled = s[s.str.strip() != ""]
            dtype, lo, hi = guess_type(filled.head(n_typed).tolist(), t.year_hint)
            cols.append(ColumnProfile(name=str(c), dtype=dtype, non_null=int(filled.size), distinct=int(filled.nunique()),
                                      samples=filled.drop_duplicates().head(n_samples).tolist(), min=lo, max=hi))
        tables.append(TableProfile(table_id=t.table_id, n_rows=len(t.frame), header_rows=t.header_rows, columns=cols))
    return BusinessProfile(tables=tables, readme=raw.readme, warnings=list(raw.warnings))
