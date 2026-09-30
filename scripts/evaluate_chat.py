"""
Live chat evaluation: ask the running API the evaluation questions and check
the *answers*.

Purpose:
    ``python -m app.rag.evaluation`` measures retrieval without a model. This
    checks the whole chain against the real, configured LLM: for each case the
    answer must contain the expected facts, and figures the answer states that
    are not in the retrieved context are counted. It needs the API running
    (default http://127.0.0.1:8000), an LLM configured, and the sample file in
    a workspace; it is not part of the automated suite because it calls a
    real model.

Usage::

    python scripts/evaluate_chat.py --workspace <workspace-id> \
        --file moderate_sales_report.cbl \
        --cases tests/fixtures/rag_eval/sales_report_cases.json

Each case may carry ``"answer": [[alt, alt], ...]``: every group needs at least
one of its alternatives (case-insensitive) somewhere in the answer.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

_TIMEOUT_S = 660.0


def _check(answer: str, groups: list[list[str]]) -> list[list[str]]:
    """The groups for which none of the alternatives is in *answer*."""
    text = answer.lower()
    return [g for g in groups if not any(alt.lower() in text for alt in g)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--workspace", required=True, help="workspace id holding the file"
    )
    parser.add_argument("--file", required=True, help="filename inside the workspace")
    parser.add_argument(
        "--cases", default="tests/fixtures/rag_eval/sales_report_cases.json"
    )
    parser.add_argument("--top-k", type=int, default=None)
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
    cases = [c for c in cases if c.get("answer")]
    base = f"{args.api}/api/v1/chat"

    with httpx.Client(timeout=_TIMEOUT_S) as client:
        indexed = client.post(
            f"{base}/index",
            json={"workspace_id": args.workspace, "filename": args.file},
        )
        indexed.raise_for_status()
        print(f"indexed: {indexed.json()}\n")

        passed = flagged = 0
        for case in cases:
            body = {
                "query": case["question"],
                "workspace_id": args.workspace,
                "filename": args.file,
            }
            if args.top_k:
                body["top_k"] = args.top_k
            started = time.perf_counter()
            reply = client.post(f"{base}/", json=body).json()
            took = time.perf_counter() - started

            if reply.get("error"):
                print(f"ERR   {case['id']:38s} {reply['error_code']}: {reply['error']}")
                continue
            missing = _check(reply["answer"], case["answer"])
            figures = reply.get("ungrounded_figures", [])
            passed += not missing
            flagged += bool(figures)
            status = "PASS " if not missing else "FAIL "
            extra = f" missing={missing}" if missing else ""
            extra += f" unverified_figures={figures}" if figures else ""
            print(f"{status} {case['id']:38s} {took:5.1f}s{extra}")

    print(
        f"\nanswers with all expected facts: {passed}/{len(cases)}   "
        f"answers with unverified figures: {flagged}/{len(cases)}"
    )
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
