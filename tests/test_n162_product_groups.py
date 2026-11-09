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
