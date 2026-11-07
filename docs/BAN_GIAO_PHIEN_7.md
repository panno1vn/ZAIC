# Bàn giao phiên 7 (06/11) → phiên 8

*Viết 06/11/2026. Đóng băng 16/11 23:59. Chi tiết từng bản sửa ở [HAN_CHE_VA_CAI_THIEN.md](HAN_CHE_VA_CAI_THIEN.md) mục N (N22–N44). Việc chờ lượt nộp lẻ ở [CAN_XAC_MINH.md](CAN_XAC_MINH.md). Bàn giao trước: [BAN_GIAO_PHIEN_6.md](BAN_GIAO_PHIEN_6.md).*

## Bắt đầu phiên mới
Dán vào phiên chat mới:

> Đọc `docs/BAN_GIAO_PHIEN_7.md`, rồi `docs/CAN_XAC_MINH.md`. Kiểm `git status` và test (`.venv\Scripts\python.exe -m pytest -q`). Làm tiếp mục "Việc tiếp theo", bắt đầu từ dev_012.

- **Python:** `.venv\Scripts\python.exe` (python hệ thống không có pytest).
- **LLM:** trưởng nhóm tự mở llama-server, cổng 8091; Claude không chạy file `.exe`:
  ```powershell
  cd E:\llm\llama-b12064
  .\llama-server.exe -m E:\llm\models\Qwen3-8B-Q4_K_M.gguf --jinja -ngl 99 -c 8192 --parallel 1 --host 127.0.0.1 --port 8091
  ```
