"""G1 loader: cell text, header detection, summary rows, year hints, money formats, xlsx / csv / sqlite reading."""
from datetime import date, datetime

import openpyxl
import pytest

from datamate.loader import guess_type, load_business
from datamate.loader.grid import cell_text, to_table, year_hint
from datamate.loader.parse import parse_datetime, parse_money, parse_number

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
    t = to_table([HEADER, ROW, ["Cộng", "", "", "", "", "280.183.667đ"], ["Tổng cộng", "", "", "", "", "1tr440"],
                  ["Tổng tháng", "", "", "", "", "901.896.400đ"], ["Ghi chú: số liệu ghi tay"]])
    assert len(t.frame) == 1 and t.frame.iloc[0]["Khách"] == "Tống Văn An"
    assert any("bỏ 3 dòng tổng" in n for n in t.notes) and any("chú thích cuối sheet" in n for n in t.notes)


def test_a_daily_total_inside_the_sheet_is_dropped_whatever_column_holds_its_label():
    """04/11, a hand-kept ledger with shuffled columns: "3,411,000 | Tổng ngày 01/03" between two days' rows."""
    t = to_table([HEADER, ROW, ["", "", "", "", "", "3.411.000"], ["", "", "", "Tổng ngày 01/02", "", "3.411.000"], ROW])
    assert list(t.frame["Hàng"]) == ["Mì", "", "Mì"]  # a sparse row without a total label stays
    assert any("bỏ 1 dòng tổng: Tổng ngày 01/02" in n for n in t.notes)


def test_a_dated_total_is_dropped_even_on_a_full_row():
    """04/11, a public shop: "tổng 01/05" in the order id column with the day's sums in five other columns."""
    t = to_table([HEADER, ROW, ["tổng 01/02", "", "", "", "12", "1.200.000"], ROW])
    assert len(t.frame) == 2 and list(t.frame["Khách"]) == ["Tống Văn An"] * 2


def test_the_header_written_again_inside_the_data_is_no_record():
    """04/11, a public shop: one row "Mã đơn hàng | Ngày đặt hàng | Trạng thái đơn hàng…" among 84 000 lines."""
    t = to_table([HEADER, ROW, HEADER, ROW])
    assert len(t.frame) == 2 and any("bỏ 1 dòng lặp lại header" in n for n in t.notes)


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
    ("41,785tr", 41785000), ("1.5tr", 1500000), ("2,5k", 2500), ("25000k", 25000000),  # R25: decimal before tr / k
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


# ---- N169: more forms of date, money and number are read
@pytest.mark.parametrize("text,when", [
    ("27/08/2026 2:05 PM", datetime(2026, 8, 27, 14, 5)), ("27/08/2026 12:30 AM", datetime(2026, 8, 27, 0, 30)),
    ("27/08/2026 12:30 PM", datetime(2026, 8, 27, 12, 30)), ("2026-08-27 2:05 PM", datetime(2026, 8, 27, 14, 5)),
    ("27/08/2026 2:05 CH", datetime(2026, 8, 27, 14, 5)), ("27/08/2026 9:05 SA", datetime(2026, 8, 27, 9, 5)),
    ("Thứ Năm, 27/08/2026 14:05", datetime(2026, 8, 27, 14, 5)), ("CN 30/08/2026", datetime(2026, 8, 30)),
    ("14:05 27/08/2026", datetime(2026, 8, 27, 14, 5)), ("27.08.2026", datetime(2026, 8, 27)),
    ("27-08-2026 14:05", datetime(2026, 8, 27, 14, 5)), ("2026-01-01 14:58:08", datetime(2026, 1, 1, 14, 58, 8)),
    ("2026-01-01T10:00:00+07:00", datetime(2026, 1, 1, 10)), ("1 thg 12 2025", datetime(2025, 12, 1)),
    ("2026-08-27 hello", None), ("2026-08-27 14:05 PM", None), ("hôm qua", None),
])
def test_dates_with_am_pm_weekday_and_dots(text, when):
    assert parse_datetime(text, 2026) == when


@pytest.mark.parametrize("text,amount", [
    ("1,2 triệu", 1_200_000), ("2 triệu", 2_000_000), ("500 nghìn", 500_000), ("150 ngàn", 150_000),
    ("(30.000)", -30_000), ("VND 30.000", 30_000), ("1 234 000", 1_234_000), ("2 triệu đồng", 2_000_000),
    ("1tr440", 1_440_000), ("25k", 25_000), ("41,785tr", 41_785_000), ("30.500đ", 30_500), ("-30.500đ", -30_500),
])
def test_money_in_words_brackets_and_spaced_thousands(text, amount):
    assert parse_money(text) == amount


