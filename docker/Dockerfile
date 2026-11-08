# ZAIC 2026 DataMate image, laid out as the Docker guideline 2026 asks (/code/predict.sh, /code/README.md,
# /code/models/, /code/training_code/). Build on the rented RTX 5090 VM, never on the laptop (4G):
#   python tools/stage_training_code.py            # -> build/training_code (needs data/train and outputs/ in place)
#   docker build --platform linux/amd64 -f docker/Dockerfile -t zaic2026_datamate_<team>:final \
#       --build-arg MODEL_FILE=Qwen3-8B-Q4_K_M.gguf .
# The model file must sit in docker/models/ at build time (downloaded on the VM, see docker/README.md).
# Base image: the guideline recommends vllm/vllm-openai and accepts alternatives that support RTX 5090 (sm_120). We run
# Qwen3-8B with llama.cpp built for sm_120 on CUDA 12.8 (what every measurement was made with); no vLLM.
# Scoring command (guideline §10): docker run --rm --gpus '"device=0,1"' --network none --shm-size=16g \
#   --entrypoint bash -v <test>:/data:ro -v <out>:/result zaic2026_datamate_<team>:final /code/predict.sh

ARG CUDA_VERSION=12.8.1

# ---------------------------------------------------------------- llama.cpp for Blackwell (RTX 5090 = sm_120)
FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu22.04 AS llama
ARG LLAMA_TAG=b12064
RUN apt-get update && apt-get install -y --no-install-recommends git cmake build-essential ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch ${LLAMA_TAG} https://github.com/ggml-org/llama.cpp /src/llama.cpp
WORKDIR /src/llama.cpp
RUN cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="120" -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build --target llama-server -j"$(nproc)" \
    && mkdir -p /opt/llama && cp build/bin/llama-server /opt/llama/ \
    && find build -name "*.so*" -exec cp -P {} /opt/llama/ \;

# ---------------------------------------------------------------- runtime
FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu22.04
ARG MODEL_FILE=Qwen3-8B-Q4_K_M.gguf
ENTRYPOINT []
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 LD_LIBRARY_PATH=/code/llama:${LD_LIBRARY_PATH}
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /code
COPY requirements.txt /code/requirements.txt
RUN pip3 install --no-cache-dir -r /code/requirements.txt
COPY --from=llama /opt/llama /code/llama
# weights apart from the code, so a code change keeps this layer cached (guideline §9)
COPY docker/models/${MODEL_FILE} /code/models/model.gguf
COPY build/training_code /code/training_code
# inference code and the assets it reads at run time (H14: example bank, linking vocabulary, rules, mappings)
COPY datamate /code/datamate
COPY assets /code/assets
COPY configs /code/configs
COPY tools /code/tools
COPY docker/README_IMAGE.md /code/README.md
COPY docker/predict.sh /code/predict.sh
RUN chmod +x /code/predict.sh
CMD ["bash", "/code/predict.sh"]
