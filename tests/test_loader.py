"""G1 loader: cell text, header detection, summary rows, year hints, money formats, xlsx / csv / sqlite reading."""
from datetime import date, datetime

import openpyxl
import pytest

from datamate.loader import guess_type, load_business
from datamate.loader.grid import cell_text, to_table, year_hint
from datamate.loader.parse import parse_money, parse_number

HEADER = ["Mã đơn", "Ngày", "Khách", "Hàng", "SL", "Tiền"]
ROW = ["ORD1", "01/02/2025", "Tống Văn An", "Mì", "2", "10.000đ"]


@pytest.mark.parametrize("value,text", [
    (None, ""), (float("nan"), ""), (1001.0, "1001"), (2.5, "2.5"), (datetime(2025, 2, 1), "2025-02-01"),
    (datetime(2025, 2, 1, 6, 0, 25), "2025-02-01 06:00:25"), (date(2025, 2, 1), "2025-02-01"), ("  Mì  ", "Mì"),
])
def test_cell_text(value, text):
    assert cell_text(value) == text


def test_title_rows_above_the_header_are_skipped():
    t = to_table([["SỔ CHI TIẾT BÁN HÀNG"], ["Kỳ báo cáo: toàn bộ", "Kênh bán: Tất cả"], [], HEADER, ROW])
    assert list(t.frame.columns) == HEADER and t.frame.iloc[0].tolist() == ROW and t.header_rows == 3
    assert not any("nhóm cột" in n for n in t.notes)  # "label: value" rows are not column groups


def test_two_row_header_keeps_the_names_and_notes_the_groups():
    groups = ["Đơn", "", "", "Hàng", "", "Tiền"]
    t = to_table([groups, HEADER, ROW])
    assert list(t.frame.columns) == HEADER and t.header_rows == 2
    assert any("Đơn: Mã đơn, Ngày, Khách" in n for n in t.notes)


def test_summary_rows_are_dropped_but_a_customer_named_tong_is_kept():
    t = to_table([HEADER, ROW, ["Cộng", "", "", "", "", "280.183.667đ"], ["Tổng cộng", "", "", "", "", "1tr440"]])
    assert len(t.frame) == 1 and t.frame.iloc[0]["Khách"] == "Tống Văn An"
    assert any("bỏ 2 dòng tổng" in n for n in t.notes)


def test_duplicate_and_empty_column_names():
    t = to_table([["", "Tên", "Tên", "", "Giá"], ["", "Mì", "Mì gói", "x", "5"]])
    assert list(t.frame.columns) == ["Tên", "Tên_2", "cot_3", "Giá"]  # the all-empty first column is dropped


@pytest.mark.parametrize("sheet,file,year", [
    ("Thang 06 2026", "SoBanHang_1", 2026), ("T7-2025", "x", 2025), ("Sheet1", "BanHang_T11_2025", 2025),
    ("T01_2025", "DonHang", 2025), ("Sheet1", "SoBanHang_1", None),
])
def test_year_hint(sheet, file, year):
    assert year_hint(sheet, file) == year


@pytest.mark.parametrize("raw,amount", [
    ("45,000.0000", 45000), ("1tr440", 1440000), ("409tr663", 409663000), ("1tr5", 1500000), ("-1tr440", -1440000),
    ("332,5972tr", 332597200), ("1.234,50", 1234.5), ("1,200,000", 1200000), ("55.000đ", 55000),
])
def test_money_formats_seen_in_the_data(raw, amount):
    assert parse_money(raw) == amount


def test_number_uses_the_same_separators():
    assert parse_number("45,000.0000") == 45000 and parse_number("1.500") == 1500 and parse_number("1,5 kg") == 1.5


def test_guess_type():
    assert guess_type(["01/02/2025", "02/02/2025"])[0] == "date"
    assert guess_type(["10.000đ", "25k", "1tr440"])[:2] == ("money", "10000")
    assert guess_type(["1", "2", "3"]) == ("number", "1", "3")
    assert guess_type(["Mì", "Sữa"])[0] == "text" and guess_type([])[0] == "empty"


def test_load_business_reads_xlsx_sheets_csv_and_skips_unknown_files(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Thang 02 2025"
    for r in (["BÁO CÁO"], HEADER, ["ORD1", datetime(2025, 2, 1), "Lan", "Mì", 2.0, "10.000đ"]):
        ws.append(r)
    wb.create_sheet("Thang 03 2025").append(HEADER)
    wb.save(tmp_path / "SoBanHang.xlsx")
    (tmp_path / "khach.csv").write_bytes("Ma;Ten\nK1;Café Tư\n".encode("cp1258"))  # not utf-8, ";" separated
    (tmp_path / "anh.png").write_bytes(b"x")
    raw = load_business(tmp_path)
    by_id = {t.table_id: t for t in raw.tables}
    feb = by_id["SoBanHang.xlsx::Thang 02 2025"]
    assert feb.year_hint == 2025 and feb.frame.iloc[0].tolist() == ["ORD1", "2025-02-01", "Lan", "Mì", "2", "10.000đ"]
    assert len(by_id["SoBanHang.xlsx::Thang 03 2025"].frame) == 0
    assert by_id["khach.csv"].frame.iloc[0].tolist() == ["K1", "Café Tư"]
    assert any("anh.png" in w for w in raw.warnings)


def test_reading_stops_at_the_time_budget(tmp_path):
    (tmp_path / "a.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    raw = load_business(tmp_path, budget_s=-1)
    assert not raw.tables and any("hết" in w for w in raw.warnings)
