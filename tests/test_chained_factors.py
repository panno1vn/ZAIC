"""N114: a conversion factor written with a unit name counts in that unit (README "số kèm tên đơn vị là tính theo
đơn vị đó, chỉ có số là tính theo đơn vị cơ bản")."""
import pandas as pd

from datamate.contracts import CanonicalDB, ColumnMap, Mapping, TableMap
from datamate.mapping.build import chained_factors


def test_a_factor_written_with_a_unit_counts_in_that_unit():
    conv = pd.DataFrame({"product_key": ["Panadol hộp 15 vỉ x 12 viên"] * 2 + ["Hapacol hộp 24 gói"],
                         "unit": ["vỉ", "hộp", "hộp"], "factor": [12.0, 15.0, 24.0], "base_unit": ["viên", "viên", "gói"]})
    raw = pd.DataFrame({"Tên": ["Panadol hộp 15 vỉ x 12 viên"] * 2 + ["Hapacol hộp 24 gói"], "ĐV": ["vỉ", "hộp", "hộp"],
                        "Tỉ lệ": ["12", "15 vỉ", "24"]})
    m = Mapping(tables=[TableMap(target="unit_conversions", sources=["QuyDoi.xlsx::Sheet1"], columns=[
        ColumnMap(target="product_key", source="Tên"), ColumnMap(target="unit", source="ĐV"),
        ColumnMap(target="factor", source="Tỉ lệ", parse="number")])])
    db = CanonicalDB(tables={"unit_conversions": conv})
    chained_factors(db, m, {"QuyDoi.xlsx::Sheet1": raw})
    assert list(db.table("unit_conversions")["factor"]) == [12.0, 180.0, 24.0]  # hộp = 15 vỉ × 12 viên
