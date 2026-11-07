"""N40: a ledger without a status column writes the order's status in its note (public rulebook §8, "sổ không có
cột trạng thái: trạng thái đơn ghi ở cột Ghi chú. Ghi chú không nhắc trạng thái là đơn hoàn thành"): two phone
shops and a mother-and-baby shop of public, an industry train has none of."""
from pathlib import Path

import pandas as pd

from datamate.contracts import Mapping, RawBusiness, RawTable
from datamate.mapping.build import _status_from_note, build_canonical, run_checks


def test_a_note_gives_the_status_it_names_else_completed():
    assert _status_from_note("khách trả lại máy, hoàn tiền") == "returned"
    assert _status_from_note("Đơn huỷ") == "cancelled"
    assert _status_from_note("đang giao") == "delivering"
    assert _status_from_note("khách mang trả") == "returned"  # a public phone ledger's note, 06/11
    assert _status_from_note("kiểm tra lại tuần sau") == "completed"  # "check again", no return (a repair ledger)
    assert _status_from_note("xe để lại qua đêm") == "completed"  # names no status
    assert _status_from_note(None) == "completed" and _status_from_note("") == "completed"
    assert _status_from_note("đã giao, khách trả hàng") is None  # two statuses: unclear


def test_a_flat_ledger_takes_its_order_status_from_the_note():
    rows = [(f"{1 + i // 2}", f"{1 + i % 28:02d}/06/2026", f"Hàng {i % 12}", "1", "100000",
             "khách trả lại" if i == 6 else "") for i in range(40)]
    frame = pd.DataFrame(rows, columns=["STT", "Ngày", "Hàng", "SL", "Thành tiền", "Ghi chú"])
    raw = RawBusiness(root=Path("."), readme="", tables=[
        RawTable(table_id="So.xlsx::T6", file="So.xlsx", sheet="T6", frame=frame)])
    m = Mapping.model_validate({"tables": [
        {"target": "orders", "sources": ["So.xlsx::*"], "columns": [
            {"target": "order_id", "source": "STT"}, {"target": "order_time", "source": "Ngày", "parse": "datetime"},
            {"target": "has_time", "const": False}, {"target": "status", "source": "Ghi chú",
                                                     "transform": "status_from_note"}]},
        {"target": "lines", "sources": ["So.xlsx::*"], "columns": [
            {"target": "order_id", "source": "STT"}, {"target": "product_key", "source": "Hàng"},
            {"target": "product_name", "source": "Hàng"}, {"target": "is_item", "const": True},
            {"target": "qty", "source": "SL", "parse": "qty"},
            {"target": "line_amount", "source": "Thành tiền", "parse": "money"}]}]})
    db = build_canonical(raw, m)
    o = db.tables["orders"].set_index("order_id")["status"]
    assert o["4"] == "returned" and (o.drop("4") == "completed").all()  # the return is noted on the order's first row
    checks = {c.name: c.passed for c in run_checks(db, "")}
    assert checks["trạng thái đơn đã quy đổi"] and checks["trạng thái hợp lý"]


