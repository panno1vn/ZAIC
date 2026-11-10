"""Write data/synth_private/: two hand-made shops of business types that are in neither train nor public (T013 gate).

    python tools/synth_shops.py                    # writes data/synth_private/ (gitignored, share by drive)
    python -m datamate.predict --data data/synth_private --out outputs/synth_run [--llm-url ...]
    python -m datamate.eval.run --split synth_private --pred outputs/synth_run/submission.jsonl

- syn_001: hair salon & spa. Exported from sales software: invoice lines with the invoice cells only on the first
  line, title rows above the header, a total row, prepaid session packages paid by "Thẻ liệu trình" (no revenue).
- syn_002: pet shop. Hand-kept ledger, one sheet per month, unaccented headers, days without a year, notes as
  status / payment, a separate grooming book (csv), purchases with lot expiry, debt payments, stock by lot.

The split's rulebook is train's plus a §6 section for each new business type, as a private split may have. Every
answer is computed here from the clean frames, before the files are made messy, by the rulebook's rules.
Deterministic (fixed seed). Development only: no organizer data is read except train's calendar and rulebook.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261111


# ------------------------------------------------------------------------------------------------ helpers
def half_up(x: float, nd: int = 0):
    v = Decimal(str(x)).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP)
    return int(v) if nd == 0 else float(v)


def pct(a: float, b: float) -> float:
    return half_up(a * 100 / b, 2)


def month(y: int, m: int) -> tuple[date, date]:
    nxt = date(y + m // 12, m % 12 + 1, 1)
    return date(y, m, 1), nxt - timedelta(days=1)


def quarter(y: int, q: int) -> tuple[date, date]:
    return date(y, 3 * q - 2, 1), month(y, 3 * q)[1]


def prev_week(d: date) -> tuple[date, date]:
    mon = d - timedelta(days=d.weekday())
    return mon - timedelta(days=7), mon - timedelta(days=1)


def last_n(d: date, n: int) -> tuple[date, date]:
    return d - timedelta(days=n - 1), d


def daterange(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def tet_range(year: int, cal: list[dict]) -> tuple[date, date]:
    """§2: 23 tháng Chạp of lunar year Y-1 to mùng 10 tháng Giêng of lunar year Y."""
    a = next(r["date"] for r in cal if r["lunar_year"] == year - 1 and r["lunar_month"] == 12
             and r["lunar_day"] == 23 and not r["leap"])
    b = next(r["date"] for r in cal if r["lunar_year"] == year and r["lunar_month"] == 1
             and r["lunar_day"] == 10 and not r["leap"])
    return a, b


def read_calendar(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [{"date": date.fromisoformat(r["date"]), "lunar_day": int(r["lunar_day"]),
                 "lunar_month": int(r["lunar_month"]), "lunar_year": int(r["lunar_year"]),
                 "leap": r["lunar_leap"] == "true"} for r in csv.DictReader(f)]


def top(scores: dict, key=lambda k: k, k: int = 1, reverse: bool = True) -> list:
    """Keys by score (descending), ties by key ascending (§9)."""
    items = sorted(scores.items(), key=lambda kv: ((-kv[1]) if reverse else kv[1], key(kv[0])))
    return [kv[0] for kv in items[:k]]


def norm_name(s: str) -> str:
    return " ".join(s.lower().split())


def write_xlsx(path: Path, sheets: list[tuple[str, list[list]]]) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in sheets:
        ws = wb.create_sheet(title)
        for r in rows:
            ws.append(r)
    wb.save(path)


def qid(biz: str, text: str) -> str:
    return "q_" + hashlib.sha1(f"{biz}|{text}".encode("utf-8")).hexdigest()[:12]


class Book:
    """Questions and answers of one shop."""

    def __init__(self, biz: str):
        self.biz, self.q, self.a = biz, [], []

    def add(self, text: str, as_of: date, typ: str, answer=None, alias=None, kind: str = "") -> None:
        i = qid(self.biz, text)
        self.q.append({"id": i, "business_id": self.biz, "question": text, "as_of_date": as_of.isoformat()})
        self.a.append({"id": i, "type": typ, "answer": answer, "alias": alias or [], "kind": kind})


VN_HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Phan", "Trịnh"]
VN_DEM = ["Thị", "Văn", "Ngọc", "Minh", "Thu", "Hoàng", "Thanh", "Kim", "Quốc", "Bảo", "Hải", "Mỹ", "Đức", "Phương"]
VN_TEN = ["An", "Bình", "Châu", "Dung", "Giang", "Hà", "Hạnh", "Hiền", "Hoa", "Hùng", "Hương", "Khánh", "Lan", "Linh",
          "Loan", "Long", "Mai", "My", "Nam", "Nga", "Ngân", "Nhung", "Oanh", "Phúc", "Quân", "Quyên", "Sơn", "Tâm",
          "Thảo", "Trang", "Trinh", "Tú", "Tuấn", "Uyên", "Vân", "Vy", "Yến", "Duy", "Khoa", "Thư"]


# ------------------------------------------------------------------------------------------------ syn_001 salon
SALON_STAFF = {"NV01": "Minh Tâm", "NV02": "Quốc Bảo", "NV03": "Thu Hà", "NV04": "Ngọc Lan", "NV05": "Văn Khoa"}
SALON_ITEMS = [  # code, name, group, kind, price, cost, staff pool, weight
    ("DV01", "Cắt tóc nam", "Cắt tóc", "service", 80000, None, ["NV01", "NV02", "NV05"], 30),
    ("DV02", "Cắt tóc nữ", "Cắt tóc", "service", 150000, None, ["NV01", "NV02", "NV03"], 22),
    ("DV03", "Gội dưỡng sinh", "Gội - Sấy", "service", 120000, None, ["NV03", "NV04"], 16),
    ("DV04", "Gội sấy tạo kiểu", "Gội - Sấy", "service", 70000, None, list(SALON_STAFF), 18),
    ("DV05", "Uốn setting", "Uốn", "service", 650000, None, ["NV01", "NV02"], 5),
    ("DV06", "Uốn lạnh Hàn Quốc", "Uốn", "service", 850000, None, ["NV01", "NV02"], 3),
    ("DV07", "Duỗi phồng", "Uốn", "service", 700000, None, ["NV02"], 3),
    ("DV08", "Nhuộm thời trang", "Nhuộm", "service", 550000, None, ["NV01", "NV02", "NV05"], 7),
    ("DV09", "Nhuộm phủ bạc", "Nhuộm", "service", 350000, None, ["NV05", "NV02"], 5),
    ("DV10", "Phục hồi Keratin", "Phục hồi", "service", 450000, None, ["NV03", "NV01"], 5),
    ("DV11", "Chăm sóc da cơ bản", "Spa mặt", "service", 350000, None, ["NV03", "NV04"], 7),
    ("DV12", "Lấy nhân mụn", "Spa mặt", "service", 250000, None, ["NV04"], 5),
    ("DV13", "Sơn gel", "Nail", "service", 150000, None, ["NV04"], 8),
    ("DV14", "Cắt da tay", "Nail", "service", 50000, None, ["NV04", "NV03"], 6),
    ("SP01", "Dầu gội Tsubaki 490ml", "Sản phẩm", "product", 195000, 138000, None, 4),
    ("SP02", "Sáp vuốt tóc By Vilain 65g", "Sản phẩm", "product", 320000, 230000, None, 3),
    ("SP03", "Serum dưỡng tóc Mise en scène 80ml", "Sản phẩm", "product", 165000, 112000, None, 3),
    ("SP04", "Dầu xả phục hồi Karseell 500ml", "Sản phẩm", "product", 240000, 160000, None, 2),
    ("GOI1", "Gói gội dưỡng sinh 10 buổi", "Gói liệu trình", "package", 990000, None, None, 0),
    ("GOI2", "Gói chăm sóc da 5 buổi", "Gói liệu trình", "package", 1490000, None, None, 0),
]
SALON_PACKAGE = {"GOI1": ("DV03", 10), "GOI2": ("DV11", 5)}
SALON_PRICE_CHANGES = {"DV05": [(date(2026, 1, 5), 700000)], "DV13": [(date(2025, 9, 1), 170000)],
                       "SP01": [(date(2025, 11, 1), 210000)]}
SALON_START, SALON_END = date(2025, 1, 1), date(2026, 6, 30)
REFUND_WORD = "Trả hàng"  # --refund-word: a status word the mapper may not know ("Hoàn tiền")


def salon_price(code: str, base: int, d: date) -> int:
    p = base
    for since, newp in SALON_PRICE_CHANGES.get(code, []):
        if d >= since:
            p = newp
    return p


def gen_salon(rng: random.Random, cal: list[dict], out: Path) -> Book:
    items = {c[0]: c for c in SALON_ITEMS}
    services = [c for c in SALON_ITEMS if c[3] == "service"]
    products = [c for c in SALON_ITEMS if c[3] == "product"]

    customers = []
    for i in range(1, 241):
        name = f"{rng.choice(VN_HO)} {rng.choice(VN_DEM)} {rng.choice(VN_TEN)}"
        reg = date(2024, 3, 1) + timedelta(days=rng.randint(0, (date(2026, 6, 20) - date(2024, 3, 1)).days))
        tier = rng.choices(["Thường", "Bạc", "Vàng"], [60, 28, 12])[0]
        customers.append({"code": f"KH{i:04d}", "name": name, "phone": f"09{rng.randint(10000000, 99999999)}",
                          "tier": tier, "reg": reg, "w": rng.paretovariate(1.6)})
    customers[57]["name"] = customers[12]["name"]  # two codes, one name (§3: two customers)
    tier_of = {c["code"]: c["tier"] for c in customers}
    name_of = {c["code"]: c["name"] for c in customers}

    invoices, lines, packages = [], [], []
    usage_due: dict[date, list[dict]] = defaultdict(list)
    for d in daterange(SALON_START, SALON_END):
        active = [c for c in customers if c["reg"] <= d]
        n = rng.randint(7, 12) + (5 if d.weekday() >= 5 else 0)
        for _ in range(n):
            cust = rng.choices(active, [c["w"] for c in active])[0] if active and rng.random() < 0.72 else None
            dt = datetime(d.year, d.month, d.day, rng.randint(8, 20), rng.choice([0, 10, 15, 20, 30, 40, 45, 50]))
            inv = {"dt": dt, "cust": cust["code"] if cust else None, "voucher": 0, "note": "", "pkg": None}
            ls = []
            first = rng.choices(services, [s[7] for s in services])[0]
            chosen = [first]
            if rng.random() < 0.25:
                other = [s for s in services if s[2] != first[2]]
                chosen.append(rng.choices(other, [s[7] for s in other])[0])
            for s in chosen:
                p = salon_price(s[0], s[4], d)
                disc = half_up(p * 0.1 / 1000) * 1000 if cust and tier_of[cust["code"]] == "Vàng" and rng.random() < 0.5 else 0
                ls.append({"code": s[0], "qty": 1, "price": p, "disc": disc, "staff": SALON_STAFF[rng.choice(s[6])]})
            if rng.random() < 0.13:
                pr = rng.choices(products, [p[7] for p in products])[0]
                q = rng.choice([1, 1, 1, 2])
                ls.append({"code": pr[0], "qty": q, "price": salon_price(pr[0], pr[4], d), "disc": 0, "staff": None})
            bought = None
            if cust and rng.random() < 0.035:
                bought = rng.choice(["GOI1", "GOI1", "GOI2"])
                ls.append({"code": bought, "qty": 1, "price": items[bought][4], "disc": 0, "staff": None})
            if rng.random() < 0.04:
                inv["voucher"] = rng.choice([20000, 50000])
            inv["pay"] = rng.choices(["Tiền mặt", "Chuyển khoản", "Quẹt thẻ"], [55, 40, 5])[0]
            r = rng.random()
            inv["status"] = "Hoàn thành" if bought or r >= 0.035 else ("Đã huỷ" if r < 0.025 else REFUND_WORD)
            inv["lines"] = ls
            invoices.append(inv)
            if bought:
                pkg = {"code": f"G{len(packages) + 1:04d}", "cust": cust["code"], "item": bought,
                       "sessions": SALON_PACKAGE[bought][1], "bought": d, "inv": inv}
                packages.append(pkg)
                nxt, k = d + timedelta(days=rng.randint(3, 14)), 0
                while k < pkg["sessions"] and nxt <= SALON_END and rng.random() < 0.97:
                    usage_due[nxt].append(pkg)
                    nxt += timedelta(days=rng.randint(5, 20))
                    k += 1
        for pkg in usage_due.pop(d, []):
            svc = items[SALON_PACKAGE[pkg["item"]][0]]
            dt = datetime(d.year, d.month, d.day, rng.randint(8, 20), rng.choice([0, 15, 30, 45]))
            invoices.append({"dt": dt, "cust": pkg["cust"], "voucher": 0, "pay": "Thẻ liệu trình",
                             "status": "Hoàn thành", "note": f"Dùng gói {pkg['code']}", "pkg": pkg["code"],
                             "lines": [{"code": svc[0], "qty": 1, "price": salon_price(svc[0], svc[4], d), "disc": 0,
                                        "staff": SALON_STAFF[rng.choice(svc[6])]}]})

    invoices.sort(key=lambda v: v["dt"])
    for i, inv in enumerate(invoices, 1):
        inv["id"] = f"HD{i:06d}"
        inv["d"] = inv["dt"].date()
        for ln in inv["lines"]:
            it = items[ln["code"]]
            ln.update({"inv": inv, "name": it[1], "group": it[2], "kind": it[3],
                       "amount": ln["qty"] * ln["price"] - ln["disc"]})
            lines.append(ln)
    for p in packages:
        p["inv_id"] = p["inv"]["id"]

    # ---- files
    biz = out / "data" / "syn_001"
    biz.mkdir(parents=True, exist_ok=True)
    head = ["Mã hoá đơn", "Thời gian", "Mã KH", "Khách hàng", "Mã DV/SP", "Tên dịch vụ/sản phẩm", "SL", "Đơn giá",
            "Giảm giá", "Thành tiền", "Nhân viên thực hiện", "Giảm giá HĐ", "Hình thức TT", "Trạng thái", "Ghi chú"]
    rows = [["BÁO CÁO CHI TIẾT HOÁ ĐƠN BÁN HÀNG"],
            [f"Từ ngày {SALON_START:%d/%m/%Y} đến ngày {SALON_END:%d/%m/%Y}"], [], head]
    tot_q = tot_a = 0
    for inv in invoices:
        for j, ln in enumerate(inv["lines"]):
            first = j == 0
            rows.append([inv["id"], f"{inv['dt']:%d/%m/%Y %H:%M}" if first else None,
                         (inv["cust"] or None) if first else None,
                         (name_of[inv["cust"]] if inv["cust"] else "Khách lẻ") if first else None,
                         ln["code"], ln["name"], ln["qty"], ln["price"], ln["disc"] or None, ln["amount"], ln["staff"],
                         (inv["voucher"] or None) if first else None, inv["pay"] if first else None,
                         inv["status"] if first else None, (inv["note"] or None) if first else None])
            tot_q += ln["qty"]
            tot_a += ln["amount"]
    rows.append(["Tổng cộng", None, None, None, None, None, tot_q, None, None, tot_a])
    write_xlsx(biz / "Chi_tiet_hoa_don.xlsx", [("Chi tiết HĐ", rows)])

    cat = [["Mã", "Tên", "Nhóm", "Đơn giá", "Giá vốn"]]
    for it in SALON_ITEMS:
        cat.append([it[0], it[1], it[2], salon_price(it[0], it[4], SALON_END), it[5]])
    hist = [["Mã", "Tên", "Ngày áp dụng", "Giá mới"]]
    for code, ch in SALON_PRICE_CHANGES.items():
        for since, p in ch:
            hist.append([code, items[code][1], f"{since:%d/%m/%Y}", p])
    staff = [["Mã NV", "Tên nhân viên"]] + [[k, v] for k, v in SALON_STAFF.items()]
    write_xlsx(biz / "Danh_muc.xlsx", [("Dịch vụ - Sản phẩm", cat)])
    write_xlsx(biz / "Lich_su_gia.xlsx", [("Lịch sử giá", hist)])
    write_xlsx(biz / "Nhan_vien.xlsx", [("Nhân viên", staff)])
    write_xlsx(biz / "Khach_hang.xlsx", [("Khách hàng", [["Mã KH", "Tên khách hàng", "SĐT", "Hạng thẻ", "Ngày đăng ký"]] +
                                           [[c["code"], c["name"], c["phone"], c["tier"], f"{c['reg']:%d/%m/%Y}"]
                                            for c in customers])])
    write_xlsx(biz / "Goi_lieu_trinh.xlsx", [("Gói đã bán", [["Mã gói", "Mã KH", "Khách hàng", "Tên gói", "Số buổi",
                                                               "Ngày mua", "Mã hoá đơn"]] +
                                               [[p["code"], p["cust"], name_of[p["cust"]], items[p["item"]][1],
                                                 p["sessions"], f"{p['bought']:%d/%m/%Y}", p["inv_id"]]
                                                for p in packages])])
    (biz / "README.md").write_text(SALON_README.replace("REFUND_WORD", REFUND_WORD), encoding="utf-8")

    # ---- answers
    book = Book("syn_001")
    staff_code = {v: k for k, v in SALON_STAFF.items()}

    def rev_lines(a, b):
        return [ln for ln in lines if a <= ln["inv"]["d"] <= b and ln["inv"]["status"] == "Hoàn thành"
                and ln["inv"]["pay"] != "Thẻ liệu trình"]

    def counted(a, b):
        return [v for v in invoices if a <= v["d"] <= b and v["status"] == "Hoàn thành"]

    def rev(a, b, pred=lambda ln: True):
        return sum(ln["amount"] for ln in rev_lines(a, b) if pred(ln))

    def service_lines(a, b):
        return [ln for v in counted(a, b) for ln in v["lines"] if ln["kind"] == "service"]

    def by(lines_, key, val=lambda ln: ln["amount"]):
        s = defaultdict(int)
        for ln in lines_:
            k = key(ln)
            if k is not None:
                s[k] += val(ln)
        return s

    A = book.add
    m3 = month(2026, 3)
    A("Doanh thu tháng 3/2026 của tiệm là bao nhiêu?", date(2026, 4, 10), "number", rev(*m3), kind="revenue")
    d = date(2026, 5, 16)
    A("hôm nay tiệm thu được bao nhiêu tiền", d, "number", rev(d, d), kind="revenue")
    d = date(2026, 6, 10)
    A("Tuần trước có bao nhiêu hoá đơn?", d, "number", len(counted(*prev_week(d))), kind="order_count")
    p = month(2025, 11)
    allinv = [v for v in invoices if p[0] <= v["d"] <= p[1]]
    A("Tỉ lệ hoá đơn bị huỷ trong tháng 11/2025 là bao nhiêu %?", date(2025, 12, 5), "percent",
      pct(sum(v["status"] == "Đã huỷ" for v in allinv), len(allinv)), kind="cancel_rate")
    s = by(service_lines(*month(2026, 4)), lambda ln: ln["code"], lambda ln: ln["qty"])
    c = top(s)[0]
    A("Tháng 4/2026 dịch vụ nào được làm nhiều lượt nhất?", date(2026, 5, 2), "string", items[c][1], [c],
      kind="best_seller")
    s = by(rev_lines(*month(2025, 1)[:1], date(2025, 12, 31)), lambda ln: ln["inv"]["cust"])
    t3 = top(s, k=3)
    A("Top 3 khách chi nhiều tiền nhất năm 2025", date(2026, 1, 15), "list", [name_of[k] for k in t3],
      [[k] for k in t3], kind="top_customer")
    s = by(rev_lines(*month(2026, 5)), lambda ln: ln["inv"]["cust"])
    c = top(s)[0]
    A("Khách nào chi nhiều tiền nhất tháng 5/2026?", date(2026, 6, 3), "string", name_of[c], [c], kind="top_customer")
    p = month(2026, 2)
    A("Giá trị trung bình một hoá đơn tháng 2/2026 là bao nhiêu?", date(2026, 3, 3), "number",
      half_up(rev(*p) / len(counted(*p))), kind="avg_order")
    A("Doanh thu nhóm Nhuộm quý 1/2026", date(2026, 4, 20), "number",
      rev(*quarter(2026, 1), lambda ln: ln["group"] == "Nhuộm"), kind="group_revenue")
    p = month(2026, 6)
    A("Nhóm Sản phẩm chiếm bao nhiêu % doanh thu của tiệm tháng 6/2026?", date(2026, 6, 30), "percent",
      pct(rev(*p, lambda ln: ln["group"] == "Sản phẩm"), rev(*p)), kind="group_share")
    A("Doanh thu chuyển khoản tháng 1/2026 được bao nhiêu?", date(2026, 2, 10), "number",
      rev(*month(2026, 1), lambda ln: ln["inv"]["pay"] == "Chuyển khoản"), kind="payment_revenue")
    r4, r5 = rev(*month(2026, 4)), rev(*month(2026, 5))
    A("Doanh thu tháng 5/2026 tăng hay giảm bao nhiêu % so với tháng 4/2026?", date(2026, 6, 5), "percent",
      pct(r5 - r4, r4), kind="growth")
    A("Doanh thu dịp Tết 2026 được bao nhiêu?", date(2026, 3, 1), "number", rev(*tet_range(2026, cal)), kind="tet")
    s = by(rev_lines(*m3), lambda ln: ln["inv"]["d"])
    A("Ngày nào trong tháng 3/2026 tiệm có doanh thu cao nhất?", date(2026, 4, 1), "date", top(s)[0].isoformat(),
      kind="which_day")
    s = by(rev_lines(date(2025, 1, 1), date(2025, 12, 31)), lambda ln: ln["inv"]["d"].strftime("%Y-%m"))
    A("Năm 2025 tháng nào doanh thu cao nhất?", date(2026, 1, 10), "date", top(s)[0], kind="which_month")
    p = month(2026, 4)
    A("Doanh thu ca sáng và ca chiều tháng 4/2026 lần lượt là bao nhiêu?", date(2026, 5, 5), "list",
      [rev(*p, lambda ln: 6 <= ln["inv"]["dt"].hour <= 13), rev(*p, lambda ln: 14 <= ln["inv"]["dt"].hour <= 21)],
      kind="shift")
    A("Tháng 5/2026 có bao nhiêu khách đã đến tiệm?", date(2026, 6, 1), "number",
      len({v["cust"] for v in counted(*month(2026, 5)) if v["cust"]}), kind="customer_count")
    A("Doanh thu từ khách hạng Vàng tháng 3/2026 là bao nhiêu?", date(2026, 4, 2), "number",
      rev(*m3, lambda ln: ln["inv"]["cust"] is not None and tier_of[ln["inv"]["cust"]] == "Vàng"),
      kind="customer_group_revenue")
    s = by(rev_lines(*month(2026, 6)), lambda ln: ln["group"])
    A("Doanh thu từng nhóm hàng tháng 6/2026", date(2026, 6, 30), "table",
      {"columns": ["nhom_hang", "doanh_thu"], "rows": [[g, s[g]] for g in top(s, k=len(s))]}, kind="table")
    A("Doanh thu tháng 6/2026 có cao hơn tháng 5/2026 không?", date(2026, 6, 30), "boolean",
      rev(*month(2026, 6)) > r5, kind="boolean")
    # type-specific
    s = by(service_lines(*month(2026, 5)), lambda ln: ln["staff"], lambda ln: ln["qty"])
    c = top(s, key=lambda n: staff_code[n])[0]
    A("Thợ nào làm nhiều lượt nhất tháng 5/2026?", date(2026, 6, 2), "string", c, [staff_code[c]],
      kind="salon_staff_visits")
    A("Doanh thu của thợ Thu Hà tháng 4/2026 là bao nhiêu?", date(2026, 5, 3), "number",
      rev(*month(2026, 4), lambda ln: ln["kind"] == "service" and ln["staff"] == "Thu Hà"), kind="salon_staff_revenue")
    s = by([ln for ln in rev_lines(*quarter(2026, 1)) if ln["kind"] == "service"], lambda ln: ln["staff"])
    t3 = top(s, key=lambda n: staff_code[n], k=3)
    A("3 thợ có doanh thu cao nhất quý 1/2026", date(2026, 4, 3), "list", t3, [[staff_code[n]] for n in t3],
      kind="salon_staff_revenue")
    A("Năm 2025 tiệm bán được bao nhiêu gói liệu trình?", date(2026, 1, 8), "number",
      sum(ln["qty"] for ln in rev_lines(date(2025, 1, 1), date(2025, 12, 31)) if ln["kind"] == "package"),
      kind="salon_package")
    A("Doanh thu bán gói liệu trình tháng 3/2026", date(2026, 4, 4), "number",
      rev(*m3, lambda ln: ln["kind"] == "package"), kind="salon_package")
    d = date(2026, 5, 20)
    used = Counter(v["pkg"] for v in invoices if v["pkg"] and v["d"] <= d)
    owned = Counter((p["cust"], p["item"]) for p in packages if p["bought"] <= d)
    pk = next(p for p in packages if p["bought"] <= d and 0 < used[p["code"]] < p["sessions"]
              and owned[(p["cust"], p["item"])] == 1 and list(name_of.values()).count(name_of[p["cust"]]) == 1)
    A(f"Khách {name_of[pk['cust']]} còn mấy buổi của {items[pk['item']][1]} tính đến hôm nay?", d, "number",
      pk["sessions"] - used[pk["code"]], kind="salon_package_left")
    A("Tháng 5/2026 có bao nhiêu lượt khách dùng thẻ liệu trình?", date(2026, 6, 4), "number",
      sum(1 for v in counted(*month(2026, 5)) if v["pay"] == "Thẻ liệu trình"), kind="salon_package_use")
    cnt = Counter(v["cust"] for v in counted(*month(2026, 4)) if v["cust"])
    A("Tháng 4/2026 có bao nhiêu khách quay lại tiệm từ 2 lần trở lên?", date(2026, 5, 6), "number",
      sum(1 for n in cnt.values() if n >= 2), kind="salon_returning")
    s = by(rev_lines(date(2025, 1, 1), date(2025, 12, 31)), lambda ln: ln["code"] if ln["group"] == "Uốn" else None)
    c = top(s)[0]
    A("Trong nhóm Uốn, dịch vụ nào có doanh thu cao nhất năm 2025?", date(2026, 1, 12), "string", items[c][1], [c],
      kind="group_rank")
    A("Tháng 6/2026 tiệm làm được bao nhiêu lượt nail?", date(2026, 6, 30), "number",
      sum(ln["qty"] for ln in service_lines(*month(2026, 6)) if ln["group"] == "Nail"), kind="salon_visits")
    A("Có bao nhiêu khách đăng ký thành viên mới trong tháng 3/2026?", date(2026, 4, 1), "number",
      sum(1 for c in customers if m3[0] <= c["reg"] <= m3[1]), kind="new_members")
    dd = next(ln["inv"]["d"] for ln in lines if ln["code"] == "DV05" and ln["inv"]["d"] >= date(2026, 2, 1))
    A(f"Giá dịch vụ Uốn setting ngày {dd:%d/%m/%Y} là bao nhiêu?", date(2026, 3, 15), "number",
      salon_price("DV05", 650000, dd), kind="price_on_day")
    d = date(2026, 2, 28)
    A("7 ngày gần nhất tiệm thu được bao nhiêu?", d, "number", rev(*last_n(d, 7)), kind="revenue")
    d = date(2025, 8, 18)
    y = d - timedelta(days=1)
    A("Hôm qua tiệm bán được bao nhiêu tiền?", d, "number", rev(y, y), kind="revenue")
    d = date(2026, 6, 20)
    A("Tháng này tới giờ có mấy hoá đơn bị huỷ?", d, "number",
      sum(1 for v in invoices if date(2026, 6, 1) <= v["d"] <= d and v["status"] == "Đã huỷ"), kind="cancel_count")
    # unanswerable: the shop records none of it
    A("Tính đến hôm nay khách còn nợ tiệm tổng cộng bao nhiêu?", date(2026, 6, 30), "unanswerable", kind="unans_debt")
    A("Tiền nhập sản phẩm tháng 3/2026 là bao nhiêu?", date(2026, 4, 5), "unanswerable", kind="unans_purchase")
    A("Doanh thu tháng 10/2024 là bao nhiêu?", date(2026, 1, 5), "unanswerable", kind="unans_out_of_range")
    A("Thợ nào được khách đánh giá tốt nhất tháng 5/2026?", date(2026, 6, 2), "unanswerable", kind="unans_quality")
    A("Lãi ròng tháng 5/2026 của tiệm là bao nhiêu?", date(2026, 6, 6), "unanswerable", kind="unans_expense")
    return book


SALON_README = """# Dữ liệu syn_001

