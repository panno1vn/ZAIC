"""Apply a Mapping to raw tables (build_canonical), run the required checks, and summarise the result (data card).

Skeleton (05/11): parse types, rename, value maps, constants, §8 duplicate rows. Named transforms
(contracts.mapping.TRANSFORMS) are not implemented yet: a column that needs one is left empty with a warning (G2).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from datamate.contracts import (ORDER_STATUSES, TABLES, CanonicalDB, CheckResult, DataCard, Mapping, RawBusiness,
                                TableMap, check_frame)
from datamate.loader.parse import parse_bool, parse_date, parse_datetime, parse_money, parse_number

# the column that dates each table, for CanonicalDB.date_ranges
DATE_COLUMNS = {"orders": "order_time", "purchases": "receipt_time", "payments": "paid_time", "inventory": "as_of",
                "price_history": "effective_date", "expenses": "expense_date", "deliveries": "delivery_time",
                "shift_reports": "report_date", "warranty_visits": "visit_time"}
REQUIRED_CHECKS = ("có orders và lines", "bảng đúng schema", "trạng thái đơn đã quy đổi", "khoảng ngày hợp lý",
                   "dòng hàng thuộc đơn có thật", "cột bắt buộc đủ giá trị")

_PARSERS = {
    "money": parse_money, "number": parse_number, "qty": parse_number, "bool": parse_bool,
    "date": parse_date, "datetime": parse_datetime,
}


def _column(frame: pd.DataFrame, cm, warnings: list[str], target: str) -> pd.Series:
    if cm.const is not None:
        return pd.Series([cm.const] * len(frame), index=frame.index)
    if cm.transform is not None:
        warnings.append(f"{target}.{cm.target}: transform {cm.transform} chưa cài (G2), để trống")
        return pd.Series([None] * len(frame), index=frame.index)
    if cm.source is None or cm.source not in frame.columns:
        warnings.append(f"{target}.{cm.target}: không có cột nguồn {cm.source!r}")
        return pd.Series([None] * len(frame), index=frame.index)
    s = frame[cm.source]
    parse = _PARSERS.get(cm.parse)
    if parse is not None:
        return s.map(parse)
    return s.map(lambda v: None if v is None or (isinstance(v, str) and not v.strip()) else str(v).strip())


def _build_table(tm: TableMap, raw: RawBusiness, mapping: Mapping, warnings: list[str]) -> pd.DataFrame:
    frames = [t.frame.assign(_source=t.table_id) for t in raw.tables if t.table_id in tm.sources]
    missing = set(tm.sources) - {t.table_id for t in raw.tables}
    if missing:
        warnings.append(f"{tm.target}: thiếu bảng nguồn {sorted(missing)}")
    if not frames:
        return pd.DataFrame(columns=[c.target for c in tm.columns])
    frame = pd.concat(frames, ignore_index=True)
    if mapping.record_grain == "order" and tm.target in ("orders", "lines"):
        frame = frame.drop_duplicates(subset=[c for c in frame.columns if c != "_source"])  # §8 export duplicates
    out = pd.DataFrame(index=frame.index)
    for cm in tm.columns:
        col = _column(frame, cm, warnings, tm.target)
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
        out = out.drop_duplicates(subset="order_id", keep="first")  # §8: order fields are those of its first row
    return out.reset_index(drop=True)


def build_canonical(raw: RawBusiness, mapping: Mapping) -> CanonicalDB:
    db = CanonicalDB(industry=mapping.industry, warnings=list(raw.warnings))
    for tm in mapping.tables:
        db.tables[tm.target] = _build_table(tm, raw, mapping, db.warnings)
    for table, col in DATE_COLUMNS.items():
        df = db.table(table)
        if df is not None and col in df.columns and df[col].notna().any():
            values = pd.to_datetime(df[col], errors="coerce").dropna()
            if len(values):
                db.date_ranges[table] = (values.min().date(), values.max().date())
    return db


def empty_required_cells(db: CanonicalDB) -> list[str]:
    """Required canonical columns with empty cells. An unread date drops its order from every period and an unread
    amount zeroes its line, so the answers would be wrong without any error."""
    out = []
    for name, df in db.tables.items():
        spec = TABLES.get(name)
        if spec is None or not len(df):
            continue
        for c in spec.columns:
            n = int(df[c.name].isna().sum()) if c.required and c.name in df.columns else 0
            if n:
                out.append(f"{name}.{c.name}: {n}/{len(df)} ô trống")
    return out


def run_checks(db: CanonicalDB) -> list[CheckResult]:
    """The required checks (H8): a mapping is usable only if every one of them passes."""
    has_core = db.has("orders") and db.has("lines")
    problems = [p for name, df in db.tables.items() for p in check_frame(name, df)]
    status_ok = has_core and set(db.tables["orders"]["status"].dropna()) <= set(ORDER_STATUSES) \
        and db.tables["orders"]["status"].notna().all()
    span = db.date_ranges.get("orders")
    span_ok = span is not None and date(2000, 1, 1) <= span[0] <= span[1] <= date(2100, 1, 1)
    lines_ok = has_core and set(db.tables["lines"]["order_id"].dropna()) <= set(db.tables["orders"]["order_id"])
    empty = empty_required_cells(db)
    results = [has_core, not problems, status_ok, span_ok, lines_ok, not empty]
    details = ["", "; ".join(problems[:5]), "", str(span), "", "; ".join(empty[:5])]
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
