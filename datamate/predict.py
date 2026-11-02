"""Entry point: answer every question of a split, write submission.jsonl and one log per question.

    python -m datamate.predict --data data/public_test --out outputs/public_run
    python -m datamate.predict --data /data --out /result                       # inside Docker

`--data` may be the split folder itself or a folder containing exactly one split.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROCESS_START = time.monotonic()  # the 6-hour limit includes model loading, so the clock starts here

from .pipeline import RunConfig, run  # noqa: E402

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "default.json"


def load_config(path: Path) -> RunConfig:
    cfg = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return RunConfig(time_budget_s=cfg.get("time_budget_hours", 5.5) * 3600,
                     reserve_s=cfg.get("reserve_seconds", 120.0),
                     write_logs=cfg.get("write_logs", True),
                     started_at=PROCESS_START)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="thư mục split (hoặc thư mục chứa đúng một split)")
    ap.add_argument("--out", required=True, help="thư mục ghi submission.jsonl và logs/")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--budget-hours", type=float, help="ghi đè ngân sách thời gian trong config")
    ap.add_argument("--no-logs", action="store_true")
    args = ap.parse_args(argv)

    config = load_config(Path(args.config))
    if args.budget_hours is not None:
        config.time_budget_s = args.budget_hours * 3600
    if args.no_logs:
        config.write_logs = False
    summary = run(Path(args.data), Path(args.out), config)
    types = ", ".join(f"{t}={n}" for t, n in summary.types.most_common())
    print(f"{summary.n_questions} câu · {types} · lỗi {summary.errors} · hết giờ {summary.timed_out} · "
          f"{summary.elapsed_s:.1f}s → {Path(args.out) / 'submission.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