def test_the_readme_path_reads_a_ledger_whose_status_is_in_its_note():
    """The README phrases of public ledgers that train never used: "số thứ tự đơn (hoá đơn) trong sổ" / "số hoá đơn"
    for the order id, "thành tiền của dòng", "hàng bán, có thể ghi tắt", and no status column but "ghi chú của đơn;
    đơn khách trả lại hàng ghi ở đây"."""
    from datamate.mapping.from_readme import map_from_readme
    notes = {"Ngày": "ngày bán", "STT": "số thứ tự đơn (hoá đơn) trong sổ", "Khách": "tên khách (khách lẻ nếu không lưu)",
             "Hàng": "hàng bán, có thể ghi tắt (tra ở sheet Ghi tắt)", "SL": "số lượng",
             "Giá": "đơn giá một cái", "Thành tiền": "thành tiền của dòng",
             "Ghi chú": "ghi chú của đơn; đơn khách trả lại hàng ghi ở đây"}
    readme = "## Cột trong `SoBanHang.xlsx`\n" + "".join(f"- **{c}**: {m}\n" for c, m in notes.items()) + \
        "\n## Quy ước\n- Dữ liệu có đến hết 28/06/2026.\n"
    rows = [(f"{1 + i % 28:02d}/06/2026", f"{1 + i // 2}", "An" if i % 3 else "Khách lẻ", f"Ốp lưng {i % 12}", "1",
             "100000", "100000", "khách trả lại" if i == 6 else "") for i in range(40)]
    frame = pd.DataFrame(rows, columns=list(notes))
    raw = RawBusiness(root=Path("."), readme=readme, tables=[
        RawTable(table_id="SoBanHang.xlsx::Sổ bán hàng", file="SoBanHang.xlsx", sheet="Sổ bán hàng", frame=frame)])
    m, why = map_from_readme(raw)
    assert m is not None, why
    orders = {c.target: c for c in m.tables[0].columns}
    assert orders["order_id"].source == "STT" and orders["status"].source == "Ghi chú"
    assert orders["status"].transform == "status_from_note"
    lines = {c.target: c.source for c in m.tables[1].columns}
    assert lines["line_amount"] == "Thành tiền" and lines["product_name"] == "Hàng"
    db = build_canonical(raw, m)
    assert all(c.passed for c in run_checks(db, readme)), [(c.name, c.detail) for c in run_checks(db, readme)
                                                           if not c.passed]


def test_rows_whose_note_names_nothing_do_not_outvote_the_order_note():
    """The note sits on the order's first row; its voucher and shipping rows have none (public mother-and-baby shop,
    06/11): a cancelled order with an empty voucher row was "cancelled and completed", unclear, and the shop failed
    the status check. Notes naming nothing do not count; an order whose notes name nothing is completed."""
    from datamate.mapping.build import _note_status, _status_from_notes
    assert _status_from_notes(pd.Series([_note_status(n) for n in ["Huỷ", None, ""]])) == "cancelled"
    assert _status_from_notes(pd.Series([_note_status(n) for n in [None, "xe để lại qua đêm"]])) == "completed"
    assert _status_from_notes(pd.Series([_note_status(n) for n in ["Huỷ", "khách trả lại"]])) is None
    assert _status_from_notes(pd.Series([_note_status("đã giao, khách trả hàng")])) is None
    assert _status_from_note("chưa giao") == "delivering"  # not delivered yet: in delivery (§8: four statuses)


def test_voucher_points_and_shipping_rows_are_order_amounts_not_lines():
    """N41, public mother-and-baby ledger (06/11): after an order's lines come rows "Voucher" and "Dùng <n> điểm"
    (negative amount) and "Phí ship". §1: an order's revenue is its item lines, not less its voucher, without its
    shipping; §6 asks these amounts as positive numbers. They become the order's voucher_discount, points_discount and
    shipping_fee, and leave the lines."""
    from datamate.contracts import CanonicalDB
    from datamate.mapping.build import order_level_lines
    db = CanonicalDB(tables={
        "orders": pd.DataFrame({"order_id": ["D1", "D2"]}),
        "lines": pd.DataFrame({"order_id": ["D1", "D1", "D1", "D1", "D2"],
                               "product_name": ["Sữa Enfamil số 1", "Voucher", "Dùng 30 điểm", "Phí ship", "Bỉm L"],
                               "qty": [1, None, None, None, 2],
                               "line_amount": [560_000, -10_000, -3_000, 25_000, 300_000]})})
    order_level_lines(db)
    o = db.tables["orders"].set_index("order_id")
    assert o.loc["D1", "voucher_discount"] == 10_000 and o.loc["D1", "points_discount"] == 3_000
    assert o.loc["D1", "shipping_fee"] == 25_000 and pd.isna(o.loc["D2", "voucher_discount"])
    assert db.tables["lines"]["product_name"].tolist() == ["Sữa Enfamil số 1", "Bỉm L"]


