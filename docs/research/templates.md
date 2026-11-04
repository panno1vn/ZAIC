# Mẫu câu hỏi của train (T1)

**Mục đích.** Đề DataMate sinh câu hỏi theo mẫu: điền tên hàng, số, ngày vào vài trăm khuôn câu. T1 gom 3000 câu train thành các cụm mẫu câu để có hai thứ:
- **danh sách việc của T3**, xếp theo số câu mà mỗi hàm tính đem lại;
- **thước đo độ phủ**: bao nhiêu phần trăm câu train rơi vào mẫu đã có hàm.

Chỉ dùng train, không đọc câu hỏi public hay private (thể lệ §4.2).

Lệnh: `python tools/research/templates.py [--llm-url http://127.0.0.1:8091]`. Kết quả gồm:
- `assets/plans/templates_train.json`: cụm → id câu, câu đại diện, dạng plan, trạng thái hàm;
- phần bảng của file này (giữa hai dấu mốc AUTO).

Code chuẩn hoá nằm ở `datamate/nlu/templates.py`, để T4 (cổng "câu anh em") dùng lại lúc chạy thật.

## Cách làm và căn cứ

1. **Chuẩn hoá câu** (`template_text`):
   - Bỏ dấu, chữ thường.
   - **Gỡ lỗi gõ telex khi tắt bộ gõ**: "thangs" → "thang", "dduwowcj" → "duoc", "tawng/giamr" → "tang giam". Căn cứ: chữ Việt không dấu không bao giờ tận cùng bằng s, f, r, x, j. Khoảng 290 câu train (~10%) có từ như vậy, phần lớn là telex, một ít là tên hàng tiếng Anh. Tên hàng cũng qua cùng phép này nên vẫn khớp.
   - Che mọi số, ngày, tiền bằng `#`. Tiền ghi `# tien`.
   - Chỉ thay những viết tắt có **một nghĩa**: dthu, bn, hnay, hqua, trc, "bình quân" → "trung bình", "mấy" → "bao nhiêu", ko/k → "không".
   - Bỏ câu mở đầu, từ đệm và tên gọi của cửa hàng: "cho tôi biết", "xem giúp", "nhỉ", "z", "cửa hàng", "quán", "nhà thuốc".
   - **Không bỏ** từ làm đổi câu hỏi: "không" (hàng không bán được), "chi" (chi tiêu, chi phí), "thẻ", "tối". Đã kiểm ngữ cảnh của từng từ này trên train trước khi chọn.
2. **Che tên riêng** (`NameIndex`):
   - Lấy tên từ **dữ liệu của chính cửa hàng** đó. Vai trò của cột (mặt hàng `<SP>`, nhóm `<NHOM>`, khách `<KH>`, nhân viên `<NV>`, hoạt chất `<HC>`, nhà cung cấp `<NCC>`, nhóm khách `<NHOMKH>`) đoán theo tên cột.
   - **Cùng một luật cho cả 30 cửa hàng**, không theo id. Kế hoạch định dùng mapping tay cho 8 cửa hàng; luật chung đơn giản hơn và đã đủ tốt. Cột tên chung "TenGoi" của biz_123 lấy vai trò theo tên bảng.
   - Tên dài nhất được che trước.
   - **Tên một chữ chỉ che khi có từ báo trước**, ví dụ "nhóm trà", vì "trà" bỏ dấu trùng với "trả" trong "khách trả nợ".
   - Kênh bán và hình thức thanh toán **không che**: đây là bộ từ đóng (tại quầy, COD, tiền mặt…), để nguyên vẫn tách đúng mẫu.
3. **Gom cụm kiểu "câu đại diện"**:
   - Duyệt các dạng câu, dạng nhiều câu nhất trước, rồi theo thứ tự chữ cái, nên chạy lại ra đúng kết quả cũ.
   - Mỗi dạng vào cụm của câu đại diện giống nhất nếu điểm ≥ 90; không thì tự làm đại diện của cụm mới.
   - **Đổi `token_set_ratio` (kế hoạch) sang `token_sort_ratio`.** Căn cứ:
     - `token_set_ratio` cho 100 điểm khi mọi từ của câu này nằm trong câu kia. "số đơn" và "số đơn bị huỷ" vì thế thành một cụm; đây đúng là rủi ro kế hoạch đã nêu (có test `test_token_set_ratio_would_merge_a_template_with_its_extension`).
     - Đo ở ngưỡng 90 trước khi tách: `token_set_ratio` ra 196 cụm, trong đó **44 cụm** có plan viết tay khác nhau. `token_sort_ratio` ra 448 cụm, chỉ **6 cụm** như vậy, và cả 6 chỉ khác kiểu kỳ hoặc `k`.
