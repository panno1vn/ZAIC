"""N115: stock in a shop that keeps none is unanswerable (§7); N116: lots and the lots each sale took, from the README,
when a mapping moved from an example has none, and stock read from the lots; N117: the README's conversion list when a
moved mapping has none."""
from pathlib import Path

import pandas as pd

from datamate.contracts import CanonicalDB, ColumnMap, Mapping, QueryPlan, RawBusiness, TableMap
from datamate.mapping.from_readme import enrich
from datamate.verify import not_recorded

from test_mapping_readme import section, table

README = "# Dữ liệu\n\n## Cột trong `ban.csv`\n- **Mã đơn**: mã đơn\n- **Hàng**: tên hàng\n"
STOCK = {"intent": "value", "period": {"kind": "today"}, "measures": [{"metric": "stock_qty", "filters": [
    {"field": "product", "value": "Bia Tiger lon"}]}]}


def test_stock_in_a_shop_that_keeps_none_is_unanswerable():
    plan = QueryPlan.model_validate(STOCK)
    q = "hết hôm nay bia tiger còn mấy lon trong kho"
    assert not_recorded(plan, q, CanonicalDB(readme=README)) == "tồn kho"
    # the README names a stock column, or lots, or the mapping found a stock table: recorded
    assert not_recorded(plan, q, CanonicalDB(readme=README + "- **Tồn thực**: tồn kho (đơn vị cơ bản)\n")) is None
    assert not_recorded(plan, q, CanonicalDB(readme=README + "- **Mã lô**: số lô\n")) is None
    inv = pd.DataFrame({"product_key": ["Bia Tiger lon"], "as_of": ["2026-07-01"], "base_qty": [3.0]})
    assert not_recorded(plan, q, CanonicalDB(readme=README, tables={"inventory": inv})) is None


SALES = {"Mã đơn hàng": "mã đơn", "Tên sản phẩm": "tên hàng", "Số lượng sản phẩm": "số lượng",
         "Đơn vị tính": "đơn vị tính"}
GOODS = {"Tên sản phẩm": "tên", "Mã SKU": "mã hàng"}
RECEIPT = {"Mã đơn nhập": "mã phiếu nhập", "Mã SKU": "mã hàng", "Mã lô": "số lô", "Hạn sử dụng": "hạn sử dụng",
           "Số lượng nhập": "số lượng nhập (đơn vị cơ bản)"}
TAKEN = {"Mã đơn hàng": "mã đơn", "Mã lô": "số lô", "Số lượng": "số lượng bán lấy từ lô (đơn vị cơ bản)",
         "Số lượng trả": "số lượng khách trả lại (đơn vị cơ bản)"}
CONV = {"Tên sản phẩm": "tên hàng (file chỉ có mặt hàng có đơn vị lớn)", "Đơn vị quy đổi": "đơn vị lớn",
        "Tỉ lệ quy đổi": "hệ số: số đơn vị cơ bản trong 1 đơn vị lớn", "Đơn vị cơ bản": "đơn vị cơ bản"}


def pharmacy() -> RawBusiness:
    readme = section("ban.csv", SALES) + section("sp.csv", GOODS) + section("nhap.csv", RECEIPT) + \
        section("lo.csv", TAKEN) + section("quydoi.csv", CONV)
    return RawBusiness(root=Path("."), readme=readme, tables=[
        table("ban.csv", [("D1", "Panadol", 2, "viên")], list(SALES)),
        table("sp.csv", [("Panadol", "SP1")], list(GOODS)),
        table("nhap.csv", [("N1", "SP1", "L1", "01/12/2026", 100)], list(RECEIPT)),
        table("lo.csv", [("D1", "L1", 2, 0)], list(TAKEN)),
        table("quydoi.csv", [("Panadol", "hộp", 100, "viên")], list(CONV))])