File Excel xuất từ phần mềm quản lý salon tóc và spa, mỗi danh sách một file. Chi tiết hoá đơn: mỗi dòng một dòng hàng (dịch vụ, sản phẩm bán lẻ hoặc gói liệu trình); thông tin đơn chỉ ghi ở dòng đầu của đơn. Ba dòng đầu sheet là tiêu đề báo cáo, dòng cuối là dòng tổng. Ngày dạng dd/mm/yyyy.

## File
- `Chi_tiet_hoa_don.xlsx` (xlsx)
- `Danh_muc.xlsx` (xlsx)
- `Lich_su_gia.xlsx` (xlsx)
- `Nhan_vien.xlsx` (xlsx)
- `Khach_hang.xlsx` (xlsx)
- `Goi_lieu_trinh.xlsx` (xlsx)

## Cột trong `Chi_tiet_hoa_don.xlsx`
- **Mã hoá đơn**: mã đơn
- **Thời gian**: thời điểm đặt đơn
- **Mã KH**: mã khách
- **Khách hàng**: tên khách (Khách lẻ nếu không lưu)
- **Mã DV/SP**: mã hàng
- **Tên dịch vụ/sản phẩm**: tên hàng
- **SL**: số lượng
- **Đơn giá**: đơn giá
- **Giảm giá**: tiền giảm của cả dòng
- **Thành tiền**: thành tiền sau giảm
- **Nhân viên thực hiện**: thợ làm dịch vụ của dòng (dòng sản phẩm, dòng gói để trống)
- **Giảm giá HĐ**: tiền bớt cho cả đơn
- **Hình thức TT**: hình thức thanh toán của đơn: Tiền mặt, Chuyển khoản, Quẹt thẻ, Thẻ liệu trình
- **Trạng thái**: trạng thái đơn
- **Ghi chú**: ghi chú của đơn

