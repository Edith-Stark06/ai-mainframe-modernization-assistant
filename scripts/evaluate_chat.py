"""
Live chat evaluation: ask the running API questions and check the *answers*.

Purpose:
    ``python -m app.rag.evaluation`` measures retrieval without a model. This
    checks the whole chain against the real, configured LLM:

    * **Facts** -- for each case in ``--cases`` the answer must contain the
      expected facts, and figures the answer states that are not in the
      retrieved context are counted.
    * **Style** -- every answer (those cases plus the open-ended questions in
      ``--questions``) is scored for readability noise by
      :func:`app.rag.style.measure_style`: raw chunk ids, table rows, hedging
      words, ``Summary:`` style labels, stray ``**``, and length.

    It needs the API running (default http://127.0.0.1:8000), an LLM
    configured, and the sample file in a workspace; it is not part of the
    automated suite because it calls a real model.

Usage::

    python scripts/evaluate_chat.py --workspace <workspace-id> \
        --file moderate_sales_report.cbl [--save before.json]

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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.style import measure_style  # noqa: E402

_TIMEOUT_S = 660.0


def _norm(text: str) -> str:
    """Lower-case; unify the non-breaking spaces and hyphens models like to use."""
    for odd in ("‑", "‐", "‒", "–"):
        text = text.replace(odd, "-")
    return " ".join(text.lower().split())


def _check(answer: str, groups: list[list[str]]) -> list[list[str]]:
    """The groups for which none of the alternatives is in *answer*."""
    text = _norm(answer)
    return [g for g in groups if not any(_norm(alt) in text for alt in g)]


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
    parser.add_argument(
        "--questions", default="tests/fixtures/rag_eval/open_questions.json"
    )
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument(
        "--save", default=None, help="write all answers to this JSON file"
    )
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
    cases = [c for c in cases if c.get("answer")]
    open_questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))[
        "questions"
    ]
    # An open question is either a plain string (style only) or
    # {"question": ..., "answer": [[alt, ...], ...]} (style and facts).
    jobs = [(c["id"], c["question"], c["answer"]) for c in cases] + [
        (
            f"open_{i + 1}",
            q if isinstance(q, str) else q["question"],
            [] if isinstance(q, str) else q.get("answer", []),
        )
        for i, q in enumerate(open_questions)
    ]
    base = f"{args.api}/api/v1/chat"

    saved: list[dict] = []
    passed = flagged = 0
    totals = {"words": 0, "noise": 0, "ids": 0, "tables": 0, "hedges": 0, "labels": 0}
    answered = 0

    with httpx.Client(timeout=_TIMEOUT_S) as client:
        indexed = client.post(
            f"{base}/index",
            json={"workspace_id": args.workspace, "filename": args.file},
        )
        indexed.raise_for_status()
        print(f"indexed: {indexed.json()}\n")

        for case_id, question, expected in jobs:
            body = {
                "query": question,
                "workspace_id": args.workspace,
                "filename": args.file,
            }
            if args.top_k:
                body["top_k"] = args.top_k
            started = time.perf_counter()
            reply = client.post(f"{base}/", json=body).json()
            took = time.perf_counter() - started

            if reply.get("error"):
                print(f"ERR   {case_id:38s} {reply['error_code']}: {reply['error']}")
                continue

            answer = reply["answer"]
            style = measure_style(answer)
            missing = _check(answer, expected)
            figures = reply.get("ungrounded_figures", [])
            answered += 1
            passed += bool(expected) and not missing
            flagged += bool(figures)
            totals["words"] += style.words
            totals["noise"] += style.noise
            totals["ids"] += style.chunk_id_citations
            totals["tables"] += style.table_rows
            totals["hedges"] += style.hedges
            totals["labels"] += style.section_labels
            saved.append({"id": case_id, "question": question, "answer": answer})

            status = ("FAIL " if missing else "PASS ") if expected else "     "
            extra = f" missing={missing}" if missing else ""
            extra += f" unverified_figures={figures}" if figures else ""
            print(
                f"{status} {case_id:38s} {took:5.1f}s  words={style.words:4d} "
                f"ids={style.chunk_id_citations} table_rows={style.table_rows} "
                f"hedges={style.hedges} labels={style.section_labels}{extra}"
            )

    n = max(answered, 1)
    print(
        f"\nfacts: {passed}/{len([j for j in jobs if j[2]])} expected-fact answers pass, "
        f"{flagged}/{answered} with unverified figures"
    )
    print(
        f"style over {answered} answers: avg words={totals['words'] / n:.0f}  "
        f"chunk-id citations={totals['ids']}  table rows={totals['tables']}  "
        f"hedges={totals['hedges']}  section labels={totals['labels']}  "
        f"total noise={totals['noise']}"
    )
    if args.save:
        Path(args.save).write_text(json.dumps(saved, indent=2), encoding="utf-8")
        print(f"answers saved to {args.save}")
    return 0 if passed == len([j for j in jobs if j[2]]) else 1


if __name__ == "__main__":
    sys.exit(main())
