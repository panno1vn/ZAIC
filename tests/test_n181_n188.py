"""N181–N188 (train blanks 10/11): comparisons of periods — one period back written as n = 1, the same month of last
year, a price rise whose day the question writes, a price list the README's "Giá bán" convention names, months
listed for "n tháng liền nhau", "N ngày trước Tết", two shifts as two measures, a trend over a range of months."""
from pathlib import Path

import pandas as pd

from datamate.contracts import QueryPlan
from datamate.nlu import grounding, repair


def plan(**kw) -> QueryPlan:
    return QueryPlan.model_validate({"intent": "compare", "measures": [{"metric": "revenue"}], **kw})


def test_one_period_back_is_no_length():
    p = plan(period={"kind": "tet", "lunar_year": 2026}, compare={"kind": "previous", "n": 1})
    assert grounding.one_period_back(p).compare.n is None
    before = plan(period={"kind": "tet", "lunar_year": 2026}, compare={"kind": "before_tet", "n": 17})
    assert grounding.one_period_back(before) is before


def test_the_same_month_of_last_year():
    p = plan(period={"kind": "month", "year": 2026, "month": 6}, compare={"kind": "previous"})
    q = "dthu thang 6 nam 2026 tang truong bnhiu % so vs thang 6 nam 2025"
    assert grounding.same_month_last_year(q, p).compare.kind == "same_period_last_year"
    assert grounding.same_month_last_year("dthu thang 6/2026 so vs 6/2025", p).compare.kind == "same_period_last_year"
    assert grounding.same_month_last_year("dthu thang 6/2026 so voi thang truoc", p) is p


def test_a_price_rise_on_a_day_the_question_writes():
    q = "ê X lên giá 231.500đ từ ngày 20/05/2025; so 30 ngày kể từ ngày tăng giá với 30 ngày ngay trc"
    p = plan(measures=[{"metric": "quantity", "filters": [{"field": "product", "value": "X"}]}],
             period={"kind": "days_from", "anchor_price": 231500, "n": 30}, compare={"kind": "before_days_from"})
    got = grounding.rise_day_written(q, p).period
    assert (got.date, got.anchor_price) == ("2025-05-20", None)
    assert grounding.rise_day_written("từ hồi X lên giá 47.000đ, so 30 ngày", p) is p


def test_months_listed_for_n_months_in_a_row():
    p = QueryPlan.model_validate({"intent": "series", "measures": [{"metric": "revenue"}],
                                  "period": {"kind": "months", "months": ["2025-04", "2025-05", "2025-06"]}})
    q = "dthu 3 tháng liền nhau kết thúc ở tháng 6/2025 là bao nhiêu mỗi tháng"
    got = grounding.months_listed_as_run(q, p).period
    assert (got.kind, got.end, got.n, got.months) == ("months", "2025-06", 3, None)
    assert grounding.months_listed_as_run("dthu th4, th5, th6/2025 lần lượt", p) is p


def test_days_before_tet():
    p = plan(period={"kind": "tet", "lunar_year": 2026},
             compare={"kind": "before_days_from", "period": {"kind": "days_from", "date": "2026-01-20", "n": 17}})
    got = grounding.days_before_tet("Dịp Tết âm lịch 2026 có doanh thu hơn hay kém 17 ngày trước Tết bao nhiêu %?", p)
    assert (got.compare.kind, got.compare.n, got.compare.period) == ("before_tet", 17, None)


def test_two_shifts_written_as_two_measures():
    raw = {"intent": "compare", "period": {"kind": "last_week"},
           "measures": [{"metric": "order_count", "filters": [{"field": "shift", "value": "afternoon"}]},
                        {"metric": "order_count", "filters": [{"field": "shift", "value": "morning"}]}],
           "compare": {"kind": "period", "output": "pct_change", "n": 2}}
    out = repair.repair(raw, "Tuần trước số đơn ca chiều chênh ca sáng bao nhiêu phần trăm?",
                        "compare period cần trường period")
    p = QueryPlan.model_validate(out)
    assert p.compare.kind == "filter" and [f.value for f in p.compare.filters] == ["morning"]
    assert [f.value for f in p.measures[0].filters] == ["afternoon"] and len(p.measures) == 1


