"""N29: the attribute columns the README names that a mapping (moved from an example's shop that did not record them)
leaves out are added: on the orders by their own column or by the customer code; on the catalogue by its own column or
by the product code from a drug list."""
from pathlib import Path

from datamate.contracts import ColumnMap, Mapping, RawBusiness, TableMap
from datamate.mapping.from_readme import enrich

from test_mapping_readme import section, table

ORDERS = {"Mã HĐ": "mã đơn", "Ngày": "ngày bán", "TT": "trạng thái đơn", "Mã KH": "mã khách (trống nếu khách lẻ)",
          "Tên KH": "tên khách", "NV": "mã nhân viên bán", "HTTT": "hình thức thanh toán của đơn"}
CLIENTS = {"Mã KH": "mã khách", "Tên": "tên", "Nhóm": "nhóm khách"}
GOODS = {"Mã hàng": "mã hàng", "Tên hàng": "tên", "Nhóm hàng": "nhóm hàng"}
DRUGS = {"Mã hàng": "mã hàng", "Hoạt chất": "hoạt chất (trống với thực phẩm chức năng)", "Kê đơn": "thuốc kê đơn"}


def shop() -> RawBusiness:
    readme = section("hd.csv", ORDERS) + section("kh.csv", CLIENTS) + section("sp.csv", GOODS) + \
        section("thuoc.csv", DRUGS)
    return RawBusiness(root=Path("."), readme=readme, tables=[
        table("hd.csv", [("D1", "01/06/2026", "Xong", "KH1", "An", "NV1", "Tiền mặt")], list(ORDERS)),
        table("kh.csv", [("KH1", "An", "sỉ")], list(CLIENTS)),
        table("sp.csv", [("SP1", "Panadol", "giảm đau")], list(GOODS)),
        table("thuoc.csv", [("SP1", "Paracetamol", "TRUE")], list(DRUGS))])


def moved(customer_key: str = "Mã KH") -> Mapping:
    """What a mapping moved from a shop without these attributes reads."""
    cm = lambda t, s: ColumnMap(target=t, source=s)  # noqa: E731
    return Mapping(tables=[
        TableMap(target="orders", sources=["hd.csv"], columns=[cm("order_id", "Mã HĐ"), cm("order_time", "Ngày"),
                                                                 cm("status", "TT"), cm("customer_key", customer_key)]),
        TableMap(target="products", sources=["sp.csv"], columns=[cm("product_key", "Mã hàng"),
                                                                   cm("product_name", "Tên hàng")])],
        notes=["chuyển từ mapping mẫu X"])


def cols(m: Mapping, target: str) -> dict:
    return {c.target: c for c in next(t for t in m.tables if t.target == target).columns}


def test_attributes_the_readme_names_are_added():
    m = enrich(moved(), shop())
    orders, products = cols(m, "orders"), cols(m, "products")
    assert orders["employee"].source == "NV" and orders["payment_method"].source == "HTTT"
    group = orders["customer_group"]
    assert group.transform == "lookup" and group.source == "Mã KH"
    assert group.args == {"table": "kh.csv", "key": "Mã KH", "value": "Nhóm", "keep_missing": False}
    assert products["product_group"].source == "Nhóm hàng"
    assert products["active_ingredient"].args["table"] == "thuoc.csv" and products["active_ingredient"].args["value"] == "Hoạt chất"
    assert products["is_prescription"].parse == "bool" and products["is_prescription"].args["value"] == "Kê đơn"
    assert m.notes[0] == "chuyển từ mapping mẫu X" and m.notes[-1].startswith("bổ sung từ README")


def test_a_column_the_mapping_reads_is_kept_and_a_name_key_is_no_code_to_look_up_by():
    base = moved(customer_key="Tên KH")
    base.tables[0].columns.append(ColumnMap(target="payment_method", source="TT"))
    m = enrich(base, shop())
    orders = cols(m, "orders")
    assert orders["payment_method"].source == "TT"  # what the mapping read stays
    assert "customer_group" not in orders  # orders keyed by name: the customer list's code cannot be matched


LINES = {"Mã HĐ": "mã đơn", "Mã hàng": "mã hàng", "SL": "số lượng", "Tiền": "thành tiền sau giảm"}


def test_a_mapping_without_catalogue_gets_the_readmes_when_the_lines_carry_its_code():
    raw = shop()
    raw.readme += section("ct.csv", LINES)
    raw.tables.append(table("ct.csv", [("D1", "SP1", 2, 20_000)], list(LINES)))
    cm = lambda t, s: ColumnMap(target=t, source=s)  # noqa: E731
    base = Mapping(tables=[moved().tables[0], TableMap(target="lines", sources=["ct.csv"], columns=[
        cm("order_id", "Mã HĐ"), cm("product_key", "Mã hàng"), cm("product_name", "Mã hàng"), cm("qty", "SL"),
        cm("line_amount", "Tiền")])])
    products = cols(enrich(base, raw), "products")
    assert products["product_key"].source == "Mã hàng" and products["product_name"].source == "Tên hàng"
    assert products["product_group"].source == "Nhóm hàng"
    assert products["active_ingredient"].args["table"] == "thuoc.csv" and products["is_prescription"].parse == "bool"


def test_a_shop_whose_readme_describes_no_column_is_left_alone():
    raw = shop()
    raw.readme = "# Dữ liệu\n"
    assert enrich(moved(), raw) == moved()