4. **Tách cụm lẫn**:
   - **Theo kiểu đáp án của train.** "5 khách mua nhiều tiền nhất" (list) và "khách nào mua nhiều tiền nhất" (string) chỉ khác nhau một con số đã bị che. Trước khi tách có 38 cụm lẫn kiểu đáp án. Phần lớn là câu `unanswerable` (kỳ hỏi nằm ngoài dữ liệu), mà đó là chuyện của dữ liệu chứ không phải của mẫu câu, nên `unanswerable` không làm tách cụm.
   - **Theo dạng plan viết tay khác nhau**, không tính kiểu kỳ, vì một hàm tính phục vụ mọi kiểu kỳ (G4 tính kỳ).
   - Câu không có nhãn đi theo câu có nhãn giống nó nhất.
   - Việc tách theo đáp án chỉ dùng để phân tích train. Lúc chạy thật, T4 so dạng plan; dạng plan có `k` nên vẫn tách được hai trường hợp trên.
   - Ngưỡng 90 cân bằng nhất giữa số cụm và độ phủ:

     | Ngưỡng | Số cụm | Câu trong cụm ≥ 2 câu | Cụm phải tách |
     |---|---:|---:|---:|
     | 85 | 352 | 96,8% | 27 |
     | **90** | **450** | **95,3%** | **10** |
     | 95 | 670 | 89,9% | 2 |

     Ngưỡng 95 không đạt tiêu chí ≥ 95%. Ngưỡng 85 phải tách nhiều hơn, tức là gộp nhầm nhiều hơn.
5. **Gắn plan cho cụm**, theo thứ tự ưu tiên:
   1. plan viết tay (123 plan của `assets/plans`);
   2. plan LLM (Qwen3-8B, như K3) của câu đại diện;
   3. plan của baseline (bộ đọc bằng luật).

   Với cụm không có plan tay, LLM đọc 2 câu: câu đại diện và câu **ít giống nó nhất**. Hai plan khác dạng thì cụm bị đánh dấu để xem tay.
6. **Trạng thái hàm**:
   - **có**: `datamate/metrics` đã đăng ký hàm cho (loại câu, chỉ số, đối tượng) và hàm nhận đủ bộ lọc. Đây là mức registry: hàm vẫn có thể từ chối một biến thể, ví dụ nhiều measure.
   - **T3**: chỉ số nhóm bán hàng còn thiếu.
   - **v2**: công nợ, nhập hàng, kho, lãi, giá bán, luật theo ngành.

## Kết quả

<!-- BEGIN AUTO -->
*Sinh bằng `python tools/research/templates.py` (ngưỡng 90, `token_sort_ratio`). Phần giữa hai dấu mốc AUTO được ghi đè mỗi lần chạy.*

| Chỉ số | Giá trị |
|---|---:|
| Số câu train | 3000 |
| Dạng câu sau chuẩn hoá (khác nhau từng chữ) | 880 |
| Số cụm mẫu câu | 450 |
| Câu nằm trong cụm ≥ 2 câu | 2858 (95.3%) |
| Câu nằm trong cụm có mặt ở ≥ 2 cửa hàng | 94.1% |
| Cụm tách ra vì kiểu đáp án hoặc plan viết tay khác nhau | 10 |
| Câu nằm trong cụm có plan viết tay | 51.2% |
| Câu nằm trong cụm có plan LLM (không có plan tay) | 47.7% |
| Câu nằm trong cụm chỉ có plan baseline | 0.0% |
| Cụm có 2 plan LLM khác dạng | 16 / 172 |

**Trạng thái hàm tính** (số câu train nằm trong cụm có trạng thái đó):

| Trạng thái | Câu | Tỉ lệ |
|---|---:|---:|
| đã có hàm trong `datamate/metrics` | 908 | 30.3% |
| chưa có, nhóm bán hàng (T3) | 1656 | 55.2% |
| chưa có, nhóm v2 (công nợ, nhập, kho, lãi, giá, theo ngành) | 395 | 13.2% |
| ngoài phạm vi | 7 | 0.2% |
| chưa rõ (cụm chưa có plan) | 34 | 1.1% |

### Dạng plan (bỏ kiểu kỳ), xếp theo số câu: danh sách việc của T3 / v2

