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
- [x] **K3. Schema chưa thử với LLM thật.** *(xong 05/11: Qwen3-8B Q4_K_M, llama.cpp b12064 trên RTX 4060 laptop, 123 câu, mỗi câu bị loại khỏi kho ví dụ của chính nó)*

  | Lần | Thay đổi | Plan khớp hoàn toàn | JSON hợp lệ |
  |---|---|---|---|
  | 1 | schema của hợp đồng | 69,9% | 95,9% |
  | 2 | schema sinh output tách theo loại câu | **83,7%** | 98,4% |
  | 3 | thêm kiểm tra bộ lọc có căn cứ | **83,7%** | 94,3% |

  - **Lần 1:** dưới mốc 70%. Câu xếp hạng chỉ khớp 6%. Lỗi chính: model bỏ kỳ (10 câu), **bỏ sót bộ lọc** (7 câu, mỗi câu là một −1 chắc chắn), điền phần thừa của loại câu khác.
  - **Lần 2:** mỗi loại câu có các trường bắt buộc theo thứ tự; `filters` phải ghi tường minh; hợp đồng không nhận phần thừa; so plan theo nghĩa. Câu xếp hạng lên 94%, **0 câu bỏ sót bộ lọc**. Tác dụng phụ: 10 câu thêm bộ lọc thừa.
  - **Lần 3:** plan có bộ lọc bịa (5) bị loại; plan viết tay và plan đúng bị loại oan: 0.
  - 1,8 giây/câu. **Chạy lại cho ra plan giống hệt nhau: 0/123 khác** (cùng máy).
  - Kết quả từng câu: `outputs/k3/`.
  - Lưu ý: hướng dẫn trong prompt được chỉnh sau khi xem lỗi trên chính 123 câu này, nên số trên có thể cao hơn thực tế một chút. Số thật sẽ đo trên câu train ngoài kho ví dụ, khi chạy cả 30 cửa hàng.

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
- [x] **H17 (Cao, leader + G2). Kiểm tra mapping chỉ kiểm cấu trúc, không kiểm nghĩa.** *(xong 05/11: thêm 4 bước kiểm tra theo nghĩa vào `run_checks`, nay có 10 bước)*
  - *Ngưỡng đo trên 8 mapping tay đúng:*

    | Đại lượng | Đo được | Ngưỡng đặt |
    |---|---|---|
    | Thành tiền ≈ số lượng × đơn giá − giảm giá | 98,0–100% dòng | ≥ 95% |
    | Đơn hoàn thành + đang giao | 95–98% | ≥ 50% |
    | Ngày cuối dữ liệu so với ngày README ghi | lệch 0 ngày ở cả 8 | lệch ≤ 1 ngày |
    | Số âm ngoài đơn trả hàng | 0 | ≤ 0,1% |

    Các bước theo tỉ lệ chỉ chạy khi có ≥ 20 đơn / dòng.
  - *Thử phá có chủ đích 8 kiểu trên dữ liệu thật: bị chặn cả 8.*
    - Thành tiền lấy từ cột đơn giá: biz_103, biz_105, biz_120, còn 50–85% dòng khớp.
    - Số lượng lấy từ cột thành tiền: biz_117, còn 3,5%.
    - Đảo trạng thái hoàn thành ↔ huỷ: biz_103, biz_123, còn 1–3%.
    - Bỏ sót file cuối: biz_105, dữ liệu dừng ở 31/01 trong khi README ghi 24/06.
    - Thành tiền lấy từ cột giảm giá: biz_120, còn 0%.
  - 8 mapping đúng qua đủ 10/10 bước, không bị chặn oan.
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
- [ ] **N4 (Cao, G3 + leader). Chưa tính tới độ ổn định của LLM khi BTC chạy lại.** *(05/11: cùng máy, chạy 2 lần cho 123/123 plan giống hệt; còn phải đo trên GPU khác, ví dụ RTX 5090)*
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

- [x] **R23 (Cao, phát hiện khi viết mapping tay 04/11).** Hai kiểu dòng không phải dữ liệu mà loader chưa bỏ:
  - dòng chú thích cuối sheet ("Ghi chú: tiền tính bằng đồng", biz_105, biz_117);
  - dòng "**Tổng tháng** + số tiền" (biz_117).

  Có phép điền xuống theo §8 thì cả hai sẽ thành dòng hàng giả. Lần này bước kiểm tra R18 chặn được, nhưng mất trọn cửa hàng. → Loader bỏ dòng chú thích cuối sheet (dòng chỉ có 1 ô, bảng ≥ 4 cột); mẫu dòng tổng nới thành "dòng thưa bắt đầu bằng Cộng / Tổng / Total".
- [x] **R24 (TB, 04/11).** Dòng trả hàng ghi *ngày trả* và có thể nằm trước dòng bán (biz_105: 333 đơn trải nhiều ngày). Lấy ngày đơn theo dòng đầu có thể ra nhầm ngày trả. → Ngày của đơn = ngày sớm nhất trong các dòng của đơn.
- [x] **R25 (Cao, phát hiện khi viết mapping tay biz_124 ngày 05/11).** `41,785tr` (41,785 triệu) bị đọc thành **41,8 tỉ**, gấp 1000 lần, vì phần `41,785` khớp mẫu dấu phân cách nghìn trước khi xét hậu tố `tr`. Lỗi có từ bản đầu của bộ đọc tiền; profile của biz_124 cho thấy chi phí 41,8 tỉ và tiền nhập 23 tỉ, vô lý cho một nhà thuốc nhỏ. → Có hậu tố `k` / `tr` thì một dấu `,` hoặc `.` duy nhất là dấu thập phân; có test.
- [ ] **H20 (Cao, 04/11). Mạng 4G của leader không tải được file nặng:**
  - model 5–9 GB;
  - llama.cpp khoảng 300 MB;
  - lớn nhất là **upload image Docker 10–20 GB lên Google Drive trước 16/11**.

  Thêm nữa, quyền chạy file `.exe` tải về đang bị chặn trên máy. Cách xử lý đề xuất: làm mọi việc nặng trên **máy GPU thuê** (tải model, chạy K3, so 8B / 14B, build Docker, upload thẳng từ máy thuê lên Google Drive bằng `rclone`); laptop chỉ viết code. Cần leader quyết định ngày thuê.
- [ ] **H21 (Thấp, 04/11).** `profile_business` chỉ tính min / max trên 300 giá trị đầu, nên khoảng ngày trong profile có thể sai (biz_103: "01/04–09/04"). Cần sửa trước khi đưa profile cho LLM viết mapping (G2 phần 3).

## F. T1: gom cụm mẫu câu (phiên 3)

Chi tiết ở [research/templates.md](research/templates.md).

- [ ] **N5 (TB). Plan của cụm không có plan viết tay chưa được kiểm bằng đáp án.**
  - Nguồn của các plan này: LLM (Qwen3-8B, khớp 83,7% ở K3) hoặc baseline.
  - Vì vậy dạng plan, và trạng thái hàm, của các cụm đó có thể sai.
  - Đã giảm rủi ro một phần: LLM đọc 2 câu mỗi cụm (câu đại diện và câu ít giống nhất), hai plan khác dạng thì đánh dấu.
  - Cách sửa: T4 chạy plan trên 8 cửa hàng có mapping và so với đáp án.
- [ ] **N6 (Thấp). "Đã có hàm" mới ở mức registry.** Hàm được đăng ký và nhận đủ bộ lọc, nhưng vẫn có thể từ chối một biến thể (nhiều measure, `k` ≠ 1, xếp tăng dần). Câu đó lại cần mapping đúng mới trả lời được. Vì vậy tỉ lệ "câu nằm trong cụm có hàm" là **cận trên**; số thật là kết quả của `oracle --all`.
- [x] **N7 (TB, cho T3 / G3). `baseline.fold` không gỡ lỗi gõ telex khi tắt bộ gõ** ("thangs", "dduwowcj"). *Xong 03/11: `fold` dùng `templates.tokens`. Baseline đọc được 39/290 câu telex (trước là 0). `oracle --all` không LLM: 116 đúng / 0 sai (trước 113); có LLM: 570 đúng / 0 sai (trước 567). K3 chưa chạy lại.*
  - Probe ngày 03/11 trên 290 câu train có từ dạng telex: **baseline đọc được 0/290; sau khi gỡ telex bằng `templates.tokens` thì đọc được 35**.
  - Bộ chọn ví dụ BM25 của prompt dùng cùng `fold`, nên các câu này cũng được chọn ví dụ kém hơn.
  - Lỗi này an toàn (bỏ trống, không trả lời sai) nhưng làm mất độ phủ.
  - Cách sửa: `fold` dùng phép gỡ telex của `datamate/nlu/templates.py`. Sửa ở T3, lúc nối LLM, rồi chạy lại K3, vì ví dụ BM25 sẽ đổi.
- [ ] **N8 (Thấp). Che tên dựa vào tên cột.** Cột có tên lạ thì tên trong cột không được che, và câu bị tách thành cụm riêng.
  - Kênh bán và hình thức thanh toán cố ý không che.
  - Chỉ ảnh hưởng số cụm; danh sách việc của T3 không bị ảnh hưởng, vì danh sách này gom theo dạng plan.
  - T4 dùng `NameIndex` lúc chạy thật thì nên lấy tên từ bảng chuẩn hoá (`products.product_name`, `customers`…), không lấy theo tên cột thô.

## G. T2: nối tên (phiên 3)

Chi tiết ở [research/linking.md](research/linking.md).

- [x] **R26 (TB, phát hiện khi đo T2 ngày 03/11). Linking bỏ sót 6/231 giá trị lẽ ra nối được** (đáp án là số):
  - LLM chép cả đơn vị đếm vào tên hàng: "bình Gas Petrolimex 12kg", "xe 4m3 cat xay to".
  - LLM chép sai tên dù câu hỏi có tên đầy đủ: "sinh tu bo" cho "sinh tố bơ (m)", "Nguyễn Mai Hiếu" cho "nghiêm mai hiếu".

  Đây là lỗi an toàn (bỏ trống). → Thử thêm tên hàng sau khi bỏ **đơn vị đếm có thật của cửa hàng** ở đầu; nối theo tên đầy đủ có trong câu hỏi khi tên đó có chung ≥ 2 chữ và ≥ nửa số chữ với giá trị LLM ghi. Cả 6 đã nối đúng; có test hồi quy.
- [ ] **N9 (TB). Bước "tên có trong câu hỏi" dựa vào việc đề chèn nguyên tên.** Nếu private viết tên tắt hoặc khác cách, bước này không giúp được; câu đó rơi về so khớp mờ (ngưỡng 90) hoặc bỏ trống. Lỗi an toàn, nhưng làm giảm độ phủ. Kiểm lại trên câu public sau lần nộp đầu, chỉ đếm số câu không nối được (không đọc đáp án vì không có).
- [ ] **N10 (TB). Chưa có đáp án chuẩn cho việc nối.** 9 lần nối không phải khớp tuyệt đối đã xem tay, đều đúng. Kiểm thật bằng đáp án ở T3: câu đã nối mà trả lời sai phải là 0.

## H. T3: thư viện hàm nhóm bán hàng (phiên 3)

Đo bằng `python -m datamate.eval.check_plans`: lấy plan có sẵn (plan tay + plan LLM đã cache), chạy qua cả chuỗi của pipeline, rồi chấm với đáp án train của 8 cửa hàng.

- Lần đầu: 363 câu, **9 sai**.
- Sau các bản sửa dưới đây: **230 đúng / 2 sai / 131 bỏ trống**. Phần bỏ trống chủ yếu là chỉ số v2.

- [x] **R27 (Cao). Khách lẻ ghi "kl" bị coi là một khách** (biz_117). Khách mua nhiều tiền nhất ra "kl" ở 3 câu.
  - Nguyên nhân: mapping tay chỉ khai "Khách lẻ / khách lẻ / lẻ".
  - Sửa: thêm `blank_walk_ins` khi dựng dữ liệu chuẩn. Mọi cách ghi khách lẻ đã thấy trong file train ("khách lẻ", "lẻ", "kl", "vãng lai") và ô rỗng đều thành không có mã khách (§3). Mapping tự động (T5) cũng được hưởng; có test.
- [x] **R28 (TB). Plan `count_where` không có measure (hợp đồng v1.1 cho phép) không tìm được hàm**, vì `metric_name` chỉ biết lấy chỉ số từ xếp hạng, từ điều kiện liệt kê và từ measure. 6 câu đếm đơn / đếm ngày theo ngưỡng bị bỏ trống oan. → `metric_name` lấy `threshold.metric`; test bắt được.
- [x] **R29 (Cao). LLM bịa ngày.** Câu "kể từ khi X lên giá …" không ghi ngày (ngày tăng giá nằm trong bảng giá, tức `anchor_price`), LLM ghi ngày hôm nay. Kết quả: 4 câu hiệu ứng tăng giá ra −95% trong khi đáp án là +130…+390%.
  - Sửa (`grounding.py`): ngày trong plan phải có trong câu hỏi (d/m; hôm nay / hôm qua chỉ khi câu nói vậy); với chuỗi tháng liên tiếp chỉ xét tháng đầu và tháng cuối. Năm của tháng / quý / Tết mà câu không ghi thì **bỏ đi**, để §2 tự suy năm.
  - Trên 827 plan (149 plan tay + 678 plan LLM), cổng chỉ loại đúng 4 plan bịa ngày.
- [ ] **N11 (TB, hợp đồng). `trend` không ghi được chiều tăng hay giảm.** Cả 21 câu trend của train đều hỏi chiều tăng, nên hàm trả lời "tăng ngặt qua từng tháng". Nếu private hỏi "giảm liên tục" thì sẽ sai. Cách sửa khi có thời gian: thêm `direction` vào hợp đồng (v1.2), kèm từ khoá căn cứ "giảm".
- [x] **R30 (Cao). LLM đọc sai ý câu, hàm tính vẫn đúng.** Lượt `oracle --all --llm-url` đầu tiên (790 câu) ra **567 đúng / 2 sai**. Hai câu sai:
  - "số **ddown** ca chiều" (telex của "đơn") bị đọc thành doanh thu;
  - "có **bao nhiêu** mặt hàng không bán được" bị đọc thành danh sách.

  Trên plan cache còn một câu nữa: "dthu thuốc kê đơn" bị đọc thành tỉ trọng.
  - Sửa: `ungrounded_measures` trong `grounding.py`, nằm trong cổng `accept_plan`. Doanh thu cần từ về tiền; số đơn cần "đơn"; tỉ trọng và "% thay đổi" cần từ về phần trăm; đếm hay liệt kê phải khớp chữ của câu ("cái nào" không phải liệt kê).
  - Trên 807 plan (149 plan tay + plan LLM của cả 30 cửa hàng), cổng chỉ bắt 12 plan, cả 12 đều là LLM đọc sai; không plan tay nào bị loại oan.
  - **Sau khi sửa: 567 đúng / 0 sai / 223 bỏ trống, PA +0,718.**
- [ ] **N12 (Cao, T4). Các cổng căn cứ được rút ra từ lỗi trên 8 cửa hàng có mapping**, nên có thể khớp quá sát với chính các câu này. Phép thử thật là T4: đo kiểu bỏ ra một cửa hàng, và chạy trên 22 cửa hàng còn lại khi có mapping tự động. Cổng "câu anh em" (T4) là lớp chặn thứ hai cho LLM đọc sai ý câu.
- [ ] **N13 (Thấp). Chưa làm:**
  - xếp hạng tăng dần ("bán chậm nhất");
  - bảng kèm số đo;
  - `min_orders` ("khách sộp");
  - đếm ngày có doanh thu dưới N (cần cả những ngày không có đơn);
  - `which_more`;
  - số lượng hỏi theo đơn vị lớn.

  Gặp các dạng này thì hàm trả `None` (bỏ trống). Theo T1, mỗi dạng chỉ có vài câu.

## I. T4: kho đã kiểm chứng và cổng câu anh em (đêm 03→04/11)

Đo trung thực: LLM **không thấy ví dụ của chính cửa hàng** (mặc định của `oracle` từ 03/11), giống khi gặp cửa hàng lạ ở private. Số 571 đúng / 0 sai trước đó lạc quan, vì kho BM25 chứa chính câu đang chấm.

- [x] **R31 (TB). Cổng câu anh em cho qua plan không có câu anh em nào** khi ngưỡng là 0: điểm mặc định 0,0 ≥ 0. → `Twin.passes`: phải có câu anh em, rồi mới so điểm; `oracle --twin-threshold -1` là tắt cổng. Có test.
- [x] **R32 (Cao). Lượt đo trung thực đầu tiên (790 câu, tắt cổng): 575 đúng / 7 sai.** Cả 7 câu đều do LLM đọc sai ý, hàm tính không sai:
  - 4 câu hỏi tồn ("còn bao nhiêu tuýp", "kho còn tồn") đọc thành số đã bán tính đến hôm nay;
  - "đơn giá bao nhiêu tiền một viên" đọc thành doanh thu;
  - "số nhập trừ số bán" đọc thành số bán;
  - "có tổng cộng mấy mặt hàng ế, bán ko dc món nào" đọc thành danh sách.

  Sửa trong `ungrounded_measures`: số lượng bán cần chữ "bán / chạy / hot / tiêu thụ / xuất"; plan chỉ có chỉ số bán hàng thì bị loại khi câu hỏi tồn (cụm "còn bao nhiêu", "tồn kho", "trong kho"…), hỏi nhập ("nhập"), hoặc đơn giá ("đơn giá", "giá bán"); "không … món nào" không phải chữ liệt kê. Đo trước khi sửa: luật bắt đủ 7/7, không đụng câu đúng nào, 0/149 plan tay và 0/2105 plan trong kho bị loại oan. Có test cho cả 7 câu.
- [x] **R33 (TB). Bộ lọc ca chỉ cần chữ "ca", mà "cá" bỏ dấu cũng là "ca".** "bán Chả cá chiên được bao nhiêu tiền" đọc thành doanh thu ca chiều (cửa hàng không mapping, câu anh em 83 điểm nên lọt cổng). → ca sáng cần chữ "sáng", ca chiều cần "chiều". Có test.
- [x] **N14 (TB). Bộ lọc "trạng thái = huỷ" trên chỉ số huỷ.** LLM thêm bộ lọc này vào 12/2895 plan ("mấy đơn ở trạng thái huỷ"). Với số đơn huỷ, bộ lọc thừa làm hàm từ chối nên câu bị bỏ trống; với tỉ lệ huỷ, bộ lọc làm tỉ lệ thành 100%. → `nlu.drop_implied_filters` bỏ bộ lọc này. Có test.
- **Chọn ngưỡng cổng (`twin_gate`).** Trên 749 plan của 8 cửa hàng có mapping, không ngưỡng nào có câu sai, nên bảng này không chọn được ngưỡng. Thêm phép đo trên 22 cửa hàng không có mapping: plan **khác dạng** với cách đọc đã kiểm chứng của cụm mẫu câu thì nhiều khả năng là đọc sai. Đọc tay 61 plan khác dạng:
  - khoảng một nửa là đọc sai thật ("hoạt chất" đọc thành tên hàng, "quý 2" đọc thành tháng, "Chả cá chiên" đọc thành ca);
  - phần còn lại chỉ khác loại kỳ ("tháng này" so với "tháng 3"), vì T1 che số khi gom cụm.

  Điểm giống của câu anh em không tách được hai nhóm: câu đúng nhưng diễn đạt khác có điểm 54–89, câu đọc sai 76–83. Vì vậy chọn **ngưỡng 0**, tức chỉ đòi có câu đã kiểm chứng cùng dạng plan ở cửa hàng khác.
- [x] **N15 (TB). Cổng làm mất câu đúng chỉ vì loại kỳ.** Lượt có cổng (trước khi sửa) mất 11 câu đúng, phần lớn vì kho có "tháng 3" mà câu hỏi "tháng này". → `twins.twin_shape` gộp loại kỳ theo họ (hôm nay / hôm qua / một ngày; tuần này / tuần trước; tháng này / tháng trước / một tháng). Các kỳ đổi ý câu vẫn tách riêng: "đến hết ngày" (tồn), quý, Tết, khoảng ngày. Trên 749 plan có mapping, số câu đúng bị chặn giảm từ 12 xuống 6.
- [x] **N16 (TB). Có nên giữ cổng câu anh em không: số trên train còn sát nhau.** **Đã quyết (05/11): tắt cổng.** Lượt chẩn đoán public `tat_cong_cau_anh_em` (lượt 1 cộng thêm 28 câu cổng chặn) được 0,336, so với 0,316. Vậy 28 câu bị chặn gồm **24 đúng / 4 sai**: cổng chặn oan 86%, trong khi cổng chỉ có lợi khi hơn nửa số câu nó chặn là câu sai. Đã đổi `configs/default.json` sang `"twin_threshold": null` (test `test_twin_gate_is_off_by_default`). Train không đổi, vì `eval.mapping` vốn chấm không qua cổng. Chạy lại run4 bằng cấu hình mới trùng khớp hoàn toàn với `outputs/public_run4_twin_off/` (432 câu trả lời = run4 + 38 câu cổng chặn).
  - Sau mọi bản sửa (lượt v2): bật cổng 570 đúng / 0 sai, tắt cổng 575 đúng / 0 sai. Như vậy trên train cổng chỉ làm mất 5 câu đúng: 2 câu Tết, 2 câu ca làm, 1 câu số gói. Lý do là khi đo bỏ ra một cửa hàng, kho thiếu dạng plan của cửa hàng đó.
  - Phép đo duy nhất trên **lỗi đọc sai kiểu mới**, trước khi có luật khớp riêng với chúng, là lượt đầu: cổng chặn 6/7 câu sai và mất 11 câu đúng. Sau N15, số câu đúng mất ở mức 5.
  - Quyết định tạm: **giữ cổng (ngưỡng 0)**. Khi chạy thật, kho có câu của mọi cửa hàng train, nên số câu đúng bị mất sẽ ít hơn con số đo bỏ ra một cửa hàng. Còn lỗi đọc sai kiểu mới ở private thì luật căn cứ chưa biết trước được.
  - Muốn tắt: đổi `"twin_threshold"` thành `null` trong `configs/default.json`.
  - Cách đo thật: lần nộp public đầu tiên (09/11), nếu lượt nộp cho phép thì nộp cả hai bản (bật / tắt cổng) và so điểm trên leaderboard. Đó là cửa hàng lạ thật.

## J. Chỉ số v2: nhập hàng, giá bán, tồn kho, công nợ (04/11)

Mỗi công thức đều được dò với đáp án train trước khi viết (xem [metrics/README](../datamate/metrics/README.md)).
- Đã có: nhập hàng, giá bán, tồn, công nợ (thu / nợ thêm / còn nợ / xếp khách nợ), số đợt giao, lãi gộp, lãi ròng.
- `check_plans`: 316 đúng / **0 sai** / 47 bỏ trống trên 363 câu (trước: 230 / 2 / 131).
- Plan LLM của `build_bank` trên 8 cửa hàng có mapping: 690 đúng / 0 sai / 58 bỏ trống trên 748 plan (trước v2: 565 / 0 / 184).

- [x] **R34 (TB). "Số nhập trừ số bán" bị đọc thành tồn cuối tháng.** Lỗi lộ ra khi đã có hàm tồn: `check_plans` ra 98, trong khi đáp án là −28. → Chỉ số tồn cần chữ về tồn ("tồn", "còn", "trong kho", "hết hàng"). Trên 149 plan tay và 2346 plan trong kho, luật không gạt nhầm plan nào. Có test.
- [x] **R35 (TB, phòng trước cho public). Rulebook public có dòng "nhà cung cấp chính" = nhiều phiếu nhập nhất, khác với nhập nhiều tiền nhất.** LLM có thể đọc câu đó thành xếp theo tiền nhập.
  - Sửa 1: tiền nhập cần chữ "tiền" hoặc "giá trị". Cả 9 cụm câu về tiền nhập trong train đều có một trong hai chữ này.
  - Sửa 2: thêm hàm xếp theo số phiếu, gắn dòng luật `§5.nha_cung_cap_chinh`. Trên train, [R] tự chặn hàm này vì rulebook train không có dòng đó. Có test.
