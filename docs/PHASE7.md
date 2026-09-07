# Phase 7 / #121 — Reproducible fine-tuning pipeline

#121 builds a **scientifically defensible** pipeline that can answer one
question:

> *Does fine-tuning the Phase 6 curated dataset produce a measurable
> improvement over the #120 baseline?*

It does **not** assume the answer is yes. "No" is a valid, successful
outcome as long as the pipeline proves it reproducibly.

```
data/dataset/phase6-v1/  (#118, train split)
        │  resolve + hash-check + BENCHMARK ISOLATION
        ▼
app/training/config.py      versioned TrainingConfig  (config_hash)
        ▼
app/training/pipeline.py    run_training  ──►  reports/training-runs/<run_id>/
        │                                        training_manifest.json
        │                                        resolved_config.yaml
        │                                        training_records.jsonl
        ▼
app/training/backend.py     TransformersLoRABackend (real)  |  DeterministicMockBackend (fixture)
        ▼
app/training/evaluation.py  evaluate_model  ── SAME frozen benchmark + #119/#120 metrics
        ▼
app/training/comparison.py  compare_models  ──►  IMPROVED | NO_MEANINGFUL_IMPROVEMENT
                                                 | REGRESSED | INCONCLUSIVE
        ▼
app/training/registry.py    models/registry.json   (TRAINED → VALIDATED/CANDIDATE/REJECTED → ADOPTED)
```

## Strict data separation

The #118 training dataset and the #119 benchmark are drawn from the
**same source corpus** — 17 of 20 programs are byte-identical between
`data/benchmark/benchmark-v1/examples.jsonl` and
`data/dataset/phase6-v1/all.jsonl`.

`resolve_training_data` therefore **removes every source that also
appears in the benchmark** and refuses to proceed if fewer than
`min_training_sources` (default 8) remain. On `phase6-v1` only
`fx_combined` and `fx_simple_proc` survive, so the default path raises
`BenchmarkLeakageError`. This is a **Phase 6 corpus issue to fix before
#121 can produce real evidence** (hold sources out of the benchmark, or
exclude benchmark sources from the dataset) — it is out of #121's scope.

`min_training_sources=1` is a documented *pipeline dry-run* lever used
only by the mock backend and the test suite.

## Training backend availability

Real fine-tuning needs `transformers` + `peft` + `datasets` +
`accelerate` and base-model weights (realistically a GPU). The current
environment has CPU-only `torch` and `transformers` but **not** the rest,
so `build_backend("auto")` raises `TrainingBackendUnavailableError`. The
pipeline never fabricates a model.

`DeterministicMockBackend` is a **labelled test fixture**: it writes a
checkpoint *descriptor* (no weights, carries a `NOT A REAL FINE-TUNED
MODEL` warning) so the manifest / evaluation / comparison / decision /
registry path can be exercised end to end. It is never registered as
`ADOPTED` (the registry refuses).

## Commands

```bash
# train (real backend; fails loudly if the stack/weights are absent)
python -m scripts.training.train_model --config configs/training/finetune-v1.yaml --register

# train — pipeline dry-run only, NOT a real model
python -m scripts.training.train_model --config configs/training/finetune-v1.yaml \
    --backend mock --min-training-sources 1

# evaluate a checkpoint against the frozen benchmark (#119/#120 metrics)
python -m scripts.training.evaluate_finetuned_model --run-dir reports/training-runs/<run_id> \
    --mode raw --out reports/training-runs/<run_id>/eval

# baseline vs fine-tuned + decision
python -m scripts.training.compare_models \
    --baseline reports/baseline-eval/benchmark-v1/raw \
    --candidate reports/training-runs/<run_id>/eval \
    --out reports/training-runs/<run_id>/comparison \
    --register --model-version <model_version>
```

## Reproducible vs identical weights

The pipeline guarantees a **reproducible run specification** — seed,
`dataset_manifest_hash`, `config_hash`, base model, tokenizer,
`preprocessing_version`, training-record selection/ordering, benchmark
isolation, environment snapshot, command. It does **not** claim
bit-for-bit identical floating-point weights across machines /
frameworks / hardware; `training_manifest.json → reproducibility` states
this explicitly.

## Versions

`training_pipeline_version=phase7-train-v1`,
`preprocessing_version=p7-preproc-v1`,
`decision_policy_version=p7-decision-v1`,
`registry_schema_version=p7-registry-v1`. Phase 6 constants are never
modified by #121.

## Security

No API keys, tokens or credentials are read, logged, stored in model
metadata, or committed. Nothing is uploaded. The environment snapshot in
the manifest is asserted secret-free by the test suite.
