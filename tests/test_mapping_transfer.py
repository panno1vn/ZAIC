"""T5: a hand mapping moved onto a shop of the same export format (datamate/mapping/transfer.py), on two tiny shops."""
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

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
    # public dev_003 (06/11): a status cell "Khách trả" alone is a return; "khách trả tiền" is no status word
    assert transfer.read_word("orders", "status", "Khách trả") == "returned"
    assert transfer.read_word("orders", "status", "Khách trả tiền mặt") is None


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


def test_a_customer_with_the_phone_written_several_ways_is_one_customer():
    """N106 (public dev_011): §9 "không phân biệt hoa thường, khoảng trắng, dấu câu"; another number is another
    customer, and two names apart by diacritics stay two."""
    from datamate.contracts import CanonicalDB
    from datamate.mapping.build import unify_keys
    o = pd.DataFrame({"order_id": list("1234567"), "customer_key": [
        "Trịnh Hằng Nam 0977824094", "Trịnh Hằng Nam - 0977 824 094", "Trịnh Hằng Nam (0977824094)",
        "Trịnh Hằng Nam 0977824094", "Trịnh Hằng Nam 0977824095", "Lê Thị Bò", "Lê Thị Bơ"]})
    db = CanonicalDB(tables={"orders": o})
    unify_keys(db)
    assert db.tables["orders"]["customer_key"].tolist() == ["Trịnh Hằng Nam 0977824094"] * 4 + [
        "Trịnh Hằng Nam 0977824095", "Lê Thị Bò", "Lê Thị Bơ"]


def test_a_topping_written_in_the_dish_cell_is_its_own_line():
    """N108, §6 Cà phê: "món và topping là hai mặt hàng bán; số lượng, tiền của topping tính vào mặt hàng topping"."""
    from datamate.contracts import CanonicalDB
    from datamate.mapping.build import split_toppings, unify_keys
    lines = pd.DataFrame({"order_id": ["1", "2", "3"],
                          "product_key": ["Matcha latte (M) + 2 Thach ca phe (14.000đ)", "Topping Thạch cà phê",
                                          "Trà chanh (M) + Trân châu đen (7.000đ)"],
                          "qty": [2.0, 1.0, 2.0], "unit": ["ly", "phần", "ly"], "unit_price": [49_000.0, 7_000.0, 26_000.0],
                          "line_amount": [112_000.0, 7_000.0, 59_000.0], "is_item": True})
    lines["product_name"] = lines["product_key"]
    db = CanonicalDB(tables={"lines": lines})
    split_toppings(db)
    unify_keys(db)
    got = db.tables["lines"].groupby("product_key").agg(qty=("qty", "sum"), money=("line_amount", "sum"))
    assert got.loc["Matcha latte (M)"].tolist() == [2.0, 98_000.0]  # the dish keeps its quantity, less the topping
    assert got.loc["Topping Thạch cà phê"].tolist() == [3.0, 21_000.0]  # 2 portions written + 1 on its own line
    assert got.loc["Trà chanh (M)"].tolist() == [2.0, 52_000.0]
    assert got.loc["Topping Trân châu đen"].tolist() == [1.0, 7_000.0]


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


def test_a_database_table_is_named_by_its_table_alone():
    """N27: the file name of a database says nothing of its format; with it in the stem, a shop of the same POS whose
    file was named otherwise paired with no example (variant of biz_123, 05/11)."""
    assert transfer.stem("pos.sqlite::don_hang") == transfer.stem("du_lieu.db::don_hang") == "donhang"
    assert transfer.stem("don_hang.csv") == "donhang"  # the same table exported as csv by another shop
    assert transfer.stem("SoBanHang_1.xlsx::Sheet1") == transfer.stem("SoBanHang_2026.xlsx::Thang 6") == "sobanhang"


