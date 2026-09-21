"""
The git-ignored ``train.jsonl``/``validation.jsonl`` are derivable.

``.gitignore`` excludes them on purpose (size) and tracks ``all.jsonl``,
``split_manifest.json`` and ``test.jsonl``. ``conftest.py`` regenerates any
missing split from those tracked files; these tests prove the derivation is
faithful, so a fresh checkout and a developer machine see identical data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.dataset.io import write_jsonl

from .conftest import derive_splits

_ROOT = Path(__file__).resolve().parents[2] / "data" / "dataset"


@pytest.mark.parametrize("name", ["mmim-v1", "mmim-v2"])
def test_derived_test_split_matches_the_tracked_test_jsonl(name, tmp_path) -> None:
    """``test.jsonl`` is tracked, so it is the ground truth the derivation
    must reproduce byte-for-byte."""
    parts = derive_splits(_ROOT / name)
    write_jsonl(tmp_path / "test.jsonl", parts["test"])
    assert (tmp_path / "test.jsonl").read_bytes() == (
        _ROOT / name / "test.jsonl"
    ).read_bytes()


@pytest.mark.parametrize("name", ["mmim-v1", "mmim-v2"])
def test_train_and_validation_files_equal_the_derivation(name, tmp_path) -> None:
    """Whether regenerated just now or produced by the builder, the files on
    disk are exactly what the derivation gives."""
    parts = derive_splits(_ROOT / name)
    for split in ("train", "validation"):
        write_jsonl(tmp_path / f"{split}.jsonl", parts[split])
        assert (tmp_path / f"{split}.jsonl").read_bytes() == (
            _ROOT / name / f"{split}.jsonl"
        ).read_bytes(), split


@pytest.mark.parametrize("name", ["mmim-v1", "mmim-v2"])
def test_splits_partition_all_examples(name) -> None:
    from app.dataset.io import read_examples

    parts = derive_splits(_ROOT / name)
    total = len(read_examples(_ROOT / name / "all.jsonl"))
    assert sum(len(v) for v in parts.values()) == total
