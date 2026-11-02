# Hạn chế và cách cải thiện

Danh sách việc phải sửa để tăng điểm. Ghi lại ngày 03/11 sau khi rà phần nghiên cứu và hợp đồng v0. Xong mục nào thì đánh dấu `[x]`, ghi ngày và người làm.

Mức độ: **Cao** = phải sửa trước khi khóa hợp đồng (tối T5 05/11) · **TB** = sửa trong tuần đầu sau chia vai · **Thấp** = sửa khi có thời gian.

## A. Lỗ hổng trong hợp đồng

### Mức cao

- [x] **H1. Danh sách chỉ số và bộ lọc chỉ lấy từ câu hỏi train, chưa lấy từ rulebook public.** *(xong 04/11, leader: bảng đối chiếu ở docs/contracts.md)*
  - Ảnh hưởng: rulebook public có luật cho 3 ngành mới mà hợp đồng chưa có chỉ số tương ứng:
    - Sửa xe: lượt xe, tỉ lệ bảo hành, số chiếc xe theo biển số, xe khách quen.
    - Mẹ và bé: tiền giảm voucher, tiền giảm nhờ điểm, phí ship, % theo size bỉm/số sữa, khách thành viên mới.
    - Điện thoại: khách phải trả, tiền thu máy cũ, kỳ góp quá hạn, tỉ lệ bảo hành, dòng máy, hãng.
    - Câu hỏi các ngành này chỉ rơi vào `other`, mà thư viện hàm không xử lý `other`, nên mất điểm nguyên nhóm câu.
  - Cách sửa: rà **từng dòng** rulebook public (§3 phần bổ sung, §6), dòng nào cần chỉ số hay bộ lọc mới thì thêm vào `Metric` / `FilterField` trong `datamate/contracts/plan.py`. Dùng rulebook là hợp lệ, vì đó là luật của đề chứ không phải đáp án test.
  - Kiểm chứng: mỗi dòng luật trong rulebook public đều chỉ ra được chỉ số hoặc bộ lọc nào phục vụ nó.

- [x] **H2. Câu hiệu ứng tăng giá có thể không ghi ngày.** *(xong 04/11: `PeriodExpr.anchor_price`)*
  - Ảnh hưởng: "Acemuc Kids… tăng giá lên 3.200đ: so 7 ngày kể từ ngày tăng…" không có ngày D. `PeriodExpr` kiểu `days_from` hiện **bắt buộc** `date`, nên LLM không viết được plan hợp lệ và câu này luôn bỏ trống. Có ~70 câu tăng giá trong train.
  - Cách sửa: cho phép mốc là "ngày tăng giá lên X đồng" (thêm trường `anchor_price`); code tự tìm ngày D trong bảng giá theo luật §5 (lần tăng đầu tiên lên đúng giá đó).
  - Kiểm chứng: viết được plan cho mọi câu tăng giá trong train.

- [x] **H3. `ColumnMap` chỉ chép thẳng một cột, không biến đổi được.** *(xong 04/11 ở hợp đồng: 8 biến đổi có tên trong `mapping.TRANSFORMS`; phần chạy thật do G2 cài)*
  - Ảnh hưởng: dữ liệu thật cần biến đổi ở nhiều chỗ:
    - Trạng thái nằm trong cột ghi chú ("khách trả lại").
    - Size nằm trong tên món "(M)".
    - Biển số dính với dòng xe "Vision 110 72B9-225.05".
    - Số lượng dính đơn vị "5 chai".
    - Năm lấy từ tên sheet.
    - Trạng thái ghi theo từng dòng nhưng phải gộp thành trạng thái của đơn.

    Thiếu những biến đổi này thì mapping tay lẫn mapping LLM đều bế tắc, và cửa hàng đó bỏ trống hết.
  - Cách sửa: thêm bộ biến đổi có tên, số lượng giới hạn, ví dụ `regex_extract`, `split_qty_unit`, `year_from_sheet`, `note_contains`, `order_status_from_lines`. Mapping gọi biến đổi theo tên, không viết code tự do.
  - Kiểm chứng: viết được mapping tay cho 8 cửa hàng train đa dạng mà không cần sửa code riêng cho từng cửa hàng.

