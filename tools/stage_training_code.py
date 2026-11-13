"""Stage /code/training_code/ for the Docker image (Docker guideline 2026 §8), on the build machine:

    python tools/stage_training_code.py [--out build/training_code]

No model is trained or fine-tuned. What is built from the training data is the content of assets/ (mappings, verified
plans, templates, synonyms, reference rules) and the LLM outputs it was built from; this folder holds:
- README.md (docker/training_code_README.md): what was built, the exact commands, hardware, nondeterministic steps;
- requirements.txt: the pinned dependencies (the same as inference);
- configs/: run settings; data_generation/: the build tools (tools/, datamate/eval/);
- data/train/: the training split as released (questions, answers, rulebook, calendar, shops);
- data/generated/: the LLM outputs the assets come from (plan bank of the train questions, column-matching cache,
  production-like train run cache), kept because a re-generation may differ (§8 "save prompts/responses");
- logs/: the evaluation logs of the final code on train;
- data_manifest.json: every file with its size and SHA-256, the dataset counts, the base model's public source.

Its inputs (data/, outputs/) are not in git (competition data): the build machine needs them in place.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GENERATED = {  # outputs/ file -> what it is
    "outputs/bank/llm_plans.jsonl": "plans the local LLM (Qwen3-8B Q4_K_M, greedy) wrote for every train question "
                                    "(datamate.eval.build_bank); the verified ones became assets/plans/verified_train.jsonl",
    "outputs/llm_cache_mapping.jsonl": "column-matching answers of the local LLM for the train shops (mapping by transfer)",
    "outputs/llm_cache_prod_train.jsonl": "LLM answers of the production-like train run (tools/prod_train.py)",
}
LOGS = ["outputs/eval_cached_n199.log", "outputs/prod_train_n199.log", "outputs/build_bank_v3.log"]
CODE = ["tools", "datamate/eval"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def count_lines(path: Path) -> int:
    return sum(1 for line in open(path, encoding="utf-8-sig") if line.strip())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "build" / "training_code")
    args = ap.parse_args(argv)
    out = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    copy(ROOT / "docker" / "training_code_README.md", out / "README.md")
    copy(ROOT / "requirements.txt", out / "requirements.txt")
    copy(ROOT / "configs", out / "configs")
    for c in CODE:
        copy(ROOT / c, out / "data_generation" / c)
    train = ROOT / "data" / "train"
    if not (train / "questions.jsonl").exists():
        print("thiếu data/train: chép bộ train vào data/train trước", file=sys.stderr)
        return 1
    copy(train, out / "data" / "train")
    missing = []
    for rel in GENERATED:
        src = ROOT / rel
        if src.exists():
            copy(src, out / "data" / "generated" / Path(rel).name)
        else:
            missing.append(rel)
    for rel in LOGS:
        if (ROOT / rel).exists():
            copy(ROOT / rel, out / "logs" / Path(rel).name)
    files = []
    for p in sorted(x for x in out.rglob("*") if x.is_file()):
        rel = p.relative_to(out).as_posix()
        files.append({"path": f"/code/training_code/{rel}", "bytes": p.stat().st_size, "sha256": sha256(p)})
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "training": "none: no model was trained or fine-tuned; the base model is used as released",
        "data_generation": "assets/ built from the train split with rule code and the local LLM (README.md)",
        "datasets": {
            "train": {"source": "Zalo AI Challenge 2026 DataMate, train split as released",
                      "path": "/code/training_code/data/train",
                      "questions": count_lines(train / "questions.jsonl"),
                      "answers": count_lines(train / "answers.jsonl"),
                      "businesses": sum(1 for d in (train / "data").iterdir() if d.is_dir())},
            "validation": "none held out: development measured on train itself (tools/eval_cached.py, prod_train.py); "
                          "public/private test data never used for training",
        },
        "generated": {Path(k).name: v for k, v in GENERATED.items() if k not in missing},
        "base_model": {"name": "Qwen3-8B", "file": "Qwen3-8B-Q4_K_M.gguf", "source": "https://huggingface.co/Qwen/Qwen3-8B-GGUF",
                       "license": "Apache-2.0", "in_image": "/code/models/model.gguf",
                       "sha256": "see /code/README.md (recorded at download)"},
        "files": files,
    }
    (out / "data_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    total = sum(f["bytes"] for f in files)
    print(f"{out}: {len(files)} files, {total / 1e6:.1f} MB" + (f"; THIẾU: {missing}" if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
