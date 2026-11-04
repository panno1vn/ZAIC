"""T5: a hand mapping moved onto a shop of the same export format (datamate/mapping/transfer.py), on two tiny shops."""
from datetime import datetime
from pathlib import Path

import pandas as pd

from datamate.contracts import Mapping, RawBusiness, RawTable
from datamate.mapping import transfer
from datamate.mapping.build import build_canonical, run_checks

EXAMPLE = Mapping.model_validate({
    "industry": "tạp hóa",
    "tables": [
        {"target": "orders", "sources": ["HoaDon.xlsx::*"], "columns": [
            {"target": "order_id", "source": "Mã HĐ"},
            {"target": "order_time", "source": "Thời gian", "parse": "datetime"},
            {"target": "has_time", "const": True},
            {"target": "status", "source": "Trạng thái"},
            {"target": "channel", "source": "Kênh bán"}],
         "value_maps": {"status": {"Xong": "completed", "Đã hủy": "cancelled"}}},
        {"target": "lines", "sources": ["ChiTiet.xlsx::Sheet1"], "columns": [
            {"target": "order_id", "source": "Mã HĐ"},
            {"target": "product_key", "source": "Tên hàng"},
            {"target": "product_name", "source": "Tên hàng"},
            {"target": "qty", "source": "SL", "parse": "qty"},
            {"target": "line_amount", "source": "Thành tiền", "parse": "money"}]},
        {"target": "inventory", "sources": ["TonKho.xlsx::Sheet1"], "columns": [
            {"target": "product_key", "source": "Hàng"},
            {"target": "as_of", "const": "2026-06-24", "parse": "date"},
            {"target": "base_qty", "source": "Tồn", "parse": "qty"}]},
    ]})
LAYOUT = {"HoaDon.xlsx::T01": ("Mã HĐ", "Thời gian", "Trạng thái", "Kênh bán"),
          "ChiTiet.xlsx::Sheet1": ("Mã HĐ", "Tên hàng", "SL", "Thành tiền"),
          "TonKho.xlsx::Sheet1": ("Hàng", "Tồn")}
EX = transfer.Example("mau", EXAMPLE, LAYOUT)


def table(table_id: str, rows: list[tuple], columns: list[str]) -> RawTable:
    file, sheet = table_id.split("::")
    return RawTable(table_id=table_id, file=file, sheet=sheet, frame=pd.DataFrame(rows, columns=columns))


def new_shop(extra_order_table: bool = False) -> RawBusiness:
    orders = [("HD1", "01/06/2026 00:00", "Xong"), ("HD2", "02/06/2026 00:00", "Đã hoàn hàng"),
              ("HD3", "03/06/2026 00:00", "Hoàn thành")]
    tables = [  # no "Kênh bán": an optional column the new shop does not record; two monthly sheets
        table("HoaDon.xlsx::T06", orders[:2], ["Mã HĐ", "Thời gian", "Trạng thái"]),
        table("HoaDon.xlsx::T07", orders[2:], ["Mã HĐ", "Thời gian", "Trạng thái"]),
        table("ChiTiet.xlsx::Sheet1", [("HD1", "Bánh", 1, 10_000), ("HD2", "Bánh", 2, 20_000),
                                       ("HD3", "Kẹo", 1, 5_000)], ["Mã HĐ", "Tên hàng", "SL", "Thành tiền"]),
        table("TonKho.xlsx::Sheet1", [("Bánh", 7), ("Kẹo", 3)], ["Hàng", "Tồn"]),
    ]
    if extra_order_table:  # another layout holding the same order columns, as alike to the example as the first
        tables.append(table("Khac.xlsx::Sheet1", [o + ("",) for o in orders],
                            ["Mã HĐ", "Thời gian", "Trạng thái", "Ghi chú"]))
    return RawBusiness(root=Path("."), readme="", tables=tables)


def test_a_mapping_moves_onto_a_shop_with_the_same_columns():
    m = transfer.transfer(EX, new_shop())
    orders = next(t for t in m.tables if t.target == "orders")
    assert orders.sources == ["HoaDon.xlsx::T06", "HoaDon.xlsx::T07"]  # both months stacked
    assert "channel" not in [c.target for c in orders.columns]  # optional and not recorded here: left out
    # status words the example never met, read by the vocabulary of the hand mappings or by their key words
    assert orders.value_maps["status"]["Đã hoàn hàng"] == "returned"
    assert orders.value_maps["status"]["Hoàn thành"] == "completed"


