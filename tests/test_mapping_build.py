"""G2 part 1: named transforms, §8 fill-down before dedup, glob sources, base quantity, order date, parsed constants."""
from datetime import date
from pathlib import Path

import pandas as pd

from datamate.contracts import ColumnMap, Mapping, RawBusiness, RawTable, TableMap
from datamate.mapping import build_canonical, run_checks

STATUS = {"Xong": "completed", "Hủy": "cancelled", "Trả": "returned", "Đang giao": "delivering"}


def raw(*tables: tuple[str, pd.DataFrame, int | None]) -> RawBusiness:
    return RawBusiness(root=Path("."), readme="", tables=[
        RawTable(table_id=tid, file=tid.split("::")[0], sheet=None, frame=f.astype(str), year_hint=y)
        for tid, f, y in tables])


def sales_mapping(status: ColumnMap | None = None, extra_lines: list[ColumnMap] = ()) -> Mapping:
    return Mapping(tables=[
        TableMap(target="orders", sources=["So.xlsx::*"], value_maps={"status": STATUS},
                 columns=[ColumnMap(target="order_id", source="Ma"),
                          ColumnMap(target="order_time", source="Ngay", parse="datetime"),
                          status or ColumnMap(target="status", source="TT"),
                          ColumnMap(target="customer_key", source="Khach")]),
        TableMap(target="lines", sources=["So.xlsx::*"],
                 columns=[ColumnMap(target="order_id", source="Ma"), ColumnMap(target="product_key", source="Hang"),
                          ColumnMap(target="product_name", source="Hang"),
                          ColumnMap(target="qty", source="SL", transform="split_qty_unit", args={"part": "qty"},
                                    parse="qty"),
                          ColumnMap(target="unit", source="SL", transform="split_qty_unit", args={"part": "unit"}),
                          ColumnMap(target="line_amount", source="Tien", parse="money"), *extra_lines]),
        TableMap(target="unit_conversions", sources=["QuyDoi.xlsx::Sheet1"],
                 columns=[ColumnMap(target="product_key", source="Hang"), ColumnMap(target="unit", source="DV"),
                          ColumnMap(target="factor", source="HS", parse="number"),
                          ColumnMap(target="base_unit", source="Goc")])])


# one order per month sheet; order A's second line leaves the order cells blank (§8); dates "1/6" take the sheet year
JUNE = pd.DataFrame({"Ma": ["A", "", "", "B"], "Ngay": ["1/6", "", "", "2/6"], "TT": ["Xong", "", "", "Hủy"],
                     "Khach": ["Lan", "", "", "lẻ"], "Hang": ["Bia", "Mì", "Mì", "Bia"],
                     "SL": ["1 thùng", "2 gói", "2 gói", "3 lon"], "Tien": ["240.000đ", "8.000đ", "8.000đ", "30k"]})
JULY = pd.DataFrame({"Ma": ["C", "C"], "Ngay": ["3/7", "9/7"], "TT": ["Xong", "Trả"], "Khach": ["Tư", "Tư"],
                     "Hang": ["Bia", "Bia"], "SL": ["2 lon", "-1 lon"], "Tien": ["20k", "-10k"]})
CONV = pd.DataFrame({"Hang": ["Bia"], "DV": ["thùng"], "HS": ["24"], "Goc": ["lon"]})


def shop(mapping: Mapping):
    return build_canonical(raw(("So.xlsx::T06", JUNE, 2025), ("So.xlsx::T07", JULY, 2025),
                               ("QuyDoi.xlsx::Sheet1", CONV, None)), mapping)


def test_fill_down_then_dedup_glob_sources_and_sheet_year():
    db = shop(sales_mapping(ColumnMap(target="status", source="TT", transform="order_status_from_lines")))
    lines = db.tables["lines"]
    assert sorted(lines["order_id"]) == ["A", "A", "B", "C", "C"]  # A's two identical 'Mì' rows count once (§8)
    orders = db.tables["orders"].set_index("order_id")
    assert orders.loc["A", "customer_key"] == "Lan" and orders.loc["A", "order_time"].date() == date(2025, 6, 1)
    assert orders.loc["C", "status"] == "returned"  # one returned line makes the order returned
    assert orders.loc["C", "order_time"].date() == date(2025, 7, 3)  # the return line's later date is not the order's
    assert all(c.passed for c in run_checks(db))


