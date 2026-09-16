"""
#129 — deterministic parsing of a single COBOL comparison condition, and
boundary-oriented value generation.

Only the shape the deterministic business-rule engine actually produces
is modeled: an optional ``NOT (...)`` wrapper around one comparison
``<identifier> <op> <literal>``. Anything else (compound ``AND``/``OR``,
class conditions, etc.) is deliberately left unparsed — the caller must
then mark the resulting test ``executable=False``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Comparison", "parse_condition", "generate_boundary_values"]

_NUMERIC = re.compile(r"^-?\d+$")
_STRING_LIT = re.compile(r"^'(.*)'$|^\"(.*)\"$")
_COND_RE = re.compile(
    r"^\s*(?P<not>NOT\s*\(\s*)?"
    r"(?P<var>[A-Z0-9][A-Z0-9-]*)\s*"
    r"(?P<op>>=|<=|<>|=|>|<)\s*"
    r"(?P<lit>'[^']*'|\"[^\"]*\"|-?\d+)"
    r"(?(not)\s*\))\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Comparison:
    variable: str
    operator: str  # ">=" | "<=" | "<>" | "=" | ">" | "<"
    literal: str  # raw literal text, quotes stripped for strings
    is_numeric: bool
    negated: bool
    raw: str

    @property
    def effective_operator(self) -> str:
        """The operator once ``NOT (...)`` is folded in."""
        if not self.negated:
            return self.operator
        return {
            ">=": "<",
            "<=": ">",
            ">": "<=",
            "<": ">=",
            "=": "<>",
            "<>": "=",
        }[self.operator]


def parse_condition(text: str) -> Comparison | None:
    m = _COND_RE.match(text.strip())
    if not m:
        return None
    lit = m.group("lit")
    is_numeric = bool(_NUMERIC.match(lit))
    if not is_numeric:
        sm = _STRING_LIT.match(lit)
        lit = (sm.group(1) if sm.group(1) is not None else sm.group(2)) if sm else lit
    return Comparison(
        variable=m.group("var").upper(),
        operator=m.group("op"),
        literal=lit,
        is_numeric=is_numeric,
        negated=bool(m.group("not")),
        raw=text.strip(),
    )


def generate_boundary_values(cmp: Comparison) -> list[tuple[str, bool]]:
    """Deterministic ``[(value, condition_holds), ...]`` boundary partition.

    Uses :attr:`Comparison.effective_operator` so the result already
    reflects a ``NOT (...)`` wrapper — ``taken`` means "this comparison,
    as written, evaluates true for this value".
    """
    op = cmp.effective_operator
    if cmp.is_numeric:
        n = int(cmp.literal)
        candidates = [n - 1, n, n + 1]
        out: list[tuple[str, bool]] = []
        seen: set[int] = set()
        for v in candidates:
            if v in seen or v < 0:
                continue
            seen.add(v)
            out.append((str(v), _holds(v, op, n)))
        return out
    # string comparison: the literal itself, and one deterministic "other"
    other = "OTHER" if cmp.literal != "OTHER" else "ALT"
    return [
        (cmp.literal, _holds_str(cmp.literal, op, cmp.literal)),
        (other, _holds_str(other, op, cmp.literal)),
    ]


def _holds(v: int, op: str, n: int) -> bool:
    return {
        ">=": v >= n,
        "<=": v <= n,
        ">": v > n,
        "<": v < n,
        "=": v == n,
        "<>": v != n,
    }[op]


def _holds_str(v: str, op: str, lit: str) -> bool:
    if op == "=":
        return v == lit
    if op == "<>":
        return v != lit
    return False  # ordering ops on strings are not modeled