| # | Dạng plan | Câu | Cụm | Cửa hàng | Trạng thái | Cộng dồn |
|---:|---|---:|---:|---:|---|---:|
| 1 | `value \| revenue` | 535 | 29 | 30 | có | 17.8% |
| 2 | `value \| avg_order_value` | 167 | 9 | 23 | T3 | 23.4% |
| 3 | `value \| order_count` | 159 | 27 | 26 | có | 28.7% |
| 4 | `value \| cancel_rate` | 140 | 4 | 22 | T3 | 33.4% |
| 5 | `value \| quantity[product]/unit` | 138 | 14 | 29 | T3 | 38.0% |
| 6 | `rank \| day by revenue k=1 desc` | 126 | 3 | 29 | có | 42.2% |
| 7 | `value \| cancel_count` | 100 | 5 | 18 | T3 | 45.5% |
| 8 | `compare \| revenue \| vs previous pct_change` | 97 | 3 | 20 | T3 | 48.7% |
| 9 | `share \| revenue[product_group]` | 86 | 4 | 18 | T3 | 51.6% |
| 10 | `compare \| quantity[product]/unit \| vs before_days_from pct_change` | 83 | 7 | 12 | T3 | 54.4% |
| 11 | `value \| revenue[product]` | 79 | 6 | 24 | T3 | 57.0% |
| 12 | `value \| purchase_avg_cost[product]/unit` | 63 | 4 | 14 | v2 | 59.1% |
| 13 | `value \| unit_price[product]/unit` | 63 | 5 | 29 | v2 | 61.2% |
| 14 | `rank \| product by quantity k=k desc` | 59 | 18 | 22 | có | 63.2% |
| 15 | `compare \| revenue \| vs previous_same_days pct_change` | 57 | 3 | 12 | T3 | 65.1% |
| 16 | `value \| revenue[product_group]` | 50 | 3 | 18 | T3 | 66.7% |
| 17 | `rank \| customer by revenue k=k desc` | 46 | 9 | 20 | T3 | 68.3% |
| 18 | `value \| quantity[size]/unit` | 46 | 5 | 5 | T3 | 69.8% |
| 19 | `value \| stock_qty[product]/unit` | 46 | 13 | 15 | v2 | 71.3% |
| 20 | `value \| revenue[active_ingredient]` | 45 | 4 | 6 | T3 | 72.8% |
| 21 | `value \| purchase_amount` | 41 | 6 | 10 | v2 | 74.2% |
| 22 | `value \| revenue[shift]` | 38 | 12 | 10 | T3 | 75.5% |
| 23 | `value \| debt_paid` | 35 | 4 | 8 | v2 | 76.6% |
| 24 | `(chưa có plan)` | 34 | 14 | 11 | chưa rõ | 77.8% |
| 25 | `list_items \| product unsold_in_period count` | 33 | 9 | 5 | T3 | 78.9% |
| 26 | `rank \| product by quantity k=1 desc` | 29 | 10 | 16 | có | 79.8% |
| 27 | `count_where \| order revenue gte` | 28 | 4 | 10 | T3 | 80.8% |
| 28 | `rank \| customer by revenue k=1 desc` | 27 | 9 | 17 | T3 | 81.7% |
| 29 | `value \| revenue[customer_group]` | 23 | 9 | 7 | T3 | 82.4% |
| 30 | `compare \| revenue \| vs same_period_last_year pct_change` | 22 | 4 | 11 | T3 | 83.2% |
| 31 | `series \| revenue` | 22 | 5 | 12 | T3 | 83.9% |
| 32 | `share \| revenue[customer_group]` | 22 | 7 | 9 | T3 | 84.6% |
| 33 | `share \| revenue[prescription]` | 22 | 6 | 6 | T3 | 85.4% |
| 34 | `value \| revenue[prescription]` | 22 | 6 | 6 | T3 | 86.1% |
| 35 | `trend \| revenue` | 21 | 3 | 11 | T3 | 86.8% |
| 36 | `value \| debt_added[customer] + debt_paid[customer]` | 21 | 6 | 5 | v2 | 87.5% |
| 37 | `count_where \| customer order_count gte` | 20 | 3 | 9 | T3 | 88.2% |
| 38 | `compare \| revenue[shift] \| vs filter[shift] pct_change` | 19 | 7 | 8 | T3 | 88.8% |
| 39 | `count_where \| day revenue gte` | 18 | 3 | 7 | T3 | 89.4% |
| 40 | `value \| debtor_count` | 18 | 3 | 6 | v2 | 90.0% |
| 41 | `rank \| customer by debt_amount k=k desc +values` | 16 | 3 | 7 | v2 | 90.5% |
| 42 | `rank \| month by revenue k=1 desc` | 16 | 5 | 8 | T3 | 91.1% |
| 43 | `value \| delivery_count` | 16 | 5 | 2 | v2 | 91.6% |
| 44 | `value \| order_count[shift]` | 15 | 11 | 10 | T3 | 92.1% |
| 45 | `rank \| customer by order_count k=1 desc` | 14 | 4 | 9 | T3 | 92.6% |
| 46 | `value \| stock_qty[product]/unit + stock_qty[product]/unit` | 14 | 7 | 6 | v2 | 93.0% |
| 47 | `value \| quantity/unit` | 13 | 5 | 8 | T3 | 93.5% |
| 48 | `value \| revenue[channel] + revenue[channel]` | 13 | 5 | 7 | T3 | 93.9% |
| 49 | `value \| revenue[payment_method] + revenue[payment_method]` | 12 | 8 | 7 | T3 | 94.3% |
| 50 | `count_where \| product order_presence gte` | 11 | 4 | 5 | T3 | 94.7% |
| 51 | `value \| debt_total` | 10 | 2 | 6 | v2 | 95.0% |
| 52 | `value \| revenue[employee]` | 10 | 4 | 4 | T3 | 95.3% |
| 53 | `share \| revenue[channel]` | 9 | 4 | 6 | T3 | 95.6% |
| 54 | `count_where \| customer order_count gte as_share` | 8 | 2 | 5 | T3 | 95.9% |
| 55 | `value \| gross_profit` | 8 | 3 | 4 | v2 | 96.2% |
| 56 | `value \| revenue[payment_method]` | 8 | 5 | 4 | T3 | 96.4% |
| 57 | `count_where \| product order_count gte` | 7 | 1 | 4 | T3 | 96.7% |
| 58 | `out_of_scope` | 7 | 7 | 6 | ngoài phạm vi | 96.9% |
| 59 | `rank \| employee by revenue k=1 desc` | 7 | 3 | 4 | T3 | 97.1% |
| 60 | `rank \| product by gross_profit k=1 desc` | 7 | 3 | 3 | v2 | 97.4% |
| 61 | `value \| quantity[unit]` | 6 | 5 | 4 | T3 | 97.6% |
| 62 | `value \| debt_total[debt_age_days]` | 5 | 3 | 4 | v2 | 97.7% |
| 63 | `value \| nearest_expiry[product]` | 5 | 3 | 2 | v2 | 97.9% |
| 64 | `compare \| order_count[shift] \| vs filter[shift] pct_change` | 4 | 2 | 3 | T3 | 98.0% |
| 65 | `rank \| supplier by purchase_amount k=1 desc` | 4 | 3 | 3 | v2 | 98.2% |
| 66 | `share \| revenue[payment_method]` | 4 | 1 | 4 | T3 | 98.3% |
| 67 | `value \| revenue[channel]` | 4 | 2 | 3 | T3 | 98.4% |
| 68 | `value \| stock_qty[product]/unit/split` | 4 | 1 | 1 | v2 | 98.6% |
| 69 | `value \| stock_value` | 4 | 2 | 4 | v2 | 98.7% |
| 70 | `list_items \| product expiring_within` | 3 | 1 | 3 | v2 | 98.8% |
| 71 | `list_items \| product expiring_within count` | 3 | 2 | 2 | v2 | 98.9% |
| 72 | `value \| customer_count[customer]` | 3 | 3 | 3 | T3 | 99.0% |
| 73 | `value \| revenue[customer]` | 3 | 2 | 3 | T3 | 99.1% |
| 74 | `share \| revenue[channel] \| of revenue` | 2 | 1 | 1 | T3 | 99.2% |
| 75 | `value \| avg_order_value[customer_group]` | 2 | 1 | 2 | T3 | 99.2% |
| 76 | `value \| debtor_count[debt_age_days.gt]` | 2 | 1 | 2 | v2 | 99.3% |
| 77 | `value \| net_profit` | 2 | 2 | 1 | v2 | 99.4% |
| 78 | `compare \| order_count[order_status] + order_count[order_status] \| vs previous pct_change` | 1 | 1 | 1 | T3 | 99.4% |
| 79 | `compare \| quantity[product]/unit/avg_per_day \| vs before_days_from pct_change` | 1 | 1 | 1 | T3 | 99.4% |
| 80 | `compare \| revenue \| vs before_tet pct_change` | 1 | 1 | 1 | T3 | 99.5% |
| 81 | `compare \| revenue[customer] \| vs previous[customer] pct_change` | 1 | 1 | 1 | T3 | 99.5% |
| 82 | `compare \| revenue[product] \| vs same_period_last_year pct_change` | 1 | 1 | 1 | T3 | 99.5% |
| 83 | `compare \| revenue[shift] + revenue[shift] \| vs filter[shift] pct_change` | 1 | 1 | 1 | T3 | 99.6% |
| 84 | `count_where \| order order_count eq` | 1 | 1 | 1 | T3 | 99.6% |
| 85 | `list_items \| product out_of_stock_end_of_day` | 1 | 1 | 1 | v2 | 99.6% |
| 86 | `rank \| product by revenue k=k desc \| revenue[product]` | 1 | 1 | 1 | T3 | 99.7% |
| 87 | `share \| revenue` | 1 | 1 | 1 | T3 | 99.7% |
| 88 | `share \| revenue[channel] + revenue` | 1 | 1 | 1 | T3 | 99.7% |
| 89 | `share \| revenue[payment_method] + revenue` | 1 | 1 | 1 | T3 | 99.8% |
| 90 | `value \| cancel_count[category]` | 1 | 1 | 1 | T3 | 99.8% |
| 91 | `value \| debt_total[debt_age_days.gt]` | 1 | 1 | 1 | v2 | 99.8% |
| 92 | `value \| debt_total[order_status]/split` | 1 | 1 | 1 | v2 | 99.9% |
| 93 | `value \| purchase_amount[product] + revenue[product]` | 1 | 1 | 1 | v2 | 99.9% |
| 94 | `value \| quantity[product,size]/unit` | 1 | 1 | 1 | T3 | 99.9% |
| 95 | `value \| quantity[unit]/unit` | 1 | 1 | 1 | T3 | 100.0% |
| 96 | `value \| stock_qty[expiry_within_days]` | 1 | 1 | 1 | v2 | 100.0% |

