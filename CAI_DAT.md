# Cài đặt và chạy DataMate (Windows và Linux)

Làm theo thứ tự từ trên xuống. Mỗi bước có lệnh cho **Windows (PowerShell)** và **Linux (bash)**.
Xong bước 6 là máy bạn ra đúng số của nhóm: `pytest` qua hết, train **2747 đúng / 0 sai**.

| Bước | Việc | Cần mạng | Bắt buộc |
|---|---|---|---|
| 1 | Cài Python 3.10 và Git | ít | có |
| 2 | Clone repo | ít | có |
| 3 | Tạo môi trường ảo, cài thư viện | ~100 MB | có |
| 4 | Đặt dữ liệu của BTC vào `data/` | ~300 MB | có |
| 5 | Giải nén gói `outputs` trưởng nhóm gửi | 3 MB | có |
| 6 | Kiểm tra: test và đo train | không | có |
| 7 | Cài llama.cpp và model Qwen3-8B (chạy LLM) | ~5 GB | chỉ khi việc của bạn cần LLM |

---

## 1. Python 3.10 và Git

Dự án viết và kiểm trên **Python 3.10** (`pyproject.toml`). Bản 3.11 hay 3.12 nhiều khả năng vẫn chạy, nhưng nếu có lỗi lạ thì quay về 3.10.

**Windows:** tải Python 3.10 ở python.org (tick "Add python.exe to PATH") và Git ở git-scm.com.
```powershell
python --version      # Python 3.10.x
git --version
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install -y git python3.10 python3.10-venv   # hoặc python3 nếu hệ có sẵn 3.10
python3.10 --version
```

## 2. Clone repo
```bash
git clone https://github.com/panno1vn/ZAIC.git
cd ZAIC
```
Repo ép xuống dòng kiểu Linux (`.gitattributes`), nên không cần chỉnh gì thêm trên Windows.

## 3. Môi trường ảo và thư viện

**Windows:**
```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

**Linux:**
```bash
python3.10 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
```

`requirements.txt` là thư viện để chạy (pandas, numpy, openpyxl, python-calamine, pydantic, rapidfuzz, rank-bm25). `requirements-dev.txt` thêm `pytest`.

Từ đây trở đi, **gọi Python của môi trường ảo**:
- Windows: `.venv\Scripts\python.exe`
- Linux: `.venv/bin/python`

Windows in tiếng Việt ra màn hình bị lỗi font nếu không đặt biến này, nên đặt một lần trong mỗi cửa sổ PowerShell:
```powershell
$env:PYTHONIOENCODING = "utf-8"
```

## 4. Dữ liệu của BTC

Thư mục `data/` **không có trong repo** (nằm trong `.gitignore`). Tải `train.zip` và `public_test.zip` từ trang cuộc thi, giải nén sao cho có đúng cấu trúc:
```
data/
├── train/
│   ├── questions.jsonl   3000 câu hỏi
│   ├── answers.jsonl     đáp án (chỉ train có)
│   ├── rulebook.md       luật tính
│   ├── calendar.csv      lịch (Tết, tuần…)
│   └── data/biz_101/ …   file của từng cửa hàng
└── public_test/
    ├── questions.jsonl   1000 câu
    ├── rulebook.md
    ├── calendar.csv
    └── data/dev_001/ …
