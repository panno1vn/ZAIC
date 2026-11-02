"""Run the pipeline with hand-made mappings of train businesses ("oracle" mappings) and score the result.

Development only, never used at inference: it looks mappings up by business folder name, which the competition
forbids in the submitted solution. It lets the metric library [D1] and the rest of the chain be built and measured
before the automatic mapping [B] exists, and it scores the automatic mapping against the hand-made one later.

    python -m datamate.eval.oracle --business biz_101 --out outputs/oracle_biz101
    python -m datamate.eval.oracle --all --out outputs/oracle_all          # every business with a mapping file
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from datamate.contracts import Mapping
from datamate.pipeline import RunConfig, run

from .run import main as score_main

MAPPINGS = Path(__file__).resolve().parents[2] / "assets" / "mappings"


def mapping_files(split: str) -> dict[str, Path]:
    folder = MAPPINGS / split
    return {p.stem: p for p in sorted(folder.glob("*.json"))} if folder.exists() else {}


def oracle_map_fn(split: str):
    files = mapping_files(split)

    def map_fn(raw, profile, rulebook, llm=None) -> Mapping:
        path = files.get(raw.root.name)
        if path is None:
            return Mapping()
        return Mapping.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return map_fn


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="train")
    ap.add_argument("--data-root", default="data")
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--business", nargs="+", help="các cửa hàng cần chạy")
    which.add_argument("--all", action="store_true", help="mọi cửa hàng có file mapping tay")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    chosen = set(args.business or mapping_files(args.split))
    config = RunConfig(map_fn=oracle_map_fn(args.split), question_filter=lambda q: q["business_id"] in chosen)
    summary = run(Path(args.data_root) / args.split, Path(args.out), config)
    print(f"Đã chạy {summary.n_questions} câu của {len(chosen)} cửa hàng; lỗi {summary.errors}")
    return score_main(["--pred", str(Path(args.out) / "submission.jsonl"), "--split", args.split,
                       "--data-root", args.data_root, "--business", *sorted(chosen)])


if __name__ == "__main__":
    sys.exit(main())
