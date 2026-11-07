"""N29: the attribute columns the README names that a mapping (moved from an example's shop that did not record them)
leaves out are added: on the orders by their own column or by the customer code; on the catalogue by its own column or
by the product code from a drug list."""
from pathlib import Path

from datamate.contracts import ColumnMap, Mapping, RawBusiness, TableMap
from datamate.mapping.from_readme import enrich

from test_mapping_readme import section, table

ORDERS = {"Mã HĐ": "mã đơn", "Ngày": "ngày bán", "TT": "trạng thái đơn", "Mã KH": "mã khách (trống nếu khách lẻ)",
          "Tên KH": "tên khách", "NV": "mã nhân viên bán", "HTTT": "hình thức thanh toán của đơn"}
CLIENTS = {"Mã KH": "mã khách", "Tên": "tên", "Nhóm": "nhóm khách"}
GOODS = {"Mã hàng": "mã hàng", "Tên hàng": "tên", "Nhóm hàng": "nhóm hàng"}
DRUGS = {"Mã hàng": "mã hàng", "Hoạt chất": "hoạt chất (trống với thực phẩm chức năng)", "Kê đơn": "thuốc kê đơn"}


def shop() -> RawBusiness:
    readme = section("hd.csv", ORDERS) + section("kh.csv", CLIENTS) + section("sp.csv", GOODS) + \
        section("thuoc.csv", DRUGS)
    return RawBusiness(root=Path("."), readme=readme, tables=[
        table("hd.csv", [("D1", "01/06/2026", "Xong", "KH1", "An", "NV1", "Tiền mặt")], list(ORDERS)),
        table("kh.csv", [("KH1", "An", "sỉ")], list(CLIENTS)),
        table("sp.csv", [("SP1", "Panadol", "giảm đau")], list(GOODS)),
        table("thuoc.csv", [("SP1", "Paracetamol", "TRUE")], list(DRUGS))])


def moved(customer_key: str = "Mã KH") -> Mapping:
    """What a mapping moved from a shop without these attributes reads."""
    cm = lambda t, s: ColumnMap(target=t, source=s)  # noqa: E731
    return Mapping(tables=[
        TableMap(target="orders", sources=["hd.csv"], columns=[cm("order_id", "Mã HĐ"), cm("order_time", "Ngày"),
                                                                 cm("status", "TT"), cm("customer_key", customer_key)]),
        TableMap(target="products", sources=["sp.csv"], columns=[cm("product_key", "Mã hàng"),
                                                                   cm("product_name", "Tên hàng")])],
        notes=["chuyển từ mapping mẫu X"])


def cols(m: Mapping, target: str) -> dict:
    return {c.target: c for c in next(t for t in m.tables if t.target == target).columns}


def test_attributes_the_readme_names_are_added():
    m = enrich(moved(), shop())
    orders, products = cols(m, "orders"), cols(m, "products")
    assert orders["employee"].source == "NV" and orders["payment_method"].source == "HTTT"
    group = orders["customer_group"]
    assert group.transform == "lookup" and group.source == "Mã KH"
    assert group.args == {"table": "kh.csv", "key": "Mã KH", "value": "Nhóm", "keep_missing": False}
    assert products["product_group"].source == "Nhóm hàng"
    assert products["active_ingredient"].args["table"] == "thuoc.csv" and products["active_ingredient"].args["value"] == "Hoạt chất"
    assert products["is_prescription"].parse == "bool" and products["is_prescription"].args["value"] == "Kê đơn"
    assert m.notes[0] == "chuyển từ mapping mẫu X" and m.notes[-1].startswith("bổ sung từ README")


def test_a_column_the_mapping_reads_is_kept_and_a_name_key_is_no_code_to_look_up_by():
    base = moved(customer_key="Tên KH")
    base.tables[0].columns.append(ColumnMap(target="payment_method", source="TT"))
    m = enrich(base, shop())
    orders = cols(m, "orders")
    assert orders["payment_method"].source == "TT"  # what the mapping read stays
    assert "customer_group" not in orders  # orders keyed by name: the customer list's code cannot be matched


