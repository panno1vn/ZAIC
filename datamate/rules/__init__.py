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
from dataclasses import dataclass
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[2] / "assets" / "rules" / "reference_rules.json"
THRESHOLD = 0.95  # similarity below which a rule counts as changed; see docs/HAN_CHE_VA_CAI_THIEN.md H9


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
    """rule id -> True when the rule exists in this rulebook and matches one accepted version closely enough."""
    current = parse_rulebook(rulebook)
    ref = load_reference() if reference is None else reference
    out = {}
    for rid in rule_ids:
        row, versions = current.get(rid), ref.get(rid)
        if isinstance(versions, str):
            versions = [versions]
        out[rid] = row is not None and bool(versions) and any(same_rule(row.text, v, threshold) for v in versions)
    return out


def diff_rulebooks(old: str, new: str) -> dict[str, list]:
    a, b = parse_rulebook(old), parse_rulebook(new)
    changed = [(rid, round(similarity(a[rid].text, b[rid].text), 3)) for rid in a.keys() & b.keys()
               if normalize(a[rid].text) != normalize(b[rid].text)]
    return {"same": sorted(rid for rid in a.keys() & b.keys() if normalize(a[rid].text) == normalize(b[rid].text)),
            "changed": sorted(changed, key=lambda x: x[1]),
            "added": sorted(b.keys() - a.keys()), "removed": sorted(a.keys() - b.keys())}