def test_constants_of_the_example_shop_are_worked_out_again():
    shop = new_shop()
    shop.readme = "- **Tồn kho**: **Tồn** là tồn cuối ngày cuối có dữ liệu, theo đơn vị cơ bản."
    m = transfer._settle_constants(transfer.transfer(EX, shop), shop)
    db = build_canonical(shop, m)
    assert str(db.tables["inventory"]["as_of"].iloc[0])[:10] == "2026-06-03"  # last day of this shop's data
    assert not db.tables["orders"]["has_time"].iloc[0]  # every order at midnight: no hour recorded
    assert all(c.passed for c in run_checks(db)[:6])


def test_a_stock_snapshot_is_dated_only_where_the_readme_says_when_it_was_taken():
    """Review 04/11: the example's snapshot date was set to the last day of any shop's data, whatever its README said."""
    said = new_shop()
    said.readme = "- **Tồn kho**: **Tồn** là tồn cuối ngày cuối có dữ liệu, theo đơn vị cơ bản."
    assert "inventory" in [t.target for t in transfer._settle_constants(transfer.transfer(EX, said), said).tables]
    silent = new_shop()  # no README sentence: a stock at the start of the data, or of another day, is not dated
    assert "inventory" not in [t.target for t in transfer._settle_constants(transfer.transfer(EX, silent), silent).tables]


def test_status_words_are_read_only_when_their_key_words_agree():
    assert transfer.read_word("orders", "status", "Khách huỷ đơn") == "cancelled"
    assert transfer.read_word("orders", "status", "Hoàn") is None  # "hoàn thành" or "hoàn hàng"?
    assert transfer.read_word("orders", "status", "Đã giao, khách trả hàng") is None  # two statuses at once
    assert transfer.read_word("orders", "channel", "Xong") is None  # key words read order statuses only


def test_spellings_of_one_name_share_a_key_and_a_service_fee_is_no_item():
    from datamate.contracts import CanonicalDB
    from datamate.mapping.build import mark_fee_lines, unify_keys
    lines = pd.DataFrame({"product_key": ["Gạo ST25", "Gao ST25", "GẠO  ST25", "Bánh bò", "Bánh bơ", "Banh bo",
                                          "Phí phục vụ"],
                          "product_name": ["Gạo ST25", "Gao ST25", "GẠO  ST25", "Bánh bò", "Bánh bơ", "Banh bo",
                                           "Phí phục vụ"],
                          "is_item": True})
    lines = pd.concat([lines, lines.iloc[[0]]], ignore_index=True)  # "Gạo ST25" the most frequent spelling
    db = CanonicalDB(tables={"lines": lines})
    unify_keys(db)
    mark_fee_lines(db)
    keys = db.tables["lines"]["product_key"].tolist()
    assert keys[:3] == ["Gạo ST25"] * 3  # case, spaces, missing diacritics: one product (§8)
    assert keys[3:6] == ["Bánh bò", "Bánh bơ", "Banh bo"]  # two names apart by diacritics: no merge, no guess
    assert db.tables["lines"]["is_item"].tolist() == [True] * 6 + [False, True]  # §3 "Phí phục vụ"


def test_a_ledger_with_order_ids_is_told_from_one_without():
    """04/11: a shop with order ids read row by row like an example without ids passed every check, 68 wrong."""
    ids = pd.Series(["HD1", "HD1", "HD2", "HD3", "HD3", "HD3", "HD4", "HD5", "HD5", "HD6"])
    first_line_only = pd.Series(["HD1", "", "HD2", "HD3", "", "", "HD4", "HD5", "", "HD6"])
    products = pd.Series(["Mì", "Bánh", "Mì", "Kẹo", "Mì", "Bánh", "Kẹo", "Mì", "Bánh", "Kẹo"])
    assert transfer._groups_rows(ids) and transfer._groups_rows(first_line_only)
    assert not transfer._groups_rows(products)  # names repeat, but rarely on the next row


def test_a_product_sold_in_two_units_without_a_factor_has_no_base_quantity():
    """04/11: a mapping moved from a shop without a conversion table counted "1 thùng" as one can."""
    from datamate.contracts import CanonicalDB
    from datamate.mapping.build import derive_base_qty
    lines = pd.DataFrame({"product_key": ["Bia", "Bia", "Mì"], "unit": ["lon", "thùng", "gói"], "qty": [3, 1, 2]})
    db = CanonicalDB(tables={"lines": lines})
    derive_base_qty(db)
    assert db.tables["lines"]["base_qty"].isna().tolist() == [True, True, False]


