"""Write data/synth3_dev/: one hand-made shop of a business type in neither train, public nor the other synth splits
(dried seafood), written eight ways (14/11). The orders and the questions are the same in every shop; one thing
differs at a time, so a shop that abstains says which way of writing the files the system does not read.

    python tools/synth_shops3.py                   # writes the split (gitignored)
    python -m datamate.predict --data data/synth3_dev --out outputs/synth3/dev --llm-url http://127.0.0.1:8091
    python -m datamate.eval.run --split synth3_dev --pred outputs/synth3/dev/submission.jsonl

Layout of the sales sheet (status words "Hoàn thành / Đã huỷ / Trả hàng"):
- syn_031 flat: order cells on every line, no title rows, no total row
- syn_032 three title rows above the header      - syn_033 order cells (date, customer, payment, status) on the
- syn_034 a total row under the data               order's first line only
- syn_035 all three
Order status words (flat layout):
- syn_041 "Đã bán / Huỷ / Trả hàng"      - syn_042 "Hoàn tất / Đã huỷ / Trả hàng"
- syn_043 "Đã thanh toán / Đã huỷ / Khách trả hàng"

Measured 14/11, right / wrong / blank of 30 questions a shop:
                   syn_031..035      syn_041      syn_042      syn_043
    before N201    29 / 0 / 1 each   0 / 0 / 30   0 / 0 / 30   0 / 0 / 30   (the word of the completed order is not
    with N201      (no unread word)  29 / 0 / 1   28 / 0 / 2   28 / 0 / 2    read: every candidate fails the status
                                                                             checks)

Like tools/synth_shops2.py, §6 follows the organizers' style (the business type adds its own measures and leaves the
general revenue of §1 alone); the questions are its train templates, without the two of the business type.
Deterministic (fixed seed). Development only: no organizer data is read except train's calendar and rulebook.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import synth_shops as S  # noqa: E402
import synth_shops2 as G  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ITEMS = [
    ("K001", "Tôm khô loại 1", "Tôm - mực", "kg", 650000, 8, None),
    ("K002", "Tôm khô loại 2", "Tôm - mực", "kg", 480000, 10, None),
    ("K003", "Mực khô câu", "Tôm - mực", "kg", 900000, 5, None),
    ("K004", "Mực một nắng", "Tôm - mực", "kg", 420000, 6, None),
    ("C001", "Cá cơm khô", "Cá khô", "kg", 180000, 12, None),
    ("C002", "Cá chỉ vàng", "Cá khô", "kg", 210000, 12, None),
    ("C003", "Khô cá lóc", "Cá khô", "kg", 320000, 8, None),
    ("C004", "Khô cá dứa", "Cá khô", "kg", 450000, 5, None),
    ("C005", "Cá đù một nắng", "Cá khô", "kg", 190000, 7, None),
    ("R001", "Ruốc khô", "Ruốc - tép", "kg", 150000, 6, None),
    ("R002", "Tép khô", "Ruốc - tép", "kg", 260000, 5, None),
    ("M001", "Nước mắm cá cơm 500ml", "Mắm", "chai", 75000, 8, None),
    ("M002", "Mắm ruốc Huế 400g", "Mắm", "hũ", 55000, 6, None),
    ("M003", "Mắm tôm chua 400g", "Mắm", "hũ", 68000, 5, None),
    ("M004", "Rong biển khô 100g", "Hàng khác", "gói", 45000, 4, None),
]
RULE6 = """### Cửa hàng hải sản khô
| Luật | Mặc định |
|---|---|
| Hàng khô | **Hàng khô** là hàng thuộc nhóm `Cá khô`, `Tôm - mực` hoặc `Ruốc - tép`; mắm là nhóm riêng, không tính vào hàng khô |
| Số ký bán ra | cộng số lượng các mặt hàng có đơn vị tính là kg; hàng đóng chai, đóng hũ không quy ra kg |

"""
USUAL = {"done": "Hoàn thành", "cancel": "Đã huỷ", "refund": "Trả hàng"}
VARIANTS = [  # shop, title rows, order cells on the first line only, total row, status words
    ("syn_031", False, False, False, USUAL), ("syn_032", True, False, False, USUAL),
    ("syn_033", False, True, False, USUAL), ("syn_034", False, False, True, USUAL),
    ("syn_035", True, True, True, USUAL),
    ("syn_041", False, False, False, {"done": "Đã bán", "cancel": "Huỷ", "refund": "Trả hàng"}),
    ("syn_042", False, False, False, {"done": "Hoàn tất", "cancel": "Đã huỷ", "refund": "Trả hàng"}),
    ("syn_043", False, False, False, {"done": "Đã thanh toán", "cancel": "Đã huỷ", "refund": "Khách trả hàng"}),
]


def readme(biz: str, title: bool, first: bool, total: bool, status: dict) -> str:
    lay = "Bảng kê bán hàng: mỗi dòng một dòng hàng"
    lay += "; thông tin phiếu chỉ ghi ở dòng đầu của phiếu." if first else "."
    if title and total:
        lay += " Ba dòng đầu sheet là tiêu đề báo cáo, dòng cuối là dòng tổng."
    elif title:
        lay += " Ba dòng đầu sheet là tiêu đề báo cáo."
    elif total:
        lay += " Dòng cuối là dòng tổng."
    return f"""# Dữ liệu {biz}

File Excel xuất từ phần mềm bán hàng của cửa hàng hải sản khô, mỗi danh sách một file. {lay} Ngày dạng dd/mm/yyyy.