- [x] **R36 (TB). "Lợi nhuận ròng" bị đọc thành lãi gộp** (lỗi lộ ra khi đã có hàm lãi gộp: 81 130 158 so với đáp án 8 125 158). → Lãi gộp không được dùng khi câu có chữ "ròng"; lãi ròng cần chữ "ròng" hoặc "chi phí". Thêm hàm lãi ròng (3/3 câu dò khớp). Có test.
- [ ] **N17 (TB). Tồn của một ngày trước ảnh tồn duy nhất thì bỏ trống.** Phần lớn cửa hàng chỉ có một ảnh tồn vào ngày cuối dữ liệu; muốn ra tồn ngày trước đó phải lùi các phát sinh nhập / bán / trả, mà luật trả hàng với kho chưa rõ. Mọi câu tồn trong train đều hỏi "hết hôm nay", trùng với ngày của ảnh tồn. Nếu private hỏi ngày khác thì câu bị bỏ trống (an toàn).
- [ ] **N18 (Thấp). Giá bán hỏi theo đơn vị lớn ("giá một thùng") và giá nhập hỏi theo đơn vị khác đơn vị nhập thì bỏ trống**, vì §5 chỉ định nghĩa theo đơn vị cơ bản / đơn vị nhập. Train không có câu nào như vậy.

## K. T5: mapping tự động (04/11)

Cách làm ở [mapping/README](../datamate/mapping/README.md). Đo bằng `eval.mapping` (plan LLM đã lưu) và `oracle --all --auto-mapping` (cả chuỗi, LLM thật); mapping của chính cửa hàng luôn bị bỏ khỏi ví dụ.
- Cả chuỗi trên 3000 câu train: v1 (chỉ theo tên cột) 830 đúng / 0 sai; v2 (thêm theo nghĩa, gộp khoá, cổng năm) 1060 / 0; v4 1712 / 0; **v5 (ghép bảng theo README + chốt R43) 1815 đúng / 0 sai, PA +0,605**.
- Public: 8/14 cửa hàng có mapping qua kiểm tra.

- [x] **R37 (Cao). Mapping "theo nghĩa" từ một sổ không mã đơn đọc một cửa hàng có mã đơn từng dòng một**: qua đủ 10 bước kiểm tra mà sai 68/119 câu (số đơn, đơn huỷ, doanh thu). → Mẫu không mã đơn chỉ dùng khi không cột nào của cửa hàng mới gom dòng thành đơn (`_groups_rows`: ≥ 20% dòng tiếp nối dòng trên, ≥ 5% giá trị khác nhau). Có test.
- [x] **R38 (TB). Tên hàng / tên khách ghi nhiều cách** ("MÌ OMACHI", "Coca  Cola", "Gao ST25"; 7/70 tên ở biz_101, cả ở mapping tay). Số lượng của một mặt hàng bị chia ra nhiều khoá: một câu "bán chạy nhất" sai. → `build.unify_keys` gộp về cách viết hay gặp nhất; hai tên chỉ khác dấu thì không gộp. Có test.
- [x] **R39 (TB). Dòng "Phí phục vụ" bị tính là mặt hàng** khi mapping chuyển từ cửa hàng không có dòng này: 3 câu "mấy mặt hàng xuất hiện ≥ N đơn" thừa 1. → `build.mark_fee_lines` theo §3. Có test.
- [x] **R40 (TB). Dòng tổng giữa sheet không bị bỏ** khi nhãn "Tổng ngày…" không nằm ở ô đầu (cột xáo thứ tự). → loader xét mọi ô của dòng thưa. Có test.
- [x] **R41 (TB). LLM đọc sai, lộ ra trên các cửa hàng mới có mapping:**
  - năm của ngày tăng giá khác năm câu hỏi ghi;
  - "quý 2" đọc thành tháng 2;
  - bộ lọc "thứ Hai" bịa từ chữ "thu" của "doanh thu";
  - "bao nhiu mặt hàng" đọc thành danh sách;
  - "bán được bao nhiêu ly" thêm doanh thu.

  Mỗi lỗi có cổng căn cứ và test. 0/149 plan tay, 0/2390 plan trong kho bị loại oan.
- [x] **R42 (Thấp). `count_where` theo khách và nợ theo khách lỗi khi cửa hàng không ghi khách** (mapping chuyển sang bỏ cột tuỳ chọn). → trả `None`.
- [x] **R43 (Cao). Ghép bảng theo mô tả README (khi tên file khác nhau) mở ra cặp mẫu khác cấu trúc: 47 câu sai** trên train. Ba nguyên nhân, ba chốt, mỗi chốt có test:
  - LLM ghép cột "số lượng quy đổi" của mẫu vào chính cột số lượng → hai cột mẫu khác nghĩa không được chung một cột mới (`_one_meaning_each`);
  - mặt hàng bán theo hai đơn vị mà không có hệ số quy đổi → số lượng cơ bản để trống (`derive_base_qty`);
  - mẫu có mã đơn dùng cho sổ không mã đơn → cột ghép làm mã đơn của dòng hàng phải gom dòng thành đơn (`_order_ids_group_lines`).

  Sau đó: **1881 đúng / 0 sai** trên 30 cửa hàng train; public 8/14. Mẫu cùng tên file được thử trước mẫu chỉ khớp theo README.
- [ ] **N19 (TB). Ngưỡng 0,5% đơn không rõ trạng thái** (một cửa hàng public có 1/820 đơn để trống trạng thái ở dòng đầu). Số liệu nào đơn đó có thể làm thay đổi thì bỏ trống, nên an toàn. Nhưng ngưỡng mới dựa trên một trường hợp. Review 04/11: **không cửa hàng train nào có đơn thiếu trạng thái**, nên quy tắc này sinh ra từ việc nhìn dữ liệu public (vùng xám của luật, xem mục L).
- [ ] **N20 (Cao). Độ phủ public còn thấp (8/14).** Các họ định dạng còn thiếu mapping mẫu:
  - csv `danh_sach_hoa_don` chỉ có đơn, không có dòng hàng (train biz_110);
  - `chi_tiet_hoa_don.csv`, `ChiTietHoaDon_*.xlsx`;
  - sổ có sheet "Ghi tắt";
  - sổ sửa xe, sổ điện thoại (§6).

  Cách sửa: thêm mapping tay cho cửa hàng train cùng họ (nếu có). Review 04/11 đổi cách dò: **dò trên 10 cửa hàng train không map được khi bỏ mapping của chính nó** (biz_101, 107, 110, 111, 113, 120, 123, 124, 126, 127), không dò từng cửa hàng public (xem mục L).

## L. Review cuối phiên 3: hướng đi, luật, bug (04/11)

Soát toàn bộ phần T1–T5 và v2. 317 test qua. Sau hai chỗ sửa, `eval.mapping` vẫn ra **1881 đúng / 0 sai / 1119 bỏ trống** trên train (PA +0,627).

**Bug đã sửa (mỗi mục có test):**
- [x] **R44 (TB). README của bảng không được README gọi đúng tên lấy nhầm mô tả của mục README đầu tiên** (`transfer.column_notes`: phép so tên gốc của file luôn đúng). Ví dụ `SoBanHang_1.xlsx` nhận mô tả cột của `KhachHang.xlsx`; LLM ghép cột theo nghĩa thấy mô tả của bảng khác.
  - Đo: train 0/339 bảng dính, nên các số đo T5 không bị ảnh hưởng. Public 34/163 bảng, ở 2 cửa hàng; cả hai map theo tên cột (không qua LLM), nên đáp án cũng không đổi.
  - Sửa: so đúng tên gốc; README không nhắc bảng thì không có mô tả.
- [x] **R45 (TB). Ngày ảnh tồn kho được gán là ngày cuối dữ liệu cho mọi cửa hàng mới**, dù README của cửa hàng đó có nói vậy hay không. Một cửa hàng ghi tồn đầu kỳ, hoặc tồn tại ngày khác, sẽ sai mọi câu tồn kho mà không bước kiểm tra nào bắt được.
  - Căn cứ: mọi README train có file tồn đều ghi "**X** là tồn cuối ngày cuối có dữ liệu".
  - Sửa: hằng số ngày tồn chỉ giữ khi README cửa hàng mới có câu đó; không có thì bỏ bảng tồn (câu tồn kho bỏ trống). Train 5/5 cửa hàng có câu này, nên không đổi. Public chưa cửa hàng nào dính, vì cửa hàng duy nhất có tồn lấy ngày từ cột của file.

**Luật thi:**
- Code chạy thật không đọc `answers.jsonl` hay `outputs/`, không ghi vào thư mục dữ liệu, không có id cửa hàng hay câu hỏi (`test_no_id_logic`). LLM giải mã tham lam (temperature 0, top_k 1, seed 0), nên BTC chạy lại cho cùng kết quả. Cache LLM chỉ dùng khi phát triển.
- Mapping tay chỉ có ở 10 cửa hàng train. Không từ khoá trạng thái nào chỉ xuất hiện ở public (đếm 04/11).
- [ ] **N21 (Thấp). Đo leave-one-out còn rò từ điển giá trị**: `vocabulary()` gộp cả mapping tay của cửa hàng đang bị bỏ ra. Đo 04/11: chỉ khác 2 từ khách lẻ ('kl', 'lẻ'), mà `blank_walk_ins` đằng nào cũng xử lý; trạng thái đơn không khác từ nào. Số đo vẫn đúng; sửa khi động vào phần này.
- [ ] **N22 (TB, cần trưởng nhóm quyết). Vùng xám: thiết kế dựa trên dữ liệu public.** N19 (ngưỡng 0,5% đơn không rõ trạng thái) sinh ra từ một cửa hàng public. Đây không phải nhãn hay huấn luyện: quy tắc chung, và số liệu đơn đó có thể làm đổi thì bỏ trống. Đề xuất: giữ, ghi rõ trong tài liệu phương pháp. Từ nay không dò lỗi từng cửa hàng public nữa (N20 đổi cách dò).
  - **Trưởng nhóm quyết 04/11: hỏi BTC; trong lúc chờ chỉ cải thiện bằng dữ liệu train.** Câu hỏi đã soạn sẵn gửi BTC.
- `R_MAIN_SUPPLIER` đọc một dòng chỉ có trong rulebook public. Rulebook là đầu vào đi kèm mỗi split, và [R] chặn khi dòng đó vắng, nên hợp lệ.

**Hướng đi:**
- 2/3 số câu bỏ trống trên train (≈ 790/1185) là của 10 cửa hàng không map được. Ở 20 cửa hàng map được: ≈ 85% đúng, 0 sai. **Đòn bẩy lớn nhất vẫn là độ phủ mapping.** Mapping chuyển từ mẫu chỉ phủ các định dạng train có; private có thể có định dạng mới.
- [x] **N23 (Cao). Mapping dựng từ README khi không mẫu nào khớp** ([from_readme.py](../datamate/mapping/from_readme.py), làm 04/11).
  - Không cần LLM. README mô tả mỗi cột bằng một cụm nghĩa lấy từ danh sách cố định (74 cụm ở train), và mỗi cụm của bảng bán ứng với đúng một cột chuẩn ở mọi mapping tay.
  - Đo trên train: chỉ đường README (`eval.mapping --readme-only`) **2048 đúng / 0 sai** trên 25/30 cửa hàng. Cả hệ (chuyển mẫu trước, README sau): **2294 đúng / 0 sai / 706 bỏ trống, PA +0,765** (trước +0,627).
  - Ba cửa hàng chưa từng có mapping tay (107, 113, 127) đúng 181 / 0. Đây là phép đo sạch nhất: từ điển cụm nghĩa không học từ chúng.
  - Hai lỗi gom bảng lộ ra khi dò trên train và đã sửa, mỗi lỗi có test:
    - một workbook có 4 sheet, README mô tả từng sheet (biz_116);
    - hai phần của một sổ, mỗi phần một mục README (biz_105).
  - Còn trượt: biz_110 (chỉ có đơn), 123 và 124 (README không mô tả cột theo khuôn).
  - **Public: không phủ thêm cửa hàng nào** (đường README qua 3/14, cả ba đã được chuyển mẫu phủ). Muốn biết vì sao phải xem định dạng public, nên chờ N22.
- [x] **R46 (TB). Thuật ngữ chỉ rulebook public định nghĩa** ("khách trung thành nhất" = nhiều ngày có mua nhất, "khách sộp nhất", "mặt hàng được ưa chuộng nhất" = có trong nhiều đơn nhất, "giờ cao điểm"… 17 dòng không có bản train). LLM sẽ đọc chúng thành hàm train gần nhất (nhiều đơn, nhiều số lượng) mà không cổng nào chặn.
  - Cổng `terms` (`rules.unverified_terms`): câu hỏi dùng thuật ngữ của dòng luật không có bản train, mà hàm không dẫn dòng đó, thì bỏ trống. Áp cho cả thuật ngữ mới của private.
  - Đo: train không đổi (rulebook train không có dòng mới). Public lượt 1 không có câu đã trả lời nào dính, nên đây không phải nguồn của 27 câu sai; cổng giữ để phòng. Có test.
- [ ] **N24 (Cao). "0 sai" là số trong mẫu.** Các cổng và chốt được thêm sau khi thấy lỗi trên chính train, nên tỉ lệ sai thật trên cửa hàng mới chưa biết. **Nộp public sớm nhất có thể** để đo; mỗi ngày được 5 lần, so cả bật / tắt cổng câu anh em (N16).
  - **Đã đo 04/11: lượt 1 điểm 0,316 = 343 đúng / 27 sai trên 370 câu trả lời (sai 7,3%).** Chưa biết câu sai nằm ở đâu.
  - Hai giả thuyết đã loại: thuật ngữ mới của rulebook (R46), mapping (3 cửa hàng map được bằng hai đường cho 140/140 câu giống nhau).
  - Nộp thử bỏ trống từng nhóm hàm (`outputs/public_ablation/bo_nhom_{A,B,C}.jsonl`, 04/11 18:38). Số sai = (số câu − (0,316 − điểm) × 1000) / 2:

    | Nhóm | Câu | Điểm | Đúng | Sai |
    |---|---:|---:|---:|---:|
    | A `sales.value_of` | 190 | 0,148 | 179 | 11 (5,8%) |
    | B `sales.rank` + `count_where` | 101 | 0,241 | 88 | 13 (12,9%) |
    | C so sánh, tỉ trọng, chuỗi, xu hướng | 64 | 0,258 | 61 | 3 |
    | D công nợ, nhập, đợt giao (suy ra) | 15 | — | 15 | 0 |
  - Điểm giống câu anh em: dưới 80 có 17,6% câu public đã trả lời, nhưng chỉ 3,4% câu train đúng; dưới 90 là 52% so với 7,6%. Câu public diễn đạt khác train nhiều hơn hẳn.
  - Cổng chặn đại trà không lên điểm: hệ đúng 93%, nên một cổng chỉ có lợi khi hơn nửa số câu nó chặn là câu sai.
  - Lượt chẩn đoán `bo_diem_duoi_80.jsonl` (bỏ trống 65 câu có điểm giống < 80): **0,257 → 62 đúng / 3 sai**. Câu diễn đạt lạ vẫn đúng 95%; **24/27 câu sai là câu trông quen** (có câu mẫu train rất giống).
    - Hướng nghi ngờ: dữ liệu cửa hàng public bị hiểu sai giống nhau ở cả hai đường mapping (chữ trạng thái đọc theo từ khoá, gộp tên, quy đổi đơn vị), hoặc cách tính / trình bày của hàm xếp hạng, đếm (nhóm B 13%).
    - Hệ quả cho N16: câu lạ vẫn đúng 95%, nên cổng câu anh em (chặn 28 câu) có thể chặn oan; nên nộp thử một lượt tắt cổng.
  - Lượt chẩn đoán tiếp (05/11): tách nhóm B thành xếp hạng (54) và đếm (47); tách theo mẫu mapping (mẫu nào chuyển sang cửa hàng nào); tắt cổng câu anh em.
  - **Kết quả nộp 05/11** (so từng file với lượt 1: mỗi lượt chỉ đổi đúng nhóm định thử, không câu nào đổi đáp án):

    | Lượt | Đổi so với lượt 1 | Điểm | Đúng | Sai |
    |---|---|---:|---:|---:|
    | `tat_cong_cau_anh_em` | +28 câu cổng câu anh em chặn | 0,336 | 24 | 4 (14%) |
    | `bo_xep_hang` | −54 câu `sales.rank` | 0,276 | 47 | 7 (13%) |
    | `bo_map_theo_nghia` | −169 câu của 4 cửa hàng ghép cột theo nghĩa | 0,175 | 155 | 14 (8,3%) |
    | `public_run4` | −7 câu (3 hoà hạng, 4 đổi plan), +31 câu mới | **0,342** | | |

    - Suy ra: `count_where` sai 13 − 7 = **6/47 (13%)**; các cửa hàng còn lại (khớp tên cột hoặc README) sai 27 − 14 = **13/201 (6,5%)**. 23/54 câu xếp hạng nằm trong 4 cửa hàng ghép theo nghĩa, nên hai lượt chẩn đoán có phần chồng nhau.
    - Run4 so với lượt 1: hiệu (đúng − sai) của phần thay đổi là +26. 31 câu mới có **ít nhất 25 câu đúng** (≥ 81%), dù 7 câu bị bỏ là đúng hay sai. Trong 7 câu bị bỏ có ít nhất 1 câu sai. Chưa tách riêng được tác dụng của cổng hoà hạng (cần nộp run2).
    - **Đường ghép theo nghĩa giữ lại:** đúng 92%, so với 93,5% ở các cửa hàng khác.
    - **Tỉ lệ sai cao nhất là các câu xếp hạng và đếm (13%).** Theo thống kê lượt 1, 40/101 câu nhóm này dính tới khách (xếp khách theo số đơn hoặc doanh thu, đếm khách có ≥ N đơn). Nghi ngờ cách nhận ra một khách (khách lẻ, mã khách hay tên hay số điện thoại) ở định dạng mới. Rà trên train.
    - **Bỏ trống lớn nhất là mapping, không phải độ chính xác:** 6/14 cửa hàng public trượt mọi đường mapping (log run4, chỉ đếm), **360 câu (36%)**. Cả 6 cửa hàng trượt cùng một bộ kiểm tra: không có bảng orders/lines, trạng thái, khoảng ngày, dòng thuộc đơn, tức không dựng được mapping nào. Train chỉ có 2/30 cửa hàng như vậy (biz_123, biz_124: N27). N27 là đòn bẩy lớn nhất.
- Docker chưa làm (kế hoạch 10–12/11, chờ guideline BTC): llama-server CUDA ≥ 12.8 trong image, chép `assets/` (H14), chạy thử đủ 6 giờ trên máy thuê.

## M. Phiên 4: cổng hoà hạng, cửa hàng chỉ có đơn, chạy lại từ log (tối 04/11, ngày hệ thống)

**Cách đo:** con số 2294 / 0 của phiên 3 là `eval.mapping --llm-url` (8 cửa hàng ghép cột theo nghĩa bằng LLM). Chạy không có `--llm-url` thì các cửa hàng đó đi đường README: **2292 / 0** với cùng code. Hai số chỉ so được khi cùng cờ.

**Sau N25 + N26 (`eval.mapping --llm-url`): 2331 đúng / 0 sai / 669 bỏ trống, PA +0,777** (trước 2294 / 0 / 706, +0,765). Log: `outputs/eval_mapping_s4a.log`. 335 test qua.

- [x] **N25 (TB). Bảng xếp hạng bị hoà mà vẫn trả lời.** Luật §9 xếp hoà theo mã, nhưng hoà là lúc đáp án nhạy nhất với mọi khác biệt nhỏ trong cách đọc dữ liệu.
  - Căn cứ (đo trên train): 281 câu xếp hạng trả lời đúng, **không câu nào** hoà ở ranh giới top-k hay trong top-k. Trong khi đó, xếp khách theo số đơn trong một tháng thì **39%** số tháng hoà ở hạng 1 (60/154 tháng, 10 cửa hàng có mapping tay). 11 câu train loại này mà không câu nào hoà: nếu bộ sinh đề không tránh hoà, xác suất chỉ khoảng 0,6¹¹ ≈ 0,4%. Vậy **bộ sinh đề bỏ các câu hoà**. Khi số liệu của hệ cho ra hoà, gần như chắc chắn số liệu đã khác của bộ sinh đề ở đâu đó.
  - Sửa: `sales._tied` (hoà ở ranh giới k; hoà trong top k khi đáp án là danh sách có thứ tự; bảng thì không xét thứ tự dòng). Ba hàm xếp hạng (bán hàng, công nợ, nhà cung cấp) ghi chú `tie`; [V] đặt `Signals.ranking_clear = False`; [E] chặn với lý do `tie`. Có test (`tests/test_rank_ties.py`).
  - Đo: train không mất câu đúng nào (không câu xếp hạng nào bị gắn cờ). Public lượt 1 chạy lại: **chặn 3 câu `sales.rank`** đã trả lời.
- [x] **N26 (Cao). Cửa hàng chỉ có bảng đơn, không có dòng hàng** (train biz_110: "mỗi dòng một đơn hàng, không có chi tiết mặt hàng"). Trước đây cả cửa hàng bỏ trống.
  - Căn cứ: README ghi "**tiền hàng của đơn**: cộng thành tiền các mặt hàng, trước giảm giá của đơn, chưa gồm phí giao", đúng định nghĩa doanh thu một đơn ở §1. Bốn cửa hàng train có cả cột "tổng tiền hàng của đơn" lẫn dòng hàng (108, 119, 120, 128): **100%** đơn có cột này bằng tổng thành tiền các dòng.
  - Sửa:
    - cột chuẩn mới `orders.goods_amount`;
    - `frames.orders` lấy doanh thu từ cột này khi không có bảng dòng hàng; mọi số cần dòng hàng (số lượng, xếp hạng mặt hàng…) không có bảng nên bỏ trống;
    - `ExecResult.requires` ghi `orders.goods_amount` thay cho `lines.line_amount` (`frames.requires`);
    - `Mapping.ok` và các bước kiểm tra nhận cửa hàng chỉ có đơn (kiểm tra số âm áp cho tiền hàng của đơn);
    - đường README (`from_readme._orders_only`): bảng có mã đơn, ngày, trạng thái, tiền hàng; mã đơn phải không lặp.
  - **Kiểm tra nghĩa mới (H17):** "tiền hàng của đơn khớp tổng dòng", ≥ 95% đơn khớp khi cửa hàng có cả hai (train 4/4 cửa hàng 100%). Kiểm tra này bắt luôn trường hợp cột thành tiền của dòng bị map sai.
  - Đo: biz_110 **37 đúng / 0 sai / 3 bỏ trống** (trước 0 / 0 / 40). Có test (`tests/test_orders_only.py`).
  - [ ] **Chưa kiểm chứng:** "Chờ giao" được đọc là **đang giao** (`STATUS_WORDS`). Căn cứ: §8 nói mỗi đơn có đúng một trong bốn trạng thái, và chờ giao không phải hoàn thành, huỷ hay trả hàng; 53% đơn chờ giao chưa trả tiền, giống đơn đang giao. Nhưng 15 đơn này rơi vào 01–03/07/2026, ngoài mọi kỳ câu train hỏi, nên chưa đáp án nào xác nhận.
  - Chưa làm: công nợ của cửa hàng chỉ có đơn (cột "số khách còn nợ của đơn"). Train không hỏi công nợ ở biz_110.
- [x] **Công cụ `tools/replay_run.py`: chạy lại một lượt từ log của chính nó**, không cần LLM. Lấy mapping và plan đã ghi trong log, chạy phần sau plan bằng code hiện tại, chỉ in số đếm thay đổi theo hàm và theo cổng (không in câu hỏi hay đáp án, đúng N22). Chạy lại lượt 1 bằng code cũ thì khớp 1000/1000 dòng. Dùng để đo cổng mới trên public và dựng file chẩn đoán trong khoảng 1 phút, thay cho 23 phút chạy lại.
  - Giới hạn: mapping lấy từ log, nên thay đổi ở mapping (như N26) không hiện ra. Muốn thấy thì phải chạy `predict` lại.