def test_a_moved_mapping_reads_the_status_from_the_note_of_a_ledger_without_one():
    """A public phone ledger with no README column notes (06/11) is mapped by role from a train example, whose status
    column the ledger has not: the one "Ghi chú" column of the shop's table gives the status (§8), whether the LLM
    left the status unmatched or took the note for it."""
    from datamate.contracts import ColumnMap, TableMap
    from datamate.mapping import transfer
    rows = [(f"{1 + i // 2}", f"{1 + i % 28:02d}/06/2026", f"Ốp lưng {i % 12}", "1", "100000",
             "khách trả lại" if i == 6 else "") for i in range(40)]
    frame = pd.DataFrame(rows, columns=["STT", "Ngày", "Hàng", "SL", "Thành tiền", "Ghi chú"])
    raw = RawBusiness(root=Path("."), readme="", tables=[
        RawTable(table_id="So.xlsx::T6", file="So.xlsx", sheet="T6", frame=frame)])
    taken = Mapping(tables=[TableMap(target="orders", sources=["So.xlsx::T6"], columns=[
        ColumnMap(target="order_id", source="STT"), ColumnMap(target="status", source="Ghi chú")],
        value_maps={"status": {"khách trả lại": "returned"}})])
    fixed = transfer.status_in_note(taken, raw)
    status = next(c for c in fixed.tables[0].columns if c.target == "status")
    assert status.transform == "status_from_note" and "status" not in fixed.tables[0].value_maps
    assert transfer.note_column(raw, ["So.xlsx::T6"]) == "Ghi chú"
    words = frame.assign(**{"Ghi chú": ["Xong"] * 39 + ["Huỷ"]})  # a real status column named so: left alone
    raw2 = RawBusiness(root=Path("."), readme="", tables=[RawTable(table_id="So.xlsx::T6", file="So.xlsx", sheet="T6",
                                                                     frame=words)])
    kept = transfer.status_in_note(taken, raw2)
    assert next(c for c in kept.tables[0].columns if c.target == "status").transform is None


def test_abbreviated_products_are_read_with_the_shop_abbreviation_sheet():
    """Public phone ledgers (06/11): "Hàng: hàng bán, có thể ghi tắt (tra ở sheet Ghi tắt)": the lines write "Sạc 20W",
    "IP16 128 đen", the questions "Củ sạc nhanh 20W Type-C". A table of the shop whose one column holds most of the
    lines' product values and another their names (written with a space) gives the product key and name."""
    from datamate.contracts import ColumnMap, TableMap
    from datamate.mapping import transfer
    abbrev = pd.DataFrame([(f"Sạc {i}W", f"Củ sạc nhanh {i}W Type-C", "phụ kiện") for i in range(12)],
                          columns=["Ghi tắt", "Tên hàng", "Loại"])
    # some lines abbreviated, the others written by the full name (as the public ledger: 59 and 56 of 115)
    sales = pd.DataFrame([(f"{1 + i // 2}", f"Sạc {i % 12}W" if i % 3 else f"Củ sạc nhanh {i % 12}W Type-C", "1")
                          for i in range(40)], columns=["STT", "Hàng", "SL"])
    raw = RawBusiness(root=Path("."), readme="", tables=[
        RawTable(table_id="So.xlsx::Ghi tắt", file="So.xlsx", sheet="Ghi tắt", frame=abbrev),
        RawTable(table_id="So.xlsx::T6", file="So.xlsx", sheet="T6", frame=sales)])
    m = Mapping(tables=[TableMap(target="lines", sources=["So.xlsx::T6"], columns=[
        ColumnMap(target="order_id", source="STT"), ColumnMap(target="product_key", source="Hàng"),
        ColumnMap(target="product_name", source="Hàng"), ColumnMap(target="qty", source="SL", parse="qty")])])
    out = {c.target: c for c in transfer.expand_abbreviations(m, raw).tables[0].columns}
    for target in ("product_key", "product_name"):
        assert out[target].transform == "lookup" and out[target].args["table"] == "So.xlsx::Ghi tắt"
        assert out[target].args["key"] == "Ghi tắt" and out[target].args["value"] == "Tên hàng"
    # a ledger keyed by codes, a catalogue of codes and names: the codes stay the keys (train, 06/11)
    coded = RawBusiness(root=Path("."), readme="", tables=[
        RawTable(table_id="sp.csv", file="sp.csv", sheet=None, frame=pd.DataFrame(
            [(f"SP{i:03d}", f"Củ sạc nhanh {i}W Type-C") for i in range(12)], columns=["Mã HH", "Tên sản phẩm"])),
        RawTable(table_id="ct.csv", file="ct.csv", sheet=None, frame=pd.DataFrame(
            [(f"{1 + i // 2}", f"SP{i % 12:03d}", "1") for i in range(40)], columns=["STT", "Hàng", "SL"]))])
    m2 = Mapping(tables=[TableMap(target="lines", sources=["ct.csv"], columns=[
        ColumnMap(target="order_id", source="STT"), ColumnMap(target="product_key", source="Hàng"),
        ColumnMap(target="qty", source="SL", parse="qty")])])
    assert transfer.expand_abbreviations(m2, coded) is m2


