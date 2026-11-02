"""[R] rulebook parsing and rule checks."""
from pathlib import Path

import pytest

from datamate.rules import check_rules, diff_rulebooks, load_reference, parse_rulebook, similarity

DATA = Path(__file__).resolve().parents[1] / "data"
SAMPLE = """# Rulebook

Hôm nay là as_of_date.

## 1. Đơn hàng
| Luật | Mặc định |
|---|---|
| Đơn tính vào doanh thu | đơn **không huỷ** và **không trả hàng** |
| Số đơn | chỉ tính đơn không huỷ |

## 6. Theo ngành
### Cà phê
| Luật | Mặc định |
|---|---|
| Size M, size L | món có tên kết thúc bằng `(M)` |
"""


def test_parse_ids_and_header_rows_skipped():
    rows = parse_rulebook(SAMPLE)
    assert set(rows) == {"§0.p_hom_nay_la_as_of_date", "§1.don_tinh_vao_doanh_thu", "§1.so_don",
                         "§6.ca_phe.size_m_size_l"}
    assert rows["§1.don_tinh_vao_doanh_thu"].text == "đơn **không huỷ** và **không trả hàng**"


def test_check_rules_exact_changed_missing():
    ref = {rid: r.text for rid, r in parse_rulebook(SAMPLE).items()}
    ids = ("§1.don_tinh_vao_doanh_thu", "§1.so_don", "§9.khong_co")
    assert check_rules(SAMPLE, ids, ref) == {"§1.don_tinh_vao_doanh_thu": True, "§1.so_don": True, "§9.khong_co": False}
    changed = SAMPLE.replace("chỉ tính đơn không huỷ", "tính mọi đơn, kể cả đơn huỷ và trả hàng")
    assert check_rules(changed, ids[:2], ref)["§1.so_don"] is False


def test_similarity_ignores_markdown_and_spacing():
    assert similarity("đơn **không huỷ**", "đơn  không huỷ") == 1.0


@pytest.mark.skipif(not (DATA / "public_test" / "rulebook.md").exists(), reason="cần data/")
def test_real_rulebooks_diff_and_reference():
    train = (DATA / "train" / "rulebook.md").read_text(encoding="utf-8")
    public = (DATA / "public_test" / "rulebook.md").read_text(encoding="utf-8")
    d = diff_rulebooks(train, public)
    assert len(d["changed"]) == 3 and len(d["added"]) == 25 and len(d["removed"]) == 3
    ref = load_reference()
    assert ref and all(check_rules(public, tuple(parse_rulebook(public)), ref).values())