- [x] **N28 (TB). Bật "không trả lời được" nhóm A: kỳ hỏi nằm hoàn toàn ngoài khoảng ngày có dữ liệu** (§7: "kỳ nằm hoàn toàn ngoài khoảng ngày có dữ liệu của shop … không trả lời được, không phải 0").
  - Đo trước khi bật (train, mapping tự động không LLM, plan đã lưu): kỳ hỏi hoặc kỳ so sánh nằm hoàn toàn ngoài khoảng ngày của bảng đơn có **16 câu, cả 16 đều là unanswerable**. Còn 44 câu unanswerable có kỳ nằm trong dữ liệu: nhóm B (cửa hàng không ghi loại thông tin đó) và câu chủ quan, chưa bật.
  - Sửa: `Signals.outside_data` tính theo khoảng ngày của bảng đơn, tức khoảng dữ liệu của cửa hàng (không lấy khoảng của từng bảng: tồn kho chỉ có một ngày ảnh). Chỉ tính khi [R] thấy hai dòng §7 không đổi. [E] trả `unanswerable` khi câu đã đọc được, mapping dùng được, tên đã nối, cổng câu anh em và cổng thuật ngữ không chặn. Kỳ chỉ nằm một phần trong dữ liệu thì không thuộc nhóm này (§7).
  - Danh sách dòng luật [R] soát gom về `pipeline.rule_ids()` (trước đây 5 chỗ tự tính lại). Có test (`tests/test_unanswerable.py`).
  - Đo sau khi bật (`eval.mapping --llm-url`): **2347 đúng / 0 sai / 653 bỏ trống, PA +0,782** (+16 câu, ở 4 cửa hàng). Log: `outputs/eval_mapping_s4b.log`.
  - Kỳ chỉ nằm một phần trong dữ liệu (§7 "tính trên phần có dữ liệu"): hệ vẫn bỏ trống, nhưng đo trên train **không câu nào** bị bỏ trống chỉ vì lý do này, nên chưa đáng sửa.
  - Rủi ro còn lại: mapping bỏ sót một sheet đầu kỳ làm khoảng ngày bắt đầu muộn hơn thật. Kiểm tra "ngày cuối khớp README" chỉ bắt được phía cuối.
- [x] **N29 (Cao). Mapping chuyển từ mẫu chỉ có những cột mà cửa hàng mẫu có.** Phân loại 653 câu train còn bỏ trống: 324 câu "hàm không ra kết quả", trong đó **142 câu doanh thu / tỉ trọng doanh thu** có bộ lọc theo một thuộc tính mà mapping tự động không đọc: hoạt chất 26, nhóm khách 32 (+2 unanswerable), thuốc kê đơn 25, nhóm hàng 26, thanh toán 8, nhân viên 7. Ví dụ biz_108 chuyển từ mẫu biz_120, mà biz_120 không có nhóm khách, nên "nhóm khách" của biz_108 bị bỏ dù README ghi rõ.
  - Sửa: `from_readme.enrich`, chạy với **mọi** mapping ứng viên trước khi kiểm tra (`transfer._passes`). Thêm các cột README gọi bằng cụm nghĩa cố định, chỉ khi mapping chưa có cột đó:
    - trên bảng đơn: "mã nhân viên bán", "hình thức thanh toán của đơn", "kênh bán", "nhóm khách"; nếu không có thì tra nhóm khách từ danh sách khách theo **mã khách** mà bảng đơn đang đọc (giống mapping tay biz_111);
    - trên danh mục: "nhóm hàng", "hoạt chất", "thuốc kê đơn", từ chính danh mục, hoặc tra từ danh sách thuốc theo **mã hàng**.
  - Bảng đơn khoá theo tên khách thì không tra nhóm (không có mã để khớp). Có test (`tests/test_mapping_enrich.py`).
  - Đo phần này (`eval.mapping --llm-url`): **2407 đúng / 0 sai / 593 bỏ trống, PA +0,802** (+60 câu: biz_108 +16, 111 +9, 120 +17, 128 +7, 129 +11). Log: `outputs/eval_mapping_s4c.log`.
  - Phần 2: mapping không có bảng danh mục nào (cửa hàng mẫu không có, ví dụ hai nhà thuốc chuyển từ biz_103) thì thêm danh mục của README, khi cột mặt hàng của dòng hàng chính là "mã hàng" của README. Kèm nhóm hàng, đơn vị cơ bản, hoạt chất và kê đơn tra theo mã.
- [x] **N30 (Cao). Plan đọc đúng mà bị cổng căn cứ bỏ.** Gọi lại LLM (có cache) cho 25 câu train không có plan: **10 câu** bị loại chỉ vì LLM tự thêm `order_status = completed` vào câu đếm đơn / doanh thu thường ("bữa qua bán được mấy đơn"), 3 câu vì "tm", "tiền tươi" (tiền mặt) không được coi là căn cứ, 1 câu vì "không cần đơn bác sĩ". Public lượt 1 có **109 câu** dừng ở bước này, nhiều khả năng cùng nguyên nhân.
  - Sửa (`grounding.drop_restated_status`): bộ lọc trạng thái chỉ gồm hoàn thành / đang giao, trong câu không nhắc trạng thái nào, là nhắc lại mặc định §1 nên **bỏ bộ lọc, giữ plan**. Câu có nói "hoàn thành", "thành công", "xong", "đang giao"… thì giữ bộ lọc như cũ (hàm số liệu không nhận bộ lọc trạng thái nên vẫn bỏ trống). Bộ lọc "huỷ" không có căn cứ vẫn làm plan bị loại.
  - Kênh bán và hình thức thanh toán được coi là có căn cứ khi câu chứa một từ đồng nghĩa của mã đó trong `assets/linking/synonyms.json`. Đây là bộ từ bước nối tên đã dùng, nên hai bước không lệch nhau. "đơn bác sĩ" thành từ nhận diện của bộ lọc kê đơn.
  - Đọc lại (LLM có cache) các câu train đang không có plan: **thêm 28 câu có plan**. File plan cũ lưu ở `outputs/bank/llm_plans.before_N30.jsonl`. Có test (`tests/test_plan_reading.py`).
  - **Đo N29 phần 2 + N30 (`eval.mapping --llm-url`): 2433 đúng / 0 sai / 567 bỏ trống, PA +0,811** (+26 câu; biz_110 lên 40/40). Log: `outputs/eval_mapping_s4d.log`. 344 test qua.
  - Còn lại trong 25 câu dò: 4 plan sai schema (so sánh theo bộ lọc thiếu `filters`, kỳ `months` ghi start/end, answer_type mâu thuẫn), 3 câu LLM chọn sai chỉ số.
- [x] **N32 (TB). Plan sai schema ở những dạng đã gặp trên train thì tự sửa** (`nlu/repair.py`; chỉ sửa khi kiểm schema báo lỗi, plan sau khi sửa vẫn qua các cổng căn cứ). Ba dạng, mỗi dạng chỉ có một cách hiểu:
  - so sánh theo bộ lọc mà viết thành 2 measures, thiếu `compare.filters`: measure đầu là phần được hỏi, measure sau là phần đem ra so (giống plan tay "ca chiều so với ca sáng");
  - chuỗi tháng ghi bằng start/end: tính số tháng `n`;
  - câu đếm mà LLM ghi `answer_type` percent: chỉ sửa khi câu hỏi không có từ phần trăm nào.
  - Đọc lại (LLM có cache): thêm 6 câu train có plan. Có test (`tests/test_plan_repair.py`).
  - Đo (`eval.mapping --llm-url`): **2439 đúng / 0 sai / 561 bỏ trống, PA +0,813** (+6). Log: `outputs/eval_mapping_s5a.log`.
- **Chuẩn bị Kaggle K1 và Docker (05/11):**
  - `tools/kaggle_pack.py` đóng gói mã nguồn (0,5 MB) và train (128 MB) để tải lên một Dataset riêng tư; `kaggle/k1_qwen14b.ipynb` mở gói rồi chạy `tools/kaggle_k1.py`. Script này build llama.cpp cho T4, tải 8B và 14B, chạy K3 trên 2 card cùng lúc, cho 14B đọc 3000 câu train (2 card, `tools/read_plans_shard.py`, cache riêng), rồi chấm `eval.mapping` với cache ghép cột của laptop (mapping giống hệt laptop). `read_plans_shard` đã chạy thử trên laptop; phần chạy trên Kaggle chưa thử được.
  - Bản nháp `docker/Dockerfile` (CUDA 12.8, llama.cpp sm_120, model nằm sẵn trong image), `docker/predict.sh` (server không lên thì chạy baseline, vẫn có file nộp), `.dockerignore`, hướng dẫn buổi GPU trong `docker/README.md`. Chưa build: phải build trên máy RTX 5090 thuê dạng VM.
- **Public run3** (code cuối phiên 4, `outputs/public_run3/`): 392 câu trả lời; so với run2: +29 câu (10 nhờ N30, 19 nhờ N29), −4 câu. Chưa nộp (kế hoạch nộp: `docs/CAN_XAC_MINH.md`).
- [ ] **N31 (TB). LLM đọc lại câu khác đi khi thẻ dữ liệu (data card) trong prompt đổi.** N29 thêm cột vào mapping làm thẻ dữ liệu đổi, nên 4 câu public run2 có trả lời thì run3 ra plan khác (3 câu không còn plan). Chạy lại với cùng code thì vẫn tất định (run2 khớp lượt 1). Nhưng mọi thay đổi ở mapping đều có thể đổi cách đọc câu ở chỗ khác. Hướng: đo xem thẻ dữ liệu giúp được bao nhiêu câu; nếu ít thì chỉ đưa vào prompt những trường thật sự cần.
- [ ] **N27 (Cao). Định dạng train mà mọi đường mapping đều trượt: biz_123 (sqlite POS), biz_124 (3 nguồn).** README hai cửa hàng này không mô tả từng cột theo khuôn, nên đường README không đọc được. Đường ghép theo nghĩa thì cần một cửa hàng mẫu cùng tên file, mà train không có cửa hàng anh em nào. Hướng làm: từ điển **tên cột** (tách CamelCase và gạch dưới, bỏ dấu) → cột chuẩn, rút từ mapping của 30 cửa hàng train, đo leave-one-out. Theo ghi chú cũ (trước N22), dev_003 gần biz_124.
- Nghi ngờ đã xét mà chưa thấy lỗi: chữ trạng thái (`STATUS_WORDS` cặp từ chặt, từ lạ thì cả cửa hàng dừng), khách lẻ (bộ sinh dữ liệu dùng chung cho train và public, nên nhiều khả năng các cách ghi đã gặp hết trên train), phiếu trả hàng (§0: trạng thái lấy theo đơn).
- Thống kê từ log lượt 1 (chỉ đếm): 101 câu nhóm B gồm 54 xếp hạng (khách theo số đơn k=1: 10; ngày theo doanh thu: 12; mặt hàng theo số lượng: 14; khách theo doanh thu: 8; tháng: 7; lãi: 3) và 47 đếm (khách có ≥ N đơn, kể cả tỉ lệ: 22; đơn ≥ X tiền: 13; ngày ≥ X tiền: 12). **40/101 câu dính tới khách.**

## N. Phiên 6 (đêm 05/11): định dạng lạ (N27), khách vãng lai (N33), README của image

- [x] **N33 (TB). Khách vãng lai ghi bằng chữ chưa gặp thì thành "khách" mua nhiều nhất.** `blank_walk_ins` chỉ biết các cách ghi đã gặp trên train ("khách lẻ", "lẻ", "kl", "khách vãng lai", "vãng lai"). Một cửa hàng ghi "Khách hàng lẻ" hay một mã giữ chỗ thì "khách" đó đứng đầu mọi bảng xếp khách theo số đơn và theo doanh thu, và làm mỗi phép đếm khách dư 1. Kiểu sai này khớp với nhóm sai nhiều nhất ở public (xếp hạng 13%, đếm 13%, 40% số câu của hai nhóm dính tới khách).
  - Căn cứ (train, 25 cửa hàng có ghi khách): khách vãng lai chiếm **39,2–40,5%** số đơn ở mọi cửa hàng; khách thật đứng đầu chiếm **tối đa 0,6%**.
  - Sửa: mã khách chiếm từ 5% số đơn trở lên **và** gấp 10 lần số đơn của khách trung vị thì coi là khách vãng lai, có ghi cảnh báo trong `db.warnings`. Không chạm cửa hàng nào trên train (khách thật lớn nhất 0,6%). Có test (`test_a_walk_in_spelling_never_met_is_known_by_its_share_of_orders`): bắt cách ghi lạ chiếm 40%; cửa hàng chỉ có 4 khách thật, mỗi khách 20–30% thì không ai bị coi là vãng lai.
  - Chưa biết đây có phải nguồn sai ở public không. Cửa hàng không có mã khách mà ghi tên kèm số điện thoại, hay một khách ghi hai kiểu tên, vẫn chưa xét.
- [ ] **N27 (Cao), phần 1. Cửa hàng có định dạng lạ.**
  - **Căn cứ:** đếm từ log run4 (không đọc dữ liệu public):
    - 6/14 cửa hàng public không có mapping, 360 câu;
    - 5/6 cửa hàng không thử được đường nào ngoài README, tức không có mẫu train nào chung tên file;
    - 1 cửa hàng còn lại có mẫu nhưng thiếu cột bắt buộc.
  - **Cách đo mới, chỉ dùng train (`tools/variant_eval.py`):** lấy cửa hàng có mapping tay, đổi tên mọi cột sang tên mà cửa hàng khác dùng cho cùng nghĩa (hoặc viết lại kiểu khác), sửa README cho khớp. Dữ liệu giữ nguyên nên chấm được bằng đáp án train. Bốn kịch bản:
    - **A**: còn mẫu của chính nó;
    - **B**: bỏ mẫu của chính nó;
    - **C1, C2**: như A, B nhưng đổi cả tên file và tên bảng sang "bang_a", "bang_b"…
  - **Sửa 1, `transfer.stem`:** bảng trong file cơ sở dữ liệu nhận theo tên bảng. Trước đây tên file nằm trong gốc tên, nên sqlite đổi tên file thì không ghép được với mẫu nào (đã chạy thử xác nhận). Bảng `don_hang` của sqlite cũng không gặp được `don_hang.csv` của 3 cửa hàng csv. Có test.
  - **Sửa 2, `_ask_required_again`:** cột bắt buộc LLM không ghép được thì hỏi lại một lần, chỉ trong các cột chưa dùng. Ví dụ: bản sao của biz_123 mất cột "Số lượng sản phẩm" trong một câu hỏi 8 cột, nên mất cả mapping. Bước kiểm tra "thành tiền khớp số lượng × đơn giá" chặn nếu lần chọn sau sai. Có test.
  - **Sửa 3, `by_role`:** khi mọi đường khác trượt, LLM ghép bảng của cửa hàng với bảng của từng mẫu theo vai trò (xem tên, cột, giá trị, số dòng), rồi ghép cột theo nghĩa như cũ. Nếu bảng đơn và bảng dòng hàng rơi vào cùng một bảng thì không đoán. Có test.
  - **Đo:**
    - kịch bản A: 10/10 bản sao map lại được, **926 đúng / 0 sai**, khớp hoàn toàn mapping tay;
    - kịch bản B (trước sửa 2 và 3): 7/10, **555 đúng / 0 sai**;
    - `eval.mapping` (sửa 1–3 cùng N33): **2493 đúng / 0 sai / 507 bỏ trống, PA +0,831** (log `outputs/eval_mapping_s6a.log`). biz_123 từ 0 lên 57 câu.
  - **Đổi lại, biz_111 mất 3 câu (107 → 104).** Nó giờ ghép theo nghĩa với mẫu biz_123, trước đây đi đường README. Trong lần ghép theo nghĩa, LLM bỏ sót cặp `SLQuyDoi` ↔ "SL quy đổi" (cột không bắt buộc), nên mất `lines.base_qty` và 3 câu "bán chạy nhất" bỏ trống. Chưa sửa: hỏi lại cả cột không bắt buộc thì không bước kiểm tra nào chặn được lần ghép sai.
- [x] **N34 (TB). Bộ lọc chỉ nhắc lại chỉ số được hỏi** (`grounding.drop_restated_metric`, cùng kiểu N30). Căn cứ, train 05/11:
  - "tiền khách trả bớt nợ" đọc thành `debt_paid` kèm `payment_method` = "bớt nợ" / "trả nợ" / "mua chịu": 13 câu;
  - "xe chở được bao nhiêu đợt hàng" đọc thành `delivery_count` kèm `vehicle_model` = "xe chở": 6 câu;
  - "cộng mọi món tính theo ly" thành bộ lọc `unit` (10 câu), nay chuyển sang đơn vị của chỉ số (§3 "bao nhiêu <đơn vị>"). Chỉ chuyển khi chỉ có một đơn vị.

  Kèm theo: `quantity` với đơn vị mà cửa hàng không hề ghi thì không trả lời, thay vì trả 0. Một câu "… tính theo ly ta" ("ta" là trợ từ) có plan thứ hai với đơn vị "ly ta"; sau khi chuyển bộ lọc, câu này ra `[214, 0]`, sai (đã chạy thử xác nhận). Có test.
- [x] **N35 (Cao). Mapping chuyển từ mẫu không có sổ thu tiền thì mất mọi câu công nợ và lãi gộp** (`from_readme.with_conventions`, chạy trong `enrich`).
  - Căn cứ: biz_106 và biz_109 chuyển từ mẫu biz_120 (không có sổ thu, "phải trả cả đơn", giá vốn trên dòng), dù có `SoQuy`, cột "Tổng sau giảm giá", cột "Giá vốn". Phần "Quy ước" của README gọi tên các cột này theo khuôn cố định: "**A** là số tiền trả lần đó; **B** là số khách phải trả cho cả đơn", "**Z** là giá vốn một đơn vị bán" (cơ sở dữ liệu thì ghi `bang.Cot`).
  - Sửa: khi mapping chưa có thì thêm
    - `orders.total_due` = B;
    - `lines.unit_cost` = Z;
    - `orders.payment_method` = cột duy nhất của bảng đơn mà ≥ 90% giá trị đọc ra phương thức thanh toán;
    - bảng `payments`: bảng chứa A, chỉ một kiểu bố cục, có đúng một cột mã đơn mà ≥ 95% giá trị là mã đơn có thật, và đúng một cột ngày. Không thoả thì không đoán.
  - Có test.
  - Đo trên 2 cửa hàng: biz_106 75 → 98, biz_109 77 → 103, có **1 câu sai**: plan bỏ sót tên khách, xem N36.
- [x] **N36 (Cao). Plan bỏ sót một tên có trong câu hỏi.** Câu "khách cao thu hạnh ghi nợ thêm bao nhiêu": LLM không ghi khách mà ghi bộ lọc trạng thái, N30 bỏ bộ lọc đó, nên plan còn lại trả tổng của cả cửa hàng. Câu này lộ ra khi N35 có dữ liệu công nợ.
  - Căn cứ (train): câu nêu tên khách hoặc tên hàng của cửa hàng (từ 2 chữ trở lên, khớp nguyên từ) mà plan không có bộ lọc trường đó chỉ có **1 câu**, chính là câu sai này.
  - Sửa: `nlu.omitted_names` khi nối tên, ghi vào `ResolvedPlan.omitted`; [V] đặt `entities_ok = False`. Tên nằm trong giá trị của một bộ lọc khác ("nhóm cà phê sữa") thì không tính là bỏ sót. Có test.
- **Thêm cho N27 (sau khi đo kịch bản B):**
  - **`by_role` xếp mẫu theo số bảng của cửa hàng mà mẫu đọc được, rồi mới tới tỉ lệ.** Trước đó một sổ chỉ có một bảng được thử trước các bản xuất nhiều bảng.
  - **`unfilled_extras`:** bảng phụ (không phải đơn, dòng hàng) có cột bắt buộc bị trống thì bỏ riêng bảng đó, không đánh trượt cả cửa hàng. Bản sao của biz_120 có bảng đơn và dòng hàng ghép đúng, nhưng danh mục bị ghép nhầm thành lịch sử giá, nên cả cửa hàng trượt.
  - **`quantity` và `rank` không còn báo lỗi `KeyError`** khi mapping không có `base_qty` (đã chạy thử xác nhận lỗi). Có test.
  - **Đo kịch bản B sau các sửa này:** bản sao biz_124 81 đúng / 0 sai (tay 93), biz_120 94 / 0 (tay 115), cả hai qua mẫu biz_123.
- **N27 phần 1, thêm `requantify`:** khi chỉ riêng kiểm tra "thành tiền khớp số lượng × đơn giá" trượt, thử từng cột số chưa dùng của bảng dòng hàng làm số lượng. Chỉ nhận khi đúng một cột làm mọi kiểm tra qua; hai cột cùng qua thì không đoán. Có test.
  - Căn cứ: biz_124 thật, ghép bảng theo vai trò với mẫu biz_123. Bảng đã ghép đúng, nhưng LLM lấy "SL cơ bản" (số lượng quy ra đơn vị cơ bản) làm số lượng của dòng, bỏ sót "Slg", nên cả cửa hàng trượt.
  - Đo: **biz_124 từ 0 lên 85 đúng / 0 sai / 33 bỏ trống** (mapping tay được 93).
- **N27 phần 1, kịch bản C2 (đổi tên file, bỏ mẫu của chính nó) lộ 5 câu sai ở bản sao biz_123** (ghép theo vai trò với mẫu biz_124). Hai bản sửa:
  - **Cột mã đơn không mang nghĩa nào khác** (`_one_meaning_each`). LLM lấy cột mã đơn làm luôn mã hàng; cả hai cột đều bắt buộc nên `_one_meaning_each` cũ giữ cả hai. Mã hàng và tên hàng từ một cột thì vẫn hợp lệ (cửa hàng chỉ ghi tên). Có test.
  - **Kiểm tra bắt buộc mới "mã hàng và tên hàng hợp lý"** (`build.product_check`): ≥ 10 mã hàng, ≥ 50% tên hàng có khoảng trắng.
    - Căn cứ train: mọi cửa hàng có 50–80 mã hàng, 100% tên có khoảng trắng.
    - Sau bản sửa trên, mã hàng được hỏi lại và chọn phải cột "Id cửa hàng" (một giá trị). Tên hàng lại là cột mã ("SP0001"), nên bảng xếp hạng ra mã.
    - Hai test cũ có dữ liệu giả 1–2 mặt hàng tên một chữ, không giống cửa hàng nào; đã sửa dữ liệu cho giống thật.
  - Đo: bản sao biz_123 ở C2 từ 47 đúng / 5 sai thành **70 đúng / 0 sai** (qua mẫu biz_111).
  - Đo trước bản sửa: C1 801 / 0 / 225; C2 650 / 5 / 371; train `eval.mapping` 2651 / 0 / 349, PA +0,884 (log `eval_mapping_s6c.log`).
- **Public run5** (code trước bản sửa C2, `outputs/public_run5/`): 438 câu trả lời, 3 unanswerable. Đếm từ log: đường ghép theo vai trò đã chạy cho 5/6 cửa hàng chưa map được nhưng **chưa cửa hàng nào qua kiểm tra**. Lỗi là thiếu cột bắt buộc ("thiếu bảng"), hoặc nhiều kiểm tra trượt cùng lúc (schema, trạng thái, số âm). Mẫu được chọn phần lớn là sổ một bảng (101, 105, 126, 103). Chưa xem giá trị nào của dữ liệu public (N22).
- **N27 phần 2, kịch bản E: README sơ sài** (`variant_eval.py --strip-readme`: bỏ mọi mục "Cột trong …", chỉ giữ tên file và "Quy ước"; kèm đổi tên file, bỏ mẫu của chính nó).
  - **E tái hiện đúng kiểu trượt của public:** 4/10 bản sao (111, 115, 124, 126) trượt y như 6 cửa hàng public (đường README trượt, ghép theo vai trò "thiếu bảng"). 6/10 map được, 497 đúng / 0 sai.
  - Ba bản sửa:
    - **`_as_rows`:** mẫu sổ phẳng có mã đơn (đơn và dòng hàng cùng một bảng), cửa hàng không có cột nào gom dòng, thì mỗi dòng là một đơn (§8, mã đơn `_row` như mapping tay biz_126). Trước đó sổ không mã đơn chỉ map được khi có đúng mẫu cùng kiểu. biz_126 ở E từ 0 lên **35 / 0**.
    - **Giới hạn khi ghép bảng theo vai trò:**
      - bảng của mẫu đọc trạng thái đơn từ một cột chỉ được ghép với bảng có cột chữ trạng thái (`_has_statuses`, ≥ 90% giá trị đọc ra trạng thái);
      - bảng của mẫu đọc thành tiền dòng chỉ được ghép với bảng có cột tiền (`_has_amounts`, trung vị ≥ 1.000 đồng);
      - không bảng nào đạt điều kiện thì không giới hạn.

      Căn cứ: bản sao biz_115 bị ghép sổ bán với "Bảng kê phiếu giao hàng" (cùng mã đơn, tên hàng, số lượng, nhưng không có trạng thái); biz_124 bị ghép dòng hàng với bảng bán theo lô (không có tiền). biz_115 ở E từ 0 lên **100 / 0**.
    - Công cụ `variant_eval`: cột vừa là mã vừa là tên thì lấy tên khác theo nghĩa "tên". Cột mã không nhận tên của cửa hàng dùng chung một cột cho mã và tên (trước đó bản sao có cột mã tên "Tên hàng hóa", không giống cửa hàng thật).
  - Còn trượt ở E: 111 (đã ghép bảng đúng nhưng tên hàng chỉ có ở danh mục), 124. Cả hai đều bị kiểm tra chặn, không ra câu sai.
  - **Đo E sau các sửa: 645 đúng / 0 sai / 381 bỏ trống** (trước 497 / 0); 8/10 bản sao map được.
  - **Hồi quy đã sửa:** lúc đầu `_as_rows` chạy ở mọi đường ghép theo nghĩa. biz_107 (40 → 29) và biz_126 (40 → 36) khi đó được map bằng mẫu 105 chuyển sang "mỗi dòng một đơn", thay vì đi đường README tốt hơn. Nay chỉ dùng ở đường cuối (ghép theo vai trò): hai cửa hàng trở lại 40/40, bản sao biz_126 ở E vẫn 35 / 0.
  - Public run7 (code có các sửa này và N38): trùng hoàn toàn run6 (438 câu trả lời). 6 cửa hàng public vẫn chưa map; theo E, các cửa hàng có trạng thái và cột tiền đọc được giờ có thêm cơ hội, nhưng ở public chưa thành mapping.
