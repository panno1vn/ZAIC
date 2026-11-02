# Các loại câu hỏi (intent) trong 3000 câu train

Phân loại bằng luật từ khóa (`tools/research/analyze_questions.py`), nên số đếm là **ước lượng ±5%**: một số câu bị xếp nhầm nhóm, ví dụ câu tỉ trọng nhóm hàng có chữ "đóng góp" bị xếp vào công nợ. Mục đích là biết hợp đồng `QueryPlan` phải diễn đạt được những gì.

| Loại câu | Số câu | Kiểu đáp án chính | Ví dụ | Thông tin plan cần có |
|---|---:|---|---|---|
| Doanh thu (có/không lọc) | ~876 | number (804), list, percent | "Tháng 5/2025 cửa hàng bán đc tổng cộng bao nhiêu tiền?" | chỉ số, kỳ, bộ lọc (nhóm hàng, mặt hàng, hoạt chất, nhóm khách, kênh, hình thức TT, ca, nhân viên) |
| Số đơn | ~305 | number, list | "check gium hnay cua hang co bao nhiu don" | chỉ số, kỳ, bộ lọc |
| Đơn hủy (số đơn / tỉ lệ) | ~239 | percent (137), number (100) | "tỉ lệ huỷ đơn tháng 6/2025 là nhiêu %" | chỉ số `cancel_rate` hoặc `cancel_count` |
| Tăng trưởng % | ~199 | percent | "so cùng kỳ năm trước, doanh thu thangs 5/2026 tawng/giamr mấy %" | kỳ hỏi + **kỳ so** (kỳ trước, cùng kỳ năm trước, cùng số ngày tháng trước, trước Tết) hoặc **so giữa hai bộ lọc** (ca chiều vs ca sáng) |
| Số lượng bán | ~171 | number | "tháng 8/2025 quán bán đc bn ly size m" | mặt hàng hoặc **đơn vị** (ly, chai, kg…) hoặc size |
| Giá trị trung bình đơn | ~164 | number | "Trung bình mỗi đơn tuần trước mang về bao nhiêu dthu?" | chỉ số `avg_order_value` |
| Công nợ | ~150 | number, list, table | "Tính đến hết ngày 19/08/2026, có bao nhiêu khách còn nợ cửa hàng?" | kỳ dạng **tình trạng đến hết ngày X**; số khách nợ, tổng nợ, top-k nợ (table), nợ thêm / trả nợ của một khách (list 2 số) |
| Xếp hạng mặt hàng | ~148 | list, string, number | "3 mặt hàng bán chạy nhất tuần này là những mặt hàng nào?" | đối tượng, tiêu chí (số lượng, doanh thu, lãi, số đơn có mặt), k, chiều (chạy nhất / chậm nhất / không bán được) |
| Ngày/tháng cao nhất | ~140 | date | "Doanh thu ngày nào cao nhất trong tháng 7 năm 2026?" | đối tượng là **ngày / tháng / giờ**, tiêu chí |
| Tỉ trọng % | ~119 | percent | "Tháng 2/2026 nhóm hải sản chiếm bao nhiêu % doanh thu?" | tử số (bộ lọc) / mẫu số (tổng shop, hoặc tổng khách đã mua) |
| Nhập hàng | ~114 | number, string | "tháng này tổng giá trị các phiếu nhập hàng là bao nhiu" | tổng tiền nhập, giá nhập bình quân, nhà cung cấp chính |
| Xếp hạng khách | ~94 | list, string | "cho tooi 5 khách mua nhìu tiền nhất thangs 6/2026" | tiêu chí (doanh thu, số đơn, số ngày mua, TB đơn với ngưỡng ≥3 đơn, số đơn hủy) |
| Hiệu ứng tăng giá | ~70 | percent | "So số ly Latte (L) bán ra trong 30 ngày kể từ ngày 05/02/2026… với 30 ngày ngay trước ngày đó" | mặt hàng, ngày D, N ngày; so N ngày kể từ D với N ngày trước D |
| Tồn kho, lô, hạn dùng | ~50 | number, list, date | "Lô Oresol 245 DHG hộp 20 gói gần hết hạn nhất có hạn dùng ngày nào?" | tình trạng đến hết ngày X; tồn theo đơn vị lớn (list [lớn, lẻ]); lô gần hết hạn; hàng hết hạn trong N ngày |
| Giá bán ngày D | ~26 | number | "gia ban mot goi mi hao hao tom chua cay vao ngay 21/04/2026 la bn" | mặt hàng, ngày, đơn vị (chỉ có trong rulebook train) |
| Lãi, giá vốn | ~26 | number, string | "Cuối ngày 09/07/2026, tổng giá trị hàng còn trong kho tính theo giá vốn là bao nhiêu tiền?" | lãi gộp, giá trị tồn kho, hàng lời nhất |
| Tăng liên tục | ~21 | boolean | "Doanh thu có tăng liên tục qua 3 tháng 12/2025, 1/2026, 2/2026 không?" | **chuỗi kỳ** (danh sách tháng) |
| Đếm theo ngưỡng | ~18 | number | "số đơn có doanh thu ≥ 580.000 đồng là bao nhiêu?" | đối tượng đếm (đơn, ngày, mặt hàng, khách), chỉ số, phép so (≥, >, …), giá trị |
| Nhân viên | ~18 | number, string | "Tháng 2/2026 nhân viên mã NV001 bán được bao nhiêu tiền?" | lọc theo nhân viên; xếp hạng nhân viên |
| Số khách | ~15 | number, percent | "Trong số khách đã mua hàng tháng 3/2026, bao nhiêu phần trăm mua từ 4 đơn trở lên?" | đếm khách, tỉ lệ khách theo ngưỡng số đơn |
| Giao nhiều đợt | ~7 | number | "Giúp mình đếm số đợt giao hàng trong tháng 1/2026." | chỉ số riêng của ngành vật liệu xây dựng |
| Khác | ~29 | number | "Tháng 4/2026 xe đã giao tổng cộng mấy đợt hàng?" | phần lớn là giá bán ngày D và giao hàng diễn đạt khác |

