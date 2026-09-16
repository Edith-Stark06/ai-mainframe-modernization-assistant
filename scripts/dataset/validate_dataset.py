"""
Validate an existing Phase 6 dataset JSONL file (#118).

    python -m scripts.dataset.validate_dataset PATH [--version phase6-v1] [--pii]

Prints a summary and writes ``<PATH>.validation.json``. Exit code is
non-zero on any error-severity issue or HIGH secret finding.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.dataset.security import SecretScanConfig
from app.dataset.validation import validate_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--version", default=None)
    parser.add_argument("--pii", action="store_true", help="also scan for PII")
    args = parser.parse_args(argv)

    cfg = SecretScanConfig(pii_enabled=args.pii)
    report = validate_dataset(args.path, cfg, expected_version=args.version)

    out = Path(str(args.path) + ".validation.json")
    out.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"path:            {report.path}")
    print(f"dataset_version: {report.dataset_version}")
    print(f"examples:        {report.valid} valid / {report.total} total")
    print(f"errors:          {report.error_count}")
    print(f"warnings:        {report.warning_count}")
    print(f"secret findings: {len(report.secret_findings)}")
    for issue in report.issues[:25]:
        print(f"  [{issue.severity.value}] L{issue.line} {issue.code}: {issue.message}")
    print("OK" if report.ok else "FAILED")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
