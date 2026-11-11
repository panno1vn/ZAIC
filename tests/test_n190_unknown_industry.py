"""N190: a revenue answer in a shop of a business type whose §6 rows the functions were never checked against is
left blank; known business types, other shops and other metrics are untouched."""
from pathlib import Path

import pytest

from datamate import rules
from datamate.contracts import QueryPlan

TRAIN = Path(__file__).resolve().parents[1] / "data" / "train" / "rulebook.md"
SALON = """
### Salon tóc và spa
| Luật | Mặc định |
|---|---|
| Hoá đơn trả bằng thẻ liệu trình | buổi dùng của gói: **không tính vào doanh thu** |
"""
PHONE_RENAMED = """
### Cửa hàng điện thoại di động
| Luật | Mặc định |
|---|---|
| Doanh thu máy | doanh thu chỉ gồm máy |
"""
NO_REVENUE = """
### Tiệm giặt là
| Luật | Mặc định |
|---|---|
| Lượt giặt | mỗi phiếu là một lượt |
"""


def plan(metric: str) -> QueryPlan:
    return QueryPlan.model_validate({"intent": "value", "measures": [{"metric": metric}],
                                     "period": {"kind": "this_month"}})


def with_section(extra: str) -> str:
    text = TRAIN.read_text(encoding="utf-8-sig")
    head = text.index("## 7.")
    return text[:head] + extra + "\n" + text[head:]


pytestmark = pytest.mark.skipif(not TRAIN.exists(), reason="cần data/")


def test_revenue_in_a_shop_of_an_unknown_type_is_flagged():
    book = with_section(SALON)
    readme = "File Excel xuất từ phần mềm quản lý salon tóc và spa"
    assert rules.unknown_industry(book, readme, plan("revenue")) == ["§6.salon_toc_va_spa"]
    assert rules.unknown_industry(book, readme, plan("avg_order_value")) == ["§6.salon_toc_va_spa"]


def test_other_metrics_other_shops_and_known_types_are_not():
    book = with_section(SALON)
    assert rules.unknown_industry(book, "phần mềm quản lý salon tóc và spa", plan("order_count")) == []
    assert rules.unknown_industry(book, "sổ bán hàng cửa hàng thú cưng, sổ spa", plan("revenue")) == []  # not all words
    assert rules.unknown_industry(with_section(PHONE_RENAMED), "cửa hàng điện thoại di động", plan("revenue")) == []
    assert rules.unknown_industry(with_section(NO_REVENUE), "tiệm giặt là", plan("revenue")) == []


def test_train_and_public_rulebooks_have_no_unknown_section():
    root = TRAIN.parents[1]
    for split in ("train", "public_test"):
        path = root / split / "rulebook.md"
        if path.exists():
            assert rules.unknown_sections(path.read_text(encoding="utf-8-sig")) == ()
