"""Inventory which kinds of information each business's files carry, from file/sheet names and header cells."""
import collections
import csv
import json
import os
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import openpyxl

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(sys.argv[1])


def fold(s):
    t = unicodedata.normalize("NFD", str(s).lower()).replace("đ", "d")
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).replace("_", " ").split())


CONCEPTS = {
    "mã đơn": r"ma (?:don|hoa don|hd|bill|phieu)|so phieu|\bhd\b|\bstt\b|order|so hoa don|ma giao dich",
    "ngày/giờ": r"ngay|thoi gian|\bgio\b|time|date|tao luc",
    "trạng thái": r"trang thai|status|ket qua|tinh trang|xu ly",
    "ghi chú": r"ghi chu|dien giai|note",
    "khách (tên)": r"khach|ben mua|doi tac|customer|ten kh|nguoi mua",
    "mã khách": r"ma (?:kh|khach)",
    "nhóm khách": r"nhom khach|loai khach|hang khach|loai hinh kh",
    "kênh bán": r"kenh|loai ban|nguon don|ban qua",
    "hình thức TT": r"thanh toan|hinh thuc|phuong thuc|httt|tra bang",
    "nhân viên/thợ": r"nhan vien|thu ngan|nguoi ban|\btho\b|nv ban",
    "mặt hàng": r"ten (?:hang|sp|mon)|san pham|mat hang|\bmon\b|hang hoa|noi dung|hang ban|\bhang\b|ten goi",
    "mã hàng": r"ma (?:hang|sp|hh)|sku|ma vach",
    "nhóm hàng": r"nhom hang|danh muc|loai hang|nhom sp|nhom mon|\bnhom\b",
    "số lượng": r"so luong|\bsl\b|so lg|qty",
    "đơn vị": r"don vi|dvt|\bunit\b|dv tinh",
    "quy đổi đơn vị": r"quy doi|he so|dv le|so luong le|sl le|don vi co so",
    "đơn giá": r"don gia|gia ban|gia le|gia don vi",
    "thành tiền": r"thanh tien|tri gia|amount|tong tien|tien hang|tong don",
    "giảm giá": r"giam gia|chiet khau|voucher|khuyen mai|\bbot\b",
    "phí giao": r"phi (?:giao|ship|van chuyen)",
    "VAT": r"\bvat\b|thue",
    "giá vốn": r"gia von",
    "đã trả / còn nợ": r"da tra|con no|du no|khach tra|so tien thu|da thanh toan|con phai thu|\bno\b",
    "trả hàng": r"tra hang|hoan tra|phieu tra",
    "nhập hàng": r"nhap|nha cung cap|\bncc\b",
    "tồn kho": r"\bton\b",
    "lịch sử giá": r"gia moi|gia cu|ngay ap dung|lich su gia|bang gia",
    "lô / hạn dùng": r"\blo\b|ma lo|han (?:dung|su dung)",
    "hoạt chất / kê đơn": r"hoat chat|ke don|thanh phan|ban theo don",
    "chi phí": r"chi phi",
    "giao nhiều đợt": r"dot giao|ngay giao|giao hang",
    "báo cáo ca": r"\bca\b|bao cao ca",
    "sửa xe (xe, việc)": r"lam gi|\bxe\b|bien so",
    "trả góp": r"\bgop\b|so ky|tra truoc",
    "thu máy cũ / IMEI": r"thu may|may cu|imei",
    "bảo hành": r"bao hanh",
    "thành viên / điểm": r"dang ky|thanh vien|\bdiem\b",
    "ghi tắt": r"ghi tat",
}


def header_cells_xlsx(path):
    out, info = [], {"sheets": 0, "two_row_header": 0}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    info["sheets"] = len(wb.sheetnames)
    out.extend(wb.sheetnames)
    for name in wb.sheetnames[:3]:
        rows = [r for _, r in zip(range(4), wb[name].iter_rows(values_only=True))]
        texts = [[c for c in (r or []) if isinstance(c, str) and c.strip()] for r in rows]
        best = max(range(len(texts)), key=lambda i: len(texts[i])) if texts else 0
        if best > 0 and texts[best - 1] and len(texts[best - 1]) < len(texts[best]):
            info["two_row_header"] += 1
        for t in texts[: best + 1]:
            out.extend(t)
    wb.close()
    return out, info


def scan_business(d):
    cells, files, info = [], [], collections.Counter()
    for f in sorted(d.iterdir()):
        if f.name == "README.md":
            continue
        files.append(f.name)
        cells.append(f.stem)
        if f.suffix == ".csv":
            info["csv"] += 1
            with open(f, encoding="utf-8-sig", newline="") as fh:
                cells.extend(next(csv.reader(fh), []))
        elif f.suffix == ".xlsx":
            info["xlsx"] += 1
            c, i = header_cells_xlsx(f)
            cells.extend(c)
            info["sheets"] += i["sheets"]
            info["two_row_header"] += i["two_row_header"]
        elif f.suffix == ".sqlite":
            info["sqlite"] += 1
            con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
            for (t,) in con.execute("select name from sqlite_master where type='table'"):
                cells.append(t)
                cells.extend(c[1] for c in con.execute(f'pragma table_info("{t}")'))
            con.close()
    text = " | ".join(fold(c) for c in cells)
    found = [k for k, p in CONCEPTS.items() if re.search(p, text)]
    return files, info, found


def main():
    rows = {}
    for split in ("train", "public_test"):
        for d in sorted((ROOT / split / "data").iterdir()):
            files, info, found = scan_business(d)
            rows[d.name] = {"split": split, "files": files, "info": dict(info), "found": found}
    counts = collections.Counter(k for r in rows.values() for k in r["found"])
    print("concept presence (of", len(rows), "businesses):")
    for k in CONCEPTS:
        tr = sum(k in r["found"] for r in rows.values() if r["split"] == "train")
        pu = sum(k in r["found"] for r in rows.values() if r["split"] == "public_test")
        print(f"  {k:22s} train {tr:2d}/30   public {pu:2d}/14")
    print("\nfile kinds:")
    kinds = collections.Counter()
    for b, r in rows.items():
        i = r["info"]
        kind = "sqlite" if i.get("sqlite") else ("csv" if i.get("csv") and not i.get("xlsx") else ("xlsx+csv" if i.get("csv") else "xlsx"))
        kinds[(r["split"], kind)] += 1
    print(" ", dict(kinds))
    print("businesses with multi-sheet xlsx:", sum(1 for r in rows.values() if r["info"].get("sheets", 0) > r["info"].get("xlsx", 0)))
    print("businesses with 2-row headers:", [b for b, r in rows.items() if r["info"].get("two_row_header")])
    print("files per business: min", min(len(r["files"]) for r in rows.values()), "max", max(len(r["files"]) for r in rows.values()))
    json.dump(rows, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)


main()