def test_tables_of_a_format_no_example_shares_are_paired_by_the_llm():
    """N27: no file name and no README note pairs the tables; the LLM picks, for each example table, the new table
    playing its part, seeing columns, values and row counts. Orders and lines on one table: no guess."""
    from datamate.llm import MockLLM
    shop = RawBusiness(root=Path("."), readme="", tables=[
        table("bang_a.csv::x", [("B1", "Bánh", 1, 10_000), ("B1", "Kẹo", 2, 4_000)], ["Bill", "Hàng", "Slg", "Tiền"]),
        table("bang_b.csv::x", [("B1", "01/06/2026 08:00", "Xong")], ["Bill", "Lúc", "Tình trạng"])])
    llm = MockLLM([{"t1": "b1", "t2": "b2", "t3": ""}])  # ChiTiet, HoaDon, TonKho (sorted)
    pairs = transfer.pair_tables_by_llm(EX, shop, llm)
    assert pairs == {"ChiTiet.xlsx::Sheet1": ["bang_a.csv::x"], "HoaDon.xlsx::T01": ["bang_b.csv::x"]}
    prompt = llm.calls[0][0][1]["content"]
    assert '"bang_a.csv::x", 2 dòng' in prompt and "lines (Một dòng mỗi dòng hàng của đơn)" in prompt
    assert transfer.pair_tables_by_llm(EX, shop, MockLLM([{"t1": "b2", "t2": "b2", "t3": ""}])) == {}  # no ids group
    with pytest.raises(transfer.LLMUnavailable):  # the LLM failed (twice): said so, not "nothing pairs" (N164b)
        transfer.pair_tables_by_llm(EX, shop, MockLLM([]))


def test_a_required_column_left_unmatched_is_asked_again_among_the_free_columns():
    """N27, 05/11: a shop's quantity column ("Số lượng sản phẩm") left unmatched in a question of 8 columns lost the
    whole mapping; asked again alone, among the columns not taken, it is found."""
    from datamate.llm import MockLLM
    shop = RawBusiness(root=Path("."), readme="", tables=[
        table("CT.csv::x", [("B1", "Bánh", 1, 10_000)], ["Bill", "Hàng", "Số lượng sản phẩm", "Tiền"])])
    # example columns, sorted: Mã HĐ, SL, Thành tiền, Tên hàng
    llm = MockLLM([{"c1": "Bill", "c2": "", "c3": "Tiền", "c4": "Hàng"}, {"c1": "Số lượng sản phẩm"}])
    got = transfer._ask_required_again(EX, "ChiTiet.xlsx::Sheet1", ["Mã HĐ", "SL", "Thành tiền", "Tên hàng"], shop,
                                       ["CT.csv::x"], llm)
    assert got == {"Mã HĐ": "Bill", "SL": "Số lượng sản phẩm", "Thành tiền": "Tiền", "Tên hàng": "Hàng"}
    assert llm.calls[1][1]["properties"]["c1"]["enum"] == ["Số lượng sản phẩm", ""]  # taken columns not offered
    # nothing missing: one question only
    llm = MockLLM([{"c1": "Bill", "c2": "Số lượng sản phẩm", "c3": "Tiền", "c4": "Hàng"}])
    transfer._ask_required_again(EX, "ChiTiet.xlsx::Sheet1", ["Mã HĐ", "SL", "Thành tiền", "Tên hàng"], shop,
                                 ["CT.csv::x"], llm)
    assert len(llm.calls) == 1


def test_a_side_table_with_empty_required_cells_is_left_out_not_the_shop():
    """N27, 05/11: an unfamiliar shop's orders and lines matched right, its product list taken for a price history
    with no dates, and the whole shop failed "cột bắt buộc đủ giá trị"."""
    from datamate.contracts import CanonicalDB
    db = CanonicalDB(tables={
        "orders": pd.DataFrame({"order_id": ["D1"], "order_time": [None]}),  # a core table: the check decides
        "price_history": pd.DataFrame({"product_key": ["SP1"], "effective_date": [None], "price": [None]}),
        "customers": pd.DataFrame({"customer_key": ["KH1"], "customer_name": ["An"]})})
    assert transfer.unfilled_extras(db) == ["price_history"]