## Cột trong `Danh_muc.xlsx`
- **Mã**: mã hàng
- **Tên**: tên hàng
- **Nhóm**: nhóm hàng
- **Đơn giá**: giá bán hiện tại
- **Giá vốn**: giá vốn (chỉ sản phẩm bán lẻ)

## Cột trong `Lich_su_gia.xlsx`
- **Mã**: mã hàng
- **Tên**: tên hàng
- **Ngày áp dụng**: ngày bắt đầu áp dụng giá
- **Giá mới**: giá bán áp dụng từ ngày đó

## Cột trong `Nhan_vien.xlsx`
- **Mã NV**: mã nhân viên
- **Tên nhân viên**: họ tên nhân viên

## Cột trong `Khach_hang.xlsx`
- **Mã KH**: mã khách
- **Tên khách hàng**: tên khách
- **SĐT**: số điện thoại
- **Hạng thẻ**: nhóm khách
- **Ngày đăng ký**: ngày đăng ký

## Cột trong `Goi_lieu_trinh.xlsx`
- **Mã gói**: mã gói liệu trình
- **Mã KH**: mã khách
- **Khách hàng**: tên khách
- **Tên gói**: tên hàng của gói
- **Số buổi**: số buổi của gói
- **Ngày mua**: ngày bán gói
- **Mã hoá đơn**: mã đơn bán gói

