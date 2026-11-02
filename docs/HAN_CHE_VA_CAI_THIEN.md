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

- [x] **H8. `Mapping.ok` dễ đạt quá.** *(xong 05/11: 5 bước kiểm tra bắt buộc `REQUIRED_CHECKS` trong `mapping/build.py`; review lần 2 thêm bước 6, mục R18)* Chỉ cần một bước kiểm tra tầm thường qua là xem như ổn.
  - Cách sửa: quy định danh sách bước kiểm tra bắt buộc (tổng dòng khớp tổng đơn, trạng thái về đủ 4 loại, khoảng ngày hợp lý, khóa nối khớp), thiếu bước nào thì không đạt.

- [ ] **H9. Cổng quyết định có thể chặt quá, làm mất điểm câu đáng lẽ trả lời được.**
  - `entities_ok` chưa định nghĩa cho câu không có tên riêng. Cần ghi rõ: không có bộ lọc nào thì coi như đạt.
  - `rules_unchanged` so nguyên văn dòng luật, nên rulebook private chỉ cần sửa một chữ là cả nhóm câu liên quan bỏ trống. Cần so gần đúng, có ngưỡng, và đo trên cặp rulebook train ↔ public.
  - *Đã làm 04/11:* [R] so gần đúng với ngưỡng 0,95. Đo trên train ↔ public: 81 luật giống, 3 luật đổi (độ giống 0,573 / 0,798 / 0,964), 25 luật thêm, 3 luật bỏ. Luật chỉ thêm vài chữ (0,964) được coi là không đổi; hai luật đổi nội dung thật bị đánh dấu. Còn cần xem lại ngưỡng khi có thêm ví dụ thật.

- [ ] **H11. Kỳ hỏi chỉ một phần nằm trong dữ liệu đang bị bỏ trống.** Luật §7 nói phải tính trên phần có dữ liệu, nhưng [E] hiện chỉ trả lời khi kỳ nằm trọn trong dữ liệu (`period_coverage = full`), để an toàn khi chưa đo. Cách sửa: khi thư viện hàm đã đúng trên train, cho phép `partial` và đo xem có bị sai thêm không.

- [ ] **H10. Test chặn logic theo id chỉ dò chuỗi `biz_`, `dev_`, `q_` cố định**, không bắt được id ghép động. Review code vẫn là chốt chặn chính; ghi rõ trong checklist review.

## B. Hạn chế của phần nghiên cứu

- [ ] **N1. Số loại câu là ước lượng ±5%.** Cách sửa: gắn nhãn tay 150 câu train ngẫu nhiên để đo độ chính xác bộ phân loại (T3–T5). Về lâu dài: cho parser G3 parse cả 3000 câu, chạy bằng thư viện hàm, câu nào ra đúng đáp án thì loại câu chắc chắn đúng (sau 09/11).
- [x] **N2. Kiểm kê bảng có nhiễu** *(03/11: loader mới đọc đúng header của cả 44 cửa hàng; khi cần số đếm chính xác thì chạy lại kiểm kê bằng `load_business`)* (chỉ đọc 4 dòng đầu, 3 sheet đầu, dò theo tên cột). Cách sửa: khi loader [A] xong, chạy lại trên header đã dò đúng.
- [ ] **N3. 2 câu unanswerable chưa chắc lý do** (biz_122 giá nhập 02/2025 và lãi gộp 03/2025). Cách sửa: tính khoảng ngày thật của từng bảng bằng loader rồi xác nhận lại nhóm A.

## C. Hạn chế của kế hoạch mẫu và việc kiểm chứng

- [ ] **K1. 24 plan mẫu viết tay, mới đúng format và kiểu đáp án, chưa chắc đúng nghĩa.**
  - Chỗ cần xem lại: câu Tết "17 ngày trước Tết" (đang dùng `before_tet`, không ghi số 17; nên thêm `n` để đối chiếu); câu lô gần hết hạn (kỳ để trống = tính tại hôm nay); câu "ly size M" (bộ lọc `size = "M"`).
  - Cách sửa: một người khác review chéo (T4); khi có thư viện hàm thì chạy từng plan, chỉ giữ plan ra đúng đáp án ("kho ví dụ đã kiểm chứng").