```
Kiểm: `data/train/questions.jsonl` và `data/public_test/questions.jsonl` phải tồn tại.

## 5. Gói `outputs` của trưởng nhóm

Thư mục `outputs/` cũng không có trong repo. Trưởng nhóm gửi `team_pack.zip` (vài MB), giải nén **ngay tại gốc repo** để có `outputs/...`:

**Windows:**
```powershell
Expand-Archive team_pack.zip -DestinationPath . -Force
```
**Linux:**
```bash
unzip -o team_pack.zip
```

Trong gói:

| File | Dùng để |
|---|---|
| `outputs/llm_cache_mapping.jsonl` | câu trả lời đã lưu của LLM ở bước ghép cột: đo train không cần server |
| `outputs/bank/llm_plans.jsonl` | plan LLM đã đọc cho 3000 câu train: đo train không cần server |
| `outputs/public_run11/` | lượt chạy public đủ 1000 câu có LLM (07/11): `submission.jsonl` và log từng câu |
| `outputs/replay/run11_s3x/` | các lượt đọc lại run11 bằng code mới; bản mới nhất là bản nên nộp |
| `outputs/public_ablation12/` | bộ bài nộp chẩn đoán (bỏ trống từng nhóm) |

## 6. Kiểm tra máy đã chạy đúng

**Windows:**
```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe tools/eval_cached.py
```
**Linux:**
```bash
.venv/bin/python -m pytest -q
PYTHONIOENCODING=utf-8 .venv/bin/python tools/eval_cached.py
```

Phải thấy:
- `pytest`: mọi test **passed**, không có failed (khoảng 20 giây);
- `eval_cached` (khoảng 15 phút): dòng cuối `3000 câu · đúng 2747 · sai 0 · bỏ trống 253` và `CACHE MISSES: 0`.

Số khác là máy bạn khác máy nhóm: báo trưởng nhóm trước khi sửa code.

## 7. LLM: llama.cpp và Qwen3-8B (khi việc của bạn cần)

Cần cho: chạy lượt public đủ (`datamate.predict --llm-url`), chạy lại plan cho vài cửa hàng (`tools/run_shops.py`), đo train khi đổi prompt. **Không cần** cho: test, `eval_cached`, `replay_run`, `compare_runs`.

**Model** (khoảng 5 GB, tải ở mạng mạnh, không dùng 4G): `Qwen/Qwen3-8B-GGUF`, file `Qwen3-8B-Q4_K_M.gguf`.
```bash
.venv/bin/python -m pip install -U huggingface_hub          # Windows: .venv\Scripts\python.exe -m pip ...
huggingface-cli download Qwen/Qwen3-8B-GGUF Qwen3-8B-Q4_K_M.gguf --local-dir models
```
Cần GPU NVIDIA khoảng 8 GB VRAM. Không có GPU vẫn chạy được trên CPU nhưng rất chậm (nhiều giờ cho 1000 câu).

**llama.cpp**: dùng **đúng bản `b12064`**, giống bản trong Docker.
- **Windows:** vào trang Releases của `ggml-org/llama.cpp`, tag `b12064`, tải gói `bin-win-cuda-…-x64.zip` cùng gói `cudart-…` tương ứng, giải nén cả hai vào một thư mục (ví dụ `E:\llm\llama-b12064`).
- **Linux:** build từ mã nguồn với CUDA:
  ```bash
  git clone --depth 1 --branch b12064 https://github.com/ggml-org/llama.cpp
  cd llama.cpp && cmake -B build -DGGML_CUDA=ON && cmake --build build --target llama-server -j
  ```

**Mở server** (giữ cửa sổ này mở trong lúc chạy):
```powershell
# Windows
cd E:\llm\llama-b12064
.\llama-server.exe -m <đường dẫn>\Qwen3-8B-Q4_K_M.gguf --jinja -ngl 99 -c 8192 --parallel 1 --host 127.0.0.1 --port 8091
```
```bash
# Linux
./build/bin/llama-server -m <đường dẫn>/Qwen3-8B-Q4_K_M.gguf --jinja -ngl 99 -c 8192 --parallel 1 --host 127.0.0.1 --port 8091
```
Kiểm: mở `http://127.0.0.1:8091/health`, thấy `{"status":"ok"}` là được. Các tham số phải giữ như trên (`--parallel 1`, `-c 8192`, cổng 8091), vì kết quả của nhóm đo bằng đúng cấu hình này.

---

## Lệnh hay dùng

Viết theo Windows; trên Linux thay `.venv\Scripts\python.exe` bằng `.venv/bin/python`.

| Việc | Lệnh | Cần LLM |
|---|---|---|
| Chạy toàn bộ test | `.venv\Scripts\python.exe -m pytest -q` | không |
| Đo train (bằng cache) | `.venv\Scripts\python.exe tools/eval_cached.py` | không |
| Đọc lại lượt public bằng code mới | `.venv\Scripts\python.exe tools/replay_run.py outputs/public_run11 --out outputs/replay/ten_cua_ban --enrich` | không |
| So hai lượt từng câu | `.venv\Scripts\python.exe tools/compare_runs.py outputs/replay/ten_cua_ban outputs/replay/run11_s35/submission.jsonl` | không |
| Đếm câu trống theo lý do | `.venv\Scripts\python.exe tools/run_stats.py outputs/replay/ten_cua_ban` | không |
| Kiểm định dạng file nộp | `.venv\Scripts\python.exe -m datamate.eval.validate --pred <file> --split public_test` | không |
| Chạy public đủ 1000 câu (~40 phút) | `.venv\Scripts\python.exe -m datamate.predict --data data/public_test --out outputs/public_runN --llm-url http://127.0.0.1:8091` | có |
| Chạy LLM cho vài cửa hàng | `.venv\Scripts\python.exe tools/run_shops.py outputs/public_x dev_007 dev_008` | có |
| So rulebook train và public | `.venv\Scripts\python.exe -m datamate.rules diff data/train/rulebook.md data/public_test/rulebook.md` | không |

---

## Các thư mục và file làm gì

