# G7 — Docker và vận hành

*(Chi tiết build còn để trống, chờ BTC công bố Docker guideline: base image, lệnh chạy container, cấu trúc `/data` và `/result`, định dạng nộp image.)*

**Đã biết:**
- Image chứa source code, model weights, `predict.sh` và README.
- `predict.sh` đọc `/data`, ghi `/result/submission.jsonl` và `/result/logs/`.
- Container chạy không có mạng, `/data` chỉ đọc; máy chấm có 2× RTX 5090; tối đa 6 giờ.

Lệnh chạy trong container (đã có): `python -m datamate.predict --data /data --out /result`.

**Việc cần làm khi có guideline (từ T3 10/11):**
1. Dockerfile theo base image của BTC; chép **cả** `datamate/`, `configs/`, `assets/` (mục H14: thiếu `assets/` thì mọi câu bỏ trống); weights của model.
2. `predict.sh` với xuống dòng LF (đã ép bằng `.gitattributes`).
3. Chạy thử: `--network none`, `/data` gắn chỉ đọc (`:ro`), `--gpus all`; đo thời gian chạy hết bộ public và nhân 1,5 để dự phòng.
4. Chạy 2 lần, so từng câu: lệch phải ≤ 0,03 PA.
5. Quy trình nộp: `docker save` → nén → `sha256sum` → upload Google Drive → form "Solution Submission".

---

## Bản nháp đã viết (04/11, kế hoạch §11): `docker/Dockerfile`, `docker/predict.sh`, `.dockerignore`

Bản này theo mặc định trong kế hoạch (CUDA 12.8, RTX 5090). Khi BTC gửi guideline thì sửa base image, đường dẫn `/data`, `/result` và lệnh chạy cho khớp. **Không build trên laptop**: base image CUDA nặng vài GB, mà laptop dùng mạng 4G (H20). Build trên máy RTX 5090 thuê dạng **VM** (container thuê không chạy được Docker bên trong).

### Buổi GPU (10–12/11), trên VM RTX 5090, theo Docker guideline 2026 (`zac2026_DataMate_docker_guideline_final.pdf`)
```bash
# 0. máy: Ubuntu + driver NVIDIA ≥ 570 (CUDA 12.8), Docker 24 + BuildKit, nvidia-container-toolkit; ổ trống ≥ 120 GB
nvidia-smi && docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu22.04 nvidia-smi

# 1. code, dữ liệu, model
git clone https://github.com/panno1vn/ZAIC && cd ZAIC
#    data/train, data/public_test và outputs/ (bank, llm_cache_mapping, llm_cache_prod_train, log đo cuối) tải từ Drive
#    (gói dữ liệu của nhóm), giải nén đúng chỗ
pip install -U huggingface_hub
huggingface-cli download Qwen/Qwen3-8B-GGUF Qwen3-8B-Q4_K_M.gguf --local-dir docker/models
sha256sum docker/models/Qwen3-8B-Q4_K_M.gguf
git ls-remote https://huggingface.co/Qwen/Qwen3-8B-GGUF HEAD   # commit của repo model
#    → điền revision và SHA-256 vào docker/README_IMAGE.md (bảng "Model và giấy phép") TRƯỚC khi build

# 2. training_code (guideline §8) rồi build (llama.cpp chiếm phần lớn thời gian)
python3 tools/stage_training_code.py          # -> build/training_code, in số file và dung lượng
docker build --platform linux/amd64 -f docker/Dockerfile -t zaic2026_datamate_<team>:final     --build-arg MODEL_FILE=Qwen3-8B-Q4_K_M.gguf .
docker image inspect -f '{{.Os}}/{{.Architecture}} {{.Size}}' zaic2026_datamate_<team>:final
docker run --rm --network none --entrypoint "" zaic2026_datamate_<team>:final find /code -maxdepth 2

# 3. chạy đúng lệnh chấm (guideline §10): 2 GPU, không mạng, /data chỉ đọc, shm 16 GB; đo thời gian
mkdir -p /tmp/r1 /tmp/r2
time docker run --rm --gpus '"device=0,1"' --network none --shm-size=16g --entrypoint bash     -v "$PWD/data/public_test:/data:ro" -v /tmp/r1:/result zaic2026_datamate_<team>:final /code/predict.sh
python3 -m datamate.eval.validate --pred /tmp/r1/submission.jsonl --split public_test
python3 tools/compare_runs.py /tmp/r1 outputs/replay/p17_h16/submission.jsonl   # lệch ~1% là bình thường, "LỖI" = 0
head -c 600 /tmp/r1/logs/questions.jsonl   # mỗi dòng có id, answer, elapsed_ms, thinking, code, inputs, output
#    lần 2 (guideline §6: hai lượt phải ra cùng đáp án, hoặc PA train lệch ≤ 0,03)
docker run --rm --gpus '"device=0,1"' --network none --shm-size=16g --entrypoint bash     -v "$PWD/data/public_test:/data:ro" -v /tmp/r2:/result zaic2026_datamate_<team>:final /code/predict.sh
python3 tools/compare_runs.py /tmp/r2 /tmp/r1/submission.jsonl

# 4. đóng gói (guideline §11): .tar.gz, MD5, kích thước .tar chưa nén (≤ 100 GB)
set -o pipefail
docker save zaic2026_datamate_<team>:final | pigz -p 8 > zaic2026_datamate_<team>.tar.gz
pigz -dc zaic2026_datamate_<team>.tar.gz | wc -c          # gửi BTC số byte này
md5sum zaic2026_datamate_<team>.tar.gz > zaic2026_datamate_<team>.tar.gz.md5
rclone copy zaic2026_datamate_<team>.tar.gz gdrive:ZAIC/ && rclone copy zaic2026_datamate_<team>.tar.gz.md5 gdrive:ZAIC/
#    tải lại từ link trên một máy khác và chạy md5sum -c trước khi gửi link; không đổi tên file sau khi tạo .md5
```