LINES = {"Mã HĐ": "mã đơn", "Mã hàng": "mã hàng", "SL": "số lượng", "Tiền": "thành tiền sau giảm"}


def test_a_mapping_without_catalogue_gets_the_readmes_when_the_lines_carry_its_code():
    raw = shop()
    raw.readme += section("ct.csv", LINES)
    raw.tables.append(table("ct.csv", [("D1", "SP1", 2, 20_000)], list(LINES)))
    cm = lambda t, s: ColumnMap(target=t, source=s)  # noqa: E731
    base = Mapping(tables=[moved().tables[0], TableMap(target="lines", sources=["ct.csv"], columns=[
        cm("order_id", "Mã HĐ"), cm("product_key", "Mã hàng"), cm("product_name", "Mã hàng"), cm("qty", "SL"),
        cm("line_amount", "Tiền")])])
    products = cols(enrich(base, raw), "products")
    assert products["product_key"].source == "Mã hàng" and products["product_name"].source == "Tên hàng"
    assert products["product_group"].source == "Nhóm hàng"
    assert products["active_ingredient"].args["table"] == "thuoc.csv" and products["is_prescription"].parse == "bool"


def test_a_shop_whose_readme_describes_no_column_is_left_alone():
    raw = shop()
    raw.readme = "# Dữ liệu\n"
    assert enrich(moved(), raw) == moved()


CONVENTIONS = ("# Dữ liệu\n\n## Quy ước\n- Dữ liệu có đến hết 02/06/2026.\n"
               "- **Công nợ**: mỗi lần khách trả tiền cho một đơn là một dòng, **Giá trị** là số tiền trả lần đó; "
               "**Tổng sau giảm giá** là số khách phải trả cho cả đơn.\n"
               "- **Giá vốn**: **Giá vốn** là giá vốn một đơn vị bán.\n")


def ledger_shop(payments: list[tuple] | None = None, two_layouts: bool = False) -> RawBusiness:
    pay = payments or [("PT1", "01/06/2026 09:00", "D1", "Tiền mặt", "50.000đ"),
                       ("PT2", "02/06/2026 10:00", "D2", "Chuyển khoản", "20.000đ")]
    tables = [
        table("HoaDon.xlsx::Sheet1", [("D1", "01/06/2026", "Xong", "50,000", "Tiền mặt"),
                                      ("D2", "02/06/2026", "Xong", "30,000", "Ghi nợ"),
                                      ("D3", "02/06/2026", "Xong", "10,000", "Chuyển khoản")],
              ["Mã hóa đơn", "Thời gian", "Trạng thái", "Tổng sau giảm giá", "Phương thức thanh toán"]),
        table("ChiTiet.xlsx::Sheet1", [("D1", "Bánh", 1, "50,000", "30,000")],
              ["Mã hóa đơn", "Tên hàng", "Số lượng", "Thành tiền", "Giá vốn"]),
        table("SoQuy.xlsx::Sheet1", pay, ["Mã phiếu", "Thời gian", "Mã hóa đơn", "Phương thức thanh toán", "Giá trị"])]
    if two_layouts:
        tables.append(table("SoQuy2.xlsx::Sheet1", [("D1", "50.000đ")], ["Mã hóa đơn", "Giá trị"]))
    return RawBusiness(root=Path("."), readme=CONVENTIONS, tables=tables)


def moved_sales() -> Mapping:
    cm = lambda t, s: ColumnMap(target=t, source=s)  # noqa: E731
    return Mapping(tables=[
        TableMap(target="orders", sources=["HoaDon.xlsx::*"], columns=[
            cm("order_id", "Mã hóa đơn"), cm("order_time", "Thời gian"), cm("status", "Trạng thái")]),
        TableMap(target="lines", sources=["ChiTiet.xlsx::Sheet1"], columns=[
            cm("order_id", "Mã hóa đơn"), cm("product_name", "Tên hàng"), cm("qty", "Số lượng"),
            cm("line_amount", "Thành tiền")])], notes=["chuyển từ mapping mẫu X"])


