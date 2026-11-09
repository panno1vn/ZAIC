"""Rulebook edits a private split may bring, and whether the frozen image notices them. Each edit changes the meaning
of one public rulebook row (a number, two words swapped, a sentence added, a row renamed, a time rule changed) or
only its wording. An edit that changes the meaning must blank the questions that rest on the row (never answer them
with the old formula: a silent wrong answer); a wording-only edit must change nothing (a blank there is lost score).

For each edit: which rule ids the [R] gate flips (rules.check_rules, the run's own rule list), then a replay of a live
public run from its logs with the edited rulebook (tools/replay_run.py, no LLM), compared with the run's answers:
answers changed, answers turned blank, and of the "exposed" questions (answered in the run and resting on the row:
the row id among the function's cited rules, or the edit's own plan predicate for rows no function cites) how many
are still answered. Never compared with gold.

    python tools/robust_rulebook.py                       # every edit
    python tools/robust_rulebook.py --edits week_sunday drop_ca_phe --replay

Development only.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from datamate import rules  # noqa: E402
from datamate.pipeline import rule_ids  # noqa: E402


def _kind(*kinds):
    return lambda log: ((log.get("plan") or {}).get("period") or {}).get("kind") in kinds


def _metric(*names):
    return lambda log: any(m.get("metric") in names for m in (log.get("plan") or {}).get("measures") or [])


def _any(log):
    return True


# name -> (kind, old text, new text, exposed predicate or None = by cited rule ids flipped / rule id given)
# kind: "meaning" (the old formula is now wrong for the exposed questions) or "wording" (nothing should move)
EDITS: dict[str, tuple[str, str, str, object]] = {
    # numbers inside cited rows
    "shift_hours": ("meaning", "ca sáng 06:00–13:59, ca chiều 14:00–21:59", "ca sáng 06:00–11:59, ca chiều 12:00–21:59",
                    "§2.ca_sang_ca_chieu"),
    "tet_window": ("meaning", "từ ngày dương của **23 tháng Chạp**", "từ ngày dương của **25 tháng Chạp**", "§2.tet_nam_y_dip_tet_mua_tet"),
    "big_spender_5": ("meaning", "chỉ xét khách có **từ 3 đơn trở lên**", "chỉ xét khách có **từ 5 đơn trở lên**", None),
    # two words swapped in a cited row (no number, no meaning word changes)
    "period_by_delivery": ("meaning", "theo **ngày đặt**, không theo ngày giao hay ngày thu tiền",
                           "theo **ngày giao**, không theo ngày đặt hay ngày thu tiền", "§1.don_thuoc_ky_nao"),
    "best_seller_by_money": ("meaning", "theo **số lượng quy về đơn vị cơ bản**, không theo số dòng hay số tiền",
                             "theo **số tiền**, không theo số dòng hay số lượng quy về đơn vị cơ bản", "§3.ban_chay"),
    "best_staff_by_orders": ("meaning", "theo **doanh thu** (§1) của nhân viên trong kỳ, không theo số đơn",
                             "theo **số đơn** (§1) của nhân viên trong kỳ, không theo doanh thu", "§3.nhan_vien_ban_gioi_nhat"),
    "debt_age_from_due": ("meaning", "số ngày tính từ **ngày đặt**, không từ hạn thanh toán",
                          "số ngày tính từ **hạn thanh toán**, không từ ngày đặt", "§4.tuoi_no"),
    "round_half_down": ("meaning", "làm tròn về đồng, nửa đồng làm tròn lên", "làm tròn về đồng, nửa đồng làm tròn xuống",
                        "§3.gia_tri_trung_binh_mot_don"),
    "in_delivery_excluded": ("meaning", "Đơn đang giao vẫn tính |", "Đơn đang giao cũng bỏ |", "§1.don_tinh_vao_doanh_thu"),
    "vat_included": ("meaning", "**không** cộng thuế VAT, **không** gồm phí giao hàng",
                     "**có** cộng thuế VAT, **có** gồm phí giao hàng", "§1.doanh_thu_mot_don"),
    # a sentence added that narrows the rule (accepted by rules.extends as a clarification)
    "sentence_cod_out": ("meaning", "Đơn đang giao vẫn tính |",
                         "Đơn đang giao vẫn tính. Đơn COD chưa thu tiền không tính vào doanh thu |", "§1.don_tinh_vao_doanh_thu"),
    "sentence_service_fee": ("meaning", "Dòng **Phí phục vụ** không phải mặt hàng: không xếp hạng, không đếm.",
                             "Dòng **Phí phục vụ** không phải mặt hàng: không xếp hạng, không đếm. Dòng quà tặng giá 0 đồng cũng không phải mặt hàng.",
                             "§3.mat_hang"),
    # rows no function cites
    "week_sunday": ("meaning", "| Tuần | bắt đầu **thứ Hai**. **Tuần này**: từ thứ Hai", "| Tuần | bắt đầu **Chủ nhật**. **Tuần này**: từ Chủ nhật",
                    _kind("last_week", "this_week")),
    "last_n_without_today": ("meaning", "N ngày liền nhau **kể cả hôm nay**, ngày cuối là hôm nay",
                             "N ngày liền nhau **trước hôm nay**, ngày cuối là hôm qua", _kind("last_n_days")),
    "ytd_to_yesterday": ("meaning", "từ 01/01 của năm nay đến **hết hôm nay**", "từ 01/01 của năm nay đến **hết hôm qua**",
                         _kind("ytd")),
    "cogs_fifo": ("meaning", "bình quân gia quyền theo lô nhập, tại thời điểm bán; không theo FIFO",
                  "theo FIFO (lô nhập trước bán trước); không theo bình quân gia quyền", _metric("gross_profit", "net_profit")),
    "dup_rows_twice": ("meaning", "lỗi xuất file, tính một lần.", "là hai lần bán, tính cả hai.", None),
    # wording only: nothing should move
    "rename_revenue_row": ("wording", "| Đơn tính vào doanh thu |", "| Đơn được tính doanh thu |", "§1.don_tinh_vao_doanh_thu"),
    "rename_period_row": ("wording", "| Đơn thuộc kỳ nào |", "| Đơn tính vào kỳ nào |", "§1.don_thuoc_ky_nao"),
    "reword_revenue_row": ("wording", "Đơn có trả hàng, **kể cả chỉ trả một phần**, là đơn trả hàng: bỏ **cả đơn**.",
                           "Đơn có trả hàng (kể cả trả một phần) là đơn trả hàng, bỏ **cả đơn**.", "§1.don_tinh_vao_doanh_thu"),
    "table_to_bullets_s4": ("wording", None, None, None),  # §4 table rewritten as bullets "- **Tuổi nợ**: …"
    "new_industry": ("wording", None, None, None),  # a new "### Giặt là" section appended to §6
    # an industry the private split has no shop of, left out of its rulebook: only that industry's questions may move
    "drop_ca_phe": ("wording", None, None, None),
    "drop_nha_thuoc": ("wording", None, None, None),
    "drop_sua_xe": ("wording", None, None, None),
}


def apply(text: str, name: str) -> str:
    kind, old, new, _ = EDITS[name]
    if name == "table_to_bullets_s4":
        out, in4 = [], False
        for line in text.splitlines():
            if line.startswith("## "):
                in4 = line.startswith("## 4.")
            if in4 and line.startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if cells[0] in ("Luật", "") or set(cells[0]) <= set("-: "):
                    continue
                out.append(f"- **{cells[0]}**: {' | '.join(cells[1:])}")
            else:
                out.append(line)
        return "\n".join(out) + "\n"
    if name.startswith("drop_"):
        title = {"drop_ca_phe": "Cà phê", "drop_nha_thuoc": "Nhà thuốc", "drop_sua_xe": "Sửa xe"}[name]
        out, skip = [], False
        for line in text.splitlines():
            if line.startswith(("## ", "### ")):
                skip = line.strip() == "### " + title
            if not skip:
                out.append(line)
        assert len(out) < len(text.splitlines())
        return "\n".join(out) + "\n"
    if name == "new_industry":
        anchor = "\n## 7."
        sec = ("\n### Giặt là\n| Luật | Mặc định |\n|---|---|\n| Số ký đồ giặt | cộng cột **Số ký** của phiếu không huỷ |\n"
               "| Phiếu giặt gấp | phiếu có ghi **giặt nhanh**; tính theo ngày nhận đồ |\n")
        assert anchor in text
        return text.replace(anchor, sec + anchor, 1)
    assert text.count(old) == 1, (name, text.count(old))
    return text.replace(old, new)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default=str(ROOT / "data" / "public_test"))
    ap.add_argument("--run", default=str(ROOT / "outputs" / "public_live_778f898"))
    ap.add_argument("--edits", nargs="*", default=list(EDITS))
    ap.add_argument("--out", default=str(ROOT / "outputs" / "robust_rulebook"))
    ap.add_argument("--replay", action="store_true", help="also replay the run (slow, ~25 min an edit); without it "
                    "the blanks are counted from the [R] gate (verify: an answer whose cited rule fails is blanked)")
    args = ap.parse_args(argv)
    split, run, out = Path(args.split), Path(args.run), Path(args.out)
    rulebook = (split / "rulebook.md").read_text(encoding="utf-8-sig")
    ids = rule_ids()
    base_status = rules.check_rules(rulebook, ids)
    logs = {}
    for f in (run / "logs").glob("q_*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        logs[d["id"]] = d
    answered = {k for k, d in logs.items() if (d.get("answer") or {}).get("type") not in (None, "abstain")}
    base = {json.loads(x)["id"]: x.strip() for x in (run / "submission.jsonl").read_text(encoding="utf-8").splitlines()
            if x.strip()}
    report = []
    for name in args.edits:
        kind, _, _, expose = EDITS[name]
        text = apply(rulebook, name)
        status = rules.check_rules(text, ids)
        flipped = sorted(r for r in ids if base_status[r] and not status[r])
        if callable(expose):
            exposed = {k for k in answered if expose(logs[k])}
        else:
            rid = expose
            cites = (lambda d, r: r in (((d.get("result") or {}) if isinstance(d.get("result"), dict) else {})
                                         .get("rule_ids") or []))
            targets = [rid] if rid else flipped
            exposed = {k for k in answered if any(cites(logs[k], r) for r in targets)}
        gate_blank = {k for k in answered if set(((logs[k].get("result") if isinstance(logs[k].get("result"), dict)
                                                    else {}) or {}).get("rule_ids") or []) & set(flipped)}
        row = {"edit": name, "kind": kind, "flipped": flipped, "exposed": len(exposed), "gate_blanks": len(gate_blank),
               "gate_blank_shops": len({logs[k]["business_id"] for k in gate_blank}),
               "exposed_not_blanked": len(exposed - gate_blank)}
        if args.replay:
            import replay_run
            copy = out / "splits" / name
            if copy.exists():
                subprocess.run(["cmd", "/c", "rmdir", str(copy / "data")], capture_output=True)
                shutil.rmtree(copy)
            copy.mkdir(parents=True)
            subprocess.run(["cmd", "/c", "mklink", "/J", str(copy / "data"), str((split / "data").resolve())],
                           check=True, capture_output=True)
            for f in ("calendar.csv", "questions.jsonl"):
                shutil.copy2(split / f, copy / f)
            (copy / "rulebook.md").write_text(text, encoding="utf-8")
            dest = out / "replay" / name
            replay_run.main([str(run), "--out", str(dest), "--data", str(copy), "--enrich"])
            got = {json.loads(x)["id"]: json.loads(x) for x in
                   (dest / "submission.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()}
            changed = [k for k in base if base[k] != json.dumps(got.get(k), ensure_ascii=False) and
                       json.loads(base[k]) != got.get(k)]
            to_blank = [k for k in changed if (got.get(k) or {}).get("type") == "abstain"]
            exposed_still = [k for k in exposed if (got.get(k) or {}).get("type") not in (None, "abstain")]
            row.update(changed=len(changed), to_blank=len(to_blank), to_other=len(changed) - len(to_blank),
                       exposed_still_answered=len(exposed_still))
        report.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
