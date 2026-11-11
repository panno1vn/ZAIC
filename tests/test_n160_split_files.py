"""N160: the split's files written another way than in train and public must not blank a shop or the whole split:
CSV and README in UTF-16 (Excel "Unicode text"), a lower-case readme.md, an as_of_date with a time or day first."""
import json

from datamate import loader
from datamate.pipeline import iso_day, load_questions

CSV = "Mã đơn,Ngày,Thành tiền\nHD001,01/02/2025,120.000\nHD002,02/02/2025,85.000\n"


def test_utf16_csv_with_or_without_bom_reads_like_utf8(tmp_path):
    for name, data in (("a.csv", CSV.encode("utf-8-sig")), ("b.csv", CSV.encode("utf-16")),
                       ("c.csv", CSV.encode("utf-16-le")), ("d.csv", CSV.encode("utf-16-be"))):
        (tmp_path / name).write_bytes(data)
    raw = loader.load_business(tmp_path)
    frames = {t.file: t.frame for t in raw.tables}
    assert len(frames) == 4
    first = frames["a.csv"]
    for f in ("b.csv", "c.csv", "d.csv"):
        assert list(frames[f].columns) == list(first.columns) and frames[f].values.tolist() == first.values.tolist()


def test_readme_any_case_and_encoding(tmp_path):
    (tmp_path / "readme.md").write_bytes("# Dữ liệu\nMỗi dòng một đơn.".encode("utf-16"))
    (tmp_path / "x.csv").write_text(CSV, encoding="utf-8")
    raw = loader.load_business(tmp_path)
    assert raw.readme.startswith("# Dữ liệu") and not any("readme" in w.lower() for w in raw.warnings)


def test_cp1258_still_read():
    text, note = loader._decode("Mã đơn".encode("cp1258", errors="ignore") + b",x\n")
    assert note and "cp1258" in note


def test_as_of_date_forms():
    assert iso_day("2026-08-27") == "2026-08-27"
    assert iso_day("2026-08-27T00:00:00") == "2026-08-27"
    assert iso_day("2026-08-27 00:00") == "2026-08-27"
    assert iso_day("27/08/2026") == "2026-08-27"
    assert iso_day("2026/8/7") == "2026-08-07"
    assert iso_day("hôm nay") == "hôm nay" and iso_day(None) == ""
    assert iso_day("2026-13-40") == "2026-13-40"


def test_load_questions_normalises_dates(tmp_path):
    rows = [{"id": "q1", "business_id": "b", "question": "?", "as_of_date": "2026-08-27T00:00:00", "extra": 1}]
    (tmp_path / "questions.jsonl").write_text("".join(json.dumps(r) + "\r\n" for r in rows), encoding="utf-8-sig")
    assert load_questions(tmp_path)[0]["as_of_date"] == "2026-08-27"


def test_n163_total_rows_by_their_word_not_its_fold():
    from datamate.loader.grid import _summary_cell
    for c in ("Cộng", "Tổng cộng", "TỔNG", "Cộng tiền hàng", "Total", "Cong", "tong cong"):
        assert _summary_cell(c), c
    for c in ("Công tắc 1 chiều Panasonic", "Tống Văn An", "Cong tac 1 chieu Panasonic Wide", "Công"):
        assert not _summary_cell(c), c


def test_n163_product_named_cong_tac_kept_in_a_sparse_catalogue(tmp_path):
    rows = ["Ghi chú,Mã,Tên,Nhóm,Đơn vị,Giá,Tồn,Bảo hành,Mô tả,Hình,Thuộc tính,Ghi chú 2"]
    rows += [f",SP{i},Hàng {i},nhóm {i % 3},cái,{1000 + i},,,,,," for i in range(5)]
    rows += [",SP9,Công tắc 1 chiều Panasonic,điện,cái,5000,,,,,,"]
    (tmp_path / "danh_muc.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    raw = loader.load_business(tmp_path)
    assert len(raw.tables[0].frame) == 6


# ---- N170 (R001): a total label written without accents is made of total words, however many
def test_n170_unaccented_total_labels_are_totals():
    from datamate.loader.grid import _summary_cell
    for label in ("Tong doanh thu ca ngay", "Tong cong tien hang", "Tong tien ban hang ca ngay", "Total sales this week",
                  "Cong", "Tong cong", "cong thang 3"):
        assert _summary_cell(label), label
    for label in ("Cong tac 1 chieu Panasonic", "Tong Van An", "Tong do cat toc", "Cong ty ABC"):
        assert not _summary_cell(label), label


def test_n170_a_long_unaccented_total_row_is_dropped_from_the_grid():
    from datamate.loader.grid import to_table
    g = [["Ma don", "Ngay", "Hang", "SL", "Don gia", "Thanh tien"], ["D1", "01/02/2025", "Bia", "2", "10000", "20000"],
         ["", "", "Mi", "1", "8000", "8000"], ["D2", "02/02/2025", "Bia", "1", "10000", "10000"],
         ["D3", "02/02/2025", "Cong tac 1 chieu Panasonic", "1", "45000", "45000"],
         ["Tong doanh thu ca ngay", "", "", "", "", "83000"]]
    t = to_table(g)
    assert len(t.frame) == 4 and "Tong doanh thu ca ngay" not in set(t.frame["Ma don"])
    assert "Cong tac 1 chieu Panasonic" in set(t.frame["Hang"])
