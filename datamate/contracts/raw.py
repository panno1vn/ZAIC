"""Output of [A] (raw tables as read from the files) and [A2] (their profile, which feeds the mapping step)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from pydantic import BaseModel


@dataclass
class RawTable:
    """One table as found in the files: a csv, one sheet, or one sqlite table. Cells parsed by [A], header resolved."""
    table_id: str  # "file::sheet" or "file::table"; unique within a business
    file: str
    sheet: str | None
    frame: pd.DataFrame
    header_rows: int = 1
    year_hint: int | None = None  # year of the sheet (e.g. "Thang 06 2026"), for dates written without a year (§8)
    notes: list[str] = field(default_factory=list)


@dataclass
class RawBusiness:
    root: Path
    readme: str
    tables: list[RawTable] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ColumnProfile(BaseModel):
    name: str
    dtype: str  # what [A] parsed it as: text, number, money, date, datetime, bool, empty
    non_null: int
    distinct: int
    samples: list[str] = []  # a few raw values, for the mapping prompt
    min: str | None = None
    max: str | None = None


class TableProfile(BaseModel):
    table_id: str
    n_rows: int
    header_rows: int = 1
    columns: list[ColumnProfile] = []


class BusinessProfile(BaseModel):
    """What the mapping step [B] sees about a business, besides its README."""
    tables: list[TableProfile] = []
    readme: str = ""
    warnings: list[str] = []
