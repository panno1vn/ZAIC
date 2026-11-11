"""N162: a shop whose mapping has no product group takes it from a column whose header says group, accents or not,
and whose values are a few names; never from a column of many values or of numbers."""
import pandas as pd

from datamate.contracts import Mapping, RawBusiness
from datamate.contracts.raw import RawTable
from datamate.mapping.named_sides import _Shop, product_groups


def _shop(group_header="Nhom hang(3 Cap)", groups=None):
    n = 12
    groups = groups or (["sữa", "gạo", "bia"] * 4)
    frame = pd.DataFrame({"Ma HD": [f"HD{i}" for i in range(n)], "Ngay": ["01/02/2025"] * n,
                          "Ma hang": [f"SP{i % 4}" for i in range(n)], group_header: groups,
                          "SL": ["1"] * n, "Thanh tien": ["1000"] * n})
    raw = RawBusiness(root=None, readme="", tables=[RawTable(table_id="ban.csv", file="ban.csv", sheet=None,
                                                             frame=frame)])
    mapping = Mapping.model_validate({"tables": [
        {"target": "orders", "sources": ["ban.csv"], "columns": [
            {"target": "order_id", "source": "Ma HD"}, {"target": "order_time", "source": "Ngay", "parse": "date"}]},
        {"target": "lines", "sources": ["ban.csv"], "columns": [
            {"target": "order_id", "source": "Ma HD"}, {"target": "product_key", "source": "Ma hang"},
            {"target": "product_name", "source": "Ma hang"}, {"target": "is_item", "const": True},
            {"target": "qty", "source": "SL", "parse": "qty"},
            {"target": "line_amount", "source": "Thanh tien", "parse": "money"}]}]})
    return _Shop(mapping, raw)


def test_group_column_found_without_accents():
    got = product_groups(_shop())
    assert [(t, c.target, c.source) for t, cols in got.items() for c in cols] == [
        ("lines", "product_group", "Nhom hang(3 Cap)")]


def test_customer_group_or_many_values_are_not_product_groups():
    assert product_groups(_shop(group_header="Nhom khach hang")) == {}
    assert product_groups(_shop(groups=[f"g{i}" for i in range(12)])) != {}  # 12 names: still few
    assert product_groups(_shop(groups=[str(i) for i in range(12)])) == {}  # numbers are not group names


# ---- N170 (R003): the header must say the group is of goods
def test_headers_that_are_not_product_groups():
    for header in ("Ten phan loai hang", "Phan loai khach", "Phan loai kenh", "Danh muc khach hang"):
        assert product_groups(_shop(group_header=header)) == {}, header
    for header in ("Nhom hang(3 Cap)", "Nhom hang", "Loai hang", "Danh muc san pham"):
        assert product_groups(_shop(group_header=header)) != {}, header


def test_bare_danh_muc_is_not_a_group_in_the_lines_table():
    assert product_groups(_shop(group_header="Danh muc")) == {}


def test_column_taken_by_customer_group_is_not_the_product_group():
    assert product_groups(_shop(), taken={"Nhom hang(3 Cap)"}) == {}
