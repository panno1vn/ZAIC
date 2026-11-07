# ZAIC 2026 DataMate: draft image (plan §11). Build on the rented RTX 5090 VM, never on the laptop (4G, H20):
#   docker build -f docker/Dockerfile -t zaic-datamate:v1 --build-arg MODEL_FILE=Qwen3-8B-Q4_K_M.gguf .
# The model file must sit in docker/models/ at build time (downloaded on the VM, see docker/README.md).
# Runs offline: the model, llama.cpp and every Python package are inside the image. Adjust to the BTC guideline
# (base image, paths, command) when it comes.

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
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 \
    LD_LIBRARY_PATH=/opt/llama:${LD_LIBRARY_PATH} MODEL=/models/model.gguf DATA_DIR=/data OUT_DIR=/result
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt
COPY --from=llama /opt/llama /opt/llama
COPY docker/models/${MODEL_FILE} /models/model.gguf
# code and the assets it reads at run time (H14: example bank, linking vocabulary, rules, mappings)
COPY datamate /app/datamate
COPY assets /app/assets
COPY configs /app/configs
# the rules ask for the source code of training too: here, the tools that rebuild assets/ from train; and a README
COPY tools /app/tools
COPY docker/README_IMAGE.md /app/README.md
COPY docker/predict.sh /app/predict.sh
COPY docker/predict_notebook.ipynb /app/predict_notebook.ipynb
RUN chmod +x /app/predict.sh
WORKDIR /app
ENTRYPOINT ["/app/predict.sh"]
