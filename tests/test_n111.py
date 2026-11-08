"""N111: side tables the README's conventions name (stock, expenses, receipts, unit conversions, drug attributes), for a
mapping moved from an example whose shop kept none; their other columns read from the values. Also the README's own
column for the order's amount due, and the customers' name column named as the catalogue's."""
from pathlib import Path

from datamate.contracts import ColumnMap, Mapping, RawBusiness, TableMap
from datamate.mapping import named_sides as N
from datamate.mapping.from_readme import with_conventions

from test_mapping_readme import table

CONVENTIONS = """# Dữ liệu

## Quy ước
- **Tồn kho**: **Ton kho** là tồn cuối ngày cuối có dữ liệu, theo đơn vị cơ bản.
- **Sổ chi phí**: các khoản chi vận hành theo tháng (tiền **So tien**).
- **Nhập hàng**: **Giá nhập** là giá nhập một đơn vị, theo đơn vị nhập của dòng; **Thành tiền** là tiền nhập của cả dòng.
- **Thuốc**: **Kê đơn** đúng (TRUE/1) là thuốc kê đơn. Hoạt chất ghi không kèm hàm lượng (hàm lượng ở tên hàng); nhiều chất nối bằng " + ".
- **Quy đổi đơn vị**: số lượng ghi theo đơn vị của dòng, hệ số quy đổi ở `quydoi.csv`.
"""
ORDERS = ["Mã HĐ", "Ngày", "TT", "PT", "Tiền hàng"]
LINES = ["Mã HĐ", "Mã hàng", "SL", "ĐVT", "SL lẻ", "Thành tiền"]
PURCHASES = ["Số phiếu", "Ngày nhập", "Nhà cung cấp", "Product", "SL nhập", "ĐVT nhập", "Giá nhập", "Thành tiền", "HSD"]


def cm(target: str, source: str, parse: str = "text") -> ColumnMap:
    return ColumnMap(target=target, source=source, parse=parse)


def core(sales: str = "hd.csv", lines: str = "ct.csv", key: str = "Mã hàng", catalogue: str = "sp.csv",
         name: str = "Tên") -> list[TableMap]:
    return [
        TableMap(target="orders", sources=[sales], columns=[
            cm("order_id", "Mã HĐ"), cm("order_time", "Ngày", "datetime"), cm("status", "TT"), cm("payment_method", "PT"),
            cm("total_due", "Tiền hàng", "money")], value_maps={"status": {"Xong": "completed"}}),
        TableMap(target="lines", sources=[lines], columns=[
            cm("order_id", "Mã HĐ"), cm("product_key", key), cm("product_name", key), cm("qty", "SL", "qty"),
            cm("unit", "ĐVT"), cm("base_qty", "SL lẻ", "qty"), cm("line_amount", "Thành tiền", "money"),
            ColumnMap(target="is_item", const=True)]),
        TableMap(target="products", sources=[catalogue], columns=[cm("product_key", key), cm("product_name", name)])]


def shop(purchases: list[tuple] | None = None) -> RawBusiness:
    return RawBusiness(root=Path("."), readme=CONVENTIONS, tables=[
        table("hd.csv", [("D1", "01/06/2026 10:00", "Xong", "Tiền mặt", 105000),
                         ("D2", "02/06/2026 11:00", "Xong", "Tiền mặt", 5000)], ORDERS),
        table("ct.csv", [("D1", "SP1", 2, "hộp", 20, 100000), ("D1", "SP2", 1, "gói", 1, 5000),
                         ("D2", "SP1", 5, "viên", 5, 5000)], LINES),
        table("sp.csv", [("SP1", "Panadol"), ("SP2", "Oresol")], ["Mã hàng", "Tên"]),
        table("tonkho.csv", [("SP1", 112, "Panadol"), ("SP2", 40, "Oresol")], ["ID SP", "Ton kho", "Hàng hóa"]),
        table("chiphi.csv", [("01/06/2026", "thuê", "5000k", ""), ("02/06/2026", "điện", "300k", "")],
              ["Ngày chi", "Mục", "So tien", "Ghi chú"]),
        table("nhap.csv", purchases or [
            ("PN1", "01/05/2026", "Cty A", "Panadol", 2, "hộp", "198k", "396k", "2026-05-20"),
            ("PN1", "2026-05-01", "Cty A", "Oresol", 3, "hộp", "50k", "150k", "2026-05-25"),  # one day, two spellings
            ("PN2", "03/05/2026", "Cty B", "Panadol", 1, "hộp", "200k", "200k", "2026-05-30"),
            ("PN3", "04/05/2026", "Cty A", "Oresol", 4, "hộp", "52k", "208k", "2026-05-31")], PURCHASES),
        table("thuoc.csv", [("SP1", "Paracetamol + Cafein", "TRUE"), ("SP2", "Glucose", "FALSE")],
              ["Mã HH", "Hoạt chất", "Kê đơn"]),
        table("quydoi.csv", [("SP1", "hộp", 10, 50000), ("SP2", "hộp", 20, 60000)], ["Mã sp", "Đơn vị", "Bằng", "Giá"])])


