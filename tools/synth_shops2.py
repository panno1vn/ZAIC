"""Write data/synth2_dev/ and data/synth2_hold/: four hand-made shops of business types that are in neither train,
public nor synth_private (T013b, 13/11).

    python tools/synth_shops2.py                   # writes both splits (gitignored)
    python -m datamate.predict --data data/synth2_dev --out outputs/synth2/dev
    python -m datamate.eval.run --split synth2_dev --pred outputs/synth2/dev/submission.jsonl

Unlike tools/synth_shops.py (whose §6 rows change what revenue is), these follow the organizers' own §6 style, read
from the six business types of the train and public rulebooks: a business type adds its own measures and leaves the
general revenue of §1 alone. Questions are train's most frequent templates, in train's wording, plus two of the type.

- dev  syn_011 bookshop: one flat csv (order cells on every line), member cards; §6 speaks of revenue.
- dev  syn_012 flower shop: orders / order lines / products in three xlsx, customers by name; §6 has no revenue row.
- hold syn_021 clothes shop: sqlite, customers by code; §6 speaks of revenue.
- hold syn_022 rice shop: invoice lines in one xlsx (order cells on the first line only, title rows, total row),
  no time of day; §6 has no revenue row.

The hold split is the check of any change made after looking at dev: it is run once, after the code is frozen, and
only its counts are read. Every answer is computed here from the clean orders by the rulebook's rules.
Deterministic (fixed seeds). Development only: no organizer data is read except train's calendar and rulebook.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import synth_shops as S  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
START, END = date(2025, 1, 1), date(2026, 6, 30)


def unaccent(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def write_csv(path: Path, rows: list[list]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)


def price_on(spec: dict, it: tuple, d: date) -> int:
    since, newp = spec["price_change"].get(it[0], (None, None))
    return newp if since and d >= since else it[4]


# items: code, name, group, unit, price, weight, extra (author | None | (size, colour))
BOOK_ITEMS = [
    ("S001", "Toán 6 tập 1", "Sách giáo khoa", "cuốn", 22000, 12, "Bộ Giáo dục và Đào tạo"),
    ("S002", "Ngữ văn 7 tập 2", "Sách giáo khoa", "cuốn", 24000, 10, "Bộ Giáo dục và Đào tạo"),
    ("S003", "Tiếng Anh 8", "Sách giáo khoa", "cuốn", 45000, 8, "Bộ Giáo dục và Đào tạo"),
    ("S004", "Mắt biếc", "Văn học", "cuốn", 110000, 6, "Nguyễn Nhật Ánh"),
    ("S005", "Cho tôi xin một vé đi tuổi thơ", "Văn học", "cuốn", 80000, 7, "Nguyễn Nhật Ánh"),
    ("S006", "Tôi thấy hoa vàng trên cỏ xanh", "Văn học", "cuốn", 125000, 5, "Nguyễn Nhật Ánh"),
    ("S007", "Dế Mèn phiêu lưu ký", "Thiếu nhi", "cuốn", 60000, 8, "Tô Hoài"),
    ("S008", "Chuyện cũ Hà Nội", "Văn học", "cuốn", 135000, 3, "Tô Hoài"),
    ("S009", "Tuyển truyện tuổi học trò", "Văn học", "cuốn", 95000, 4, "Nguyễn Nhật Ánh, Lê Thị Kim"),
    ("S010", "Đắc nhân tâm", "Kỹ năng", "cuốn", 86000, 7, "Dale Carnegie"),
    ("S011", "Nhà giả kim", "Văn học", "cuốn", 79000, 7, "Paulo Coelho"),
    ("S012", "Truyện cổ tích Việt Nam", "Thiếu nhi", "cuốn", 55000, 6, "Nhiều tác giả"),
    ("V001", "Bút bi Thiên Long TL-027", "Văn phòng phẩm", "cây", 5000, 20, None),
    ("V002", "Vở kẻ ngang Campus 200 trang", "Văn phòng phẩm", "quyển", 18000, 16, None),
    ("V003", "Bút chì 2B Staedtler", "Văn phòng phẩm", "cây", 7000, 10, None),
    ("V004", "Thước kẻ 30cm", "Văn phòng phẩm", "cái", 8000, 8, None),
    ("V005", "Bìa hồ sơ A4", "Văn phòng phẩm", "cái", 6000, 6, None),
    ("V006", "Giấy A4 Double A 70gsm", "Văn phòng phẩm", "ram", 78000, 5, None),
]
FLOWER_ITEMS = [
    ("H001", "Bó hồng đỏ 20 bông", "Bó hoa", "bó", 350000, 12, None),
    ("H002", "Bó hướng dương 5 bông", "Bó hoa", "bó", 280000, 10, None),
    ("H003", "Bó baby trắng", "Bó hoa", "bó", 220000, 8, None),
    ("H004", "Bó tulip 10 bông", "Bó hoa", "bó", 550000, 4, None),
    ("H005", "Giỏ hoa sinh nhật pastel", "Giỏ hoa", "giỏ", 450000, 8, None),
    ("H006", "Giỏ lan hồ điệp mini", "Giỏ hoa", "giỏ", 650000, 4, None),
    ("H007", "Lẵng hoa khai trương 1 tầng", "Lẵng hoa", "lẵng", 900000, 4, None),
    ("H008", "Lẵng hoa khai trương 2 tầng", "Lẵng hoa", "lẵng", 1500000, 2, None),
    ("H009", "Lẵng hoa chia buồn trắng", "Lẵng hoa", "lẵng", 800000, 3, None),
    ("H010", "Chậu sen đá mix", "Chậu cây", "chậu", 120000, 7, None),
    ("H011", "Chậu lưỡi hổ để bàn", "Chậu cây", "chậu", 180000, 5, None),
    ("H012", "Chậu kim tiền", "Chậu cây", "chậu", 320000, 3, None),
    ("P001", "Thiệp viết tay", "Phụ kiện", "cái", 15000, 10, None),
    ("P002", "Gấu bông nhỏ", "Phụ kiện", "con", 90000, 4, None),
    ("P003", "Hộp socola Ferrero 8 viên", "Phụ kiện", "hộp", 160000, 3, None),
]
CLOTHES_ITEMS = [
    ("A001", "Áo thun basic cổ tròn - Trắng - M", "Áo", "cái", 150000, 12, ("M", "Trắng")),
    ("A002", "Áo thun basic cổ tròn - Đen - L", "Áo", "cái", 150000, 11, ("L", "Đen")),
    ("A003", "Áo sơ mi oxford - Xanh - M", "Áo", "cái", 320000, 7, ("M", "Xanh")),
    ("A004", "Áo sơ mi oxford - Trắng - L", "Áo", "cái", 320000, 6, ("L", "Trắng")),
    ("A005", "Áo khoác bomber - Đen - XL", "Áo", "cái", 550000, 4, ("XL", "Đen")),
    ("Q001", "Quần jean slim - Xanh - 30", "Quần", "cái", 450000, 7, ("30", "Xanh")),
    ("Q002", "Quần jean slim - Đen - 32", "Quần", "cái", 450000, 6, ("32", "Đen")),
    ("Q003", "Quần short kaki - Be - M", "Quần", "cái", 220000, 6, ("M", "Be")),
    ("Q004", "Quần tây âu - Đen - 31", "Quần", "cái", 390000, 4, ("31", "Đen")),
    ("V001", "Váy hoa nhí - Vàng - S", "Váy", "cái", 380000, 5, ("S", "Vàng")),
    ("V002", "Váy suông công sở - Đen - M", "Váy", "cái", 420000, 4, ("M", "Đen")),
    ("V003", "Chân váy xếp ly - Trắng - S", "Váy", "cái", 260000, 5, ("S", "Trắng")),
    ("G001", "Giày sneaker cổ thấp - Trắng - 40", "Giày dép", "đôi", 620000, 4, ("40", "Trắng")),
    ("G002", "Dép quai ngang - Đen - 41", "Giày dép", "đôi", 180000, 5, ("41", "Đen")),
    ("P001", "Thắt lưng da - Nâu", "Phụ kiện", "cái", 240000, 4, (None, "Nâu")),
    ("P002", "Mũ lưỡi trai - Đen", "Phụ kiện", "cái", 120000, 6, (None, "Đen")),
    ("P003", "Tất cổ ngắn", "Phụ kiện", "đôi", 25000, 8, (None, None)),
]
RICE_ITEMS = [
    ("G001", "Gạo ST25", "Gạo", "kg", 32000, 14, None),
    ("G002", "Gạo Jasmine", "Gạo", "kg", 19000, 14, None),
    ("G003", "Gạo Nàng Hoa", "Gạo", "kg", 22000, 10, None),
    ("G004", "Gạo tấm thơm", "Gạo", "kg", 17000, 8, None),
    ("G005", "Gạo lứt đỏ", "Gạo", "kg", 30000, 5, None),
    ("G006", "Gạo ST25 túi 5kg", "Gạo", "túi", 165000, 6, None),
    ("N001", "Nếp cái hoa vàng", "Nếp", "kg", 34000, 7, None),
    ("N002", "Nếp than", "Nếp", "kg", 40000, 3, None),
    ("D001", "Đậu xanh cà vỏ", "Đậu - hạt", "kg", 55000, 5, None),
    ("D002", "Đậu phộng", "Đậu - hạt", "kg", 60000, 4, None),
    ("D003", "Mè trắng", "Đậu - hạt", "kg", 90000, 2, None),
    ("D004", "Hạt sen khô", "Đậu - hạt", "kg", 180000, 2, None),
    ("M001", "Nước mắm Phú Quốc 40 độ 500ml", "Gia vị", "chai", 85000, 5, None),
    ("M002", "Muối hồng Himalaya 500g", "Gia vị", "hũ", 45000, 3, None),
    ("M003", "Dầu ăn Tường An 1L", "Gia vị", "chai", 52000, 6, None),
]


# ------------------------------------------------------------------------------------------------ orders
def simulate(spec: dict) -> list[dict]:
    rng = random.Random(spec["seed"])
    seen: set[str] = set()
    custs = []
    while len(custs) < spec["n_cust"]:
        name = f"{rng.choice(S.VN_HO)} {rng.choice(S.VN_DEM)} {rng.choice(S.VN_TEN)}"
        if name in seen:
            continue
        seen.add(name)
        custs.append({"code": f"{spec['cust_prefix']}{len(custs) + 1:04d}", "name": name,
                      "phone": f"09{rng.randint(10000000, 99999999)}",
                      # capped: in train the busiest real customer has 0.6 % of a shop's orders at most
                      "reg": START - timedelta(days=rng.randint(1, 300)), "w": min(rng.paretovariate(1.5), 3.0)})
    spec["custs"] = custs
    orders = []
    for d in S.daterange(START, END):
        for _ in range(rng.randint(*spec["per_day"]) + (spec["weekend"] if d.weekday() >= 5 else 0)):
            dt = datetime(d.year, d.month, d.day, rng.randint(7, 21), rng.randrange(60))
            cust = rng.choices(custs, [c["w"] for c in custs])[0] if rng.random() < spec["known_rate"] else None
            pool, lines = list(spec["items"]), []
            for _ in range(rng.choices([1, 2, 3, 4], spec["basket"])[0]):
                it = rng.choices(pool, [p[5] for p in pool])[0]
                pool.remove(it)
                qty = rng.choice(spec["qty"](it))
                price = price_on(spec, it, d)
                disc = (S.half_up(qty * price * 0.05 / 1000) * 1000
                        if spec["line_disc"] and cust and rng.random() < 0.3 else 0)
                lines.append({"code": it[0], "name": it[1], "group": it[2], "unit": it[3], "qty": qty, "price": price,
                              "disc": disc, "amount": qty * price - disc, "x": it[6]})
            r = rng.random()
            status = "cancel" if r < 0.03 else "refund" if r < 0.05 else "done"
            if status == "done" and spec["shipping"] and d > END - timedelta(days=3) and rng.random() < 0.4:
                status = "ship"
            o = {"dt": dt, "d": d, "cust": cust, "lines": lines, "status": status,
                 "pay": rng.choices([p for p, _ in spec["pays"]], [w for _, w in spec["pays"]])[0],
                 "voucher": rng.choice([20000, 50000]) if spec["voucher"] and rng.random() < 0.05 else 0,
                 "ship_d": d + timedelta(days=rng.choice([0, 0, 0, 1, 1, 2])), "fee": rng.choice([0, 0, 20000, 30000]),
                 "occasion": rng.choices(["Sinh nhật", "Khai trương", "Chia buồn", "Tình yêu", None],
                                         [30, 12, 8, 20, 30])[0]}
            orders.append(o)
    orders.sort(key=lambda o: o["dt"])
    for i, o in enumerate(orders, 1):
        o["id"] = f"{spec['order_prefix']}{i:06d}"
    return orders


# ------------------------------------------------------------------------------------------------ files
def write_books(spec: dict, orders: list[dict], biz: Path) -> None:
    st = spec["status"]
    rows = [["Số chứng từ", "Thời gian", "Mã thẻ", "Tên khách", "Mã hàng", "Tên hàng", "ĐVT", "Số lượng", "Đơn giá",
             "Giảm giá", "Thành tiền", "Thanh toán", "Trạng thái"]]
    for o in orders:
        for ln in o["lines"]:
            rows.append([o["id"], f"{o['dt']:%d/%m/%Y %H:%M}", o["cust"]["code"] if o["cust"] else "",
                         o["cust"]["name"] if o["cust"] else "Khách lẻ", ln["code"], ln["name"], ln["unit"], ln["qty"],
                         ln["price"], ln["disc"], ln["amount"], o["pay"], st[o["status"]]])
    write_csv(biz / "ban_hang.csv", rows)
    write_csv(biz / "danh_muc.csv", [["Mã hàng", "Tên hàng", "Nhóm hàng", "ĐVT", "Tác giả", "Giá bìa"]] +
              [[it[0], it[1], it[2], it[3], it[6] or "", price_on(spec, it, END)] for it in spec["items"]])
    write_csv(biz / "the_thanh_vien.csv", [["Mã thẻ", "Họ tên", "SĐT", "Ngày đăng ký"]] +
              [[c["code"], c["name"], c["phone"], f"{c['reg']:%d/%m/%Y}"] for c in spec["custs"]])


def write_flowers(spec: dict, orders: list[dict], biz: Path) -> None:
    st = spec["status"]
    head = [["Mã đơn", "Thời gian đặt", "Ngày giao", "Khách hàng", "SĐT", "Dịp", "Phí giao", "Giảm giá đơn",
             "Thanh toán", "Trạng thái"]]
    det = [["Mã đơn", "Mã SP", "Tên sản phẩm", "ĐVT", "SL", "Đơn giá", "Thành tiền"]]
    for o in orders:
        head.append([o["id"], f"{o['dt']:%d/%m/%Y %H:%M}", f"{o['ship_d']:%d/%m/%Y}",
                     o["cust"]["name"] if o["cust"] else "Khách lẻ", o["cust"]["phone"] if o["cust"] else None,
                     o["occasion"], o["fee"] or None, o["voucher"] or None, o["pay"], st[o["status"]]])
        for ln in o["lines"]:
            det.append([o["id"], ln["code"], ln["name"], ln["unit"], ln["qty"], ln["price"], ln["amount"]])
    S.write_xlsx(biz / "DonHang.xlsx", [("Đơn hàng", head)])
    S.write_xlsx(biz / "ChiTietDon.xlsx", [("Chi tiết đơn", det)])
    S.write_xlsx(biz / "SanPham.xlsx", [("Sản phẩm", [["Mã SP", "Tên sản phẩm", "Loại", "ĐVT", "Giá bán"]] +
                                         [[it[0], it[1], it[2], it[3], price_on(spec, it, END)] for it in spec["items"]])])


def write_clothes(spec: dict, orders: list[dict], biz: Path) -> None:
    st = spec["status"]
    con = sqlite3.connect(biz / "pos.sqlite")
    con.executescript("""
        create table khach_hang (MaKH text primary key, TenKH text, SoDienThoai text, NgayDangKy text);
        create table san_pham (MaSP text primary key, TenSP text, NhomHang text, Size text, Mau text, DonViTinh text,
                               GiaBan integer);
        create table don_hang (MaDon text primary key, ThoiGian text, MaKH text, HinhThucTT text, GiamGiaDon integer,
                               TrangThai text);
        create table chi_tiet_don (MaDon text, MaSP text, SoLuong integer, DonGia integer, ThanhTien integer);
    """)
    con.executemany("insert into khach_hang values (?, ?, ?, ?)",
                    [(c["code"], c["name"], c["phone"], c["reg"].isoformat()) for c in spec["custs"]])
    con.executemany("insert into san_pham values (?, ?, ?, ?, ?, ?, ?)",
                    [(it[0], it[1], it[2], it[6][0], it[6][1], it[3], price_on(spec, it, END)) for it in spec["items"]])
    con.executemany("insert into don_hang values (?, ?, ?, ?, ?, ?)",
                    [(o["id"], f"{o['dt']:%Y-%m-%d %H:%M:%S}", o["cust"]["code"] if o["cust"] else None, o["pay"],
                      o["voucher"], st[o["status"]]) for o in orders])
    con.executemany("insert into chi_tiet_don values (?, ?, ?, ?, ?)",
                    [(o["id"], ln["code"], ln["qty"], ln["price"], ln["amount"]) for o in orders for ln in o["lines"]])
    con.commit()
    con.close()


def write_rice(spec: dict, orders: list[dict], biz: Path) -> None:
    st = spec["status"]
    rows = [["BẢNG KÊ CHI TIẾT HOÁ ĐƠN BÁN HÀNG"], [f"Từ ngày {START:%d/%m/%Y} đến ngày {END:%d/%m/%Y}"], [],
            ["Số HĐ", "Ngày", "Khách hàng", "Tên hàng", "ĐVT", "Số lượng", "Đơn giá", "Thành tiền", "HTTT",
             "Tình trạng"]]
    tq = ta = 0
    for o in orders:
        for j, ln in enumerate(o["lines"]):
            f = j == 0
            rows.append([o["id"], f"{o['d']:%d/%m/%Y}" if f else None,
                         (o["cust"]["name"] if o["cust"] else "Khách lẻ") if f else None, ln["name"], ln["unit"],
                         ln["qty"], ln["price"], ln["amount"], o["pay"] if f else None, st[o["status"]] if f else None])
            tq += ln["qty"]
            ta += ln["amount"]
    rows.append(["Tổng cộng", None, None, None, None, tq, None, ta])
    S.write_xlsx(biz / "DanhSachHoaDonChiTiet.xlsx", [("Chi tiết HĐ", rows)])
    S.write_xlsx(biz / "DanhSachSanPham.xlsx", [("Sản phẩm", [["Mã hàng", "Tên hàng", "Nhóm", "ĐVT", "Giá bán lẻ"]] +
                                                 [[it[0], it[1], it[2], it[3], price_on(spec, it, END)]
                                                  for it in spec["items"]])])


README_BOOKS = """# Dữ liệu syn_011

