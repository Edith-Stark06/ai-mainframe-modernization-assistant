"""
Answer Grounding Check.

Purpose:
    After a model answers, verify -- deterministically -- that the *figures* in
    its answer appear in the context it was given. A model that fills a gap
    with a plausible number ("typically 5,000") is the most damaging failure of
    a question about business logic; this catches it without another model
    call.

Responsibilities:
    - :func:`find_ungrounded_figures` -- the numbers in an answer that are in
      neither the retrieved context nor the question.

Non-responsibilities:
    - Judging prose, or numbers the model correctly derived by arithmetic (they
      are reported as unverified, which is the safe direction).
    - Detecting a *wrong* use of a number that does appear in the context.

Dependencies:
    - re, decimal (standard library)

Examples:
    >>> find_ungrounded_figures("The limit is 7,500.", ["IF X > 50000"], "limit?")
    ['7,500']

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

__all__ = ["find_ungrounded_figures"]

# 10,000 / 10 000 (also non-breaking spaces) / 12,345.67, or a plain number.
_NUMBER = re.compile(
    r"(?<![\w.\-])(\d{1,3}(?:[ ,  ]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\w\-])"
)
# Chunk-id citations such as [business_rule-0b43ac...] contain digits.
_CITATION = re.compile(r"\[[^\]]*\]")
_SEPARATORS = re.compile(r"[ ,  ]")

#: Whole numbers below this are counts/enumerations ("2 steps"), not figures.
_TRIVIAL_INTEGER_BELOW = 10


def _value(token: str) -> Decimal | None:
    try:
        return Decimal(_SEPARATORS.sub("", token))
    except InvalidOperation:  # pragma: no cover - the regex only yields numbers
        return None


def _key(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _figures(text: str) -> list[tuple[str, Decimal]]:
    found: list[tuple[str, Decimal]] = []
    for match in _NUMBER.finditer(_CITATION.sub(" ", text)):
        value = _value(match.group(1))
        if value is not None:
            found.append((match.group(1), value))
    return found


def find_ungrounded_figures(
    answer: str, context_texts: Iterable[str], question: str = ""
) -> list[str]:
    """
    Numbers in *answer* that appear in neither the context nor the question.

    A figure is grounded if it appears in the context/question, or is its
    percentage/fraction form (``18`` for ``0.18``, ``0.1`` for ``10``). Whole
    numbers under 10 are ignored as enumerations.

    Args:
        answer: The model's answer.
        context_texts: The retrieved chunks' text.
        question: The user's question (numbers it states are grounded).

    Returns:
        The offending figures as written in the answer, unique, in order.
    """
    grounded: set[str] = set()
    for text in [question, *context_texts]:
        for _, value in _figures(text):
            grounded.add(_key(value))

    ungrounded: list[str] = []
    for raw, value in _figures(answer):
        if value == value.to_integral_value() and abs(value) < _TRIVIAL_INTEGER_BELOW:
            continue
        candidates = {_key(value), _key(value / 100), _key(value * 100)}
        if candidates & grounded:
            continue
        if raw not in ungrounded:
            ungrounded.append(raw)
    return ungrounded