- **Đã đo, không đổi: đưa đường README lên trước đường ghép theo nghĩa.** Với 10 cửa hàng train đang map theo nghĩa mà đường README cũng qua, đi README trước được:
  - thêm: 101 (+4), 103 (+1), 111 (+3), 129 (+4);
  - mất: 105 (−10);
  - còn lại không đổi; cả hai đường đều 0 sai.

  Tổng chỉ +2, nằm trong mức nhiễu, nên giữ thứ tự cũ.
- [x] **N38 (TB). Nhập hàng mà cửa hàng không ghi thì trả không trả lời được (§7).**
  - Căn cứ (train): phần "## Quy ước" có ở cả 30 README.
    - Cửa hàng có mục "**Nhập hàng**": 104/104 câu nhập hàng (tổng tiền nhập, giá nhập bình quân, số phiếu, xếp hạng nhà cung cấp) trả lời được.
    - Cửa hàng không có mục đó: 5/5 câu là unanswerable, kể cả biz_122 dù có file `DonNhapHang`.
    - Riêng tồn kho thì không dùng được tín hiệu này: cửa hàng không có mục "Tồn kho" vẫn có 12 câu tồn kho trả lời được.
  - Sửa:
    - `build.readme_conventions` ghi các mục của "Quy ước" vào `CanonicalDB.conventions`;
    - [V] đặt `Signals.not_recorded` khi câu hỏi về nhập hàng, "Quy ước" không có mục "nhập hàng", mapping không có bảng nhập, và hai dòng §7 không đổi;
    - [E] trả `unanswerable` khi đọc được câu, mapping dùng được, tên đã nối.
  - README không có phần "Quy ước" thì không suy ra gì. Có test.
- **N22 đổi (06/11): BTC cho phép xem dữ liệu public.** Giữ các giới hạn:
  - chỉ xem để tìm kiểu lỗi;
  - mọi bản sửa là quy tắc chung, không có id cửa hàng hay câu hỏi trong code, kể cả comment (`test_no_id_logic` đã bắt một lần 06/11);
  - không gán nhãn, không viết mapping tay cho cửa hàng public;
  - mỗi bản sửa có test, train vẫn 0 sai.

  6 cửa hàng public chưa map gồm 4 ngành **không có trong train**: điện thoại (011, 014), sửa xe (012), mẹ và bé (013). Hai cửa hàng còn lại có dạng đã gặp: 003 là bản xuất phần mềm có hoá đơn và chi tiết gộp một sheet, 009 chỉ có bảng hoá đơn.
- [x] **N39 (Cao). Hai dạng đã gặp mà vẫn không map được.**
  - **Đơn ghi trùng** (§8 "hai dòng của cùng một đơn giống nhau ở mọi ô: tính một lần"). Đường README cho cửa hàng chỉ có bảng đơn (N26) từ chối khi mã đơn lặp; cửa hàng 009 có 308/22.798 hoá đơn ghi hai lần giống hệt nhau. Nay chỉ từ chối khi hai dòng cùng mã mà khác nhau. Có test.
  - **Workbook nhiều danh sách:** `_new_groups` gom bảng theo tên file, bỏ cả nhóm khi bố cục khác nhau, nên các sheet bán hàng của 003 không được đưa cho LLM chọn. Nay `layout_groups` tách theo bố cục khi ghép theo vai trò. Có test.
  - **Bảng đơn và dòng hàng của mẫu cùng ghép vào một sheet gộp:** được phép khi sheet đó có cột mã đơn gom được dòng thành đơn (README của 003: "hoá đơn và chi tiết gộp chung sheet, thông tin hoá đơn lặp lại"). Có test.
  - **Chữ trạng thái "Khách trả"** đứng riêng một ô là trả hàng; "khách trả tiền" không phải chữ trạng thái. Có test.
  - **Đo:**
    - train `eval.mapping` **2656 / 0 / 344**, không đổi;
    - public run8: **553 câu trả lời** (run6: 438), thêm 116, mất 1. Cửa hàng 003 trả lời 97/129 câu, 009 trả lời 19/21.
    - Chưa biết 116 câu mới đúng bao nhiêu: nộp cặp run8 và `outputs/public_ablation8/bo_cua_hang_moi.jsonl` để đo.
- [x] **N40 (Cao). Sổ không có cột trạng thái: trạng thái nằm trong Ghi chú** (§8 của rulebook public, train không có dòng này). Ba cửa hàng public cần: điện thoại 011, 014; mẹ và bé 013.
  - Phép biến đổi `status_from_note`:
    - ghi chú nhắc đúng một trạng thái thì lấy trạng thái đó;
    - mọi ghi chú của đơn không nhắc trạng thái nào thì đơn hoàn thành;
    - nhắc hai trạng thái thì không rõ.

    Các dòng có ghi chú không nhắc gì (dòng Voucher, dòng tiếp theo của đơn) không tính khi gộp theo đơn.
  - Đường README nhận "ghi chú của đơn" / "ghi chú" khi không có cột trạng thái. Đường chuyển mapping, khi mẫu có cột trạng thái mà cửa hàng không có, dùng cột "Ghi chú…" duy nhất (cột phần lớn để trống, hoặc không phải chữ trạng thái).
  - Từ khoá thêm:
    - "chưa giao" → đang giao;
    - "mang trả" → trả hàng;
    - "khách trả" đứng riêng một ô → trả hàng;
    - "kiểm tra lại" **không** phải trả hàng (ghi chú của tiệm sửa xe "kiểm tra lại tuần sau" từng làm 50 phiếu thành trả hàng).
  - **Lỗi chung đã sửa: `_fill_down`.** Lệnh `ffill` lấy ô không trống gần nhất của bất kỳ dòng nào phía trên, tức ghi chú hay khách của **đơn trước**. Kết quả: một sổ điện thoại có 834/3.819 đơn thành trả hàng trong khi chỉ có 29 ghi chú trả. Nay dòng tiếp theo lấy ô ở dòng đầu của chính đơn đó. Train không đổi (2656 / 0). Có test.
- [x] **N41 (TB). Dòng "Voucher", "Dùng n điểm", "Phí ship" là khoản của đơn, không phải dòng hàng** (sổ mẹ và bé public). §1: doanh thu không trừ voucher, không gồm phí giao. Ba loại dòng này chuyển thành `voucher_discount`, `points_discount`, `shipping_fee` của đơn và bỏ khỏi bảng dòng hàng. Train không có dòng nào như vậy. Có test.
- [x] **N42 (TB). Sổ phiếu sửa xe** (mỗi dòng một phiếu, không mã, không dòng hàng):
  - đường "chỉ có bảng đơn" nhận sổ không mã (mã `_row`, §8 "bảng không ghi theo đơn");
  - đọc "tổng tiền cả phiếu" làm doanh thu, thợ làm nhân viên, "các việc đã làm" thành `services`;
  - tách biển số và dòng xe từ một ô;
  - ghi chú "bảo hành" thành `is_warranty`.

  Thêm:
  - giá trị trung bình một phiếu bỏ phiếu bảo hành (§6 Sửa xe);
  - danh sách thợ ("họ tên thợ") thành bảng `employees`;
  - `full_employee_names` đổi tên gọi có danh xưng ("A.Phúc", "a Phúc", "Phúc") sang họ tên khi khớp đúng một người.

  Có test.
- [x] **N43 (TB). Tên hàng ghi tắt** (sổ điện thoại public: "hàng bán, có thể ghi tắt, tra ở sheet Ghi tắt"). `expand_abbreviations` tìm bảng có:
  - một cột khoá chứa ≥ 20% tên trong sổ;
  - một cột tên dài hơn, cùng cột khoá phủ ≥ 80% tên trong sổ, so theo dạng chuẩn hoá (§8).

  Khi có thì mã và tên hàng tra qua bảng đó (`lookup` có `fold`). Kèm theo, `sane_base_units`: cột đơn vị cơ bản có hơn 30 giá trị thì bỏ (train tối đa 15). Có test.
  - **Hồi quy đã sửa:** bản đầu của `expand_abbreviations` kích hoạt cả ở sổ ghi theo mã ("SP001") có danh mục mã và tên, rồi đổi mã hàng thành tên hàng. Train mất 67 câu (111, 123, 127, 129); public run9 lần đầu đã dừng giữa chừng. Nay đòi ≥ 10% tên trong sổ bán ghi thẳng tên đầy đủ (sổ điện thoại public: 56/115; sổ ghi theo mã: 0). Bốn cửa hàng trở lại 107, 63, 109, 112. Có test.
- [x] **N44 (TB). Chỉ số theo ngành của §6 public** (schema plan đã có sẵn tên chỉ số, prompt không đổi):
  - sửa xe:
    - `ticket_count`: mọi phiếu, kể cả bảo hành;
    - `avg_ticket_value`: chỉ phiếu có thu tiền;
    - `vehicle_count`: số biển số khác nhau;
    - `warranty_count`;
    - `warranty_rate`: phiếu bảo hành / phiếu có thu tiền.

    Bộ lọc thêm: thợ, dòng xe (không phân biệt hoa thường, §6), phiếu bảo hành. Chỉ chạy ở sổ có biển số.
  - mẹ và bé: `voucher_discount`, `points_discount`, `shipping_fee_total`. Là số dương, theo ngày của hoá đơn, chỉ đơn không huỷ, không trả.
  - điện thoại: `trade_in_amount`. Đường README đọc thêm các cột cấp đơn của sổ gộp: "tiền bớt cho cả đơn", "tiền thu máy cũ", "số tiền khách trả cho cả đơn".
  - Cửa hàng không có cột tương ứng thì không trả lời. Có test, kỳ vọng tính tay theo từng dòng luật.
  - **Chưa làm:**
    - sửa xe: hoa hồng thợ, lượt theo việc ("sửa điện", "thay dầu láp"), xe khách quen;
    - điện thoại: dòng máy, hãng, máy mới hay cũ, trả góp, bảo hành;
    - mẹ và bé: số sữa, size bỉm, khách thành viên mới.
- **Kết quả:** cả 6 cửa hàng public trước đây chưa map nay đều map được (đo trực tiếp bằng `map_by_transfer`): 003 và 014 qua ghép theo vai trò, 009 và 012 qua đường chỉ có bảng đơn, 011 qua README, 013 qua ghép theo nghĩa. **Chưa đo độ chính xác:** 4 cửa hàng thuộc ngành không có trong train; xem `docs/CAN_XAC_MINH.md`.

### Phiên 8 (06/11)
- [x] **N45 (CAO). Cửa hàng chỉ có bảng đơn mà có thêm bảng phụ bị coi là chưa dùng được.**
  - Triệu chứng: sổ sửa xe public trả lời 0/50 ở run9. Mọi kiểm tra của mapping đều qua (6060 phiếu), nhưng `Mapping.ok` đòi tập bảng **đúng bằng** `{"orders"}`. N42 thêm bảng `employees` (danh sách thợ), nên `ok = False`. Pipeline không gọi LLM (46 câu không có plan), cổng `mapping_ok` chặn nốt 4 câu baseline đã tính ra số.
  - Sửa: "chỉ có bảng đơn" = không có bảng `lines` và bảng `orders` có `goods_amount`, như `frames.orders_only` vẫn dùng. Bảng phụ không ảnh hưởng.
  - Test: `test_contracts.py::test_an_orders_only_shop_with_a_side_table_is_usable`, `test_repair_ledger.py` (khẳng định `m.ok`). Train không đổi (2656/0).
- [x] **N46 (TB). Khái niệm mới của rulebook public, chung cho mọi ngành:**
  - §2 "trung bình mỗi ngày thứ X của kỳ": tổng của kỳ chia cho số ngày thứ X trong kỳ, kể cả ngày không có đơn (`aggregate: avg_per_weekday`, có sẵn trong schema nhưng hàm từng từ chối). Trung bình tiền làm tròn về đồng (§9). `avg_per_day` chia cho mọi ngày của kỳ.
  - §6 "thợ làm nhiều nhất": theo số lượt xe, kể cả phiếu bảo hành (`rank employee by ticket_count`).
  - §3 "nhân viên, thợ chăm chỉ nhất": nhiều ngày có đơn nhất (`work_days`). "Khách trung thành nhất": nhiều ngày có mua nhất (`days_with_purchase`).
  - §6 "xe tới nhiều lần, xe khách quen": xe theo biển số, chỉ đếm phiếu có thu tiền (`count_where` thực thể `vehicle`).
  - Mã luật chỉ được dẫn khi plan dùng đến (rulebook train không có các dòng này). Có test tính tay (`test_industry_metrics.py`).
- [x] **N47 (TB). Hoa hồng thợ** (README của sổ sửa xe public: "Hoa hồng (%): phần trăm hoa hồng của thợ, tính trên tổng Tiền các phiếu thợ làm trong tháng"):
  - cột chuẩn `employees.commission_pct`, đọc từ README ("phần trăm hoa hồng");
  - chỉ số `commission` = phần trăm × tiền các phiếu người đó làm trong kỳ, làm tròn về đồng. Chỉ trong một tháng (gốc tính là tiền của tháng). Có người trong kỳ thiếu phần trăm thì bỏ trống;
  - xếp hạng nhân viên có `with_values` thành bảng §9 (`["nhan_vien", <số đo>]`), trước đây luôn bỏ trống.
  - Rủi ro đã chặn: không có chỉ số này, LLM có thể đọc "thợ X lãnh bao nhiêu hoa hồng" thành doanh thu của thợ X; cổng thuật ngữ không bắt được vì "hoa hồng" là từ của README, không phải rulebook.
- [x] **N48 (TB). Sổ sửa xe: việc trong ô "Làm gì", dòng xe viết tắt.**
  - `nlu/jobs.py`: bảng các cách gọi việc sửa xe, theo cách đọc §6 ("nhớt" trơn là nhớt máy; "ruột" trơn là thay ruột; sửa điện không gồm bóng đèn, ắc quy) và tên thường dùng của nghề (BD/bdtq = bảo dưỡng; NSD = nhông sên dĩa; bình = ắc quy; nhớt láp = nhớt hộp số = dầu láp). Bộ lọc `service` lấy phiếu có việc đó, bỏ phiếu bảo hành. Sổ có một ô không đọc được thì mọi câu lọc theo việc bỏ trống. Trên sổ public: 6060/6060 phiếu đọc được.
  - `linking.model_lines`: §6 "tên dòng xe chỉ khác hoa/thường hoặc ghi tắt là cùng một dòng". Gộp: cùng chữ cái ("shmode"), là một phần các từ ("Vision" của Vision 110, "Alpha" của Wave Alpha), chữ đầu ("AB" của Air Blade), phần đầu ("Ex" của Exciter); "Wave α" đọc là alpha. Cách viết có thể thuộc hai dòng ("Wave" khi có cả Wave Alpha và Wave RSX) thì không gộp, và câu lọc theo dòng xe bỏ trống.
    - Lỗi đã bắt: trước đó "Air Blade" chỉ nối với đúng cách viết đó, nên sẽ đếm thiếu phiếu "AB", "airblade" mà vẫn trả lời; "Wave Alpha", "SH Mode", "Vision" thì hoà giữa các cách viết, không nối được.
    - `norm` sửa lỗi gõ telex nên "Air" thành "ai"; tên dòng xe dùng cách gấp chữ không sửa telex.
  - Xếp hạng theo dòng xe (`RankEntity` thêm `vehicle_model`).
  - **Gợi ý trong prompt** (`prompt.hints`): vài dòng cách viết plan cho sổ sửa xe, hoa hồng, "trung bình mỗi thứ X". Chỉ thêm khi cửa hàng có dữ liệu đó (cột biển số, cột phần trăm hoa hồng) hoặc câu hỏi dùng từ đó. Không câu train nào nhận gợi ý (có test), nên prompt của 3000 câu train giữ nguyên từng byte và 3000 plan đã kiểm chứng vẫn dùng được.
  - Căn cứ xem dữ liệu public: chỉ xem kiểu ghi của ô "Làm gì" và "Xe" (luật N22 đã gỡ, giới hạn "chỉ tìm kiểu định dạng"). Bảng tên việc là tri thức ngành chung, không có id cửa hàng, không gán gì cho câu hỏi.
- [x] **N49 (CAO). K1 trên Kaggle: Qwen3-14B so với Qwen3-8B, và 4 lỗ hổng cổng.**
  - Kết quả (`outputs/kaggle_k1/` trong zip; plan 14B chép vào `outputs/bank/llm_plans.14b_kaggle.jsonl`):
    - K3, 149 plan tay: 8B khớp hoàn toàn 82,6%, 14B 83,2% (+0,6 điểm; ngưỡng §11 là ≥ 3 điểm). JSON hợp lệ 93,3% / 94,6%.
    - Tốc độ trên T4: 8B 3,0 giây/câu, 14B 5,8 giây/câu.
    - `eval.mapping` cùng code hôm nay: 8B **2656 đúng / 0 sai**, 14B **2652 đúng / 10 sai** (PA +0,885 / +0,881).
    - Hai model đọc giống hệt nhau 2617/3000 câu.
  - **Quyết định: giữ Qwen3-8B.** Không hơn rõ, chậm gấp đôi, sai nhiều hơn; giữ 8B thì image Docker nhẹ hơn (5 GB so với 9 GB) và chạy private được trên laptop.
  - 10 câu sai của 14B là plan đọc sai mà lọt qua mọi cổng. 8B cũng có thể đọc như vậy ở cửa hàng lạ, nên thêm cổng (`grounding.ungrounded_measures`):
    - **phần và tổng** (5 câu): "tổng cộng mấy ly size M, cộng tất cả các món" thành [ly size M, mọi ly]. Hai measure cùng chỉ số, bộ lọc của một cái là tập con thật của cái kia, mà câu chỉ hỏi một số (không có hai từ hỏi, không có "mỗi loại / lần lượt / hai số") → bỏ;
    - **k câu hỏi nêu** (3 câu): "3 khách nào nợ nhiều nhất" mà k để mặc định 1. `stated_k` đọc "top N", "N khách/món/… nào"; số trong ngày tháng ("27/10 khách nào") hay sau từ chỉ thời gian ("tháng 3 khách nào") không tính;
    - **cùng kỳ năm trước** (1 câu): "ca chiều hơn hay kém ca sáng" thành so với năm trước, kỳ so rơi ngoài dữ liệu nên ra unanswerable (sai). Cần chữ "năm trước / năm ngoái / cùng kỳ" hoặc câu nêu hai năm khác nhau;
    - **ngưỡng chỉ nhắm số 0** (1 câu): "không bán được lần nào" thành `order_presence = 0`; hàm chỉ thấy đối tượng có mặt trong kỳ nên luôn ra 0. `count_where` bỏ trống khi ngưỡng nhận 0 mà không nhận 1. "Dưới 3 đơn" vẫn đếm như cũ.
  - Trên 3000 plan 8B, các cổng mới chỉ chặn 1 plan ("bảng 3 khách" đọc thành k=1, vốn không thể đúng). Có test (`test_k1_gates.py`).
  - **Đo lại với các cổng mới** (`outputs/eval_mapping_s8c.log`, `_s8c_14b.log`): 8B 2656 / 0 / 344 (PA +0,885); 14B **2652 / 0** / 348 (PA +0,884). Hai model hoà nhau.
  - **Bài học (xem tiếp N53):** "0 sai" của 8B trên train không phải số đo độc lập. Các cổng được dựng dần từ lỗi của chính 8B trên chính 3000 câu này, nên model nào khác cũng sẽ lộ những kiểu sai mà cổng chưa thấy. Ở public và private, 8B gặp cửa hàng lạ là tình huống tương tự. Plan của một model khác trên train là một bộ thử rẻ để tìm lỗ hổng cổng; nên dùng tiếp nếu còn giờ GPU (chỉ lúc phát triển, không dùng khi dự đoán).
- [x] **N50 (CAO). Nhóm hàng có trong README mà mapping không lấy** (public: 4 cửa hàng cũ, khoảng 30 câu theo nhóm bị bỏ trống vì không nối được tên nhóm).
  - Nguyên nhân: `enrich` chỉ thêm nhóm hàng vào bảng danh mục khi mapping **đã có** bảng đó. Các cửa hàng này chỉ có `orders` + `lines`; nhóm nằm ngay trên dòng hàng ("Phân loại: nhóm hàng", "Nhóm hàng: nhóm hàng") hoặc trong một danh mục mapping bỏ qua ("Loại sản phẩm: nhóm hàng", "Nhóm: nhóm hàng" của sổ "nối qua tên hàng").
  - Sửa (`from_readme._line_group`): mapping chưa có nhóm thì lấy cột "nhóm hàng" của chính dòng hàng; không có thì tra danh mục theo mã hàng, hoặc theo tên hàng (so không phân biệt cách viết, §8); file dòng hàng không có mục README thì nối theo cột danh mục **cùng tên cột**.
  - Kết quả: train **2681 / 0** (trước 2656; biz_121 83 → 88, biz_122 83 → 93). Public (chạy lại run9 từ log): +14 câu trả lời. Có test.