## Những dạng dễ bị hợp đồng bỏ sót
- **Nhiều số đo trong một câu**: "lần lượt là bao nhiêu", "ghi hai số", "mỗi bên bao nhiêu". Đáp án là list số, đúng thứ tự câu hỏi nêu (87 câu train).
- **So sánh giữa hai bộ lọc thay vì hai kỳ**: ca chiều với ca sáng, COD với tiền mặt, khách đường A với khách đường B.
- **Chuỗi kỳ**: "3 tháng liền nhau kết thúc ở tháng 6/2025… mỗi tháng" (list), "tăng liên tục qua 3 tháng" (boolean), "xét 3 tháng 3/2025, 4/2025 và 5/2025, tháng nào lớn nhất" (date `YYYY-MM`).
- **Ngưỡng trên đối tượng khác nhau**: đơn có doanh thu ≥ X; ngày có doanh thu ≥ X; mặt hàng có mặt trong ≥ N đơn; khách có ≥ N đơn.
- **Tồn theo đơn vị lớn**: list `[số đơn vị lớn nguyên, số đơn vị cơ bản lẻ]`.
- **Câu ngoài phạm vi dữ liệu**: đánh giá chủ quan ("nhân viên nào lành nghề nhất"), kiến thức ngoài ("liều dùng mỗi lần mấy viên"). Đáp án là `unanswerable`.

## Hệ quả cho `QueryPlan`
1. `measures` là một **danh sách**, giữ thứ tự câu hỏi.
2. Phần so sánh (`compare`) phải nhận được **kỳ so** hoặc **bộ lọc so**.
3. Kỳ hỏi phải biểu diễn được một **chuỗi kỳ** (nhiều tháng).
4. Cần các khối riêng cho xếp hạng (`rank`) và cho ngưỡng (`threshold`), mỗi khối có trường chỉ rõ đối tượng.
5. Cần loại câu `out_of_scope` để LLM đánh dấu câu hỏi không thể trả lời từ dữ liệu.
6. Bộ lọc phải mở rộng được (size, hoạt chất, kê đơn, ca, thứ trong tuần…), vì bộ private có ngành mới.
