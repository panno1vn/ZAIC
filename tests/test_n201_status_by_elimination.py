"""N201: a shop that writes its completed orders with a word no hand mapping and no key word reads ("Đã bán",
"Hoàn tất") had every order without a status, failed the status checks on each candidate and abstained on every
question (self-made dev shops, tools/synth_shops3.py). §8: every order has exactly one of the four statuses, so the
one word left unread, on most orders of a shop where no word reads as completed, is the completed order."""
from pathlib import Path

import pandas as pd

from datamate.contracts import Mapping, RawBusiness, RawTable
from datamate.mapping import transfer
from datamate.mapping.build import build_canonical, run_checks
from datamate.mapping.transfer import read_word, status_by_elimination

STATUS_CHECKS = ("trạng thái đơn đã quy đổi", "trạng thái hợp lý")


def _shop(statuses: list[str]) -> RawBusiness:
    """One order per status given, two lines each, the order's cells on both lines."""
    rows = [(f"PX{i + 1:04d}", f"{1 + i % 28:02d}/06/2026", f"Hàng số {(i + j) % 12}", "2", "50000", "100000", st)
            for i, st in enumerate(statuses) for j in range(2)]
    frame = pd.DataFrame(rows, columns=["Số phiếu", "Ngày bán", "Tên hàng", "SL", "Đơn giá", "Thành tiền",
                                        "Trạng thái"])
    return RawBusiness(root=Path("."), readme="", tables=[
        RawTable(table_id="BangKe.xlsx::Bảng kê", file="BangKe.xlsx", sheet="Bảng kê", frame=frame)])


def _mapping(raw: RawBusiness, status: dict | None = None) -> Mapping:
    """What a transfer gives: the status words the hand mappings and the key words read, the others left out."""
    words = {str(v) for t in raw.tables for v in t.frame["Trạng thái"].unique() if str(v)}
    vm = {w: s for w in words if (s := read_word("orders", "status", w)) is not None}
    return Mapping.model_validate({"notes": ["mapping thử"], "tables": [
        {"target": "orders", "sources": ["BangKe.xlsx::*"], "value_maps": {"status": vm}, "columns": [
            {"target": "order_id", "source": "Số phiếu"}, {"target": "order_time", "source": "Ngày bán",
                                                          "parse": "datetime"},
            {"target": "has_time", "const": False}, status or {"target": "status", "source": "Trạng thái"}]},
        {"target": "lines", "sources": ["BangKe.xlsx::*"], "columns": [
            {"target": "order_id", "source": "Số phiếu"}, {"target": "product_key", "source": "Tên hàng"},
            {"target": "product_name", "source": "Tên hàng"}, {"target": "is_item", "const": True},
            {"target": "qty", "source": "SL", "parse": "qty"}, {"target": "unit_price", "source": "Đơn giá",
                                                               "parse": "money"},
            {"target": "line_amount", "source": "Thành tiền", "parse": "money"}]}]})


def _status_map(m: Mapping) -> dict:
    return next(tm for tm in m.tables if tm.target == "orders").value_maps.get("status", {})


def _checks(raw: RawBusiness, m: Mapping) -> dict:
    return {c.name: c.passed for c in run_checks(build_canonical(raw, m), "")}


def test_the_words_of_the_dev_shops_are_not_read_by_themselves():
    for word in ("Đã bán", "Hoàn tất", "Đã thanh toán"):
        assert read_word("orders", "status", word) is None
    assert read_word("orders", "status", "Huỷ") == "cancelled" and read_word("orders", "status", "Trả hàng") == "returned"


def test_the_one_unread_word_on_most_orders_is_the_completed_order():
    for word in ("Đã bán", "Hoàn tất", "Đã thanh toán"):
        raw = _shop([word] * 54 + ["Huỷ"] * 3 + ["Trả hàng"] * 3)
        before = _mapping(raw)
        checks = _checks(raw, before)
        assert not any(checks[name] for name in STATUS_CHECKS)  # the shop was dropped on these
        after = status_by_elimination(before, raw)
        assert _status_map(after) == {**_status_map(before), word: "completed"}
        checks = _checks(raw, after)
        assert all(checks[name] for name in STATUS_CHECKS)
        orders = build_canonical(raw, after).tables["orders"]["status"].value_counts().to_dict()
        assert orders == {"completed": 54, "cancelled": 3, "returned": 3}


def test_order_cells_written_on_the_first_line_only_count_once():
    raw = _shop(["Đã bán"] * 54 + ["Huỷ"] * 6)
    frame = raw.tables[0].frame
    frame.loc[frame.index % 2 == 1, "Trạng thái"] = ""  # the second line of every order leaves the cell blank
    after = status_by_elimination(_mapping(raw), raw)
    assert _status_map(after)["Đã bán"] == "completed"


def test_two_unread_words_are_left():
    raw = _shop(["Đã bán"] * 40 + ["Tạm giữ"] * 15 + ["Huỷ"] * 5)
    assert read_word("orders", "status", "Tạm giữ") is None
    m = _mapping(raw)
    assert status_by_elimination(m, raw) is m


def test_a_shop_whose_completed_word_is_read_is_left():
    for statuses in (["Hoàn thành"] * 40 + ["Tạm giữ"] * 15 + ["Huỷ"] * 5,
                     ["Tạm giữ"] * 35 + ["Hoàn thành"] * 20 + ["Huỷ"] * 5):
        raw = _shop(statuses)
        m = _mapping(raw)
        assert status_by_elimination(m, raw) is m


def test_an_unread_word_on_few_orders_is_left():
    raw = _shop(["Tạm giữ"] * 20 + ["Huỷ"] * 25 + ["Trả hàng"] * 15)
    m = _mapping(raw)
    assert status_by_elimination(m, raw) is m


def test_a_column_where_no_word_reads_as_a_status_is_left():
    for statuses in (["Bán lẻ"] * 60, ["Tiền mặt"] * 40 + ["Chuyển khoản"] * 20):
        raw = _shop(statuses)
        m = _mapping(raw)
        assert _status_map(m) == {} and status_by_elimination(m, raw) is m


def test_a_status_read_from_a_note_is_left():
    raw = _shop(["Đã bán"] * 54 + ["Huỷ"] * 6)
    m = _mapping(raw, {"target": "status", "source": "Trạng thái", "transform": "status_from_note"})
    assert status_by_elimination(m, raw) is m


def test_a_candidate_with_such_a_word_passes_the_checks():
    raw = _shop(["Đã bán"] * 54 + ["Huỷ"] * 3 + ["Trả hàng"] * 3)
    tried: list[str] = []
    ok = transfer._passes(_mapping(raw), raw, tried)
    assert ok is not None, tried
    assert _status_map(ok)["Đã bán"] == "completed" and any("§8" in n for n in ok.notes)
