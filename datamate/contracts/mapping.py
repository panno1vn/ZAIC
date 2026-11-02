"""Mapping produced by [B]: how a business's raw tables become canonical tables. Serialised as JSON, so mappings
written by hand for train businesses and mappings produced by the LLM share one format."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, model_validator

from .canonical import TABLES

Parse = Literal["text", "money", "number", "qty", "date", "datetime", "bool"]

# Named transforms a mapping may apply to a source column, so hand-written and LLM mappings never need free code.
# name -> (required args, meaning). Implemented by [B] (work package G2).
TRANSFORMS: dict[str, tuple[tuple[str, ...], str]] = {
    "regex_extract": (("pattern",), "lấy nhóm `group` (mặc định 1) của regex `pattern`, ví dụ size '(M)', biển số"),
    "split_qty_unit": (("part",), "'5 chai' → part='qty' cho 5, part='unit' cho 'chai'"),
    "year_from_sheet": ((), "ngày không ghi năm lấy năm của sheet chứa dòng (§8)"),
    "note_contains": (("map",), "map từ khóa → giá trị khi ô chứa từ khóa, ví dụ ghi chú 'khách trả lại' → returned"),
    "lookup": (("table", "key", "value"), "tra cột `value` của bảng thô `table` theo khóa `key`, ví dụ sheet Ghi tắt"),
    "order_status_from_lines": ((), "trạng thái đơn gộp từ trạng thái từng dòng: có dòng trả → returned…"),
    "concat": (("sep",), "nối các cột trong `sources` bằng `sep`"),
    "negate": ((), "đổi dấu số"),
}
Transform = Literal["regex_extract", "split_qty_unit", "year_from_sheet", "note_contains", "lookup",
                    "order_status_from_lines", "concat", "negate"]


class ColumnMap(BaseModel):
    target: str  # canonical column
    source: str | None = None  # raw column name; None when the value is a constant or derived
    sources: list[str] = []  # several raw columns (for concat)
    parse: Parse = "text"
    transform: Transform | None = None
    args: dict[str, Any] = {}
    const: str | float | bool | None = None
    note: str = ""

    @model_validator(mode="after")
    def _transform_args(self) -> "ColumnMap":
        if self.transform is not None:
            missing = [a for a in TRANSFORMS[self.transform][0] if a not in self.args]
            if missing:
                raise ValueError(f"transform {self.transform} thiếu args {missing}")
        return self


class TableMap(BaseModel):
    target: str  # canonical table
    sources: list[str]  # raw table_ids stacked together (e.g. one sheet per month)
    columns: list[ColumnMap]
    value_maps: dict[str, dict[str, str]] = {}  # canonical column -> raw value -> canonical value (e.g. status)
    row_filter: str = ""  # rows to drop, in words (e.g. "dòng tổng cuối sheet")

    @model_validator(mode="after")
    def _known_target(self) -> "TableMap":
        spec = TABLES.get(self.target)
        if spec is None:
            raise ValueError(f"bảng chuẩn không tồn tại: {self.target}")
        unknown = [c.target for c in self.columns if spec.column(c.target) is None]
        if unknown:
            raise ValueError(f"{self.target}: cột chuẩn không tồn tại {unknown}")
        return self


class ExtraTableSpec(BaseModel):
    name: str
    sources: list[str]
    description: str
    column_notes: dict[str, str] = {}  # raw column -> meaning


class CheckResult(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class Mapping(BaseModel):
    industry: str | None = None  # ngành nhận diện từ README / dữ liệu, để áp luật §6
    record_grain: Literal["order", "line_is_record"] = "order"  # "line_is_record": sổ không có mã đơn (§8)
    tables: list[TableMap] = []
    extra_tables: list[ExtraTableSpec] = []
    checks: list[CheckResult] = []
    confidence: float = 0.0
    notes: list[str] = []

    @property
    def ok(self) -> bool:
        """Usable for answering: has orders and lines, and every check passed."""
        targets = {t.target for t in self.tables}
        return {"orders", "lines"} <= targets and bool(self.checks) and all(c.passed for c in self.checks)
