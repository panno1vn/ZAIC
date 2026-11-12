"""Inference code must not branch on business or question ids (DataMate technical requirement 4)."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ID_PATTERN = re.compile(r"\b(?:biz|dev)_\d{3}\b|\bq_[0-9a-f]{12}\b")
SCANNED = [ROOT / "datamate", ROOT / "configs"]
EXEMPT_DIRS = {ROOT / "datamate" / "eval"}  # dev-time evaluation may name train businesses
SUFFIXES = {".py", ".json", ".yaml", ".yml"}  # code and config; docs (README) may name train businesses as examples


def test_no_ids_in_inference_code():
    offenders = []
    for base in SCANNED:
        for path in base.rglob("*"):
            if path.suffix not in SUFFIXES or any(d in path.parents for d in EXEMPT_DIRS):
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if ID_PATTERN.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not offenders, "Có id cửa hàng/câu hỏi trong code inference:\n" + "\n".join(offenders)


# H10 (12/11): ids composed at run time escape the plain search above: an id prefix as a string ("dev_", startswith),
# an f-string building one (f"biz_{n:03}"), a comparison of a business / question id or a shop folder's name with
# constants
_PREFIX = re.compile(r"^(?:biz|dev)_|^q_[0-9a-f]*$")
_ID_SIDE = re.compile(r"business_id|\bbiz\b|\[.id.\]|\.root\.name")


def _composed_ids(source: str) -> list[str]:
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _PREFIX.search(node.value):
            out.append(f"{node.lineno}: chuỗi {node.value[:40]!r}")
        elif isinstance(node, ast.JoinedStr):
            text = "".join(v.value if isinstance(v, ast.Constant) else "{" for v in node.values)
            if re.search(r"(?:biz|dev)_\{|^q_\{", text):
                out.append(f"{node.lineno}: f-string {text[:40]!r}")
        elif isinstance(node, ast.Compare):
            sides = [node.left, *node.comparators]
            if any(_ID_SIDE.search(ast.unparse(s)) for s in sides) and \
                    any(isinstance(s, (ast.Constant, ast.Set, ast.List, ast.Tuple)) for s in sides):
                out.append(f"{node.lineno}: so sánh {ast.unparse(node)[:60]!r}")
    return out


def test_composed_ids_are_caught():
    bad = '''
if q["business_id"] == "x": pass
if raw.root.name in {"a", "b"}: pass
name = f"biz_{n:03}"
if shop.startswith("dev_"): pass
'''
    assert {h.split(":")[0] for h in _composed_ids(bad)} == {"2", "3", "4", "5"}
    assert _composed_ids('x = q["id"]\nlog = f"{q[\'id\']}.json"\n') == []


def test_no_composed_ids_in_inference_code():
    offenders = []
    for path in (ROOT / "datamate").rglob("*.py"):
        if any(d in path.parents for d in EXEMPT_DIRS):
            continue
        offenders += [f"{path.relative_to(ROOT)}:{h}" for h in _composed_ids(path.read_text(encoding="utf-8"))]
    assert not offenders, "Code inference ghép / so id cửa hàng hay câu hỏi:\n" + "\n".join(offenders)
