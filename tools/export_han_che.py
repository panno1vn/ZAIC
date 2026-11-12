"""Export docs/HAN_CHE_VA_CAI_THIEN.md to a spreadsheet: every limitation (checkbox item), its status (handled,
handled with a trade-off, accepted trade-off, won't fix, no longer applies, open), what is left or traded, and the
review note of 12/11 for the items still unticked. Development / reporting only.

    python tools/export_han_che.py                      # -> docs/HAN_CHE_TONG_HOP.xlsx
    python tools/export_han_che.py --out x.xlsx
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "HAN_CHE_VA_CAI_THIEN.md"

DONE, DONE_TRADE, DONE_LATER = "Đã xử lý", "Đã xử lý, còn đánh đổi", "Đã xử lý về sau"
ACCEPTED, WONTFIX, OBSOLETE, OPEN = "Đánh đổi chấp nhận", "Không xử lý (wontfix)", "Không còn áp dụng", "Còn mở"
STATUSES = (DONE, DONE_TRADE, DONE_LATER, ACCEPTED, WONTFIX, OBSOLETE, OPEN)
LEGEND = {
    DONE: "Đã sửa, có test / số đo; không còn phần nào ghi là thiếu.",
    DONE_TRADE: "Đã sửa, nhưng tài liệu ghi phần còn lại, giá phải trả hoặc rủi ro chấp nhận (cột 'Đánh đổi').",
    DONE_LATER: "Ô đánh dấu trong tài liệu chưa tick, nhưng đã được xử lý ở phiên sau (rà 12/11, xem cột ghi chú).",
    ACCEPTED: "Giữ nguyên có chủ đích: an toàn (bỏ trống thay vì trả sai) đổi lấy mất điểm, hoặc đã đo và chấp nhận.",
    WONTFIX: "Biết lỗi, không sửa (sửa cần đổi prompt / model đã chốt, hoặc lợi quá nhỏ).",
    OBSOLETE: "Việc cũ không còn liên quan (công cụ dev đã bỏ, điều kiện đã đổi).",
    OPEN: "Còn mở: chưa làm, có thể làm tiếp.",
}

# Review of 12/11 for the items still unticked: id -> (status, note, next step)
REVIEW: dict[str, tuple[str, str, str]] = {
    "H9": (DONE_LATER, "[R] so gần đúng (04/11), rồi N159, N166–N172: dòng luật viết lại / thêm câu được nhận theo nghĩa.",
           ""),
    "H11": (ACCEPTED, "decide vẫn chỉ trả lời khi period_coverage = full; kỳ chỉ có một phần dữ liệu thì trống.",
            "Có thể mở 'partial' nếu đo train không thêm sai; chưa ưu tiên."),
    "H10": (OPEN, "Chưa làm; review code vẫn là chốt chặn.", "Thấp."),
    "N1": (OBSOLETE, "Không cần ước lượng: eval chạy trên đủ 3000 câu train.", ""),
    "N3": (DONE_LATER, "Hai câu biz_122 nay trả đúng (không nằm trong 19 câu trống, 0 sai).", ""),
    "K1": (DONE_LATER, "Kho plan chỉ giữ plan ra đúng đáp án train (kho đã kiểm chứng, T4).", ""),
    "H12": (DONE_LATER, "Đồng hồ tổng của lượt chạy (câu quá giờ ghi trống), timeout mỗi lời gọi LLM, ghi đủ dòng (N165); "
            "Docker v1 chạy public 16 phút.", ""),
    "H13": (ACCEPTED, "Đường [D2] (codegen) vẫn có trong pipeline nhưng hầu như không qua cổng luật: an toàn, bỏ trống.",
            ""),
    "H14": (DONE_LATER, "Image Docker chép assets/; Docker v1 qua Test Solution 11/11.", ""),
    "H15": (DONE_TRADE, "Thay bằng N170 (chữ nội dung, STOP / PHRASES); vẫn là danh sách chọn tay.",
            "Rulebook private viết lại một chữ nội dung thì dòng đó trống (đã ghi ở N170)."),
    "H16": (OPEN, "verify._sane chỉ kiểm số hữu hạn / danh sách không rỗng; chưa chặn doanh thu âm, % vô lý.",
            "Thấp: chưa thấy câu sai nào do lỗi này trên train / prod_train."),
    "N4": (ACCEPTED, "Đo trên RTX 5090 (VM): chạy hai lần giống nhau 1000/1000; so với máy nhà lệch 9/1000 câu.", ""),
    "H19": (ACCEPTED, "Phiên bản luật nhận tự động theo bản tham chiếu train / public; đổi nghĩa thì trống (N167, N170, "
            "N172).", ""),
    "H20": (OBSOLETE, "Đã có wifi; build / test Docker trên VM thuê.", ""),
    "H21": (OPEN, "profile_business vẫn đoán kiểu và min / max trên 300 giá trị đầu.", "Thấp."),
    "N5": (DONE_LATER, "Plan dùng khi chạy lấy từ kho đã kiểm bằng đáp án train.", ""),
    "N6": (OBSOLETE, "Đo trực tiếp bằng eval train, không cần ước lượng từ registry.", ""),
    "N8": (OBSOLETE, "Chỉ ảnh hưởng công cụ gom cụm (dev).", ""),
    "N9": (ACCEPTED, "Tên viết tắt / khác cách: so khớp mờ hoặc bỏ trống (an toàn).", ""),
    "N10": (DONE_LATER, "Đo bằng đáp án: train 0 câu sai, prod_train 0 sai / 1500.", ""),
    "N11": (OPEN, "trend chỉ trả lời 'tăng liên tục?'; câu hỏi 'giảm liên tục' sẽ bị trả lời sai. Train: 0 / 23 câu "
            "trend hỏi chiều giảm.", "Nên thêm cổng: plan trend mà câu có chữ giảm / đi xuống thì bỏ trống."),
    "N12": (ACCEPTED, "Đã đo kiểu bỏ ra một shop: prod_train 1494 / 0 / 6 (12/11); synth ngành mới 7 / 1 / 72.", ""),
    "N13": (DONE_LATER, "Hợp đồng có order asc, min_orders.", ""),
    "N17": (ACCEPTED, "Tồn ngày trước ảnh tồn duy nhất vẫn bỏ trống (train mọi câu tồn là 'hết hôm nay').", ""),
    "N18": (ACCEPTED, "Giá theo đơn vị lớn vẫn bỏ trống; train không có câu.", ""),
    "N19": (ACCEPTED, "Ngưỡng 0,5% đơn không rõ trạng thái giữ nguyên (bỏ trống, an toàn).", ""),
    "N20": (DONE_LATER, "14 / 14 shop public ghép được mapping.", ""),
    "N21": (OPEN, "Rò 2 từ khách lẻ khi đo bỏ-một-shop; không đổi số đo.", "Thấp."),
    "N22": (DONE_LATER, "BTC cho xem dữ liệu public (06/11); luật chỉ dựa đáp án public đã gỡ (11/11).", ""),
    "N24": (ACCEPTED, "Đã đo: bản nộp tốt nhất public 0,948 (960 đúng / 12 sai / 28 trống); prod_train 0 sai.", ""),
    "N31": (ACCEPTED, "Đổi mapping làm thẻ dữ liệu đổi, LLM đọc lại vài câu khác (12/11: N171 làm 1 câu trống → đúng).",
            ""),
    "N27": (DONE_LATER, "biz_123 / biz_124 và 14 / 14 shop public đều ghép được (by_role, README, requantify…).", ""),
    "<reorder>": (WONTFIX, "LLM nhạy với thứ tự cột; sửa cần đổi prompt (đã chốt không đổi trước v2). 0 câu sai.", ""),
    "<layout-left>": (DONE_LATER, "Đảo cột nhà thuốc POS: N164; thêm cột trống: N171 (lấy vào 12/11).", ""),
}

ITEM = re.compile(r"^- \[( |x)\] (?:\((wontfix)\) )?\*\*(.+?)\*\*(.*)$")
ID = re.compile(r"^((?:[A-Z][A-Za-z]*\d+[a-z]?)(?:\s*\+\s*[A-Z]\d+[a-z]?)*)\s*(?:\(([^)]*)\))?\s*[.:]?\s*(.*)$")
LEVEL = re.compile(r"\b(cao|tb|trung bình|thấp)\b", re.I)
TRADE = re.compile(r"rủi ro chấp nhận|chấp nhận rủi ro|đổi lại|\bgiá:|đánh đổi|chưa xử lý|chưa sửa|wontfix|"
                   r"lỗ còn mở|còn lại:|còn lại \(|chưa làm|rủi ro:|rủi ro còn|rủi ro private", re.I)
OPEN_NOTE = re.compile(r"^- (?!\[)(?!\*\*).{0,60}(chưa sửa|chưa xử lý|wontfix)", re.I)


def _level(s: str) -> str:
    m = LEVEL.search(s or "")
    if not m:
        return ""
    w = m[1].lower()
    return {"cao": "Cao", "tb": "TB", "trung bình": "TB", "thấp": "Thấp"}[w]


def _code(rest: str) -> str:
    m = re.match(r"\s*\(([^)]*)\)", rest)
    return ", ".join(re.findall(r"`([^`]+)`", m[1])) if m else ""


def _trade(text: str) -> str:
    """The sentences that say what is left, traded or accepted; a heading sentence ("Chưa làm:") takes the next three."""
    text = re.sub(r"^\s*\([^)]*\)", "", text)  # the code references in parentheses after the title
    parts = [p.strip() for p in re.split(r"(?<=[.;])\s+|\n", text) if p.strip()]
    keep = []
    for k, p in enumerate(parts):
        if TRADE.search(p):
            keep.append(p)
            if p.replace("*", "").rstrip().endswith(":"):
                keep.extend(parts[k + 1:k + 4])
    out = " … ".join(dict.fromkeys(keep))
    return out[:900] + ("…" if len(out) > 900 else "")


def _clean(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s.replace("**", "")).strip()
    return s[:n] + ("…" if len(s) > n else "")


def parse(doc: Path) -> list[dict]:
    lines = doc.read_text(encoding="utf-8").splitlines()
    rows, section, seen = [], "", set()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#"):
            section = line.lstrip("#").strip()
        m = ITEM.match(line)
        note = OPEN_NOTE.match(line) if not m else None
        if m or note:
            subs, j = [], i + 1
            while j < len(lines) and (lines[j].startswith("  ") or (not lines[j].strip() and j + 1 < len(lines)
                                                                    and lines[j + 1].startswith("  "))):
                subs.append(lines[j].strip())
                j += 1
            if m:
                box, wontfix, bold, rest = m[1], m[2], m[3], m[4]
                idm = ID.match(bold)
                ident, paren, title = (idm[1], idm[2] or "", idm[3]) if idm else ("", "", bold)
                if not title.strip(" .:"):
                    title = rest
            else:
                box, wontfix, ident, paren, title, rest = " ", None, "", "", line[2:], ""
            full = rest + "\n" + "\n".join(subs)
            key = ident.split()[0] if ident else ("<reorder>" if "Cột đảo thứ tự còn" in title
                                                  else "<layout-left>" if "thử bố cục" in title else "")
            review = REVIEW.get(key) if box == " " else None
            trade = _trade(full) if m else _clean(title, 600)
            if review:
                status, rnote, nxt = review
                if status == DONE_TRADE:  # the review names what is traded
                    trade, nxt = nxt, ""
            elif wontfix:
                status, rnote, nxt = WONTFIX, "", ""
            elif box == "x":
                status, rnote, nxt = (DONE_TRADE if trade else DONE), "", ""
            else:
                status, rnote, nxt = OPEN, "", ""
            dup = ident in seen
            seen.add(ident)
            under = _level(section) if section.startswith("Mức") else ""  # "### Mức thấp" of part A
            rows.append({"id": ident or "—", "level": _level(paren) or _level(bold[:40]) or under, "section": section,
                         "title": _clean(title, 220), "status": status, "trade": trade,
                         "review": rnote, "next": nxt, "code": _code(rest), "line": i + 1,
                         "detail": _clean(full, 1500), "dup": dup})
            i = j
            continue
        i += 1
    return rows


ARIAL = "Arial"
HEAD_FILL = PatternFill("solid", fgColor="1F4E78")
FILLS = {DONE: "E2EFDA", DONE_TRADE: "FFF2CC", DONE_LATER: "DDEBF7", ACCEPTED: "FCE4D6", WONTFIX: "EDEDED",
         OBSOLETE: "F2F2F2", OPEN: "F8CBAD"}
THIN = Side(style="thin", color="BFBFBF")


def _header(ws, row: int, names: list[str], widths: list[int]) -> None:
    for c, (n, w) in enumerate(zip(names, widths), 1):
        cell = ws.cell(row=row, column=c, value=n)
        cell.font = Font(name=ARIAL, bold=True, color="FFFFFF", size=10)
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(c)].width = w


def _body(cell, status: str | None = None) -> None:
    cell.font = Font(name=ARIAL, size=9)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    cell.border = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
    if status:
        cell.fill = PatternFill("solid", fgColor=FILLS[status])


def write(rows: list[dict], out: Path) -> None:
    wb = Workbook()
    summary = wb.active
    summary.title = "Tổng hợp"
    full = wb.create_sheet("Danh sách")
    focus = wb.create_sheet("Cần chú ý")

    cols = ["STT", "Mã", "Mức", "Phần / phiên", "Hạn chế", "Trạng thái", "Đánh đổi / phần còn lại",
            "Ghi chú rà soát 12/11", "Việc tiếp (nếu làm)", "Code", "Dòng trong HAN_CHE", "Chi tiết (trích)"]
    widths = [5, 9, 6, 22, 45, 16, 55, 45, 30, 28, 8, 80]
    _header(full, 1, cols, widths)
    for r, x in enumerate(rows, 2):
        vals = [r - 1, x["id"], x["level"], x["section"], x["title"], x["status"], x["trade"], x["review"], x["next"],
                x["code"], x["line"], x["detail"]]
        for c, v in enumerate(vals, 1):
            _body(full.cell(row=r, column=c, value=v), x["status"] if c == 6 else None)
    full.freeze_panes = "C2"
    full.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(rows) + 1}"

    pick = [x for x in rows if x["status"] in (OPEN, ACCEPTED, WONTFIX, DONE_TRADE)]
    order = {"Cao": 0, "TB": 1, "Thấp": 2, "": 3}
    st = {OPEN: 0, WONTFIX: 1, ACCEPTED: 2, DONE_TRADE: 3}
    pick.sort(key=lambda x: (st[x["status"]], order[x["level"]], x["line"]))
    fcols = ["Mã", "Mức", "Trạng thái", "Hạn chế", "Đánh đổi / phần còn lại", "Ghi chú rà soát 12/11",
             "Việc tiếp (nếu làm)", "Dòng trong HAN_CHE"]
    _header(focus, 1, fcols, [9, 6, 16, 45, 55, 50, 40, 8])
    for r, x in enumerate(pick, 2):
        for c, v in enumerate([x["id"], x["level"], x["status"], x["title"], x["trade"], x["review"], x["next"],
                               x["line"]], 1):
            _body(focus.cell(row=r, column=c, value=v), x["status"] if c == 3 else None)
    focus.freeze_panes = "B2"
    focus.auto_filter.ref = f"A1:H{len(pick) + 1}"

    s = summary
    s.column_dimensions["A"].width = 28
    s.column_dimensions["B"].width = 12
    s.column_dimensions["C"].width = 90
    s["A1"] = "Hạn chế và cách cải thiện — tổng hợp"
    s["A1"].font = Font(name=ARIAL, bold=True, size=14)
    s["A2"] = f"Nguồn: docs/{DOC.name} (xuất bằng tools/export_han_che.py). Trạng thái các mục chưa tick: rà 12/11/2026."
    s["A2"].font = Font(name=ARIAL, italic=True, size=9)
    _header(s, 4, ["Trạng thái", "Số mục", "Nghĩa"], [28, 12, 90])
    n = len(rows) + 1
    for r, name in enumerate(STATUSES, 5):
        s.cell(row=r, column=1, value=name)
        s.cell(row=r, column=2, value=f"=COUNTIF('Danh sách'!$F$2:$F${n},A{r})")
        s.cell(row=r, column=3, value=LEGEND[name])
        for c in (1, 2, 3):
            _body(s.cell(row=r, column=c), name if c == 1 else None)
    total = 5 + len(STATUSES)
    s.cell(row=total, column=1, value="Tổng")
    s.cell(row=total, column=2, value=f"=SUM(B5:B{total - 1})")
    s.cell(row=total, column=3, value=f"=IF(B{total}=COUNTA('Danh sách'!$B$2:$B${n}),\"khớp số dòng của Danh sách\","
                                       f"\"LỆCH số dòng\")")
    for c in (1, 2, 3):
        _body(s.cell(row=total, column=c))
        s.cell(row=total, column=c).font = Font(name=ARIAL, bold=True, size=9)
    r0 = total + 2
    _header(s, r0, ["Mục còn mở theo mức", "Số mục", "Ghi chú"], [28, 12, 90])
    for k, lv in enumerate(("Cao", "TB", "Thấp"), r0 + 1):
        s.cell(row=k, column=1, value=lv)
        s.cell(row=k, column=2, value=f"=COUNTIFS('Danh sách'!$F$2:$F${n},\"{OPEN}\",'Danh sách'!$C$2:$C${n},A{k})")
        s.cell(row=k, column=3, value="Danh sách lọc sẵn ở sheet 'Cần chú ý' (còn mở, wontfix, đánh đổi chấp nhận, đã xử lý còn đánh đổi).")
        for c in (1, 2, 3):
            _body(s.cell(row=k, column=c))
    # openpyxl stores no computed values: Excel / Sheets compute the COUNTIF cells when the file opens
    from openpyxl.workbook.properties import CalcProperties
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "HAN_CHE_TONG_HOP.xlsx")
    args = ap.parse_args(argv)
    rows = parse(DOC)
    write(rows, args.out)
    from collections import Counter
    print(len(rows), "mục:", dict(Counter(x["status"] for x in rows)))
    unreviewed = [x["id"] for x in rows if x["status"] == OPEN and not x["review"]]
    if unreviewed:
        print("chưa rà (còn mở, không có ghi chú):", unreviewed)
    print("→", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
