"""N23: a mapping built from what the README says of each column (datamate/mapping/from_readme.py)."""
from pathlib import Path

import pandas as pd

from datamate.contracts import RawBusiness, RawTable
from datamate.mapping.from_readme import map_from_readme


def table(table_id: str, rows: list[tuple], columns: list[str]) -> RawTable:
    file, _, sheet = table_id.partition("::")
    return RawTable(table_id=table_id, file=file, sheet=sheet or None, frame=pd.DataFrame(rows, columns=columns))


def section(name: str, notes: dict[str, str]) -> str:
    return f"## Cột trong `{name}`\n" + "".join(f"- **{c}**: {m}\n" for c, m in notes.items()) + "\n"


LEDGER = {"Bill": "mã đơn", "Ngày": "ngày bán", "TT": "trạng thái đơn", "Hàng": "tên hàng", "SL": "số lượng",
          "Tiền": "thành tiền sau giảm (đ)", "Khách": "tên khách"}


def columns(m, target: str) -> dict:
    tm = next(t for t in m.tables if t.target == target)
    return {c.target: c for c in tm.columns}


def test_a_flat_export_gives_orders_and_lines_from_one_file():
    rows = [("B1", "01/06/2026", "Xong", "Mì", 2, 10_000, "An"), ("B1", "01/06/2026", "Xong", "Kẹo", 1, 5_000, "An"),
            ("B2", "02/06/2026", "Đã hủy", "Mì", 1, 5_000, "Bình")]
    shop = RawBusiness(root=Path("."), readme=section("ban.csv", LEDGER),
                       tables=[table("ban.csv", rows, list(LEDGER))])
    m, why = map_from_readme(shop)
    assert m is not None, why
    assert m.record_grain == "order"
    orders, lines = columns(m, "orders"), columns(m, "lines")
    assert orders["order_id"].source == "Bill" and orders["order_time"].source == "Ngày"
    assert orders["status"].transform == "order_status_from_lines"  # the status is written on every line
    assert orders["customer_key"].source == orders["customer_name"].source == "Khách"
    assert lines["line_amount"].source == "Tiền" and lines["qty"].parse == "qty"
    status = next(t for t in m.tables if t.target == "orders").value_maps["status"]
    assert status == {"Xong": "completed", "Đã hủy": "cancelled"}


def test_a_ledger_without_order_ids_takes_each_line_for_an_order():
    notes = {k: v for k, v in LEDGER.items() if k not in ("Bill", "Khách")}
    rows = [("01/06/2026", "Xong", ["Mì", "Kẹo", "Bánh"][i % 3], 1, 5_000) for i in range(30)]
    shop = RawBusiness(root=Path("."), readme=section("SoBanHang.xlsx", notes),
                       tables=[table("SoBanHang.xlsx::Sheet1", rows, list(notes))])
    m, why = map_from_readme(shop)
    assert m is not None, why
    assert m.record_grain == "line_is_record"
    assert columns(m, "orders")["order_id"].source == columns(m, "lines")["order_id"].source == "_row"


def test_lines_with_a_product_code_take_its_name_from_the_catalogue():
    readme = (section("don.csv", {"Mã": "mã đơn", "Ngày": "ngày bán", "TT": "trạng thái đơn", "KH": "mã khách"})
              + section("chi_tiet.csv", {"Mã đơn": "mã đơn", "SKU": "mã hàng", "SL": "số lượng",
                                         "TT": "thành tiền sau giảm"})
              + section("san_pham.csv", {"SKU": "mã hàng", "Tên": "tên", "Nhóm": "nhóm hàng"}))
    shop = RawBusiness(root=Path("."), readme=readme, tables=[
        table("don.csv", [("D1", "01/06/2026", "Xong", "K1"), ("D2", "01/06/2026", "Xong", "K2")],
              ["Mã", "Ngày", "TT", "KH"]),
        table("chi_tiet.csv", [("D1", "S1", 1, 10), ("D1", "S2", 1, 10), ("D2", "S1", 2, 20), ("D2", "S1", 1, 10)],
              ["Mã đơn", "SKU", "SL", "TT"]),
        table("san_pham.csv", [("S1", "Mì", "Khô"), ("S2", "Kẹo", "Ngọt")], ["SKU", "Tên", "Nhóm"])])
    m, why = map_from_readme(shop)
    assert m is not None, why
    name = columns(m, "lines")["product_name"]
    assert name.transform == "lookup" and name.args["table"] == "san_pham.csv" and name.args["value"] == "Tên"
    assert columns(m, "orders")["status"].transform is None  # the orders' own file: its status as written
    assert columns(m, "products")["product_group"].source == "Nhóm"