File xuất từ phần mềm bán hàng của nhà sách. Sổ bán hàng là một file phẳng, mỗi dòng một bản ghi (một dòng hàng trong đơn), thông tin đơn lặp lại ở mọi dòng của đơn.

## File
- `ban_hang.csv` (csv)
- `danh_muc.csv` (csv)
- `the_thanh_vien.csv` (csv)

## Cột trong `ban_hang.csv`
- **Số chứng từ**: mã đơn
- **Thời gian**: thời điểm đặt đơn
- **Mã thẻ**: mã khách
- **Tên khách**: tên khách (Khách lẻ nếu không lưu)
- **Mã hàng**: mã hàng
- **Tên hàng**: tên hàng
- **ĐVT**: đơn vị tính
- **Số lượng**: số lượng
- **Đơn giá**: đơn giá
- **Giảm giá**: tiền giảm của cả dòng
- **Thành tiền**: thành tiền sau giảm
- **Thanh toán**: hình thức thanh toán của đơn
- **Trạng thái**: trạng thái đơn

## Cột trong `danh_muc.csv`
- **Mã hàng**: mã hàng
- **Tên hàng**: tên hàng
- **Nhóm hàng**: nhóm hàng
- **ĐVT**: đơn vị cơ bản
- **Tác giả**: tác giả của sách (văn phòng phẩm để trống)
- **Giá bìa**: giá bán hiện tại