def cols(m: Mapping, target: str) -> dict:
    return {c.target: c for c in next(t for t in m.tables if t.target == target).columns}


def test_the_conventions_name_their_columns():
    conv = N.named(CONVENTIONS)
    assert N._ref(conv, "ton kho", "la ton cuoi ngay cuoi co du lieu") == (None, "Ton kho")
    assert N._ref(conv, "nhap hang", "la gia nhap mot don vi") == (None, "Giá nhập")
    assert N._ref(conv, "nhap hang", "la tien nhap cua ca dong") == (None, "Thành tiền")
    assert N._ref(conv, "thuoc", "dung (true/1) la thuoc ke don") == (None, "Kê đơn")
    assert conv["so chi phi"][1] == [(None, "So tien", ").")]
    card = N.named("- **Tồn kho**: mỗi dòng `the_kho.TonCuoi` là tồn sau lần nhập/bán/trả đó, theo đơn vị cơ bản.")
    assert N._ref(card, "ton kho", "la ton sau lan") == ("the_kho", "TonCuoi")


def test_the_side_tables_are_read_from_their_values():
    m = N.with_named_sides(Mapping(tables=core(), notes=["chuyển từ mapping mẫu X"]), shop())
    assert m.notes[-1].startswith("bảng phụ theo quy ước README")
    inv = cols(m, "inventory")
    assert inv["product_key"].source == "ID SP" and inv["base_qty"].source == "Ton kho"
    assert inv["as_of"].const == "2026-06-02"  # the last day (transfer._settle_constants)
    exp = cols(m, "expenses")
    assert (exp["expense_date"].source, exp["amount"].source, exp["category"].source) == ("Ngày chi", "So tien", "Mục")
    pur = cols(m, "purchases")
    assert pur["qty"].source == "SL nhập" and pur["unit_cost"].source == "Giá nhập" and pur["amount"].source == "Thành tiền"
    assert pur["receipt_id"].source == "Số phiếu" and pur["receipt_time"].source == "Ngày nhập"  # not the expiry
    assert pur["supplier"].source == "Nhà cung cấp" and pur["unit"].source == "ĐVT nhập"
    # the notebook writes the product's name: translated into the lines' code through the catalogue
    key = pur["product_key"]
    assert key.source == "Product" and key.transform == "lookup"
    assert key.args == {"table": "sp.csv", "key": "Tên", "value": "Mã hàng", "keep_missing": False, "fold": True}
    conv = cols(m, "unit_conversions")
    assert (conv["product_key"].source, conv["unit"].source, conv["factor"].source) == ("Mã sp", "Đơn vị", "Bằng")
    prod = cols(m, "products")
    assert prod["is_prescription"].args["table"] == "thuoc.csv" and prod["is_prescription"].parse == "bool"
    assert prod["active_ingredient"].args["value"] == "Hoạt chất" and prod["active_ingredient"].args["key"] == "Mã HH"


def test_receipts_keyed_otherwise_than_the_lines_are_read_again():
    base = core() + [TableMap(target="purchases", sources=["nhap.csv"], columns=[
        cm("receipt_id", "Số phiếu"), cm("receipt_time", "Ngày nhập", "datetime"), cm("product_key", "Product"),
        cm("qty", "SL nhập", "qty")])]
    m = N.with_named_sides(Mapping(tables=base), shop())
    assert cols(m, "purchases")["product_key"].transform == "lookup"
    assert sum(t.target == "purchases" for t in m.tables) == 1


def test_no_guess_when_the_quantity_does_not_give_the_money():
    rows = [("PN1", "01/05/2026", "Cty A", "Panadol", 2, "hộp", "198k", "999k", "2026-05-20"),
            ("PN2", "03/05/2026", "Cty B", "Oresol", 1, "hộp", "200k", "1k", "2026-05-30")]
    assert N.purchases(N._Shop(Mapping(tables=core()), shop(rows)), N.named(CONVENTIONS)) is None


POS = """## Quy ước
- **Nhập hàng**: `chi_tiet_nhap.DonGiaNhap` là giá nhập một đơn vị, theo đơn vị nhập của dòng; `phieu_nhap.TongGiaTriNhap` là tổng tiền của cả phiếu nhập.
- **Tồn kho**: mỗi dòng `the_kho.TonCuoi` là tồn sau lần nhập/bán/trả đó, theo đơn vị cơ bản; tồn tại một thời điểm là tồn ở dòng cuối của sản phẩm tính đến thời điểm đó.
"""