def test_split_qty_unit_and_base_quantity_from_conversions():
    lines = shop(sales_mapping()).tables["lines"]
    first = lines[(lines.order_id == "A") & (lines.product_key == "Bia")].iloc[0]
    assert (first.qty, first.unit, first.base_qty) == (1, "thùng", 24)  # 1 thùng = 24 lon
    assert lines[lines.order_id == "B"].iloc[0].base_qty == 3  # the base unit itself
    assert lines[lines.product_key == "Mì"].iloc[0].base_qty == 2  # a product without conversions


def test_unknown_unit_of_a_converted_product_gets_no_base_quantity():
    june = JUNE.assign(SL=["1 két", "2 gói", "2 gói", "3 lon"])
    db = build_canonical(raw(("So.xlsx::T06", june, 2025), ("QuyDoi.xlsx::Sheet1", CONV, None)), sales_mapping())
    assert pd.isna(db.tables["lines"].iloc[0].base_qty) and any("không quy đổi" in w for w in db.warnings)


def test_note_contains_with_default_regex_concat_negate_lookup_and_parsed_constant():
    notes = pd.DataFrame({"Ma": ["A", "B", "C"], "Ngay": ["2025-06-01"] * 3, "GhiChu": ["", "khách trả lại", "hủy nhé"],
                          "Hang": ["Trà (M)", "Trà (L)", "CF"], "Xe": ["Vision", "SH", ""], "Bien": ["72B9", "51C", ""],
                          "Tien": ["10", "20", "30"], "Tat": ["TD", "TD", "CF"]})
    abbrev = pd.DataFrame({"Viet tat": ["CF"], "Ten day du": ["Cà phê đen"]})
    m = Mapping(tables=[
        TableMap(target="orders", sources=["S.csv"], columns=[
            ColumnMap(target="order_id", source="Ma"), ColumnMap(target="order_time", source="Ngay", parse="datetime"),
            ColumnMap(target="status", source="GhiChu", transform="note_contains",
                      args={"map": {"trả lại": "returned", "hủy": "cancelled"}, "default": "completed"}),
            ColumnMap(target="vehicle_model", transform="concat", sources=["Xe", "Bien"], args={"sep": " | "})]),
        TableMap(target="lines", sources=["S.csv"], columns=[
            ColumnMap(target="order_id", source="Ma"),
            ColumnMap(target="product_key", source="Tat", transform="lookup",
                      args={"table": "Tat.csv", "key": "Viet tat", "value": "Ten day du"}),
            ColumnMap(target="product_name", source="Hang"), ColumnMap(target="qty", const="2", parse="qty"),
            ColumnMap(target="line_amount", source="Tien", parse="money", transform="negate"),
            ColumnMap(target="unit", source="Hang", transform="regex_extract", args={"pattern": r"\((M|L)\)"})])])
    db = build_canonical(raw(("S.csv", notes, None), ("Tat.csv", abbrev, None)), m)
    o, ln = db.tables["orders"], db.tables["lines"]
    assert o["status"].tolist() == ["completed", "returned", "cancelled"]
    assert o["vehicle_model"].tolist() == ["Vision | 72B9", "SH | 51C", None]
    assert ln["product_key"].tolist() == ["TD", "TD", "Cà phê đen"] and ln["qty"].tolist() == [2, 2, 2]
    assert ln["line_amount"].tolist() == [-10, -20, -30] and ln["unit"].tolist() == ["M", "L", None]


# ---------------------------------------------------------------- H17: checks of meaning
def big_shop(n: int = 40) -> pd.DataFrame:
    return pd.DataFrame({"Ma": [f"O{i}" for i in range(n)], "Ngay": ["2025-06-01"] * (n - 1) + ["2025-06-30"],
                         "TT": ["Xong"] * (n - 2) + ["Hủy", "Trả"], "Hang": [f"Mì gói {i % 12}" for i in range(n)],
                         "SL": ["2"] * n,
                         "Gia": ["5.000đ"] * n, "Tien": ["10.000đ"] * n})