- [x] **N51 (TB). Tên Bắc – Nam** (public: "Lạc rang muối 200g" cho "Đậu phộng rang muối 200g", "Đậu phụ rán giòn" cho "Đậu hũ chiên giòn"). `linking.dialects`: thêm biến thể đổi từ miền Bắc sang miền Nam và ngược lại (lạc/đậu phộng, đậu phụ/đậu hũ, rán/chiên, vừng/mè, ngô/bắp, lợn/heo, dứa/thơm…). Chỉ đổi trên chữ **còn dấu**: "lạc" không phải "lắc" (khoai tây lắc); "lac" không dấu thì không đổi. Public: +4 câu. Có test.
- [x] **N52 (TB). Khái niệm §3 public (H4):** khách sộp (giá trị trung bình một đơn cao nhất, chỉ khách từ 3 đơn), khách hay đổi ý (nhiều đơn huỷ nhất), mặt hàng được ưa chuộng (có mặt trong nhiều đơn nhất), giờ cao điểm (khung một giờ nhiều đơn nhất, đáp án là giờ bắt đầu, number). Mỗi xếp hạng dẫn đúng mã luật của khái niệm (`RANK_TERMS`), nên cổng thuật ngữ biết hàm đọc đúng từ. Gợi ý prompt chỉ khi câu dùng từ đó (public 9 câu, train 0). Có test tính tay.
- [x] **N53 (CAO). Mã luật dẫn theo điều kiện không được kiểm** (bắt trước khi chạy). Cổng "luật không đổi" kiểm các mã trong `pipeline.rule_ids()`, dựng từ luật khai báo lúc đăng ký hàm. Bốn mã chỉ dẫn khi plan dùng tới ("trung bình mỗi thứ X", việc trong ô Làm gì, thợ làm nhiều nhất, xe khách quen) không nằm trong đó, nên [V] coi là luật đã mất và mọi câu như vậy sẽ bỏ trống. Test đơn vị không thấy vì gọi thẳng hàm tính. Sửa: `sales.CONDITIONAL_RULES` đưa vào `rule_ids()`; test `test_rank_terms.py` kiểm mọi mã mà các hình plan mới dẫn đều nằm trong danh sách và qua rulebook public.
- [x] **N55 (CAO). Sổ sửa xe với LLM (50 câu public dev_012): 0 → 37 → 43 câu trả lời.** Đọc log từng câu ở mức hình plan (không tự tính đáp án để đối chiếu), các kiểu đọc sai có hệ thống và cách sửa chung:
  - **bảng "từng / mọi thợ" với k = 1** (2 câu đã trả lời bảng 1 dòng, gần như chắc sai): `grounding.widen_each_table`: bảng có số đo, k = 1, câu không nêu số lượng mà có "bảng / từng / mọi / các / tất cả" → lấy mọi đối tượng. Gợi ý hoa hồng ghi rõ "k null, không filter employee";
  - **"3/26" đọc thành ngày 26/03/2026**: `month_of_short_year`. Người Việt viết ngày trước tháng, nên "M/YY" với YY > 12 là tháng M năm 20YY; chỉ sửa đúng dấu hiệu ngày = YY, tháng = M, năm = 20YY;
  - **quý thiếu số** ("Quý 4/2025" thành `{"kind": "quarter", "year": 2025}`, sai schema): `repair._fill_number` lấy số quý/tháng duy nhất câu nêu;
  - **`is_warranty` lặp ý chỉ số** ("phiếu có thu tiền … trung bình 1 phiếu" ghi `is_warranty = false`, cổng chỉ nhận chữ "bảo hành"): bỏ bộ lọc khi chỉ số đã nói điều đó (`avg_ticket_value` / false; `warranty_count`, `warranty_rate` / true). "Tiệm lên bao nhiêu phiếu" mà ghi `is_warranty = false` vẫn bị chặn;
  - **"đếm phiếu" thành "đếm đơn có ≥ 1 phiếu"**: `count_as_value` đổi về `value` của chính chỉ số đó (cùng nghĩa); ngưỡng khác giữ nguyên;
  - gợi ý: mã từng thứ trong tuần ("thứ Tư" từng thành `thu`, "thứ 3" thành `wed`, cả hai bị cổng chặn); việc sửa xe là `service`, không phải `product_group`; từ miền Trung "mô / rứa / ni" (bật cho câu có từ đó; "răng" bỏ vì train có "kem đánh răng").
  - Còn bỏ trống, đúng là nên bỏ: plan thêm `is_warranty` câu không nói; "thứ 3" vẫn ra `wed`; plan ghi cả 4 tên thợ; hoà hạng; "thợ mô làm ra nhiều tiền nhất" bị cổng thuật ngữ khớp với "thợ làm nhiều nhất" của §6 (plan đúng nhưng cổng khớp lỏng; để an toàn).
  - Có test (`test_plan_rewrites.py`).
- [x] **N56 (CAO). run10 (đủ 1000 câu, 06/11): 681 câu trả lời** (run9 608): 598 giữ nguyên, 79 mới (45 ở dev_012), 6 mất, 1 đổi giá trị. Cả 7 câu đổi đều do LLM đọc ra plan khác run9: schema thêm `commission`, `vehicle_model` làm grammar đổi, đường giải mã đổi theo ở vài câu. Bài học: **mọi thay đổi schema/prompt đổi cách đọc của một phần câu cũ**; phải so từng câu với lượt trước.
  - Từ 7 câu đó, sửa chung:
    - cổng "cùng kỳ năm trước" chỉ nhận năm 4 chữ số, chặn oan "tháng 7/26 so với tháng 7/25": `stated_months` đọc cả M/YY;
    - "th 6/26 so với th 6/25" đọc thành `previous` (tháng 6 so với tháng 5, **một câu sai mới**; `temporal` bỏ qua kỳ ghi kèm khi kind là previous): cổng mới, câu nêu cùng một tháng của hai năm thì không được là `previous`. Chặn 3 câu trả lời của run10, cả 3 sai kiểu này;
    - "khách trả nợ" ghi thêm `payment_method = debt` (mã) nên bị chặn: bộ lọc mã "debt" trên chỉ số công nợ là lặp ý, bỏ đi (+4 câu);
    - "**từ 10 củ trở lên**" (10 triệu) đọc thành ngưỡng 10 đồng ở run9, gần như chắc **sai**: `scale_money` nhân theo đơn vị câu viết (củ, triệu, tr: × 10⁶; k, nghìn, ngàn: × 10³) khi plan ghi đúng con số trơn.
  - `tools/replay_run.py`: log có `reading.llm_raw` (từ run10) thì đọc lại từ đầu ra LLM đã ghi qua đúng `parse_question` hôm nay (cổng, sửa plan, so baseline), chỉ bỏ bước gọi model. Áp các sửa trên lên run10 không cần chạy lại 37 phút: 684 câu trả lời (`outputs/replay/run10_s8`).
  - Train sau mọi sửa: **2681 / 0** (PA +0,894). Có test (`test_plan_rewrites.py`).
  - **Nộp 06/11: 0,608** (run9 0,540). 646 đúng / 38 sai. Phần mới đều ≥ 93% đúng (sổ sửa xe 42/3, dev_003+009 117/3, điện thoại 26/1, mẹ và bé 32/0). 31 câu sai nằm ở 8 cửa hàng cũ; bộ nộp 07/11 khoanh vùng theo hàm (`docs/CAN_XAC_MINH.md`).
- [x] **N57 (TB). Chữ của public mà cổng `metric` không biết** (log run10: 143 câu không plan, 106 bị cổng đọc loại, nhiều nhất `metric=order_count` 23 câu). "đh" là viết tắt "đơn hàng" (14/23), "o đờ" là "order", §3 "giờ cao điểm" tính theo số đơn; "doanhthu" viết liền; tiền có đơn vị và số đứng trước ("từ 40tr trở lên", không nhận "k" đứng một mình vì "k" còn là "không"). Không câu train nào chứa các chữ này (đã kiểm), nên train không đổi. Phần lớn câu bị chặn ở `metric=revenue` là chặn **đúng** (LLM đọc "bnhiu đh", "bán bnhiu đĩa" thành doanh thu); giữ nguyên. run10 áp thêm: +18 câu trả lời (`outputs/replay/run10_s9`, 702 câu). Có test.
- [x] **N58 (CAO). Năm hai chữ số "th 6/25" bị bỏ, §2 đặt tháng vào năm nay: 14 câu trả lời sai năm** (run10, gồm 2/3 câu sai của dev_003 và 1/3 của dev_012 đo được ngày 06/11). `_year_grounded` chỉ nhận năm 4 chữ số, nên năm 2025 LLM ghi đúng bị coi là "câu không nêu" và bị bỏ; §2 ("tháng M không ghi năm là của năm nay") đưa tháng 6 về 2026. Cùng nguyên nhân: chuỗi tháng "th 12/25, th 1/26, th 2/26" bị cổng tháng chặn (5 câu).
  - Sửa: `stated_months` đọc "M/YY" (YY từ 20 đến 35, để "ngày 6/12" không thành 2012) và "M/YYYY"; năm câu viết hai chữ số là năm câu đã nêu; plan tháng không ghi năm mà câu viết "M/YY" của đúng tháng đó thì lấy năm ấy; cổng tháng và cổng chuỗi tháng nhận dạng này.
  - Train không có câu nào viết "M/YY" (kiểu định dạng riêng của public), nên train không đổi. run10 áp lại: 15 câu đổi giá trị, 6 câu mới, 708 câu trả lời (`outputs/replay/run10_s10`). Có test.
  - `tools/replay_run.py` ghi log từng câu (để dựng lượt chẩn đoán từ bản chạy lại).
- [x] **N59 (TB). Ba dạng JSON sai schema sửa được** (run10: 32 đầu ra sai schema). `repair.py`:
  - "đơn bị huỷ chiếm mấy %" thành [cancel_count, order_count] kiểu percent (6 câu): nghĩa duy nhất là `cancel_rate` (§1);
  - kiểu đáp án LLM ghi "list" / "date" cho plan một con số (9 câu): trường tuỳ chọn, bỏ đi để hình plan quyết định khi câu không hỏi nhiều số; cổng chỉ số vẫn kiểm (các plan đọc nhầm như "số viên nhập" thành tồn kho vẫn bị chặn);
  - chuỗi tháng ghi thành một tháng ("Dthu th7, th8, th9/2025 lần lượt", 8 câu): các tháng câu nêu theo thứ tự, liền nhau và tăng, năm của plan; cổng tháng kiểm năm như thường (không ghi năm thì vẫn chặn).
  - Phần còn lại là đọc sai (ca "store", "T10" ghi vào ca, `is_warranty` ở sổ điện thoại…), để chặn.
  - **Không đo được trên train**: 3000 plan train đã lưu đều hợp lệ, và cache cũ khoá theo prompt đã đổi. Vì vậy giữ ba phép thật hẹp, mỗi phép một nghĩa. run10 áp thêm: +13 câu (`outputs/replay/run10_s11`, 721 câu). Có test.
  - Rà ngày tháng có hệ thống sau N58: các dạng chỉ public có là "M/YY" (76 câu, N58), "M-YYYY" (40 câu: 23 câu đã trả lời đều đúng tháng, năm), "T8" (74). Trên 503 câu đã trả lời có ghi năm, năm câu viết đều nằm trong kỳ tính ra.
- [x] **N60 (TB). "T5/2025" là tháng, và "từ hồi X lên giá Y" không ghi ngày.**
  - "Trong T5/2025, trung bình một đơn…", "Hồi T3/2025 bị huỷ mấy đơn" đọc thành bộ lọc thứ Sáu / thứ Tư (6 plan bị cổng thứ chặn). Thứ trong tuần không bao giờ đi với năm: `drop_month_as_weekday` bỏ bộ lọc thứ khi câu có "T<số>/<năm>" và không có chữ chỉ thứ nào khác. +5 câu.
  - "Từ hồi Trà vải (L) lên giá 47.000đ, so 30 ngày kể từ ngày đổi giá…": train luôn ghi ngày, public thì không. LLM tự đoán một ngày (6 plan bị cổng ngày chặn). `anchor_by_price`: kỳ `days_from` có ngày câu không ghi, mà câu nêu đúng một giá mới ("lên (giá) N đ/đồng") → dùng giá làm mốc (`anchor_price`, như plan tay của train).
  - **`temporal` chưa từng làm `anchor_price`** (docstring cũ: "trừ days_from có anchor_price"). `price_rise_day`: §5 "lần tăng giá = ngày D giá mới cao hơn giá liền trước (theo bảng giá); tăng lên cùng một giá nhiều lần thì lấy lần đầu" → ngày đầu tiên bảng giá của mặt hàng (nối tên như [C3]) tăng lên đúng giá đó; thiếu bảng giá, không nối được tên, hay không có lần tăng nào thì bỏ trống. +6 câu.
  - Train không có plan nào dùng `anchor_price`, và chỉ 1 câu có dạng "T<số>". run10 áp thêm: 732 câu trả lời (`outputs/replay/run10_s13`). Có test.
- [x] **N61 (TB). Kênh "sàn TMĐT", "tại tiệm"** chưa có trong bảng đồng nghĩa (`assets/linking/synonyms.json`), dù rulebook §4 nhắc "đơn bán qua sàn TMĐT" và một sổ public ghi kênh "Sàn TMĐT", "Tại tiệm". Thêm mã `marketplace` ("sàn tmđt", "sàn thương mại điện tử") và "tại tiệm", "tại cửa hàng" cho `store`; không có "sàn" đứng một mình ("gạch lát sàn"). Nguồn ghi trong `_nguon`. Train 2681 / 0. +3 câu.
- [x] **N62 (CAO). Nợ chia theo tuổi nợ** ("nợ còn lại chia theo tuổi nợ 0–7, 8–15 và trên 15 ngày"). Train có 5 câu (đáp án list), public 6 câu; tất cả bỏ trống vì hàm nợ không hiểu bộ lọc tuổi nợ, và LLM ghi ba khoảng dạng chữ vào một bộ lọc.
  - `grounding.split_debt_ages`: mỗi khoảng một measure `debt_total`, ngưỡng số ("0–7" thành ≥ 0 và ≤ 7; "trên 15" thành > 15; "15+" sau "8–15" thành > 15), theo thứ tự câu hỏi.
  - `debt._owing`: lọc theo tuổi nợ = ngày X − ngày đặt (§4 "đơn đặt hôm nay có tuổi nợ 0 ngày"); dẫn luật `§4.tuoi_no`.
  - **Train: 3/5 câu thành đúng, 0 sai** (2681 → 2684, PA +0,895); 2 câu còn trống (một cửa hàng chưa map được nợ). Public +4. Có test tính tay.
- [x] **N63 (TB). Sổ bán ghi tên hàng, danh sách thuốc khoá theo mã SKU** (public: nhà thuốc có `DanhSachThuoc.xlsx` "Thuốc kê đơn"; 5 câu kê đơn / không kê đơn bỏ trống). `enrich`: khi mapping không có danh mục và dòng hàng mang **tên** hàng, thêm danh mục khoá theo tên, chỉ mang các cột thuốc (hoạt chất, kê đơn) tra qua mã SKU của chính danh mục; không thêm đơn vị cơ bản (số lượng giữ quy đổi cũ). Public: cờ kê đơn đủ 100% dòng, +12 câu. Có test.
  - **Train: danh mục khoá theo tên mở 35 câu đúng, 0 sai** (biz_121 88 → 106, biz_122 93 → 110; hai nhà thuốc train cũng ghi tên hàng trên sổ bán). Train 2684 → **2719 / 0, PA +0,906**.
- [x] **N64 (TB). Cửa hàng điện thoại (H2): loại hàng, dòng máy, hãng, số lượng.**
  - Loại hàng: sheet "Ghi tắt" cho tên đầy đủ và **Loại** (máy mới, máy cũ, phụ kiện). `transfer._kind_of_goods`: danh mục khoá theo tên đầy đủ (khoá dòng hàng đã mang sau N43) nhận cột `category`; chưa có danh mục thì dựng từ sheet đó. `expand_abbreviations` áp được cả lên mapping đã tra sẵn (chạy lại từ log).
  - Dòng máy, hãng: `build.phone_lines` theo đúng §6 ("phần tên đứng trước …GB; không có …GB thì cả tên"; hãng = chữ đầu, iPhone là Apple), chỉ bật khi ≥ 20% tên hàng có "…GB" (không cửa hàng train nào). Bộ lọc dòng hàng nhận `product_line`.
  - `nlu.product_as_attribute`: LLM ghi "máy cũ", "Xiaomi Redmi Note 14" vào bộ lọc **tên hàng**; tên không nối được mà trùng đúng (sau khi gấp chữ) một loại hàng / dòng máy / hãng / nhóm hàng duy nhất của cửa hàng → đổi sang bộ lọc đó.
  - **Sổ không ghi đơn vị** (chỉ "SL", không bảng quy đổi): mỗi mặt hàng bán theo một đơn vị, nên số lượng ghi là số lượng cơ bản (`derive_base_qty`); chữ đơn vị trong câu ("chiếc", "máy") không bắt khớp đơn vị cửa hàng (vì cửa hàng không có). Trước đó mọi câu "bán mấy chiếc" của hai sổ điện thoại đều trống.
  - Tên vùng miền thêm: ngao/nghêu, cá tràu/cá quả/cá lóc, trát → tô (một chiều: "tô phở"), găng tay/bao tay.
  - Train không đổi (2719 / 0). run10 áp thêm: +14 câu (`outputs/replay/run10_s18`, 765 câu). Có test (`test_phone_shop.py`).
- [x] **N65 (TB). Quy đổi đơn vị ghi bằng lời trong README.** Một sổ vật liệu public: "Hàng theo bó: Ống PVC … D32, … D50, … D90 bán theo bó, 1 bó = 10 cây", bảng danh mục không có dòng này → 1398 dòng không có số lượng cơ bản, mọi câu số lượng và bán chạy của cửa hàng bỏ trống. `build.readme_conversions`: đọc "- Tên hàng: 1 bao = 5 kg" (README train, cạnh bảng của chúng) và "A, B, C bán theo bó, 1 bó = 10 cây"; chỉ thêm dòng mà bảng quy đổi chưa có, cho tên hàng trùng đúng tên sổ ghi. Public +6 câu, không câu nào đổi giá trị. Có test.
- [x] **N66 (TB). Đơn giao từ N đợt; trạng thái "đang ship".**
  - "Đơn đặt tháng 6/2025, tới hôm nay có mấy đơn đã giao từ 2 đợt trở lên": `industry.orders_by_batches`, đơn theo ngày đặt, đợt giao tính đến hết hôm nay (§6 public "giao nhiều đợt: tính đến hết hôm nay; đợt đã chở vẫn tính dù đơn sau đó trả hàng"). Có test tính tay.
  - "đang ship", "chờ ship" là đơn đang giao (`STATUS_WORDS`): 3 đơn không rõ trạng thái làm mọi câu đếm đợt giao của các ngày đó bỏ trống. `transfer.refresh_status_words` cho bản chạy lại đọc lại từ trạng thái như một lượt mới.
- [x] **N67 (CAO). Cột "số lượng đã đổi ra đơn vị cơ bản" bị map làm số lượng của dòng** (một cửa hàng train chuyển từ mẫu, LLM chọn cột). Lộ ra khi N65 thêm quy đổi từ README: "bán bao nhiêu lon" thành 611 (đáp án 59), hai câu bán chạy lệch thứ tự, **3 câu sai trên train**. Trước đó lỗi bị che vì số lượng cơ bản trống nên câu bỏ trống. `enrich` sửa theo nghĩa README: cột README gọi "số lượng đã đổi ra đơn vị cơ bản" là `base_qty`; nếu `qty` đang lấy đúng cột ấy thì trả về cột README gọi "số lượng". Train: **2730 / 0, PA +0,910** (sau N65 + N66 + N67). Public không đổi giá trị câu nào. Có test.
  - Bài học: một bản sửa đúng có thể làm lộ lỗi cũ đang bị một câu bỏ trống che đi; lượt train đủ sau mỗi thay đổi là thứ bắt được.
- [x] **N68 (CAO). Sổ phụ của cửa hàng điện thoại** (`datamate/mapping/side_books.py`, gọi trong `build_canonical`; mỗi sổ nhận ra theo tên cột README nêu trong quy ước; một sổ đọc lỗi chỉ bỏ sổ đó, không làm hỏng cửa hàng):
  - mapping sai được sửa theo README: "**Khách trả** là số tiền khách trả cho cả đơn" là tổng tiền đơn (mapping chuyển từ mẫu lấy nhầm cột tiền của dòng); cột "hình thức thanh toán" toàn số tiền thì bỏ (`drop_amount_as_method`);
  - khách: ô "Khách" ghi tên kèm số điện thoại theo nhiều kiểu → khách là số điện thoại, tên là phần trước (§3);
  - sổ thu máy cũ → `orders.trade_in_amount` theo "Trừ vào (STT sổ bán)"; chỉ số `amount_due_total` (§6 "khách phải trả");
  - sổ bảo hành → `warranty_visits`, nối đơn qua IMEI; `warranty_count`, `warranty_rate` theo §6 điện thoại (lượt có ngày nhận trong kỳ / máy bán trong kỳ, không tính phụ kiện); xếp hạng dòng máy theo lượt bảo hành và theo số lượng;
  - sổ nợ, sổ góp → `payments` (trả lúc mua, trả nợ, góp), `installments` (kỳ k hạn ngày "Hạn góp" của tháng thứ k sau tháng mua), hình thức nợ / trả góp; đơn trả góp là đơn nợ (§6). Chỉ số mới `overdue_amount` ("kỳ có hạn trước ngày hỏi mà chưa góp đủ"), `overdue_installment_count` (số khách); nợ lọc được theo hình thức ("tiền góp chưa trả");
  - gợi ý prompt cho cửa hàng điện thoại (dòng trả góp chỉ khi câu có "góp": gợi ý chung làm LLM gắn bộ lọc trả góp vào câu khác).
  - Cổng mới cho các kiểu đọc sai gặp khi chạy: "hợp đồng trả góp còn bao nhiêu" thành tổng khách phải trả; "% đơn có thu máy cũ" thành tổng tiền; "máy bán tháng 8 đã mang lại bảo hành" thành lượt bảo hành của tháng; "trung bình mỗi đơn khách phải trả" thành giá trị đơn theo doanh thu; "khách X góp tới hạn mấy kỳ" và "tiền góp quá hạn" thành số khách; "khách phải trả, sau khi trừ…" thành hai số; "% tiền bán máy" không ghi mẫu số.
  - Hai cửa hàng điện thoại: 40 → 58 câu trả lời. Train không đổi. Có test.
- [x] **N69 (TB). Mẹ và bé (§6).**
  - Danh mục khoá theo tên có Hãng, "Số / Size" (`products.brand`, `stage`, `size`). Bộ lọc số sữa / size bỉm theo cột danh mục; hàng để trống thì không thuộc số, size nào. Hàng có trong danh mục mà ô Hãng trống là không có hãng.
  - "sữa bột số 2" ghi vào tên hàng → nhóm + số (`product_as_attribute`).
  - Cột chữ "Quy đổi: 1 thùng = 4 bịch" của danh mục (`catalogue_conversions`): 9124 dòng trước đó không có số lượng cơ bản.
  - Mẫu số tỉ trọng "% số bịch bỉm": nhóm "bỉm tã" được nhận khi câu viết "bỉm" (chỉ ở mẫu số).
  - Danh sách thành viên ("Ngày đăng ký thành viên") → `customers.registered_date`, khoá theo tên như sổ bán; `new_customer_count`.
  - dev_013: +6 câu, 2 câu đổi giá trị (size theo danh mục và quy đổi thùng ra bịch). Train 2730 / 0. Có test.
- [x] **N70 (TB). Tỉ trọng có mẫu số chép y tử số** ("dthu đơn bán tại quầy chiếm bn % tổng dthu của shop", share_of = doanh thu tại quầy): đáp án 100% bất kể dữ liệu, đáp án đúng 89,26%. `whole_not_part`: mẫu số là toàn cửa hàng.
- [x] **N71 (TB). "Dthu th 3/26 tăng trưởng bao nhiêu % so th 3/25"** đọc thành compare previous có ghi kỳ so sánh 3/2025: previous bỏ qua kỳ đã ghi. `written_last_year`: tháng của năm khác plan đã ghi là kỳ so sánh (kind period). +3 câu.
- **Kết quả nộp 07/11: 0,744** (run10_s27m, 802 câu: 773 đúng / 29 sai). Chẩn đoán theo hàm ở 8 cửa hàng cũ: so sánh 3 sai / 73, xếp hạng 4 / 70, đếm theo ngưỡng 6 / 58, một số có bộ lọc 4 / 72; 12 câu sai còn lại chưa khoanh vùng (`docs/CAN_XAC_MINH.md`). 198 câu bỏ trống: 93 có plan mà hàm không ra kết quả (log không ghi lý do, việc tiếp theo), 76 bị cổng đọc loại, 11 sai schema.
- [x] **N54 (TB). Log ghi lý do không có plan.** Run9 có 140 câu ở các cửa hàng đã map không có plan (14,7%; train 2,8%) mà log không nói vì sao. `parse_question(..., trace=)` ghi vào log mục `reading`: đầu ra thô của LLM, lỗi gọi, plan sai schema (sửa được hay không), cổng đọc loại vì đâu, plan của baseline khi hai bên đọc khác. Không đổi hành vi. `tools/replay_run.py` nhận thêm `trace` (thiếu thì mọi câu chạy lại sẽ lỗi) và `--enrich`.
- [x] **N37 (TB). Câu "ngoài phạm vi" không nêu thời gian thì trả không trả lời được (§7).**
  - Căn cứ (train): 8 câu LLM đọc là ngoài phạm vi. 7 câu không có mốc thời gian (tay nghề, thái độ, liều dùng thuốc) đều là unanswerable. Câu thứ 8 có "tháng 12/2025" ("nhân viên bán giỏi nhất tháng 12/2025") là câu xếp hạng bị đọc nhầm, vẫn bỏ trống.
  - Sửa:
    - `Signals.subjective`, tính khi hai dòng §7 không đổi và câu hỏi không có mốc thời gian (`verify._TIME`);
    - [E] trả `unanswerable`;
    - `collect_signals` nhận thêm `question` (pipeline, `check_plans`, `train_blanks`).
  - Có test. Public: run4 có 5 câu dừng ở "ngoài phạm vi".