### 60 cụm lớn nhất

| Cụm | Câu | Cửa hàng | Câu đại diện | Dạng plan | Nguồn plan | Hàm |
|---|---:|---:|---|---|---|---|
| T001 | 89 | 20 | thang 6/2025 ti le don bi huy la bn phan tram | `value \| cancel_rate` | tay | T3 |
| T002 | 76 | 28 | tong dthu thang 8 nam 2025 la bao nhieu | `value \| revenue` | tay | có |
| T003 | 61 | 26 | Tháng 5/2025 cửa hàng bán đc tổng cộng bao nhiêu tiền? | `value \| revenue` | tay | có |
| T004 | 53 | 16 | Doanh thu hôm qua của cửa hàng là bao nhiêu? | `value \| revenue` | LLM | có |
| T005 | 53 | 26 | Doanh thu ngày nào cao nhất trong tháng 7 năm 2026? | `rank \| day by revenue k=1 desc` | tay | có |
| T006 | 51 | 24 | Cho tôi biết doanh thu tháng 3/2026. | `value \| revenue` | LLM | có |
| T007 | 46 | 21 | tháng 4/2026 bans Bột ngọt Ajinomoto 400g được bao nhiêu tieenf | `value \| revenue[product]` | tay | T3 |
| T008 | 45 | 17 | Doanh thu trung bình trên một đơn tháng 3/2025 là bao nhiêu ạ? | `value \| avg_order_value` | LLM | T3 |
| T009 | 45 | 17 | Cho mình hỏi trung bình mỗi đơn tháng 7/2025 mang về bao nhiêu doanh thu? | `value \| avg_order_value` | tay | T3 |
| T010 | 44 | 24 | thang 2/2026 ngay nao cua hang ban dc nhiu tien nhat | `rank \| day by revenue k=1 desc` | LLM | có |
| T011 | 41 | 16 | Cho mình hỏi so với tháng trước đó, doanh thu tháng 2/2026 tăng hay giảm mấy phần trăm? | `compare \| revenue \| vs previous pct_change` | tay | T3 |
| T012 | 40 | 24 | Doanh thu tháng 4/2026 bao nhiêu? | `value \| revenue` | LLM | có |
| T013 | 39 | 20 | trong thang 4 nam 2025 cua hang ban duoc may dia rau can xao toi | `value \| quantity[product]/unit` | tay | T3 |
| T014 | 37 | 16 | Tháng 2/2025 doanh thu thay đổi bao nhiêu % so với tháng liền trước? | `compare \| revenue \| vs previous pct_change` | LLM | T3 |
| T015 | 35 | 19 | gias trị trung bình một đơn thangs 4/2026 là bao nhiêu | `value \| avg_order_value` | LLM | T3 |
| T016 | 35 | 20 | soos kg nếp cái hoa vàng bán đươc trong thangs 9/2025 là bn | `value \| quantity[product]/unit` | tay | T3 |
| T017 | 35 | 11 | Cho mình hỏi so với cùng kỳ tháng trước, doanh thu từ đầu tháng này đến hết hôm nay tăng hay giảm bao nhiêu %? | `compare \| revenue \| vs previous_same_days pct_change` | tay | T3 |
| T018 | 35 | 18 | thang 9/2025 cua hang co bnhiu % don bi huy | `value \| cancel_rate` | LLM | T3 |
| T019 | 29 | 12 | thang 10/2025 bi huy may don | `value \| cancel_count` | tay | T3 |
| T020 | 29 | 10 | Tháng 5/2026 giá nhập bình quân một hộp Bánh croissant là bao nhiêu vậy? | `value \| purchase_avg_cost[product]/unit` | tay | v2 |
| T021 | 29 | 16 | trong thang 5/2026, xet theo dthu, ngay nao ban dat nhat | `rank \| day by revenue k=1 desc` | tay | có |
| T022 | 28 | 17 | Cho tôi biết doanh thu hôm qua. | `value \| revenue` | tay | có |
| T023 | 27 | 19 | gia ban mot ly soda chanh day (m) vao ngay 01/12/2025 la bn | `value \| unit_price[product]/unit` | tay | v2 |
| T024 | 27 | 15 | cho hỏi tháng 8/2026 nhóm sắt thép bán đc bao nhiêu tiền | `value \| revenue[product_group]` | tay | T3 |
| T025 | 26 | 14 | đếm số đơn đã huỷ trong tháng 12/2025 | `value \| cancel_count` | tay | T3 |
| T026 | 26 | 9 | Trung bình mỗi đơn tuần trước mang về bao nhiêu dthu? | `value \| avg_order_value` | tay | T3 |
| T027 | 25 | 13 | ê doanh thu nhoms hàng sinh tố chiếm bao nhiêu % tổng doanh thu thangs 9 năm 2025 | `share \| revenue[product_group]` | tay | T3 |
| T028 | 25 | 16 | thang 6/2025 ban ra bnhiu kg nep cai hoa vang | `value \| quantity[product]/unit` | tay | T3 |
| T029 | 25 | 17 | thang 4/2026 mat hang ngheu hap sa thu ve bn tien | `value \| revenue[product]` | LLM | T3 |
| T030 | 24 | 12 | hom qua cua hang ban duoc bao nhiu tien | `value \| revenue` | LLM | có |
| T031 | 24 | 9 | So số ly Latte (L) bán ra trong 30 ngày kể từ ngày 05/02/2026, ngày tăng giá lên 53.500đ, với 30 ngày ngay trước ngày đó: tăng hay giảm bao nhiêu %? | `compare \| quantity[product]/unit \| vs before_days_from pct_change` | tay | T3 |
| T032 | 24 | 17 | Tháng 4/2026 mặt hàng Nếp cái hoa vàng bán được tổng cộng bao nhiêu kg? | `value \| quantity[product]/unit` | tay | T3 |
| T033 | 24 | 14 | Tỉ trọng của nhóm gỏi trong doanh thu tháng 12/2025 là bao nhiêu %? | `share \| revenue[product_group]` | tay | T3 |
| T034 | 22 | 13 | revenue hnay la bao nhiu | `value \| revenue` | LLM | có |
| T035 | 21 | 8 | Từ đầu tháng này đến hết hôm nay, doanh thu hơn hay kém cùng kỳ tháng trước mấy %? | `compare \| revenue \| vs previous_same_days pct_change` | tay | T3 |
| T036 | 20 | 11 | Cho hỏi số đơn bị huỷ trong tháng 8 năm 2025 là bao nhiêu? | `value \| cancel_count` | tay | T3 |
| T037 | 20 | 13 | Tổng doanh thu trong ngày hôm nay là bao nhiêu? | `value \| revenue` | LLM | có |
| T038 | 20 | 13 | trong thang 4/2025, nhom tieu hoa dong gop bnhiu % doanh thu ca cua hang | `share \| revenue[product_group]` | tay | T3 |
| T039 | 19 | 12 | Doanh thu tháng 11/2025 hơn hay kém tháng trước bao nhiêu phần trăm? | `compare \| revenue \| vs previous pct_change` | tay | T3 |
| T040 | 18 | 13 | hnay cua hang ban dc bao nhiu tien vay | `value \| revenue` | tay | có |
| T041 | 18 | 14 | Cho hỏi tổng doanh thu quý 2/2026 là bao nhiêu? | `value \| revenue` | LLM | có |
| T042 | 18 | 12 | Trong quý 3 năm 2025, doanh thu của cửa hàng được bao nhiêu tiền ạ? | `value \| revenue` | tay | có |
| T043 | 18 | 10 | trong thang 9/2025, cua hang co may don o trang thai huy | `value \| cancel_count` | tay | T3 |
| T044 | 17 | 12 | Xem giúp tháng 2/2026 nhóm hải sản chiếm bao nhiêu % doanh thu? | `share \| revenue[product_group]` | LLM | T3 |
| T045 | 16 | 9 | doanh thu 30 ngày gần nhất của cửa hangf là bao nhiêu | `value \| revenue` | LLM | có |
| T046 | 16 | 10 | Từ ngày 16/03/2025, Fugacar 500mg hộp 1 viên tăng giá lên 23.000đ. So 7 ngày kể từ ngày 16/03/2025 với 7 ngày ngay trước đó, số viên bán ra thay đổi bao nhiêu phần trăm nhỉ? | `compare \| quantity[product]/unit \| vs before_days_from pct_change` | tay | T3 |
| T047 | 15 | 10 | Giá nhập bình quân một hộp Oresol 245 DHG hộp 20 gói trong tháng 2 năm 2026 là bao nhiêu ạ? | `value \| purchase_avg_cost[product]/unit` | tay | v2 |
| T048 | 15 | 11 | Xem giúp ngày 15/04/2025 cửa hàng bán Ếch chiên nước mắm với đơn giá bao nhiêu một đĩa? | `value \| unit_price[product]/unit` | LLM | v2 |
| T049 | 15 | 10 | soos đơn hoom nay là bao nhiêu | `value \| order_count` | tay | có |
| T050 | 15 | 6 | coi gium thuoc co hoat chat Vitamin C thang 8/2026 ban duoc tong cong bao nhieu tien | `value \| revenue[active_ingredient]` | LLM | T3 |
| T051 | 15 | 14 | Trong tháng này, tỉ lệ đơn huỷ là bao nhiêu phần trăm? | `value \| cancel_rate` | tay | T3 |
| T052 | 14 | 9 | nhang quảng trí bó đổi giá từ 26.000đ lên 27.500đ vào ngày 24/01/2026. 7 ngày kể từ ngày đó bán được nhiều hay ít hơn 7 ngày liền trước bao nhiu %, tính theo bó | `compare \| quantity[product]/unit \| vs before_days_from pct_change` | LLM | T3 |
| T053 | 14 | 8 | Doanh thu từ đầu năm tới hết hnay là bao nhiêu? | `value \| revenue` | tay | có |
| T054 | 14 | 7 | hom qua co tong cong bao nhiu don | `value \| order_count` | LLM | có |
| T055 | 14 | 6 | thang 11/2025 cac thuoc co hoat chat natri clorid ban dc bnhiu tien z | `value \| revenue[active_ingredient]` | LLM | T3 |
| T056 | 14 | 8 | e tinh tu ngay 1/1 den het hnay, dthu nam nay la bn | `value \| revenue` | LLM | có |
| T057 | 14 | 6 | Trong tháng 1/2025, Mì Omachi sườn hầm nhập vào giá bình quân một thùng là bao nhiêu ạ? | `value \| purchase_avg_cost[product]/unit` | tay | v2 |
| T058 | 13 | 9 | Cho tôi biết số đơn hôm qua. | `value \| order_count` | tay | có |
| T059 | 13 | 5 | thang 6/2025 quan ban ra tong cong may ly size m, cong tat ca cac mon | `value \| quantity[size]/unit` | LLM | T3 |
| T060 | 13 | 8 | Tính riêng ngày hôm nay, cửa hàng bán đc bao nhiêu đơn hàng? | `value \| order_count` | tay | có |
<!-- END AUTO -->