- [x] **K2. Chưa có bài thử sức hợp đồng.** *(xong 02/11, leader + Claude: 99 câu, 6 thay đổi → hợp đồng v1.1, xem docs/contracts.md và mục R21 bên dưới; nhóm vẫn có thể làm thêm trên câu khác để tập viết plan)* Cách sửa: 100 câu train ngẫu nhiên, mỗi người tự viết plan bằng tay; câu nào không viết được là lỗ hổng hợp đồng (T4–T5, trước khi khóa).
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
  - *Review lần 2:* [D2] chỉ chạy khi [D1] trả `None`, nên lúc đó không có kết quả [D1] để so. Phương án 1 thực chất là tắt [D2]; nó chỉ còn dùng được như bước kiểm tra chéo nếu cho [D2] chạy cả khi [D1] đã có kết quả.
- [ ] **H14 (TB). Docker phải chép cả thư mục `assets/`** (luật tham chiếu, ví dụ mẫu). Đường dẫn hiện tính theo vị trí repo; thiếu thư mục này thì [R] coi mọi luật là "đã đổi" và mọi câu bỏ trống.
- [ ] **H15 (TB). Danh sách từ mang nghĩa của [R] là chọn tay**, có thể đánh dấu "đã đổi" quá tay. Ví dụ luật chỉ thêm chữ "chưa giao" cũng bị coi là đổi. Hiện an toàn vì bỏ trống, nhưng mất điểm. Cần chỉnh khi có thêm các phiên bản rulebook.
- [ ] **H16 (Thấp). Kiểm tra "kết quả hợp lý" còn nông**: chưa chặn doanh thu âm, phần trăm vô lý, list có phần tử trùng. Bổ sung khi có thư viện hàm.

## E. Review lần 2 (sau bộ khung, trước khi khóa hợp đồng)

Rà lại toàn bộ code ngày 1–4. Mỗi lỗi nghi ngờ đều được xác nhận bằng probe chạy thật trên biz_101 hoặc trên toàn bộ 3000 câu train.

**Đã sửa** (test hồi quy trong `tests/test_review2_fixes.py`; trên code cũ 19/20 test fail, test còn lại là đối chứng):
- [x] **R15 (Cao).** Hàm tính trả `np.int64` (chuyện thường gặp khi dùng `df.sum()`):
  - Ra số đơn lẻ thì câu bị bỏ trống âm thầm.
  - Nằm trong list thì `json.dumps` lỗi. Lỗi này xảy ra ở `writer.write`, nằm **ngoài** vùng bắt lỗi của từng câu, nên **cả lượt chạy dừng**: mọi câu còn lại, kể cả của các cửa hàng sau, đều bỏ trống.
  - → Formatter đổi kiểu numpy/pandas sang kiểu Python (ngày dạng `Timestamp` ra `YYYY-MM-DD`); pipeline bắt lỗi khi ghi dòng, chỉ câu đó bỏ trống.
- [x] **R16 (Cao).** `NaN` hay `None` trong list/table vẫn qua kiểm tra format. Kết quả là file nộp có `NaN`, không phải JSON hợp lệ, và `eval.validate` vẫn báo OK. → Phần tử list và ô bảng chỉ được là chuỗi hoặc số hữu hạn (đáp án train chỉ có `str` và `int`); writer dùng `allow_nan=False`.
- [x] **R17 (Cao).** Registry hàm tính có hai lỗ:
  - Khóa chỉ gồm `(intent, metric)`, nên "mặt hàng / khách / ngày có doanh thu cao nhất" tranh nhau một khóa. Đăng ký trùng thì hàm sau **ghi đè im lặng** hàm trước: G5 và G6 làm song song sẽ xóa hàm của nhau mà không ai biết.
  - Không có gì chặn một hàm **bỏ qua bộ lọc nó không hiểu**, mà đây là cách dễ bị −1 nhất.
  - → Khóa là `(intent, metric, entity)`; đăng ký trùng thì báo lỗi; hàm khai báo `filters=` mà nó áp dụng, plan có bộ lọc khác thì `execute` không gọi hàm.
