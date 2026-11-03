"""Print what a mapping author needs about one business: README, then each raw table with its columns, guessed types,
ranges and sample values. Train businesses only (hand mappings are not allowed for test data, rule §4.2).

    python tools/show_business.py data/train/data/biz_103 [--readme-lines 80]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datamate.loader import load_business, profile_business  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--readme-lines", type=int, default=80)
    ap.add_argument("--samples", type=int, default=4)
    args = ap.parse_args()
    raw = load_business(Path(args.folder))
    prof = profile_business(raw, n_samples=args.samples)
    print("\n".join(raw.readme.splitlines()[:args.readme_lines]))
    print("\nCảnh báo:", raw.warnings or "không")
    for t, p in zip(raw.tables, prof.tables):
        print(f"\n## {t.table_id}  ({p.n_rows} dòng, header {t.header_rows} dòng, năm sheet {t.year_hint})")
        for n in t.notes:
            print(f"   ghi chú: {n[:200]}")
        for c in p.columns:
            rng = f" [{c.min} .. {c.max}]" if c.min is not None else ""
            print(f"   - {c.name}: {c.dtype}{rng}, {c.non_null} ô, {c.distinct} giá trị; ví dụ {c.samples}")


if __name__ == "__main__":
    main()