### Gốc repo
| Đường dẫn | Là gì |
|---|---|
| `CAI_DAT.md` | file này |
| `README.md` | giới thiệu ngắn, lệnh cơ bản |
| `DataMate_instruction.md` | đề bài của BTC |
| `requirements.txt`, `requirements-dev.txt` | thư viện chạy / thư viện phát triển |
| `pyproject.toml` | cấu hình pytest (bỏ qua test chậm `-m slow` mặc định) |
| `.gitignore` | `data/`, `outputs/`, model `.gguf`, `.zip` không bao giờ lên repo |
| `.gitattributes` | ép xuống dòng kiểu Linux (script trong Docker cần) |
| `.dockerignore` | chỉ chép `datamate/`, `assets/`, `configs/`, `docker/`, `tools/` vào image |

### `datamate/`: mã nguồn của hệ (chạy khi dự đoán)
Luồng một câu hỏi: đọc file → map → LLM đọc câu thành plan → đọc kỳ, nối tên → hàm tính → cổng → ghi đáp án.

| Thư mục / file | Làm gì |
|---|---|
| `predict.py` | **điểm vào**: `python -m datamate.predict --data … --out …` |
| `pipeline.py` | điều phối: chuẩn bị từng cửa hàng một lần, rồi xử lý từng câu; ghi log mỗi câu |
| `loader/` | đọc csv, xlsx, sqlite; tìm dòng tiêu đề, bỏ dòng tổng, hiểu ngày và tiền ghi nhiều kiểu |
| `mapping/` | đưa bảng của mỗi shop về bảng chuẩn. `transfer.py`: chuyển từ 30 mapping mẫu train (khớp tên cột, hoặc LLM ghép theo nghĩa). `from_readme.py`: dựng từ README, bổ sung cột và bảng phụ còn thiếu. `side_books.py`: sổ phụ của cửa hàng điện thoại. `build.py`: dựng bảng chuẩn và 10 phép kiểm |
| `contracts/` | định nghĩa dữ liệu chung: `plan.py` (plan JSON LLM viết), `canonical.py` (các bảng chuẩn), `mapping.py`, `results.py`, `schemas/` (JSON schema xuất ra) |
| `llm/` | gọi llama-server (JSON ép theo schema, temperature 0) và cache |
| `nlu/` | đọc câu hỏi. `prompt.py`: prompt và chọn ví dụ. `grounding.py`: cổng căn cứ và các luật viết lại plan. `repair.py`: sửa JSON sai khuôn. `linking.py`: nối tên trong câu với dữ liệu. `baseline.py`: bộ đọc luật đơn giản (không LLM). `twins.py`: tìm câu train tương tự |
| `temporal/` | biến kỳ trong plan thành ngày cụ thể (tháng, quý, tuần, Tết, "đến hết ngày X"…) |
| `metrics/` | **hàm tính đúng rulebook**: `sales.py` (doanh thu, đơn, xếp hạng, tỉ trọng…), `stock.py` (nhập, giá, tồn), `debt.py` (công nợ), `lots.py` (lô, hạn dùng, hết hàng), `industry.py` (ngành riêng), `registry.py` (bảng tra hàm theo loại câu), `frames.py` (bảng trung gian, bộ lọc) |
| `verify/`, `decide/` | thu tín hiệu và quyết định trả lời / bỏ trống / "không trả lời được" |
| `rules/` | đọc rulebook, so với bản luật train đã kiểm (phát hiện luật đổi) |
| `formatter/`, `output/` | định dạng đáp án theo §9; ghi `submission.jsonl` và log; canh giờ |
| `diagnose.py` | khi đọc lại một lượt: ghi dòng code nơi hàm trả "không có số" |
| `eval/` | **chỉ dùng lúc phát triển**: chấm điểm trên train (`run.py`, `scorer.py`), đo mapping (`mapping.py`), kiểm định dạng (`validate.py`) |
| `codegen/` | chỗ để dành cho LLM viết code dự phòng; hiện chưa dùng |

### `assets/`: dữ liệu hệ đọc lúc chạy (dựng từ train)
| Đường dẫn | Là gì |
|---|---|
| `assets/plans/verified_train.jsonl` | 2390 plan train đã kiểm đúng: kho ví dụ cho prompt và cổng câu anh em |
| `assets/plans/templates_train.json`, `examples_v0.jsonl`… | mẫu câu và ví dụ tay |
| `assets/mappings/train/biz_*.json` | mapping tay của một số cửa hàng train: mẫu để chuyển sang shop mới |
| `assets/mappings/signatures.json` | dấu hiệu nhận dạng file của từng mẫu |
| `assets/linking/synonyms.json` | từ đồng nghĩa: "ck" = chuyển khoản, "tm" = tiền mặt… |
| `assets/rules/reference_rules.json` | bản luật đã kiểm để so khi rulebook đổi |