- **Hai trang tổng kết** (artifact, riêng tư):
  - [Nhật ký DataMate 04–06/11](https://claude.ai/artifact/HxQE5wiQDt2bJLCbnMfftj): việc đã làm và luật dữ liệu;
  - [Đường lên 0,9](https://claude.ai/artifact/ByVitABJohuFUt9UKUL3rM): các hướng H1–H7, mục "Khi đã chạm 0,8", lịch tới 16/11.

## Tình hình
| Thước đo | Giá trị |
|---|---|
| Điểm public mới nhất | **0,540** (`outputs/public_run9/submission.jsonl`, nộp 05/11 16:43, ghi chú "thử full") |
| Câu trả lời public | 608/1000; suy từ điểm: khoảng **574 đúng, 34 sai** (94%) |
| Train `eval.mapping --llm-url` | **2656 đúng / 0 sai / 344 bỏ trống, PA +0,885** (`outputs/eval_mapping_s7d.log`) |
| Test | **389 qua** (`outputs/pytest_s7c.log`) |
| Cửa hàng public map được | **14/14** (đầu phiên 6: 8/14) |

Điểm public qua các lượt: lượt 1 0,316 → run4 0,342 → **run9 0,540**.

| Cửa hàng mới map | Ngành, đường map | Trả lời ở run9 |
|---|---|---|
| dev_003 | bản xuất phần mềm, ghép bảng theo vai trò (mẫu biz_124) | 97/129 |
| dev_009 | chỉ có hoá đơn, README | 19/21 |
| dev_013 | mẹ và bé, ghép theo nghĩa (mẫu biz_101) | 30/57 |
| dev_011 | điện thoại, README | 15/40 |
| dev_014 | điện thoại, ghép theo vai trò (mẫu biz_111) | 10/63 |
| dev_012 | sửa xe, chỉ có bảng phiếu | **0/50** |

## Luật dữ liệu (đã đổi trong phiên 7)
- **N22 được gỡ (06/11):** BTC cho xem dữ liệu public. Giới hạn giữ lại:
  - chỉ xem để tìm **kiểu lỗi định dạng**;
  - mọi bản sửa là quy tắc chung;
  - không có id cửa hàng hay id câu hỏi trong code, kể cả comment (`test_no_id_logic` đã bắt một lần);
  - không viết mapping, plan hay đáp án tay cho cửa hàng public;
  - train vẫn phải 0 sai.
- **Luật về dữ liệu và tài nguyên, nguyên văn:** "teams may use public data and open-source models released before 26 October 2026, provided their licences allow it. Synthetic data may be generated with other services or models (LLM, TTS, …) during development, but these must not be used at inference. Labelling public_test or private_test (manually or with external services or models) to train or tune a solution is not allowed."
  - **Được:** dùng API (Claude, GPT…) sinh dữ liệu tổng hợp từ train hoặc từ cửa hàng tự dựng, lúc phát triển. API chỉ viết; đáp án do code tính theo rulebook.
  - **Không được:**
    - gọi API khi chạy dự đoán;
    - gán plan hay đáp án cho câu public, private;
    - dò đáp án từng câu public bằng lượt nộp (chỉ chẩn đoán theo nhóm lớn);
    - dùng model có tổng > 15B hoặc công bố sau 26/10/2026.
- Vẫn như cũ: khi nộp chọn loại "SLM"; trưởng nhóm tự commit; hỏi trước khi tải file > 50 MB (mạng 4G).

## Phiên 7 đã làm (HAN_CHE mục N)
| Mục | Việc | Kết quả |
|---|---|---|
| N39 | đơn ghi trùng y hệt tính một lần (§8); nhóm bảng theo bố cục cho workbook nhiều danh sách; cho phép sheet gộp hoá đơn và chi tiết có mã đơn; chữ "Khách trả" là trả hàng | dev_003, dev_009 map được |
| N40 | trạng thái từ cột Ghi chú (§8 mới của public), phép biến đổi `status_from_note`; cụm đồng nghĩa trong README ("số hoá đơn", "thành tiền của dòng", "hàng bán"…); "chưa giao", "mang trả"; "kiểm tra lại" không phải trả hàng | dev_011, dev_013, dev_014 |
| — | **Lỗi chung đã sửa: `_fill_down`.** Lấy nhầm ô của đơn trước (một sổ có 834/3819 đơn thành trả hàng) | train không đổi |
| N41 | dòng Voucher, Dùng n điểm, Phí ship thành khoản của đơn (§1) | dev_013 |
| N42 | sổ phiếu sửa xe không mã; biển số, dòng xe; phiếu bảo hành; thợ về họ tên đầy đủ; giá trị trung bình bỏ phiếu bảo hành | dev_012 map được |
| N43 | tên viết tắt tra sheet "Ghi tắt" (`expand_abbreviations`, `lookup` có `fold`); đơn vị cơ bản > 30 giá trị thì bỏ | dev_011, dev_014 có 59 tên đầy đủ |
| N44 | chỉ số ngành: số phiếu, tiền trung bình một phiếu, số xe, phiếu bảo hành, tỉ lệ bảo hành, voucher, điểm, phí ship, tiền thu máy cũ; bộ lọc dòng xe, phiếu bảo hành | có test tính tay |
| — | Docker: `predict.sh` in thời gian nạp model và thời gian dự đoán; thêm `docker/predict_notebook.ipynb`; đối chiếu hướng dẫn Docker 2025 trong `docker/README.md` | chưa build |
| — | Kaggle K1: `tools/kaggle_k1.py` tự tìm `libcuda` (Kaggle lên CUDA 13), dừng sớm nếu không có GPU | chưa chạy lại |
| — | `tools/ablate.py` thêm `--shops`, `--metric`, `--entity` | dựng lượt chẩn đoán |

**Một lần hồi quy và cách bắt:** bản đầu của `expand_abbreviations` kích hoạt nhầm ở cửa hàng ghi mã "SP001", làm train mất 67 câu. Lượt `eval.mapping` bắt được, nên run9 lần đầu đã dừng giữa chừng. Cách sửa: đòi ≥ 10% tên trong sổ ghi thẳng tên đầy đủ.

## Việc tiếp theo (theo trang "Đường lên 0,9")
1. **H1. dev_012 sửa xe, 0/50.**
   - Cửa hàng đã map (6060 phiếu, qua mọi kiểm tra), nhưng log run9 có 46 câu "không có kết quả" và 4 câu "mapping_ok".
   - Đọc log từng câu (`outputs/public_run9/logs/q_*.json`, cửa hàng dev_012) để xem hàm nào được gọi, vì sao rỗng.
   - Nghi: đường chỉ có bảng đơn với grain `line_is_record`; hoặc plan dùng `ticket_count` / `employee` mà điều kiện `_tickets` không thoả.
   - Có thể dựng một sổ sửa xe giả (H7 S1) để thử.
2. **H6. Nộp chẩn đoán** để đo độ chính xác phần mới. Dựng từ **run9** (lượt đủ đã nộp):
   - bỏ hai cửa hàng mới map đầu tiên: `python tools/ablate.py outputs/public_run9 --out outputs/public_ablation9/bo_003_009.jsonl --shops dev_003 dev_009`;
   - bỏ từng cửa hàng ngành mới: `--shops dev_011 dev_014`, `--shops dev_013`;
   - số sai của nhóm = (số câu − (0,540 − điểm) × 1000) / 2. Cửa hàng sai ≥ 30% thì tạm chặn.
3. **H2. Điện thoại:**
   - loại máy (cột Loại của sheet "Ghi tắt" → `category`);
   - dòng máy, hãng (§6: phần tên trước "…GB"; chữ đầu tên, iPhone là Apple);
   - sổ nợ, sổ góp, sổ bảo hành của dev_014.
4. **H3. Mẹ và bé:** số sữa, size bỉm (cột Số / Size của danh mục), khách thành viên mới, quy đổi "1 thùng = 4 bịch".
5. **H4. Khái niệm mới của rulebook public:** khách trung thành, khách sộp (≥ 3 đơn), khách hay đổi ý, mặt hàng được ưa chuộng, nhân viên chăm chỉ, ngày đắt khách, giờ cao điểm, nhà cung cấp chính, trung bình mỗi ngày thứ X.
6. **H7. Dữ liệu tổng hợp** (luật cho phép):
   - S1: cửa hàng giả của ba ngành mới, đáp án do code tính;
   - S2: câu hỏi cho ngành mới, đưa vào kho ví dụ;
   - S3: các cách viết khác của câu train.
7. **Khi đã chạm 0,8** (mục K1–K5 trong trang "Đường lên 0,9"):
   - bỏ trống nhóm có chính xác < 50%;
   - trả unanswerable đúng chỗ;
   - **đọc tham số từ rulebook** thay vì chặn khi luật đổi (quan trọng cho private);
   - sinh code dự phòng có kiểm chứng.
8. **Docker** (10–12/11): build trên RTX 5090 thuê dạng VM, chạy public trong container không mạng, đo thời gian; nộp lần 1 ngày 14/11.

## Lệnh hay dùng
| Việc | Lệnh |
|---|---|
| Đo train (so được với các số ở trên) | `.venv\Scripts\python.exe -m datamate.eval.mapping --llm-url http://127.0.0.1:8091` |
| Chạy public đủ 1000 câu (~42 phút) | `.venv\Scripts\python.exe -m datamate.predict --data data/public_test --out outputs/public_runN --llm-url http://127.0.0.1:8091` |
| Kiểm định dạng file nộp | `.venv\Scripts\python.exe -m datamate.eval.validate --pred outputs/public_runN/submission.jsonl --split public_test` |
| Lượt chẩn đoán | `python tools/ablate.py outputs/public_runN --out x.jsonl [--shops …] [--function …] [--metric …] [--entity …]` |
| Bản sao đổi tên trên train | `python tools/variant_eval.py --llm-url http://127.0.0.1:8091 [--leave-out] [--rename-files] [--strip-readme]` |
| Chạy lại một lượt từ log, không LLM | `python tools/replay_run.py outputs/public_runN --out outputs/replay/x` |
| Xuất lại schema sau khi đổi hợp đồng | `python -m datamate.contracts.export_schema` |

**Quy tắc khi sửa:** mỗi bản sửa có test và một mục trong HAN_CHE. Sau mỗi thay đổi ở `datamate/mapping/` hay `datamate/metrics/` phải chạy `eval.mapping`: train phải vẫn 0 sai và **không giảm** câu đúng.

## Git
Chưa commit gì từ `70c3dc4`. Lệnh cho trưởng nhóm:
```powershell
cd E:\ZAIC
git add .gitignore .dockerignore configs datamate docker docs kaggle tests tools
git commit -m "Phiên 5-7: N27, N33-N44: định dạng lạ, ngành mới (điện thoại, sửa xe, mẹ và bé), trạng thái từ ghi chú, sửa _fill_down; train 2656/0 PA +0.885; public run9 0.540"
git push origin main
```