def meaning(frame: pd.DataFrame, amount: str = "Tien", readme: str = "", status=None) -> dict[str, bool]:
    m = Mapping(tables=[
        TableMap(target="orders", sources=["S.csv"], value_maps={"status": status or STATUS},
                 columns=[ColumnMap(target="order_id", source="Ma"),
                          ColumnMap(target="order_time", source="Ngay", parse="datetime"),
                          ColumnMap(target="status", source="TT")]),
        TableMap(target="lines", sources=["S.csv"],
                 columns=[ColumnMap(target="order_id", source="Ma"), ColumnMap(target="product_key", source="Hang"),
                          ColumnMap(target="product_name", source="Hang"),
                          ColumnMap(target="qty", source="SL", parse="qty"),
                          ColumnMap(target="unit_price", source="Gia", parse="money"),
                          ColumnMap(target="line_amount", source=amount, parse="money")])])
    return {c.name: c.passed for c in run_checks(build_canonical(raw(("S.csv", frame, None)), m), readme)}


def test_h17_a_correct_mapping_passes_every_check():
    assert all(meaning(big_shop(), readme="Dữ liệu có đến hết 30/06/2025.").values())


def test_h17_amount_taken_from_the_price_column_is_caught():
    assert not meaning(big_shop(), amount="Gia")["thành tiền khớp số lượng × đơn giá"]


def test_h17_statuses_mapped_the_wrong_way_round_are_caught():
    swapped = {**STATUS, "Xong": "cancelled", "Hủy": "completed"}
    assert not meaning(big_shop(), status=swapped)["trạng thái hợp lý"]


def test_h17_a_left_out_file_shows_as_an_early_data_end():
    assert not meaning(big_shop(), readme="Dữ liệu có đến hết 31/12/2025.")["ngày cuối khớp README"]


def test_h17_negative_amounts_outside_returns_are_caught():
    shop = big_shop().assign(Tien=["-10.000đ"] * 40, Gia=["-5.000đ"] * 40)
    assert not meaning(shop)["số âm chỉ ở đơn trả"]


def test_products_of_the_lines_look_like_products():
    """N27, train 05/11: every shop has 50-80 product keys and 100% of its names written with a space. An unfamiliar
    shop matched a one-value column for the product key and a code column for the name: the check stops it."""
    import pandas as pd

    from datamate.contracts import CanonicalDB
    from datamate.mapping.build import product_check
    names = [f"Sản phẩm {i}" for i in range(30)]
    ok = CanonicalDB(tables={"lines": pd.DataFrame({"product_key": [f"SP{i}" for i in range(30)], "product_name": names})})
    assert product_check(ok)[0]
    one = CanonicalDB(tables={"lines": pd.DataFrame({"product_key": ["1"] * 30, "product_name": names})})
    assert not product_check(one)[0]
    codes = CanonicalDB(tables={"lines": pd.DataFrame({"product_key": [f"K{i}" for i in range(30)],
                                                       "product_name": [f"SP{i:04d}" for i in range(30)]})})
    assert not product_check(codes)[0]
    few = CanonicalDB(tables={"lines": pd.DataFrame({"product_key": ["1"] * 5, "product_name": ["A"] * 5})})
    assert product_check(few)[0]  # too few lines to judge


def test_fill_down_takes_the_cell_of_the_order_first_row_not_of_an_earlier_order():
    """§8 "ô để trống ở các dòng sau của cùng một nhóm dòng: giống ô đó ở dòng đầu nhóm". The fill-down took the last
    non-blank cell of any row above: an order whose first row has no note took an earlier order's "trả lại hàng"
    (a public phone ledger, 06/11: 834 of 3 819 orders read as returned for 29 return notes)."""
    import pandas as pd

    from datamate.mapping.build import _fill_down
    ids = pd.Series(["1", "", "2", "", ""])
    notes = pd.Series(["trả lại hàng", "", "", "", ""])
    customers = pd.Series(["An", "", "", "", "Bình"])  # order 2: walk-in on its first row
    follow = ids.map(lambda v: v == "")
    assert _fill_down(notes, follow).tolist() == ["trả lại hàng", "trả lại hàng", "", "", ""]
    assert _fill_down(customers, follow).tolist() == ["An", "An", "", "", "Bình"]