## Cột trong `the_thanh_vien.csv`
- **Mã thẻ**: mã khách
- **Họ tên**: tên khách
- **SĐT**: số điện thoại
- **Ngày đăng ký**: ngày đăng ký

## Quy ước
- Dữ liệu có đến hết 30/06/2026.
- **Trạng thái đơn**: Hoàn thành, Đã huỷ, Trả hàng.
"""
README_FLOWERS = """# Dữ liệu syn_012

File Excel xuất từ phần mềm bán hàng của cửa hàng hoa tươi, mỗi danh sách một file. Mã đơn nối `DonHang.xlsx` với `ChiTietDon.xlsx`. Ngày dạng dd/mm/yyyy.

## File
- `DonHang.xlsx` (xlsx)
- `ChiTietDon.xlsx` (xlsx)
- `SanPham.xlsx` (xlsx)

## Cột trong `DonHang.xlsx`
- **Mã đơn**: mã đơn
- **Thời gian đặt**: thời điểm đặt đơn
- **Ngày giao**: ngày giao hoa
- **Khách hàng**: tên khách (Khách lẻ nếu không lưu)
- **SĐT**: số điện thoại
- **Dịp**: dịp tặng hoa khách ghi khi đặt (để trống nếu không ghi)
- **Phí giao**: phí giao hàng
- **Giảm giá đơn**: tiền bớt cho cả đơn
- **Thanh toán**: hình thức thanh toán của đơn
- **Trạng thái**: trạng thái đơn

