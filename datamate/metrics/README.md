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

**Đã có (T3, phiên 3): nhóm bán hàng A–F**, làm theo thứ tự số câu của [templates.md](../../docs/research/templates.md).
- [frames.py](frames.py): bảng đơn kèm doanh thu từng đơn; bảng dòng hàng kèm nhóm, hoạt chất, kê đơn, đơn vị cơ bản; dựng một lần cho mỗi cửa hàng.
- **Một bộ lọc dùng chung** cho mọi chỉ số:
  - theo đơn: kênh, thanh toán, nhóm khách (bỏ đơn vãng lai), khách, nhân viên, ca, thứ;
  - theo dòng hàng: mặt hàng, nhóm, hoạt chất, kê đơn, size "(M)" / "(L)", loại, thương hiệu.

  Lọc không được chính xác (thiếu cột, tên chưa nối, một dòng hàng thiếu thuộc tính) thì hàm trả `None`.
- [sales.py](sales.py):
  - 7 chỉ số: doanh thu, số đơn, số đơn huỷ, tỉ lệ huỷ, trung bình đơn, số lượng theo đơn vị cơ bản, số khách;
  - hàm theo loại câu: value (một hay nhiều số), compare (kỳ / bộ lọc, %, chênh lệch), share, rank (mặt hàng, khách, nhân viên, ngày, tháng), count_where (đơn, ngày, khách, mặt hàng; cả dạng %), trend, series, hàng ế.
- Test: [tests/test_metrics_sales.py](../../tests/test_metrics_sales.py), cửa hàng tí hon có đáp án tính tay.
- Đo bằng `python -m datamate.eval.check_plans`: 230 đúng / 2 sai (LLM đọc sai ý câu) trên 363 câu có plan của 8 cửa hàng. Xem mục H của file hạn chế.

**Đã có (v2, 04/11):** mỗi công thức đều được dò với đáp án train của các cửa hàng có mapping tay trước khi viết.
- [stock.py](stock.py), §5:
  - tiền nhập trong kỳ (20/20 câu dò khớp; lọc theo mặt hàng, nhà cung cấp);
  - giá nhập bình quân theo số lượng nhập (28/28);
  - giá bán một đơn vị cơ bản ngày D, tính cả dòng của đơn huỷ / trả (13/13);
  - tồn đến hết ngày X: dòng tồn cuối cùng có ngày ≤ X, và sau dòng đó không được có phát sinh. Cách này đọc được cả ảnh tồn cuối dữ liệu lẫn thẻ kho. Hỏi theo đơn vị lớn thì trả `[số chẵn, số lẻ]`;
  - xếp nhà cung cấp theo tiền nhập (4/4), và theo số phiếu ("nhà cung cấp chính", dòng luật chỉ có ở rulebook public).
- [debt.py](debt.py), §4:
  - nợ thêm và trả nợ trong kỳ, tổng hoặc theo khách (15/15);
  - còn nợ đến hết ngày X: tổng, số khách nợ, nợ của một khách, xếp khách theo nợ kèm bảng (13/13). Có một đơn không ghi nợ (khác COD) mà vẫn còn thiếu tiền thì bỏ trống: luật tính đơn đó là nợ, nhưng trên train mọi khoản nợ đều nằm ở đơn ghi nợ, nên trường hợp này nhiều khả năng là dữ liệu hoặc mapping đọc sai.
- [industry.py](industry.py), §6: số đợt giao của cửa hàng vật liệu xây dựng (9/9).
- [sales.py](sales.py), thêm: lãi gộp theo giá vốn ghi trên dòng bán, và xếp "hàng lời nhất" (5/5); lãi ròng = lãi gộp − sổ chi phí (3/3).
- Test: [tests/test_metrics_stock.py](../../tests/test_metrics_stock.py), [tests/test_metrics_debt.py](../../tests/test_metrics_debt.py), [tests/test_metrics_industry.py](../../tests/test_metrics_industry.py).
- `check_plans`: 316 đúng / 0 sai / 47 bỏ trống trên 363 câu (trước v2: 230 / 2 / 131).
- Chưa làm:
  - tồn của một ngày trước ảnh tồn duy nhất (phải lùi phát sinh, hiện bỏ trống);
  - tuổi nợ;
  - giá trị tồn;
  - lô và hạn dùng;
  - hiệu ứng tăng giá tính theo trung bình mỗi ngày.

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
