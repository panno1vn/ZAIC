"""Apply a Mapping to raw tables (build_canonical), run the required checks, and summarise the result (data card).

Every raw table gets pseudo-columns a mapping may use: `_source` (table id), `_row` (a row id, for books without order
ids) and `_year` (the sheet's year). Order-level cells left blank on the following rows of an order are filled from
its first row before duplicate rows are dropped (§8). Dates without a year take the year of their sheet (§8).
The named transforms of contracts.mapping.TRANSFORMS are applied to the raw text before parsing.
"""
from __future__ import annotations

import fnmatch
import re
import unicodedata
from collections import Counter
from datetime import date

import pandas as pd

from datamate.contracts import (ORDER_STATUSES, TABLES, CanonicalDB, CheckResult, ColumnMap, DataCard, Mapping,
                                RawBusiness, TableMap, check_frame)
from datamate.loader.parse import parse_bool, parse_date, parse_datetime, parse_money, parse_number

# the column that dates each table, for CanonicalDB.date_ranges
DATE_COLUMNS = {"orders": "order_time", "purchases": "receipt_time", "payments": "paid_time", "inventory": "as_of",
                "price_history": "effective_date", "expenses": "expense_date", "deliveries": "delivery_time",
                "shift_reports": "report_date", "warranty_visits": "visit_time"}
REQUIRED_CHECKS = ("có orders và lines", "bảng đúng schema", "trạng thái đơn đã quy đổi", "khoảng ngày hợp lý",
                   "dòng hàng thuộc đơn có thật", "cột bắt buộc đủ giá trị",
                   # H17, checks of meaning; thresholds measured on the 8 hand mappings of 05/11 (docs/HAN_CHE §E)
                   "thành tiền khớp số lượng × đơn giá", "trạng thái hợp lý", "ngày cuối khớp README",
                   "số âm chỉ ở đơn trả")
AMOUNT_MATCH_MIN = 0.95  # share of lines with amount ≈ qty × price − discount; 0.980–1.000 on correct mappings
SOLD_SHARE_MIN = 0.5  # share of orders completed or delivering; 0.95–0.98 on correct mappings
NEGATIVE_MAX = 0.001  # share of lines with a negative amount or qty outside returned orders; 0 on correct mappings
MIN_ROWS = 20  # the share checks need this many orders / lines to mean anything (real shops have hundreds or more)
# orders whose status cell is blank on their first row (a public shop: 1 order of 820, nothing to read it from): the
# shop is kept and every figure such an order could change is not given (metrics/frames.unknown_status)
UNKNOWN_STATUS_MAX = 0.005
_README_END = re.compile(r"đến hết (?:ngày )?(\d{1,2})/(\d{1,2})/(\d{4})")
PSEUDO = ("_source", "_row", "_year")

_PARSERS = {"money": parse_money, "number": parse_number, "qty": parse_number, "bool": parse_bool}
_DATED = {"date": parse_date, "datetime": parse_datetime}
_QTY_UNIT = re.compile(r"^\s*(-?\d[\d.,]*)\s*(.*?)\s*$")


def _fold(s: str) -> str:
    t = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip())


def _text(v):
    return None if _blank(v) else str(v).strip()


def _fill_down(col: pd.Series, follow: pd.Series) -> pd.Series:
    """Blank cells of continuation rows take the value of the order's first row."""
    blank = col.map(_blank)
    filled = col.where(~blank, None).ffill()
    return col.where(~(follow & blank), filled)


def source_ids(tm: TableMap, table_ids: list[str]) -> list[str]:
    """Raw tables a TableMap stacks, in file order: exact ids and glob patterns ("SoBanHang.xlsx::*")."""
    return [t for t in table_ids if any(t == s or fnmatch.fnmatchcase(t, s) for s in tm.sources)]


def prepare_raw(raw: RawBusiness, mapping: Mapping) -> dict[str, pd.DataFrame]:
    """Raw frames by table id, with the pseudo-columns and the §8 fill-down of order-level cells (within a sheet)."""
    orders = next((tm for tm in mapping.tables if tm.target == "orders"), None)
    id_col = next((c.source for c in orders.columns if c.target == "order_id"), None) if orders else None
    order_cols = {src for c in orders.columns for src in [c.source, *c.sources] if src} if orders else set()
    order_tables = set(source_ids(orders, [t.table_id for t in raw.tables])) if orders else set()
    frames = {}
    for t in raw.tables:
        f = t.frame.copy()
        f["_source"] = t.table_id
        f["_row"] = [f"{t.table_id}#{i + 1}" for i in range(len(f))]
        f["_year"] = t.year_hint
        if (mapping.record_grain == "order" and t.table_id in order_tables
                and id_col in f.columns and id_col not in PSEUDO):
            follow = f[id_col].map(_blank)  # a row without order id continues the order above it (§8)
            for c in sorted(order_cols & set(f.columns) - set(PSEUDO)):
                f[c] = _fill_down(f[c], follow)
        frames[t.table_id] = f
    return frames