## Cột trong `ChiTietDon.xlsx`
- **Mã đơn**: mã đơn
- **Mã SP**: mã hàng
- **Tên sản phẩm**: tên hàng
- **ĐVT**: đơn vị tính
- **SL**: số lượng
- **Đơn giá**: đơn giá
- **Thành tiền**: thành tiền sau giảm

## Cột trong `SanPham.xlsx`
- **Mã SP**: mã hàng
- **Tên sản phẩm**: tên hàng
- **Loại**: nhóm hàng
- **ĐVT**: đơn vị cơ bản
- **Giá bán**: giá bán hiện tại

## Quy ước
- Dữ liệu có đến hết 30/06/2026.
- **Trạng thái đơn**: Đã giao, Đã huỷ, Trả hàng, Đang giao.
"""
README_CLOTHES = """# Dữ liệu syn_021

File máy POS của shop thời trang xuất ra.

## File
- `pos.sqlite` (sqlite)

## Bảng
`khach_hang`, `san_pham`, `don_hang`, `chi_tiet_don`

Mã đơn nối `don_hang` với `chi_tiet_don`. Ngày giờ dạng text.

## Quy ước
- Dữ liệu có đến hết 30/06/2026.
- **Dòng hàng**: `chi_tiet_don.ThanhTien` là thành tiền của dòng (đã trừ giảm giá dòng).
- **Giảm giá đơn**: `don_hang.GiamGiaDon` là tiền bớt cho cả đơn.
- **Trạng thái đơn**: Hoàn thành, Đã huỷ, Trả hàng, Đang giao.
- **Size, màu**: `san_pham.Size`, `san_pham.Mau`; phụ kiện không có size thì để trống.
"""
README_RICE = """# Dữ liệu syn_022