## Nhận xét (viết tay, 03/11, phiên 3)

**1. Đề rất "theo mẫu", và mẫu dùng chung giữa các cửa hàng.**
- 3000 câu gom về 450 cụm. 95,3% câu nằm trong cụm ≥ 2 câu.
- 94,1% câu nằm trong cụm có mặt ở ≥ 2 cửa hàng. Vì vậy mẫu học được trên train nhiều khả năng gặp lại ở private.
- Nếu gom theo dạng plan thì chỉ **46 dạng đầu đã chiếm 93% câu**.

**2. Tỉ lệ câu train nằm trong cụm đã có hàm: 30,3%.** Đây là cận trên, đo ở mức registry (N6). Số thật hiện nay với mapping tay là 113/790 câu trả lời đúng (14%), vì các hàm hiện có chưa nhận bộ lọc và chỉ có 8 cửa hàng có mapping.

**3. Danh sách việc cho T3** (nhóm bán hàng, 55,2% câu), xếp theo số câu, đối chiếu với các nhóm A–F của kế hoạch:

| Thứ tự | Việc | Câu train | Nhóm |
|---:|---|---:|---|
| 1 | `avg_order_value` | 167 | A |
| 2 | `cancel_rate`, `cancel_count` | 140 + 100 | A |
| 3 | `quantity` theo đơn vị, có lọc mặt hàng hoặc size | 138 + 46 | C |
| 4 | Bộ lọc dùng chung cho `revenue`: mặt hàng, nhóm, hoạt chất, ca, nhóm khách, kê đơn | 79 + 50 + 45 + 38 + 23 + 22 | A |
| 5 | `compare` theo kỳ: previous, previous_same_days, same_period_last_year | 97 + 57 + 22 | B |
| 6 | `share`: nhóm hàng, nhóm khách, kê đơn, kênh | 86 + 22 + 22 + … | B |
| 7 | **Hiệu ứng tăng giá**: `compare quantity vs before_days_from` | 83 | B |
| 8 | Xếp hạng khách theo doanh thu / số đơn | 46 + 27 + 14 | D |
| 9 | Đếm theo ngưỡng (đơn, ngày, khách), `trend`, `series`, tháng cao nhất | 28 + 18 + 20 + 21 + 22 + 16 | E |
| 10 | Hàng ế đếm số | 33 | F |