- [x] **R18 (Cao).** Ô bắt buộc không đọc được vẫn qua kiểm tra mapping:
  - Probe làm hỏng 1/3 ngày của tháng 6/2026: 508 đơn mất ngày, mapping vẫn `ok`, doanh thu ra 161.409.400 thay vì 238.924.600, tức **−1**.
  - Gõ sai tên cột nguồn thì cả cột `line_amount` trống, mapping vẫn `ok`.
  - → Thêm bước kiểm tra thứ 6, "cột bắt buộc đủ giá trị".
- [x] **R19 (TB).** Loader sqlite đổi ô NULL thành chuỗi `"None"`: 144.870 ô ở biz_123, tương tự ở dev_006. Tên khách, nhân viên, nhóm sẽ có giá trị `"None"`, nên đếm khách, xếp hạng khách đều sai. → NULL thành ô trống như csv.
- [x] **R20 (TB).** Bộ hiểu câu hỏi baseline hiểu sai câu hỏi "cái nào":
  - 4/6 câu tự đặt bị đọc thành câu hỏi tổng, ví dụ "doanh thu cao nhất là ngày nào", "sản phẩm nào bán được nhiều tiền nhất", "ngày nào có số đơn cao nhất". Nguyên nhân: `nao`, `nhat` nằm trong danh sách từ đệm.
  - Trên train chưa gặp (596 câu đọc được, 5 câu lệch kiểu, cả 5 là unanswerable và cổng độ phủ đã chặn), nhưng private hỏi khác cách là bị −1.
  - → Câu dạng "giá trị" mà còn sót `nao` / `nhat` thì trả `None`. Sau khi sửa: train vẫn 596 câu, biz_101 vẫn 28 đúng / 0 sai.

- [x] **R21 (Cao, phát hiện khi làm K2).** Model pydantic **bỏ qua trường lạ**: plan có `"filter"` (gõ nhầm của `"filters"`) vẫn hợp lệ nhưng mất bộ lọc, nên câu hỏi về một mặt hàng bị trả lời bằng doanh thu cả cửa hàng, tức −1. JSON schema đưa cho LLM cũng không cấm trường lạ. → `extra="forbid"` cho mọi model plan và mapping.

**Chưa sửa** (cần quyết định thiết kế hoặc thuộc gói khác):
- [ ] **H17 (Cao, leader + G2). Kiểm tra mapping chỉ kiểm cấu trúc, không kiểm nghĩa.**
  - Probe: map `line_amount` vào cột **đơn giá** của biz_101 thì cả 6 bước vẫn qua, và doanh thu tháng 6/2026 ra 150.180.900 thay vì 238.924.600. Mapping tự động cho cửa hàng private chưa từng thấy sẽ sai kiểu này, và đây là nguồn −1 lớn nhất.
  - Cách sửa: thêm kiểm tra chéo, chạy khi có đủ cột:
    - `line_amount ≈ qty × unit_price − line_discount` trên ≥ 99% dòng.
    - Tổng các dòng ≈ tổng đơn, nếu file có cột tổng đơn.
    - Khoảng ngày khớp README.
    - `completed` là trạng thái nhiều nhất.
    - Số âm chỉ ở dòng trả.
  - Ngưỡng phải đo trên ít nhất 8 mapping tay của cửa hàng train, không đặt theo cảm tính.
