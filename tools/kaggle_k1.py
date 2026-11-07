"""K1 on Kaggle (GPU T4 x2, plan §11): does Qwen3-14B read train questions better than Qwen3-8B?

Runs inside a Kaggle notebook, from the unpacked code at /kaggle/working/ZAIC with the train data at data/train:
  1. build llama.cpp with CUDA for the T4 (sm_75);
  2. download Qwen3-8B and Qwen3-14B (Q4_K_M GGUF) from Hugging Face;
  3. K3 (123 hand plans) with 8B on GPU 0 and 14B on GPU 1 at once;
  4. 14B reads the 3000 train questions, half on each GPU (tools/read_plans_shard.py, a cache of its own);
  5. eval.mapping with the 14B plans; the column matching reuses the laptop's cache (outputs/llm_cache_mapping.jsonl),
     so the mappings are the laptop's and only the reading differs;
  6. everything worth keeping zipped into /kaggle/working/k1_results.zip.
Each step skips what is already done, so a rerun picks up where a session stopped.

    python tools/kaggle_k1.py            # every step
    python tools/kaggle_k1.py --steps 3 4

Development only: train data, never test data (N22).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent
LLAMA = WORK / "llama.cpp"
MODELS = WORK / "models"
OUT = ROOT / "outputs"
LOG = OUT / "kaggle_k1"
LLAMA_TAG = os.environ.get("LLAMA_TAG", "b12064")  # the laptop's build (E:\llm\llama-b12064)
MODEL_REPOS = {"8b": ("Qwen/Qwen3-8B-GGUF", "Qwen3-8B-Q4_K_M.gguf"),
               "14b": ("Qwen/Qwen3-14B-GGUF", "Qwen3-14B-Q4_K_M.gguf")}
SERVER_ARGS = ["--jinja", "-ngl", "99", "-c", "8192", "--parallel", "1", "--host", "127.0.0.1"]  # as on the laptop


def say(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.mkdir(parents=True, exist_ok=True)
    with (LOG / "steps.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd: list[str], cwd: Path | None = None, log: Path | None = None, env: dict | None = None) -> int:
    say("$ " + " ".join(map(str, cmd)))
    if log is None:
        return subprocess.call(cmd, cwd=cwd, env=env)
    with log.open("a", encoding="utf-8") as f:
        return subprocess.call(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)


# ---------------------------------------------------------------- 1. llama.cpp
def server_binary() -> Path:
    return LLAMA / "build" / "bin" / "llama-server"


def glob_dirs(pattern: str) -> list[str]:
    import glob
    return [d for d in glob.glob(pattern) if Path(d).is_dir()]


def build_llama() -> None:
    if server_binary().exists():
        say("llama-server đã có, bỏ qua bước build")
        return
    if not LLAMA.exists():
        if run(["git", "clone", "--depth", "1", "--branch", LLAMA_TAG, "https://github.com/ggml-org/llama.cpp",
                str(LLAMA)]) != 0:
            say(f"không có tag {LLAMA_TAG}: lấy bản mới nhất")
            run(["git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp", str(LLAMA)])
    log = LOG / "build_llama.log"
    import shutil
    if shutil.which("nvidia-smi") is None or subprocess.call(["nvidia-smi", "-L"]) != 0:
        raise SystemExit("KHÔNG CÓ GPU: chọn Accelerator = GPU T4 x2 (và kiểm tra GPU quota) rồi chạy lại")
    cuda = next((d for d in ("/usr/local/cuda", *sorted(glob_dirs("/usr/local/cuda-*"), reverse=True))
                 if Path(d, "bin", "nvcc").exists()), None)
    if cuda is None and shutil.which("nvcc") is None:
        raise SystemExit("có GPU nhưng không thấy nvcc (CUDA toolkit): gửi Claude output của ô nvidia-smi")
    if cuda is not None:
        os.environ["PATH"] = f"{cuda}/bin:" + os.environ["PATH"]
        os.environ["CUDAToolkit_ROOT"] = cuda
        say(f"CUDA toolkit: {cuda}")
    # Kaggle 11/2026 ships CUDA 13, whose FindCUDAToolkit misses libcuda: "CUDA::cuda_driver ... target was not
    # found", then the link fails after 25 minutes of compiling. Point CMake at the driver library (real or stub).
    import glob
    driver = next((p for pat in ("/usr/local/cuda/lib64/stubs/libcuda.so",
                                 "/usr/local/cuda/targets/x86_64-linux/lib/stubs/libcuda.so",
                                 "/usr/lib/x86_64-linux-gnu/libcuda.so", "/usr/lib/x86_64-linux-gnu/libcuda.so.1",
                                 "/usr/local/nvidia/lib64/libcuda.so.1", "/usr/lib64-nvidia/libcuda.so.1",
                                 "/usr/local/cuda*/**/libcuda.so")
                   for p in sorted(glob.glob(pat, recursive=True))), None)
    say(f"libcuda: {driver}")
    extra = [f"-DCUDA_cuda_driver_LIBRARY={driver}"] if driver else []
    if run(["cmake", "-B", "build", "-DGGML_CUDA=ON", "-DCMAKE_CUDA_ARCHITECTURES=75", "-DLLAMA_CURL=OFF",
            "-DCMAKE_BUILD_TYPE=Release", *extra], cwd=LLAMA, log=log) != 0 or "CMake Error" in log.read_text(
            encoding="utf-8", errors="replace"):
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
        say("cmake cấu hình hỏng:\n" + "\n".join(tail))
        raise SystemExit(f"cmake cấu hình hỏng, xem {log}")
    run(["cmake", "--build", "build", "--target", "llama-server", "-j", str(os.cpu_count() or 4)], cwd=LLAMA, log=log)
    if not server_binary().exists():
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-60:] if log.exists() else []
        say("60 dòng cuối của log build:\n" + "\n".join(tail))
        raise SystemExit(f"build llama-server hỏng, xem {log}")
    say("build llama-server xong")


# ---------------------------------------------------------------- 2. models
def model_path(name: str) -> Path:
    return MODELS / MODEL_REPOS[name][1]


def download_models() -> None:
    from huggingface_hub import hf_hub_download, list_repo_files
    MODELS.mkdir(parents=True, exist_ok=True)
    for name, (repo, file) in MODEL_REPOS.items():
        if model_path(name).exists():
            continue
        files = list_repo_files(repo)
        if file not in files:  # the repo names its files another way: the one Q4_K_M
            hits = [f for f in files if f.endswith(".gguf") and "Q4_K_M" in f]
            if len(hits) != 1:
                raise SystemExit(f"{repo}: không tìm thấy đúng một file Q4_K_M ({hits})")
            file = hits[0]
        say(f"tải {repo}/{file}")
        got = Path(hf_hub_download(repo, file, local_dir=MODELS))
        if got != model_path(name):
            got.rename(model_path(name))
    say("model đã đủ: " + ", ".join(f"{n} {model_path(n).stat().st_size / 1e9:.1f} GB" for n in MODEL_REPOS))


# ---------------------------------------------------------------- servers
SERVERS: dict[int, subprocess.Popen] = {}


def start_server(name: str, gpu: int, port: int) -> str:
    stop_server(port)
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu)}
    log = (LOG / f"server_{port}_{name}.log").open("a", encoding="utf-8")
    SERVERS[port] = subprocess.Popen([str(server_binary()), "-m", str(model_path(name)), "--port", str(port),
                                      *SERVER_ARGS], env=env, stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    for _ in range(180):
        try:
            with urllib.request.urlopen(url + "/health", timeout=5) as r:
                if json.loads(r.read()).get("status") == "ok":
                    say(f"server {name} sẵn sàng trên GPU {gpu}, cổng {port}")
                    return url
        except Exception:
            pass
        if SERVERS[port].poll() is not None:
            raise SystemExit(f"server {name} dừng lúc khởi động, xem {log.name}")
        time.sleep(5)
    raise SystemExit(f"server {name} không lên sau 15 phút")


def stop_server(port: int) -> None:
    p = SERVERS.pop(port, None)
    if p is not None and p.poll() is None:
        p.terminate()
        p.wait(timeout=60)


# ---------------------------------------------------------------- 3. K3
def k3() -> None:
    outs = {name: OUT / "k3" / f"qwen3-{name}-q4-t4.jsonl" for name in MODEL_REPOS}
    if all(p.exists() for p in outs.values()):
        say("K3 đã có, bỏ qua")
        return
    urls = {"8b": start_server("8b", 0, 8091), "14b": start_server("14b", 1, 8092)}
    procs = {}
    for name, url in urls.items():
        log = (LOG / f"k3_{name}.log").open("a", encoding="utf-8")
        procs[name] = subprocess.Popen([sys.executable, "-m", "datamate.eval.k3", "--base-url", url, "--timeout",
                                        "180", "--out", str(outs[name])], cwd=ROOT, stdout=log,
                                       stderr=subprocess.STDOUT)
    for name, p in procs.items():
        p.wait()
        tail = (LOG / f"k3_{name}.log").read_text(encoding="utf-8").splitlines()[-12:]
        say(f"K3 {name}:\n" + "\n".join(tail))


# ---------------------------------------------------------------- 4. 14B reads the train questions
def read_train() -> None:
    plans = OUT / "bank" / "llm_plans.jsonl"
    shards = [OUT / "bank" / f"shard{i}_14b.jsonl" for i in (0, 1)]
    urls = [start_server("14b", 0, 8091), start_server("14b", 1, 8092)]
    procs = []
    for i, url in enumerate(urls):
        log = (LOG / f"read_shard{i}.log").open("a", encoding="utf-8")
        procs.append(subprocess.Popen([sys.executable, "tools/read_plans_shard.py", "--llm-url", url, "--shard",
                                       str(i), "--of", "2", "--out", str(shards[i]), "--cache",
                                       str(OUT / f"llm_cache_14b_{i}.jsonl")], cwd=ROOT, stdout=log,
                                      stderr=subprocess.STDOUT))
    for p in procs:
        p.wait()
    rows = [x for s in shards for x in s.read_text(encoding="utf-8").splitlines() if x.strip()]
    if plans.exists() and not (OUT / "bank" / "llm_plans.8b_laptop.jsonl").exists():
        shutil.copy(plans, OUT / "bank" / "llm_plans.8b_laptop.jsonl")
    plans.write_text("\n".join(rows) + "\n", encoding="utf-8")
    none = sum(json.loads(x)["plan"] is None for x in rows)
    say(f"14B đọc xong {len(rows)} câu; không ra plan: {none}")


# ---------------------------------------------------------------- 5. scores
def evaluate() -> None:
    cache = OUT / "llm_cache_mapping.jsonl"
    before = sum(1 for _ in cache.open(encoding="utf-8")) if cache.exists() else 0
    url = start_server("14b", 0, 8091)  # only for a column match the laptop cache lacks (counted below)
    run([sys.executable, "-m", "datamate.eval.mapping", "--llm-url", url, "--llm-cache", str(cache)], cwd=ROOT,
        log=LOG / "eval_mapping_14b.log", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    after = sum(1 for _ in cache.open(encoding="utf-8")) if cache.exists() else 0
    tail = (LOG / "eval_mapping_14b.log").read_text(encoding="utf-8").splitlines()
    summary = next((x for x in tail if x.startswith("3000 câu")), "?")
    say(f"eval.mapping với plan 14B: {summary}")
    say(f"ghép cột theo nghĩa phải gọi LLM mới: {after - before} lần (0 = mapping giống hệt laptop)")


# ---------------------------------------------------------------- 6. results
def pack() -> None:
    dest = WORK / "k1_results.zip"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in [*(OUT / "k3").glob("*.jsonl"), *(OUT / "bank").glob("*.jsonl"), *LOG.glob("*.log")]:
            z.write(p, p.relative_to(ROOT))
    say(f"kết quả: {dest} ({dest.stat().st_size / 1e6:.1f} MB)")


STEPS = {1: build_llama, 2: download_models, 3: k3, 4: read_train, 5: evaluate, 6: pack}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--steps", type=int, nargs="*", default=list(STEPS))
    args = ap.parse_args(argv)
    if not (ROOT / "data" / "train" / "questions.jsonl").exists():
        raise SystemExit(f"thiếu {ROOT / 'data' / 'train'}: giải nén dữ liệu train vào đó trước")
    t0 = time.time()
    try:
        for s in args.steps:
            say(f"=== bước {s}: {STEPS[s].__name__}")
            STEPS[s]()
    finally:
        for port in list(SERVERS):
            stop_server(port)
        say(f"tổng thời gian {(time.time() - t0) / 60:.0f} phút")
    return 0


if __name__ == "__main__":
    sys.exit(main())
