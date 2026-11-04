# Nối tên trong câu hỏi với dữ liệu (T2 / G6)

*Phiên 3, ngày thật 03/11. Code: [datamate/nlu/linking.py](../../datamate/nlu/linking.py). Từ điển: [assets/linking/synonyms.json](../../assets/linking/synonyms.json). Lệnh đo: `python -m datamate.eval.linking [--llm-url …] --out outputs/linking/run.jsonl`.*

## Làm gì
Plan ghi tên **như trong câu hỏi**, ví dụ "nước ép dưa hấu (l)", "tại quầy", "bình anh". Linking đổi mỗi tên thành **giá trị mà hàm tính dùng để lọc** và ghi vào `ResolvedPlan.linked`:

| Trường | Nối về | Lấy ứng viên từ |
|---|---|---|
| product | **mã hàng** (`product_key`). Một nhà thuốc train có 162 tên cho 80 mã | tên và mã ở `lines`, `products` |
| customer | mã khách | tên và mã ở `customers`, `orders` |
| employee | giá trị ghi trên đơn (mã hoặc tên) | `orders.employee`; bảng `employees` (tên → mã) chỉ khi đơn ghi mã |
| product_group, active_ingredient, customer_group, category, brand, supplier… | chính giá trị trong dữ liệu | cột tương ứng |
| channel, payment_method | **mã**: store / phone / zalo_oa; cash / transfer / ewallet / cod / debt | từ điển đồng nghĩa |

Tên không nối được thì **không ghi** vào `linked`; khi đó [V] cho câu bỏ trống (`entities_ok = False`).

## Thuật toán
So sánh trên chữ đã chuẩn hoá: bỏ dấu, gỡ lỗi gõ telex, bỏ dấu câu. Dùng cùng hàm `tokens` với T1.

1. **Khớp tuyệt đối** với một tên hoặc một mã.
2. **Tên đầy đủ có trong câu hỏi.** Đề sinh câu bằng cách chèn nguyên tên, nên nếu câu chứa nguyên văn một tên có thật thì tên đó là bằng chứng mạnh hơn chữ LLM chép lại. Nối khi một trong hai điều sau đúng:
   - tên đó chứa giá trị LLM ghi ("bình anh" → "Quách Bình Anh");
   - tên đó có chung ≥ 2 chữ và ≥ nửa số chữ với giá trị LLM ghi ("Nguyễn Mai Hiếu" → "Nghiêm Mai Hiếu").

   Câu có hai tên cùng hợp thì không nối.
3. **So khớp mờ** bằng `token_sort_ratio`: ngưỡng **90**, và phải hơn giá trị đứng thứ hai **≥ 5 điểm**.
   - Chọn `token_sort_ratio` vì nó phạt chữ thừa. `token_set_ratio` cho "bia tiger" khớp 100 điểm với cả "Bia Tiger lon" lẫn "Bia Tiger Bạc lon", như đã thấy ở T1.
   - Nhiều tên của cùng một mã chỉ tính là một ứng viên, nên không tự "ngang điểm" với chính mình.

Thêm hai quy tắc:
- **Tên hàng** được thử thêm một lần sau khi bỏ **đơn vị đếm có thật của cửa hàng** ở đầu ("bình Gas Petrolimex 12kg", "xe 4m3 cát xây tô"), vì LLM hay chép cả đơn vị câu hỏi đếm theo.
- **Kênh bán và thanh toán** nối qua từ điển. Dữ liệu train ghi theo hai kiểu, mã (`cash`) hoặc chữ (`Tiền mặt`, `Thu hộ (COD)`), và **có cột trộn cả hai** (biz_111). Vì vậy giá trị nối là mã. Hàm `linking.matches(field, cột, giá trị)` lọc đúng cả hai kiểu ghi; T3 lọc bằng hàm này, không so bằng `==`.
  - Từ điển chỉ có cách viết thấy được ở dữ liệu hoặc câu hỏi train: tại quầy, điện thoại, zalo; tiền mặt, tm, tiền tươi; chuyển khoản, ck; ví điện tử; COD, thu hộ; ghi nợ.
  - Thêm "trực tiếp", vì kế hoạch đã ghi sẵn.
  - Mã không có trong dữ liệu của cửa hàng thì không nối, ví dụ cửa hàng không có đơn trả bằng ví điện tử.

## Đo trên train (8 cửa hàng có mapping tay)
- **Câu được đo:** các câu thuộc mẫu (T1) có bộ lọc cần nối, tổng 220 câu.
- **Plan dùng để đo:** plan tay nếu có, không có thì plan của Qwen3-8B (kho 149 ví dụ). 4 câu LLM không cho plan.
- **Tổng cộng 231 giá trị bộ lọc.**

| Trường | n | Khớp tuyệt đối | Qua câu hỏi | Mờ | Không nối | Nối được |
|---|---:|---:|---:|---:|---:|---:|
| product | 150 | 145 | 5 | 0 | 0 | **100%** |
| customer | 17 | 12 | 4 | 0 | 1 | 94% |
| active_ingredient | 17 | 17 | 0 | 0 | 0 | 100% |
| channel | 14 | 12 | 0 | 0 | 2 | 86% |
| product_group | 14 | 14 | 0 | 0 | 0 | 100% |
| customer_group | 12 | 11 | 0 | 0 | 1 | 92% |
| payment_method | 4 | 2 | 0 | 0 | 2 | 50% |
| employee | 3 | 3 | 0 | 0 | 0 | 100% |

- **Mọi giá trị không nối được đều thuộc câu có đáp án `unanswerable`.** Đó là biz_105 không ghi kênh bán và thanh toán, "khách nữ" (giới tính) và "khách ở đường Trần Não" (địa chỉ). Bỏ trống ở đây là đúng; T3 / unanswerable sẽ quyết có trả lời `unanswerable` hay không.
- Mọi trường hợp nối không phải khớp tuyệt đối (9 giá trị) đã được xem tay, và cả 9 đều đúng.
- **Lần đo đầu** (chưa có hai quy tắc bỏ đơn vị và "chung nhiều chữ") bỏ sót 6 giá trị lẽ ra nối được, vì đáp án của chúng là số:
  - "bình Gas Petrolimex 12kg" (2 lần);
  - "xe 4m3 cat xay to";
  - "sinh tu bo";
  - "Nguyễn Mai Hiếu" (2 lần).

  Sau khi thêm hai quy tắc, cả 6 đều nối đúng. Có test hồi quy trong `tests/test_linking.py`.
- Chưa có đáp án chuẩn cho chính việc nối. Kiểm đúng / sai thật sự là ở T3: **câu đã nối mà trả lời sai phải là 0** (tiêu chí của kế hoạch).

## Lưu ý cho T3
- Lọc bằng giá trị trong `linked`. Với mặt hàng, lọc theo `product_key`; với kênh và thanh toán, lọc bằng `linking.matches`.
- **Nhóm khách:** đơn vãng lai (không có mã khách) **không thuộc nhóm nào, kể cả nhóm `lẻ`** (rulebook dòng 17).
- **Khách:** shop có mã khách thì hai mã trùng tên là hai khách (rulebook dòng 46). Linking không nối khi hai mã trùng tên.
