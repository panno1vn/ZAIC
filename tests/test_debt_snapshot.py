"""N100: debts recorded only as each order's state at the end of the data (README "… tính đến hết ngày cuối dữ liệu"),
as an amount or as words in a note; known on that day only."""
from datetime import date, datetime

import pandas as pd

from datamate.contracts import CanonicalDB
from datamate.mapping.debt_snapshot import last_day, owed_from_note
from datamate.metrics.debt import open_orders


def test_notes_read_as_the_debt_left():
    assert owed_from_note("khách đưa trước 87k, còn thiếu 73 nghìn", 160000) == 73000
    assert owed_from_note("trả 259k, nợ 449.500đ", 708500) == 449500
    assert owed_from_note("đưa trước 236k, còn lại ghi sổ", 286000) == 50000
    assert owed_from_note("nợ cả đơn", 500000) == 500000
    assert owed_from_note("ghi nợ 867k, đã trả đủ", 867000) == 0
    assert owed_from_note("nợ 79k, khách ck đủ rồi", 79000) == 0
    assert owed_from_note("trả 300k, nợ 449.500đ", 708500) is None  # does not add up to the order: unread
    assert owed_from_note("", 100) is None  # a debt order with no word: unknown
    assert last_day("- Dữ liệu có đến hết 22/07/2026.") == date(2026, 7, 22)


def shop() -> CanonicalDB:
    orders = pd.DataFrame({"order_id": ["O1", "O2", "O3"],
                           "order_time": [datetime(2026, 7, 1), datetime(2026, 7, 10), datetime(2026, 7, 20)],
                           "status": ["completed"] * 3, "customer_key": ["K1", "K2", "K1"],
                           "payment_method": ["debt", "cash", "debt"], "debt_left": [50000.0, 0.0, 20000.0]})
    lines = pd.DataFrame({"order_id": ["O1", "O2", "O3"], "product_key": ["P"] * 3, "line_amount": [1.0] * 3})
    return CanonicalDB(tables={"orders": orders, "lines": lines}, debt_snapshot_day=date(2026, 7, 22))


def test_debts_known_on_the_last_day_only():
    owing = open_orders(shop(), date(2026, 7, 22))
    assert len(owing) == 2 and float(owing["balance"].sum()) == 70000
    assert open_orders(shop(), date(2026, 7, 21)) is None  # any other day: not recorded


def test_a_debt_on_an_order_not_written_as_debt_is_no_guess():
    db = shop()
    db.tables["orders"].loc[1, "debt_left"] = 10000.0  # a cash order owing: COD-like, §4 never a debt
    assert open_orders(db, date(2026, 7, 22)) is None
