"""N161: a value the question names that is in the shop's files is recorded (§7 does not apply), even when the
mapping did not recognise its column: unanswerable would be wrong, blank is not."""
import pandas as pd

from datamate.contracts import CanonicalDB, QueryPlan, RawBusiness
from datamate.contracts.raw import RawTable
from datamate.mapping.build import raw_values
from datamate.verify import not_recorded

README = "# Dữ liệu\n\n## File\n- `ban_hang.csv`: mỗi dòng một mặt hàng trong đơn\n"


def _plan(group):
    return QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "revenue", "filters": [
        {"field": "product_group", "op": "eq", "value": group}]}], "period": {"kind": "month", "year": 2025, "month": 6}})


def _db(groups):
    frame = pd.DataFrame({"Ma don": ["HD1", "HD2", "HD3"], "Nhom hang(3 Cap)": groups, "Thanh tien": ["1", "2", "3"]})
    raw = RawBusiness(root=None, readme=README, tables=[RawTable(table_id="t", file="ban_hang.csv", sheet=None,
                                                                 frame=frame)])
    return CanonicalDB(tables={"lines": pd.DataFrame({"product_key": ["a"], "line_amount": [1.0]})}, readme=README,
                       values=raw_values(raw), conventions=())


def test_value_in_an_unmapped_column_is_recorded():
    db = _db(["Sữa", "Gạo", "sữa"])
    assert "sua" in db.values and "gao" in db.values
    assert not_recorded(_plan("sữa"), "doanh thu nhóm sữa tháng 6/2025", db) is None


def test_value_nowhere_in_the_files_is_still_not_recorded():
    db = _db(["Sữa", "Gạo", "Gạo"])
    assert not_recorded(_plan("bánh kẹo"), "doanh thu nhóm bánh kẹo tháng 6/2025", db) == "nhóm hàng"


def test_numbers_and_many_valued_columns_are_not_values():
    frame = pd.DataFrame({"so": [str(i) for i in range(5)], "ten": [f"khach {i}" for i in range(5)]})
    big = pd.DataFrame({"ma": [f"x{i}" for i in range(400)]})
    raw = RawBusiness(root=None, readme="", tables=[RawTable(table_id="a", file="a.csv", sheet=None, frame=frame),
                                                     RawTable(table_id="b", file="b.csv", sheet=None, frame=big)])
    vals = raw_values(raw)
    assert "khach 1" in vals and "1" not in vals and "x1" not in vals
