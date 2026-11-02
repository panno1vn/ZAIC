# Hợp đồng giữa các khối (bản v1.1 · sau K2, khóa ở buổi họp chia vai)

Bản v1 sửa các lỗ hổng H1–H7 trong [HAN_CHE_VA_CAI_THIEN.md](HAN_CHE_VA_CAI_THIEN.md): thêm chỉ số và bộ lọc cho các ngành mới theo rulebook public, mốc "ngày tăng giá" không cần ghi ngày, bộ biến đổi có tên cho mapping, cách tổng hợp "trung bình mỗi ngày thứ X", khối điều kiện cho `list_items`, kiểu đáp án tự suy ra, kiểm tra định dạng ngày, thêm thông tin khách và loại giảm giá.

Code: [datamate/contracts/](../datamate/contracts/). Sau khi khóa, mọi thay đổi phải qua leader. Góp ý thì mở issue hoặc nhắn trước tối T5 05/11.

## Luồng dữ liệu

```
[A]  load_business(thư mục)            → RawBusiness        (bảng thô đã parse)
[A2] profile_business(raw)             → BusinessProfile    (mô tả cột, mẫu giá trị)
[B]  map_business(raw, profile, …)     → Mapping            (JSON: cột thô → cột chuẩn, có kiểm tra)
     build_canonical(raw, mapping)     → CanonicalDB        (các bảng chuẩn + khoảng ngày)
     build_card(db)                    → DataCard           (tóm tắt ngắn đưa vào prompt)
[C]  parse_question(câu hỏi, as_of, …) → QueryPlan          (LLM, structured output)
[C2] resolve(plan, as_of, calendar)    → ResolvedPlan       (kỳ ký hiệu → ngày cụ thể)
[C3] link_entities(resolved, db)       → ResolvedPlan       (tên trong câu → giá trị trong dữ liệu)
[D1] metrics.execute(resolved, db)     → ExecResult | None  (đường chính)
[D2] codegen.solve(…)                  → ExecResult | None  (dự phòng)
[R]  check_rules(rulebook, rule_ids)   → {rule_id: còn nguyên?}
[V]  collect_signals(…)                → Signals
[E]  decide(signals, result)           → Decision           (answer / unanswerable / abstain)
[F]  to_line(qid, decision, result)    → SubmissionLine     (đúng format §9)
```

Mọi khối đã có **stub** chạy được và luôn dẫn tới bỏ trống. Test `test_stub_chain_abstains` gọi đủ chuỗi trên.

## Các quyết định thiết kế cần cả nhóm biết
1. **Schema chuẩn** (`canonical.py`): 16 bảng. Lõi là `orders` + `lines`; các bảng khác có thì điền, không có thì để trống. Thông tin lạ không thuộc bảng nào (trả góp, thu máy cũ, sổ sửa xe…) vào `extra` để đường sinh code [D2] dùng.
2. **Giá trị chuẩn viết bằng mã ASCII**: trạng thái đơn là `completed / cancelled / returned / delivering`, để code không bao giờ so chuỗi tiếng Việt có dấu.
3. **Mapping là JSON** (`mapping.py`): mapping viết tay cho cửa hàng train và mapping do LLM sinh ra có cùng một format, nên dùng mapping tay để chấm mapping tự động.
4. **QueryPlan** (`plan.py`) có 9 loại câu: `value, compare, share, rank, count_where, trend, series, list_items, out_of_scope`.
   - `measures` là danh sách, giữ đúng thứ tự câu hỏi (cho câu hỏi nhiều số).
   - `compare` so được với **kỳ khác** (kỳ trước, cùng kỳ năm trước, cùng số ngày tháng trước, trước Tết, N ngày trước D) hoặc với **bộ lọc khác** (ca sáng/chiều).
   - Kỳ hỏi để ở **dạng ký hiệu**. LLM không bao giờ tự tính ngày.
   - `Filter.value` ghi đúng như trong câu hỏi; [C3] mới nối với dữ liệu.
