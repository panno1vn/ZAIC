"""N164: the LLM's column matching changes with the order of the columns; a pick whose values cannot hold the
meaning (a "name" with 3 values for 300 keys, a "group" holding one value) is refused and asked once more among
the columns not taken."""
from pathlib import Path

import pandas as pd
import pytest

from datamate.contracts.raw import RawBusiness, RawTable
from datamate.mapping import transfer

TARGETS = {"ma": {"customer_key"}, "ten": {"customer_name"}, "nhom": {"customer_group"}}


def _raw() -> RawBusiness:
    n = 60
    frame = pd.DataFrame({"Loai": ["lẻ", "sỉ", "thân thiết"] * (n // 3), "TrangThai": ["Đang hoạt động"] * n,
                          "Ma": [f"KH{i:03}" for i in range(n)], "Ten": [f"Khách {i}" for i in range(n)]})
    return RawBusiness(root=Path("."), readme="", tables=[RawTable("kh.csv", "kh.csv", None, frame)])


def _patch(monkeypatch, answers):
    monkeypatch.setattr(transfer, "_targets", lambda e, t, c: TARGETS[c])
    monkeypatch.setattr(transfer, "_is_required", lambda e, t, c: c == "ma")
    calls = []

    def ask(e, example_id, columns, raw, ids, llm, taken=frozenset()):
        calls.append((list(columns), set(taken)))
        return answers[len(calls) - 1](columns, taken)
    monkeypatch.setattr(transfer, "_ask", ask)
    return calls


def test_name_with_few_values_and_constant_group_are_refused(monkeypatch):
    monkeypatch.setattr(transfer, "_targets", lambda e, t, c: TARGETS[c])
    got = {"ma": "Ma", "ten": "Loai", "nhom": "TrangThai"}
    assert sorted(transfer._implausible(None, "kh.csv", got, _raw(), ["kh.csv"])) == ["nhom", "ten"]
    assert transfer._implausible(None, "kh.csv", {"ma": "Ma", "ten": "Ten", "nhom": "Loai"}, _raw(), ["kh.csv"]) == []


def test_refused_picks_asked_again_among_free_columns(monkeypatch):
    first = lambda cols, taken: {"ma": "Ma", "ten": "Loai", "nhom": "TrangThai"}  # noqa: E731
    second = lambda cols, taken: {"ten": "Ten", "nhom": "Loai"}  # noqa: E731
    calls = _patch(monkeypatch, [first, second])
    got = transfer._ask_required_again(None, "kh.csv", ["ma", "nhom", "ten"], _raw(), ["kh.csv"], None)
    assert got == {"ma": "Ma", "ten": "Ten", "nhom": "Loai"}
    assert sorted(calls[1][0]) == ["nhom", "ten"] and calls[1][1] == {"Ma", "TrangThai"}


def test_plausible_picks_ask_once(monkeypatch):
    calls = _patch(monkeypatch, [lambda cols, taken: {"ma": "Ma", "ten": "Ten", "nhom": "Loai"}])
    got = transfer._ask_required_again(None, "kh.csv", ["ma", "nhom", "ten"], _raw(), ["kh.csv"], None)
    assert got == {"ma": "Ma", "ten": "Ten", "nhom": "Loai"} and len(calls) == 1


def test_second_answer_still_implausible_left_unmatched(monkeypatch):
    first = lambda cols, taken: {"ma": "Ma", "ten": "Loai", "nhom": "Loai"}  # noqa: E731
    second = lambda cols, taken: {"ten": "TrangThai", "nhom": "Ten"}  # noqa: E731
    _patch(monkeypatch, [first, second])
    got = transfer._ask_required_again(None, "kh.csv", ["ma", "nhom", "ten"], _raw(), ["kh.csv"], None)
    assert got["ten"] is None and got["nhom"] == "Ten"


def test_constant_group_kept_when_the_re_ask_gives_nothing(monkeypatch):
    """N164c: a shop whose customers are all one kind has one group, not a wrong one."""
    first = lambda cols, taken: {"ma": "Ma", "ten": "Ten", "nhom": "TrangThai"}  # noqa: E731
    _patch(monkeypatch, [first, lambda cols, taken: {"nhom": None}])
    got = transfer._ask_required_again(None, "kh.csv", ["ma", "nhom", "ten"], _raw(), ["kh.csv"], None)
    assert got == {"ma": "Ma", "ten": "Ten", "nhom": "TrangThai"}


def test_few_valued_name_is_not_restored(monkeypatch):
    first = lambda cols, taken: {"ma": "Ma", "ten": "Loai", "nhom": "Loai"}  # noqa: E731
    _patch(monkeypatch, [first, lambda cols, taken: {"ten": None}])
    got = transfer._ask_required_again(None, "kh.csv", ["ma", "nhom", "ten"], _raw(), ["kh.csv"], None)
    assert got["ten"] is None and got["nhom"] == "Loai"


class _Flaky:
    def __init__(self, fail: int, answer: dict):
        self.fail, self.answer, self.calls = fail, answer, 0

    def generate_json(self, messages, schema):
        self.calls += 1
        if self.calls <= self.fail:
            raise TimeoutError("busy")
        return self.answer


def test_a_failed_call_is_retried_once_then_reported(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(transfer, "_targets", lambda e, t, c: TARGETS[c])
    monkeypatch.setattr(transfer, "_is_required", lambda e, t, c: c == "ma")
    monkeypatch.setattr(transfer, "_meaning", lambda e, t, c: "")
    e = SimpleNamespace(notes={}, samples={})
    answer = {"c1": "Ma", "c2": "Loai", "c3": "Ten"}
    llm = _Flaky(1, answer)
    got = transfer._ask_required_again(e, "kh.csv", ["ma", "nhom", "ten"], _raw(), ["kh.csv"], llm)
    assert got["ma"] == "Ma" and llm.calls == 2
    with pytest.raises(transfer.LLMUnavailable):
        transfer._ask_required_again(e, "kh.csv", ["ma", "nhom", "ten"], _raw(), ["kh.csv"], _Flaky(2, answer))


def test_map_by_transfer_notes_a_dead_llm_not_a_mismatch():
    from tests.test_mapping_transfer import EX, table
    shop = RawBusiness(root=Path("."), readme="", tables=[
        table("a.csv::x", [("B1", "Bánh", 1, 10_000)], ["Bill", "Hàng", "Slg", "Tiền"]),
        table("b.csv::x", [("B1", "01/06/2026 08:00", "Xong")], ["Bill", "Lúc", "Tình trạng"])])
    m, tried = transfer.map_by_transfer(shop, [EX], llm=_Flaky(99, {}))
    assert m is None
    text = " | ".join(tried)
    assert "LLM không trả lời" in text and "thiếu bảng đơn hoặc dòng hàng" not in text


def test_column_order_does_not_change_the_checks(monkeypatch):
    monkeypatch.setattr(transfer, "_targets", lambda e, t, c: TARGETS[c])
    raw = _raw()
    raw.tables[0].frame = raw.tables[0].frame[raw.tables[0].frame.columns[::-1]]
    got = {"ma": "Ma", "ten": "Loai", "nhom": "TrangThai"}
    assert sorted(transfer._implausible(None, "kh.csv", got, raw, ["kh.csv"])) == ["nhom", "ten"]