- [x] **H18 (TB, G1). `TableMap.row_filter` là câu chữ ("dòng tổng cuối sheet"), code không chạy được.** Mapping không có cách nào bỏ dòng tổng, dòng tiêu đề lặp lại giữa sheet, dòng ghi chú. Nếu dữ liệu có những dòng này thì doanh thu bị cộng hai lần. Cách sửa: đổi thành điều kiện có cấu trúc (cột, phép so, giá trị hoặc regex), cài trong `build_canonical`.
  - *Quét Excel của train (02/11):* biz_105 có dòng **"Cộng"** ở cuối **cả 17 sheet tháng**, ví dụ `('Cộng', None, None, '280.183.667đ')`. Các cửa hàng train khác không có. Hiện bước kiểm tra R18 làm cả biz_105 không đạt, vì dòng này không có mã đơn và ngày. Như vậy là an toàn, nhưng mất trọn cửa hàng. Cửa hàng private kiểu "sổ ghi tay" chắc chắn còn gặp dạng này.
  - *Quyết định 02/11:* để sau. Đây là lỗi an toàn (cửa hàng bỏ trống, không bị điểm âm), mất tối đa 119/3000 câu train (4%). Không cần đổi hợp đồng: giao G1 bỏ dòng tổng ngay ở loader (ô đầu là "Cộng" / "Tổng cộng", các cột mã đơn và ngày trống), mất khoảng 1 giờ, có test. `row_filter` giữ làm ghi chú.
  - *Xong 03/11 (G1):* loader bỏ dòng tổng. Quét lại cả 44 cửa hàng thấy dòng tổng ở **3 cửa hàng: biz_105, dev_004, dev_014**, tức 2/14 cửa hàng public, nhiều hơn ước tính lúc đầu. `row_filter` vẫn để làm ghi chú.
  - Cùng các dòng đó có 2 kiểu ghi tiền mới cho G1: `332,5972tr` và `409tr663`. `parse_money` hiện chưa đọc được kiểu sau.
- [ ] **N4 (Cao, G3 + leader). Chưa tính tới độ ổn định của LLM khi BTC chạy lại.**
  - Điểm cuối do BTC chạy lại trên RTX 5090 và phải lệch ≤ 0,03 PA.
  - Kể cả temperature 0, kết quả của vLLM/llama.cpp vẫn có thể khác nhau giữa GPU và giữa kích thước batch, nên một số plan sẽ đổi.
  - Cách sửa:
    - Decoding greedy, seed cố định, batch cố định (hoặc chạy từng câu).
    - Chạy cùng 200 câu hai lần, trên hai máy khác nhau, đếm số plan khác nhau.
    - Giữ đối chiếu với baseline: plan khác baseline thì bỏ trống.
- [ ] **H19 (Thấp). `rules build` tự chấp nhận mọi phiên bản luật có trong các rulebook được đưa vào**, không có bước người kiểm.
  - Lần này đã đọc tay 3 luật đổi giữa train và public: cả 3 chỉ làm rõ thêm, không làm sai hàm nào đang có.
  - Riêng luật "Giao nhiều đợt" bản public thêm điều kiện "tính đến hết hôm nay": khi viết `delivery_count`, G5 phải cài theo bản này.
  - Cách sửa: mỗi phiên bản trong `reference_rules.json` có trường ghi ai đã kiểm và vì sao chấp nhận.

- [x] **R22 (Cao, phát hiện khi làm G1 03/11).** `parse_money` không đọc được `45,000.0000` (cột Đơn giá / Thành tiền của biz_112) và `1tr440` (cột Tiền của biz_117). Tệ hơn, `parse_number` đọc **sai lặng lẽ** `45,000.0000` thành 45 và `1tr440` thành 1. → Dùng chung một quy tắc dấu phân cách (có cả `,` và `.` thì dấu sau cùng là dấu thập phân), thêm dạng `AtrB`; có test.
  - Khi sửa có lỡ làm hỏng regex dấu phân cách nghìn: test oracle biz_101 và bước kiểm tra R18 ("278 ô thành tiền trống") bắt được ngay, cửa hàng bỏ trống chứ không trả lời sai.

## Thứ tự xử lý đề xuất
1. **T4 sáng:** sửa H1–H7, sinh lại schema, thêm test cho từng mục.
2. **T4–T5:** K2 (cả nhóm), K3 (người có kinh nghiệm), K1 review chéo.
3. **Tối T5:** khóa hợp đồng.
4. **Sau chia vai:** H8, H9, H10; N1–N3 khi loader và parser xong.
