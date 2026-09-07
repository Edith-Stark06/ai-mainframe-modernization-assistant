"""JSONL read/write helpers for Phase 6 datasets and benchmarks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from app.dataset.schema import DatasetExample

__all__ = [
    "write_jsonl",
    "read_jsonl_raw",
    "read_examples",
    "canonical_json_line",
]


def canonical_json_line(obj: Any) -> str:
    """One deterministic JSON line (sorted keys, no trailing whitespace)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def write_jsonl(path: str | Path, rows: Iterable[Any]) -> int:
    """
    Write *rows* (pydantic models or dicts) as canonical JSONL.

    Returns the number of rows written. Deterministic byte output for
    identical input.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            if hasattr(row, "model_dump"):
                data = row.model_dump(mode="json")
            elif hasattr(row, "to_dict"):
                data = row.to_dict()
            else:
                data = row
            fh.write(canonical_json_line(data))
            fh.write("\n")
            count += 1
    return count


def read_jsonl_raw(path: str | Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """Yield ``(1-based line number, parsed dict)`` for each non-blank line."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            yield lineno, json.loads(stripped)


def read_examples(path: str | Path) -> list[DatasetExample]:
    """Parse a dataset JSONL file into validated :class:`DatasetExample`."""
    out: list[DatasetExample] = []
    for _lineno, data in read_jsonl_raw(path):
        out.append(DatasetExample.model_validate(data))
    return out