def test_number_with_spaced_thousands():
    assert parse_number("1 234 000") == 1_234_000 and parse_number("1 234") == 1234
    assert parse_number("5 chai") == 5 and parse_number("3 4") == 3  # not a thousands form


def test_a_column_of_weekday_dates_and_of_words_is_typed():
    assert guess_type(["Thứ Năm, 27/08/2026 14:05", "CN 30/08/2026 09:00", "T2 31/08/2026 10:00"])[0] == "date"
    assert guess_type(["1,2 triệu", "500 nghìn", "2 triệu", "150 ngàn"])[0] == "money"


def test_a_named_column_with_no_value_is_dropped():
    """N174: a notes column left blank in every row tells nothing; offered to the column matching it, it took picks."""
    t = to_table([["Ghi chú nội bộ", "Mã", "Tiền", "Ghi chú"], ["", "A1", "10.000", ""], ["", "A2", "20.000", "gấp"]])
    assert list(t.frame.columns) == ["Mã", "Tiền", "Ghi chú"] and len(t.frame) == 2
    assert any("bỏ cột không có giá trị" in n for n in t.notes)
    only_header = to_table([["Mã", "Tiền"]])
    assert list(only_header.frame.columns) == ["Mã", "Tiền"] and len(only_header.frame) == 0


@pytest.mark.parametrize("text, delim", [
    ('Ma,Ten,Tien\nK1,Cafe,"25,000"\n', ","),
    ("Ma;Ten;Tien\nK1;Cafe;25,000\n", ";"),  # the first line decides, as before
    ("Ma\tTen\tTien\nK1\tCafe\t25,000\n", "\t"),
    ("SỔ BÁN HÀNG\nMa;Ten;Tien\nK1;Cafe;25,000\n", ";"),  # N195: a title above the header holds no delimiter
    ("\nSỔ BÁN HÀNG\n\nMa\tTen\tTien\nK1\tCafe\t25,000\n", "\t"),
    ("SỔ BÁN HÀNG\nMa,Ten,Tien\nK1,Cafe,25000\n", ","),
    ("Ma|Ten|Tien\nK1|Cafe|25,000\n", "|"),
    ("Ma,Ten|Loai,Tien\nK1,Cafe,25000\n", ","),  # a '|' inside a name of a comma file is no delimiter
    ("Sổ bán hàng, năm 2025\nMa;Ten;Tien\nK1;Cafe;25,000\n", ";"),  # a title with a comma: the header has none
    ("Sổ bán hàng; quý 1\n\nMa,Ten,Tien\nK1,Cafe,25000\n", ","),
    ("Ma,Ten,Tien\nTháng 1\nK1,Cafe,25000\nK2,Tra,20000\n", ","),  # a label row inside the data
    ("Ma;Ten;Tien\n", ";"),  # the header alone
    ("Ten, loai\nCafe\nTra\n", ","),  # one column whose name has a comma: as before
    ("Ten\nCafe\nTra\n", ","),  # one column
    ("", ","),
])
def test_csv_delimiter(text, delim):
    from datamate.loader import _delimiter
    assert _delimiter(text) == delim


def test_a_csv_under_a_title_line_is_read_by_its_own_delimiter(tmp_path):
    """N195: read by its first line alone, a ';' file under a title was cut at the commas of its amounts."""
    rows = "Mã đơn;Ngày;Tên hàng;SL;Thành tiền\nD1;01/06/2026;Cà phê sữa;2;50,000\nD2;02/06/2026;Bạc xỉu;1;29,000\n"
    (tmp_path / "a.csv").write_text(rows, encoding="utf-8")
    (tmp_path / "b.csv").write_text("SỔ BÁN HÀNG\n" + rows, encoding="utf-8")
    a, b = load_business(tmp_path).tables
    assert list(b.frame.columns) == ["Mã đơn", "Ngày", "Tên hàng", "SL", "Thành tiền"] and b.frame.equals(a.frame)
    assert b.frame["Thành tiền"].tolist() == ["50,000", "29,000"] and b.header_rows == 2