## Quy ước
- Dữ liệu có đến hết 30/06/2026.
- **Trạng thái đơn**: Hoàn thành, Đã huỷ, REFUND_WORD (khách được hoàn tiền cả đơn, là đơn trả hàng).
- **Thẻ liệu trình**: đơn trả bằng thẻ liệu trình là một buổi dùng gói khách đã mua; **Ghi chú** ghi mã gói (`Dùng gói G0001`).
"""


# ------------------------------------------------------------------------------------------------ syn_002 pet shop
PET_ITEMS = [  # code, name, group, base unit, big unit, factor, base price, base cost, shelf days (None: no expiry), weight, supplier
    ("TC001", "Hạt Royal Canin Mini Adult 2kg", "Thức ăn chó", "túi", None, 1, 395000, 318000, 420, 6, "NPP Thú Cưng Phương Nam"),
    ("TC002", "Hạt SmartHeart Puppy 1.5kg", "Thức ăn chó", "túi", None, 1, 145000, 112000, 360, 8, "Công ty TNHH Hạt Vàng"),
    ("TC003", "Hạt Ganador Adult 3kg", "Thức ăn chó", "túi", None, 1, 210000, 165000, 360, 5, "Công ty TNHH Hạt Vàng"),
    ("TC004", "Hạt Pedigree bò rau củ 1.5kg", "Thức ăn chó", "túi", "bao", 6, 128000, 99000, 300, 7, "Đại lý Minh Phát"),
    ("TC005", "Xương gặm Orgo sữa 90g", "Thức ăn chó", "gói", None, 1, 45000, 31000, 240, 6, "Đại lý Minh Phát"),
    ("TC006", "Hạt Me-O cá ngừ 1.2kg", "Thức ăn mèo", "túi", "bao", 10, 115000, 88000, 330, 9, "Công ty TNHH Hạt Vàng"),
    ("TC007", "Hạt Royal Canin Kitten 2kg", "Thức ăn mèo", "túi", None, 1, 480000, 392000, 420, 5, "NPP Thú Cưng Phương Nam"),
    ("TC008", "Hạt Whiskas cá biển 1.2kg", "Thức ăn mèo", "túi", "bao", 8, 112000, 86000, 300, 8, "Đại lý Minh Phát"),
    ("TC009", "Hạt Catsrang 2kg", "Thức ăn mèo", "túi", None, 1, 185000, 142000, 360, 6, "Công ty TNHH Hạt Vàng"),
    ("TC010", "Súp thưởng Ciao Churu cá ngừ 14g", "Thức ăn mèo", "gói", "hộp", 20, 12000, 8000, 270, 9, "NPP Thú Cưng Phương Nam"),
    ("TC011", "Pate Whiskas cá ngừ 85g", "Pate", "lon", "thùng", 24, 17000, 12500, 540, 10, "Đại lý Minh Phát"),
    ("TC012", "Pate Me-O gà 80g", "Pate", "lon", "thùng", 24, 14000, 10000, 540, 9, "Công ty TNHH Hạt Vàng"),
    ("TC013", "Pate Pedigree bò 400g", "Pate", "lon", "thùng", 12, 52000, 39000, 540, 5, "Đại lý Minh Phát"),
    ("TC014", "Pate Kitcat cá hồi 85g", "Pate", "lon", "thùng", 24, 19000, 13500, 480, 6, "NPP Thú Cưng Phương Nam"),
    ("TC015", "Cát đậu nành Cature 6L", "Cát vệ sinh", "túi", "bao", 4, 135000, 98000, None, 8, "NPP Thú Cưng Phương Nam"),
    ("TC016", "Cát bentonite Me-O 5L", "Cát vệ sinh", "túi", "bao", 4, 85000, 61000, None, 7, "Công ty TNHH Hạt Vàng"),
    ("TC017", "Cát gỗ thông 10L", "Cát vệ sinh", "túi", None, 1, 120000, 86000, None, 3, "Đại lý Minh Phát"),
    ("TC018", "Vòng cổ chuông size S", "Phụ kiện", "cái", None, 1, 35000, 18000, None, 4, "Đại lý Minh Phát"),
    ("TC019", "Dây dắt nylon 1.2m", "Phụ kiện", "cái", None, 1, 65000, 38000, None, 3, "Đại lý Minh Phát"),
    ("TC020", "Bát ăn inox đôi", "Phụ kiện", "cái", None, 1, 89000, 52000, None, 2, "Đại lý Minh Phát"),
    ("TC021", "Đồ chơi chuột lông", "Phụ kiện", "cái", None, 1, 25000, 12000, None, 4, "NPP Thú Cưng Phương Nam"),
    ("TC022", "Nệm tròn size M", "Phụ kiện", "cái", None, 1, 220000, 140000, None, 1, "NPP Thú Cưng Phương Nam"),
    ("TC023", "Sữa tắm SOS lông trắng 530ml", "Vệ sinh - Thuốc", "chai", None, 1, 135000, 96000, 720, 4, "Đại lý Minh Phát"),
    ("TC024", "Nhỏ gáy trị ve Frontline Plus", "Vệ sinh - Thuốc", "ống", "hộp", 3, 125000, 92000, 600, 4, "NPP Thú Cưng Phương Nam"),
    ("TC025", "Thuốc tẩy giun Drontal", "Vệ sinh - Thuốc", "viên", "hộp", 10, 38000, 26000, 600, 3, "NPP Thú Cưng Phương Nam"),
    ("TC026", "Xịt khử mùi Bio 300ml", "Vệ sinh - Thuốc", "chai", None, 1, 95000, 64000, 720, 2, "Đại lý Minh Phát"),
]
PET_SPA = {  # service: (dog <5kg, 5-15kg, >15kg) price; cats use the first two tiers
    "Tắm": (120000, 180000, 250000), "Tắm + cắt tỉa": (250000, 350000, 450000),
    "Cạo lông": (200000, 300000, 400000), "Cắt móng - vệ sinh tai": (60000, 60000, 60000),
}
PET_START, PET_END = date(2025, 3, 1), date(2026, 8, 31)
PET_DISCONTINUED = {"TC022": date(2026, 4, 1), "TC020": date(2026, 4, 15)}  # not restocked after: sold out, then unsold
PET_NAMES = ["Hoa", "Lan", "Tuấn", "Hùng", "Mai", "Nga", "Bình", "Vy", "Thảo", "Long", "Khoa", "Trang", "Hạnh", "Duy",
             "Phúc", "Yến", "Thư", "Nam", "Linh", "Quân", "Hà", "Uyên", "Sơn", "My", "Tâm", "Giang", "Châu", "Oanh"]
PET_PETS = ["Mochi", "Lu", "Bông", "Mít", "Na", "Kem", "Sữa", "Bơ", "Tiểu Hổ", "Đậu", "Mun", "Gấu", "Lucky", "Milo",
            "Xoài", "Bi", "Cún", "Miu", "Su", "Ken"]


def gen_pet(rng: random.Random, cal: list[dict], out: Path) -> Book:
    items = {c[0]: c for c in PET_ITEMS}
    custs = []
    for pre in ["Chị", "Anh", "Cô", "Chú", "Em"]:
        for n in rng.sample(PET_NAMES, 9):
            custs.append(f"{pre} {n}")
    custs = sorted(set(custs))
    cust_w = {c: rng.paretovariate(1.5) for c in custs}
    variant = {c: c[0].lower() + c[1:] for c in custs}  # "chị Hoa": the same customer (§3)

    def spell(c):
        return variant[c] if rng.random() < 0.15 else c

    # stock by lot, FEFO among lots not expired
    lots: dict[str, list[dict]] = defaultdict(list)
    purchases, orders, spa, payments = [], [], [], []
    demand = {c: 0.0 for c in items}
    wsum = sum(i[9] for i in PET_ITEMS)
    for it in PET_ITEMS:
        demand[it[0]] = 14 * it[9] / wsum * (1.6 if it[4] else 1.4) * (3 if it[3] in ("lon", "gói") else 1)
    pn = [0]

    def import_lines(d, codes, note=""):
        bysup = defaultdict(list)
        for c in codes:
            bysup[items[c][10]].append(c)
        for sup, cs in sorted(bysup.items()):
            pn[0] += 1
            ph = {"id": f"PN{pn[0]:04d}", "d": d, "sup": sup, "note": note, "cancelled": False, "lines": []}
            for c in cs:
                it = items[c]
                days_ = 45 if note else 35
                need = demand[c] * days_
                if it[4]:
                    q, unit, f = max(1, -(-int(need) // it[5])), it[4], it[5]
                else:
                    q, unit, f = max(2, int(need) + 1), it[3], 1
                price = half_up(it[7] * f * rng.uniform(0.95, 1.05) / 100) * 100
                exp = d + timedelta(days=rng.randint(int(it[8] * 0.45), it[8])) if it[8] else None
                ln = {"code": c, "unit": unit, "qty": q, "factor": f, "price": price, "amount": q * price, "exp": exp}
                ph["lines"].append(ln)
                lots[c].append({"ph": ph["id"], "d": d, "exp": exp, "left": q * f, "base_price": price / f})
            purchases.append(ph)

    def available(c, d):
        return sum(lt["left"] for lt in lots[c] if lt["exp"] is None or lt["exp"] >= d)

    def take(c, d, n):
        for lt in sorted((lt for lt in lots[c] if lt["exp"] is None or lt["exp"] >= d),
                         key=lambda lt: (lt["exp"] or date.max, lt["d"])):
            k = min(n, lt["left"])
            lt["left"] -= k
            n -= k
            if n == 0:
                return

    import_lines(PET_START, list(items), note="Nhập đầu kỳ")
    pets = []
    for i in range(70):
        sp = rng.choices(["Chó", "Mèo"], [62, 38])[0]
        w = round(rng.uniform(1.5, 32) if sp == "Chó" else rng.uniform(2.0, 7.5), 1)
        owner = rng.choice(custs) if rng.random() < 0.75 else None
        pets.append({"name": rng.choice(PET_PETS), "sp": sp, "w": w, "owner": owner})
    no = 0
    for d in daterange(PET_START, PET_END):
        n = rng.randint(5, 11) + (3 if d.weekday() >= 5 else 0)
        for _ in range(n):
            cust = rng.choices(custs, [cust_w[c] for c in custs])[0] if rng.random() < 0.55 else None
            r = rng.random()
            status = "cancelled" if r < 0.03 else ("returned" if r < 0.04 else "done")
            pay = "no" if cust and status == "done" and rng.random() < 0.08 else rng.choices(["cash", "ck"], [62, 38])[0]
            o = {"d": d, "cust": cust, "spelled": spell(cust) if cust else None, "status": status, "pay": pay,
                 "lines": []}
            for _ in range(rng.choices([1, 2, 3], [55, 32, 13])[0]):
                it = rng.choices(PET_ITEMS, [i[9] for i in PET_ITEMS])[0]
                if any(ln["code"] == it[0] for ln in o["lines"]):
                    continue
                big = it[4] is not None and rng.random() < (0.12 if it[3] == "lon" else 0.06)
                q = 1 if big else rng.choices([1, 2, 3, 4, 6], [50, 25, 12, 8, 5])[0] * (2 if it[3] in ("lon", "gói") else 1)
                f = it[5] if big else 1
                if available(it[0], d) < q * f:
                    continue
                price = (half_up(it[6] * f * 0.95 / 1000) * 1000) if big else it[6]
                disc = 5000 * rng.randint(1, 4) if q * price >= 200000 and rng.random() < 0.1 else 0
                o["lines"].append({"code": it[0], "unit": it[4] if big else it[3], "qty": q, "factor": f,
                                   "price": price, "disc": disc, "amount": q * price - disc})
                if status == "done":
                    take(it[0], d, q * f)
            if o["lines"]:
                no += 1
                o["id"] = f"P{no:05d}"
                orders.append(o)
                if pay == "no":
                    total = sum(ln["amount"] for ln in o["lines"])
                    r = rng.random()
                    if r < 0.7:
                        k = rng.choice([1, 1, 2])
                        part = [total] if k == 1 else [half_up(total * 0.5 / 1000) * 1000, None]
                        if k == 2:
                            part[1] = total - part[0]
                        pd = d
                        for amt in part:
                            pd = pd + timedelta(days=rng.randint(3, 40))
                            payments.append({"d": pd, "cust": o["cust"], "spelled": spell(o["cust"]), "order": o["id"],
                                             "amount": amt})
                    elif r < 0.85:
                        amt = half_up(total * rng.uniform(0.3, 0.7) / 1000) * 1000
                        payments.append({"d": d + timedelta(days=rng.randint(5, 30)), "cust": o["cust"],
                                         "spelled": spell(o["cust"]), "order": o["id"], "amount": amt})
        for _ in range(rng.randint(2, 5) + (2 if d.weekday() >= 5 else 0)):
            pet = rng.choice(pets) if rng.random() < 0.8 else {
                "name": rng.choice(PET_PETS), "sp": rng.choice(["Chó", "Mèo"]), "w": round(rng.uniform(2, 20), 1),
                "owner": None}
            svc = rng.choices(list(PET_SPA), [40, 25, 15, 20])[0]
            tier = 0 if pet["w"] < 5 else (1 if pet["w"] <= 15 else 2)
            spa.append({"d": d, "pet": pet["name"], "sp": pet["sp"], "w": pet["w"], "svc": svc,
                        "price": PET_SPA[svc][tier], "owner": pet["owner"],
                        "spelled": spell(pet["owner"]) if pet["owner"] else None, "cancelled": rng.random() < 0.03})
        low = [c for c in items if available(c, d) < demand[c] * 12 and d < PET_DISCONTINUED.get(c, date.max)]
        if low and d < PET_END:
            import_lines(d, low)
    for _ in range(max(2, len(purchases) // 50)):  # cancelled receipts: written, never received
        src = rng.choice(purchases[1:])
        pn[0] += 1
        purchases.append({**src, "id": f"PN{pn[0]:04d}", "d": src["d"] + timedelta(days=1), "note": "Huỷ phiếu",
                          "cancelled": True})
    purchases.sort(key=lambda p: (p["d"], p["id"]))
    payments = [p for p in payments if p["d"] <= PET_END]
    payments.sort(key=lambda p: (p["d"], p["order"]))

    # ---- files
    biz = out / "data" / "syn_002"
    biz.mkdir(parents=True, exist_ok=True)
    head = ["ngay", "so phieu", "ten hang", "dvt", "sl", "don gia", "giam", "thanh tien", "khach", "ghi chu"]
    note_of = {"cancelled": "huy", "returned": "khach tra lai"}
    for year in (2025, 2026):
        sheets = []
        for m in range(1, 13):
            mo = [o for o in orders if o["d"].year == year and o["d"].month == m]
            if not mo:
                continue
            rows, tot = [head], 0
            for o in mo:
                note = note_of.get(o["status"]) or {"no": "no", "ck": "ck", "cash": None}[o["pay"]]
                out_lines = list(o["lines"])
                if len(out_lines) > 1 and rng.random() < 0.01:  # export error: one line written twice (§8)
                    out_lines.insert(2, out_lines[1])
                for j, ln in enumerate(out_lines):
                    first = j == 0
                    rows.append([f"{o['d'].day}/{o['d'].month}" if first else None, o["id"], items[ln["code"]][1],
                                 ln["unit"], ln["qty"], ln["price"], ln["disc"] or None, ln["amount"],
                                 (o["spelled"] if first else None), (note if first else None)])
                    tot += ln["amount"]
            rows.append([None, None, "TONG THANG", None, None, None, None, tot, None, None])
            sheets.append((f"Thang {m}-{year}", rows))
        write_xlsx(biz / f"SoBanHang_{year}.xlsx", sheets)
    with (biz / "SoSpa.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Ngày", "Tên bé", "Loài", "Cân nặng (kg)", "Dịch vụ", "Giá", "Chủ", "Ghi chú"])
        for s in spa:
            w.writerow([f"{s['d']:%d/%m/%Y}", s["pet"], s["sp"], str(s["w"]).replace(".", ","), s["svc"], s["price"],
                        s["spelled"] or "", "huỷ - không đến" if s["cancelled"] else ""])
    prow = [["Số phiếu", "Ngày nhập", "Nhà cung cấp", "Mã hàng", "Tên hàng", "ĐVT nhập", "SL", "Giá nhập",
             "Thành tiền", "Hạn dùng", "Ghi chú"]]
    for ph in purchases:
        for ln in ph["lines"]:
            prow.append([ph["id"], f"{ph['d']:%d/%m/%Y}", ph["sup"], ln["code"], items[ln["code"]][1], ln["unit"],
                         ln["qty"], ln["price"], ln["amount"], f"{ln['exp']:%d/%m/%Y}" if ln["exp"] else None,
                         ph["note"] or None])
    write_xlsx(biz / "SoNhapHang.xlsx", [("Nhap hang", prow)])
    write_xlsx(biz / "ThuNo.xlsx", [("Thu no", [["Ngày", "Khách", "Số phiếu bán", "Số tiền"]] +
                                     [[f"{p['d']:%d/%m/%Y}", p["spelled"], p["order"], p["amount"]] for p in payments])])
    write_xlsx(biz / "DanhMuc.xlsx", [("Danh muc", [["Mã hàng", "Tên hàng", "Nhóm", "ĐVT cơ bản", "ĐVT lớn",
                                                     "Quy đổi", "Giá bán lẻ"]] +
                                       [[i[0], i[1], i[2], i[3], i[4], i[5] if i[4] else None, i[6]] for i in PET_ITEMS])])
    trow = [[f"Tồn kho theo lô đến hết {PET_END:%d/%m/%Y}"], ["Mã hàng", "Tên hàng", "Số phiếu nhập", "Ngày nhập",
                                                           "Hạn dùng", "Tồn (ĐVT cơ bản)"]]
    for c in sorted(lots):
        for lt in sorted(lots[c], key=lambda lt: lt["d"]):
            if lt["left"] > 0:
                trow.append([c, items[c][1], lt["ph"], f"{lt['d']:%d/%m/%Y}",
                             f"{lt['exp']:%d/%m/%Y}" if lt["exp"] else None, lt["left"]])
    write_xlsx(biz / "TonKho_theo_lo.xlsx", [("Ton theo lo", trow)])
    (biz / "README.md").write_text(PET_README, encoding="utf-8")

    # ---- answers
    book = Book("syn_002")
    A = book.add
    canon = {norm_name(c): c for c in custs}

    def sold(a, b, pred=lambda o, ln: True):
        return [(o, ln) for o in orders if a <= o["d"] <= b and o["status"] == "done" for ln in o["lines"]
                if pred(o, ln)]

    def sales_rev(a, b, pred=lambda o, ln: True):
        return sum(ln["amount"] for o, ln in sold(a, b, pred))

    def spa_ok(a, b):
        return [s for s in spa if a <= s["d"] <= b and not s["cancelled"]]

    def shop_rev(a, b):
        return sales_rev(a, b) + sum(s["price"] for s in spa_ok(a, b))

    def n_orders(a, b):
        return sum(1 for o in orders if a <= o["d"] <= b and o["status"] == "done")

    def debts(x):
        paid = defaultdict(int)
        for p in payments:
            if p["d"] <= x:
                paid[p["order"]] += p["amount"]
        out_ = defaultdict(int)
        for o in orders:
            if o["pay"] == "no" and o["status"] != "cancelled" and o["d"] <= x:
                left = sum(ln["amount"] for ln in o["lines"]) - paid[o["id"]]
                if left > 0:
                    out_[o["cust"]] += left
        return out_

    def aliases(c):
        return [variant[c]]

    p = month(2026, 7)
    A("Doanh thu tháng 7/2026 của cửa hàng là bao nhiêu?", date(2026, 8, 5), "number", shop_rev(*p), kind="revenue")
    A("Tháng 7/2026 sổ bán hàng thu được bao nhiêu tiền, không tính spa?", date(2026, 8, 5), "number", sales_rev(*p),
      kind="pet_sales_only")
    A("Tháng 12/2025 cửa hàng có bao nhiêu đơn?", date(2026, 1, 4), "number", n_orders(*month(2025, 12)),
      kind="order_count")
    p = month(2026, 1)
    allo = [o for o in orders if p[0] <= o["d"] <= p[1]]
    A("Tỉ lệ đơn huỷ tháng 1/2026 là bao nhiêu?", date(2026, 2, 2), "percent",
      pct(sum(o["status"] == "cancelled" for o in allo), len(allo)), kind="cancel_rate")

    def base_qty(a, b):
        s = defaultdict(int)
        for o, ln in sold(a, b):
            s[ln["code"]] += ln["qty"] * ln["factor"]
        return s

    c = top(base_qty(*month(2026, 6)))[0]
    A("Mặt hàng nào bán chạy nhất tháng 6/2026?", date(2026, 7, 1), "string", items[c][1], [c], kind="best_seller")
    t3 = top(base_qty(*quarter(2026, 2)), k=3)
    A("Top 3 mặt hàng bán chạy nhất quý 2/2026", date(2026, 7, 3), "list", [items[c][1] for c in t3],
      [[c] for c in t3], kind="best_seller")
    A("Tháng 5/2026 cửa hàng bán được bao nhiêu lon?", date(2026, 6, 2), "number",
      sum(ln["qty"] * ln["factor"] for o, ln in sold(*month(2026, 5)) if items[ln["code"]][3] == "lon"),
      kind="unit_count")

    def cust_rev(a, b):
        s = defaultdict(int)
        for o, ln in sold(a, b):
            if o["cust"]:
                s[o["cust"]] += ln["amount"]
        for x in spa_ok(a, b):
            if x["owner"]:
                s[x["owner"]] += x["price"]
        return s

    c = top(cust_rev(date(2025, 1, 1), date(2025, 12, 31)))[0]
    A("Năm 2025 khách nào mua nhiều tiền nhất?", date(2026, 1, 6), "string", c, aliases(c), kind="top_customer")
    d = date(2026, 5, 20)
    dbt = debts(d)
    A("Tính đến hôm nay khách còn nợ cửa hàng tổng cộng bao nhiêu?", d, "number", sum(dbt.values()), kind="debt_total")
    c = top(dbt)[0]
    A("Khách nào đang nợ nhiều nhất tính đến hôm nay?", d, "string", c, aliases(c), kind="debt_top")
    p = month(2026, 4)
    od = {o["id"]: o for o in orders}
    A("Tháng 4/2026 cửa hàng thu nợ được bao nhiêu tiền?", date(2026, 5, 3), "number",
      sum(x["amount"] for x in payments if p[0] <= x["d"] <= p[1] and x["d"] > od[x["order"]]["d"]
          and od[x["order"]]["status"] != "cancelled"), kind="debt_collected")
    dbt = debts(date(2026, 3, 31))
    keys = top(dbt, k=len(dbt))
    A("Bảng công nợ theo khách tính đến hết ngày 31/03/2026", date(2026, 4, 5), "table",
      {"columns": ["khach_hang", "so_tien_no"], "rows": [[k, dbt[k]] for k in keys]}, [aliases(k) for k in keys],
      kind="debt_table")
    p = month(2026, 3)
    A("Tiền nhập hàng tháng 3/2026 là bao nhiêu?", date(2026, 4, 2), "number",
      sum(ln["amount"] for ph in purchases if p[0] <= ph["d"] <= p[1] and not ph["cancelled"] for ln in ph["lines"]),
      kind="purchase_total")
    s = defaultdict(int)
    for ph in purchases:
        if ph["d"].year == 2025 and not ph["cancelled"]:
            s[ph["sup"]] += sum(ln["amount"] for ln in ph["lines"])
    A("Năm 2025 cửa hàng nhập hàng nhiều nhất từ nhà cung cấp nào?", date(2026, 1, 9), "string", top(s)[0],
      kind="top_supplier")
    pick = None
    for y_, m_ in [(2026, m) for m in range(1, 9)] + [(2025, m) for m in range(4, 13)]:
        a_, b_ = month(y_, m_)
        g = defaultdict(list)
        for ph in purchases:
            if a_ <= ph["d"] <= b_ and not ph["cancelled"]:
                for ln in ph["lines"]:
                    g[(ln["code"], ln["unit"])].append(ln)
        for (code, unit), ls in sorted(g.items()):
            if len(ls) >= 2 and len({ln["price"] for ln in ls}) > 1 and len({ln["unit"] for ln in ls}) == 1:
                pick = (y_, m_, code, ls)
                break
        if pick:
            break
    y_, m_, code, ls = pick
    A(f"Giá nhập bình quân của {items[code][1]} tháng {m_}/{y_} là bao nhiêu?", month(y_, m_)[1] + timedelta(days=3),
      "number", half_up(sum(ln["amount"] for ln in ls) / sum(ln["qty"] for ln in ls)), kind="avg_purchase_price")
    A("Doanh thu nhóm Thức ăn mèo tháng 2/2026 là bao nhiêu?", date(2026, 3, 2), "number",
      sales_rev(*month(2026, 2), lambda o, ln: items[ln["code"]][2] == "Thức ăn mèo"), kind="group_revenue")
    p = month(2026, 5)
    A("Nhóm Pate chiếm bao nhiêu % doanh thu tháng 5/2026?", date(2026, 6, 3), "percent",
      pct(sales_rev(*p, lambda o, ln: items[ln["code"]][2] == "Pate"), shop_rev(*p)), kind="group_share")
    A("Doanh thu chuyển khoản tháng 6/2026 là bao nhiêu?", date(2026, 7, 2), "number",
      sales_rev(*month(2026, 6), lambda o, ln: o["pay"] == "ck"), kind="payment_revenue")
    r7, r8 = shop_rev(*month(2026, 7)), shop_rev(*month(2026, 8))
    A("Doanh thu tháng 8/2026 tăng bao nhiêu % so với tháng 7/2026?", date(2026, 8, 31), "percent", pct(r8 - r7, r7),
      kind="growth")
    d = date(2026, 7, 15)
    a_, b_ = last_n(d, 7)
    before = {ln["code"] for o, ln in sold(PET_START, a_ - timedelta(days=1))}
    inside = {ln["code"] for o, ln in sold(a_, b_)}
    A("7 ngày gần nhất có mấy mặt hàng không bán được cái nào?", d, "number", len(before - inside), kind="unsold_count")
    p = month(2026, 3)
    A("Giá trị trung bình một đơn tháng 3/2026 là bao nhiêu?", date(2026, 4, 3), "number",
      half_up(sales_rev(*p) / n_orders(*p)), kind="avg_order")
    s = {f"2025-{m:02d}": shop_rev(*month(2025, m)) for m in range(3, 13)}
    A("Năm 2025 tháng nào doanh thu cao nhất?", date(2026, 1, 7), "date", top(s)[0], kind="which_month")
    left = sum(lt["left"] for lt in lots["TC011"])
    A("Hiện còn tồn bao nhiêu thùng Pate Whiskas cá ngừ 85g?", PET_END, "list", [left // 24, left % 24],
      kind="stock_big_unit")
    # type-specific
    A("Tháng 6/2026 có bao nhiêu lượt spa?", date(2026, 7, 1), "number", len(spa_ok(*month(2026, 6))),
      kind="pet_spa_count")
    A("Doanh thu spa quý 2/2026 là bao nhiêu?", date(2026, 7, 5), "number",
      sum(x["price"] for x in spa_ok(*quarter(2026, 2))), kind="pet_spa_revenue")
    A("Tháng 7/2026 có bao nhiêu lượt spa cho mèo?", date(2026, 8, 1), "number",
      sum(1 for x in spa_ok(*month(2026, 7)) if x["sp"] == "Mèo"), kind="pet_spa_species")
    s = Counter(x["svc"] for x in spa_ok(date(2025, 1, 1), date(2025, 12, 31)))
    A("Năm 2025 dịch vụ spa nào được làm nhiều nhất?", date(2026, 1, 8), "string", top(dict(s))[0], kind="pet_spa_rank")
    ok = spa_ok(*month(2026, 5))
    A("Tháng 5/2026 chó chiếm bao nhiêu % lượt spa?", date(2026, 6, 4), "percent",
      pct(sum(x["sp"] == "Chó" for x in ok), len(ok)), kind="pet_spa_share")
    dogs = [x["w"] for x in spa_ok(*month(2026, 4)) if x["sp"] == "Chó"]
    A("Cân nặng trung bình của các bé chó đi spa tháng 4/2026 là bao nhiêu kg?", date(2026, 5, 2), "number",
      half_up(sum(dogs) / len(dogs), 2), kind="pet_spa_weight")
    d = PET_END
    live = [(c, lt) for c in lots for lt in lots[c] if lt["left"] > 0 and lt["exp"]]
    for nn in (90, 120, 180, 270):
        soon = [(c, lt) for c, lt in live if d <= lt["exp"] <= d + timedelta(days=nn)]
        if len({c for c, _ in soon}) >= 2:
            break
    first_exp = {}
    for c, lt in soon:
        first_exp[c] = min(first_exp.get(c, date.max), lt["exp"])
    order_ = sorted(first_exp, key=lambda c: (first_exp[c], c))
    A(f"Liệt kê các mặt hàng có lô hết hạn trong {nn} ngày tới", d, "list", [items[c][1] for c in order_],
      [[c] for c in order_], kind="expiry_list")
    A(f"Tiền vốn của hàng hết hạn trong {nn} ngày tới là bao nhiêu?", d, "number",
      half_up(sum(lt["left"] * lt["base_price"] for c, lt in soon)), kind="expiry_value")
    cand = sorted(c for c in lots if len([lt for lt in lots[c] if lt["left"] > 0 and lt["exp"] and lt["exp"] >= d]) >= 2)
    c = cand[0]
    e = min(lt["exp"] for lt in lots[c] if lt["left"] > 0 and lt["exp"] and lt["exp"] >= d)
    A(f"Lô {items[c][1]} gần hết hạn nhất còn trong kho hết hạn ngày nào?", d, "date", e.isoformat(),
      kind="nearest_expiry")
    s = cust_rev(date(2025, 1, 1), date(2025, 12, 31))
    c = sorted(s, key=lambda k: -s[k])[5]
    A(f"Khách {c} năm 2025 mua tổng cộng bao nhiêu tiền, tính cả tiền spa?", date(2026, 1, 10), "number", s[c],
      kind="customer_revenue")
    d = date(2026, 6, 14)
    A("7 ngày gần nhất cửa hàng thu được bao nhiêu?", d, "number", shop_rev(*last_n(d, 7)), kind="revenue")
    d = date(2025, 11, 3)
    y = d - timedelta(days=1)
    A("Hôm qua cửa hàng bán được bao nhiêu tiền?", d, "number", shop_rev(y, y), kind="revenue")
    A("Lãi gộp tháng 5/2026 là bao nhiêu?", date(2026, 6, 3), "unanswerable", kind="unans_cost")
    A("Nhân viên nào bán được nhiều tiền nhất tháng 6/2026?", date(2026, 7, 2), "unanswerable", kind="unans_staff")
    A("Doanh thu tháng 1/2025 là bao nhiêu?", date(2026, 1, 20), "unanswerable", kind="unans_out_of_range")
    A("Doanh thu ca chiều tháng 5/2026 là bao nhiêu?", date(2026, 6, 2), "unanswerable", kind="unans_time")
    A("Tháng 6/2026 có bao nhiêu khách đăng ký thành viên mới?", date(2026, 7, 2), "unanswerable",
      kind="unans_members")
    return book


PET_README = """# Dữ liệu syn_002

