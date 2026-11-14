# DataMate: training code and data (`/code/training_code/`)

**No model was trained or fine-tuned.** The base model Qwen3-8B (GGUF Q4_K_M, Apache-2.0) is used as released, with
greedy decoding (temperature 0, top_k 1, fixed seed, thinking off). What is built from the training data is the
content of `/code/assets/`, which the inference code reads; this folder holds what is needed to rebuild and verify it.

*(Tiếng Việt: không huấn luyện hay tinh chỉnh model nào. Phần dựng từ dữ liệu train là `assets/`; thư mục này chứa
mã, dữ liệu, đầu ra LLM và log để dựng lại và kiểm tra.)*

## Contents

| Path | What |
|---|---|
| `data/train/` | the train split as released: `questions.jsonl` (3000), `answers.jsonl`, `rulebook.md`, `calendar.csv`, `data/<business_id>/` (30 shops) |
| `data/generated/llm_plans.jsonl` | the plan the local LLM wrote for each train question (source of `assets/plans/verified_train.jsonl`) |
| `data/generated/llm_cache_mapping.jsonl` | the local LLM's column-matching answers for the train shops |
| `data/generated/llm_cache_prod_train.jsonl` | the local LLM's answers on the production-like train run |
| `data_generation/tools/`, `data_generation/datamate/eval/` | the build and evaluation scripts |
| `configs/` | run settings (time budget, twin threshold) |
| `logs/` | evaluation of the final code on train (`eval_cached_n201.log`, `prod_train_n201.log`), building of the plan bank (`build_bank_v3.log`) |
| `requirements.txt` | pinned dependencies (the same as inference, installed in the image) |
| `data_manifest.json` | every file with its size and SHA-256, dataset counts, base model source |

No validation split was held out: development measured the pipeline on train (rules are checked against the train
answers) and on self-made shops (`tools/synth_shops*.py`). Every data file here is built from train alone, except the
reference rule texts (`assets/rules/reference_rules.json`), which also hold the public rulebook's text. During
development the pipeline was also run on the public test set and its inputs (files, READMEs, rulebook, question
wording) were read to find where files, columns or questions were misread; code written after such a finding says
"public" in its comment. Nothing in this image was built or tuned with answers to public questions; the only public
score known is the leaderboard total. The private test set has not been seen.

## Assets and how to rebuild them

Run from `/code` (the image's working folder), with the train split at `data/train` (`ln -s /code/training_code/data
data`). Steps that call the LLM need `llama-server` on port 8091 (`/code/llama/llama-server -m /code/models/model.gguf
--jinja -ngl 99 -c 8192 --parallel 1 --port 8091`).

| Asset | What | Command |
|---|---|---|
| `assets/plans/verified_train.jsonl` | plans of train questions verified against the train answers (prompt examples) | `python -m datamate.eval.build_bank --llm-url http://127.0.0.1:8091` (≈3000 LLM calls; with `data/generated/llm_plans.jsonl` in `outputs/bank/` it only re-verifies) |
| `assets/plans/templates_train.json` | question templates of train | same command |
| `assets/mappings/train/*.json` | hand-written mappings of 10 train shops (examples for mapping by transfer) | written by hand from each shop's README; column signatures: `python tools/mapping_signatures.py` |
| `assets/linking/synonyms.json` | spellings and abbreviations for name linking | written by hand from train questions |
| `assets/rules/reference_rules.json` | reference rule texts | `python -m datamate.rules build data/train/rulebook.md <public rulebook>` |

Verification on train with the final code: `python tools/eval_cached.py` (no server; reads
`data/generated/llm_cache_mapping.jsonl` and `llm_plans.jsonl`): 3000 questions, 2981 right, 0 wrong, 19 blank (`eval_cached_n201.log`).
`python tools/prod_train.py 2 out.jsonl` (server; as the run reads a shop it never saw): 1500 questions, 1494 right,
0 wrong, 6 blank (`prod_train_n201.log`, code of 14/11).

## Hardware, runtime, nondeterminism

- Built on a laptop (NVIDIA RTX-class GPU, llama.cpp b12064): `build_bank` ≈ 1.5 h, `prod_train` ≈ 1 h without cache.
- The LLM decodes greedily with a fixed seed and one slot (`--parallel 1`); a re-run gives the same output except for
  rare floating-point differences between builds or GPUs (about 1% of questions between two full runs).
- The generated files above are the outputs actually used; a re-generation may differ slightly for that reason.
