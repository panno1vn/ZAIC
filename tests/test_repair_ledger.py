"""N42: a repair shop's ledger (public, 06/11; an industry train has none of): one row per ticket, no ticket code, no
lines; the README: "Ngày: ngày sửa", "Xe: dòng xe và biển số ghi chung một ô", "Làm gì: các việc đã làm",
"Thợ: thợ làm phiếu", "Tiền: tổng tiền cả phiếu", "Ghi chú" (a warranty ticket: "bảo hành", Tiền 0). Public rulebook
§6 Sửa xe: the average of a ticket is over the tickets with money, warranty tickets left out."""
from datetime import date
from pathlib import Path

import pandas as pd

from datamate import metrics
from datamate.contracts import QueryPlan, RawBusiness, RawTable, ResolvedPeriod, ResolvedPlan
from datamate.mapping import build_canonical, run_checks
from datamate.mapping.from_readme import map_from_readme

NOTES = {"Ngày": "ngày sửa", "Xe": "dòng xe và biển số ghi chung một ô", "Làm gì": "các việc đã làm cho xe, nhiều việc ghi chung một ô",
         "Thợ": "thợ làm phiếu, ghi tên gọi", "Tiền": "tổng tiền cả phiếu", "Ghi chú": "ghi chú"}


def shop(n: int = 40) -> RawBusiness:
    rows = [(f"{1 + i % 28:02d}/06/2026", f"Wave alpha 59B{i % 9}-219.{10 + i}", "thay nhớt + vá xe",
             ["A.Đức", "a An"][i % 2], "0" if i % 10 == 3 else "120.000đ", "bảo hành" if i % 10 == 3 else "")
            for i in range(n)]
    readme = "## Cột trong `SoSuaXe.xlsx`\n" + "".join(f"- **{c}**: {m}\n" for c, m in NOTES.items()) + \
        "\n## Quy ước\n- Dữ liệu có đến hết 28/06/2026.\n"
    return RawBusiness(root=Path("."), readme=readme, tables=[
        RawTable(table_id="SoSuaXe.xlsx::T6-2026", file="SoSuaXe.xlsx", sheet="T6-2026",
                 frame=pd.DataFrame(rows, columns=list(NOTES)))])


def test_the_readme_maps_a_repair_ledger_one_ticket_per_row():
    raw = shop()
    m, why = map_from_readme(raw)
    assert m is not None, why
    assert m.record_grain == "line_is_record" and [t.target for t in m.tables] == ["orders"]
    cols = {c.target: c for c in m.tables[0].columns}
    assert cols["order_id"].source == "_row" and cols["goods_amount"].source == "Tiền"
    assert cols["employee"].source == "Thợ" and cols["services"].source == "Làm gì"
    assert cols["status"].transform == "status_from_note"
    db = build_canonical(raw, m)
    o = db.tables["orders"]
    assert len(o) == 40 and o["vehicle_plate"].iloc[0] == "59B0-219.10" and o["vehicle_model"].iloc[0] == "Wave alpha"
    assert int(o["is_warranty"].sum()) == 4 and (o["status"] == "completed").all()
    assert all(c.passed for c in run_checks(db, raw.readme)), [(c.name, c.detail) for c in run_checks(db, raw.readme)
                                                                if not c.passed]


def test_the_average_ticket_leaves_warranty_tickets_out():
    raw = shop()
    m, _ = map_from_readme(raw)
    db = build_canonical(raw, m)
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "avg_order_value"}],
                                                       "period": {"kind": "this_month"}}),
                        as_of=date(2026, 6, 30), period=ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30)))
    assert metrics.execute(plan, db).value == 120_000  # 36 tickets of 120 000, 4 warranty tickets of 0 left out


def test_a_mechanic_written_by_nickname_is_the_full_name_of_the_staff_list():
    """A public repair shop (06/11): "sổ ghi thợ theo tên gọi" ("A.Phúc", "a Phúc", "Phúc") while DanhSachTho.xlsx and
    the questions use the full name ("thợ Đoàn Bảo Phúc"): one mechanic was three, and rankings named a nickname.
    The honorific dropped, a nickname that is the last word of exactly one full name becomes that name."""
    from datamate.contracts import CanonicalDB
    from datamate.mapping.build import full_employee_names
    db = CanonicalDB(tables={
        "orders": pd.DataFrame({"employee": ["A.Phúc", "a Phúc", "Phúc", "anh Đức", "Lan", None]}),
        "employees": pd.DataFrame({"employee_key": ["Đoàn Bảo Phúc", "Lương Chi Đức", "Hà Lan", "Đàm Lan An"],
                                   "employee_name": ["Đoàn Bảo Phúc", "Lương Chi Đức", "Hà Lan", "Đàm Lan An"]})})
    full_employee_names(db)
    assert db.tables["orders"]["employee"].tolist() == ["Đoàn Bảo Phúc"] * 3 + ["Lương Chi Đức", "Hà Lan", None]


def test_the_readme_maps_the_staff_list_of_a_repair_shop():
    raw = shop()
    staff = {"Họ tên": "họ tên thợ", "Ngày vào làm": "ngày vào làm",
             "Hoa hồng (%)": "phần trăm hoa hồng của thợ, tính trên tổng Tiền các phiếu thợ làm trong tháng"}
    raw.readme += "## Cột trong `DanhSachTho.xlsx`\n" + "".join(f"- **{c}**: {m}\n" for c, m in staff.items())
    raw.tables.append(RawTable(table_id="DanhSachTho.xlsx::Sheet1", file="DanhSachTho.xlsx", sheet="Sheet1",
                               frame=pd.DataFrame([("Lương Chi Đức", "2024-09-19", "25"), ("Đàm Lan An", "2023-10-03", "33")],
                                                  columns=list(staff))))
    m, why = map_from_readme(raw)
    assert m is not None, why
    db = build_canonical(raw, m)
    assert set(db.tables["employees"]["employee_name"]) == {"Lương Chi Đức", "Đàm Lan An"}
    assert db.tables["employees"]["commission_pct"].tolist() == [25.0, 33.0]
    assert set(db.tables["orders"]["employee"]) == {"Lương Chi Đức", "Đàm Lan An"}  # "A.Đức", "a An"
    # public run9 (05/11): every check passed, yet Mapping.ok asked an orders-only shop for tables == {"orders"}, so the
    # staff list made the shop unusable and all its questions abstained without the LLM
    m.checks = run_checks(db, raw.readme)
    assert m.ok, [(c.name, c.detail) for c in m.checks if not c.passed]