### Những gì image chứa
- llama.cpp `llama-server` build cho sm_120 (Blackwell), tag `b12064` như trên laptop.
- Model GGUF ở `/code/models/model.gguf` (Qwen3-8B Q4_K_M, Apache 2.0; K1 ngày 06/11 chốt 8B: 14B không hơn rõ, chậm gấp đôi, xem HAN_CHE N49).
- `datamate/`, `assets/` (H14: kho ví dụ, từ điển nối tên, luật tham chiếu, mapping mẫu), `configs/`.
- `tools/` (thể lệ đòi mã "huấn luyện": các công cụ dựng lại `assets/` từ train) và `/code/README.md` (bản `docker/README_IMAGE.md`: cách chạy, phương pháp, tài sản dựng từ train, giấy phép).
- `predict.sh`: mở server, chạy `datamate.predict` trên `$DATA_DIR`, ghi `$OUT_DIR/submission.jsonl`. Server không lên thì chạy bộ đọc luật (baseline), vẫn có file nộp.

### Đối chiếu với hướng dẫn Docker năm 2025 (đề RoadBuddy)
Nguồn: [Scribd](https://www.scribd.com/document/950068255/zac2025-roadbuddy-docker-guideline). Trang chính bị khoá; nội dung lấy từ bản nhúng của Scribd, chỉ có phần tóm lược.
- **Máy chấm 2025:** driver 535.86.10, CUDA 12.2; base image mẫu `nvidia/cuda:12.2.0-devel-ubuntu22.04`. Năm 2026 máy chấm là RTX 5090, cần CUDA ≥ 12.8 và driver ≥ 570 (driver 535 không chạy được 5090), nên giữ CUDA 12.8. Khi có guideline 2026 thì đối chiếu lại phiên bản driver.
- **`predict.sh`** đọc `/data`, ghi `/result/submission.*`: đã khớp.
- **In ra màn hình thời gian nạp model và thời gian dự đoán:** đã thêm vào `predict.sh` (`Model load time`, `Prediction time`, `Total time`).
- **Nộp kèm `predict_notebook.ipynb`** để BTC đo thời gian: đã soạn `docker/predict_notebook.ipynb` (làm đúng các bước của `predict.sh`, in từng mốc thời gian), chép vào `/app`. Image không cài Jupyter; nếu BTC 2026 đòi chạy notebook trong container thì thêm `jupyter` vào image.
- **Cách làm năm 2025:** dựng container, chép code và model, `commit`, `save`. Mình dùng Dockerfile, ra cùng một image nhưng dựng lại được.
- **Hướng dẫn 2025 không nói:** lệnh `docker run` của BTC, giới hạn thời gian, dung lượng, mạng, cách nộp. Vẫn theo thể lệ 2026: không mạng, ≤ 6 giờ, nộp link Drive và checksum.

### Còn chờ
- Guideline BTC: base image bắt buộc, cấu trúc `/data` (`find_split_dir` nhận cả thư mục split lẫn thư mục cha), lệnh chạy, có cần ghi log hay không.
- Có dùng 2 card (2 server, chia cửa hàng) để chạy nhanh hơn hay không: chỉ cần nếu private đông câu.