- **README trong image** (`docker/README_IMAGE.md`, chép vào `/app/README.md`) và `tools/` trong image. Thể lệ đòi "source code (training and inference)" và README. README ghi cách chạy, định dạng log, các bước của phương pháp, tài sản dựng từ train và lệnh dựng lại, giấy phép của model và thư viện.

### Phiên 9 (07/11)
- [x] **N72 (TB). Log ghi lý do có plan mà không ra kết quả.** Lượt 0,744 có 93 câu bỏ trống ở bước này mà log chỉ ghi `result: null`.
  - `metrics.execute(..., trace=)` ghi vào log mục `no_result`: `no_function` (khoá intent / metric / entity chưa có hàm), `filter_not_taken` (bộ lọc hàm không khai báo), `function_none` (hàm chạy rồi trả None); pipeline thêm `period_unresolved` (kỳ không giải được). Không đổi hành vi: đọc lại ba nguồn của 0,744 ra đúng từng câu của `run10_s27m`.
  - `datamate/diagnose.py`: khi `diagnose.ENABLED` (chỉ `tools/replay_run.py` bật), chạy lại hàm dưới `sys.settrace` và ghi chuỗi dòng `return None` (hàm ngoài ⟵ hàm con đã trả None ⟵ …, tối đa 6 tầng; comprehension và generator trong suốt). `predict` không bật.
  - `tools/run_stats.py` tách bước 4 theo lý do và theo dòng dừng.
  - Kết quả trên 93 câu:
    - 42 bộ lọc không áp được: 33 giá trị không nối được, phần lớn chặn đúng (nhóm hàng cửa hàng không ghi, LLM lặp một bộ lọc 10 lần, mỗi kiểu 1–2 câu); 9 lọc theo ca ở cửa hàng không có giờ (→ N73);
    - 19 chưa có hàm cho khoá (giá trị tồn kho, hạn dùng gần nhất, hàng hết cuối ngày…), 5 hàm không nhận bộ lọc, 1 kỳ không giải được;
    - 6 xếp hạng tăng dần hoặc kèm giá trị (hàm chặn có chủ ý);
    - 8 nợ, 5 nhập hàng: phần lớn ở hai cửa hàng map theo mẫu một file (biz_101), nên sổ nhập và danh mục không được map; một cửa hàng ghi nợ trong ô Note, chỉ có tình trạng cuối dữ liệu, không có ngày trả;
    - 7 lẻ (giá trị đơn trung bình hay số đơn huỷ lọc theo mặt hàng…).
  - Hướng sau: `sibling_files` xếp mẫu theo tỉ lệ bảng của **mẫu** ghép được, nên mẫu một file thắng mẫu ghép được cả sổ nhập. Xếp theo số file của **cửa hàng** được dùng thì hợp hơn, nhưng đổi mapping của hai cửa hàng đang trả lời tốt và cần LLM: chỉ làm khi có thời gian đo lại cả train.
- [x] **N73 (TB). Giờ đặt đơn từ cột README gọi là "thời điểm đặt đơn".** Hai cửa hàng public map theo mẫu một file đọc ngày đơn từ "Ngày giao dịch / Ngày xuất: ngày bán" bên cạnh "Giờ bán: thời điểm đặt đơn (ngày giờ)": `has_time` = False, 9 câu lọc theo ca (§2) bỏ trống. `from_readme.with_order_hour` (gọi trong `enrich`) đổi `order_time` sang cột đó khi mọi đơn giữ nguyên ngày, cột đọc được ngày giờ trên mọi đơn và có giờ khác 0h. Public: đúng 9 câu ca trống → trả lời, không câu nào khác đổi. Có test.
- [x] **N74 (TB). Lô, hạn dùng, hết hàng cuối ngày (§5, §6 Nhà thuốc).** N72 cho thấy 9 câu public "chưa có hàm" ở nhà thuốc dev_006 (đã map đủ `lots`, `lot_sales`): `nearest_expiry`, `stock_value` theo khoảng hạn dùng, `list_items expiring_within`, `out_of_stock_end_of_day`.
  - `datamate/metrics/lots.py`. Tồn còn lại của một lô tại hết ngày D = nhập (phiếu ngày ≤ D) − bán của đơn đặt ≤ D (đơn huỷ không lấy) + hàng trả theo **ngày trả** ≤ D. Kiểm trước khi viết trên nhà thuốc train: tổng các lô = thẻ kho ở **80/80** mặt hàng tại 3 ngày (tính hàng trả theo ngày đặt: 78/80). Lô không rõ ngày nhập hoặc ngày trả chỉ tính ở cuối dữ liệu.
  - Khoảng hạn dùng [D, D + N] lấy từ `n` của danh sách, bộ lọc `expiry_within_days`, hoặc kỳ câu hỏi ghi (range, next_n_days). Hai nguồn khác nhau (public: range 120 ngày bên bộ lọc 365) thì không có số. Bộ lọc "gte N" chỉ nhận khi kỳ ghi đúng khoảng đó (kho plan train có "gte 90" bên range D..D + 90). `stock_value` không có khoảng hạn dùng (§5 "giá trị hàng tồn kho" theo giá vốn danh mục) chưa làm.
  - Hết hàng cuối ngày: hàng có bản ghi tồn kho (hàng mua về để bán; món pha chế không có), tồn hết ngày bằng 0 theo `stock_base_qty`.
  - Đáp án train bằng mapping tay: 4/4 lô gần hết hạn, tiền vốn 7 899 400, danh sách 120 ngày đúng thứ tự, số lô 5, hết hàng 1. `eval_cached`: **2731 / 0 / 269** (+1: biz_120; biz_123, biz_124 bị bỏ khỏi bộ mẫu nên map tự động không có bảng lô). Public: dev_006 +8 câu, không câu nào khác đổi. Có test (`tests/test_lots.py`).
- [x] **N75 (Cao). run11: lượt LLM đủ 1000 câu bằng code cuối, chạy từ bản chép code như trong image.**
  - `outputs/snap_run11/` chỉ có `datamate/`, `assets/`, `configs/` (đúng ba thư mục Dockerfile chép). Không LLM: 1000 câu, 0 lỗi, 211 giây. Có LLM (`outputs/public_run11`): 1000 câu, 0 lỗi, 0 hết giờ, **2321 giây** (38,7 phút) trên laptop.
  - So với `run10_s32m` (ghép từ đọc lại ba nguồn): **992/1000 giống từng câu**. 8 câu khác đều do đầu ra thô của LLM khác (sinh tham lam, seed cố định; nguyên nhân là prompt đổi kể từ lượt gốc hoặc llama-server dùng lại KV cache): run11 đọc đúng hơn 4 câu ("bán mấy đĩa" theo đơn vị, "từ 10 củ" là doanh thu, "mấy khách quá hạn góp", "dthu wan mik" không phải kênh), lượt gốc đúng hơn 4. Docker sẽ dao động cỡ này.
  - Hai cách đọc sai của run11 sửa bằng quy tắc chung:
    - `grounding.rate_as_value`: `share` của một chỉ số vốn là tỉ lệ (`cancel_rate`, `warranty_rate`), không có `share_of` → `value` ("đơn huỷ chiếm bao nhiêu % toàn bộ đơn" là tỉ lệ huỷ §1);
    - `repair._fix_series_months`: chuỗi tháng vắt qua năm ("th 12/25, th 1/26, th 2/26") bị ghi thành tháng đầu → các tháng câu ghi, khi liên tiếp và tháng đầu khớp plan.
  - `run11_s33` (run11 đọc lại bằng code này): +2 câu, không câu nào khác đổi; so với lượt 0,744: 21 câu mới, 2 câu thành trống. Train 2731 / 0, CACHE MISSES 0. Có test.

- [x] **N76 (TB). Ba luật viết lại cho các cặp nhầm của LLM** (lời khuyên 07/11: LLM nhầm giữa vài case; sửa theo cặp, đo hai mặt). Lập từ sheet câu trống 07/11.
  - `grounding.unit_filter_as_unit`: bộ lọc `unit` ("quán bán dc bnhiu **đĩa**", "hqua bán đc mấy **gói**") → đơn vị của chỉ số, chỉ số là số lượng; chỉ khi câu không có chữ về tiền ("doanh thu … bao nhiêu **hỉ**": trợ từ đọc thành đơn vị, giữ nguyên cho cổng).
  - `grounding.orders_not_money`: doanh thu mà câu đếm "đh / đơn" và không có chữ về tiền → số đơn ("30 ngày gần nhất được bnhiu đh").
  - `nlu.unit_or_all_as_product` (bước nối tên): bộ lọc mặt hàng là một đơn vị của shop ("bao nhiêu ly": product = ly) → đơn vị; "tất cả các món", "mọi mặt hàng" → bỏ bộ lọc, **chỉ khi plan có một chỉ số** (lần đo đầu: "mấy ly size M, cộng tất cả các món" thành danh sách hai số, 2 câu train sai).
  - Đo hai mặt: train **2738 / 0 / 262** (+7, PA +0,913, CACHE MISSES 0). Public (`run11_s34` so với `run11_s33`): 7 câu trống → trả lời, 1 câu đổi giá trị ("Quý 3/2025 quán bán được bnhiu đh" trước trả doanh thu, nhiều khả năng là một câu sai). Có test.

- [x] **N77 (TB). Bảng phụ mượn từ README khi mapping chuyển từ mẫu thiếu** (`from_readme.with_side_tables`, gọi trong `enrich`). Sheet câu trống 07/11: 67 câu train, 10 câu public dừng vì shop thiếu bảng (sổ nhập, tồn, giao hàng, thanh toán): mẫu được chọn không có bảng đó.
  - Mượn bảng (purchases, inventory, deliveries, payments) của mapping dựng từ README khi khoá khớp, kiểm bằng cách **dựng chung** với đơn và dòng hàng như lúc chạy (cách viết của một tên được gộp xuyên bảng): ≥ 80% mặt hàng / ≥ 95% đơn của bảng mượn có trong mapping.
  - Khoá mã ↔ tên khác nhau (sổ nhập theo "SP0001", dòng bán theo tên): dịch mã sang tên qua file bán có cả hai cột (`lookup`), chỉ khi ≥ 98% khớp; sai khoá sẽ đặt tiền nhập lên nhầm mặt hàng. Dòng bán chia nhiều file thì chưa dịch (dev_008 chưa được).
  - Bảng mượn không được làm hỏng phép kiểm nào (lần đo đầu: sổ tồn có 1/61 ô trống làm hỏng "cột bắt buộc đủ giá trị", **cả 50 câu của shop thành trống**; giờ bảng đó bị loại riêng).
  - Đo: train **2747 / 0 / 253** (+9, PA +0,916, CACHE MISSES 0). Public (`run11_s35` so với `s34`): +2 câu tiền nhập, không câu nào mất. Có test (`tests/test_side_tables.py`).

- [x] **N78 (TB). Gọi lại LLM kèm lỗi schema; cổng "tháng nào … nhất".**
  - `nlu.llm_plan`: đầu ra sai schema mà N32 không sửa được → gọi lại một lần, đưa cho LLM đầu ra cũ và thông báo lỗi (`RETRY_ASK`); plan mới qua đủ các cổng. Log ghi `retry`, `llm_raw_retry`; `tools/replay_run.py` trả lại đầu ra lần gọi lại.
  - Đo có server: public 17 câu hỏng ở run11 → 7 plan cứu được, 1 câu mới đúng ý ("tuần này bán mấy đơn", bỏ bộ lọc ca "store"), nhưng không ổn định giữa các lượt (lượt sau LLM viết plan hợp lệ khác, bị cổng chặn). Train 84 câu không có plan: gọi lại cứu 2 plan, cả hai vẫn bị chặn đúng; **0 câu sai**. Giữ vì rẻ (chỉ ~1,5% câu gọi thêm) và an toàn.
  - Lần gọi lại lộ một lỗ hổng cổng: "doanh thu cao nhất rơi vào **tháng nào** trong 3 tháng" đọc thành chuỗi 3 số. Cổng mới `asks=which_time` (câu hỏi "tháng / ngày / tuần / quý … nào" kèm "nhất" mà plan là chuỗi hay một số). Train 2747 / 0 không đổi; public không câu nào đổi.
  - **Phát hiện:** kho plan train `outputs/bank/llm_plans.jsonl` dựng bằng code / prompt cũ. Với code hiện tại, 44 trong 84 câu train không có plan nay được LLM đọc đúng ngay (0 sai), nên `eval_cached` báo thấp điểm train thật (khoảng 2790 / 0). Việc sau: dựng lại kho bằng server (`datamate.eval.build_bank`), cân nhắc thêm plan đã kiểm vào kho ví dụ (đổi prompt, phải đo lại public).

- [x] **N79 (Cao). Gọi lại khi cổng căn cứ chặn plan — BẬT từ 08/11 (`nlu.GROUND_RETRY = True`), sau khi đo đủ hai mặt (cuối mục).**
  - `nlu.llm_plan`: plan bị cổng căn cứ chặn → gọi lại một lần, cho LLM xem phần bị chặn (`RETRY_GROUND`); plan mới qua đủ cổng. Có test (bật cờ trong test).
  - Đo public (76 câu bị cổng chặn ở run11, có server, 08/11): **34 câu thành trả lời** (27 nhờ gọi lại; 5 trong đó đã có trong s35 nhờ N76). Đọc từng plan: khoảng 25 đúng ý, **8 nhiều khả năng sai** vì LLM "sửa" bằng cách bỏ luôn phần bị chặn mà phần đó là ý chính: "mấy **lon**" mất đơn vị (2), "% **tiền bán máy**" / "% **số bịch bỉm**" mất mẫu số (2), "đơn **quá 7 ngày**" mất tuổi nợ, "**bảng** hoa hồng **mọi thợ**" thành một tên, "góp tới hạn **mấy kỳ**" thành tiền, "**5-2025** khách nữ" thành top 5. Lời ròng ước +0,015 nhưng sai ~25% số câu mở: trái nguyên tắc 0 sai, rủi ro private.
  - Việc tiếp: **cổng "plan bỏ sót"** (câu có ý mà plan thiếu): đếm "mấy <đơn vị>" mà không có unit; "% so với / của X" mà share_of là cả shop; "quá N ngày" mà không có debt_age; "bảng … mọi / từng" mà rank k=1 không giá trị; "mấy kỳ" mà chỉ số là tiền; rank khi câu không có từ xếp hạng (nhất, top, xếp). Các cổng này bảo vệ cả plan lần đầu. Rồi đo train như lượt thật: `python tools/prod_train.py 2 outputs/prod_train_n79.jsonl --ground-retry` (cần server, ~1 giờ khi server rảnh; so với chạy không cờ) — bật N79 chỉ khi train 0 sai. Log 34 câu: `outputs/gate_public/logs`.
  - Công cụ mới `tools/prod_train.py`: chấm train **như lượt chạy thật** (thẻ dữ liệu, kho ví dụ trừ mọi ví dụ cùng shop, cổng câu anh em) — `eval_cached` đọc theo cách của `build_bank` (thẻ trống, ví dụ tay) nên không đo được thay đổi ở bước đọc câu.
  - **Phiên 10 (08/11): cổng "plan bỏ sót" đã làm** (`grounding.ungrounded_measures`, chạy với cả plan lần đầu), mỗi cổng ứng với một trong 8 câu nghi sai:
    - `asks=debt_age`: chỉ số nợ, câu có "quá / trên / hơn N ngày", plan không có `debt_age_days`;
    - `asks=periods`: câu hỏi "mấy / bao nhiêu kỳ" (chưa chỉ số nào đếm kỳ góp; trước chỉ chặn khi chỉ số là `overdue_installment_count`);
    - `share_of=phones`: "% tiền bán máy" mà mẫu số là cả shop, nay chặn cả khi `share_of` có mà không có bộ lọc;
    - `intent=rank`: plan xếp hạng mà câu không có từ xếp hạng (nhất / nhứt / nhut / nhta, top, xếp, cao điểm, đứng đầu, best, hot). Cả 288 câu xếp hạng đã kiểm của train đều có một từ như vậy. Cổng này chặn thêm một câu run11 đang trả lời: "có mấy mặt hàng đang cháy hàng" đọc thành xếp hạng, ra một tên thuốc;
    - `asks=every`: rank k = 1 không kèm giá trị, câu có "mọi / từng / tất cả + đối tượng" và không có "nhất / top" ("bảng hoa hồng của mọi thợ, xếp từ cao xuống thấp");
    - "mấy lon" mất đơn vị: thay vì chặn, gán thẳng đơn vị (N80), vì §3 nói rõ cách tính.
  - **Ba câu "% số bịch bỉm" bị chặn oan ở plan đầu.** Plan đầu của LLM đúng ý (tử số "bỉm tã + size XL / hãng", mẫu số "bỉm tã", đúng public rulebook §6 Mẹ và bé "phần trăm của một size hay một hãng chia cho tổng số bịch mọi hàng bỉm tã"). Nhưng `product_group=bỉm tã` ở **tử số** chỉ khớp 1/2 từ ("bỉm"), dưới ngưỡng 0,6; ngoại lệ cũ chỉ áp cho mẫu số. Nay bộ lọc của tử số lặp đúng bộ lọc nhóm của mẫu số thì có căn cứ như mẫu số. Public: 3 câu trống → trả lời (giá trị trùng với lượt gọi lại N79 trước đó).
  - Đo: 5319 plan train (kho đã kiểm + kho plan 8B) qua cổng trước / sau: **không plan nào đổi trạng thái chặn** (lần đầu cổng rank chặn oan "5 best seller … là những mặt hàng nào": thêm "best", "hot"). `eval_cached` 2747 / 0 / 253 không đổi. Có test (`tests/test_n79_gates.py`).
  - `tools/replay_run.py --ground-retry --llm-url …`: đọc lại một lượt với N79 bật; lần gọi lại lượt gốc không ghi thì gọi server và ghi vào log (`llm_raw_retry`), nên lượt đọc lại sau không cần server.
  - **Đo public với cổng mới** (run11 đọc lại, lần gọi lại thật qua server, 08/11; `outputs/replay/run11_s38r` giữ log các lần gọi lại): N79 mở thêm 22 câu so với lượt tắt (s39). Đọc từng plan: 20 đúng ý (lần gọi lại chỉ bỏ bộ lọc LLM tự thêm: sản phẩm lạ, kênh "tại tiệm", ca, bảo hành, mã nhân viên; hoặc sửa loại câu), 2 sai ("mấy lon" ở shop không ghi đơn vị, nay chặn bằng `unit_not_recorded`, N80). Cả 8 câu nghi sai của lượt 08/11 trước đều bị cổng chặn hoặc được plan đầu đọc đúng.
  - **Đo train như lượt thật** (`tools/prod_train.py 2`, 1500 câu, code cuối phiên 10): N79 tắt **1391 / 0 / 109**; N79 bật **1407 / 0 / 93**. 26 câu được gọi lại: 16 thành đúng, 10 vẫn trống, **0 sai**. (Đầu phiên, code cũ: 1390 / 0 / 110.)   - **Public (nộp 08/11):** s41 (tắt) 0,784, s41r (bật) **0,804**: +0,020 = cả 20 câu mở thêm đều đúng. **Đã bật** `GROUND_RETRY = True`. `tools/prod_train.py` và `tools/replay_run.py` theo mặc định mới (`--no-ground-retry` để tắt). Lượt chạy gọi LLM thêm cho ~7% số câu.

### Phiên 10 (08/11)
- [x] **N80 (TB). Ba cặp nhầm nữa của LLM, sửa bằng luật viết lại** (theo cách N76; mỗi luật dựa trên một dòng rulebook).
  - `nlu.unit_from_question` (bước nối tên, cần danh sách đơn vị của shop): câu đếm "mấy / bao nhiêu / nhiêu <đơn vị của shop>" mà chỉ số số lượng chưa có đơn vị → đơn vị đó (§3 "bán được bao nhiêu <đơn vị>: chỉ các mặt hàng có đơn vị cơ bản là <đơn vị>"; "hôm qua bán được mấy lon" ở quán bia đọc không đơn vị thì cộng cả hàng tính theo chai, thùng). Chỉ khi câu nêu đúng một đơn vị ("bao nhiêu phần trăm" không tính); không áp cho tỉ trọng (mẫu số vẫn đếm mọi hàng), xếp hạng, ngưỡng, danh sách (§3 xếp chung các đơn vị).
  - `grounding.unpaid_as_debt`: `amount_due_total` (khách phải trả) mà câu hỏi "chưa góp / chưa trả / còn nợ" và không có "phải trả" → `debt_total`, giữ bộ lọc (đơn trả góp, một khách). Public rulebook §6 Điện thoại: "phần góp chưa trả là tiền khách còn nợ". Trước đây cổng chặn, cả lần gọi lại LLM vẫn viết `amount_due_total`.
  - `grounding.one_name_no_values`: rank k = 1 kèm giá trị (bảng một dòng) mà câu hỏi "<đối tượng> nào … nhất" không hỏi con số nào (không "bao nhiêu", "mấy", "bảng", "từng", "mỗi", "kèm") → chỉ tên. Public run11: 6 câu dừng ở `sales.rank` vì hàm không nhận bảng cho đối tượng khác nhân viên. Kho đã kiểm của train không có bảng một dòng nào (mọi `with_values` đều k 3 hoặc 5 kèm "từng người"). Plan có k rỗng (mọi đối tượng) kèm giá trị cũng thành k = 1, trừ khi câu có "các / những / tất cả / liệt kê". Bẫy bỏ dấu: "máy" và "mấy", "mới" và "mỗi", "bằng" và "bảng" đều cùng một chữ khi bỏ dấu ("trong nhóm máy mới, mặt hàng nào bán được nhiều máy nhất" bị coi là hỏi "mấy", "mỗi"); các chữ đó viết có dấu thì bỏ ra trước khi tìm từ hỏi số.
  - `nlu.unit_not_recorded` (cổng, qua `omitted`): câu đếm theo một đơn vị cụ thể (lon, chai, ly, thùng, gói, hộp, vỉ, viên…) mà shop không ghi đơn vị đó, kể cả shop không ghi đơn vị nào → không có số. "Chiếc / cái / máy / món" không tính: shop điện thoại không ghi đơn vị vẫn đếm "mấy chiếc". Public: chặn 2 câu "mấy lon" N79 mở ra (shop chỉ có file bán, không có cột đơn vị: hàm cộng mọi món).
  - Train: hai luật viết lại sau không đổi plan train nào (0 / 5319: train không có shop điện thoại, không có bảng một dòng); luật đơn vị không đổi câu nào của `eval_cached`. Có test.
  - **Lỗi bắt được khi đo public:** bản đầu của `one_name_no_values` dùng `model_copy`, nên plan giữ `answer_type="table"` (suy ra từ `with_values`) mà không còn `with_values`. `ResolvedPlan` báo mâu thuẫn, 5 câu ném ngoại lệ. `compare_runs` không thấy vì câu lỗi trả trống, mà trước đó các câu này cũng trống. Đã sửa: luật nào đổi phần quyết định `answer_type` thì dựng lại plan bằng `model_validate`, bỏ `answer_type` cho suy lại (như `split_debt_ages`); test kiểm `ResolvedPlan` dựng được. `compare_runs` nay in số câu có `error` trong log.
