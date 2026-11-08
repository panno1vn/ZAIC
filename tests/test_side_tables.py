"""N77: a mapping moved from an example without receipts takes the README's receipts, keyed as its own lines are."""
from pathlib import Path

from datamate.contracts import ColumnMap, Mapping, RawBusiness, TableMap
from datamate.mapping import build_canonical
from datamate.mapping.from_readme import UNKEYED, with_side_tables

from test_mapping_readme import section, table

SALES = {"Bill": "mã đơn", "Ngày": "ngày bán", "TT": "trạng thái đơn", "Mã": "mã hàng", "Món": "tên hàng",
         "SL": "số lượng", "Tiền": "thành tiền sau giảm"}
RECEIPTS = {"Phiếu": "mã phiếu nhập", "Ngày nhập": "ngày nhập", "Mã": "mã hàng", "SL nhập": "số lượng nhập",
            "Giá nhập": "giá nhập một đơn vị"}


def shop(receipt_codes=("SP1", "SP2")) -> RawBusiness:
    sales = [(f"B{i}", f"0{1 + i % 5}/06/2026", "completed", code, name, 1, 30_000)
             for i in range(1, 9) for code, name in (("SP1", "Cà phê đen"),
                                                     ("SP2", "Trà  đào" if i == 2 else "Trà đào"))]  # one name, two spellings
    receipts = [("PN1", "01/06/2026", code, 10, 12_000) for code in receipt_codes]
    return RawBusiness(root=Path("."), readme=section("ban.csv", SALES) + section("nhap.csv", RECEIPTS),
                       tables=[table("ban.csv", sales, list(SALES)), table("nhap.csv", receipts, list(RECEIPTS))])


def moved() -> Mapping:
    """What a mapping moved from a one-file example reads: the sales lines keyed by the product NAME, no receipts."""
    cm = lambda t, s, p="text": ColumnMap(target=t, source=s, parse=p)  # noqa: E731
    return Mapping(tables=[
        TableMap(target="orders", sources=["ban.csv"], columns=[cm("order_id", "Bill"), cm("order_time", "Ngày", "datetime"),
                                                                 cm("status", "TT"), ColumnMap(target="has_time", const=False)]),
        TableMap(target="lines", sources=["ban.csv"], columns=[cm("order_id", "Bill"), cm("product_key", "Món"),
                                                                cm("product_name", "Món"), cm("qty", "SL", "qty"),
                                                                cm("line_amount", "Tiền", "money")])],
        notes=["ghép theo nghĩa với mapping mẫu X"])


def test_receipts_keyed_by_code_are_translated_into_the_lines_names():
    m = with_side_tables(moved(), shop())
    assert "purchases" in {t.target for t in m.tables} and m.notes[-1].startswith("bảng phụ từ README")
    db = build_canonical(shop(), m)
    assert set(db.table("purchases")["product_key"]) <= set(db.table("lines")["product_key"])


def test_receipts_of_products_the_lines_never_name_stay_out():
    m = with_side_tables(moved(), shop(receipt_codes=("SP7", "SP8")))  # codes the sales file does not know
    # N94 (08/11): borrowed without its products (no receipt can land on a wrong product), for the period's totals
    tm = next((t for t in m.tables if t.target == "purchases"), None)
    assert tm is not None
    key = next(c for c in tm.columns if c.target == "product_key")
    assert key.const == UNKEYED and key.source is None