def test_the_readme_conventions_name_the_columns_of_debts_and_cost():
    """N35: a mapping moved from a shop without a payment ledger had no debts and no cost of sales, though the
    README's conventions name the columns (train: two shops, 44 questions, 05/11)."""
    from datamate.mapping.from_readme import conventions
    assert conventions(CONVENTIONS) == {"paid_amount": "Giá trị", "total_due": "Tổng sau giảm giá",
                                        "line_cost": "Giá vốn"}
    assert conventions("- **Công nợ**: `thanh_toan.SoTienThu` là số tiền trả lần đó; `don_hang.TongThanhToan` là số "
                       "khách phải trả cho cả đơn.") == {"paid_amount": "SoTienThu", "total_due": "TongThanhToan"}
    m = enrich(moved_sales(), ledger_shop())
    assert cols(m, "orders")["total_due"].source == "Tổng sau giảm giá"
    assert cols(m, "orders")["payment_method"].source == "Phương thức thanh toán"  # values read as payment methods
    assert cols(m, "lines")["unit_cost"].source == "Giá vốn"
    pay = cols(m, "payments")
    assert {k: c.source for k, c in pay.items()} == {"order_id": "Mã hóa đơn", "paid_time": "Thời gian",
                                                     "amount": "Giá trị", "method": "Phương thức thanh toán"}
    assert "bổ sung từ quy ước README" in m.notes[-1]


def test_no_payments_are_guessed():
    # the amount in two layouts of tables: which one is the ledger is not known
    assert not any(t.target == "payments" for t in enrich(moved_sales(), ledger_shop(two_layouts=True)).tables)
    # order ids not found among the orders: not this shop's payments of orders
    stray = [("PT1", "01/06/2026 09:00", "X9", "Tiền mặt", "50.000đ"), ("PT2", "02/06/2026", "X8", "Tiền mặt", "1đ")]
    assert not any(t.target == "payments" for t in enrich(moved_sales(), ledger_shop(stray)).tables)
    # no conventions in the README: nothing added
    bare = ledger_shop()
    bare.readme = "# Dữ liệu\n"
    assert enrich(moved_sales(), bare).tables == moved_sales().tables


LEDGER = {"Số HĐ": "mã đơn", "Tên hàng": "tên hàng", "SL": "số lượng", "TT": "thành tiền"}
LIST = {"Tên hàng": "tên hàng", "Nhóm": "nhóm hàng"}


def lines_only(readme_lines: bool = True, group_on_lines: bool = False) -> tuple[RawBusiness, Mapping]:
    """A shop whose mapping has orders and lines only, its groups on the lines or in a catalogue it left out."""
    line_cols = dict(LEDGER, **({"Phân loại": "nhóm hàng"} if group_on_lines else {}))
    readme = (section("ct.csv", line_cols) if readme_lines else "") + section("dm.csv", LIST)
    rows = [("H1", "Sữa bột Abc 800g", 1, "500.000") + (("sữa bột",) if group_on_lines else ())]
    raw = RawBusiness(root=Path("."), readme=readme, tables=[
        table("ct.csv", rows, list(line_cols)), table("dm.csv", [("sữa bột abc 800G", "sữa bột")], list(LIST))])
    cm = lambda t, s: ColumnMap(target=t, source=s)  # noqa: E731
    m = Mapping(tables=[TableMap(target="lines", sources=["ct.csv"], columns=[
        cm("order_id", "Số HĐ"), cm("product_key", "Tên hàng"), cm("product_name", "Tên hàng")])])
    return raw, m


