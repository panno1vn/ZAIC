"""N90: a conversion factor mapped from a price column (public 08/11: 210 000 beside "Bằng" 6 for a box of 6)."""
from pathlib import Path

import pandas as pd

from datamate.contracts import ColumnMap, Mapping, RawBusiness, TableMap
from datamate.contracts.raw import RawTable
from datamate.mapping.from_readme import factor_not_price

SHEET = "Ban.xlsx::QuyDoi"


def raw(frame: pd.DataFrame) -> RawBusiness:
    return RawBusiness(root=Path("."), readme="", tables=[RawTable(table_id=SHEET, file="Ban.xlsx", sheet="QuyDoi",
                                                                  frame=frame)])


def mapping(factor_column: str) -> Mapping:
    return Mapping(tables=[TableMap(target="unit_conversions", sources=[SHEET], columns=[
        ColumnMap(target="product_key", source="Mã"), ColumnMap(target="unit", source="Quy cách"),
        ColumnMap(target="factor", source=factor_column, parse="number")])])


def factor_source(m: Mapping) -> str:
    return next(c.source for t in m.tables for c in t.columns if c.target == "factor")


def test_a_price_read_as_the_factor_takes_the_count_column():
    frame = pd.DataFrame({"Giá theo đơn vị quy đổi": [210000, 282000], "Mã": ["SP1", "SP2"], "Bằng": [6, 6],
                          "Quy cách": ["hộp", "hộp"]})
    assert factor_source(factor_not_price(mapping("Giá theo đơn vị quy đổi"), raw(frame))) == "Bằng"


def test_a_plausible_factor_or_no_single_other_column_is_kept():
    frame = pd.DataFrame({"Giá": [210000, 282000], "Mã": ["SP1", "SP2"], "Bằng": [6, 6], "Quy cách": ["hộp", "hộp"]})
    assert factor_source(factor_not_price(mapping("Bằng"), raw(frame))) == "Bằng"  # already a count
    two = frame.assign(Khác=[12, 24])
    assert factor_source(factor_not_price(mapping("Giá"), raw(two))) == "Giá"  # two candidates: left as it is