def pos(statuses=("received", "received")) -> RawBusiness:
    t = lambda name, rows, columns: table("pos.sqlite::" + name, rows, columns)  # noqa: E731
    return RawBusiness(root=Path("."), readme=POS, tables=[
        t("don_hang", [("D1", "01/06/2026 10:00", "Xong", "cash", 105000)], ORDERS),
        t("chi_tiet_don", [("D1", "SP1", 2, "hộp", 20, 100000), ("D1", "SP2", 1, "gói", 1, 5000)],
          ["Mã HĐ", "MaHangHoa", "SL", "ĐVT", "SL lẻ", "Thành tiền"]),
        t("san_pham", [("SP1", "Panadol"), ("SP2", "Oresol")], ["MaHangHoa", "TenGoi"]),
        t("phieu_nhap", [("biz", "PN1", "NCC1", "2026-05-01", statuses[0], 546000),
                         ("biz", "PN2", "NCC2", "2026-05-03", statuses[1], 200000)],
          ["IDCuaHang", "MaPhieuNhap", "MaNhaCungCap", "NgayNhapKho", "TinhTrang", "TongGiaTriNhap"]),
        t("chi_tiet_nhap", [("biz", "PN1", 1, "SP1", "hộp", 2, 198000), ("biz", "PN1", 2, "SP2", "hộp", 3, 50000),
                            ("biz", "PN2", 1, "SP1", "hộp", 1, 200000)],
          ["IDCuaHang", "MaPhieuNhap", "SoThuTu", "MaHangHoa", "DonViTinh", "SL", "DonGiaNhap"]),
        t("the_kho", [("SP1", "2026-05-01 06:00:00", 20, 20), ("SP1", "2026-06-01 10:00:00", -20, 0)],
          ["MaHangHoa", "NgayGioPhatSinh", "SLQuyDoi", "TonCuoi"])])


def pos_core() -> list[TableMap]:
    tables = core("pos.sqlite::don_hang", "pos.sqlite::chi_tiet_don", "MaHangHoa", "pos.sqlite::san_pham", "TenGoi")
    return tables


def test_receipt_lines_take_their_day_and_supplier_from_the_receipt_named_with_the_total():
    m = N.with_named_sides(Mapping(tables=pos_core()), pos())
    pur = cols(m, "purchases")
    assert pur["receipt_id"].source == "MaPhieuNhap" and pur["qty"].source == "SL"  # Σ SL × giá = tổng phiếu
    assert pur["receipt_time"].args == {"table": "pos.sqlite::phieu_nhap", "key": "MaPhieuNhap", "value": "NgayNhapKho",
                                        "keep_missing": False}
    assert pur["supplier"].args["value"] == "MaNhaCungCap" and pur["unit"].source == "DonViTinh"
    inv = cols(m, "inventory")  # the stock card: each row the stock after one movement, dated by its own column
    assert inv["as_of"].source == "NgayGioPhatSinh" and inv["base_qty"].source == "TonCuoi"


def test_receipts_of_several_statuses_are_left_out():
    m = N.with_named_sides(Mapping(tables=pos_core()), pos(("received", "cancelled")))
    assert "purchases" not in {t.target for t in m.tables}


def test_the_readme_names_the_order_amount_due():
    readme = "## Quy ước\n- **Công nợ**: mỗi lần khách trả tiền cho một đơn là một dòng, `thanh_toan.SoTien` là số tiền " \
             "trả lần đó; `don_hang.TongThanhToan` là số khách phải trả cho cả đơn.\n"
    raw = RawBusiness(root=Path("."), readme=readme, tables=[
        table("don_hang.csv", [("D1", "01/06/2026", "Xong", "cash", 545000, 535000)], ORDERS + ["TongThanhToan"])])
    orders = TableMap(target="orders", sources=["don_hang.csv"], columns=[
        cm("order_id", "Mã HĐ"), cm("order_time", "Ngày"), cm("status", "TT"), cm("payment_method", "PT"),
        cm("total_due", "Tiền hàng", "money")])
    m = with_conventions(Mapping(tables=[orders]), raw)
    assert cols(m, "orders")["total_due"].source == "TongThanhToan"


def test_the_customers_name_is_the_column_named_as_the_products():
    raw = pos()
    raw.tables.append(table("pos.sqlite::khach_hang", [("KH1", "An", "lẻ")], ["MaKhachHang", "TenGoi", "Loai"]))
    tables = pos_core() + [TableMap(target="customers", sources=["pos.sqlite::khach_hang"],
                                    columns=[cm("customer_key", "MaKhachHang"), cm("customer_group", "Loai")])]
    shop_ = N._Shop(Mapping(tables=tables), raw)
    assert [c.source for c in N.customer_names(shop_)] == ["TenGoi"]