- [x] **N81 (TB). Giá trị hàng tồn kho theo giá vốn danh mục** (§5 "tồn hết hôm nay của từng mặt hàng nhân giá vốn một đơn vị cơ bản ghi trong danh mục hàng; chỉ tính hàng còn tồn"). `lots.stock_value_by_catalogue`: `stock_value` không bộ lọc, kỳ chỉ nêu ngày đọc tồn (hôm nay, "đến hết ngày X") → Σ `stock_base_qty` × `products.unit_cost` của hàng tồn > 0; không có số khi một hàng còn tồn thiếu giá vốn, hoặc tồn đọc không được / âm. Kiểm trước khi viết: biz_109 (mapping chuyển giao) 70 371 249 và biz_124 (mapping tay) 134 198 773, **đúng từng đồng** cả hai. Có test (`tests/test_lots.py`).
  - Lần đo đầu train không đổi: hàm ra đúng số nhưng cổng `rules_unchanged` chặn, vì [R] chỉ kiểm các dòng rulebook mà registry khai báo (`pipeline.rule_ids`), và §5 "giá trị hàng tồn kho" chưa có trong registry của `stock_value`. Đã khai báo; có test. Bài học: hàm mới viện dẫn dòng rulebook mới thì phải khai báo ở `metric(..., rules=)`, và phải đo qua cả pipeline chứ không chỉ `metrics.execute`.
  - Đo (code cuối phiên 10, gồm N79 cổng, N80, N81): `eval_cached` **2748 / 0 / 252** (+1: câu giá trị tồn kho của shop map chuyển giao), PA +0,916, CACHE MISSES 0. Public: 1 câu nhà thuốc ra số khi N79 bật (lần gọi lại bỏ bộ lọc "product = inventory").
  - Còn thiếu (public, 1 câu): một shop map từ mẫu một file có `danh_muc_hang.csv` (Giá vốn, Tồn cuối) nhưng mapping không có bảng danh mục lẫn tồn kho. Mapping dựng từ README chỉ đọc file đó thành `inventory` (không có `products.unit_cost`). Bảng tồn mượn theo N77 (dịch mã → tên qua file bán) bị loại vì danh mục có cả hàng chưa bán, nên dưới 98% khớp. Muốn có số phải (1) cho README dựng `products` từ danh mục, (2) cho phép mã danh mục không có trong file bán khi dịch khoá. Rủi ro: thêm `products` đổi đơn vị cơ bản và nhóm hàng của mọi câu của shop, nên phải đo lại đủ train và public.
- [x] **N82 (thấp). Công cụ.** `tools/run_stats.py` đổ khi gặp câu unanswerable (trả lời mà không có `result`), và đếm lý do bước 4 (N72) mà không in ra: đã sửa, nay in "bước 4 theo lý do" và "dòng dừng". `tools/compare_runs.py` in số câu lỗi khi chạy (lỗi trả trống nên trước đây lẫn vào "giống").

### Phiên 10, đêm 08/11 (không nộp được: làm từ câu trống của bản 0,804)
Đọc 47 câu public bị cổng chặn cả hai lần và 73 câu có plan mà hàm không ra số (log `run11_s43`), gom thành cụm; mỗi cụm sửa bằng một quy tắc chung có căn cứ (rulebook, đáp án train), đo hai mặt trước khi giữ.
- [x] **N83 (TB). Câu hỏi phẩm chất người / nhà cung cấp → unanswerable (§7).** `grounding.subjective_quality`: câu nói tới khách / nhân viên / thợ / nhà cung cấp mà không có chữ nào của một số đo (tiền, đơn, bán, mua, nợ, nhập, lượt…) và không có thuật ngữ rulebook (trung thành, sộp, hay đổi ý, chăm chỉ, đắt khách, bán chạy, nhà cung cấp chính…). Train: bắt đúng 5 / 3000 câu, **cả 5 đều unanswerable** ("nhân viên nào có tay nghề cao nhất tiệm", "có lễ phép, chu đáo với khách hông"…). Chỉ áp khi không có plan nào qua cổng, hoặc LLM cũng đọc là ngoài phạm vi; khi đó trả unanswerable kể cả câu có mốc thời gian (N37 vẫn giữ cho các câu khác). Public: 5 câu ("khách thân thiện / khó tính / trung thực nhất", "nhà cung cấp uy tín / đáng tin cậy"). Một câu "thợ nhiệt tình nhất" LLM đọc thành "chăm chỉ" (qua cổng) thì để nguyên.
- [x] **N84 (TB). Gõ nhiễu trên chữ khoá của cổng số đo** (`grounding.denoised`): thêm "g" sau "n" ("đơng", "tiềng", "báng"), "c" gõ thành "t" ("đượt"), dính chữ ("nhiềuđơn"). Chỉ đọc trên câu còn dấu ("đồng", "tiếng", "bảng" không đụng). Public: 3 câu mở.
- [x] **N85 (TB). Plan sai hình cho câu hỏi, viết lại theo rulebook:** "có mấy mặt hàng ế" đọc thành danh sách → đếm (`count_not_list`; train +2); tỉ trọng không có chữ phần trăm → một số (`share_as_value`); "tháng nào … cao nhất" đọc thành chuỗi → xếp hạng tháng, k = 1 (`which_time_as_rank`; test N78 sửa theo); "nhà cung cấp chính" → xếp theo số phiếu (§5), "khách sộp nhất" → giá trị đơn trung bình, khách từ 3 đơn (§3) (`rulebook_rank_terms`); "thứ 3" ghi thành thứ tư → thứ câu hỏi nêu (`weekday_as_stated`); "tiền chậm góp / quá hạn" ghi thành khách phải trả → `overdue_amount`; tỉ trọng có mẫu số ghi thành số đo thứ hai → `share_of` (`whole_as_share_of`).
- [x] **N86 (TB). Nhập trừ bán (§5).** `stock.purchase_minus_sales`: phiếu nhập trong kỳ (bỏ phiếu huỷ), từng dòng quy về đơn vị cơ bản theo đơn vị của dòng, trừ số lượng cơ bản của đơn tính vào doanh thu (§1: bỏ cả đơn huỷ lẫn đơn trả), chia hệ số của đơn vị câu hỏi. Kiểm trước khi viết, ba câu train có mapping tay: **10, −28, 41, đúng cả ba**; tính cả đơn trả thì ra −38 và 39. `grounding.in_minus_out` đưa câu "nhập trừ bán / chênh nhập và bán" (LLM đọc thành tồn kho, tiền nhập hay hai số) về chỉ số này, lấy đơn vị theo plan hoặc theo chữ sau "bao nhiêu / tổng / số". Public: 4 câu + 2 câu đã có plan đúng nhưng chưa có hàm.
- [x] **N87 (TB). "Quá N ngày" ghi thành giá trị chữ** (`debt_age_from_question`): `debt_age_days` "gt" mà giá trị là chữ → N câu hỏi nêu, phép "lớn hơn". Public 5 câu (4 ở shop có sổ nợ), train 1.
- [x] **N88 (TB). Bộ lọc rác** (`nlu.drop_generic_filters`, bước nối tên): giá trị là chữ chung (quán / wán / shop / sốp / tiệm / khách / dthu / tiền / z…) hoặc một tháng ("T8") **và** không nối được vào giá trị thật nào của shop → bỏ bộ lọc. Không bỏ "đt" (có thể là kênh điện thoại). Public ~9 câu.
- [x] **N89 (TB). Giới tính, địa chỉ khách ở shop không ghi → unanswerable (§7).** `grounding.customer_trait_not_recorded` + `pipeline.answer_question`: câu hỏi theo khách nữ / nam / giới tính, hoặc khách ở đường X / địa chỉ, ở shop mà README không có cột đó (hoặc ghi "cột trống, không có dữ liệu"). Train: bắt đúng **10 / 3000 câu, cả 10 unanswerable**, không câu nào thừa. Shop có cột địa chỉ (dev_007, dev_008, 5 shop train) thì để nguyên (train không có câu nào để đối chiếu). "Khách năm 2025" không phải giới tính: phần giới tính đọc trên câu còn dấu. Public: 7 câu.
- [x] **N90 (Cao). Hệ số quy đổi bị map từ cột giá** (`from_readme.factor_not_price`, trong `enrich`). Lộ ra khi đo N86: hai câu "nhập trừ bán" của một quán ra 5 039 879 và 2 537 912 "cái". Sheet quy đổi có "Giá bán theo đơn vị quy đổi" (210 000) bên cạnh "Bằng" (6); mapping (ghép theo vai trò, LLM chọn cột) lấy cột giá làm hệ số, nên **mọi dòng bán theo hộp của hai mặt hàng đó tính thành 210 000 cái**: mọi câu số lượng / bán chạy có dính hai mặt hàng này đều sai. Có thể đây là 2 câu sai của nhóm dev_003 + dev_009 đo được 08/11. Sửa: hệ số là số đơn vị cơ bản (≤ 1000), không phải tiền; khi mọi hệ số được map đều > 1000 và trong sheet có đúng một cột khác toàn số nguyên 2–1000 thì dùng cột đó. Có test.
- [x] **N91 (thấp). Tháng trước năm đọc thành top k** (`grounding.k_not_the_month`): "5-2026 khách nào mua nhiều đơn nhất" xếp hạng k = 5; k chỉ có ở tháng của "M-YYYY" / "M/YYYY" và câu không ghi số đối tượng → k = 1. Train không đổi plan nào. (Câu public này sau đó vẫn có thể bị cổng hoà hạng chặn.)
- [x] **N92 (thấp). Bộ lọc rác không tính là bất đồng với baseline** (`nlu._without_generic`): "Th9/2025 tiem tong doanh thu" LLM đọc product = tiem, baseline đọc doanh thu cả shop: hai cách đọc chỉ khác ở bộ lọc rác (N88 bỏ ở bước nối tên) thì không bỏ trống. Hai câu bất đồng khác (LLM đọc "hôm nay" thành tháng này, "T1/2026" thành quý 1) vẫn bỏ trống: LLM sai thật.
- [x] **N93 (thấp). Nhóm hàng ghi nhầm trường** (`nlu.attribute_in_its_field`, bước nối tên): "Nhóm gỏi" ghi là category mà shop giữ ở product_group; "nhóm máy mới / máy cũ / phụ kiện" ghi là product_group mà shop giữ ở category → đổi trường, chỉ khi giá trị không nối được ở trường đã ghi và khớp đúng một giá trị của đúng một trường khác. Public: 4 câu.
- [x] **N94 (TB). Sổ nhập không dịch được khoá mặt hàng vẫn cho tổng của kỳ** (`from_readme.with_side_tables`): khi khoá mặt hàng của sổ nhập không khớp tên trên dòng bán (dòng bán chia 2 file nên N77 không dịch được), mượn sổ nhập với khoá giữ chỗ `UNKEYED`. Tiền nhập, số phiếu, nhà cung cấp của một kỳ dùng được (công thức đã kiểm 20/20 train); mọi câu theo mặt hàng không tìm thấy phiếu nào nên trống. Chỉ khi mapping không có tồn kho / lô (các hàm đó đọc phiếu nhập theo mặt hàng). `purchase_minus_sales` thêm chốt: mặt hàng chưa từng có trong sổ nhập thì không có số (khoá lệch không được đọc thành "nhập 0"). Test N77 sửa theo.
- **Lượt public chạy thật đủ 1000 câu với LLM bằng code cuối** (`outputs/public_run12`, chạy từ bản chép `outputs/snap_run12` chỉ gồm `datamate/`, `assets/`, `configs/` như image): 0 lỗi, 0 hết giờ, 2482 giây (41 phút); giống bản đọc lại s50 ở **993 / 1000** câu. 7 câu khác do LLM sinh khác lượt trước (dao động đã biết, ~1%), trong đó có một câu sai thật → N95.
- [x] **N95 (TB). Kỳ tương đối không phải tháng câu hỏi ghi** (`grounding.ungrounded_dates`): "8/26 tiền bán ca chiều" (hôm nay 19/09/2026) lượt chạy thật đọc thành "tháng này" (tháng 9), lượt trước đọc đúng tháng 8. Câu ghi rõ tháng (M/YY, M/YYYY) mà plan dùng this_month / last_month rơi vào tháng khác → chặn (N79 gọi lại). Train: không plan nào bị chặn thêm.
- **Kết quả nộp s51: 0,854** (08/11 03:01) = 0,804 + 49 câu mới đều đúng + 1 câu sai được bỏ. Mọi luật N83–N95 đúng trên public.

### Phiên 10, sáng 08/11: ổn định lượt chạy thật, Docker guideline 2026
- [x] **Lượt chạy thật mất 4 câu so với bản đọc lại** (LLM sinh khác lần trước): xử lý 2 câu bằng quy tắc chung, để lại 2 câu cách viết lẻ ("vâu chơ" = voucher; nhân viên ghi bằng mã NV003 thay vì tên).
  - Thứ tự luật: `whole_not_part` (bỏ `share_of` trùng tử số) chạy trước `whole_as_share_of`, vì một lượt LLM ghi `share_of` trùng tử số làm che mẫu số ở số đo thứ hai ("bỉm size NB … % tổng số bịch bỉm").
  - **N96** `grounding.overdue_customers`: câu đếm khách ("bao nhiêu / mấy khách") hỏi kỳ góp quá hạn, không có chữ tiền, mà plan là tiền nợ → `overdue_installment_count` (§6 Điện thoại).
  - Đo: đọc lại s38r bằng code mới giống s51 1000/1000; đọc lại lượt chạy thật giống s51 995/1000 (trước 993).
- [x] **Docker theo guideline 2026** (`zac2026_DataMate_docker_guideline_final.pdf`):
  - Bố cục `/code` (`/code/predict.sh`, `/code/README.md`, `/code/models/model.gguf`, `/code/llama/`, `/code/training_code/`); `ENTRYPOINT []`, `CMD bash /code/predict.sh`; lệnh chấm dùng `--entrypoint bash … /code/predict.sh`. Giữ llama.cpp + CUDA 12.8 (guideline cho phép thay vLLM nếu chạy RTX 5090; đổi sang vLLM thì cách LLM đọc câu đổi, phải đo lại toàn bộ).
  - `predict.sh`: tự `cd /code`, thiết lập cố định (model, 1 GPU qua `CUDA_VISIBLE_DEVICES=0`, seed 0, một slot), log server vào `/result/logs/`.
  - **Log mỗi câu theo §3.3** (`pipeline.audit_fields`, `output/logs.py`): `thinking` = null (tắt suy nghĩ), `code` = `datamate/metrics/<module>.py::<hàm>`, `inputs` (thư mục shop + plan đã giải), `output`; mỗi bản ghi một dòng, thêm file gộp `logs/questions.jsonl`; `elapsed_ms` của câu đầu mỗi shop cộng thời gian đọc / map dữ liệu shop (`business_prep_ms`). Có test.
  - **§8 training_code**: `tools/stage_training_code.py` dựng `build/training_code/` (README `docker/training_code_README.md`, requirements, configs, mã dựng tài sản, dữ liệu train, đầu ra LLM đã dùng, log đo, `data_manifest.json` với SHA-256 từng file). Ghi rõ không huấn luyện. Thử trên laptop: 204 file, 195,7 MB.
  - README trong image: khai báo model (nguồn, phát hành 29/04/2025, Apache-2.0, 8,2 tỉ tham số); revision Hugging Face và SHA-256 của file điền trên VM lúc tải. Quy trình VM (build, chạy đúng lệnh chấm 2 lần, MD5, kích thước .tar) ở `docker/README.md`. Gói file `outputs/` cần trên VM: `outputs/docker_pack.zip`.
- Chưa làm, **dev_008 (9 câu)**: nợ chỉ ghi trong ô Note ("khách đưa trước 87k, còn thiếu 73 nghìn", "trả 259k, nợ 449.500đ", "đưa trước 236k, còn lại ghi sổ", "nợ cả đơn"…; 245 đơn ghi nợ, 15 đơn còn nợ). README: "ghi chú nợ ở Note là tình trạng của đơn tính đến hết ngày cuối dữ liệu" (22/07/2026), và cả 5 câu nợ public đều hỏi đúng ngày đó, nên tính được: đọc số còn nợ từ Note, coi như trả phần còn lại lúc mua, **chỉ trả lời khi ngày hỏi là ngày cuối dữ liệu**. Không train shop nào ghi nợ kiểu này để kiểm, nên chưa làm. Sổ nhập (3 câu tiền nhập không lọc mặt hàng) không được mượn vì khoá mặt hàng không dịch được qua 2 file bán; tiền nhập không lọc mặt hàng thì không cần khoá: có thể mượn bảng bỏ cột mặt hàng.
- Cổng thuật ngữ đang chặn đúng 3 câu điện thoại "máy cũ / máy mới bán mấy chiếc": 2 trong 3 câu sai hình (plan đòi cùng lúc hai nhóm hàng → 0; câu hỏi tổng mà trả list hai số). Giữ cổng.
- Chưa làm (cần đổi schema gửi LLM, phải chạy lại public có LLM để đo): "trung bình mỗi đơn khách phải trả" (§6 Điện thoại, 3 câu). Chưa làm (mapping): dev_008 không có sổ nhập / thanh toán vì dòng bán chia 2 file; "giá trị tồn kho" ở 2 shop không có danh mục trong mapping. → Cả hai việc đầu đã làm ở phiên 11 (N100, N101).

### Phiên 11 (chiều 08/11): tăng điểm từ câu trống của s51 (0,854)
Đo mỗi bước: train qua plan đã lưu (`tools/eval_cached.py`, phải giữ 0 sai), public đọc lại từ log s38r có gọi LLM cho lượt hỏi lại chưa có trong log (`tools/replay_run.py … --llm-url`), so với bản trước bằng `tools/compare_runs.py`. Kiểm từng câu mới trả lời bằng cách tính tay trên dữ liệu khi luật mới (không dùng đáp án).
- [x] **N97 (thấp). Xếp hạng tháng trên một tháng** (`grounding.rank_months_as_listed`, cổng `asks=months`): "Th2, th3, th4/2026 tháng nào bán nhiều tiền nhất" LLM giữ mỗi tháng có năm → xếp hạng các tháng câu hỏi liệt kê; xếp hạng tháng trên đúng một tháng mà câu không liệt kê → chặn (chỉ có thể ra chính tháng đó). Kiểm toàn bộ câu "anh em" (twin audit) thấy 1 câu nghi: đáp án không đổi.
- [x] **N98 (thấp). Bộ lọc thừa và ngưỡng ai cũng qua**: `threshold_as_value` (đếm mặt hàng có số lượng ≥ 0 khi câu hỏi một con số), `orders_with_group` (đơn có ít nhất một mặt hàng nhóm X), `series_months_as_filters` (tháng ghi thành category), `stray_numeric_filters` (tuổi nợ không phải số, cửa sổ hạn dùng câu không ghi).
- [x] **N99 (thấp). Đếm lô sắp hết hạn** (`grounding.lots_expiring_count`, `lots.expiring` với entity lot): "có mấy lô còn tồn sẽ hết hạn từ nay đến hết ngày X / trong N ngày tới" (§6 Nhà thuốc) → số lô còn hàng có hạn dùng trong cửa sổ. Train: câu duy nhất ra 5 lô như đếm tay N74. `_day_grounded` nhận "từ nay", "hiện tại", "bây giờ" là hôm nay. Train 2753 / 0 (tăng 1).
- [x] **N100 (TB). Nợ chỉ ghi là tình trạng cuối dữ liệu** (`mapping/debt_snapshot.py`, `from_readme.with_debt_snapshot`, `debt.open_orders`): README ghi "ghi chú nợ ở Note là tình trạng của đơn tính đến hết ngày cuối dữ liệu" (hoặc một cột số còn nợ) → đọc số còn nợ của mỗi đơn ghi nợ từ ghi chú ("khách đưa trước 87k, còn thiếu 73 nghìn", "trả 259k, nợ 449.500đ", "đưa trước 236k, còn lại ghi sổ", "nợ cả đơn", "nợ 79k, khách ck đủ rồi" → 0); một ghi chú không đọc được thì bỏ cả nợ của shop (không đoán). Chỉ trả lời câu nợ hỏi đúng ngày cuối dữ liệu; không trả lời "trả / thêm nợ trong kỳ" (không có sổ trả). Cần cột hình thức thanh toán; đơn COD không phải nợ (§4). Public dev_008: +5 câu (tổng nợ, số khách nợ, top 5 khách nợ, 3 nhóm tuổi nợ, nợ quá 10 ngày), đã cộng tay từng đơn khớp. Shop chỉ có cột số còn nợ mà không có hình thức thanh toán (dev_007, dev_009) để trống: không phân biệt được COD.
- [x] **N101 (TB). Cửa hàng điện thoại: chỉ số nội bộ, gộp giá trị, thuật ngữ trùng tên dữ liệu.**
  - **Chỉ số nội bộ** (`contracts.INTERNAL_METRICS`): `avg_amount_due` (trung bình mỗi đơn khách phải trả = tổng khách phải trả của đơn không huỷ, không trả / số đơn, làm tròn về đồng: §6 Thu máy cũ, §3, §9) và `trade_in_order_count` (số đơn có thu máy cũ). Chỉ luật viết lại ghi ra hai chỉ số này; `prompt.generation_schema` gỡ chúng khỏi mọi enum nên **schema gửi LLM giữ nguyên từng byte** (SHA-256 `8212c457…`, có test), câu trả lời LLM đã lưu vẫn dùng được.
  - `grounding.due_per_order`: "trung bình / bình quân mỗi đơn khách phải trả" đọc thành avg_order_value (cổng chặn) hay thành ba số → `avg_amount_due`, giữ bộ lọc có căn cứ. 3 câu.
  - `grounding.trade_in_share`: "đơn có thu máy cũ chiếm mấy % tổng đơn" → share `trade_in_order_count` / `order_count`. 2 câu.
  - `_restates`: bộ lọc là chính khoản trừ của chỉ số ("trừ tiền bớt với tiền máy cũ thu lại", "trade_in") trên amount_due_total → bỏ. 2 câu.
  - `grounding.values_together`: "gộp cả máy mới với máy cũ", "tất cả … cả máy mới lẫn máy cũ" mà plan ghi hai giá trị cùng trường (AND → 0, hoặc hai số đo → list) → một số đo với `op in`; câu hỏi tách ("lần lượt", "từng", "riêng") giữ nguyên. 2 câu (trước đó cổng thuật ngữ chặn đúng câu ra 0).
  - `rules.unverified_terms(named=…)`: từ của thuật ngữ rulebook trùng một giá trị dữ liệu plan đã nối ("máy cũ" là loại hàng, "Thu máy cũ" là thuật ngữ) thì không tính là thuật ngữ. 2 câu.
  - Đo: train 2753 / 0 (không đổi); public s55 so với s54: +11 câu trả lời, 0 câu đổi đáp án, 0 lỗi. Hai câu tháng 6 và 7/2025 cùng ra 82 máy: kiểm tay 59 + 23 và 60 + 22.
- [x] **N102 (TB). Cửa hàng điện thoại: "máy" là mọi loại không phải phụ kiện.**
  - `nlu.phone_kinds` (bước nối tên): shop có loại hàng "phụ kiện" và các loại "máy …": "máy", "điện thoại", "máy đt" → mọi loại trừ phụ kiện (như `phones_sold`, §6 Bảo hành "số máy bán"); "điện thoại cũ / mới" → "máy cũ / mới". Chỉ khi tên không nối được ở trường của nó. 3 câu.
  - `grounding.phones_as_whole`: "máy mới chiếm mấy % tiền bán máy / tổng dthu máy" → mẫu số là cùng chỉ số trên "máy". 2 câu.
  - `grounding.warranty_over_sold` + `repair._fix_warranty_share`: "lượt bảo hành so với số máy bán chiếm bnhiu %" ghi thành [warranty_count, quantity] (kiểu percent, sai hình) → `warranty_rate`. 1 câu.
  - `grounding.month_written_as_t`: "T1/2026" đọc thành quý 1 (baseline đọc tháng 1 → bất đồng, trống) → tháng; câu có "quý", "Q1" thì giữ. 1 câu.
  - Đo: public s56 so với s55: +6 câu trả lời, 0 đổi, 0 lỗi; kiểm tay 167 máy (108 + 59), 77,26 %.
