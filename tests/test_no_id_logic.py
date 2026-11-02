"""Inference code must not branch on business or question ids (DataMate technical requirement 4)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ID_PATTERN = re.compile(r"\b(?:biz|dev)_\d{3}\b|\bq_[0-9a-f]{12}\b")
SCANNED = [ROOT / "datamate", ROOT / "configs"]
EXEMPT_DIRS = {ROOT / "datamate" / "eval"}  # dev-time evaluation may name train businesses
SUFFIXES = {".py", ".json", ".yaml", ".yml", ".txt", ".md"}


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
