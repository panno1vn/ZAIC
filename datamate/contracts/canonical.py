"""Canonical schema: the tables every business is mapped into by [B], so the metric functions [D1] work the same
for every shop. A shop fills only the tables and columns it has; information that fits nowhere goes to `extra`.

Canonical values are ASCII codes (order status, payment kind) so code never compares Vietnamese spellings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

ORDER_STATUSES = ("completed", "cancelled", "returned", "delivering")  # hoàn thành, huỷ, trả hàng, đang giao (§8)
PAYMENT_KINDS = ("at_purchase", "debt_payment", "installment", "refund")
DTYPES = ("str", "float", "int", "bool", "date", "datetime")


@dataclass(frozen=True)
class Col:
    name: str
    dtype: str
    required: bool = False
    doc: str = ""


@dataclass(frozen=True)
class TableSpec:
    doc: str
    columns: tuple[Col, ...]

    def column(self, name: str) -> Col | None:
        return next((c for c in self.columns if c.name == name), None)


_SOURCE = Col("source", "str", doc="file::sheet gốc của dòng, để truy vết")

TABLES: dict[str, TableSpec] = {
    "orders": TableSpec("Một dòng mỗi đơn. Sổ không có mã đơn thì mỗi dòng sổ là một lần ghi (§8)", (
        Col("order_id", "str", True, "mã đơn; sổ không có mã thì sinh mã theo dòng"),
        Col("order_time", "datetime", True, "ngày giờ đặt; file chỉ ghi ngày thì giờ là 00:00"),
        Col("has_time", "bool", doc="False khi file chỉ ghi ngày (không xét được ca, giờ cao điểm)"),
        Col("status", "str", True, "một trong ORDER_STATUSES"),
        Col("customer_key", "str", doc="mã khách; shop không có mã thì tên đã chuẩn hoá; khách lẻ để trống"),
        Col("customer_name", "str"),
        Col("customer_group", "str"),
        Col("channel", "str", doc="kênh bán như ghi trên đơn"),
        Col("payment_method", "str", doc="hình thức thanh toán ghi trên đơn"),
        Col("employee", "str", doc="nhân viên bán / thợ"),
        Col("order_discount", "float", doc="tổng giảm giá cả đơn (voucher, điểm, khuyến mãi theo tổng), số dương"),
        Col("voucher_discount", "float", doc="phần giảm nhờ voucher, khi file tách riêng (mẹ và bé, §6)"),
        Col("points_discount", "float", doc="phần giảm nhờ dùng điểm, khi file tách riêng"),
        Col("shipping_fee", "float"),
        Col("vat", "float"),
        Col("trade_in_amount", "float", doc="tiền thu máy cũ trừ vào đơn (điện thoại, §6)"),
        Col("total_due", "float", doc="số khách phải trả cả đơn: sau giảm giá đơn và máy cũ, gồm phí giao"),
        Col("goods_amount", "float", doc="tiền hàng của đơn: cộng thành tiền các dòng (§1 doanh thu một đơn), "
            "trước giảm giá đơn, chưa gồm phí giao; file chỉ có đơn (không dòng hàng) lấy doanh thu từ đây"),
        Col("is_warranty", "bool", doc="phiếu bảo hành, không thu tiền (sửa xe, §6)"),
        Col("vehicle_plate", "str", doc="biển số (sửa xe)"),
        Col("vehicle_model", "str", doc="dòng xe (sửa xe)"),
        Col("services", "str", doc="các việc đã làm, ngăn bằng ' | ' (sửa xe, ô Làm gì)"),
        Col("note", "str"),
        Col("debt_left", "float", doc="còn nợ của đơn tính đến hết ngày cuối dữ liệu, khi shop chỉ ghi tình trạng đó "
            "(README; N100)"),
        Col("due_date", "date", doc="ngày phải trả của đơn bán chịu có hạn (README: hạn thanh toán; N113)"),
        _SOURCE,
    )),
    "lines": TableSpec("Một dòng mỗi dòng hàng của đơn", (
        Col("order_id", "str", True),
        Col("line_no", "int"),
        Col("product_key", "str", True, "mã hàng; không có mã thì tên đã chuẩn hoá"),
        Col("product_name", "str", True, "tên như ghi trong file"),
        Col("product_group", "str"),
        Col("is_item", "bool", doc="False với dòng không phải mặt hàng: phí phục vụ, voucher (§3)"),
        Col("qty", "float", True, "theo đơn vị của dòng; âm nếu là dòng trả"),
        Col("unit", "str"),
        Col("base_qty", "float", doc="số lượng quy về đơn vị cơ bản"),
        Col("unit_price", "float", doc="đơn giá trước chiết khấu dòng"),
        Col("line_discount", "float"),
        Col("line_amount", "float", True, "thành tiền sau giảm giá dòng"),
        Col("unit_cost", "float", doc="giá vốn một đơn vị bán, nếu file ghi trên dòng bán (§5)"),
        _SOURCE,
    )),
    "products": TableSpec("Danh mục hàng", (
        Col("product_key", "str", True), Col("product_name", "str", True), Col("product_group", "str"),
        Col("base_unit", "str"), Col("unit_cost", "float", doc="giá vốn một đơn vị cơ bản ghi trong danh mục"),
        Col("category", "str", doc="loại hàng nếu file ghi: máy mới / máy cũ / phụ kiện…"),
        Col("product_line", "str", doc="dòng máy (điện thoại, §6)"),
        Col("is_prescription", "bool"), Col("active_ingredient", "str"), Col("size", "str"),
        Col("stage", "str", doc="cột Số của sữa (mẹ và bé, §6)"), Col("brand", "str"),
        Col("for_resale", "bool", doc="hàng mua về để bán (khác món pha chế, chế biến)"), _SOURCE,
    )),
    "unit_conversions": TableSpec("Hệ số quy đổi; đơn vị không có dòng nào là đơn vị cơ bản, hệ số 1", (
        Col("product_key", "str", True), Col("unit", "str", True),
        Col("factor", "float", True, "số đơn vị cơ bản trong 1 đơn vị này"),
        Col("base_unit", "str", doc="đơn vị cơ bản của mặt hàng, nếu file ghi"), _SOURCE,
    )),
    "customers": TableSpec("Danh sách khách", (
        Col("customer_key", "str", True), Col("customer_name", "str"), Col("customer_group", "str"),
        Col("phone", "str"), Col("address", "str"), Col("gender", "str"), Col("registered_date", "date"), _SOURCE,
    )),
    "payments": TableSpec("Các khoản khách trả, gồm trả lúc mua, trả nợ, góp", (
        Col("order_id", "str", True), Col("paid_time", "datetime", True), Col("amount", "float", True),
        Col("method", "str"), Col("kind", "str", doc="một trong PAYMENT_KINDS"), _SOURCE,
    )),
    "returns": TableSpec("Phiếu trả hàng", (
        Col("order_id", "str", True), Col("return_time", "datetime"), Col("amount", "float"), Col("reason", "str"),
        _SOURCE,
    )),
    "purchases": TableSpec("Dòng phiếu nhập hàng", (
        Col("receipt_id", "str", True), Col("receipt_time", "datetime", True), Col("supplier", "str"),
        Col("cancelled", "bool"), Col("product_key", "str", True), Col("qty", "float"), Col("unit", "str"),
        Col("base_qty", "float"), Col("unit_cost", "float", doc="giá nhập một đơn vị nhập"),
        Col("amount", "float"), Col("lot_id", "str"), Col("expiry_date", "date"), Col("note", "str"), _SOURCE,
    )),
    "inventory": TableSpec("Tồn kho tại một ngày, theo đơn vị cơ bản", (
        Col("product_key", "str", True), Col("as_of", "date", True), Col("base_qty", "float", True), _SOURCE,
    )),
    "price_history": TableSpec("Bảng giá bán theo ngày áp dụng", (
        Col("product_key", "str", True), Col("effective_date", "date", True),
        Col("price", "float", True, "giá một đơn vị cơ bản"), _SOURCE,
    )),
    "lots": TableSpec("Lô hàng", (
        Col("lot_id", "str", True), Col("product_key", "str", True), Col("expiry_date", "date"),
        Col("base_qty_in", "float"), Col("unit_cost", "float", doc="giá nhập của lô, theo đơn vị cơ bản"),
        Col("receipt_id", "str"), _SOURCE,
    )),
    "lot_sales": TableSpec("Dòng bán lấy từ lô nào", (
        Col("order_id", "str", True), Col("line_no", "int"), Col("lot_id", "str", True), Col("base_qty", "float"),
        Col("returned_base_qty", "float"), _SOURCE,
    )),
    "expenses": TableSpec("Sổ chi phí", (
        Col("expense_date", "date", True), Col("amount", "float", True), Col("category", "str"), _SOURCE,
    )),
    "employees": TableSpec("Nhân viên / thợ", (
        Col("employee_key", "str", True), Col("employee_name", "str"), Col("start_date", "date"),
        Col("commission_pct", "float", doc="phần trăm hoa hồng, trên tổng tiền các phiếu người đó làm trong tháng"),
        _SOURCE,
    )),
    "deliveries": TableSpec("Các đợt giao của đơn (giao nhiều đợt)", (
        Col("order_id", "str", True), Col("delivery_time", "datetime", True), Col("batch_no", "int"),
        Col("product_key", "str", doc="hàng của dòng giao, khi sổ giao ghi theo từng mặt hàng (N130)"),
        Col("base_qty", "float", doc="số lượng giao theo đơn vị cơ bản (N130)"), _SOURCE,
    )),
    "shift_reports": TableSpec("Báo cáo tiền mặt theo ca", (
        Col("report_date", "date", True), Col("shift", "str"), Col("cash_amount", "float"), _SOURCE,
    )),
    "installments": TableSpec("Lịch góp của đơn trả góp (điện thoại, §6); tiền đã góp nằm ở payments", (
        Col("order_id", "str", True), Col("period_no", "int", True), Col("due_date", "date", True),
        Col("amount_due", "float"), _SOURCE,
    )),
    "warranty_visits": TableSpec("Lượt mang máy tới bảo hành (điện thoại, §6)", (
        Col("visit_time", "datetime", True), Col("product_key", "str"), Col("product_line", "str"),
        Col("imei", "str"), Col("order_id", "str"), _SOURCE,
    )),
}


@dataclass
class ExtraTable:
    """A table that fits no canonical table (trả góp, thu máy cũ, sổ sửa xe…): kept as is for the code path [D2]."""
    name: str
    description: str
    frame: pd.DataFrame
    column_notes: dict[str, str] = field(default_factory=dict)


@dataclass
class CanonicalDB:
    """One business after mapping: canonical tables, extra tables and what is known about their coverage."""
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    extra: dict[str, ExtraTable] = field(default_factory=dict)
    industry: str | None = None
    date_ranges: dict[str, tuple[date, date]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    # N38: the topics the README's conventions name ("nhap hang", "cong no"…), folded; None: no conventions section
    conventions: tuple[str, ...] | None = None
    # N100: the day the orders' debt_left holds (the README's last day of data); debts are known on that day only
    debt_snapshot_day: date | None = None
    # N112: the shop's README, for what it records (verify.not_recorded: §7 "shop không ghi loại thông tin")
    readme: str = ""

    def table(self, name: str) -> pd.DataFrame | None:
        df = self.tables.get(name)
        return df if df is not None and len(df) else None

    def has(self, table: str, column: str | None = None) -> bool:
        """True when the table has rows and, if a column is given, that column has at least one value."""
        df = self.table(table)
        if df is None:
            return False
        return column is None or (column in df.columns and df[column].notna().any())


_DTYPE_CHECKS = {"datetime": pd.api.types.is_datetime64_any_dtype, "float": pd.api.types.is_numeric_dtype,
                 "int": pd.api.types.is_numeric_dtype}


def check_frame(name: str, df: pd.DataFrame) -> list[str]:
    """Problems of a canonical table against its spec: unknown table or column, missing required column, bad status."""
    spec = TABLES.get(name)
    if spec is None:
        return [f"bảng chuẩn không tồn tại: {name}"]
    problems = [f"{name}: thiếu cột bắt buộc {c.name}" for c in spec.columns if c.required and c.name not in df.columns]
    problems += [f"{name}: cột lạ {c}" for c in df.columns if spec.column(c) is None]
    for c in spec.columns:  # dates and numbers left as text break every metric downstream
        check = _DTYPE_CHECKS.get(c.dtype)
        if check and c.name in df.columns and df[c.name].notna().any() and not check(df[c.name]):
            problems.append(f"{name}.{c.name}: cần kiểu {c.dtype}, đang là {df[c.name].dtype}")
    if name == "orders" and "status" in df.columns:
        bad = sorted(set(df["status"].dropna()) - set(ORDER_STATUSES))
        if bad:
            problems.append(f"orders: status ngoài {ORDER_STATUSES}: {bad[:5]}")
    if name == "payments" and "kind" in df.columns:
        bad = sorted(set(df["kind"].dropna()) - set(PAYMENT_KINDS))
        if bad:
            problems.append(f"payments: kind ngoài {PAYMENT_KINDS}: {bad[:5]}")
    return problems