File Excel xuất từ phần mềm bán hàng của cửa hàng gạo, mỗi danh sách một file. Chi tiết hoá đơn: mỗi dòng một dòng hàng; thông tin đơn chỉ ghi ở dòng đầu của đơn. Ba dòng đầu sheet là tiêu đề báo cáo, dòng cuối là dòng tổng. Ngày dạng dd/mm/yyyy.

## File
- `DanhSachHoaDonChiTiet.xlsx` (xlsx)
- `DanhSachSanPham.xlsx` (xlsx)

## Cột trong `DanhSachHoaDonChiTiet.xlsx`
- **Số HĐ**: mã đơn
- **Ngày**: ngày bán
- **Khách hàng**: tên khách (Khách lẻ nếu không lưu)
- **Tên hàng**: tên hàng
- **ĐVT**: đơn vị tính
- **Số lượng**: số lượng
- **Đơn giá**: đơn giá
- **Thành tiền**: thành tiền sau giảm
- **HTTT**: hình thức thanh toán của đơn
- **Tình trạng**: trạng thái đơn

## Cột trong `DanhSachSanPham.xlsx`
- **Mã hàng**: mã hàng
- **Tên hàng**: tên hàng
- **Nhóm**: nhóm hàng
- **ĐVT**: đơn vị cơ bản
- **Giá bán lẻ**: giá bán hiện tại

## Quy ước
- Dữ liệu có đến hết 30/06/2026.
- **Trạng thái đơn**: Đã bán, Huỷ, Trả hàng.
"""

RULE_BOOKS = """### Nhà sách
| Luật | Mặc định |
|---|---|
| Sách của một tác giả | sách ghi **đúng** tên tác giả đó ở cột Tác giả của danh mục. Sách ghi nhiều tác giả là **một loại riêng**, không tính cho từng tác giả trong đó. Doanh thu theo tác giả là doanh thu (§1) của các sách đó |
| Số cuốn bán ra | cộng số lượng các mặt hàng có đơn vị tính là cuốn; vở, giấy không phải sách |

"""
RULE_FLOWERS = """### Cửa hàng hoa
| Luật | Mặc định |
|---|---|
| Đơn giao trong ngày | đơn có **ngày giao** trùng ngày đặt; đếm theo §1 (bỏ đơn huỷ, đơn trả) |
| Đơn theo dịp | theo cột Dịp ghi trên đơn; đơn để trống cột Dịp không thuộc dịp nào |

"""
RULE_CLOTHES = """### Cửa hàng thời trang
| Luật | Mặc định |
|---|---|
| Size, màu | lấy theo cột Size, Màu của danh mục hàng, không theo tên hàng; hàng để trống cột Size thì không xếp vào size nào |
| Tỉ trọng của một size, một màu | tính theo **doanh thu** (§1), chia cho doanh thu cả shop cùng kỳ |
| Size bán chạy nhất | theo số lượng (§3) |

"""
RULE_RICE = """### Cửa hàng gạo
| Luật | Mặc định |
|---|---|
| Gạo, nếp | **Gạo** là hàng thuộc nhóm `Gạo`; nếp là nhóm riêng, không tính vào gạo |
| Số ký bán ra | cộng số lượng các mặt hàng có đơn vị tính là kg; hàng đóng túi, đóng chai không quy ra kg |