## File
- `BangKeBanHang.xlsx` (xlsx)
- `DanhMucHang.xlsx` (xlsx)

## Cột trong `BangKeBanHang.xlsx`
- **Số phiếu**: mã đơn
- **Ngày bán**: ngày bán
- **Tên khách**: tên khách (Khách lẻ nếu không lưu)
- **Tên hàng**: tên hàng
- **ĐVT**: đơn vị tính
- **SL**: số lượng
- **Đơn giá**: đơn giá
- **Thành tiền**: thành tiền sau giảm
- **Thanh toán**: hình thức thanh toán của đơn
- **Trạng thái**: trạng thái đơn

## Cột trong `DanhMucHang.xlsx`
- **Mã hàng**: mã hàng
- **Tên hàng**: tên hàng
- **Nhóm hàng**: nhóm hàng
- **ĐVT**: đơn vị cơ bản
- **Giá bán**: giá bán hiện tại

## Quy ước
- Dữ liệu có đến hết 30/06/2026.
- **Trạng thái đơn**: {", ".join(status[k] for k in ("done", "cancel", "refund"))}.
"""


def write(spec: dict, orders: list[dict], biz: Path, title: bool, first: bool, total: bool) -> None:
    st = spec["status"]
    rows: list[list] = []
    if title:
        rows += [["BẢNG KÊ BÁN HÀNG CHI TIẾT"], [f"Từ ngày {G.START:%d/%m/%Y} đến ngày {G.END:%d/%m/%Y}"], []]
    rows.append(["Số phiếu", "Ngày bán", "Tên khách", "Tên hàng", "ĐVT", "SL", "Đơn giá", "Thành tiền", "Thanh toán",
                 "Trạng thái"])
    tq = ta = 0
    for o in orders:
        for j, ln in enumerate(o["lines"]):
            f = j == 0 or not first
            rows.append([o["id"], f"{o['d']:%d/%m/%Y}" if f else None,
                         (o["cust"]["name"] if o["cust"] else "Khách lẻ") if f else None, ln["name"], ln["unit"],
                         ln["qty"], ln["price"], ln["amount"], o["pay"] if f else None, st[o["status"]] if f else None])
            tq += ln["qty"]
            ta += ln["amount"]
    if total:
        rows.append(["Tổng cộng", None, None, None, None, tq, None, ta])
    S.write_xlsx(biz / "BangKeBanHang.xlsx", [("Bảng kê", rows)])
    S.write_xlsx(biz / "DanhMucHang.xlsx", [("Hàng hoá", [["Mã hàng", "Tên hàng", "Nhóm hàng", "ĐVT", "Giá bán"]] +
                                             [[it[0], it[1], it[2], it[3], G.price_on(spec, it, G.END)]
                                              for it in spec["items"]])])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data"), help="folder of the split (synth3_dev)")
    ap.add_argument("--train", default=str(ROOT / "data" / "train"), help="train split: calendar.csv, rulebook.md")
    args = ap.parse_args(argv)
    train, out = Path(args.train), Path(args.out) / "synth3_dev"
    out.mkdir(parents=True, exist_ok=True)
    (out / "calendar.csv").write_text((train / "calendar.csv").read_text(encoding="utf-8"), encoding="utf-8")
    cal = S.read_calendar(out / "calendar.csv")
    rb = (train / "rulebook.md").read_text(encoding="utf-8")
    assert "## 7. Không trả lời được" in rb
    (out / "rulebook.md").write_text(rb.replace("(bộ train)", "(bộ synth3_dev)")
                                     .replace("## 7. Không trả lời được", RULE6 + "## 7. Không trả lời được"),
                                     encoding="utf-8")
    qs, ans = [], []
    for biz_id, title, first, total, status in VARIANTS:
        spec = {**G.BASE, "biz": biz_id, "split": "dev", "seed": 20261201, "items": ITEMS, "per_day": (10, 18),
                "pays": [("Tiền mặt", 65), ("Chuyển khoản", 35)], "known_rate": 0.5, "n_cust": 110,
                "cust_prefix": "KH", "order_prefix": "PX", "codes": False, "has_time": False, "status": status,
                "price_change": {"C001": (date(2026, 3, 1), 195000)}, "two_pays": ("tiền mặt", "chuyển khoản")}
        biz = out / "data" / biz_id
        biz.mkdir(parents=True, exist_ok=True)
        for old in biz.iterdir():
            old.unlink()
        orders = G.simulate(spec)
        write(spec, orders, biz, title, first, total)
        (biz / "README.md").write_text(readme(biz_id, title, first, total, status), encoding="utf-8")
        book = G.questions(spec, orders, cal)
        keep = [i for i, a in enumerate(book.a) if not a["kind"].startswith("ind_")]  # measures of another type
        qs += [book.q[i] for i in keep]
        ans += [book.a[i] for i in keep]
        print(f"{biz_id}: {len(orders)} orders, {len(keep)} questions, "
              f"{dict(Counter(book.a[i]['type'] for i in keep))}")
    assert len({x["id"] for x in qs}) == len(qs)
    with (out / "questions.jsonl").open("w", encoding="utf-8") as f:
        for x in qs:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    with (out / "answers.jsonl").open("w", encoding="utf-8") as f:
        for a in ans:
            f.write(json.dumps({k: a[k] for k in ("id", "type", "answer", "alias")}, ensure_ascii=False) + "\n")
    with (out / "question_kinds.json").open("w", encoding="utf-8") as f:
        json.dump({a["id"]: a["kind"] for a in ans}, f, ensure_ascii=False, indent=0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