def test_the_quantity_is_read_again_when_only_the_amount_check_fails():
    """N27, 05/11: an unfamiliar pharmacy's base-unit quantity ("SL cơ bản") was matched for the line's quantity and
    its "Slg" left out: amount = quantity × price failed and the shop had no mapping. The one other number column
    making every check pass is taken; none or two: the mapping still fails."""
    n = 25
    orders = [(f"D{i}", f"{1 + i % 28:02d}/06/2026 09:00", "Hoàn thành") for i in range(n)]
    lines = [(f"D{i}", f"Bia lon {i % 12}", 2, 48, 300_000, 600_000) for i in range(n)]  # 2 thùng = 48 lon
    shop = RawBusiness(root=Path("."), readme="", tables=[
        table("HoaDon.xlsx::Sheet1", orders, ["Mã HĐ", "Thời gian", "Trạng thái"]),
        table("ChiTiet.xlsx::Sheet1", lines, ["Mã HĐ", "Tên hàng", "Slg", "SL cơ bản", "Đơn giá", "Thành tiền"])])
    m = Mapping.model_validate({"tables": [
        {"target": "orders", "sources": ["HoaDon.xlsx::Sheet1"], "columns": [
            {"target": "order_id", "source": "Mã HĐ"}, {"target": "order_time", "source": "Thời gian",
                                                       "parse": "datetime"},
            {"target": "has_time", "const": True}, {"target": "status", "source": "Trạng thái"}],
         "value_maps": {"status": {"Hoàn thành": "completed"}}},
        {"target": "lines", "sources": ["ChiTiet.xlsx::Sheet1"], "columns": [
            {"target": "order_id", "source": "Mã HĐ"}, {"target": "product_key", "source": "Tên hàng"},
            {"target": "product_name", "source": "Tên hàng"}, {"target": "qty", "source": "SL cơ bản", "parse": "qty"},
            {"target": "unit_price", "source": "Đơn giá", "parse": "money"},
            {"target": "line_amount", "source": "Thành tiền", "parse": "money"}]}], "notes": ["mẫu"]})
    tried = []
    fixed = transfer._passes(m, shop, tried)
    assert fixed is not None and "số lượng của dòng đọc lại" in fixed.notes[-1]
    assert next(c for t in fixed.tables if t.target == "lines" for c in t.columns if c.target == "qty").source == "Slg"
    # two columns that would fit: no guess
    shop.tables[1] = table("ChiTiet.xlsx::Sheet1", [r + (2,) for r in lines],
                           ["Mã HĐ", "Tên hàng", "Slg", "SL cơ bản", "Đơn giá", "Thành tiền", "Slg 2"])
    assert transfer._passes(m, shop, []) is None


def test_the_order_id_column_means_nothing_else():
    """N27, 05/11: an unfamiliar shop's order id column was matched for the order id and for the product key too, both
    required, so both kept it: rankings named order lines' codes. The order id's column is the order id only; the
    other loses it (asked again among the free columns)."""
    e = transfer.Example("mau", EXAMPLE, LAYOUT)
    picked = transfer._one_meaning_each(e, "ChiTiet.xlsx::Sheet1", {"Mã HĐ": "Bill", "Tên hàng": "Bill", "SL": "Slg",
                                                                    "Thành tiền": "Tiền"})
    assert picked["Mã HĐ"] == "Bill" and picked["Tên hàng"] is None
    # a product key and name from one column stay one column (a shop keyed by name)
    two = Mapping.model_validate({"tables": [{"target": "lines", "sources": ["CT.csv"], "columns": [
        {"target": "order_id", "source": "Mã"}, {"target": "product_key", "source": "Mã hàng"},
        {"target": "product_name", "source": "Tên hàng"}, {"target": "qty", "source": "SL", "parse": "qty"}]}]})
    e2 = transfer.Example("mau2", two, {"CT.csv": ("Mã", "Mã hàng", "Tên hàng", "SL")})
    kept = transfer._one_meaning_each(e2, "CT.csv", {"Mã": "Bill", "Mã hàng": "Hàng", "Tên hàng": "Hàng", "SL": "SL"})
    assert kept["Mã hàng"] == kept["Tên hàng"] == "Hàng"


