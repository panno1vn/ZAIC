"""N192: a conversion sheet holding both the factor ("Bằng": 6) and the price of the unit (210000): the LLM took the
price for the factor in five of six live runs of a public coffee shop, 1 hộp counted as 210000 cái. A factor must be a
count of base units (a number above 0, at most FACTOR_MAX); a refused pick is asked once more among the other
columns, never offered again nor given back."""
from pathlib import Path

import pandas as pd

from datamate.contracts.raw import RawBusiness, RawTable
from datamate.mapping import transfer

TARGETS = {"ma": {"product_key"}, "dv": {"unit"}, "hs": {"factor"}}


def _raw(prices=(210000, 282000)) -> RawBusiness:
    frame = pd.DataFrame({"Giá bán theo đơn vị quy đổi": list(prices), "Mã vạch": ["SP0049", "SP0050"],
                          "Bằng": [6, 6], "Quy cách": ["hộp", "hộp"]})
    return RawBusiness(root=Path("."), readme="", tables=[RawTable("qd.xlsx::QD", "qd.xlsx", "QD", frame)])


def _patch(monkeypatch, answers):
    monkeypatch.setattr(transfer, "_targets", lambda e, t, c: TARGETS[c])
    monkeypatch.setattr(transfer, "_is_required", lambda e, t, c: True)
    calls = []

    def ask(e, example_id, columns, raw, ids, llm, taken=frozenset()):
        calls.append((list(columns), set(taken)))
        return answers[len(calls) - 1](columns, taken)
    monkeypatch.setattr(transfer, "_ask", ask)
    return calls


def test_unit_counts():
    frames = [_raw().tables[0].frame]
    assert transfer._unit_counts(frames, "Bằng")
    assert not transfer._unit_counts(frames, "Giá bán theo đơn vị quy đổi")  # money
    assert not transfer._unit_counts(frames, "Quy cách")  # words
    # train: 1 tấn = 1000 kg is a factor; written as text it still reads
    assert transfer._unit_counts([pd.DataFrame({"x": [10, 1000, "24", "4"]})], "x")
    assert not transfer._unit_counts([pd.DataFrame({"x": [0, 0, 6]})], "x")


def test_price_taken_for_factor_is_refused(monkeypatch):
    monkeypatch.setattr(transfer, "_targets", lambda e, t, c: TARGETS[c])
    raw = _raw()
    got = {"ma": "Mã vạch", "dv": "Quy cách", "hs": "Giá bán theo đơn vị quy đổi"}
    assert transfer._implausible(None, "qd.xlsx::QD", got, raw, ["qd.xlsx::QD"]) == ["hs"]
    assert transfer._implausible(None, "qd.xlsx::QD", {**got, "hs": "Bằng"}, raw, ["qd.xlsx::QD"]) == []


def test_refused_factor_asked_again_without_the_price(monkeypatch):
    first = lambda cols, taken: {"ma": "Mã vạch", "dv": "Quy cách", "hs": "Giá bán theo đơn vị quy đổi"}  # noqa: E731
    calls = _patch(monkeypatch, [first, lambda cols, taken: {"hs": "Bằng"}])
    got = transfer._ask_required_again(None, "qd.xlsx::QD", ["dv", "hs", "ma"], _raw(), ["qd.xlsx::QD"], None)
    assert got == {"ma": "Mã vạch", "dv": "Quy cách", "hs": "Bằng"}
    assert calls[1][0] == ["hs"] and "Giá bán theo đơn vị quy đổi" in calls[1][1]


PRICE = lambda cols, taken: {"ma": "Mã vạch", "dv": "Quy cách", "hs": "Giá bán theo đơn vị quy đổi"}  # noqa: E731
NOTHING = lambda cols, taken: {"hs": None}  # noqa: E731


def _with(raw: RawBusiness, **cols) -> RawBusiness:
    raw.tables[0].frame = raw.tables[0].frame.assign(**cols)
    return raw


def test_one_valued_price_not_given_back(monkeypatch):
    """Both units at one price: the price column has one value, like the constant group N164c gives back; a factor
    refused is not given back (and with no other column fit to be a factor, left unmatched: the side table is then
    dropped, its questions abstain)."""
    _patch(monkeypatch, [PRICE, NOTHING])
    raw = _raw((210000, 210000))
    raw.tables[0].frame = raw.tables[0].frame.drop(columns=["Bằng"])
    got = transfer._ask_required_again(None, "qd.xlsx::QD", ["dv", "hs", "ma"], raw, ["qd.xlsx::QD"], None)
    assert got["hs"] is None and got["ma"] == "Mã vạch"


def test_the_one_free_column_fit_for_a_factor_is_taken(monkeypatch):
    """Public coffee shop 12/11: the second answer left the factor unmatched, "Bằng" the only column left."""
    _patch(monkeypatch, [PRICE, NOTHING])
    got = transfer._ask_required_again(None, "qd.xlsx::QD", ["dv", "hs", "ma"], _raw(), ["qd.xlsx::QD"], None)
    assert got == {"ma": "Mã vạch", "dv": "Quy cách", "hs": "Bằng"}


def test_row_numbers_are_not_a_factor(monkeypatch):
    _patch(monkeypatch, [PRICE, NOTHING])
    raw = _with(_raw(), STT=[1, 2])
    got = transfer._ask_required_again(None, "qd.xlsx::QD", ["dv", "hs", "ma"], raw, ["qd.xlsx::QD"], None)
    assert got["hs"] == "Bằng"


def test_two_columns_fit_no_guess(monkeypatch):
    _patch(monkeypatch, [PRICE, NOTHING])
    raw = _with(_raw(), **{"Số lẻ": [10, 12]})
    got = transfer._ask_required_again(None, "qd.xlsx::QD", ["dv", "hs", "ma"], raw, ["qd.xlsx::QD"], None)
    assert got["hs"] is None
