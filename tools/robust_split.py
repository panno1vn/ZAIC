"""Robustness to how the split's own files are written: the private split is read by the frozen image, so a BOM, CRLF
line ends, questions in another order or with extra fields, an as_of_date with a time, or calendar columns in
another order must not move a single answer. Each variant is a copy of the split's text files (the shops' data folder
joined, not copied) replayed from a live run's logs (tools/replay_run.py); the answers are compared with the run's
own, never with gold.

    python tools/robust_split.py                       # every variant on public, from the best live run
    python tools/robust_split.py --variants crlf_bom asof_time

Development only.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

VARIANTS = ("identity", "crlf_bom", "q_shuffle_extra", "asof_time", "asof_dmy", "calendar_cols", "rulebook_renumber")


def _write(path: Path, text: str, bom: bool = False, crlf: bool = False) -> None:
    if crlf:
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8-sig" if bom else "utf-8"))


def build(split: Path, out: Path, variant: str, seed: int = 7) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    # the shops' folders: a junction (no copy, no admin rights on Windows)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(out / "data"), str((split / "data").resolve())],
                   check=True, capture_output=True)
    rulebook = (split / "rulebook.md").read_text(encoding="utf-8-sig")
    calendar = (split / "calendar.csv").read_text(encoding="utf-8-sig")
    qs = [json.loads(x) for x in (split / "questions.jsonl").read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    bom = crlf = False
    if variant == "crlf_bom":
        bom = crlf = True
    elif variant == "q_shuffle_extra":
        random.Random(seed).shuffle(qs)
        qs = [{"category": "x", **q, "extra": {"note": 1}} for q in qs]
    elif variant == "asof_time":
        qs = [{**q, "as_of_date": q["as_of_date"] + "T00:00:00"} for q in qs]
    elif variant == "asof_dmy":
        qs = [{**q, "as_of_date": "/".join(reversed(q["as_of_date"].split("-")))} for q in qs]
    elif variant == "calendar_cols":
        rows = list(csv.reader(io.StringIO(calendar)))
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows([r[::-1] for r in rows])
        calendar = buf.getvalue()
    elif variant == "rulebook_renumber":
        import re
        rulebook = re.sub(r"^(##\s*)(\d+)", lambda m: m.group(1) + str(int(m.group(2)) + 1), rulebook, flags=re.M)
    elif variant != "identity":
        raise ValueError(variant)
    _write(out / "rulebook.md", rulebook, bom, crlf)
    _write(out / "calendar.csv", calendar, bom, crlf)
    _write(out / "questions.jsonl", "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in qs), bom, crlf)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default=str(ROOT / "data" / "public_test"))
    ap.add_argument("--run", default=str(ROOT / "outputs" / "public_live_778f898"))
    ap.add_argument("--variants", nargs="*", default=list(VARIANTS))
    ap.add_argument("--out", default=str(ROOT / "outputs" / "robust_split"))
    args = ap.parse_args(argv)
    import replay_run
    split, run, out = Path(args.split), Path(args.run), Path(args.out)
    base = {json.loads(x)["id"]: x.strip() for x in (run / "submission.jsonl").read_text(encoding="utf-8").splitlines()
            if x.strip()}
    for v in args.variants:
        copy = out / "splits" / v
        build(split, copy, v)
        dest = out / "replay" / v
        replay_run.main([str(run), "--out", str(dest), "--data", str(copy), "--enrich"])
        got = {json.loads(x)["id"]: x.strip() for x in (dest / "submission.jsonl").read_text(encoding="utf-8").splitlines()
               if x.strip()}
        moved = sum(base[k] != got.get(k) for k in base)
        blank = sum(1 for k in base if json.loads(got.get(k, '{"type": "abstain"}')).get("type") == "abstain")
        print(f"== {v}: {moved} / {len(base)} đáp án đổi so với lượt chạy; {blank} câu trống", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