def test_sheets_the_readme_describes_one_by_one_are_tables_of_their_own():
    """04/11: one workbook of four sheets was one group of unlike layouts, left out whole."""
    sales = {"Ngày": "ngày bán", "Mã đơn hàng": "mã đơn", "Tên": "tên hàng", "SL": "số lượng",
             "Thành tiền": "thành tiền sau giảm", "Trạng thái": "trạng thái đơn"}
    readme = section("So_chi_tiet", sales) + section("Danh muc", {"Mã": "mã hàng", "Tên": "tên hàng"})
    rows = [("01/06/2026", "D1", "Mì", 1, 5, "Xong"), ("01/06/2026", "D1", "Kẹo", 1, 5, "Xong")]
    shop = RawBusiness(root=Path("."), readme=readme, tables=[
        table("BaoCao.xlsx::So_chi_tiet", rows, list(sales)),
        table("BaoCao.xlsx::Danh muc", [("S1", "Mì")], ["Mã", "Tên"])])
    m, why = map_from_readme(shop)
    assert m is not None, why
    assert next(t for t in m.tables if t.target == "lines").sources == ["BaoCao.xlsx::So_chi_tiet"]


def test_no_guess_between_two_tables_that_both_read_as_sales_lines():
    readme = section("a.csv", LEDGER) + section("b.csv", LEDGER)
    rows = [("B1", "01/06/2026", "Xong", "Mì", 1, 5, "An")]
    shop = RawBusiness(root=Path("."), readme=readme, tables=[
        table("a.csv", rows, list(LEDGER)), table("b.csv", rows, list(LEDGER))])
    m, why = map_from_readme(shop)
    assert m is None and "dòng hàng" in why


def test_two_parts_of_one_ledger_are_one_table_even_with_a_section_each():
    """04/11: "SoBanHang_1.xlsx" and "SoBanHang_2026.xlsx", one README section each, made two sales tables."""
    readme = section("SoBanHang_1.xlsx", LEDGER) + section("SoBanHang_2026.xlsx", LEDGER)
    rows = [("B1", "01/06/2026", "Xong", "Mì", 1, 5, "An"), ("B1", "01/06/2026", "Xong", "Kẹo", 1, 5, "An")]
    shop = RawBusiness(root=Path("."), readme=readme, tables=[
        table("SoBanHang_1.xlsx::Thang 05", rows, list(LEDGER)), table("SoBanHang_2026.xlsx::Thang 06", rows, list(LEDGER))])
    m, why = map_from_readme(shop)
    assert m is not None, why
    assert next(t for t in m.tables if t.target == "lines").sources == ["SoBanHang_1.xlsx::Thang 05",
                                                                        "SoBanHang_2026.xlsx::Thang 06"]


def test_an_hour_column_holding_full_dates_is_the_order_time():
    notes = {**LEDGER, "Giờ": "giờ đặt đơn (dòng trả hàng: lúc trả)"}
    rows = [("B1", "01/06/2026", "Xong", "Mì", 1, 5, "An", "2026-06-01 08:15:00")]
    shop = RawBusiness(root=Path("."), readme=section("ban.csv", notes), tables=[table("ban.csv", rows * 2, list(notes))])
    assert columns(map_from_readme(shop)[0], "orders")["order_time"].source == "Giờ"
    shop.tables[0].frame["Giờ"] = "08:15"  # an hour alone: the day column
    assert columns(map_from_readme(shop)[0], "orders")["order_time"].source == "Ngày"


def test_receipts_take_their_day_from_the_receipt_table_and_not_from_a_lot_table():
    readme = (section("ban.csv", LEDGER)
              + section("NhapHang.xlsx", {"Mã NH": "mã phiếu nhập", "Thời gian": "ngày nhập", "NCC": "mã nhà cung cấp",
                                          "Trạng thái": "trạng thái phiếu nhập"})
              + section("ChiTietNhap.xlsx", {"Mã NH": "mã phiếu nhập", "Hàng": "tên hàng", "SL": "số lượng",
                                             "Giá": "giá nhập một đơn vị"})
              + section("Lo.xlsx", {"Mã NH": "mã phiếu nhập", "Hàng": "tên hàng", "SL": "số lượng nhập"}))
    rows = [("B1", "01/06/2026", "Xong", "Mì", 1, 5, "An"), ("B1", "01/06/2026", "Xong", "Kẹo", 1, 5, "An")]
    head = table("NhapHang.xlsx::Sheet1", [("N1", "01/05/2026", "C1", "Đã nhập hàng")],
                 ["Mã NH", "Thời gian", "NCC", "Trạng thái"])
    shop = RawBusiness(root=Path("."), readme=readme, tables=[
        table("ban.csv", rows, list(LEDGER)), head,
        table("ChiTietNhap.xlsx::Sheet1", [("N1", "Mì", 10, 4)], ["Mã NH", "Hàng", "SL", "Giá"]),
        table("Lo.xlsx::Sheet1", [("N1", "Mì", 10)], ["Mã NH", "Hàng", "SL"])])
    bought = columns(map_from_readme(shop)[0], "purchases")
    assert bought["receipt_time"].args["table"] == "NhapHang.xlsx::Sheet1" and bought["receipt_time"].parse == "datetime"
    assert bought["unit_cost"].source == "Giá" and bought["supplier"].args["value"] == "NCC"
    head.frame.loc[0, "Trạng thái"] = "Đã hủy"  # a receipt that may be cancelled: no purchases rather than a guess
    assert "purchases" not in [t.target for t in map_from_readme(shop)[0].tables]