### `configs/`
`default.json`: ngân sách thời gian (5,5 giờ), ngưỡng cổng câu anh em, bật / tắt log.

### `tools/`: công cụ phát triển (không chạy khi dự đoán)
| File | Làm gì |
|---|---|
| `eval_cached.py` | đo 3000 câu train bằng cache, không cần server |
| `replay_run.py` | đọc lại một lượt public từ log bằng code mới, không gọi LLM |
| `compare_runs.py` | so hai lượt từng câu, đếm theo shop và hàm |
| `run_stats.py` | đếm câu trống theo bước và theo lý do |
| `run_shops.py` | chạy LLM cho vài cửa hàng public |
| `ablate.py`, `ablate_groups.py` | dựng bài nộp chẩn đoán bỏ trống một nhóm |
| `train_blanks.py` | liệt kê câu train trống theo chỗ dừng |
| `show_business.py` | xem nhanh dữ liệu của một cửa hàng |
| `mapping_signatures.py` | dựng lại `assets/mappings/signatures.json` |
| `kaggle_k1.py`, `kaggle_pack.py`, `read_plans_shard.py`, `variant_eval.py` | thí nghiệm so model (14B trên Kaggle) |
| `research/` | phân tích bộ câu hỏi (mẫu câu, thực thể) |

### `tests/`
Mỗi file kiểm một phần, tên file nói phần đó: `test_metrics_*.py` (hàm tính), `test_mapping_*.py` (mapping), `test_plan_*.py` (đọc câu và luật viết lại), `test_lots.py`, `test_no_id_logic.py` (**chặn id cửa hàng hay id câu trong code**)… Mọi bản sửa phải kèm test.

### `docker/`
`Dockerfile` (image chạy offline: llama.cpp + model + code), `predict.sh` (điểm vào của image), `README.md` (ghi chú build và nộp), `README_IMAGE.md` (README trong image), `models/` (đặt file `.gguf` khi build, không commit).

### `docs/`: tài liệu
| File | Đọc khi |
|---|---|
| `PHAN_VIEC_NHOM.md` | **đọc đầu tiên**: 5 task, câu hỏi tự nghiên cứu, mốc |
| `HAN_CHE_VA_CAI_THIEN.md` | lịch sử mọi bản sửa (N1–N79): vấn đề, căn cứ, kết quả |
| `CAN_XAC_MINH.md` | các lượt nộp, điểm, cách đọc bài nộp chẩn đoán |
| `KE_HOACH_DataMate.md` | kế hoạch tổng, phương án dự phòng |
| `architecture/`, `contracts.md` | sơ đồ kiến trúc, mô tả hợp đồng dữ liệu |

### Không có trong repo (tự tạo hoặc nhận riêng)
| Đường dẫn | Từ đâu |
|---|---|
| `data/` | tải từ BTC (bước 4) |
| `local/` | ghi chép cá nhân, bàn giao giữa các phiên làm việc: chỉ nằm trên máy mỗi người |
| `outputs/` | gói của trưởng nhóm (bước 5); mọi lượt chạy của bạn cũng ghi vào đây |
| `.venv/` | tạo ở bước 3 |
| model `.gguf` | tải ở bước 7 |

---

## Luật bắt buộc khi sửa code
- Không có id cửa hàng (`dev_…`, `biz_…`) hay id câu trong code, kể cả comment.
- Không gán nhãn hay viết đáp án tay cho câu public. Mọi sửa là quy tắc chung.
- Train phải giữ **0 sai** và không giảm câu đúng (`tools/eval_cached.py`, `CACHE MISSES: 0`).
- Mỗi sửa có test và một mục trong `docs/HAN_CHE_VA_CAI_THIEN.md`. Làm trên nhánh riêng, mở PR.
- Không gọi API ngoài khi dự đoán; không tải file lớn qua mạng 4G.

## Lỗi hay gặp
| Hiện tượng | Cách xử lý |
|---|---|
| Chữ tiếng Việt in ra thành ký tự lạ (Windows) | `$env:PYTHONIOENCODING = "utf-8"` |
| `No module named datamate` | chạy lệnh **từ thư mục gốc repo**, bằng Python của `.venv` |
| `FileNotFoundError: data/train/questions.jsonl` | sai cấu trúc `data/`, xem bước 4 |
| `eval_cached` báo `CACHE MISSES` > 0 | thiếu gói `outputs` (bước 5), hoặc code đã đổi prompt của câu train |
| `không gọi được http://127.0.0.1:8091/health` | server chưa mở, hoặc đang nạp model (chờ khoảng 30 giây) |
| Train khác 2747 / 0 | báo trưởng nhóm: máy hoặc dữ liệu khác, đừng sửa code trước |