- Việc 7 lớn hơn dự tính, nên **xếp vào T3**. Kỳ `days_from` kèm ngày thì G4 đã tính được; `anchor_price` vẫn còn thiếu.
- Một số việc v2 có nhiều câu hơn phần lớn việc T3, và hàm của chúng đơn giản. **Đề xuất làm ngay sau T3**, trước luật theo ngành:
  - `purchase_avg_cost`: 63 câu, giá nhập bình quân theo số lượng nhập (rulebook dòng 65);
  - `unit_price`: 63 câu, giá bán ngày D;
  - `stock_qty`: 60 câu;
  - `purchase_amount`: 41 câu;
  - `debt_paid`: 35 câu.

**4. LLM đọc sai một số mẫu, đã bổ sung plan tay.** Trước khi bổ sung có 4 lỗi đáng kể:
- "giá **nhập** bình quân một hộp X" (63 câu) bị đọc thành `avg_order_value` lọc theo mặt hàng. Lỗi này **làm lệch danh sách việc**: 63 câu v2 bị tính sang T3.
- "doanh thu thuốc **hoạt chất** X" bị đọc thành lọc theo tên hàng.
- "**bao nhiêu mặt hàng** không bán được cái nào" bị đọc thành số lượng.
- "tính **riêng** ngày hôm nay" (21 câu) bị **bịa bộ lọc** `order_status=completed`. Bước kiểm tra bộ lọc có căn cứ đã loại các plan này, nên câu bỏ trống chứ không bị trả lời sai.

