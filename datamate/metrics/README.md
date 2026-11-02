# G5 — [D1] Thư viện hàm

**Mục tiêu:** mỗi loại câu có một hàm tính **đúng tuyệt đối** theo rulebook. Đây là đường chính để lấy điểm.

**Hợp đồng:** hàm nhận `(ResolvedPlan, CanonicalDB)`, trả `ExecResult | None`, đăng ký bằng decorator:

```python
@metric("value", "revenue", requires=("orders.order_time", "orders.status", "lines.line_amount"),
        rules=("§1.don_tinh_vao_doanh_thu", "§1.doanh_thu_mot_don", ...))
def revenue(plan, db): ...
```

- `entity`: với xếp hạng, đếm theo ngưỡng, liệt kê thì ghi đối tượng (`"product"`, `"day"`, `"customer"`…), để "mặt hàng doanh thu cao nhất" và "ngày doanh thu cao nhất" là hai hàm khác nhau. Đăng ký trùng khóa `(intent, metric, entity)` sẽ báo lỗi ngay lúc import.
- `filters`: các trường lọc hàm **thật sự áp dụng**, ví dụ `filters=("product", "product_group")`. Plan có bộ lọc ngoài danh sách thì `execute` không gọi hàm, và câu đó bỏ trống. Như vậy không bao giờ trả lời mà bỏ sót bộ lọc. Mặc định là không nhận bộ lọc nào.
- `requires`: các cột chuẩn cần dùng. Thiếu cột thì [V] cho câu bỏ trống, và sau này dùng để quyết định unanswerable.
- `rules`: id các dòng luật mà hàm cài theo; xem `python -m datamate.rules diff …` và [assets/rules/reference_rules.json](../../assets/rules/reference_rules.json). Rulebook private đổi luật thì [R] chặn hàm đó.
- Không làm được thì trả `None`. **Không bao giờ đoán.**
- Tiền làm tròn bằng `datamate.formatter.money` (nửa lên). Không dùng `round()` của Python.
- Giá trị trả về có thể là kiểu numpy (`df.sum()` ra `np.int64`); formatter tự đổi sang kiểu Python. Phần tử list và ô của bảng chỉ được là tên hoặc số hữu hạn: có `None` hay `NaN` thì câu đó bỏ trống.

**Đã có (bộ khung 05/11):** [sales.py](sales.py) gồm `valid_orders`, `valid_lines` (đơn hợp lệ theo §1), doanh thu, số đơn, mặt hàng bán chạy nhất (theo đơn vị cơ bản, hòa thì theo mã), ngày doanh thu cao nhất.

**Việc cần làm (theo số câu trong train, xem [docs/research/intents.md](../../docs/research/intents.md)):**
1. Bộ lọc trên measure: mặt hàng, nhóm hàng, nhóm khách, kênh, hình thức thanh toán, ca (cần `has_time`), size.
2. `compare` (tăng trưởng %, chênh lệch), `share`, `count_where`, `avg_order_value`, `cancel_rate` (mẫu số là mọi đơn), `quantity` theo đơn vị (§3).
3. Xếp hạng khách theo `customer_key` (§3), nhân viên, ngày/tháng/giờ.
4. Công nợ (§4), nhập hàng và tồn kho (§5), lãi, hiệu ứng tăng giá; luật theo ngành (§6).

**Hợp đồng v1.1 (K2) cần biết:**
- Bộ lọc ca, thứ, trạng thái, kê đơn, bảo hành nhận **mã** (`morning`, `sat`, `cancelled`, `true`…), xem `CODED_VALUES`. Không so chuỗi tiếng Việt.
- `count_where`: đếm `threshold.entity` có `threshold.metric` qua ngưỡng; bộ lọc (nếu có) nằm ở `measures[0]`.
- `list_items` có `list_spec.count = true` thì trả về số đối tượng (number), không trả list.

**Thế nào là xong:** mỗi hàm chạy với mapping tay bằng `python -m datamate.eval.oracle --all --out outputs/oracle_all` cho **0 câu sai** trên train trước khi merge; có test trên dữ liệu nhỏ tự dựng (xem `tests/test_skeleton.py`).

**Luật thi:** không viết luật riêng cho cửa hàng nào. Mọi khác biệt giữa các cửa hàng phải nằm ở mapping.