def test_a_base_unit_column_of_many_values_is_no_unit():
    """A moved mapping read the abbreviation column for the base unit (59 values); a train shop has 15 at most."""
    from datamate.contracts import CanonicalDB
    from datamate.mapping.build import sane_base_units
    db = CanonicalDB(tables={"products": pd.DataFrame({"product_key": [f"P{i}" for i in range(59)],
                                                       "base_unit": [f"Sạc {i}W" for i in range(59)]})})
    sane_base_units(db)
    assert db.tables["products"]["base_unit"].isna().all()
    ok = CanonicalDB(tables={"products": pd.DataFrame({"product_key": ["P1", "P2"], "base_unit": ["chai", "gói"]})})
    sane_base_units(ok)
    assert ok.tables["products"]["base_unit"].tolist() == ["chai", "gói"]


def test_a_flat_ledger_reads_the_order_amounts_its_readme_names():
    """A public phone ledger (06/11): "Bớt: tiền bớt cho cả đơn", "Thu máy cũ: tiền thu máy cũ của khách, trừ vào tiền
    đơn", "Khách trả: số tiền khách trả cho cả đơn, đã trừ bớt và thu máy cũ" are cells of the order on its rows."""
    from datamate.mapping.from_readme import map_from_readme
    notes = {"Ngày": "ngày bán", "STT": "số thứ tự đơn (hoá đơn) trong sổ", "Hàng": "hàng bán, có thể ghi tắt",
             "SL": "số lượng", "Thành tiền": "thành tiền của dòng", "Bớt": "tiền bớt cho cả đơn (trống: không bớt)",
             "Thu máy cũ": "tiền thu máy cũ của khách, trừ vào tiền đơn (trống: không thu máy)",
             "Khách trả": "số tiền khách trả cho cả đơn, đã trừ bớt và thu máy cũ",
             "Ghi chú": "ghi chú của đơn; đơn khách trả lại hàng ghi ở đây"}
    readme = "## Cột trong `SoBanHang.xlsx`\n" + "".join(f"- **{c}**: {m}\n" for c, m in notes.items())
    rows = [(f"{1 + i % 28:02d}/06/2026", f"{1 + i // 2}" if i % 2 == 0 else "", f"Ốp lưng {i % 12}", "1", "100000",
             "10000" if i % 2 == 0 else "", "", "190000" if i % 2 == 0 else "", "") for i in range(40)]
    raw = RawBusiness(root=Path("."), readme=readme, tables=[RawTable(
        table_id="SoBanHang.xlsx::Sổ bán hàng", file="SoBanHang.xlsx", sheet="Sổ bán hàng",
        frame=pd.DataFrame(rows, columns=list(notes)))])
    m, why = map_from_readme(raw)
    assert m is not None, why
    orders = {c.target: c.source for c in m.tables[0].columns}
    assert orders["order_discount"] == "Bớt" and orders["trade_in_amount"] == "Thu máy cũ"
    assert orders["total_due"] == "Khách trả"