- [x] **H4. Thiếu cách nói "trung bình mỗi ngày" và "liệt kê theo điều kiện".** *(xong 04/11: `Measure.aggregate`, `ListSpec`)*
  - Ảnh hưởng:
    - Rulebook public có luật "trung bình mỗi ngày thứ X của kỳ" (chia cho số ngày thứ X, kể cả ngày không có đơn), nhưng hợp đồng không có trường cách tổng hợp.
    - `list_items` không có trường điều kiện, nên không viết được "hàng ế", "hàng hết hàng cuối ngày", "hàng hết hạn trong N ngày", "hàng còn tồn có hạn dùng từ… đến…".
  - Cách sửa: thêm `Measure.aggregate` (`sum` / `avg_per_day` / `avg_per_weekday`); thêm khối điều kiện cho `list_items` (`unsold_in_period`, `out_of_stock_end_of_day`, `expiring_within`, `in_stock`…).
  - Kiểm chứng: viết được plan cho các câu tương ứng trong train và cho từng dòng luật liên quan trong rulebook public.

### Mức trung bình

- [x] **H5. Kiểu đáp án do LLM tự chọn, có thể mâu thuẫn với plan.** *(xong 04/11: `expected_answer_type`; LLM được bỏ trống trường này, ghi sai thì plan bị từ chối)*
  - Cách sửa: code tự suy ra kiểu đáp án từ plan (xếp hạng k=1 → `string`, k>1 → `list`, kèm giá trị → `table`, xếp hạng theo ngày → `date`, nhiều số đo → `list`…), hoặc ít nhất kiểm tra cho khớp. Plan mâu thuẫn thì bỏ trống.

- [x] **H6. Một số trường chưa kiểm tra định dạng; có trường bị khai báo ở hai nơi.** *(xong 04/11)*
  - `PeriodExpr.date`, `start`, `end`, `months` chưa kiểm tra dạng `YYYY-MM-DD` / `YYYY-MM`. LLM ghi "05/02/2026" vẫn qua, rồi bộ tính ngày lỗi, và câu đó bỏ trống mà không ai biết vì sao.
  - Với xếp hạng, `rank.by` và `measures[0].metric` cùng khai báo chỉ số nên có thể lệch nhau.
  - Cách sửa: thêm kiểm tra định dạng; quy định `rank.by` là nơi quyết định, thêm kiểm tra cho khớp.

- [x] **H7. Schema chuẩn thiếu thông tin mà dữ liệu thật có.** *(xong 04/11; thêm bảng `installments`, `warranty_visits` và các cột cho sửa xe, điện thoại, mẹ và bé)*
  - biz_123 có giới tính (`NamNu`) và địa chỉ khách (`DiaChiLienHe`), nhưng `customers` không có chỗ chứa. Shop **có** dữ liệu vẫn không trả lời được, và [V] không phân biệt được "shop không ghi" với "chưa map".
  - `order_discount` chỉ có một cột, trong khi luật mẹ và bé tách tiền giảm voucher với tiền giảm nhờ điểm.
  - Cách sửa: thêm `customers.address`, `customers.gender`; tách giảm giá cả đơn theo loại (voucher, điểm, khuyến mãi theo tổng).

### Mức thấp

- [x] **H8. `Mapping.ok` dễ đạt quá.** *(xong 05/11: 5 bước kiểm tra bắt buộc `REQUIRED_CHECKS` trong `mapping/build.py`)* Chỉ cần một bước kiểm tra tầm thường qua là xem như ổn.
  - Cách sửa: quy định danh sách bước kiểm tra bắt buộc (tổng dòng khớp tổng đơn, trạng thái về đủ 4 loại, khoảng ngày hợp lý, khóa nối khớp), thiếu bước nào thì không đạt.

- [ ] **H9. Cổng quyết định có thể chặt quá, làm mất điểm câu đáng lẽ trả lời được.**
  - `entities_ok` chưa định nghĩa cho câu không có tên riêng. Cần ghi rõ: không có bộ lọc nào thì coi như đạt.
  - `rules_unchanged` so nguyên văn dòng luật, nên rulebook private chỉ cần sửa một chữ là cả nhóm câu liên quan bỏ trống. Cần so gần đúng, có ngưỡng, và đo trên cặp rulebook train ↔ public.
  - *Đã làm 04/11:* [R] so gần đúng với ngưỡng 0,95. Đo trên train ↔ public: 81 luật giống, 3 luật đổi (độ giống 0,573 / 0,798 / 0,964), 25 luật thêm, 3 luật bỏ. Luật chỉ thêm vài chữ (0,964) được coi là không đổi; hai luật đổi nội dung thật bị đánh dấu. Còn cần xem lại ngưỡng khi có thêm ví dụ thật.

