"""Regression: the committed dataset artifacts are line-ending reproducible.

Windows (`core.autocrlf=true`) used to check `data/dataset/*/all.jsonl`
out as CRLF, so `dataset_manifest_hash` (raw bytes) disagreed with the
LF hash pinned in the training configs and `resolve_training_data`
aborted. Fixed by `.gitattributes` (`data/**/*.jsonl text eol=lf`) plus a
defensive CRLF->LF fold in the hasher.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from app.dataset.corpus import REPO_ROOT
from app.training.dataset import _canonical_bytes, dataset_dir, dataset_manifest_hash

DATA_GLOBS = ("data/**/*.jsonl", "data/**/*.json", "data/**/*.cbl", "data/**/*.md")


def _tracked_data_files() -> list[Path]:
    out: list[Path] = []
    for g in DATA_GLOBS:
        out.extend(REPO_ROOT.glob(g))
    return sorted(out)


def test_committed_data_artifacts_are_lf_in_the_working_tree() -> None:
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in _tracked_data_files()
        if b"\r\n" in p.read_bytes()
    ]
    assert not offenders, f"CRLF in committed LF-pinned artifacts: {offenders}"


def test_gitattributes_pins_dataset_and_source_artifacts() -> None:
    text = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    for rule in (
        "data/**/*.jsonl        text eol=lf",
        "data/**/*.json         text eol=lf",
        "data/**/*.cbl          text eol=lf",
        "data/**/*.md           text eol=lf",
    ):
        assert rule in text


@pytest.mark.parametrize("version", ["phase6-v1", "phase6-v2"])
def test_manifest_hash_is_identical_for_lf_and_crlf_input(version, tmp_path) -> None:
    canonical = dataset_dir(version) / "all.jsonl"
    lf = _canonical_bytes(canonical)  # canonical LF bytes
    crlf = lf.replace(b"\n", b"\r\n")  # simulate a CRLF checkout

    lf_path = tmp_path / "lf.jsonl"
    crlf_path = tmp_path / "crlf.jsonl"
    lf_path.write_bytes(lf)
    crlf_path.write_bytes(crlf)

    h_lf = hashlib.sha256(_canonical_bytes(lf_path)).hexdigest()
    h_crlf = hashlib.sha256(_canonical_bytes(crlf_path)).hexdigest()
    assert h_lf == h_crlf == dataset_manifest_hash(version)


def test_training_configs_pin_the_canonical_phase6_v2_hash() -> None:
    canonical = dataset_manifest_hash("phase6-v2")
    for name in ("finetune-v1.yaml", "finetune-v1-full.yaml"):
        cfg = yaml.safe_load(
            (REPO_ROOT / "configs" / "training" / name).read_text(encoding="utf-8")
        )
        assert cfg["dataset_version"] == "phase6-v2"
        assert cfg["dataset_manifest_hash"] == canonical


def test_phase6_v2_canonical_hash_is_stable() -> None:
    # the value committed to the training configs and this repo's history
    assert (
        dataset_manifest_hash("phase6-v2")
        == "234d9db964883b7ad4da4009ab325a4b4667af48e5be5bf7d7e05e3754a2ebdd"
    )