def moved() -> Mapping:
    """A mapping moved from a shop with orders and lines only."""
    cm = lambda t, s, p="text": ColumnMap(target=t, source=s, parse=p)  # noqa: E731
    return Mapping(tables=[TableMap(target="lines", sources=["ban.csv"], columns=[
        cm("order_id", "Mã đơn hàng"), cm("product_key", "Tên sản phẩm"), cm("product_name", "Tên sản phẩm"),
        cm("qty", "Số lượng sản phẩm", "qty"), cm("unit", "Đơn vị tính")])], notes=["chuyển từ mapping mẫu X"])


def cols(m: Mapping, target: str) -> dict:
    return {c.target: c for c in next(t for t in m.tables if t.target == target).columns}


def test_lots_and_the_conversion_list_the_readme_names_are_added():
    m = enrich(moved(), pharmacy())
    lots, taken, conv = cols(m, "lots"), cols(m, "lot_sales"), cols(m, "unit_conversions")
    assert lots["lot_id"].source == "Mã lô" and lots["expiry_date"].parse == "date" and lots["base_qty_in"].source == "Số lượng nhập"
    # the receipt keys products by SKU, the sales lines by name: the SKU goes through the catalogue
    assert lots["product_key"].transform == "lookup" and lots["product_key"].args["value"] == "Tên sản phẩm"
    assert taken["base_qty"].source == "Số lượng" and taken["returned_base_qty"].source == "Số lượng trả"
    assert conv["product_key"].source == "Tên sản phẩm" and conv["factor"].source == "Tỉ lệ quy đổi"
    assert conv["unit"].source == "Đơn vị quy đổi" and conv["base_unit"].source == "Đơn vị cơ bản"


def test_a_mapping_that_has_them_keeps_its_own():
    m = moved()
    m.tables.append(TableMap(target="unit_conversions", sources=["quydoi.csv"], columns=[
        ColumnMap(target="product_key", source="Tên sản phẩm"), ColumnMap(target="unit", source="Đơn vị quy đổi"),
        ColumnMap(target="factor", source="Tỉ lệ quy đổi", parse="number")]))
    out = enrich(m, pharmacy())
    assert sum(t.target == "unit_conversions" for t in out.tables) == 1


def test_customers_or_debts_in_a_shop_that_records_none_are_unanswerable():
    """N121: no README column about customers / no "nợ" in the README, and nothing mapped."""
    count = QueryPlan.model_validate({"intent": "count_where", "period": {"kind": "month", "year": 2025, "month": 10},
                                      "threshold": {"entity": "customer", "metric": "order_count", "op": "gte",
                                                    "value": 11}})
    q = "Bao nhiêu khách mua ít nhất 11 đơn trong tháng 10 năm 2025?"
    assert not_recorded(count, q, CanonicalDB(readme=README)) == "khách hàng"
    named = README + "- **Khách**: tên khách (Khách lẻ nếu không lưu)\n"
    assert not_recorded(count, q, CanonicalDB(readme=named)) is None
    debt = QueryPlan.model_validate({"intent": "value", "period": {"kind": "this_month"},
                                     "measures": [{"metric": "debt_paid"}]})
    assert not_recorded(debt, "Tháng này thu hồi được bao nhiêu tiền công nợ?", CanonicalDB(readme=README)) == "công nợ"
    assert not_recorded(debt, "Tháng này thu hồi được bao nhiêu tiền công nợ?",
                        CanonicalDB(readme=README + "- **Còn nợ**: tiền khách còn nợ\n")) is None


def test_a_width_written_kho_is_no_stock_column():
    """N115b: "lưới B40 mạ kẽm khổ 1.5m" folds to "kho": stock is named by phrases, not by a single word."""
    plan = QueryPlan.model_validate(STOCK)
    widths = README + "- Lưới B40 mạ kẽm khổ 1.5m: 1 cuộn 10m\n"
    assert not_recorded(plan, "hết hôm nay bia tiger còn mấy lon trong kho", CanonicalDB(readme=widths)) == "tồn kho"
