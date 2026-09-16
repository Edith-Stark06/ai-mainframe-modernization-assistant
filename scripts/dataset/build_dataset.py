"""
Build the Phase 6 training dataset (#118).

    python -m scripts.dataset.build_dataset [--out DIR] [--seed N] [--work DIR]

Runs the deterministic Phase 1–5 analysis over the controlled corpus,
emits versioned JSONL, validates it (schema + security + duplicates),
splits it (grouped by source program) and checks for split leakage.

Writes, under ``--out`` (default ``data/dataset/<DATASET_VERSION>/``):

    all.jsonl            every example
    train.jsonl
    validation.jsonl
    test.jsonl
    manifest.json        build stats + versions
    split_manifest.json  source -> split assignment
    validation_report.json
    leakage_report.json

Exit code is non-zero if validation errors or leakage errors are found.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from app.dataset.builder import DatasetBuilder
from app.dataset.corpus import (
    REPO_ROOT,
    load_phase6_corpus,
    load_training_corpus,
)
from app.dataset.io import write_jsonl
from app.dataset.leakage import detect_leakage
from app.dataset.splitting import split_dataset
from app.dataset.validation import validate_dataset
from app.dataset.version import DATASET_VERSION, DATASET_VERSION_V2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-version",
        default=DATASET_VERSION,
        help=f"dataset version to stamp (default {DATASET_VERSION})",
    )
    parser.add_argument(
        "--corpus",
        choices=["full", "training"],
        default="full",
        help=(
            "'full' = the original 20-source corpus (phase6-v1, overlaps the "
            "benchmark); 'training' = the benchmark-disjoint corpus (phase6-v2)"
        ),
    )
    parser.add_argument(
        "--out",
        default="",
        help="output directory (default: data/dataset/<dataset-version>/)",
    )
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument(
        "--work",
        default="",
        help="analysis work dir (default: a fresh temp dir)",
    )
    parser.add_argument(
        "--created-at",
        default="",
        help="fixed ISO timestamp for reproducible manifests (default: none)",
    )
    args = parser.parse_args(argv)

    dataset_version = args.dataset_version
    if args.corpus == "training" and dataset_version == DATASET_VERSION:
        dataset_version = DATASET_VERSION_V2

    out = Path(args.out or (REPO_ROOT / "data" / "dataset" / dataset_version))
    out.mkdir(parents=True, exist_ok=True)
    work = args.work or tempfile.mkdtemp(prefix="phase6-build-")

    if args.corpus == "training":
        corpus = load_training_corpus()
    else:
        corpus = load_phase6_corpus()
    print(
        f"corpus: {len(corpus)} source program(s) "
        f"({args.corpus}) -> dataset_version={dataset_version}"
    )

    builder = DatasetBuilder(
        work_dir=work,
        created_at=(args.created_at or None),
        dataset_version=dataset_version,
    )
    result = builder.build(corpus)
    print(f"built {len(result.examples)} example(s), " f"skipped {len(result.skipped)}")

    write_jsonl(out / "all.jsonl", result.examples)
    (out / "manifest.json").write_text(
        json.dumps(result.manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    report = validate_dataset(out / "all.jsonl", expected_version=dataset_version)
    (out / "validation_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"validation: ok={report.ok} errors={report.error_count} "
        f"warnings={report.warning_count}"
    )

    split = split_dataset(result.examples, seed=args.seed)
    write_jsonl(out / "train.jsonl", split.train)
    write_jsonl(out / "validation.jsonl", split.validation)
    write_jsonl(out / "test.jsonl", split.test)
    (out / "split_manifest.json").write_text(
        json.dumps(split.manifest(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"split: train={len(split.train)} validation={len(split.validation)} "
        f"test={len(split.test)}"
    )

    leak = detect_leakage(split.train, split.validation, split.test)
    (out / "leakage_report.json").write_text(
        json.dumps(leak.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"leakage: ok={leak.ok} errors={leak.error_count} "
        f"warnings={leak.to_dict()['warning_count']}"
    )

    ok = report.ok and leak.ok
    print("OK" if ok else "FAILED — see validation_report.json / leakage_report.json")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