5. **Kỳ đã tính có `mode`**: `flow` (phát sinh trong kỳ) hoặc `stock` (tình trạng đến hết ngày X). Xem [research/periods.md](research/periods.md).
6. **Signals mặc định bi quan**: khối nào chưa chạy thì không thể làm câu hỏi được trả lời.
7. **Mỗi hàm tính khai báo** `requires` (cột chuẩn cần dùng), `rules` (dòng luật dựa vào), `filters` (bộ lọc nó áp dụng) và, với xếp hạng, đếm, liệt kê, `entity` (đối tượng). Nhờ vậy [V] biết câu nào thiếu dữ liệu, [R] biết luật nào bị đổi, và plan có bộ lọc mà hàm không khai báo thì không bao giờ được trả lời. Khóa registry là `(intent, metric, entity)`; đăng ký trùng thì báo lỗi.
8. **Unanswerable chưa bật**: kể cả câu bị đánh dấu ngoài phạm vi, hiện vẫn bỏ trống cho tới khi đo trên train thấy đủ chính xác.

## Bản v1.1: sửa sau bài thử sức K2

Viết tay plan cho 99 câu train lấy mẫu theo loại câu ([assets/plans/k2_trial.jsonl](../assets/plans/k2_trial.jsonl)). Câu nào không viết được, hoặc viết được mà sai nghĩa, là lỗ hổng. Có 6 thay đổi:

1. **Trường lạ là lỗi** (`extra="forbid"` cho mọi model plan và mapping; schema có `additionalProperties: false`).
   - Trước đây LLM gõ `"filter"` thay `"filters"` thì bộ lọc bị bỏ âm thầm, và câu "doanh thu Coca tháng 5" bị trả lời bằng doanh thu cả cửa hàng.
2. **Bộ lọc dạng mã** (`CODED_VALUES`): những trường này ghi mã, không ghi chữ như trong câu hỏi.
   - Trước đây plan mẫu ghi `"chiều"`, `"sáng"`; LLM có thể ghi `"ca sáng"`, `"buổi sáng"`; còn `true` bị đổi thành `1.0`.
   - Ảnh hưởng 77 câu theo ca và 44 câu thuốc kê đơn trong train.

   | Trường | Mã |
   |---|---|
   | `shift` | `morning` (06:00–13:59), `afternoon` (14:00–21:59) |
   | `weekday` | `mon` … `sun` |
   | `order_status` | `completed`, `cancelled`, `returned`, `delivering` |
   | `prescription`, `is_warranty` | `true`, `false` |

   Trường khác không nhận `true` / `false`. Danh sách mã có trong mô tả của trường `value` trong JSON schema, để LLM đọc được.
3. **Đếm đối tượng của một danh sách**: `list_spec.count = true` thì đáp án là **số** đối tượng. Ví dụ "bao nhiêu mặt hàng bị ế" (22 câu train, đáp án đều là number).
4. **`count_where` không cần `measures`**: đối tượng đếm là `threshold.entity`, chỉ số là `threshold.metric`. Nếu ghi `measures` thì `measures[0].metric` phải trùng `threshold.metric` (giống quy tắc của `rank`) và mang bộ lọc. Trước đây plan mẫu ghi `measures = order_count` cho câu "số đơn có doanh thu ≥ X", nghĩa không nhất quán với `rank`.
5. **Khoảng hạn dùng ghi bằng ngày**: `expiring_within` nhận `n` (N ngày tới) **hoặc** `period` dạng `range` / `next_n_days`. Ví dụ "còn hàng có hạn dùng từ 25/05/2026 đến hết 22/09/2026": LLM không phải tự tính số ngày.
6. **Tết không ghi năm**: `lunar_year` để trống nghĩa là "Tết năm nay" ([C2] lấy theo hôm nay).

Thêm quy ước cho [C2] (G4): chỉ số trong **`STOCK_METRICS`** (còn nợ, tồn, hạn dùng…) luôn tính theo kiểu `stock` (tình trạng lúc hết ngày, từ đầu dữ liệu), kể cả khi plan ghi kỳ `today`, như câu "tồn kho cuối ngày hôm nay".

Kết quả kiểm trên 99 plan:
- Theo v1.1: hợp lệ hết và khớp kiểu đáp án train (`tests/test_contracts.py`).
- Theo v1:
  - 7 plan bị từ chối (cần thay đổi 4, 5, 6).
  - 6 plan qua nhưng sai nghĩa (thay đổi 2 và 3).

## Đối chiếu rulebook public → hợp đồng (H1)

Mỗi dòng luật nêu một chỉ số hoặc định nghĩa đều có chỗ trong `QueryPlan` và schema chuẩn.