- [ ] **H11. Kỳ hỏi chỉ một phần nằm trong dữ liệu đang bị bỏ trống.** Luật §7 nói phải tính trên phần có dữ liệu, nhưng [E] hiện chỉ trả lời khi kỳ nằm trọn trong dữ liệu (`period_coverage = full`), để an toàn khi chưa đo. Cách sửa: khi thư viện hàm đã đúng trên train, cho phép `partial` và đo xem có bị sai thêm không.

- [ ] **H10. Test chặn logic theo id chỉ dò chuỗi `biz_`, `dev_`, `q_` cố định**, không bắt được id ghép động. Review code vẫn là chốt chặn chính; ghi rõ trong checklist review.

## B. Hạn chế của phần nghiên cứu

- [ ] **N1. Số loại câu là ước lượng ±5%.** Cách sửa: gắn nhãn tay 150 câu train ngẫu nhiên để đo độ chính xác bộ phân loại (T3–T5). Về lâu dài: cho parser G3 parse cả 3000 câu, chạy bằng thư viện hàm, câu nào ra đúng đáp án thì loại câu chắc chắn đúng (sau 09/11).
- [ ] **N2. Kiểm kê bảng có nhiễu** (chỉ đọc 4 dòng đầu, 3 sheet đầu, dò theo tên cột). Cách sửa: khi loader [A] xong, chạy lại trên header đã dò đúng.
- [ ] **N3. 2 câu unanswerable chưa chắc lý do** (biz_122 giá nhập 02/2025 và lãi gộp 03/2025). Cách sửa: tính khoảng ngày thật của từng bảng bằng loader rồi xác nhận lại nhóm A.

## C. Hạn chế của kế hoạch mẫu và việc kiểm chứng

- [ ] **K1. 24 plan mẫu viết tay, mới đúng format và kiểu đáp án, chưa chắc đúng nghĩa.**
  - Chỗ cần xem lại: câu Tết "17 ngày trước Tết" (đang dùng `before_tet`, không ghi số 17; nên thêm `n` để đối chiếu); câu lô gần hết hạn (kỳ để trống = tính tại hôm nay); câu "ly size M" (bộ lọc `size = "M"`).
  - Cách sửa: một người khác review chéo (T4); khi có thư viện hàm thì chạy từng plan, chỉ giữ plan ra đúng đáp án ("kho ví dụ đã kiểm chứng").
- [ ] **K2. Chưa có bài thử sức hợp đồng.** Cách sửa: 100 câu train ngẫu nhiên, mỗi người tự viết plan bằng tay; câu nào không viết được là lỗ hổng hợp đồng (T4–T5, trước khi khóa).
- [ ] **K3. Schema chưa thử với LLM thật.** Cách sửa: chạy Qwen3-8B 4-bit trên laptop (llama.cpp ép output theo JSON schema), parse 30 câu train kèm vài ví dụ mẫu, đo tỉ lệ JSON hợp lệ và tỉ lệ đúng; sai nhiều thì đơn giản hóa schema (T4, trước khi khóa).

## D. Review code ngày 04/11

