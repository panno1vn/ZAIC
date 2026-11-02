"""[A] Read and clean every file of a business; [A2] profile the resulting tables. Work package G1.

Skeleton (05/11): reads csv files and sqlite tables as text; xlsx is not read yet (G1: sheets, 1–2 row headers,
monthly sheets, files split _1/_2). Cells stay as raw text here; [B] parses them per the mapping.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from datamate.contracts import BusinessProfile, ColumnProfile, RawBusiness, RawTable, TableProfile


def load_business(root: Path) -> RawBusiness:
    """Read every csv/sqlite file under `root` (read-only) into RawTables of text cells."""
    readme = root / "README.md"
    raw = RawBusiness(root=root, readme=readme.read_text(encoding="utf-8") if readme.exists() else "")
    for f in sorted(root.iterdir()) if root.exists() else []:
        try:
            if f.suffix.lower() == ".csv":
                df = pd.read_csv(f, dtype=str, keep_default_na=False, encoding="utf-8-sig")
                raw.tables.append(RawTable(table_id=f.name, file=f.name, sheet=None, frame=df))
            elif f.suffix.lower() == ".sqlite":
                con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
                try:
                    names = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
                    for t in names:
                        df = pd.read_sql_query(f'select * from "{t}"', con).astype(str)
                        raw.tables.append(RawTable(table_id=f"{f.name}::{t}", file=f.name, sheet=t, frame=df))
                finally:
                    con.close()
            elif f.suffix.lower() == ".xlsx":
                raw.warnings.append(f"{f.name}: chưa đọc xlsx (G1)")
        except Exception as e:  # one unreadable file must not stop the business
            raw.warnings.append(f"{f.name}: lỗi đọc {type(e).__name__}: {e}")
    return raw


def profile_business(raw: RawBusiness, n_samples: int = 5) -> BusinessProfile:
    """Describe each raw table (columns, a few distinct values) for the mapping step."""
    tables = []
    for t in raw.tables:
        cols = []
        for c in t.frame.columns:
            s = t.frame[c].astype(str)
            filled = s[s.str.strip() != ""]
            cols.append(ColumnProfile(name=str(c), dtype="text", non_null=int(filled.size),
                                      distinct=int(filled.nunique()), samples=filled.drop_duplicates().head(n_samples).tolist()))
        tables.append(TableProfile(table_id=t.table_id, n_rows=len(t.frame), header_rows=t.header_rows, columns=cols))
    return BusinessProfile(tables=tables, readme=raw.readme, warnings=list(raw.warnings))
