#!/usr/bin/env bash
# Trên VM thuê (Vast.ai, template "Ubuntu 22.04 VM", RTX 5090): kiểm máy, tải từ Drive, tải model, build image,
# chạy public 2 lượt đúng lệnh chấm, so kết quả. Đã chạy thật 11/11/2026 (bản v1, Test Solution qua).
#   Laptop: rclone copy outputs/zaic_<TAG>.bundle gdrive:ZAIC_docker   (git bundle create outputs/zaic_<TAG>.bundle <TAG>)
#   VM (trong tmux):  TEAM=band TAG=docker-v2 bash ~/work/vm_build.sh 2>&1 | tee ~/work/build.log
# Biến: TEAM (tên đội, chữ thường), TAG (tag git trong bundle), REF (submission tham chiếu để so lượt 1).
set -euo pipefail
: "${TEAM:?Đặt tên đội trước: TEAM=<ten_doi> TAG=<tag> bash vm_build.sh}"
: "${TAG:?Đặt tag git: TAG=docker-v2}"
REF="${REF:-outputs/replay/run11_s71/submission.jsonl}"
[[ "$TEAM" =~ ^[a-z0-9_.-]+$ ]] || { echo "TEAM chỉ gồm chữ thường, số, _ . -"; exit 1; }
IMG="zaic2026_datamate_${TEAM}:final"
EXPECT_SHA=d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785   # Qwen3-8B-Q4_K_M dùng cho mọi phép đo
SUDO=""; [ "$(id -u)" = 0 ] || SUDO=sudo
W=~/work; mkdir -p "$W"; cd "$W"
step() { echo; echo "===== $(date +%H:%M:%S) $* ====="; }

step "0. Tắt tự cập nhật (11/11: unattended-upgrades nâng driver NVIDIA giữa chừng -> driver/library mismatch)"
$SUDO systemctl stop apt-daily.timer apt-daily-upgrade.timer unattended-upgrades 2>/dev/null || true
$SUDO systemctl disable apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
command -v nvidia-smi >/dev/null || { echo "Không có driver NVIDIA: máy này không dùng được"; exit 1; }
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv
df -h / | tail -1
command -v docker >/dev/null || curl -fsSL https://get.docker.com | $SUDO sh
if ! $SUDO docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu22.04 nvidia-smi -L; then
  step "0b. Cài nvidia-container-toolkit"
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | $SUDO gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    | $SUDO tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
  $SUDO apt-get update -qq && $SUDO apt-get install -y -qq nvidia-container-toolkit
  $SUDO nvidia-ctk runtime configure --runtime=docker && $SUDO systemctl restart docker
  $SUDO docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu22.04 nvidia-smi -L
fi
DOCKER="$SUDO docker"

step "1. Cài gói"
export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update -qq && $SUDO apt-get install -y -qq unzip pigz python3-venv python3-pip git curl >/dev/null
command -v rclone >/dev/null || curl -fsSL https://rclone.org/install.sh | $SUDO bash

step "2. Tải code + dữ liệu từ Drive"
rclone copy gdrive:ZAIC_docker . --include "*.zip" --include "zaic_${TAG}.bundle" --drive-chunk-size 256M -P
rm -rf ZAIC && git clone -q -b "$TAG" "zaic_${TAG}.bundle" ZAIC && cd ZAIC
git log --oneline -1
mkdir -p data && unzip -q -o ../train.zip -d data && unzip -q -o ../public_test.zip -d data && unzip -q -o ../docker_pack.zip
ls data/train/questions.jsonl data/public_test/questions.jsonl "$REF"
python3 -m venv .venv && . .venv/bin/activate
pip install -q -r requirements.txt huggingface_hub

step "3. Tải model, kiểm SHA-256, điền README_IMAGE"
mkdir -p docker/models
REV=$(python3 - <<'PY'
from huggingface_hub import HfApi, hf_hub_download
rev = HfApi().model_info("Qwen/Qwen3-8B-GGUF").sha
hf_hub_download("Qwen/Qwen3-8B-GGUF", "Qwen3-8B-Q4_K_M.gguf", revision=rev, local_dir="docker/models")
print(rev)
PY
)
SHA=$(sha256sum docker/models/Qwen3-8B-Q4_K_M.gguf | cut -d' ' -f1)
echo "revision=$REV"; echo "sha256=$SHA"
[ "$SHA" = "$EXPECT_SHA" ] || { echo "SHA-256 KHÁC model dùng để đo: dừng, báo lại"; exit 1; }
sed -i "s/<ghi commit khi tải>/${REV}/; s/<ghi khi tải>/${SHA}/" docker/README_IMAGE.md
grep -c "$SHA" docker/README_IMAGE.md

step "4. training_code + build image"
python3 tools/stage_training_code.py
time $DOCKER build --platform linux/amd64 -f docker/Dockerfile -t "$IMG" --build-arg MODEL_FILE=Qwen3-8B-Q4_K_M.gguf .
$DOCKER image inspect -f '{{.Os}}/{{.Architecture}} {{.Size}}' "$IMG"
$DOCKER run --rm --network none --entrypoint "" "$IMG" ls /code /code/models /code/llama

run_public() {  # $1 = thư mục kết quả, $2 = GPU ("0,1" như lệnh chấm; "0" trên máy thuê 1 GPU)
  rm -rf "$1" && mkdir -p "$1"
  time $DOCKER run --rm --gpus "\"device=$2\"" --network none --shm-size=16g --entrypoint bash \
    -v "$PWD/data/public_test:/data:ro" -v "$1:/result" "$IMG" /code/predict.sh
}
step "5a. Chạy public lượt 1 (đúng lệnh chấm)"
GPUS="0,1"; [ "$(nvidia-smi -L | wc -l)" -ge 2 ] || { GPUS="0"; echo "máy 1 GPU: dùng device=0"; }
run_public "$W/r1" "$GPUS"
python3 -m datamate.eval.validate --pred "$W/r1/submission.jsonl" --split public_test
echo "số dòng: $(grep -c . "$W/r1/submission.jsonl")"
python3 tools/compare_runs.py "$W/r1" "$REF" | tee "$W/compare_r1.txt"

step "5b. Chạy public lượt 2"
run_public "$W/r2" "$GPUS"
python3 tools/compare_runs.py "$W/r2" "$W/r1/submission.jsonl" | tee "$W/compare_r2.txt"

step "XONG. Tóm tắt"
grep -h -E "Model load time|Prediction time|Total time" "$W/build.log" 2>/dev/null || true
head -3 "$W/compare_r1.txt"; head -2 "$W/compare_r2.txt"
echo "Đạt khi: validate không lỗi, 1000 dòng, LỖI = 0, khác so với REF ~≤ 1%, r2 giống r1. Đạt thì chạy vm_pack.sh"