Đã xác nhận bằng chạy thử và **đã sửa** (có test hồi quy trong `tests/test_review_fixes.py`):
- [x] **R1.** [V] lấy khoảng ngày theo bảng `lines`, mà ngày nằm ở `orders`, nên độ phủ luôn `None` và mọi câu doanh thu sẽ bị bỏ trống. → Thêm `DATE_OWNER`: bảng không có ngày lấy khoảng ngày của bảng chứa ngày.
- [x] **R2.** Bộ lọc ở mẫu số tỉ trọng (`share_of`) không được kiểm tra đã nối tên chưa, nên có thể trả lời với mẫu số sai. → Đã gộp vào bước kiểm tra.
- [x] **R3.** Câu xếp hạng không ghi `measures` thì không chạy được hàm tính. → Tra registry theo `rank.by` (xếp hạng) và theo điều kiện (`list_items`).
- [x] **R4.** Chỉ số `other` mà đáp án là tên bị từ chối oan. → `other` không tự suy ra kiểu đáp án, LLM phải ghi rõ.
- [x] **R5.** [R] chỉ so độ giống chữ: sửa "**Không** trừ" thành "Trừ" vẫn giống 0,988, nên bị coi là không đổi. → Thêm so **từ mang nghĩa và con số**: khác một từ là luật đã đổi.
- [x] **R6.** Id các đoạn văn trong rulebook đánh theo thứ tự, chèn một đoạn là lệch hết. → Đặt id theo các chữ đầu đoạn.
- [x] **R7.** Một `business_id` lỗi làm cả pipeline dừng, ghi 0 dòng. → Mỗi cửa hàng và mỗi câu chạy trong vùng bắt lỗi riêng; điền abstain trong `finally`; lỗi ghi log được bỏ qua; đọc được file có BOM và dòng hỏng.
- [x] **R8.** Đồng hồ chặn bắt đầu tính khi `run()` chạy, không tính thời gian load model. → Bắt đầu từ lúc chương trình khởi động.
- [x] **R9.** Năm "25" được chấp nhận; `expiring_within` thiếu số ngày vẫn qua. → Thêm kiểm tra.
- [x] **R10.** `check_frame` không kiểm tra kiểu dữ liệu (ngày, tiền để dạng chữ vẫn qua). → Đã thêm.
- [x] **R11.** Chưa có `.gitattributes`: `predict.sh` viết trên Windows sẽ mang xuống dòng CRLF và lỗi trong Docker Linux. → Ép xuống dòng LF cho mọi file text.
- [x] **R12.** `pytest` nằm trong requirements chạy thật. → Tách `requirements-dev.txt`.

- [x] **R13 (05/11, phát hiện nhờ bộ khung).** File luật tham chiếu chỉ giữ một phiên bản mỗi luật (bản public ghi đè bản train), nên chạy trên train thì [R] chặn mọi câu có luật đã đổi giữa hai bản. → Mỗi luật giữ **danh sách phiên bản đã chấp nhận** (112 luật, 115 phiên bản).
- [x] **R14 (05/11).** `resolve` không nhận dữ liệu, nên không tìm được "ngày tăng giá lên X đồng" (H2 mới sửa một nửa). → Thêm tham số `db`. Thêm `RawTable.year_hint` cho ngày không ghi năm (§8).

**Chưa sửa**, vì cần quyết định thiết kế:
- [ ] **H12 (Cao). Chưa có giới hạn thời gian cho từng câu.** Một lời gọi LLM, một đoạn code sinh ra, hay việc đọc một file Excel lớn bị treo có thể ăn hết 6 giờ. Đồng hồ chặn hiện chỉ kiểm tra *giữa* các câu. Cách sửa:
  - Client LLM bắt buộc có timeout cho mỗi lời gọi.
  - [D2] chạy code trong tiến trình con có timeout.
  - Đọc file có giới hạn thời gian mỗi cửa hàng.
  - Pipeline truyền hạn chót xuống từng khối.
- [ ] **H13 (Cao). Kết quả từ [D2] không bao giờ qua được cổng `rules_unchanged`**, vì code sinh ra không khai báo được dòng luật. Như vậy đường dự phòng đang bị tắt. Cần chọn một trong hai:
  - [D2] chỉ được trả lời khi khớp với [D1];
  - hoặc [D2] có cổng riêng, ngưỡng đo trên train.
- [ ] **H14 (TB). Docker phải chép cả thư mục `assets/`** (luật tham chiếu, ví dụ mẫu). Đường dẫn hiện tính theo vị trí repo; thiếu thư mục này thì [R] coi mọi luật là "đã đổi" và mọi câu bỏ trống.
- [ ] **H15 (TB). Danh sách từ mang nghĩa của [R] là chọn tay**, có thể đánh dấu "đã đổi" quá tay. Ví dụ luật chỉ thêm chữ "chưa giao" cũng bị coi là đổi. Hiện an toàn vì bỏ trống, nhưng mất điểm. Cần chỉnh khi có thêm các phiên bản rulebook.
- [ ] **H16 (Thấp). Kiểm tra "kết quả hợp lý" còn nông**: chưa chặn doanh thu âm, phần trăm vô lý, list có phần tử trùng. Bổ sung khi có thư viện hàm.

## Thứ tự xử lý đề xuất
1. **T4 sáng:** sửa H1–H7, sinh lại schema, thêm test cho từng mục.
2. **T4–T5:** K2 (cả nhóm), K3 (người có kinh nghiệm), K1 review chéo.
3. **Tối T5:** khóa hợp đồng.
4. **Sau chia vai:** H8, H9, H10; N1–N3 khi loader và parser xong.