Sổ bán hàng ghi tay chuyển sang Excel, mỗi năm một file, mỗi tháng một sheet (tên sheet ghi tháng và năm). Ngày trong sổ bán không ghi năm. Ngày, khách, ghi chú chỉ ghi ở dòng đầu của đơn. Dòng cuối mỗi sheet là dòng tổng tháng.
Cửa hàng thú cưng có thêm dịch vụ spa (tắm, cắt tỉa cho chó mèo), ghi ở sổ riêng.

## File
- `SoBanHang_2025.xlsx` (xlsx)
- `SoBanHang_2026.xlsx` (xlsx)
- `SoSpa.csv` (csv)
- `SoNhapHang.xlsx` (xlsx)
- `ThuNo.xlsx` (xlsx)
- `DanhMuc.xlsx` (xlsx)
- `TonKho_theo_lo.xlsx` (xlsx)

## Cột trong `SoBanHang_2025.xlsx`
- **ngay**: ngày bán
- **so phieu**: mã đơn
- **ten hang**: tên hàng
- **dvt**: đơn vị tính
- **sl**: số lượng
- **don gia**: đơn giá
- **giam**: tiền giảm của cả dòng
- **thanh tien**: thành tiền sau giảm
- **khach**: tên khách (để trống là khách lẻ)
- **ghi chu**: ghi chú của đơn