def test_two_example_columns_of_different_meaning_do_not_share_a_new_column():
    """04/11: the example's base-quantity column matched to the shop's only quantity column."""
    example = Mapping.model_validate({"tables": [
        {"target": "orders", "sources": ["BH.csv"], "columns": [
            {"target": "order_id", "source": "Mã"}, {"target": "order_time", "source": "Ngày", "parse": "datetime"},
            {"target": "status", "source": "TT"}]},
        {"target": "lines", "sources": ["BH.csv"], "columns": [
            {"target": "order_id", "source": "Mã"}, {"target": "product_key", "source": "Hàng"},
            {"target": "product_name", "source": "Hàng"}, {"target": "qty", "source": "SL", "parse": "qty"},
            {"target": "base_qty", "source": "SL lẻ", "parse": "qty"},
            {"target": "line_amount", "source": "Tiền", "parse": "money"}]}]})
    e = transfer.Example("mau", example, {"BH.csv": ("Mã", "Ngày", "TT", "Hàng", "SL", "SL lẻ", "Tiền")})
    picked = transfer._one_meaning_each(e, "BH.csv", {"SL": "Số lượng", "SL lẻ": "Số lượng", "Hàng": "Tên",
                                                      "Mã": "Bill"})
    assert picked["SL"] == "Số lượng" and picked["SL lẻ"] is None  # the optional base quantity loses it
    assert picked["Hàng"] == "Tên"  # key and name read one column in the example itself: untouched


def test_tables_named_differently_pair_by_what_their_readme_says_of_the_columns():
    readme = ("## Cột trong `ChiTietHoaDon.xlsx`\n- **Bill**: mã đơn\n- **SLg**: số lượng\n- **TT đơn**: trạng thái đơn"
              "\n- **Thành tiền**: thành tiền sau giảm\n\n## Cột trong `DanhMuc.xlsx`\n- **Mã**: mã hàng\n- **Tên**: tên")
    shop = RawBusiness(root=Path("."), readme=readme, tables=[
        table("ChiTietHoaDon.xlsx::Sheet1", [("B1", 1, "Xong", 10)], ["Bill", "SLg", "TT đơn", "Thành tiền"]),
        table("DanhMuc.xlsx::Sheet1", [("SP1", "Mì")], ["Mã", "Tên"])])
    e = transfer.Example("mau", EXAMPLE, LAYOUT, notes={"ChiTiet.xlsx::Sheet1": {
        "Mã HĐ": "mã đơn", "SL": "số lượng", "Thành tiền": "thành tiền sau giảm (đ)", "Tên hàng": "tên hàng"}})
    assert transfer.pair_tables(e, shop)["ChiTiet.xlsx::Sheet1"] == ["ChiTietHoaDon.xlsx::Sheet1"]  # 3 of 4 meanings


def test_readme_notes_of_a_table_are_its_own_or_none():
    """Review 04/11: a file split _1 / _2, or one the README does not name, took the notes of the README's first
    section (another file's columns shown to the LLM as this table's)."""
    notes = transfer.readme_columns("## Cột trong `KhachHang.xlsx`\n- **Mã KH**: mã khách\n\n"
                                    "## Cột trong `SoBanHang.xlsx`\n- **Ma don**: mã đơn\n")
    assert transfer.column_notes(notes, "SoBanHang_1.xlsx::T01") == {"Ma don": "mã đơn"}
    assert transfer.column_notes(notes, "TonKho.xlsx::Sheet1") == {}
    assert transfer.column_notes(notes, "KhachHang.xlsx::Sheet1") == {"Mã KH": "mã khách"}


def test_no_guess_between_two_unlike_tables_that_fit_equally():
    assert transfer.transfer(EX, new_shop()) is not None
    shop = new_shop(extra_order_table=True)
    shop.tables = [t for t in shop.tables if not t.table_id.startswith("HoaDon")] + [
        table("HoaDon2.xlsx::Sheet1", [("HD1", "01/06/2026", "Xong", "A")], ["Mã HĐ", "Thời gian", "Trạng thái", "Kho"])]
    assert transfer.transfer(EX, shop) is None  # "Ghi chú" or "Kho": both as alike to the example, no guess
