"""N73: a mapping that reads the order's day from "ngày bán" takes its hour from the README's "thời điểm đặt đơn" column,
only when every order keeps its day (public 07/11: two shops lost their shift questions, §2 "ca sáng, ca chiều")."""
from pathlib import Path

from datamate.contracts import ColumnMap, Mapping, RawBusiness, TableMap
from datamate.mapping.from_readme import enrich, with_order_hour

from test_mapping_readme import section, table

NOTES = {"Bill": "mã đơn", "Ngày": "ngày bán", "Giờ bán": "thời điểm đặt đơn (ngày giờ)", "TT": "trạng thái đơn"}


def shop(rows: list[tuple]) -> RawBusiness:
    return RawBusiness(root=Path("."), readme=section("hd.csv", NOTES), tables=[table("hd.csv", rows, list(NOTES))])


def moved(has_time: bool = False) -> Mapping:
    """A mapping moved from a one-file example: the order's day from "Ngày", no hour."""
    return Mapping(tables=[TableMap(target="orders", sources=["hd.csv"], columns=[
        ColumnMap(target="order_id", source="Bill"), ColumnMap(target="order_time", source="Ngày", parse="datetime"),
        ColumnMap(target="status", source="TT"), ColumnMap(target="has_time", const=has_time)])],
        notes=["ghép theo nghĩa với mapping mẫu X"])


ROWS = [("B1", "01/06/2026", "2026-06-01 08:15:00", "completed"), ("B1", "01/06/2026", "2026-06-01 08:15:00", "completed"),
        ("B2", "01/06/2026", "2026-06-01 15:40:00", "completed"), ("B3", "02/06/2026", "2026-06-02 21:05:00", "cancelled")]


def time_columns(m: Mapping) -> tuple:
    cols = {c.target: c for c in next(t for t in m.tables if t.target == "orders").columns}
    return cols["order_time"].source, cols["has_time"].const


def test_the_order_takes_its_hour_from_the_readmes_moment_of_ordering():
    m = with_order_hour(moved(), shop(ROWS))
    assert time_columns(m) == ("Giờ bán", True)
    assert m.notes[-1] == "bổ sung từ README: orders.order_time có giờ"
    assert time_columns(enrich(moved(), shop(ROWS))) == ("Giờ bán", True)  # enrich applies it


def test_an_order_whose_day_would_change_keeps_the_mapping():
    rows = ROWS[:3] + [("B3", "02/06/2026", "2026-06-03 00:30:00", "cancelled")]  # past midnight: another day
    assert time_columns(with_order_hour(moved(), shop(rows))) == ("Ngày", False)


def test_a_moment_column_without_hours_or_a_mapping_with_hours_is_left_alone():
    midnight = [(b, d, t[:10] + " 00:00:00", s) for b, d, t, s in ROWS]
    assert time_columns(with_order_hour(moved(), shop(midnight))) == ("Ngày", False)
    assert time_columns(with_order_hour(moved(has_time=True), shop(ROWS))) == ("Ngày", True)
