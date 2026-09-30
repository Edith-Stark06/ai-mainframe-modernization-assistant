"""
Query Analysis.

Purpose:
    Deterministic helpers that turn a natural-language question into what
    retrieval actually needs: independent sub-questions, search terms, and
    exact phrases. No model is involved, so the same question always yields the
    same searches.

Responsibilities:
    - :func:`split_question` -- split a multi-part question into its parts.
    - :func:`tokenize` -- normalise text for lexical matching, treating COBOL
      names (``WS-TOTAL``), Java names (``wsTotal``) and numbers (``0.18``)
      consistently.
    - :func:`extract_phrases` -- exact phrases worth matching verbatim
      (quoted text, runs of capitalised words such as ``HIGH VALUE``).

Non-responsibilities:
    - Searching (see :mod:`app.rag.retrieval.hybrid`).

Dependencies:
    - re (standard library)

Examples:
    >>> split_question("What is X, and what is Y?")
    ['What is X, and what is Y?', 'What is X', 'what is Y?']
    >>> tokenize("WS-TOTAL >= 50000")
    ['ws', 'total', '50000']

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re

__all__ = ["expand_terms", "extract_phrases", "split_question", "tokenize"]

#: Words that carry no retrieval signal. Deliberately small: domain words such
#: as "total", "status" or "order" must stay searchable.
STOPWORDS = frozenset("""
    a an the of to is are was were be been being do does did done in on at by for
    with from as and or but if then than that this these those it its into what
    when where which who whom whose how why can could should would will shall
    program programs about become becomes become any all each per use uses used
    happen happens there their they them you your me my we our i not no
    """.split())

# A new question clause: ", and what ...", "; how ...", "? What ...".
_QUESTION_WORDS = (
    r"what|how|when|where|why|which|who|does|do|is|are|can|will|should|"
    r"explain|describe|show|list|tell"
)
_CLAUSE_BREAK = re.compile(
    rf"""(?:\?+\s+)                              # "?" then more text
       |(?:;\s+)                                 # semicolon
       |(?:,?\s+and\s+(?=(?:{_QUESTION_WORDS})\b))   # ", and what ..."
       |(?:,\s+(?=(?:{_QUESTION_WORDS})\b))      # ", what ..."
    """,
    re.IGNORECASE | re.VERBOSE,
)

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
# Numbers keep an internal decimal point (0.18); everything else is alnum runs.
_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")

_QUOTED = re.compile(r"""['"“”‘’]([^'"“”‘’]{2,60})['"“”‘’]""")
# Two or more consecutive ALL-CAPS words: HIGH VALUE, ZERO VALUE ORDER.
_CAPS_RUN = re.compile(r"\b[A-Z][A-Z0-9]+(?:\s+[A-Z][A-Z0-9]+)+\b")

_MIN_PART_WORDS = 3


def split_question(query: str) -> list[str]:
    """
    Split a multi-part question into its parts.

    A question with one clause returns ``[query]``. With several, the result
    is the original question first (it may carry context the parts lack)
    followed by each part, without duplicates and without parts too short to
    search on.

    Args:
        query: The user's question.

    Returns:
        Non-empty list of search strings, original first.
    """
    original = query.strip()
    parts = [p.strip(" \t\r\n,;") for p in _CLAUSE_BREAK.split(original) if p]
    parts = [p for p in parts if len(p.split()) >= _MIN_PART_WORDS]
    if len(parts) < 2:
        return [original]
    out = [original]
    for part in parts:
        if part not in out:
            out.append(part)
    return out


def tokenize(text: str, *, drop_stopwords: bool = False) -> list[str]:
    """
    Normalise *text* into lowercase lexical tokens.

    ``WS-TOTAL`` and ``wsTotal`` both become ``ws``, ``total``; ``0.18`` stays
    one token, so a number in a question matches the same number in code.

    Args:
        text: Any text (a question, a chunk, source code).
        drop_stopwords: Remove :data:`STOPWORDS` (used for queries).

    Returns:
        The tokens, in order, with repeats.
    """
    tokens = _TOKEN.findall(_CAMEL.sub(" ", text).lower())
    if drop_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS]
    return tokens


def extract_phrases(query: str) -> list[str]:
    """
    Exact phrases from *query* worth matching verbatim (case-insensitive).

    Quoted text (``'HIGH VALUE'``) and runs of two or more ALL-CAPS words
    (``HIGH VALUE``) -- the way COBOL literals and figurative names are
    usually written in a question.

    Args:
        query: The user's question.

    Returns:
        Lower-cased phrases, unique, in order of appearance.
    """
    found: list[str] = []
    for match in _QUOTED.finditer(query):
        found.append(match.group(1).strip().lower())
    for match in _CAPS_RUN.finditer(query):
        found.append(match.group(0).strip().lower())
    return [p for p in dict.fromkeys(found) if p]


#: Everyday words a person uses about what a program does -> the COBOL words
#: that do it. Without this, "which values are read from the user?" shares no
#: word with ``ACCEPT WS-QUANTITY``. Deliberately small, explicit and
#: deterministic (no model); extend it when an evaluation case shows a gap.
_GLOSSARY: dict[str, tuple[str, ...]] = {
    "user": ("accept",),
    "keyboard": ("accept",),
    "prompt": ("accept", "display"),
    "console": ("accept", "display"),
    "enter": ("accept",),
    "entered": ("accept",),
    "input": ("accept",),
    "typed": ("accept",),
    "print": ("display",),
    "printed": ("display",),
    "show": ("display",),
    "shown": ("display",),
    "screen": ("display",),
    "message": ("display",),
    "output": ("display",),
    "loop": ("perform", "until"),
    "repeat": ("perform", "until"),
    "repeated": ("perform", "until"),
    "iterate": ("perform", "until"),
    "calculate": ("compute",),
    "calculated": ("compute",),
    "calculation": ("compute",),
    "formula": ("compute",),
    "accumulate": ("add",),
    "accumulated": ("add",),
    "increment": ("add",),
    "subroutine": ("call", "perform"),
    "invoke": ("call", "perform"),
    "terminate": ("stop", "goback"),
    "finish": ("stop", "goback"),
    "condition": ("if",),
    "threshold": ("if",),
    "limit": ("if",),
    "initial": ("value", "move"),
    "initialize": ("value", "move"),
    "default": ("value", "move"),
}


def expand_terms(terms: list[str]) -> list[str]:
    """
    Add the COBOL words that correspond to everyday words in *terms*.

    Args:
        terms: Query tokens (already stop-word filtered).

    Returns:
        *terms* followed by any glossary expansions, without duplicates.
    """
    out = list(terms)
    for term in terms:
        out.extend(_GLOSSARY.get(term, ()))
    return list(dict.fromkeys(out))
