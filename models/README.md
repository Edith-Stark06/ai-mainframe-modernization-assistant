# Model registry

`registry.json` is the lightweight lineage + status record for every
model the #121 fine-tuning pipeline produces. It starts empty — **no
model has been trained** (the current environment has no fine-tuning
backend; see `docs/PHASE7.md`).

Each entry records: `model_version`, `base_model`, `training_run_id`,
`training_config_version`, `config_hash`, `dataset_version`,
`dataset_manifest_hash`, `checkpoint`, `benchmark_evaluation`, `decision`
and `status`.

Status lifecycle:

```
TRAINED --evaluate--> VALIDATED | CANDIDATE | REJECTED --adopt--> ADOPTED
```

* `TRAINED`   — checkpoint exists, not yet evaluated.
* `VALIDATED` — evaluated; `NO_MEANINGFUL_IMPROVEMENT` or `INCONCLUSIVE`. Keep the baseline.
* `CANDIDATE` — evaluated; `IMPROVED`. Eligible for a human adoption decision.
* `REJECTED`  — evaluated; `REGRESSED`.
* `ADOPTED`   — a human explicitly promoted a `CANDIDATE` with benchmark
  evidence. **Never set automatically** by training or evaluation.

Per-run manifests and reports are written under
`reports/training-runs/<run_id>/` and are not committed.
