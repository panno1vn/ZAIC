"""CLI for [R]: build the reference rule texts, or show how two rulebooks differ (see datamate/rules/__init__.py)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import REFERENCE, diff_rulebooks, normalize, parse_rulebook


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m datamate.rules")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="ghi các phiên bản luật được chấp nhận (mỗi rulebook góp một phiên bản)")
    b.add_argument("rulebooks", nargs="+")
    b.add_argument("--out", default=str(REFERENCE))
    d = sub.add_parser("diff", help="so hai rulebook")
    d.add_argument("old")
    d.add_argument("new")
    args = ap.parse_args(argv)

    if args.cmd == "build":
        ref: dict[str, dict] = {}
        for path in args.rulebooks:
            for rid, row in parse_rulebook(Path(path).read_text(encoding="utf-8")).items():
                versions = ref.setdefault(rid, {"versions": []})["versions"]
                if all(normalize(v["text"]) != normalize(row.text) for v in versions):
                    versions.append({"text": row.text, "source": Path(path).parent.name})
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(ref, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        n_versions = sum(len(v["versions"]) for v in ref.values())
        print(f"{len(ref)} luật, {n_versions} phiên bản -> {out}")
    else:
        r = diff_rulebooks(Path(args.old).read_text(encoding="utf-8"), Path(args.new).read_text(encoding="utf-8"))
        print(f"giống: {len(r['same'])} · đổi: {len(r['changed'])} · thêm: {len(r['added'])} · bỏ: {len(r['removed'])}")
        for rid, ratio in r["changed"]:
            print(f"  đổi  {ratio:.3f}  {rid}")
        for rid in r["added"]:
            print(f"  thêm        {rid}")
        for rid in r["removed"]:
            print(f"  bỏ          {rid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
