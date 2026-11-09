"""The public answer key (data/grading/public_answers.jsonl) is for grading only: no inference code, asset or config may
name it, and the Docker build context must not include data/ (tools/grade_public.py)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"grading|public_answers")


def test_no_inference_code_reads_the_answer_key():
    offenders = []
    for base in (ROOT / "datamate", ROOT / "assets", ROOT / "configs", ROOT / "docker"):
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".json", ".jsonl", ".sh", ".md", ""}:
                for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if PATTERN.search(line):
                        offenders.append(f"{path.relative_to(ROOT)}:{n}")
    assert not offenders, "the answer key is named outside tools/: " + ", ".join(offenders)


def test_the_answer_key_never_ships():
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert ignore and ignore[next(i for i, x in enumerate(ignore) if x.strip() and not x.startswith("#"))] == "*"
    assert not any(re.match(r"!/?data(/|$)", x.strip()) for x in ignore)  # "!datamate/" is code, not data
    assert "data/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    # the training code staged into the image copies data/train and named outputs only
    stage = (ROOT / "tools" / "stage_training_code.py").read_text(encoding="utf-8")
    assert not PATTERN.search(stage) and 'ROOT / "data" / "train"' in stage
