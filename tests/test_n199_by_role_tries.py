"""N199: the last mapping path (tables paired by role) tries the first three examples of its list, not two. Train,
every shop mapped by that path alone with its own hand mapping left out: 26 of 30 shops mapped with two tries, 29 with
three (334 more answers, none wrong), 29 with four."""
from pathlib import Path

from datamate.contracts import Mapping, RawBusiness
from datamate.mapping import from_readme, transfer

from test_mapping_transfer import EX

RAW = RawBusiness(root=Path("."), readme="", tables=[])


def _ranked(n: int):
    return [(transfer.Example(f"mau_{i}", EX.mapping, EX.tables), {}) for i in range(1, n + 1)]


def _patch(monkeypatch, passing: set[str], n: int = 5):
    """A shop no example fits by names, files or README; by role `n` examples are listed, those of `passing` pass."""
    tried_examples = []
    monkeypatch.setattr(transfer, "candidates", lambda raw, pool=None: [])
    monkeypatch.setattr(transfer, "sibling_files", lambda raw, pool=None: [])
    monkeypatch.setattr(from_readme, "map_from_readme", lambda raw: (None, "README không mô tả cột"))
    monkeypatch.setattr(transfer, "by_role", lambda raw, pool, llm: (_ranked(n), []))

    def by_meaning(e, raw, llm, pairs=None):
        tried_examples.append(e.name)
        return Mapping(notes=[e.name])

    def passes(m, raw, tried):
        ok = m.notes[0] in passing
        tried.append(f"{m.notes[0]}: {'qua' if ok else 'hỏng'}")
        return m if ok else None
    monkeypatch.setattr(transfer, "transfer_by_meaning", by_meaning)
    monkeypatch.setattr(transfer, "_passes", passes)
    return tried_examples


def test_the_third_example_by_role_is_tried(monkeypatch):
    tried_examples = _patch(monkeypatch, {"mau_3"})
    m, tried = transfer.map_by_transfer(RAW, llm=object())
    assert m is not None and m.notes == ["mau_3"] and tried_examples == ["mau_1", "mau_2", "mau_3"]
    assert tried[-3:] == ["mau_1: hỏng", "mau_2: hỏng", "mau_3: qua"]


def test_a_shop_whose_first_or_second_example_passes_is_mapped_as_before(monkeypatch):
    for first in ("mau_1", "mau_2"):
        tried_examples = _patch(monkeypatch, {first, "mau_3"})
        m, _ = transfer.map_by_transfer(RAW, llm=object())
        assert m.notes == [first] and tried_examples == [f"mau_{i}" for i in range(1, int(first[-1]) + 1)]


def test_no_fourth_example_is_tried(monkeypatch):
    tried_examples = _patch(monkeypatch, {"mau_4"})
    m, tried = transfer.map_by_transfer(RAW, llm=object())
    assert m is None and tried_examples == ["mau_1", "mau_2", "mau_3"]
    assert transfer.BY_ROLE_TRIES == 3


def test_examples_sharing_the_shops_files_are_still_tried_two_at_most(monkeypatch):
    """The path by file name (`by_meaning`) is not changed: no measure was made for it."""
    asked = []
    monkeypatch.setattr(transfer, "candidates", lambda raw, pool=None: [])
    monkeypatch.setattr(transfer, "sibling_files", lambda raw, pool=None: [e for e, _ in _ranked(4)])
    monkeypatch.setattr(from_readme, "map_from_readme", lambda raw: (None, ""))
    monkeypatch.setattr(transfer, "by_role", lambda raw, pool, llm: ([], []))
    monkeypatch.setattr(transfer, "transfer_by_meaning", lambda e, raw, llm, pairs=None: asked.append(e.name))
    assert transfer.map_by_transfer(RAW, llm=object())[0] is None and asked == ["mau_1", "mau_2"]