def test_a_mapping_without_groups_takes_the_lines_own_or_the_catalogues_by_name():
    """Public 06/11: four shops whose README names "nhóm hàng" had no group in their mapping (30 questions by group
    abstained): on the lines ("Phân loại: nhóm hàng"), or in a catalogue joined by the product name, however written."""
    raw, m = lines_only(group_on_lines=True)
    assert cols(enrich(m, raw), "lines")["product_group"].source == "Phân loại"
    raw, m = lines_only()
    g = cols(enrich(m, raw), "lines")["product_group"]
    assert g.transform == "lookup" and g.args["key"] == "Tên hàng" and g.args["value"] == "Nhóm" and g.args["fold"]
    raw, m = lines_only(readme_lines=False)  # the lines' file undescribed: the catalogue column of the same header
    assert cols(enrich(m, raw), "lines")["product_group"].transform == "lookup"


def test_lines_keyed_by_name_take_the_drug_list_through_the_catalogue_code():
    """Public 06/11: a pharmacy whose sales lines carry the product name, its drug list keyed by SKU ("Thuốc kê đơn"):
    a catalogue keyed by the name, the drug columns read by the catalogue's own SKU, no base unit added."""
    readme = section("sp.csv", {"Mã SKU": "mã hàng", "Tên sản phẩm": "tên", "Đơn vị": "đơn vị cơ bản"}) + \
        section("thuoc.csv", {"Mã SKU": "mã hàng", "Hoạt chất": "hoạt chất", "Thuốc kê đơn": "thuốc kê đơn"})
    raw = RawBusiness(root=Path("."), readme=readme, tables=[
        table("ct.csv", [("D1", "Panadol", 2, 20_000)], ["Mã đơn", "Tên sản phẩm", "SL", "Tiền"]),
        table("sp.csv", [("SP1", "Panadol", "viên")], ["Mã SKU", "Tên sản phẩm", "Đơn vị"]),
        table("thuoc.csv", [("SP1", "Paracetamol", "False")], ["Mã SKU", "Hoạt chất", "Thuốc kê đơn"])])
    cm = lambda t, s: ColumnMap(target=t, source=s)  # noqa: E731
    m = Mapping(tables=[TableMap(target="lines", sources=["ct.csv"], columns=[
        cm("order_id", "Mã đơn"), cm("product_key", "Tên sản phẩm"), cm("product_name", "Tên sản phẩm")])])
    products = cols(enrich(m, raw), "products")
    assert products["product_key"].source == "Tên sản phẩm" and "base_unit" not in products
    assert products["is_prescription"].args["table"] == "thuoc.csv" and products["is_prescription"].source == "Mã SKU"


def test_the_readme_base_quantity_column_is_the_base_quantity_not_the_line_quantity():
    """A train shop moved from an example read "Quy ra ĐV lẻ: số lượng đã đổi ra đơn vị cơ bản" as the line's quantity
    beside the line's own unit ("thùng"): the README's base column is base_qty, its "số lượng" column the quantity."""
    cols_ = {"Số CT": "mã đơn", "S.L": "số lượng", "Quy ra ĐV lẻ": "số lượng đã đổi ra đơn vị cơ bản",
             "ĐV tính": "đơn vị tính"}
    raw = RawBusiness(root=Path("."), readme=section("ct.csv", cols_),
                      tables=[table("ct.csv", [("D1", 1, 24, "thùng")], list(cols_))])
    cm = lambda t, s: ColumnMap(target=t, source=s)  # noqa: E731
    m = Mapping(tables=[TableMap(target="lines", sources=["ct.csv"], columns=[
        cm("order_id", "Số CT"), cm("qty", "Quy ra ĐV lẻ"), cm("unit", "ĐV tính")])])
    lines = cols(enrich(m, raw), "lines")
    assert lines["qty"].source == "S.L" and lines["base_qty"].source == "Quy ra ĐV lẻ"