Cách xử lý:
- Viết tay 26 plan cho câu đại diện của các cụm này: [assets/plans/t1_reps.jsonl](../../assets/plans/t1_reps.jsonl). Mỗi plan đã đối chiếu với kiểu đáp án của train, và với rulebook ở những chỗ có luật (nhân viên bán giỏi nhất tính theo doanh thu; giá nhập bình quân).
- File nằm trong `assets/plans`, nên cũng vào **kho ví dụ BM25**: 123 → 149 plan. Từ giờ LLM có ví dụ gần cho các mẫu này.
- Lưu ý: `python -m datamate.eval.k3` giờ chấm trên 149 câu, nên số mới không so thẳng được với 83,7% của K3 (đo trên 123 câu).

**5. Còn mở:**
- 34 câu (14 cụm hiếm) chưa có plan.
- 16/172 cụm có hai plan LLM khác dạng. Đã xem tay: plan của câu đại diện (plan được dùng) đúng ở phần lớn các cụm.
- Plan LLM chưa được kiểm bằng đáp án (N5, việc của T4).

## Cách dùng tiếp
- **T3:** làm theo bảng "Dạng plan" ở trên. Mỗi hàm xong thì chạy lại script để số "đã có hàm" tăng.
- **T4:**
  - Cổng "câu anh em" dùng `template_text` + `plan_shape` của `datamate/nlu/templates.py`.
  - `assets/plans/templates_train.json` cho biết câu train nào cùng mẫu, để chọn câu đã kiểm chứng.
  - Lúc chạy thật, `NameIndex` nên lấy tên từ bảng chuẩn hoá (N8).
