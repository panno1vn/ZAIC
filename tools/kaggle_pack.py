"""The two files to upload as one private Kaggle Dataset for K1 (plan §11): the code (datamate, assets, configs,
tools, requirements, the laptop's column-matching cache and 8B plans) and the train data. Nothing of the test sets.

    python tools/kaggle_pack.py        # -> outputs/kaggle/zaic_code.zip, outputs/kaggle/zaic_train.zip
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "outputs" / "kaggle"
CODE = ["datamate", "assets", "configs", "tools", "requirements.txt"]
CODE_OUTPUTS = ["outputs/llm_cache_mapping.jsonl", "outputs/bank/llm_plans.jsonl"]


def _add(z: zipfile.ZipFile, path: Path, base: Path) -> int:
    n = 0
    for p in [path] if path.is_file() else sorted(path.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            z.write(p, p.relative_to(base).as_posix())
            n += 1
    return n


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    DEST.mkdir(parents=True, exist_ok=True)
    code = DEST / "zaic_code.zip"
    with zipfile.ZipFile(code, "w", zipfile.ZIP_DEFLATED) as z:
        n = sum(_add(z, ROOT / c, ROOT) for c in CODE + CODE_OUTPUTS if (ROOT / c).exists())
    train = DEST / "zaic_train.zip"
    with zipfile.ZipFile(train, "w", zipfile.ZIP_DEFLATED) as z:
        m = _add(z, ROOT / "data" / "train", ROOT / "data")
    for f, k in ((code, n), (train, m)):
        print(f"{f.relative_to(ROOT)}: {k} file, {f.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