"""

BASE = {"weekend": 4, "basket": [50, 30, 15, 5], "qty": lambda it: [1, 1, 1, 2, 2, 3], "line_disc": False,
        "shipping": False, "voucher": False, "codes": True, "has_time": True, "noun": "cửa hàng"}
SHOPS = [
    {**BASE, "biz": "syn_011", "split": "dev", "seed": 20261113, "items": BOOK_ITEMS, "per_day": (20, 32),
     "pays": [("Tiền mặt", 60), ("Chuyển khoản", 30), ("Thẻ", 10)], "known_rate": 0.45, "n_cust": 180,
     "cust_prefix": "TV", "order_prefix": "BH", "line_disc": True, "noun": "nhà sách",
     "status": {"done": "Hoàn thành", "cancel": "Đã huỷ", "refund": "Trả hàng"},
     "price_change": {"S005": (date(2025, 10, 1), 85000)}, "write": write_books, "readme": README_BOOKS,
     "rule6": RULE_BOOKS, "two_pays": ("chuyển khoản", "thẻ")},
    {**BASE, "biz": "syn_012", "split": "dev", "seed": 20261114, "items": FLOWER_ITEMS, "per_day": (8, 14),
     "pays": [("Tiền mặt", 35), ("Chuyển khoản", 45), ("COD", 20)], "known_rate": 0.6, "n_cust": 150,
     "cust_prefix": "KH", "order_prefix": "DH", "shipping": True, "voucher": True, "codes": False,
     "basket": [70, 22, 6, 2], "qty": lambda it: [1, 1, 1, 1, 2],
     "status": {"done": "Đã giao", "cancel": "Đã huỷ", "refund": "Trả hàng", "ship": "Đang giao"},
     "price_change": {"H001": (date(2026, 1, 15), 380000)}, "write": write_flowers, "readme": README_FLOWERS,
     "rule6": RULE_FLOWERS, "two_pays": ("COD", "chuyển khoản")},
    {**BASE, "biz": "syn_021", "split": "hold", "seed": 20261115, "items": CLOTHES_ITEMS, "per_day": (10, 18),
     "pays": [("Tiền mặt", 40), ("Chuyển khoản", 40), ("Ví điện tử", 20)], "known_rate": 0.55, "n_cust": 200,
     "cust_prefix": "KH", "order_prefix": "DH", "shipping": True, "voucher": True, "noun": "shop",
     "status": {"done": "Hoàn thành", "cancel": "Đã huỷ", "refund": "Trả hàng", "ship": "Đang giao"},
     "price_change": {"A005": (date(2025, 11, 1), 590000)}, "write": write_clothes, "readme": README_CLOTHES,
     "rule6": RULE_CLOTHES, "two_pays": ("ví điện tử", "chuyển khoản")},
    {**BASE, "biz": "syn_022", "split": "hold", "seed": 20261116, "items": RICE_ITEMS, "per_day": (12, 20),
     "pays": [("Tiền mặt", 70), ("Chuyển khoản", 30)], "known_rate": 0.5, "n_cust": 90,
     "cust_prefix": "KH", "order_prefix": "HD", "codes": False, "has_time": False,
     "qty": lambda it: [1, 2, 2, 3, 5, 5, 10, 25] if it[3] == "kg" else [1, 1, 2],
     "status": {"done": "Đã bán", "cancel": "Huỷ", "refund": "Trả hàng"},
     "price_change": {"G001": (date(2026, 2, 1), 34000)}, "write": write_rice, "readme": README_RICE,
     "rule6": RULE_RICE, "two_pays": ("tiền mặt", "chuyển khoản")},
]


# ------------------------------------------------------------------------------------------------ questions
def questions(spec: dict, orders: list[dict], cal: list[dict]) -> S.Book:
    book = S.Book(spec["biz"])
    A, shop, q = book.add, spec["noun"], random.Random(spec["seed"] + 1000)
    items = {it[0]: it for it in spec["items"]}
    months = [(2025 + i // 12, i % 12 + 1) for i in range(1, 17)]  # 2/2025 .. 5/2026

    def M():
        y, m = q.choice(months)
        p = S.month(y, m)
        return y, m, p, p[1] + timedelta(days=5)

    def day() -> date:
        return START + timedelta(days=q.randint(60, (END - START).days - 5))

    def counted(a, b):
        return [o for o in orders if a <= o["d"] <= b and o["status"] in ("done", "ship")]

    def rev(a, b, pred=lambda ln, o: True):
        return sum(ln["amount"] for o in counted(a, b) for ln in o["lines"] if pred(ln, o))

    def by(a, b, key, val=lambda ln: ln["amount"]):
        s: dict = defaultdict(int)
        for o in counted(a, b):
            for ln in o["lines"]:
                k = key(ln, o)
                if k is not None:
                    s[k] += val(ln)
        return s

    def qty(ln):
        return ln["qty"]

    def code(ln, o):
        return ln["code"]

    ck = "code" if spec["codes"] else "name"

    def cust(ln, o):
        return o["cust"][ck] if o["cust"] else None

    cname = {c[ck]: c["name"] for c in spec["custs"]}

    y, m, p, asof = M()
    A(f"Cho tôi biết doanh thu tháng {m}/{y}.", asof, "number", rev(*p), kind="revenue")
    y, m, p, asof = M()
    A(f"Tháng {m}/{y} {shop} bán được tổng cộng bao nhiêu tiền?", asof, "number", rev(*p), kind="revenue")
    d = day()
    A("Hôm nay bán được mấy đơn hàng?", d, "number", len(counted(d, d)), kind="order_count")
    d = day()
    A("hôm qua dthu được bn", d, "number", rev(d - timedelta(days=1), d - timedelta(days=1)), kind="revenue")
    y, m, p, asof = M()
    placed = [o for o in orders if p[0] <= o["d"] <= p[1]]
    A(f"Tháng {m}/{y} bị huỷ mấy đơn nhỉ?", asof, "number", sum(o["status"] == "cancel" for o in placed),
      kind="cancel_count")
    y, m, p, asof = M()
    placed = [o for o in orders if p[0] <= o["d"] <= p[1]]
    A(f"xem giúp tháng {m}/{y} {shop} có bnhiu % đơn bị huỷ vậy", asof, "percent",
      S.pct(sum(o["status"] == "cancel" for o in placed), len(placed)), kind="cancel_rate")
    d = day()
    c = S.top(by(*S.prev_week(d), code, qty))[0]
    A("Mặt hàng bán chạy nhất tuần rồi là mặt hàng nào?", d, "string", items[c][1], [c], kind="best_seller")
    y, m, p, asof = M()
    t3 = S.top(by(*p, cust), k=3)
    A(f"Top 3 khách hàng mua nhiều tiền nhất tháng {m}/{y} là ai ạ?", asof, "list", [cname[k] for k in t3],
      [[k] for k in t3] if spec["codes"] else None, kind="top_customer")
    y, m, p, asof = M()
    c = S.top(by(*p, cust))[0]
    A(f"thang {m}/{y} ai mua hang nhiu tien nhat", asof, "string", cname[c], [c] if spec["codes"] else None,
      kind="top_customer")
    y, m, p, asof = M()
    A(f"Tháng {m}/{y} dthu bình quân mỗi đơn là bao nhiêu?", asof, "number",
      S.half_up(rev(*p) / len(counted(*p))), kind="avg_order")
    groups = sorted({it[2] for it in spec["items"]})
    y, m, p, asof = M()
    g = q.choice(groups)
    A(f"dthu nhóm hàng {g.lower()} tháng {m} năm {y} là bao nhiêu?", asof, "number",
      rev(*p, lambda ln, o: ln["group"] == g), kind="group_revenue")
    y, m, p, asof = M()
    g = q.choice(groups)
    A(f"Tỉ trọng của nhóm {g.lower()} trong dthu tháng {m}/{y} là bao nhiêu %?", asof, "percent",
      S.pct(rev(*p, lambda ln, o: ln["group"] == g), rev(*p)), kind="group_share")
    y, m, p, asof = M()
    prev = S.month(*((y, m - 1) if m > 1 else (y - 1, 12)))
    A(f"Tháng {m}/{y} doanh thu thay đổi bao nhiêu % so với tháng liền trước?", asof, "percent",
      S.pct(rev(*p) - rev(*prev), rev(*prev)), kind="growth")
    y, m, p, asof = M()
    s = by(*p, lambda ln, o: o["d"])
    A(f"thang {m}/{y} ngay nao cua hang ban dc nhieu tien nhat", asof, "date", S.top(s)[0].isoformat(),
      kind="which_day")
    i = q.randint(0, len(months) - 3)
    three = months[i:i + 3]
    s = {f"{yy}-{mm:02d}": rev(*S.month(yy, mm)) for yy, mm in three}
    A("thang nao doanh thu cao nhat trong ba thang " + ", ".join(f"{mm}/{yy}" for yy, mm in three),
      S.month(*three[-1])[1] + timedelta(days=5), "date", S.top(s)[0], kind="which_month")
    y, m, p, asof = M()
    y2, m2, p2, asof2 = M()
    if spec["has_time"]:
        A(f"dthu ca chieu thang {m}/{y} la bn", asof, "number", rev(*p, lambda ln, o: 14 <= o["dt"].hour <= 21),
          kind="shift")
        am, pm = (rev(*p2, lambda ln, o: 6 <= o["dt"].hour <= 13), rev(*p2, lambda ln, o: 14 <= o["dt"].hour <= 21))
        A(f"Xem giúp tháng {m2}/{y2}, doanh thu ca chiều tăng hay giảm bao nhiêu % so với ca sáng?", asof2, "percent",
          S.pct(pm - am, am), kind="shift")
    else:  # no time of day in the files (§7)
        A(f"dthu ca chieu thang {m}/{y} la bn", asof, "unanswerable", kind="unans_shift")
    d = day().replace(day=q.randint(12, 26))
    mtd = (d.replace(day=1), d)
    A("Doanh thu các đơn trả bằng tiền mặt tháng này bằng bao nhiêu % tổng doanh thu tháng này?", d, "percent",
      S.pct(rev(*mtd, lambda ln, o: o["pay"] == "Tiền mặt"), rev(*mtd)), kind="payment_share")
    d = day().replace(day=q.randint(12, 26))
    mtd = (d.replace(day=1), d)
    p1, p2n = spec["two_pays"]
    A(f"Tháng này, doanh thu các đơn trả bằng {p1} là bao nhiêu, doanh thu các đơn trả bằng {p2n} là bao nhiêu?", d,
      "list", [rev(*mtd, lambda ln, o, w=w: o["pay"].lower() == w.lower()) for w in (p1, p2n)], kind="payment_revenue")
    d = day().replace(day=q.randint(12, 26))
    last = d.replace(day=1) - timedelta(days=1)
    cur, old = rev(d.replace(day=1), d), rev(last.replace(day=1), last.replace(day=min(d.day, last.day)))
    A("Doanh thu từ đầu tháng này đến hết hôm nay tăng hay giảm bao nhiêu phần trăm so với cùng kỳ tháng trước?", d,
      "percent", S.pct(cur - old, old), kind="mtd_growth")
    y, m, p, asof = M()
    totals = sorted(sum(ln["amount"] for ln in o["lines"]) for o in counted(*p))
    n = max(10000, S.half_up(totals[len(totals) // 2] / 10000) * 10000)
    A(f"Đếm số đơn hàng tháng {m}/{y} có tiền hàng từ {n:,} đồng trở lên.".replace(",", "."), asof, "number",
      sum(t >= n for t in totals), kind="order_filter")
    y, m, p, asof = M()
    per = Counter(c for o in counted(*p) for c in {ln["code"] for ln in o["lines"]})
    k = sorted(per.values())[len(per) // 2]
    A(f"Tháng {m}/{y} có mấy mặt hàng được mua ở {k} đơn khác nhau trở lên?", asof, "number",
      sum(v >= k for v in per.values()), kind="item_orders")
    y, m, p, asof = M()
    it = q.choice(spec["items"][:8])
    A(f"thang {m}/{y} mat hang {unaccent(it[1]).lower()} thu ve bao nhieu tien", asof, "number",
      rev(*p, lambda ln, o: ln["code"] == it[0]), kind="item_revenue")
    y, m, p, asof = M()
    it = q.choice(spec["items"][:8])
    A(f"Tháng {m}/{y} bán ra bao nhiêu {it[3]} {it[1]} vậy?", asof, "number",
      by(*p, code, qty).get(it[0], 0), kind="item_qty")
    pc, (since, newp) = next(iter(spec["price_change"].items()))
    dd = min(o["d"] for o in orders if o["d"] >= since + timedelta(days=3) and any(ln["code"] == pc for ln in o["lines"]))
    A(f"gia ban mot {unaccent(items[pc][3])} {unaccent(items[pc][1]).lower()} vao ngay {dd:%d/%m/%Y} la bn",
      dd + timedelta(days=10), "number", newp, kind="price_on_day")
    d = day()
    pw = S.prev_week(d)
    A("Tuần trước doanh thu bình quân mỗi đơn hàng là bao nhiêu?", d, "number",
      S.half_up(rev(*pw) / len(counted(*pw))), kind="avg_order")
    c = S.top(by(*S.tet_range(2026, cal), code, qty))[0]
    A("Dịp Tết 2026, mặt hàng nào bán chạy nhất ạ?", date(2026, 3, 5), "string", items[c][1], [c], kind="tet")

    # the business type's own measures (§6)
    y, m, p, asof = M()
    y2, m2, p2, asof2 = M()
    if spec["biz"] == "syn_011":
        A(f"Doanh thu sách của tác giả Nguyễn Nhật Ánh tháng {m}/{y} là bao nhiêu?", asof, "number",
          rev(*p, lambda ln, o: ln["x"] == "Nguyễn Nhật Ánh"), kind="ind_author_revenue")
        A(f"Tháng {m2}/{y2} nhà sách bán được bao nhiêu cuốn sách của tác giả Tô Hoài?", asof2, "number",
          sum(by(*p2, lambda ln, o: ln["code"] if ln["x"] == "Tô Hoài" else None, qty).values()), kind="ind_author_qty")
    elif spec["biz"] == "syn_012":
        A(f"Tháng {m}/{y} có bao nhiêu đơn giao trong ngày?", asof, "number",
          sum(o["ship_d"] == o["d"] for o in counted(*p)), kind="ind_same_day")
        A(f"Tháng {m2}/{y2} có bao nhiêu đơn hoa dịp sinh nhật?", asof2, "number",
          sum(o["occasion"] == "Sinh nhật" for o in counted(*p2)), kind="ind_occasion")
    elif spec["biz"] == "syn_021":
        A(f"Tháng {m}/{y} size nào bán chạy nhất?", asof, "string", S.top(by(*p, lambda ln, o: ln["x"][0], qty))[0],
          kind="ind_size_best")
        A(f"Hàng màu đen chiếm bao nhiêu % doanh thu tháng {m2}/{y2}?", asof2, "percent",
          S.pct(rev(*p2, lambda ln, o: ln["x"][1] == "Đen"), rev(*p2)), kind="ind_colour_share")
    else:
        A(f"so kg nep cai hoa vang ban duoc trong thang {m}/{y} la bao nhieu nhi", asof, "number",
          by(*p, code, qty).get("N001", 0), kind="ind_kg_item")
        A(f"Tháng {m2}/{y2} cửa hàng bán được tổng cộng bao nhiêu kg gạo?", asof2, "number",
          sum(by(*p2, lambda ln, o: ln["code"] if ln["group"] == "Gạo" and ln["unit"] == "kg" else None, qty).values()),
          kind="ind_kg_group")

    # unanswerable (§7): the shop records none of it
    y, m, p, asof = M()
    A(f"Cho hỏi tháng {m}/{y} {shop} lãi gộp bao nhiêu tiền?", asof, "unanswerable", kind="unans_profit")
    d = day()
    A(f"tính đến hết ngày {d:%d/%m/%Y}, khách hàng còn nợ {shop} tổng cộng bao nhiêu tiền", d, "unanswerable",
      kind="unans_debt")
    A("Cho tôi biết doanh thu tháng 10/2024.", date(2025, 3, 1), "unanswerable", kind="unans_out_of_range")
    y, m, p, asof = M()
    it = q.choice(spec["items"][:8])
    A(f"Giá nhập bình quân một {it[3]} {it[1]} trong tháng {m} năm {y} là bao nhiêu ạ?", asof, "unanswerable",
      kind="unans_purchase")
    return book


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data"), help="folder of the splits (synth2_dev, synth2_hold)")
    ap.add_argument("--train", default=str(ROOT / "data" / "train"), help="train split: calendar.csv, rulebook.md")
    args = ap.parse_args(argv)
    train = Path(args.train)
    cal_text = (train / "calendar.csv").read_text(encoding="utf-8")
    rb = (train / "rulebook.md").read_text(encoding="utf-8")
    assert "## 7. Không trả lời được" in rb
    for split in ("dev", "hold"):
        out = Path(args.out) / f"synth2_{split}"
        out.mkdir(parents=True, exist_ok=True)
        (out / "calendar.csv").write_text(cal_text, encoding="utf-8")
        cal = S.read_calendar(out / "calendar.csv")
        shops = [s for s in SHOPS if s["split"] == split]
        (out / "rulebook.md").write_text(
            rb.replace("(bộ train)", f"(bộ synth2_{split})")
            .replace("## 7. Không trả lời được", "".join(s["rule6"] for s in shops) + "## 7. Không trả lời được"),
            encoding="utf-8")
        books = []
        for spec in shops:
            biz = out / "data" / spec["biz"]
            biz.mkdir(parents=True, exist_ok=True)
            for old in biz.iterdir():
                old.unlink()
            orders = simulate(spec)
            spec["write"](spec, orders, biz)
            (biz / "README.md").write_text(spec["readme"], encoding="utf-8")
            books.append(questions(spec, orders, cal))
            print(f"{spec['biz']}: {len(orders)} orders, {len(books[-1].q)} questions, "
                  f"{dict(Counter(a['type'] for a in books[-1].a))}")
        qs = [x for b in books for x in b.q]
        ans = [a for b in books for a in b.a]
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
