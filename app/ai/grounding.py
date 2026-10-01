"""
Grounding Rules.

Purpose:
    The instructions that keep a model's answer to a question tied to the
    context it was given. Without them a model fills gaps with plausible guesses
    -- for a code question, an invented threshold or rate. Both prompt builders
    (explanation, documentation) add these lines when a user question is
    present.

Responsibilities:
    - :data:`GROUNDING_RULES` -- the instruction lines.
    - :data:`RULES_HEADING` -- heading used for parser-derived business rules in
      a grounded prompt.

Non-responsibilities:
    - Checking an answer after the fact (see :mod:`app.rag.grounding`).

Dependencies:
    - none

Examples:
    ::

        prompt_parts.extend(GROUNDING_RULES)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

__all__ = ["GROUNDING_RULES", "RULES_HEADING"]

#: Heading for business rules in a grounded prompt: says *why* they outrank prose.
RULES_HEADING = "=== PARSER-DERIVED BUSINESS RULES ==="

GROUNDING_RULES: tuple[str, ...] = (
    "\nGrounding rules for answering the user's question:",
    "- Use ONLY facts stated in the context below. Do not use outside knowledge to "
    "fill gaps, and never guess numbers, thresholds, rates, names or behaviour.",
    "- If any part of the question is not answered by the context, say so plainly "
    'for that part ("not in the retrieved context") instead of guessing, and do '
    'not hedge with words like "presumably", "likely" or "typically".',
    "- Business rules under PARSER-DERIVED BUSINESS RULES were produced by a "
    "deterministic parser; they take precedence over any paraphrase or code below.",
    "- Cite sources by their number in square brackets, e.g. [2] or [1][3]. Never "
    'write chunk ids or the word "chunk".',
    "\nStyle rules (the answer is shown in a chat window):",
    "- Under 'Summary:' give the direct answer in one or two plain sentences. Do "
    "not restate the question or describe the whole program unless asked to.",
    "- Under 'Explanation:' use short bullet points, one line each, only for what "
    "supports the answer: at most 6 for a specific question; for a list, "
    "walk-through, analysis or whole-program explanation one bullet per item or "
    "step, up to 12. Do not repeat the summary.",
    "- No tables, headings, horizontal rules or 'Note' sections. Put identifiers "
    "and code in `backticks`. Plain markdown only.",
)
