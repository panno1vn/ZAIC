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
- [ ] **N16 (TB). Có nên giữ cổng câu anh em không: số trên train còn sát nhau.**
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
- `R_MAIN_SUPPLIER` đọc một dòng chỉ có trong rulebook public. Rulebook là đầu vào đi kèm mỗi split, và [R] chặn khi dòng đó vắng, nên hợp lệ.

**Hướng đi:**
- 2/3 số câu bỏ trống trên train (≈ 790/1185) là của 10 cửa hàng không map được. Ở 20 cửa hàng map được: ≈ 85% đúng, 0 sai. **Đòn bẩy lớn nhất vẫn là độ phủ mapping.** Mapping chuyển từ mẫu chỉ phủ các định dạng train có; private có thể có định dạng mới.
- [ ] **N23 (Cao). Mapping dựng từ README khi không mẫu nào khớp.** README mô tả từng cột ("## Cột trong `file`", "- **cột**: ý nghĩa"), và README ở mọi split đều theo một khuôn. LLM chọn cột cho từng cột chuẩn theo mô tả README, rồi qua 10 bước kiểm tra. Dò và đo trên 10 cửa hàng train không map được (leave-one-out), yêu cầu 0 sai.
- [ ] **N24 (Cao). "0 sai" là số trong mẫu.** Các cổng và chốt được thêm sau khi thấy lỗi trên chính train, nên tỉ lệ sai thật trên cửa hàng mới chưa biết. **Nộp public sớm nhất có thể** để đo; mỗi ngày được 5 lần, so cả bật / tắt cổng câu anh em (N16).
- Docker chưa làm (kế hoạch 10–12/11, chờ guideline BTC): llama-server CUDA ≥ 12.8 trong image, chép `assets/` (H14), chạy thử đủ 6 giờ trên máy thuê.

## Thứ tự xử lý đề xuất
1. **T4 sáng:** sửa H1–H7, sinh lại schema, thêm test cho từng mục.
2. **T4–T5:** K2 (cả nhóm), K3 (người có kinh nghiệm), K1 review chéo.
3. **Tối T5:** khóa hợp đồng.
4. **Sau chia vai:** H8, H9, H10; N1–N3 khi loader và parser xong.
