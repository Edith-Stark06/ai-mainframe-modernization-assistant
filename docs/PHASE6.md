# Phase 6 — Model Training Preparation (#118 / #119 / #120)

Phase 6 establishes a **dataset → benchmark → baseline evaluation**
pipeline so we can answer, with evidence:

> *How well does a baseline foundation model perform on our modernization
> tasks, and which capabilities actually need model adaptation?*

**No model was trained or fine-tuned.** Phase 6 ends before #121.

## Layers (kept physically separate)

```
controlled source corpus  (data/sources/phase6/ + repo fixtures, MIT)
        │
        ▼
#118  app/dataset/     ── data/dataset/phase6-v1/   (train / validation)  ──X── no training
        │                                                                   (Phase 6 stops here)
        ▼
#119  app/benchmark/   ── data/benchmark/benchmark-v1/  (FROZEN, hash-verified, NEVER training)
        │
        ▼
#120  app/evaluation/  ── reports/baseline-eval/benchmark-v1/  (raw vs analysis vs retrieval)
```

The dataset builder never touches `data/benchmark/`. The benchmark is
content-hashed; a mutation fails `load_benchmark()`.

## Commands

```bash
# #118 — build + validate + split the training dataset
python -m scripts.dataset.build_dataset --created-at 2026-09-06T00:00:00Z
python -m scripts.dataset.validate_dataset data/dataset/phase6-v1/all.jsonl --version phase6-v1

# #119 — freeze the benchmark (one-shot; --force to overwrite)
python -m scripts.benchmark.freeze_benchmark

# #120 — baseline evaluation (3 modes) + capability analysis
python -m scripts.evaluation.run_baseline_eval --provider heuristic-demo
python -m scripts.evaluation.run_baseline_eval --provider langchain --model ollama:llama3   # live
```

`heuristic-demo` is a **non-LLM deterministic stand-in** used only to
exercise the harness and produce a committed sample report. A real
baseline needs `--provider langchain` (or a recorded `--provider
scripted` script) against a live model. Live runs read credentials from
the environment; nothing is committed.

## Provenance & licensing

Every corpus program is MIT-licensed (repo fixtures + synthetic). The
Open Mainframe Project COBOL course was **not** ingested — its license
could not be verified from the build environment. See
`data/sources/phase6/SOURCES.md`.

## Versions recorded in every artifact

`dataset_version=phase6-v1`, `benchmark_version=benchmark-v1`,
`prompt_version=p6-prompt-v1`, `generator_version=phase6-gen-v1`,
`analysis_version=deterministic-analysis-phases-1-5`.