## Cột trong `SoBanHang_2026.xlsx`
- **ngay**: ngày bán
- **so phieu**: mã đơn
- **ten hang**: tên hàng
- **dvt**: đơn vị tính
- **sl**: số lượng
- **don gia**: đơn giá
- **giam**: tiền giảm của cả dòng
- **thanh tien**: thành tiền sau giảm
- **khach**: tên khách (để trống là khách lẻ)
- **ghi chu**: ghi chú của đơn

## Cột trong `SoSpa.csv`
- **Ngày**: ngày làm spa
- **Tên bé**: tên thú cưng
- **Loài**: Chó hoặc Mèo
- **Cân nặng (kg)**: cân nặng của bé
- **Dịch vụ**: dịch vụ spa
- **Giá**: tiền của lượt spa
- **Chủ**: tên khách (để trống nếu không lưu)
- **Ghi chú**: ghi chú (huỷ - không đến)

## Cột trong `SoNhapHang.xlsx`
- **Số phiếu**: mã phiếu nhập
- **Ngày nhập**: ngày nhập
- **Nhà cung cấp**: nhà cung cấp
- **Mã hàng**: mã hàng
- **Tên hàng**: tên hàng
- **ĐVT nhập**: đơn vị nhập
- **SL**: số lượng nhập
- **Giá nhập**: giá nhập một đơn vị
- **Thành tiền**: tiền nhập của cả dòng
- **Hạn dùng**: hạn sử dụng
- **Ghi chú**: ghi chú (Nhập đầu kỳ, Huỷ phiếu)