def _transform(values: pd.Series, cm: ColumnMap, frame: pd.DataFrame, raw_frames: dict[str, pd.DataFrame],
               warnings: list[str], target: str) -> pd.Series:
    t, a = cm.transform, cm.args
    if t == "regex_extract":
        rx, g = re.compile(a["pattern"]), a.get("group", 1)
        return values.map(lambda v: (m.group(g) if (m := rx.search(v)) else None) if isinstance(v, str) else None)
    if t == "split_qty_unit":
        part = 1 if a["part"] == "qty" else 2

        def split(v):
            if not isinstance(v, str):
                return None
            m = _QTY_UNIT.match(v)
            return (m.group(part) or None) if m else (v if part == 2 else None)
        return values.map(split)
    if t == "note_contains":
        keys = [(_fold(k), out) for k, out in a["map"].items()]
        default = a.get("default")
        return values.map(lambda v: next((out for k, out in keys if isinstance(v, str) and k in _fold(v)), default))
    if t == "lookup":
        src = raw_frames.get(a["table"])
        if src is None or a["key"] not in src.columns or a["value"] not in src.columns:
            warnings.append(f"{target}.{cm.target}: lookup không thấy bảng / cột {a}")
            return pd.Series([None] * len(values), index=values.index)
        table = {k: v for k, v in zip(src[a["key"]], src[a["value"]]) if not _blank(k)}
        keep = a.get("keep_missing", True)
        return values.map(lambda v: table.get(v, v if keep else None) if v is not None else None)
    if t == "concat":
        cols = [c for c in cm.sources if c in frame.columns]
        return frame[cols].apply(lambda r: a["sep"].join(x for x in map(_text, r) if x) or None, axis=1)
    return values  # year_from_sheet: dates always take the sheet's year; negate, order_status_from_lines: later steps