- [x] **N103 (thấp). Câu lẻ cách viết**: `particle_not_unit` ("bao nhiêu hỉ": tiểu từ không phải đơn vị), `today_not_this_month` ("Hom nay ban duoc may don" đọc thành tháng này), `order_amount_named` ("phí ship" ghi thành payment_method = Ship, "dùng điểm" ghi thành khách → shipping_fee_total, points_discount; bỏ bộ lọc không căn cứ "Tại tiệm"), synonym COD "xi ô đi". Đo: train 2753 / 0 (N102 + N103 không đổi câu nào); public s57 so với s56: +6 câu trả lời và **2 câu đổi giá trị**: "Doanh thu bữa ni của tiệm", "Bữa ni tiệm bán được bao nhiêu tiền rồi" (bản nộp 0,854 trả số của cả tháng; "bữa ni" là "bữa nay" giọng miền Trung, train có 9 câu "bữa nay" đều là hôm nay) → nay trả số của hôm nay. Nhiều khả năng là sửa 2 câu sai.
- [x] **N104 (thấp). "Mấy % khách mua từ 4 đơn trở lên" ghi kèm số đo đếm khách** (`repair._fix_threshold_count`): LLM viết threshold trên số đơn và measures = customer_count (sai hình, hợp đồng đòi cùng chỉ số); train có 3 câu cùng mẫu, plan không có measures và `as_share` → sửa về đúng hình đó, `as_share` khi câu hỏi phần trăm. Chỉ khi ngưỡng là số đơn hoặc tiền của khách (không sửa "khách trả góp còn kỳ quá hạn" đọc thành ngưỡng amount_due_total).
- [x] **N105 (Cao). Shop có mã khách mà mapping lấy tên làm khoá** (`from_readme.enrich`): dev_008 có "Mã người mua: mã khách" và "Khách: tên khách"; mapping lấy tên → 210 mã khách thành 844 "khách" (mỗi khách ghi 4–8 cách: có / không số điện thoại, hoa thường). §3: "Shop có mã khách: mỗi mã khách là một khách" → khoá là mã, tên là tên khách. Mọi câu theo khách của dev_008 (đếm khách, khách mua nhiều nhất, khách nợ) đọc lại. Kiểm 14 shop public: dev_007 (190 mã, 1120 cách viết tên) và dev_008 (210 mã) đổi, các shop khác không. Train 2753 / 0. Public s58 so với s57: **9 câu đã trả lời đổi giá trị** (6 câu đếm / % khách theo ngưỡng số đơn, ví dụ "mấy khách mua từ 9 đơn trở lên" 2 → 62; 2 câu top khách; 1 câu top khách nợ chỉ đổi cách ghi tên) và 3 câu mới (2 câu hoà hạng nay có người đứng đầu, 1 câu N104). Bản nộp 0,854 trả lời các câu này trên khách bị tách 4–8 lần: nhiều khả năng đang sai.
- [x] **N106 (Cao). Khách ghi kèm số điện thoại nhiều cách** (`build.unify_keys`): dev_011 (không có mã khách) ghi "Trịnh Hằng Nam 0977824094", "Trịnh Hằng Nam - 0977 824 094", "Trịnh Hằng Nam (0977824094)" → 1545 "khách" cho 689 người (tên + số). §9 "không phân biệt hoa thường, khoảng trắng, dấu câu": khoá khách so sánh bỏ khoảng trắng và dấu câu (vẫn giữ: khác số là khác khách, khác dấu tiếng Việt là khác khách). Chỉ khoá khách; khoá mặt hàng giữ như cũ. Public: dev_011 1545 → 689, dev_009 gộp 1 cách viết chỉ khác dấu câu, các shop khác không đổi. Train 2753 / 0. Public không có câu theo khách ở dev_011 nên s59 = s58 (có ích cho private).
- [x] **N107 (TB). Danh mục và tồn kho theo tên hàng** (`from_readme._catalogue_by_name`, `_keyed_by_name`, trong `with_side_tables`; `build._build_table`): dev_007, dev_008 có danh mục kèm tồn ("Hàng bán: tên hàng", "ĐVT: đơn vị cơ bản", "Giá vốn", "Tồn cuối"), README khoá theo mã, mapping khoá dòng bán theo tên → không mượn được. Nay: danh mục thành bảng products khoá theo cột tên của nó (đơn vị cơ bản, giá vốn, nhóm), bảng phụ khoá mã mà có cột tên thì khoá theo tên (tồn kho; sổ nhập dev_008 trước là `UNKEYED`), chỉ khi ≥ 98 % tên là mặt hàng dòng bán có. Dòng "Phí phục vụ" không có tồn trong danh sách tồn (§3: không phải mặt hàng) bị bỏ thay vì làm hỏng cả bảng. Public s60: +4 câu ("hôm qua bán mấy lon" 2, "hàng tồn tính theo giá vốn" 2). Lần đo train đầu: 2753 → 2719 đúng (0 sai, +34 trống) ở 2 nhà thuốc train vì **bảng quy đổi đơn vị** ("Tên sản phẩm" + "Đơn vị cơ bản", chỉ hàng có đơn vị lớn) bị nhận là danh mục → siết: danh mục phải có giá vốn hoặc tồn kho, không có cột hệ số / tỉ lệ quy đổi / đơn vị lớn. Sau sửa: hai nhà thuốc về như cũ, một shop vật liệu train +1.
- [x] **N108 (Cao). Topping ghi chung ô với món** (`build.split_toppings`): rulebook công khai §6 Cà phê "món và topping là hai mặt hàng bán: số lượng, tiền của topping tính vào mặt hàng topping, không tính vào món" — luật không có ở train, code chưa làm. dev_002 ghi "Matcha latte (M) + 2 Thạch cà phê (14.000đ)" (1095 dòng, 1,3 %): mỗi tổ hợp thành một "mặt hàng" riêng (376 khoá → đúng ra 50). Tách: dòng món giữ số lượng, giá, đơn vị, tiền trừ tiền topping; mỗi topping một dòng (số phần ghi trước tên, không ghi là 1; tiền trong ngoặc), cùng mặt hàng "Topping <tên>" của dòng topping riêng. Ảnh hưởng mọi câu số lượng / doanh thu theo món, theo size, số topping của dev_002.
- [x] **N109 (thấp). "Ngày đắt khách nhất"** (`grounding.rulebook_rank_terms`): §3 "ngày có nhiều đơn nhất trong kỳ" (luật công khai chưa có hàm); LLM xếp theo số khách. Rà toàn bộ dòng luật công khai không có ở train: còn §1 "báo cáo tiền mặt theo ca" chưa có hàm (không có câu public nào hỏi).
- [x] **N110 (TB). Ổn định 5 câu dao động của lượt chạy thật 08/11** (`outputs/public_run13`: giống bản nộp 994 / 1000, 5 câu trả lời ở bản nộp thành trống vì LLM sinh khác). Bốn luật chung, không id câu:
  - `grounding.order_amount_named`: "vâu chơ" là voucher; ngoài trường hợp bộ lọc nhắc lại chữ (N103), nay cả khi plan doanh thu mang bộ lọc **mà mọi bộ lọc đều không căn cứ** (lượt thật: revenue + is_warranty = true) → voucher_discount, bỏ bộ lọc. Plan doanh thu không bộ lọc ("doanh thu sau khi trừ voucher") giữ nguyên.
  - `grounding.stocked_in_as_purchase`: "cất hàng" (nhập hàng, giọng Nam / Trung) mà plan là stock_value / stock_qty và câu không có "tồn", "còn" → purchase_amount (stock_qty chỉ khi câu hỏi tiền; đếm số hàng nhập không có chỉ số). Train không có câu "cất hàng"; public 2 câu.
  - `grounding.order_amount_no_item`: chỉ số cả đơn (khách phải trả, máy cũ, voucher, điểm, phí ship) mang bộ lọc mặt hàng / nhóm / dòng / hãng **không căn cứ mà giá trị là cách trả tiền hay bán** (mã payment / channel của synonyms.json, "mua chịu", "nợ") → bỏ bộ lọc thay vì chặn (lượt thật: category = "trả góp", lần gọi lại "mua chịu"). Giá trị là mặt hàng thì không bỏ: tên viết tắt ("ip15") có thể trượt kiểm căn cứ, bỏ đi sẽ trả số cả shop (sai thay vì trống).
  - `nlu.llm_plan`: JSON hỏng (`JSONDecodeError`: grammar giữ hình nên chỉ có thể là bị cắt ở max_tokens, thường là một chuỗi lặp) → gọi lại một lần, cho xem 300 ký tự đầu và yêu cầu viết ngắn; lần gọi lại qua mọi cổng, không có lần gọi lại nào sau nó (N78 nay cũng không chạy khi đã gọi lại). Log ghi `llm_cut`; `replay_run` trả lời lần gọi đầu bằng lỗi cắt như lượt gốc.
  - Chưa làm: nhân viên ghi bằng mã ("NV003") khi câu ghi tên (cần bảng nhân viên ở bước nối tên).
  - Test `tests/test_n110.py`; toàn bộ test qua. Đo 08/11 tối: train `eval_cached` **2754 / 0 / 246** (không đổi); replay s38r → s64 **giống s63 1000 / 1000** (bản nộp không đổi câu nào, không cần nộp lại); replay `public_run13` → `run13_n110` so với `chinh.jsonl`: 994 → **997 / 1000** giống (lấy lại đúng giá trị 3 câu: voucher, cất hàng, khách phải trả). Còn khác 3: NV003 (chưa làm), JSON hỏng (log gốc không có output nên replay không kiểm được; luật có test), 1 câu run13 trả lời mà bản nộp trống.
- Còn trống ở cụm điện thoại, chưa làm: "bao nhiêu máy bán tháng X đã mang lại bảo hành" (2 câu: cần nối lượt bảo hành với máy đã bán), "khách X tới hạn mấy kỳ góp" (2), "trung bình 1 máy bán bao nhiêu tiền" (2: doanh thu máy / số máy, rulebook không định nghĩa riêng), "dòng máy nào nhiều lượt bảo hành nhất" (LLM không ra plan), "mặt hàng nào lời nhiều nhất" (dev_014 không có giá vốn).

### Phiên 12 (10/11): bảng phụ cho shop nhiều bảng
- [x] **N111 (Cao). Bảng phụ theo đúng cột mục "Quy ước" của README nêu tên** (`datamate/mapping/named_sides.py`, gọi trong `from_readme.enrich` nên áp cho cả mapping chuyển từ mẫu lẫn mapping đọc lại khi replay). Shop có README chỉ liệt kê file, không mô tả từng cột (train biz_123: `pos.sqlite` 17 bảng; biz_124: 13 file Excel/CSV) được chuyển từ một mẫu; mẫu không có bảng nào thì shop mất bảng đó (biz_123 chuyển từ biz_111 chỉ đọc 5 bảng: trống 46 / 109 câu có plan). `with_side_tables` (N77) không giúp vì nó mượn từ mapping dựng bằng README, mà README không mô tả cột thì không dựng được. Nhưng mục Quy ước luôn nêu tên **một** cột của mỗi bảng phụ bằng câu chữ cố định (rà 30 README train + 14 public: cùng khuôn chữ, chỉ khác tên cột), nên lấy cột đó làm mốc, các cột còn lại đọc theo **giá trị**, không theo tên:
  - Tồn kho: "**X** là tồn cuối ngày cuối có dữ liệu" → danh sách tồn (ngày = ngày cuối, `_settle_constants`); "mỗi dòng `t.X` là tồn sau lần nhập/bán/trả đó" → thẻ kho (ngày = cột ngày duy nhất của bảng, tồn tại một thời điểm là dòng cuối).
  - Sổ chi phí: "(tiền **X**)" → số tiền; ngày = cột ngày duy nhất; mục = cột chữ duy nhất mọi dòng đều ghi, ≤ 30 giá trị.
  - Nhập hàng: "**X** là giá nhập một đơn vị" → bảng dòng nhập. Số lượng = cột số mà **giá × số = "tiền nhập của cả dòng"** ở ≥ 98 % dòng; nếu README chỉ nêu "`h.Z` là tổng tiền của cả phiếu nhập" thì số lượng là cột mà **Σ giá × số theo phiếu = Z** ở ≥ 98 % phiếu, mã phiếu là cột có ở cả hai bảng và là khoá của bảng phiếu (cột id cửa hàng ghi mọi dòng bị loại), ngày và nhà cung cấp tra từ bảng phiếu; bảng phiếu có cột trạng thái mang hơn một giá trị (có thể có phiếu huỷ) → không nhận. Sổ ghi tay không có bảng phiếu: ngày nhập = cột ngày ≤ ngày cuối dữ liệu và **sớm hơn mọi cột ngày khác** (hạn dùng luôn sau ngày nhập, kể cả hàng cận date), so theo ngày đã đọc (một phiếu ghi "01/01/2025", "2025-01-01", "1 thg 1 2025"); mã phiếu = cột ghi ở mọi dòng, gom dòng, mỗi giá trị đúng một ngày (cột ghi chú "nhập đầu kỳ" chỉ có ở 80 / 3943 dòng bị loại); nhà cung cấp theo tên cột ("nhà cung cấp", NCC).
  - Thuốc: "**X** đúng (TRUE/1) là thuốc kê đơn" → tra cờ kê đơn vào danh mục bằng cột mã khớp mã danh mục hai chiều ≥ 90 %; hoạt chất = cột duy nhất khác có chuỗi " + " (README: "nhiều chất nối bằng ' + '").
  - Quy đổi đơn vị: "hệ số quy đổi ở bảng `t`" → mã hàng, đơn vị (giá trị là đơn vị dòng bán ghi), hệ số = cột số nguyên 1–1000 mà **số lượng dòng bán × hệ số = số lượng cơ bản** ở ≥ 98 % dòng bán theo đơn vị đó.
  - Mã hàng của mọi bảng phụ: cột có ≥ 90 % giá trị là mã hàng dòng bán; không có thì cột có ≥ 90 % giá trị là **tên** trong danh mục, dịch tên → mã qua danh mục (README biz_124: "sổ tay không có mã hàng, nối qua tên hàng"). Hai cột cùng khớp: không đoán.
  - Sổ nhập đã có trong mapping mà mã hàng < 90 % khớp dòng bán (biz_124: chuyển từ mẫu, khoá theo tên trong khi dòng bán khoá theo mã → mọi câu giá nhập trống) → đọc lại từ chính bảng đó.
  - Tên khách: bảng khách được map không có tên → cột cùng tên với cột tên hàng của danh mục (một bản xuất đặt tên cột tên giống nhau ở mọi danh sách: "TenGoi" ở sản phẩm, nhân viên, khách), giá trị không phải mã khách.
  - Mỗi bảng chỉ nhận khi không làm hỏng thêm kiểm tra nào (`_failed_checks` trước / sau).
- [x] **N111b. Số khách phải trả của đơn theo cột README nêu** (`from_readme.with_conventions`): trước chỉ thay khi mapping đọc cột thành tiền của dòng; nay thay khi mapping đọc **bất kỳ cột nào khác** cột README nêu ("`don_hang.TongThanhToan` là số khách phải trả cho cả đơn"). biz_123 chuyển theo nghĩa đọc `TongTienHang` (tiền hàng, trước chiết khấu và phí ship) → mọi đơn trả đủ vẫn "còn nợ", `open_orders` trả None, 14 câu công nợ trống.
- Test `tests/test_n111.py` (8 test: đọc quy ước, danh sách tồn / thẻ kho, sổ chi phí, sổ nhập khoá theo tên dịch qua danh mục, ngày nhập không phải hạn dùng, không đoán khi giá × số ≠ tiền, phiếu nhiều trạng thái, total_due theo README, tên khách). Toàn bộ test qua.
- Đo 10/11: `eval_cached --business biz_123 biz_124`: biz_123 **63 → 99**, biz_124 **86 → 95** (0 sai, 0 cache miss). Còn trống ở hai shop: 27 câu không có plan trong bank (LLM không ra plan hoặc `accept_plan` chặn), lô / hạn dùng (biz_123 4, biz_124 2: README không nêu cột nào của bảng lô), nhân viên theo tên / người bán nhiều nhất (3: README không nêu cột nhân viên), doanh thu theo ca (2: mapping đọc `NgayLap` không giờ thay vì `ThoiGianLap`).
- Kết quả đo N111 (10/11): train `eval_cached` **2754 → 2799 / 0 / 201** (+45, chỉ ở biz_123 và biz_124; các shop khác không đổi; 0 cache miss; log `outputs/eval_cached_n111.log`). Replay public s38r → `run11_s65` **giống s64 1000 / 1000** (0 lỗi): public không đổi câu nào, vì hai shop public cùng khuôn (dev_006 `pos.sqlite`, dev_003 `BanHang_*` + `SoTay_*`) chuyển mapping từ chính biz_123 / biz_124, đã đủ bảng phụ. Lợi ích là cho private: shop cùng khuôn nhưng đổi tên cột / tên file thì chuyển theo nghĩa hoặc theo vai trò từ mẫu khác (như biz_123, biz_124 khi bị bỏ khỏi ví dụ) và nay vẫn lấy được tồn, nhập, chi phí, quy đổi, thuốc. Không có bản nộp mới (`chinh.jsonl` vẫn là bản chính).

### Phiên 13 (10/11, chiều): nhắm 47 câu public trống của s65 (trưởng nhóm duyệt việc A, B)
- [x] **N112 (Cao). "Không trả lời được" khi shop không ghi loại dữ liệu câu hỏi cần** (§7 công khai: "Thông tin file không ghi thì không suy ra từ cột khác… shop không ghi loại thông tin câu hỏi cần thì không trả lời được"). `verify.not_recorded` (trong `collect_signals`, nên `eval_cached` đo được; README lưu vào `CanonicalDB.readme`):
  - plan lọc / xếp theo **nhóm hàng** mà README không có cột nào nghĩa "nhóm…" (trừ nhóm khách), "loại hàng", "danh mục", "phân loại" và mapping không có `product_group` → public: dev_002 (quán cà phê) 3 câu "nhóm trà / cà phê / trà sữa", dev_004 4 câu "nhóm sơn / điện". Train không có câu nhóm ở shop thiếu cột nhóm: **chưa có tiền lệ, rủi ro chính của bản nộp**.
  - chỉ số **lãi gộp** (gross_profit) mà README không nhắc "giá vốn" và mapping không có giá vốn → train biz_122 "lãi gộp tháng 3/2025" là unanswerable; public dev_014 "mặt hàng nào lời nhiều nhất".
  - câu hỏi theo **lý do trả / huỷ** ("bị huỷ vì giao trễ", "trả lại vì gọi nhầm", "huỷ đơn chủ yếu vì sao"; loại trừ "trả bằng ví điện tử") mà README không có "lý do / nguyên nhân" và bảng trả hàng không có cột lý do → train 2 / 2 câu unanswerable (biz_118, biz_121, trước đây trống); public 4 câu, trong đó dev_003 "Th5/2026 khách huỷ đơn chủ yếu vì sao" **bản nộp đang trả số 90** (câu hỏi lý do mà trả số: gần như chắc sai) → nay unanswerable.
  - `grounding.subjective_quality`: thêm phẩm chất mặt hàng ("chất lượng tốt nhất", "ngon nhất"; "chất lượng" bỏ dấu không còn trùng "số lượng"); `nlu.parse_question`: LLM xếp hạng theo phẩm chất không có định nghĩa ("thợ nhiệt tình nhất": rulebook chỉ định nghĩa "chăm chỉ") → unanswerable. Train: 5 / 5 câu `subjective_quality` bắt đều unanswerable.
- [x] **N113 (TB). Đếm đơn bán chịu theo "Ngày phải trả" của sổ hạn nợ** (dev_004, 6 câu; trưởng nhóm duyệt dù train không có câu mẫu): README "**Ngày phải trả** là ngày khách phải trả hết đơn; chỉ đơn bán nợ có hạn". `from_readme.enrich` tra `orders.due_date` (cột mới, tuỳ chọn) từ bảng có "mã đơn" + "hạn thanh toán"; chỉ số nội bộ `due_order_count` (`metrics/debt.py`, schema gửi LLM không đổi, test hash qua); `grounding.due_date_count_plan` đọc câu "mấy đơn … ngày phải trả trong tháng M/YYYY / muộn hơn (sau) hôm nay" → kỳ "đến hết hôm nay" (đơn đặt tới hôm nay, không huỷ), tháng hạn trả hoặc "sau hôm nay" ở bộ lọc `other` (tháng thường sau hôm nay nên không thể là kỳ của plan: `temporal.resolve` bỏ kỳ sau hôm nay). Đếm tay từ file gốc khớp cả 6 (152, 145, 19, 164, 21, 35). Sổ hạn nợ không có đơn huỷ (2568 đơn đều hoàn thành / đang giao).
- Test `tests/test_n112_n113.py` (7 test); schema file sinh lại (`export_schema`); toàn bộ test qua.
- Đo (đêm 10/11): train `eval_cached` **2801 / 0 / 199** (+2 so với N111: biz_118 "huỷ vì giao trễ", biz_122 "lãi gộp" không giá vốn; log `outputs/eval_cached_n113.log`). Replay s38r → `run11_s66` so với s65: **20 câu khác, 0 lỗi**: 6 câu "ngày phải trả" trống → số; 13 câu trống → unanswerable (nhóm hàng 6, lý do trả / huỷ 3, chủ quan 3, lời không giá vốn 1); 1 câu trả lời → unanswerable (dev_003 "huỷ đơn chủ yếu vì sao", trước trả 90). Bộ nộp 17: `outputs/public_cand17/` (xem CAN_XAC_MINH "Bộ nộp 17").

### Phiên 15 (09/11, đồng đội, nhánh task/chained-factors): câu trống train — chỉ ghép phần căn cứ train / README
- Ghép 10/11 bằng cherry-pick 4 commit (e4a78b0, 34805b7, 80b0478, e41bafe). **Không ghép** `tools/grade_public.py` và N114, N124–N136: các luật đó được chọn bằng cách chấm với đáp án public, quy định cấm dùng nhãn public để chỉnh giải pháp; chờ xác nhận nguồn đáp án và BTC. Số "public … / … / …" trong các mục dưới là đo bằng đáp án đó, chỉ để tham khảo.
- Bảng theo dõi "Trống - train" (268 câu, dựng từ run11): trên main + N114, 90 câu đã đúng, 179 vẫn trống (đúng bằng toàn bộ câu trống train). Đo theo bước dừng × đáp án train (`eval_cached --save`, mới): `value_of` không ra số 68 (19 unanswerable), không có plan 57 (5), `compare` 12 (0), … Ba nhóm lớn sửa bằng luật chung:
- [x] **N115 (TB). Tồn kho ở shop không ghi tồn kho → không trả lời được** (`verify.not_recorded`): train 4 shop có câu "hết hôm nay … còn mấy lon trong kho" mà README không có chữ "tồn", "kho", "lô" và mapping không có bảng tồn / lô: **9 / 9 unanswerable**; mọi shop train có câu tồn kho trả lời được đều ghi "Tồn kho", "Tồn thực" hoặc "số lô".
- [x] **N116 (TB). Lô hàng từ README khi mapping chuyển từ mẫu không có** (`from_readme._lot_tables`, tồn theo lô trong `stock.stock_base_qty`): nhà thuốc train ghi "Mã lô", "Hạn sử dụng", "Số lượng nhập (đơn vị cơ bản)" ở dòng nhập và "Số lượng bán lấy từ lô" ở sổ lô; mapping mẫu bỏ cả hai. Thêm `lots` (mặt hàng đổi từ mã SKU sang tên qua danh mục khi dòng bán nối theo tên) và `lot_sales`; shop không có sổ tồn thì tồn hết ngày = cộng phần còn của các lô (`lots_left`, N74: khớp thẻ kho 80 / 80). biz_121 107 → 114, biz_122 111 → 116.
- [x] **N117 (TB). Bảng quy đổi từ README khi mapping chuyển từ mẫu không có** (`from_readme._conversion_table`): README "Đơn vị quy đổi: đơn vị lớn", "Tỉ lệ quy đổi: hệ số", "Đơn vị cơ bản"; mapping mẫu chỉ có đơn và dòng hàng, nên mặt hàng bán theo gói và thùng không có đơn vị cơ bản: 9 câu hiệu ứng tăng giá (§5) không ra số. biz_103 100 → 116.
- Đo: train `eval_cached` **2821 / 0 / 179 → 2852 / 0 / 148, PA +0,940 → +0,951**, CACHE MISSES 0. Public (đọc lại lượt chạy thật): không đổi câu nào (shop public đã có các bảng này), 950 / 14 / 36. Có test (`tests/test_n115_n117.py`). Công cụ: `datamate.eval.mapping --save` (qua `tools/eval_cached.py`) ghi kết quả và bước dừng từng câu train; `check_plans.check` trả thêm lý do quyết định và `no_result`.

## Thứ tự xử lý đề xuất
1. **T4 sáng:** sửa H1–H7, sinh lại schema, thêm test cho từng mục.
2. **T4–T5:** K2 (cả nhóm), K3 (người có kinh nghiệm), K1 review chéo.
3. **Tối T5:** khóa hợp đồng.
4. **Sau chia vai:** H8, H9, H10; N1–N3 khi loader và parser xong.
