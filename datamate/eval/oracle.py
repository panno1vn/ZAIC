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
from datamate.mapping import transfer
from datamate.pipeline import RunConfig, run
from datamate.predict import DEFAULT_CONFIG, connect_llm, load_config

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


def auto_map_fn(raw, profile, rulebook, llm=None) -> Mapping:
    """The automatic mapping (T5) as for a shop never seen: the shop's own hand mapping is not an example."""
    mapping, tried = transfer.map_by_transfer(raw, transfer.examples(leave_out=raw.root.name), llm=llm)
    return mapping if mapping is not None else transfer.failed(tried)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="train")
    ap.add_argument("--data-root", default="data")
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--business", nargs="+", help="các cửa hàng cần chạy")
    which.add_argument("--all", action="store_true", help="mọi cửa hàng có file mapping tay")
    ap.add_argument("--out", required=True)
    ap.add_argument("--llm-url", help="llama-server đọc câu hỏi (mặc định: chỉ baseline)")
    ap.add_argument("--llm-cache", help="file jsonl giữ câu trả lời của LLM để chạy lại nhanh, ví dụ outputs/llm_cache.jsonl")
    ap.add_argument("--twin-threshold", type=float,
                    help="ngưỡng cổng câu anh em; số âm là tắt cổng (mặc định: theo configs/default.json)")
    ap.add_argument("--see-own-examples", action="store_true",
                    help="cho LLM thấy ví dụ của chính cửa hàng (mặc định: không, để số đo giống cửa hàng lạ)")
    ap.add_argument("--auto-mapping", action="store_true",
                    help="mapping tự động (T5) thay mapping tay, bỏ mapping tay của chính cửa hàng khỏi ví dụ; "
                         "với --all là mọi cửa hàng train")
    args = ap.parse_args(argv)

    llm = connect_llm(args.llm_url, cache=args.llm_cache)
    if args.llm_url and llm is None:
        return 1
    threshold = args.twin_threshold if args.twin_threshold is not None else load_config(DEFAULT_CONFIG).twin_threshold
    if threshold is not None and threshold < 0:  # --twin-threshold -1: gate off
        threshold = None
    split_dir = Path(args.data_root) / args.split
    business = {q["id"]: q["business_id"] for q in map(json.loads, (split_dir / "questions.jsonl").read_text(
        encoding="utf-8").splitlines()) if q}
    everyone = set(business.values()) if args.auto_mapping else set(mapping_files(args.split))
    chosen = set(args.business or everyone)
    own: dict[str, frozenset[str]] = {}
    for qid, b in business.items():  # every train question of the business, whether in the bank or not
        own[b] = own.get(b, frozenset()) | {qid}
    config = RunConfig(map_fn=auto_map_fn if args.auto_mapping else oracle_map_fn(args.split),
                       question_filter=lambda q: q["business_id"] in chosen,
                       twin_threshold=threshold,
                       exclude_examples=None if args.see_own_examples else (lambda q: own[q["business_id"]]))
    print(f"cổng câu anh em: {threshold if threshold is not None else 'tắt'}; "
          f"ví dụ của chính cửa hàng: {'có' if args.see_own_examples else 'không'}")
    summary = run(Path(args.data_root) / args.split, Path(args.out), config, llm)
    print(f"Đã chạy {summary.n_questions} câu của {len(chosen)} cửa hàng; lỗi {summary.errors}")
    return score_main(["--pred", str(Path(args.out) / "submission.jsonl"), "--split", args.split,
                       "--data-root", args.data_root, "--business", *sorted(chosen)])


if __name__ == "__main__":
    sys.exit(main())
