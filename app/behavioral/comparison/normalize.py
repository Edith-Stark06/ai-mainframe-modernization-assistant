"""
#131 — explicit, conservative normalization rules.

Every rule applied before comparing two observed values is named and
documented here. Nothing else is normalized: leading/internal
whitespace, case, and string padding are preserved exactly, because
COBOL fixed-width / space-padded semantics can be meaningful.
"""

from __future__ import annotations

__all__ = [
    "normalize_line_endings",
    "normalize_trailing_line_whitespace",
    "try_parse_exact_integer",
    "values_equal",
]


def normalize_line_endings(text: str) -> str:
    """Rule 1: CRLF / CR -> LF. Pure transport artifact, never COBOL semantics."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_trailing_line_whitespace(text: str) -> str:
    """Rule 2: strip trailing whitespace at the end of each line only.

    Applied ONLY to captured process stdout (buffering / println can add
    or drop a trailing space that carries no COBOL meaning). Leading and
    internal whitespace — which can be significant COBOL field padding —
    is never touched.
    """
    return "\n".join(line.rstrip() for line in normalize_line_endings(text).split("\n"))


def try_parse_exact_integer(value: str) -> int | None:
    """Rule 3: numeric values are compared as exact integers, never floats.

    ``"018"``, ``"+18"`` and ``"18"`` are the same COBOL numeric value;
    leading zeros / an explicit ``+`` sign are display formatting, not a
    different value. Returns ``None`` (not a number) rather than raising,
    so callers fall back to exact string comparison — no approximate
    floating-point equality is ever used, because COBOL decimal
    precision/rounding/truncation must not be blurred.
    """
    s = value.strip()
    if not s:
        return None
    try:
        if "." in s or "e" in s.lower():
            return None  # decimal/scientific text is not folded into an int
        return int(s)
    except ValueError:
        return None


def values_equal(cobol_value: str, java_value: str) -> bool:
    """The single comparison rule the comparator uses for one field.

    1. If both sides parse as exact integers (Rule 3), compare as integers.
    2. Otherwise compare as strings after Rule 1 (line endings) only —
       no trimming, no case-folding, no padding removal.
    """
    a, b = try_parse_exact_integer(cobol_value), try_parse_exact_integer(java_value)
    if a is not None and b is not None:
        return a == b
    return normalize_line_endings(cobol_value) == normalize_line_endings(java_value)