def test_a_trend_over_a_range_of_months():
    raw = {"intent": "trend", "period": {"kind": "range", "start": "2025-11", "end": "2026-01"},
           "measures": [{"metric": "revenue"}]}
    out = repair.repair(raw, "Từ tháng 11/2025 đến tháng 1/2026, doanh thu tháng sau có luôn cao hơn tháng trước không?",
                        "intent trend cần period kind months")
    assert out["period"] == {"kind": "months", "months": ["2025-11", "2025-12", "2026-01"]}


def test_the_price_list_the_readme_convention_names():
    """N184, on the shape of a train POS: `lich_su_gia.GiaBanLe` from `lich_su_gia.NgayApDung`."""
    from datamate.contracts import RawBusiness, RawTable
    from datamate.mapping.named_sides import _Shop, named, price_history
    from datamate.contracts import ColumnMap, Mapping, TableMap

    readme = ("# Dữ liệu\n## Quy ước\n- **Giá bán**: `lich_su_gia.GiaBanLe` (theo đơn vị cơ bản) áp dụng từ "
              "`lich_su_gia.NgayApDung` đến trước lần đổi giá sau của cùng mặt hàng; dòng đầu mỗi mặt hàng là giá lúc "
              "bắt đầu dữ liệu.\n")
    t = lambda tid, rows, cols: RawTable(table_id=tid, file="pos.sqlite", sheet=tid.split("::")[1],  # noqa: E731
                                         frame=pd.DataFrame(rows, columns=cols).astype(str))
    raw = RawBusiness(root=Path("."), readme=readme, tables=[
        t("pos.sqlite::don_hang", [("D1", "2025-11-20")], ["MaHoaDon", "NgayLap"]),
        t("pos.sqlite::chi_tiet_don", [("D1", "SP1", "Vitamin C", "2", "44000")],
          ["MaHoaDon", "MaHangHoa", "TenHang", "SL", "GiaDonVi"]),
        t("pos.sqlite::lich_su_gia", [("SP1", "2025-01-01", "40000"), ("SP1", "2025-11-20", "44000")],
          ["MaHangHoa", "NgayApDung", "GiaBanLe"])])
    cm = lambda tg, s, **k: ColumnMap(target=tg, source=s, **k)  # noqa: E731
    mapping = Mapping(tables=[
        TableMap(target="orders", sources=["pos.sqlite::don_hang"],
                 columns=[cm("order_id", "MaHoaDon"), cm("order_time", "NgayLap", parse="datetime")]),
        TableMap(target="lines", sources=["pos.sqlite::chi_tiet_don"],
                 columns=[cm("order_id", "MaHoaDon"), cm("product_key", "MaHangHoa"), cm("product_name", "TenHang"),
                          cm("qty", "SL", parse="qty"),
                          cm("unit_price", "GiaDonVi", parse="money")])])
    tm = price_history(_Shop(mapping, raw), named(readme))
    assert tm is not None and tm.sources == ["pos.sqlite::lich_su_gia"]
    assert {c.target: c.source for c in tm.columns} == {"product_key": "MaHangHoa", "effective_date": "NgayApDung",
                                                        "price": "GiaBanLe"}


def test_a_weekday_the_question_does_not_write():
    """N189."""
    p = QueryPlan.model_validate({"intent": "value", "period": {"kind": "this_week"}, "measures": [
        {"metric": "revenue", "filters": [{"field": "weekday", "op": "in", "value": "mon"}]}]})
    assert grounding.weekday_not_written("tuần nayf dthu đươc bao nhiêu", p).measures[0].filters == []
    for q in ("doanh thu thứ 2 tuần này", "doanh thu T2 tuần này", "cuối tuần này bán được bao nhiêu"):
        assert grounding.weekday_not_written(q, p) is p, q