## Cột trong `ThuNo.xlsx`
- **Ngày**: thời điểm thu
- **Khách**: tên khách
- **Số phiếu bán**: mã đơn
- **Số tiền**: số tiền

## Cột trong `DanhMuc.xlsx`
- **Mã hàng**: mã hàng
- **Tên hàng**: tên hàng
- **Nhóm**: nhóm hàng
- **ĐVT cơ bản**: đơn vị cơ bản
- **ĐVT lớn**: đơn vị lớn
- **Quy đổi**: hệ số: số đơn vị cơ bản trong 1 đơn vị lớn
- **Giá bán lẻ**: giá bán hiện tại

## Cột trong `TonKho_theo_lo.xlsx`
- **Mã hàng**: mã hàng
- **Tên hàng**: tên hàng
- **Số phiếu nhập**: mã phiếu nhập
- **Ngày nhập**: ngày nhập
- **Hạn dùng**: hạn sử dụng
- **Tồn (ĐVT cơ bản)**: tồn kho

## Quy ước
- Dữ liệu có đến hết 31/08/2026.
- **Ghi chú của đơn**: huy = đơn huỷ; khach tra lai = khách trả cả đơn; no = bán nợ; ck = chuyển khoản; trống = tiền mặt.
- **Quy đổi đơn vị**: số lượng ghi theo đơn vị của dòng, hệ số quy đổi ở `DanhMuc.xlsx`.
- **Nhập hàng**: **Giá nhập** là giá nhập một đơn vị, theo đơn vị nhập của dòng; **Thành tiền** là tiền nhập của cả dòng. Phiếu ghi Huỷ phiếu không nhập.
- **Tồn kho**: `TonKho_theo_lo.xlsx` là tồn từng lô lúc hết ngày cuối có dữ liệu, theo đơn vị cơ bản.
- **Thu nợ**: các lần khách trả nợ của đơn bán nợ, theo mã đơn.
"""

RULEBOOK_6 = """### Salon tóc và spa
| Luật | Mặc định |
|---|---|
| Hoá đơn trả bằng thẻ liệu trình | buổi dùng của gói khách đã mua: **không tính vào doanh thu** (tiền gói đã tính khi bán gói). Vẫn là một hoá đơn (số hoá đơn, khách đã đến) và mỗi dòng dịch vụ vẫn là một lượt |
| Lượt dịch vụ | mỗi đơn vị số lượng của dòng **dịch vụ** (không tính dòng sản phẩm, dòng gói) trong hoá đơn tính theo §1 |
| Thợ làm nhiều nhất | theo **số lượt dịch vụ** thợ thực hiện |
| Doanh thu của thợ | doanh thu (§1) các dòng dịch vụ thợ thực hiện; dòng sản phẩm, dòng gói không tính cho thợ. Thợ giỏi nhất theo doanh thu này |
| Số buổi còn lại của gói | số buổi của gói trừ số hoá đơn thẻ liệu trình dùng gói đó, đến hết ngày hỏi |
| Khách quay lại trong kỳ | khách có **từ 2** hoá đơn (§1) trở lên trong kỳ |