def test_the_orders_of_an_example_pair_only_with_a_table_holding_order_statuses():
    """N27, 05/11: a shop with no README notes and neutral file names had its sales ledger and a delivery note of the
    same columns (order id, product, quantity); the LLM paired the example's ledger with the delivery note, which has
    no status, and the shop had no mapping. An example table read for the order status is offered only the tables
    with a column of status words, when there is one."""
    from datamate.llm import MockLLM
    shop = RawBusiness(root=Path("."), readme="", tables=[
        table("bang_a.csv::x", [("B1", "Bánh", 2, "01/06/2026")], ["Bill", "Hàng", "SL giao", "Ngày giao"]),
        table("bang_b.csv::x", [("B1", "01/06/2026 08:00", "Hoàn thành", "Bánh", 2, 10_000)],
              ["Bill", "Lúc", "Tình trạng", "Hàng", "Slg", "Tiền"])])
    llm = MockLLM([{"t1": "b2", "t2": "b2", "t3": ""}])
    transfer.pair_tables_by_llm(EX, shop, llm)
    props = llm.calls[0][1]["properties"]
    assert props["t2"]["enum"] == ["b2", ""]  # HoaDon (orders, status read from a column): only the table with one
    assert props["t1"]["enum"] == ["b2", ""]  # ChiTiet (lines, amount from a column): only the table with money


def test_orders_and_lines_of_an_example_may_share_a_flat_sheet_with_order_ids():
    """Public dev_003 (06/11): "hoá đơn và chi tiết hoá đơn gộp chung sheet BanHang: mỗi dòng là một dòng hàng, thông
    tin hoá đơn lặp lại". An example with an orders and a lines table pairs both with that sheet when a column of it
    groups its rows into orders; a sheet whose rows group into nothing is still no guess."""
    from datamate.llm import MockLLM
    rows = [(f"B{i // 2}", f"{1 + i % 28:02d}/06/2026 08:00", "Hoàn thành", f"Bánh {i % 5}", 1, 10_000)
            for i in range(30)]
    flat = RawBusiness(root=Path("."), readme="", tables=[
        table("BanHang.xlsx::BanHang", rows, ["Đơn số", "Lúc", "Trạng thái", "Hàng", "SL", "Tiền"])])
    pairs = transfer.pair_tables_by_llm(EX, flat, MockLLM([{"t1": "b1", "t2": "b1", "t3": ""}]))
    assert pairs["HoaDon.xlsx::T01"] == pairs["ChiTiet.xlsx::Sheet1"] == ["BanHang.xlsx::BanHang"]
    lone = [(f"B{i}",) + r[1:] for i, r in enumerate(rows)]  # every row its own id: nothing groups
    ledger = RawBusiness(root=Path("."), readme="", tables=[
        table("BanHang.xlsx::BanHang", lone, ["Đơn số", "Lúc", "Trạng thái", "Hàng", "SL", "Tiền"])])
    assert transfer.pair_tables_by_llm(EX, ledger, MockLLM([{"t1": "b1", "t2": "b1", "t3": ""}])) == {}


def test_a_workbook_of_several_lists_offers_each_list_to_the_llm():
    """Public dev_003 (06/11): BanHang_TongHop_2025.xlsx holds the sales sheet and four other lists, the 2026 file the
    sales sheet alone. Grouped by file name the five layouts were "unlike" and the sales sheets never offered to the
    LLM, which paired the payments slip with the example's orders. Each layout is offered; sheets alike across files
    stay one table."""
    sales = ["Đơn số", "Ngày HĐ", "Trạng thái", "Hàng hóa", "SL", "Thành tiền"]
    shop = RawBusiness(root=Path("."), readme="", tables=[
        table("BanHang_TongHop_2025.xlsx::BanHang", [("B1", "01/03/2025", "Xong", "Bánh", 1, 10_000)], sales),
        table("BanHang_TongHop_2025.xlsx::BanHang_HangHoa", [("SP1", "Bánh")], ["Mã", "Tên"]),
        table("BanHang_TongHop_2026.xlsx::BanHang", [("B9", "01/03/2026", "Xong", "Kẹo", 1, 5_000)], sales)])
    groups = transfer.layout_groups(shop)
    assert ["BanHang_TongHop_2025.xlsx::BanHang", "BanHang_TongHop_2026.xlsx::BanHang"] in groups
    assert ["BanHang_TongHop_2025.xlsx::BanHang_HangHoa"] in groups
    assert transfer._new_groups(shop) == {}  # by file name alone: still no guess