def _column(frame: pd.DataFrame, cm: ColumnMap, raw_frames: dict[str, pd.DataFrame], warnings: list[str],
            target: str) -> pd.Series:
    if cm.const is not None:  # a constant is parsed like a cell ("2026-06-24" with parse date), except as text
        values = pd.Series([cm.const] * len(frame), index=frame.index, dtype=object)
        if cm.parse == "text" or not isinstance(cm.const, str):
            return values
    elif cm.transform != "concat" and (cm.source is None or cm.source not in frame.columns):
        warnings.append(f"{target}.{cm.target}: không có cột nguồn {cm.source!r}")
        return pd.Series([None] * len(frame), index=frame.index)
    else:
        values = frame[cm.source].map(_text) if cm.source in frame.columns else pd.Series(None, index=frame.index)
    if cm.transform is not None:
        values = _transform(values, cm, frame, raw_frames, warnings, target)
    if cm.parse in _DATED:
        parse = _DATED[cm.parse]
        values = pd.Series([parse(v, int(y) if pd.notna(y) else None) for v, y in zip(values, frame["_year"])],
                           index=frame.index, dtype=object)
    elif cm.parse in _PARSERS:
        values = values.map(_PARSERS[cm.parse])
    if cm.transform == "negate":
        values = values.map(lambda v: -v if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
    return values


def _status_from_lines(statuses: pd.Series) -> str | None:
    """Order status from the statuses of its lines (§1: an order with any returned line is a returned order)."""
    s = set(statuses.dropna())
    if "returned" in s:
        return "returned"
    if s == {"cancelled"}:
        return "cancelled"
    if "delivering" in s and s <= {"delivering", "completed"}:
        return "delivering"
    return "completed" if s == {"completed"} else None  # anything else is unclear: the status check fails


def _build_table(tm: TableMap, mapping: Mapping, warnings: list[str], raw_frames: dict[str, pd.DataFrame]
                 ) -> pd.DataFrame:
    ids = source_ids(tm, list(raw_frames))
    frames = [raw_frames[s] for s in ids]
    missing = [s for s in tm.sources if not source_ids(TableMap(target=tm.target, sources=[s], columns=[]), ids)]
    if missing:
        warnings.append(f"{tm.target}: thiếu bảng nguồn {missing}")
    if not frames:
        return pd.DataFrame(columns=[c.target for c in tm.columns])
    frame = pd.concat(frames, ignore_index=True)
    if mapping.record_grain == "order" and tm.target in ("orders", "lines"):  # §8 export duplicates
        frame = frame.drop_duplicates(subset=[c for c in frame.columns if c not in PSEUDO])
    out = pd.DataFrame(index=frame.index)
    for cm in tm.columns:
        col = _column(frame, cm, raw_frames, warnings, tm.target)
        if cm.target in tm.value_maps:
            vm = tm.value_maps[cm.target]

            def remap(v, vm=vm):
                if isinstance(v, str):
                    v = vm.get(v, v)
                return None if v == "" else v
            col = col.map(remap)
        out[cm.target] = col
    if "source" in {c.name for c in TABLES[tm.target].columns}:
        out["source"] = frame["_source"]
    for c in TABLES[tm.target].columns:  # typed columns, so check_frame and metrics see real dtypes
        if c.name in out.columns:
            if c.dtype == "datetime":
                out[c.name] = pd.to_datetime(out[c.name], errors="coerce")
            elif c.dtype in ("float", "int"):
                out[c.name] = pd.to_numeric(out[c.name], errors="coerce")
    if tm.target == "orders" and "order_id" in out.columns:
        for col in [cm.target for cm in tm.columns if cm.transform == "order_status_from_lines"]:
            out[col] = out.groupby("order_id", sort=False)[col].transform(_status_from_lines)
        if "order_time" in out.columns:  # a return line carries the return date: the order date is its earliest row
            out["order_time"] = out.groupby("order_id", sort=False)["order_time"].transform("min")
        out = out.drop_duplicates(subset="order_id", keep="first")  # §8: order fields are those of its first row
    return out.reset_index(drop=True)


def build_canonical(raw: RawBusiness, mapping: Mapping) -> CanonicalDB:
    db = CanonicalDB(industry=mapping.industry, warnings=list(raw.warnings))
    raw_frames = prepare_raw(raw, mapping)
    for tm in mapping.tables:
        db.tables[tm.target] = _build_table(tm, mapping, db.warnings, raw_frames)
    unify_keys(db)
    mark_fee_lines(db)
    derive_base_qty(db)
    blank_walk_ins(db)
    for table, col in DATE_COLUMNS.items():
        df = db.table(table)
        if df is not None and col in df.columns and df[col].notna().any():
            values = pd.to_datetime(df[col], errors="coerce").dropna()
            if len(values):
                db.date_ranges[table] = (values.min().date(), values.max().date())
    return db


FEE_LINE = re.compile(r"^(?:phi phuc vu|phi dich vu|service charge)\b")


def mark_fee_lines(db: CanonicalDB) -> None:
    """§3: a "Phí phục vụ" line is not an item (not ranked, not counted, still revenue), whatever the mapping says: a
    mapping moved from a shop without such lines writes every line as an item (04/11: three counts of products one
    too many)."""
    lines = db.tables.get("lines")
    if lines is None or not len(lines) or "product_name" not in lines.columns:
        return
    fee = lines["product_name"].map(lambda v: isinstance(v, str) and bool(FEE_LINE.match(_fold(v))))
    if fee.any():
        lines["is_item"] = (lines["is_item"] if "is_item" in lines.columns else True)
        lines.loc[fee, "is_item"] = False


def unify_keys(db: CanonicalDB) -> None:
    """One key per product and per customer however the files spell it (§8 "tên gọi, nhãn", §3 "hai tên chỉ khác
    cách viết là cùng một khách"). The train files write a name with other case, doubled spaces or no diacritics
    ("MÌ OMACHI SƯỜN HẦM", "Coca  Cola 330ml", "Gao ST25": 7 of 70 product names in one shop, 04/11); every spelling
    takes the most frequent one, in every table. Two names apart only by their diacritics ("Bánh bò", "Bánh bơ") stay
    two, and a spelling without diacritics, which could be either, stays apart from both. Codes are untouched."""
    for column in ("product_key", "customer_key"):
        frames = [df for df in db.tables.values() if column in df.columns and len(df)]
        counts = Counter(v for df in frames for v in df[column].dropna() if isinstance(v, str))
        by_fold: dict[str, list[str]] = {}
        for v in counts:
            by_fold.setdefault(_fold(v), []).append(v)
        rename = {}
        for folded, spellings in by_fold.items():
            if len(spellings) < 2:
                continue
            by_name: dict[str, list[str]] = {}
            for v in spellings:
                by_name.setdefault(" ".join(v.lower().split()), []).append(v)
            marked = [n for n in by_name if n != folded]  # names that carry diacritics
            groups = [spellings] if len(marked) <= 1 else list(by_name.values())
            for g in groups:
                keep = max(g, key=lambda v: (counts[v], v))
                rename.update({v: keep for v in g if v != keep})
        if rename:
            for df in frames:
                df[column] = df[column].map(lambda v: rename.get(v, v))
            db.warnings.append(f"{column}: gộp {len(rename)} cách viết khác của cùng một tên")


# walk-in customers written in the customer column (§3: an order without a customer code is "khách lẻ", not a
# customer); the spellings found in the train files
WALK_IN = frozenset({"khach le", "le", "kl", "khach vang lai", "vang lai"})


def blank_walk_ins(db: CanonicalDB) -> None:
    """orders.customer_key empty for walk-in orders, whatever the file wrote ("Khách lẻ", "kl", ""): a mapping that
    misses one spelling would otherwise rank "kl" as the best customer (T3, 03/11)."""
    o = db.tables.get("orders")
    if o is None or "customer_key" not in o.columns:
        return
    walk = o["customer_key"].map(lambda v: isinstance(v, str) and (not v.strip() or _fold(v) in WALK_IN))
    o.loc[walk, "customer_key"] = None


def derive_base_qty(db: CanonicalDB) -> None:
    """lines.base_qty = qty × factor of (product, unit) when the file does not record it (§3 "quy về đơn vị cơ bản").
    A unit with no conversion row is the base unit (factor 1), except for a product that has conversions and a known
    base unit different from it: that line gets no base quantity rather than a guessed one."""
    lines = db.tables.get("lines")
    if lines is None or not len(lines) or not {"qty", "unit", "product_key"} <= set(lines.columns):
        return
    if "base_qty" in lines.columns and lines["base_qty"].notna().any():
        return  # mapped from the file
    conv = db.table("unit_conversions")
    factors, base_unit = {}, {}
    if conv is not None:
        for row in conv.itertuples(index=False):
            factors[(row.product_key, _fold(str(row.unit)))] = row.factor
            if "base_unit" in conv.columns and isinstance(row.base_unit, str):
                base_unit[row.product_key] = _fold(row.base_unit)
    converted = {p for p, _ in factors}
    # a product sold in two units with no conversion row: which one is the base is unknown (04/11, a mapping moved
    # from a shop without a conversion table took every unit for the base unit, "1 thùng" for one can)
    units = lines.dropna(subset=["unit"]).groupby("product_key")["unit"].agg(
        lambda s: len({_fold(str(u)) for u in s if str(u).strip()}))
    unclear = {p for p, n in units.items() if n > 1} - converted

    def base(p, u, q):
        if pd.isna(q) or p in unclear:
            return None
        u = _fold(u) if isinstance(u, str) else ""
        if (p, u) in factors:
            return q * factors[(p, u)]
        if p not in converted or base_unit.get(p) in (None, u) or not u:
            return q
        return None
    lines["base_qty"] = pd.to_numeric(pd.Series([base(p, u, q) for p, u, q in
                                                 zip(lines["product_key"], lines["unit"], lines["qty"])],
                                                index=lines.index), errors="coerce")
    if lines["base_qty"].isna().any():
        db.warnings.append(f"lines.base_qty: {int(lines['base_qty'].isna().sum())} dòng không quy đổi được")


def empty_required_cells(db: CanonicalDB) -> list[str]:
    """Required canonical columns with empty cells. An unread date drops its order from every period and an unread
    amount zeroes its line, so the answers would be wrong without any error."""
    out = []
    for name, df in db.tables.items():
        spec = TABLES.get(name)
        if spec is None or not len(df):
            continue
        for c in spec.columns:
            if (name, c.name) == ("orders", "status"):
                continue  # a few orders without status are let through by the status check (UNKNOWN_STATUS_MAX)
            n = int(df[c.name].isna().sum()) if c.required and c.name in df.columns else 0
            if n:
                out.append(f"{name}.{c.name}: {n}/{len(df)} ô trống")
    return out


def meaning_checks(db: CanonicalDB, readme: str = "") -> list[tuple[bool, str]]:
    """(passed, detail) of the H17 checks; a check whose columns are missing does not apply and passes. They catch a
    mapping that is well formed but wrong: amount mapped to the price column, statuses mapped the wrong way round,
    sheets or files left out, a discount or price column taken for the amount."""
    o, ln = db.table("orders"), db.table("lines")
    if o is None or ln is None:
        return [(True, "không áp dụng")] * 4
    out = []
    if {"qty", "unit_price", "line_amount"} <= set(ln.columns) and ln["unit_price"].notna().sum() >= MIN_ROWS:
        rows = ln[ln["unit_price"].notna()]
        disc = rows["line_discount"].fillna(0) if "line_discount" in rows.columns else 0
        diff = (rows["line_amount"] - (rows["qty"] * rows["unit_price"] - disc)).abs()
        share = float((diff <= (0.01 * rows["line_amount"].abs()).clip(lower=1)).mean())
        out.append((share >= AMOUNT_MATCH_MIN, f"{share:.1%} dòng khớp (cần ≥ {AMOUNT_MATCH_MIN:.0%})"))
    else:
        out.append((True, "không áp dụng: thiếu số lượng, đơn giá hoặc thành tiền"))
    sold = float(o["status"].isin(("completed", "delivering")).mean())
    if len(o) >= MIN_ROWS:
        out.append((sold >= SOLD_SHARE_MIN, f"{sold:.1%} đơn hoàn thành hoặc đang giao (cần ≥ {SOLD_SHARE_MIN:.0%})"))
    else:
        out.append((True, f"không áp dụng: dưới {MIN_ROWS} đơn"))
    m, span = _README_END.search(readme), db.date_ranges.get("orders")
    if m and span:
        try:
            gap = (date(int(m[3]), int(m[2]), int(m[1])) - span[1]).days
            out.append((abs(gap) <= 1, f"README ghi đến hết {m[1]}/{m[2]}/{m[3]}, đơn cuối ngày {span[1]}"))
        except ValueError:
            out.append((True, "không áp dụng: ngày trong README không đọc được"))
    else:
        out.append((True, "không áp dụng: README không ghi ngày cuối"))
    status = ln["order_id"].map(o.set_index("order_id")["status"]) if o["order_id"].is_unique else None
    if status is not None and {"qty", "line_amount"} <= set(ln.columns):
        neg = ((ln["line_amount"] < 0) | (ln["qty"] <= 0)) & (status != "returned")
        share = float(neg.mean())
        out.append((share <= NEGATIVE_MAX, f"{int(neg.sum())} dòng âm hoặc số lượng ≤ 0 ngoài đơn trả hàng"))
    else:
        out.append((True, "không áp dụng"))
    return out


def run_checks(db: CanonicalDB, readme: str = "") -> list[CheckResult]:
    """The required checks (H8): a mapping is usable only if every one of them passes."""
    has_core = db.has("orders") and db.has("lines")
    problems = [p for name, df in db.tables.items() for p in check_frame(name, df)]
    status_ok = has_core and set(db.tables["orders"]["status"].dropna()) <= set(ORDER_STATUSES) \
        and db.tables["orders"]["status"].isna().mean() <= UNKNOWN_STATUS_MAX
    span = db.date_ranges.get("orders")
    span_ok = span is not None and date(2000, 1, 1) <= span[0] <= span[1] <= date(2100, 1, 1)
    lines_ok = has_core and set(db.tables["lines"]["order_id"].dropna()) <= set(db.tables["orders"]["order_id"])
    empty = empty_required_cells(db)
    meaning = meaning_checks(db, readme)
    results = [has_core, not problems, status_ok, span_ok, lines_ok, not empty] + [ok for ok, _ in meaning]
    details = ["", "; ".join(problems[:5]), "", str(span), "", "; ".join(empty[:5])] + [d for _, d in meaning]
    return [CheckResult(name=n, passed=bool(ok), detail=d) for n, ok, d in zip(REQUIRED_CHECKS, results, details)]


def build_card(db: CanonicalDB) -> DataCard:
    span = db.date_ranges.get("orders")
    fields = [f"{t}.{c}" for t, df in db.tables.items() for c in df.columns if df[c].notna().any()]

    def values(table: str, col: str, limit: int = 30) -> list[str]:
        df = db.table(table)
        if df is None or col not in df.columns:
            return []
        return sorted(df[col].dropna().astype(str).unique().tolist())[:limit]

    lines = db.table("lines")
    return DataCard(industry=db.industry, date_min=str(span[0]) if span else None,
                    date_max=str(span[1]) if span else None, tables=sorted(t for t in db.tables if db.has(t)),
                    fields=fields, extra_tables={k: v.description for k, v in db.extra.items()},
                    product_groups=values("lines", "product_group"), channels=values("orders", "channel"),
                    payment_methods=values("orders", "payment_method"),
                    customer_groups=values("orders", "customer_group"), units=values("lines", "unit"),
                    employees=values("orders", "employee"),
                    n_products=int(lines["product_key"].nunique()) if lines is not None else 0,
                    n_customers=int(db.tables["orders"]["customer_key"].nunique())
                    if db.has("orders", "customer_key") else 0)