### Cửa hàng thú cưng
| Luật | Mặc định |
|---|---|
| Doanh thu cửa hàng | gồm sổ bán hàng (§1) và **sổ spa** (lượt không huỷ, theo giá ghi). **Doanh thu bán hàng** chỉ sổ bán hàng, **doanh thu spa** chỉ sổ spa |
| Số đơn, giá trị trung bình một đơn, tỉ lệ huỷ, hình thức thanh toán, công nợ | chỉ theo sổ bán hàng |
| Doanh thu theo khách, xếp hạng khách | gồm tiền spa của khách (theo tên chủ) |
| Lượt spa | mỗi dòng sổ spa không huỷ là một lượt |
| Tỉ trọng nhóm hàng | mẫu số là doanh thu cửa hàng (gồm spa) |
| Hàng hết hạn trong N ngày tới, lô gần hết hạn nhất | như ngành Nhà thuốc, theo tồn từng lô |

"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "synth_private"))
    ap.add_argument("--train", default=str(ROOT / "data" / "train"), help="train split: calendar.csv, rulebook.md")
    ap.add_argument("--refund-word", default=REFUND_WORD, help="the salon's word for a refunded (returned) order")
    args = ap.parse_args(argv)
    globals()["REFUND_WORD"] = args.refund_word
    out, train = Path(args.out), Path(args.train)
    out.mkdir(parents=True, exist_ok=True)
    cal_text = (train / "calendar.csv").read_text(encoding="utf-8")
    (out / "calendar.csv").write_text(cal_text, encoding="utf-8")
    rb = (train / "rulebook.md").read_text(encoding="utf-8").replace("(bộ train)", "(bộ synth_private)")
    assert "## 7. Không trả lời được" in rb
    (out / "rulebook.md").write_text(rb.replace("## 7. Không trả lời được", RULEBOOK_6 + "## 7. Không trả lời được"),
                                     encoding="utf-8")
    cal = read_calendar(out / "calendar.csv")
    books = [gen_salon(random.Random(SEED), cal, out), gen_pet(random.Random(SEED + 1), cal, out)]
    qs = [q for b in books for q in b.q]
    ans = [a for b in books for a in b.a]
    assert len({q["id"] for q in qs}) == len(qs)
    with (out / "questions.jsonl").open("w", encoding="utf-8") as f:
        for q in qs:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    with (out / "answers.jsonl").open("w", encoding="utf-8") as f:
        for a in ans:
            f.write(json.dumps({k: a[k] for k in ("id", "type", "answer", "alias")}, ensure_ascii=False) + "\n")
    with (out / "question_kinds.json").open("w", encoding="utf-8") as f:  # kind of each question, for the report
        json.dump({a["id"]: a["kind"] for a in ans}, f, ensure_ascii=False, indent=0)
    for b in books:
        print(f"{b.biz}: {len(b.q)} questions, {Counter(a['type'] for a in b.a)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