| Luật (rulebook public) | Trong QueryPlan | Dữ liệu cần (schema chuẩn) |
|---|---|---|
| §1 Doanh thu, số đơn, tỉ lệ hủy, tăng trưởng, chênh lệch | `revenue`, `order_count`, `cancel_rate`; `compare` (`pct_change` / `diff`) | `orders`, `lines` |
| §1 Theo hình thức TT, nhóm khách, báo cáo tiền mặt theo ca | bộ lọc `payment_method`, `customer_group`; `cash_collected` | `orders.payment_method`, `orders.customer_group`, `shift_reports` |
| §2 Trung bình mỗi ngày thứ X | `Measure.aggregate = avg_per_weekday`, bộ lọc `weekday` | `orders.order_time` |
| §3 Bán chạy, bán được bao nhiêu <đơn vị>, hàng lời nhất | `rank` theo `quantity` / `gross_profit`; `Measure.unit` | `lines.base_qty`, `unit_conversions`, `lines.unit_cost` |
| §3 Khách trung thành / sộp / hay đổi ý, hàng ưa chuộng | `rank` theo `days_with_purchase` / `avg_order_value` + `min_orders` / `cancel_count` / `order_presence` | `orders.customer_key` |
| §3 Nhân viên giỏi nhất / chăm chỉ nhất, ngày đắt khách, giờ cao điểm | `rank` đối tượng `employee` theo `revenue` / `work_days`; đối tượng `day` / `hour` theo `order_count` | `orders.employee`, `orders.has_time` |
| §4 Công nợ, tuổi nợ, nợ thêm / trả nợ | `debt_total`, `debtor_count`, `debt_amount`, `debt_added`, `debt_paid`; bộ lọc `debt_age_days` | `orders.total_due`, `payments` |
| §5 Tiền nhập, nhà cung cấp nhập nhiều nhất / chính, nhập trừ bán | `purchase_amount`, `receipt_count` (rank `supplier`), `purchase_minus_sales` | `purchases` |
| §5 Giá trị tồn kho, hàng hết hàng cuối ngày, hàng ế | `stock_value`; `list_items` điều kiện `out_of_stock_end_of_day` / `unsold_in_period` | `inventory`, `products.unit_cost` |
| §5 Hiệu ứng tăng giá, lãi gộp, lãi ròng | kỳ `days_from` (+ `anchor_price`), `compare before_days_from`; `gross_profit`, `net_profit` | `price_history`, `lines.unit_cost`, `expenses` |
| §6 Cà phê: size, topping | bộ lọc `size` | `products.size` (mapping tách topping) |
| §6 Nhà thuốc: kê đơn, hết hạn trong N ngày, hoạt chất, lô gần hết hạn | bộ lọc `prescription`, `active_ingredient`; `list_items expiring_within` + `expiring_value`; `nearest_expiry` | `products`, `lots`, `lot_sales` |
| §6 Vật liệu xây dựng: số đợt giao | `delivery_count` | `deliveries` |
| §6 Mẹ và bé: voucher, điểm, phí ship, số sữa / size bỉm, thành viên mới | `voucher_discount`, `points_discount`, `shipping_fee_total`; bộ lọc `stage`, `size`, `brand`; `new_customer_count` | `orders.voucher_discount`, `orders.points_discount`, `products.stage`, `customers.registered_date` |
| §6 Sửa xe: lượt xe, việc làm, dòng xe, số chiếc xe, thợ, tỉ lệ bảo hành, xe khách quen | `ticket_count`, `avg_ticket_value`, `vehicle_count`, `warranty_rate`; bộ lọc `service`, `vehicle_model`, `is_warranty`; `rank` / `threshold` đối tượng `vehicle`; `list_items returning_vehicle` | `orders.vehicle_plate`, `orders.vehicle_model`, `orders.services`, `orders.is_warranty` |
| §6 Điện thoại: khách phải trả, thu máy cũ, trả góp quá hạn, tỉ lệ bảo hành, dòng máy, hãng | `amount_due_total`, `trade_in_amount`, `overdue_installment_count`, `overdue_amount`, `warranty_rate`; bộ lọc `product_line`, `brand`, `category` | `orders.trade_in_amount`, `installments`, `warranty_visits`, `products.product_line` |

## Ví dụ
24 kế hoạch truy vấn mẫu cho câu train: [assets/plans/examples_v0.jsonl](../assets/plans/examples_v0.jsonl). Mỗi dạng câu trong [research/intents.md](research/intents.md) có ít nhất một ví dụ. JSON schema đưa cho LLM: [datamate/contracts/schemas/query_plan.schema.json](../datamate/contracts/schemas/query_plan.schema.json). Sửa model thì chạy lại `python -m datamate.contracts.export_schema`.
