"""[R] Read the split's rulebook and check that the rule rows each metric function relies on are still there.

Every table row and paragraph of the rulebook becomes a rule with a stable id, e.g. "§1.don_tinh_vao_doanh_thu"
or "§6.ca_phe.size_m_size_l". Metric functions name the ids they implement; at run time each id is compared with
the reference text the functions were written against (assets/rules/reference_rules.json). A rule that disappeared
or changed beyond THRESHOLD lowers confidence for the questions that depend on it.

    python -m datamate.rules build data/train/rulebook.md data/public_test/rulebook.md   # write the reference
    python -m datamate.rules diff data/train/rulebook.md data/public_test/rulebook.md    # how rulebooks differ
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[2] / "assets" / "rules" / "reference_rules.json"
THRESHOLD = 0.95  # similarity below which a rule counts as changed; see docs/HAN_CHE_VA_CAI_THIEN.md H9
ADOPT_MIN_CHARS = 25  # N168: a row shorter than this is too weak a key to adopt under another name


@dataclass(frozen=True)
class RuleRow:
    id: str
    section: str
    name: str
    text: str


def _fold(s: str) -> str:
    t = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    return "".join(c for c in t if not unicodedata.combining(c))


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _fold(s)).strip("_")[:48] or "x"


def normalize(text: str) -> str:
    """Text as compared: markdown emphasis and code marks removed, whitespace collapsed, lower case."""
    t = unicodedata.normalize("NFC", text).replace("**", "").replace("`", "")
    return " ".join(t.lower().split())


def similarity(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    return 1.0 if a == b else difflib.SequenceMatcher(None, a, b).ratio()


# Words that flip or bound a rule's meaning. "Không trừ" → "Trừ" keeps 0.99 similarity, so a change in these
# words or in any number marks the rule as changed whatever the similarity.
MEANING_WORDS = frozenset({
    "không", "chỉ", "trừ", "cộng", "gồm", "kể", "bỏ", "mọi", "chưa", "hoặc", "ngoài", "riêng", "trước", "sau",
    "đầu", "cuối", "lớn", "nhỏ", "cao", "thấp", "tăng", "giảm", "âm", "dương", "quá", "hơn", "dưới", "trên", "từ",
})


def meaning_tokens(text: str) -> list[str]:
    words = re.findall(r"[^\W_]+", normalize(text))
    return sorted(w for w in words if w in MEANING_WORDS or w.isdigit())


def same_rule(a: str, b: str, threshold: float = 0.95) -> bool:
    return meaning_tokens(a) == meaning_tokens(b) and similarity(a, b) >= threshold


# N159: words that, added inside a list of the rule, would narrow or flip it ("…, không tính đơn sỉ")
_NARROWING = frozenset({"không", "chỉ", "trừ", "ngoài", "bỏ", "riêng", "ko"})
# N167: what an added sentence or list item may not contain either: a way to widen or condition the rule
_BOUNDING = _NARROWING | {"hoặc", "hay", "nếu", "khi"}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+|[^\w\s]", normalize(text))


def extends(old: str, new: str) -> bool:
    """N159: the new text is the accepted one with sentences or list items added, every word of it still there in
    order. Public 09/11 added a sentence to three train rows ("Đơn thuộc kỳ nào": "… Đơn trả hàng sau kỳ … vẫn bị
    loại khỏi doanh thu kỳ đặt"; "Giao nhiều đợt"; "Đến hết ngày X": ", chưa giao" in the list): clarifications the
    functions were already right under (public 991 right / 4 wrong with them), but 0.57 similar, so without a public
    version 925 of the 965 public answers that come from a function would have been blanked. The private rulebook is
    read by the frozen image, where no version can be added. A word changed or removed, a number changed, or a
    narrowing word added inside a sentence is still a changed rule.
    N167 (10/11, reviewer R002, F006): an added sentence or item with a narrowing or widening word ("Đơn huỷ không
    tính", "Riêng đơn sỉ…", "…, hoặc tổng chi từ 5 triệu"), or with a number ("Từ 01/2026 là từ 5 đơn"), changes the
    rule; and a sentence is added only where the old text ends one (not in the middle of an old sentence)."""
    a, b = _tokens(old), _tokens(new)
    if not a:
        return False
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag != "insert":
            return False
        run, before = b[j1:j2], (a[i1 - 1] if i1 > 0 else None)
        after = a[i1] if i1 < len(a) else None
        if _BOUNDING & set(run) or any(t.isdigit() for t in run):
            return False
        sentence = (run[0] in (".", ";") and after in (None, ".", ";")) or             (run[-1] in (".", ";") and before in (None, ".", ";"))
        item = run[0] == ","
        if not (sentence or item):
            return False
    return True


# T015. What a row says is its content words in order, sentence by sentence; the function words and the spelling
# variants below are the only freedom. Never put both words of an opposite pair here (có / không, đã / chưa, trong /
# ngoài, trước / sau): the second one is a fact and stays out of STOP.
STOP = frozenset("là thì mà của các những được bị sẽ đã có cũng vẫn này đó ấy như vậy tức rằng với ở tại trong theo "
                 "về cho do bởi nên ra vào đều việc cái sự".split())
# spelling and rulebook-declared equivalents, whole words, longest first
PHRASES = (("kể cả chỉ", "kể cả"), ("đơn hàng", "đơn"), ("hủy", "huỷ"), ("không bao gồm", "không gồm"),
           ("bao gồm", "gồm"), ("loại bỏ", "bỏ"), ("bị loại khỏi", "bỏ khỏi"), ("loại khỏi", "bỏ khỏi"),
           ("toàn bộ", "cả"), ("tất cả", "mọi"), ("hay", "hoặc"), ("không tính", "bỏ"), ("không kể", "bỏ"))
REWORD_MIN_TOKENS = 4  # fewer content words is too weak a key


def _plain(s: str) -> str:
    return _fold(s)


def _sentences(text: str, folded: bool = False) -> list[tuple[str, ...]]:
    t = normalize(text)
    stop, phrases = STOP, PHRASES
    if folded:
        t = _plain(t)
        stop = frozenset(_plain(w) for w in STOP)
        phrases = tuple((_plain(a), _plain(b)) for a, b in PHRASES)
    for a, b in phrases:
        t = re.sub(r"(?<!\w)" + re.escape(a) + r"(?!\w)", b, t)
    out = []
    for s in re.split(r"[.;|](?:\s|$)|\s\|\s", t + " "):
        toks = [w for w in re.findall(r"[^\W_]+", s) if w not in stop]
        if toks:
            out.append(tuple(toks))
    return out


def reworded(old: str, new: str) -> bool:
    """T015: `new` says what `old` says in other function words, punctuation or sentence order (F005 free rewording:
    "kể cả chỉ trả một phần" → "kể cả trả một phần" blanked 792 of 995 public answers). The content words of every
    sentence of `old`, in order, are all there; a sentence only `new` has passes N167's limits. A number, status,
    negation, bound, noun or verb added, removed, swapped or reordered inside a sentence is a changed rule."""
    n = normalize(new)
    folded = _plain(n) == n.replace("đ", "d")  # a row written without any accent: compare the unaccented forms
    a, b = _sentences(old, folded), _sentences(new, folded)
    if sum(len(s) for s in a) < REWORD_MIN_TOKENS:
        return False
    if [w for s in a for w in s] == [w for s in b for w in s]:
        return True
    left = Counter(b)
    for s in a:
        if not left[s]:
            return False
        left[s] -= 1
    bounding = {_plain(w) for w in _BOUNDING} if folded else _BOUNDING
    for s, k in left.items():  # sentences only the new text has
        if k and (set(s) & bounding or any(w.isdigit() for w in s)):
            return False
    return True


def accepted_version(old: str, new: str) -> bool:
    """`new` is the accepted text `old`: the same text, that text with harmless additions (N159 / N167), or the same
    content words in the same order under other function words and punctuation (T015). Replaces the character
    similarity test, which refused a reworded row (F005) and let a one-word change of a long row through ("hết hôm
    nay" → "hết hôm qua"; "bắt đầu thứ Hai" → "Chủ nhật"; "hai mã trùng tên là hai khách" → "là một khách")."""
    return normalize(old) == normalize(new) or extends(old, new) or reworded(old, new)


EDIT_MIN_SHARED = 3  # T016: tokens a new sentence shares with a known one before it counts as an edit of it
EDIT_SHARE = 0.5  # …and this share of the shorter sentence


def _contains(seq: tuple[str, ...], part: tuple[str, ...]) -> bool:
    n = len(part)
    return any(seq[i:i + n] == part for i in range(len(seq) - n + 1))


def _in_order(part: tuple[str, ...], seq: tuple[str, ...]) -> bool:
    it = iter(seq)
    return all(w in it for w in part)


def edited_known_sentence(text: str, versions: list[str]) -> bool:
    """T016: a sentence of `text` that is no sentence of any accepted version, but most of whose content words are
    those of one ("vẫn bị loại khỏi doanh thu kỳ đặt" → "vẫn tính vào doanh thu kỳ đặt"). Against the train version
    such a sentence is a harmless added one (N167), yet the public version already says it the other way: it is an
    edit of a known sentence, so the row is a changed rule. A sentence that only re-cuts a known one (a comma turned
    into a semicolon: it sits inside the known text) is not an edit; a sentence with few words in common is new."""
    if len({normalize(v) for v in versions}) < 2:
        return False  # one version: no added sentence known yet, and a real addition may echo that version's words
    n = normalize(text)
    folded = _plain(n) == n.replace("đ", "d")
    known = [_sentences(v, folded) for v in versions]
    flats = [tuple(w for sent in ks for w in sent) for ks in known]
    sentences = {sent for ks in known for sent in ks}
    for sent in _sentences(text, folded):
        if sent in sentences or any(_contains(flat, sent) for flat in flats):
            continue
        for k in sentences:
            shared = len(set(sent) & set(k))
            if shared >= EDIT_MIN_SHARED and shared >= EDIT_SHARE * min(len(sent), len(k)) and not _in_order(k, sent):
                return True  # (a known sentence with words added, "…, chưa giao", is N159's case, not an edit)
    return False


def accepted_row(text: str, versions: list[str]) -> bool:
    """`text` is one of the accepted versions: word for word, or (accepted_version) with harmless additions or other
    function words, and no added sentence that is an edit of a known one (T016)."""
    if any(normalize(v) == normalize(text) for v in versions):
        return True
    return any(extends(v, text) or reworded(v, text) for v in versions) and not edited_known_sentence(text, versions)


# a bullet's bold label, with or without its opening marks (the parser keeps "Tên**: …" of "- **Tên**: …")
_LABEL = re.compile(r"^(?:\*\*)?[^*:：]{1,80}\*\*\s*[:：]\s*|^\*\*[^*]{1,80}[:：]\*\*\s*")


def adopt_by_text(rows: dict[str, RuleRow], ref: dict[str, list[str]], wanted) -> dict[str, RuleRow]:
    """N168: {missing id: row} for the ids of `wanted` this rulebook lacks, each given the one row no known id claims
    whose text is an accepted version of the id: the row was renamed ("Đơn tính vào doanh thu" → "Đơn được tính doanh
    thu": 792 answers blank), or written as a bullet "- **Tên**: …" (65). Exactly one candidate, else nothing; a
    renamed row whose text also changed stays a changed rule (the text must still be an accepted version)."""
    free = {rid: row for rid, row in rows.items() if rid not in ref}
    out: dict[str, RuleRow] = {}
    taken: set[str] = set()
    for rid in sorted(wanted):
        versions = ref.get(rid) or []
        versions = [versions] if isinstance(versions, str) else versions
        if rid in rows or not versions:
            continue
        hits = []
        for fid, row in free.items():
            if fid in taken or len(normalize(_LABEL.sub("", row.text))) < ADOPT_MIN_CHARS:
                continue
            if any(accepted_row(t, versions) for t in (row.text, _LABEL.sub("", row.text))):
                hits.append(fid)
        if len(hits) == 1:
            row = free[hits[0]]
            plain = accepted_row(row.text, versions)
            out[rid] = RuleRow(rid, row.section, row.name, row.text if plain else _LABEL.sub("", row.text))
            taken.add(hits[0])
    return out


def _key(rid: str) -> str:
    """The id without its section number: "§1.so_don" -> "so_don", "§6.ca_phe.size_m" -> "ca_phe.size_m"."""
    return rid.split(".", 1)[1] if rid.startswith("§") and "." in rid else rid


def canonical_rows(rows: dict[str, RuleRow], known) -> dict[str, RuleRow]:
    """N159: rows under the ids the functions know, when the rulebook numbers its sections otherwise. An id the
    reference does not have takes the known id with the same name (sub-section and term), when exactly one such id
    is missing from this rulebook. Public sections renumbered by one: 74 -> 1 of the 77 rules the functions cite were
    found before this."""
    known = set(known)
    by_key: dict[str, list[str]] = {}
    for rid in known:
        by_key.setdefault(_key(rid), []).append(rid)
    out: dict[str, RuleRow] = {}
    for rid, row in rows.items():
        cands = [] if rid in known else [k for k in by_key.get(_key(rid), []) if k not in rows and k not in out]
        new = cands[0] if len(cands) == 1 else rid
        out[new] = RuleRow(new, row.section, row.name, row.text)
    return out


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator(line: str) -> bool:
    return line.strip().startswith("|") and all(set(c) <= set("-: ") for c in _cells(line))


def parse_rulebook(text: str) -> dict[str, RuleRow]:
    """Rule id -> row, for every table row (header rows excluded) and every paragraph or bullet."""
    rows: dict[str, RuleRow] = {}
    section, sub = "0", ""
    lines = text.splitlines()

    def add(name: str, body: str) -> None:
        base = f"§{section}" + (f".{sub}" if sub else "") + f".{_slug(name)}"
        rid, k = base, 2
        while rid in rows:
            rid, k = f"{base}_{k}", k + 1
        rows[rid] = RuleRow(rid, section + (f".{sub}" if sub else ""), name, body)

    for i, line in enumerate(lines):
        s = line.strip()
        if m := re.match(r"^##\s+(\d+)\.", s):
            section, sub = m.group(1), ""
        elif m := re.match(r"^###\s+(.+)$", s):
            sub = _slug(m.group(1))
        elif s.startswith("#") or not s:
            continue
        elif s.startswith("|"):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if _is_separator(s) or _is_separator(nxt):  # separator, or header row right above it
                continue
            cells = _cells(s)
            add(cells[0].replace("**", ""), " | ".join(cells[1:]))
        else:  # paragraph or bullet: named by its first words, so inserting a paragraph does not shift ids
            body = s.lstrip("-* ").strip()
            add("p_" + " ".join(body.replace("**", "").split()[:6]), body)
    return rows


def load_reference(path: Path = REFERENCE) -> dict[str, list[str]]:
    """rule id -> every accepted version of its text (the metric functions are correct under each of them)."""
    if not path.exists():
        return {}
    return {rid: [v["text"] for v in entry["versions"]]
            for rid, entry in json.loads(path.read_text(encoding="utf-8")).items()}


def check_rules(rulebook: str, rule_ids: tuple[str, ...], reference: dict[str, str | list[str]] | None = None,
                threshold: float = THRESHOLD) -> dict[str, bool]:
    """rule id -> True when the rule exists in this rulebook and says what one accepted version says (T015: the
    `threshold` argument is kept for callers and no longer used)."""
    ref = load_reference() if reference is None else reference
    current = canonical_rows(parse_rulebook(rulebook), set(ref) | set(rule_ids))
    current = {**current, **adopt_by_text(current, {k: ([v] if isinstance(v, str) else v) for k, v in ref.items()},
                                          rule_ids)}
    out = {}
    for rid in rule_ids:
        row, versions = current.get(rid), ref.get(rid)
        if isinstance(versions, str):
            versions = [versions]
        out[rid] = row is not None and bool(versions) and accepted_row(row.text, versions)
    return out


@lru_cache(maxsize=1)
def train_rule_ids(path: Path = REFERENCE) -> frozenset[str]:
    """Rules with a train version in the reference: the ones the metric functions were checked against."""
    if not path.exists():
        return frozenset()
    return frozenset(rid for rid, entry in json.loads(path.read_text(encoding="utf-8")).items()
                     if any(v.get("source") == "train" for v in entry["versions"]))


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _fold(text))


@lru_cache(maxsize=4)
def new_terms(rulebook: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """(rule id, words naming it in a question) of the rows of this rulebook with no train version: terms such as
    "Khách trung thành nhất" (most days with a purchase) that no function was checked against. A term is named by
    the words after its head noun ("trung thanh nhat"), of the last name when a row names several ("Nhân viên, thợ
    chăm chỉ nhất"); one word left is too common to tell ("Bảo hành")."""
    known, out = train_rule_ids(), []
    rows = canonical_rows(parse_rulebook(rulebook), load_reference())
    adopted = {(a.section, a.name) for a in adopt_by_text(rows, load_reference(), known).values()}
    for rid, row in rows.items():
        if rid in known or row.name.startswith("p_") or (row.section, row.name) in adopted:  # N168: renamed, not new
            continue
        words = _words(row.name.split(",")[-1])[1:]
        if len(words) >= 2:
            out.append((rid, tuple(words)))
    return tuple(out)


_OTHER_CRITERION = frozenset({"tien", "dthu", "doanh"})


def _says(question: list[str], words: tuple[str, ...], gap: int = 2) -> bool:
    """The words come in order in the question, at most `gap` other words between two of them ("khách nào trung
    thành nhất")."""
    for start in (i for i, w in enumerate(question) if w == words[0]):
        at, ok = start, True
        for w in words[1:]:
            nxt = next((j for j in range(at + 1, min(at + 2 + gap, len(question))) if question[j] == w), None)
            # N156: money between the words is another criterion: which worker brought in the most money (public) is the most
            # money, not the term "Thợ làm nhiều nhất" (most tickets)
            if nxt is not None and any(question[j] in _OTHER_CRITERION for j in range(at + 1, nxt)):
                nxt = None
            if nxt is None:
                ok = False
                break
            at = nxt
        if ok:
            return True
    return False


def unverified_terms(question: str, rulebook: str, cited: list[str] | tuple[str, ...],
                     named: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Rule ids of terms the question uses that this rulebook defines, no train version of which exists, and that
    the answering function does not implement (does not cite). Public 04/11: such questions ("khách trung thành
    nhất", "mặt hàng được ưa chuộng nhất"…) were read as the nearest train metric (most orders, most quantity).
    N101: words that are a data value the plan names (`named`: "máy cũ", a category of a phone shop) are that value,
    not the term ("Thu máy cũ"): "máy cũ 8/25 bán được mấy chiếc" (public run11, 3 questions refused)."""
    q = _words(question)
    values = [" " + " ".join(_words(v)) + " " for v in named]
    return [rid for rid, words in new_terms(rulebook) if rid not in cited and _says(q, words)
            and not any(" " + " ".join(words) + " " in v for v in values)]


def diff_rulebooks(old: str, new: str) -> dict[str, list]:
    a, b = parse_rulebook(old), parse_rulebook(new)
    changed = [(rid, round(similarity(a[rid].text, b[rid].text), 3)) for rid in a.keys() & b.keys()
               if normalize(a[rid].text) != normalize(b[rid].text)]
    return {"same": sorted(rid for rid in a.keys() & b.keys() if normalize(a[rid].text) == normalize(b[rid].text)),
            "changed": sorted(changed, key=lambda x: x[1]),
            "added": sorted(b.keys() - a.keys()), "removed": sorted(a.keys() - b.keys())}
