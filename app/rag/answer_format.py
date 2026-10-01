"""
Chat Answer Formatting.

Purpose:
    Turn a model's raw reply into text that reads cleanly in the chat window,
    whatever the model happened to write. The prompt asks for a clean style;
    this module makes the result reliable instead of hopeful. It never changes
    what the answer *says*, only how it is laid out.

Responsibilities:
    - :func:`clean_answer` -- replace raw chunk-id citations with the short
      numbers the Evidence list uses, turn markdown tables into bullet lists,
      remove dangling bold markers, and tidy whitespace.

Non-responsibilities:
    - Checking facts or figures (see :mod:`app.rag.grounding`).

Dependencies:
    - re (standard library)

Examples:
    >>> clean_answer("See [rule-0123456789ab].", {"rule-0123456789ab": 2})
    'See [2].'

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re
from collections.abc import Mapping

__all__ = ["clean_answer"]

#: One or more chunk ids in one bracket: ``[a-0123abcd]`` or ``[a-0123abcd, b-4567ef01]``.
_ID = r"[a-z][a-z_]*-[0-9a-f]{8,}"
_ID_GROUP = re.compile(rf"([ \t]*)\[\s*{_ID}(?:\s*[,;]\s*{_ID})*\s*\]")
_ID_ONE = re.compile(_ID)

_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")

#: Table columns that only held citations / chunk lists: dropped when a table is
#: turned into bullets (the numbers are kept inline instead).
_CITATION_HEADERS = ("chunk", "source", "reference", "citation", "ref")

_ORPHAN_BOLD = re.compile(r"(?m)^(\s*)\*{2,}\s*$")
_BLANK_RUN = re.compile(r"\n{3,}")
_HARD_BREAK = re.compile(r"[ \t]+\n")


#: Characters models substitute for plain ones, which break copy/paste of code
#: names ("WS\u2011TOTAL" is not "WS-TOTAL") and citation numbers.
_PLAIN = str.maketrans(
    {
        "\u2010": "-",  # hyphen
        "\u2011": "-",  # non-breaking hyphen
        "\u2012": "-",  # figure dash
        "\u3010": "[",  # fullwidth lenticular bracket, used as a citation mark
        "\u3011": "]",
    }
)


def _replace_citations(text: str, refs: Mapping[str, int]) -> str:
    """``[chunk-id, ...]`` -> ``[n]`` / ``[n, m]``; unknown ids are dropped."""

    def swap(match: re.Match[str]) -> str:
        numbers = sorted(
            {refs[i] for i in _ID_ONE.findall(match.group(0)) if i in refs}
        )
        if not numbers:
            return ""  # an unknown id: drop it with the space before it
        return match.group(1) + "[" + ", ".join(str(n) for n in numbers) + "]"

    return _ID_GROUP.sub(swap, text)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table_to_bullets(lines: list[str]) -> list[str]:
    """Convert one markdown table (header, rule, rows) into bullet lines."""
    header = _cells(lines[0])
    rows = [_cells(line) for line in lines[2:]]
    keep = [
        i
        for i, name in enumerate(header)
        if not any(word in name.lower() for word in _CITATION_HEADERS)
    ] or list(range(len(header)))
    bullets: list[str] = []
    for row in rows:
        parts = [row[i] for i in keep if i < len(row) and row[i]]
        if not parts:
            continue
        # Row-number columns ("1", "2", ...) add nothing once rows are bullets.
        if len(parts) > 1 and parts[0].isdigit():
            parts = parts[1:]
        bullets.append("- " + " — ".join(parts))
    return bullets


def _convert_tables(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        is_table = (
            _TABLE_ROW.match(lines[i])
            and i + 1 < len(lines)
            and _TABLE_RULE.match(lines[i + 1])
        )
        if not is_table:
            out.append(lines[i])
            i += 1
            continue
        j = i + 2
        while j < len(lines) and _TABLE_ROW.match(lines[j]):
            j += 1
        out.extend(_table_to_bullets(lines[i:j]))
        i = j
    return "\n".join(out)


def clean_answer(text: str, refs: Mapping[str, int] | None = None) -> str:
    """
    Make *text* read cleanly in chat.

    Args:
        text: The model's answer.
        refs: ``{chunk id: number}`` as shown in the Evidence list. Raw ids the
            model wrote as citations become ``[number]``; ids not in *refs*
            are removed.

    Returns:
        The cleaned text: markdown tables as bullets, no dangling ``**``, no
        trailing double-space line breaks, at most one blank line in a row.
    """
    cleaned = _replace_citations(text.translate(_PLAIN), refs or {})
    cleaned = _convert_tables(cleaned)
    cleaned = _ORPHAN_BOLD.sub("", cleaned)
    cleaned = _HARD_BREAK.sub("\n", cleaned)
    cleaned = _BLANK_RUN.sub("\n\n", cleaned)
    return cleaned.strip()
