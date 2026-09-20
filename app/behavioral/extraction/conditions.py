"""
#129 — deterministic parsing of a single COBOL comparison condition, and
boundary-oriented value generation.

Two shapes the deterministic business-rule engine actually produces are
modeled, each optionally wrapped in ``NOT (...)``:

* an ordinary comparison, ``<identifier> <op> <literal>``;
* a level-88 condition-name reference, rendered by the business-rule
  engine as ``<name> IS-TRUE <name>`` or ``<name> IS-FALSE <name>`` (the
  sentinel operators ``app.parser.syntax.procedure_parser`` assigns a
  bare/``NOT``-prefixed condition-name reference in an ``IF`` — see
  ``docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md``). The repeated name is
  not a typo: a condition-name test is unary, and the parser layer keeps
  it in the existing ``(left, operator, right)`` triple shape by setting
  both operands to the condition-name itself, so no new AST field was
  needed there — this module honors that same shape rather than inventing
  a different one.

A third shape, a **compound** condition, is handled by
:func:`parse_compound_condition` (kept separate from :func:`parse_condition`
so every existing single-term caller and behavior is completely
unaffected): the business-rule engine renders a chain of ``AND``-joined
(never mixed with ``OR`` — see that function's docstring) parenthesized
terms, each of which — once its own wrapping parens are stripped — is
already exactly a string :func:`parse_condition` can parse on its own.
:func:`parse_compound_condition` therefore *composes* :func:`parse_condition`
rather than reimplementing comparison/condition-name grammar a second
time. Class conditions and anything else are still deliberately left
unparsed — the caller must then mark the resulting test
``executable=False``.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from decimal import Decimal

__all__ = [
    "Comparison",
    "CompoundComparison",
    "parse_condition",
    "parse_compound_condition",
    "generate_boundary_values",
    "generate_compound_boundary_values",
    "evaluate_compound",
    "strip_string_literal",
]

# COBOL fixed-point literals (e.g. ``PIC 9(2)V99`` values like ``0.00`` or
# ``7.25``) are ordinary decimal literals — a sign, digits, and an optional
# ``.`` followed by more digits. No exponent/scientific notation form is
# emitted anywhere in the repository's parser or business-rule engine, so
# none is accepted here.
_NUMERIC = re.compile(r"^-?\d+(?:\.\d+)?$")
_STRING_LIT = re.compile(r"^'(.*)'$|^\"(.*)\"$")
_COND_RE = re.compile(
    r"^\s*(?P<not>NOT\s*\(\s*)?"
    r"(?P<var>[A-Z0-9][A-Z0-9-]*)\s*"
    r"(?P<op>>=|<=|<>|=|>|<)\s*"
    r"(?P<lit>'[^']*'|\"[^\"]*\"|-?\d+(?:\.\d+)?)"
    r"(?(not)\s*\))\s*$",
    re.IGNORECASE,
)

# A level-88 condition-name reference: kept as a *separate* regex, never
# folded into _COND_RE's `lit` alternation, so that admitting a bare
# identifier as the right-hand side can never widen what an *ordinary*
# comparison (=, >, etc.) accepts there — those still require a real
# literal, exactly as before. Tried only after _COND_RE fails to match.
_CONDITION_NAME_OPERATORS = ("IS-TRUE", "IS-FALSE")
_CONDITION_NAME_RE = re.compile(
    r"^\s*(?P<not>NOT\s*\(\s*)?"
    r"(?P<var>[A-Z0-9][A-Z0-9-]*)\s*"
    r"(?P<op>IS-TRUE|IS-FALSE)\s*"
    r"(?P<var2>[A-Z0-9][A-Z0-9-]*)"
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
    def is_condition_name(self) -> bool:
        """``True`` for a level-88 condition-name reference (``IS-TRUE``/
        ``IS-FALSE``), as opposed to an ordinary relational comparison."""
        return self.operator in _CONDITION_NAME_OPERATORS

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
            "IS-TRUE": "IS-FALSE",
            "IS-FALSE": "IS-TRUE",
        }[self.operator]


@dataclass(frozen=True)
class CompoundComparison:
    """A flat ``AND``- or ``OR``-joined sequence of :class:`Comparison`
    terms — never mixed connectors, never nested (see
    :func:`parse_compound_condition`, the only place this is constructed).

    Deliberately *not* a general expression tree: the business-rule
    engine that produces the strings this represents only ever emits a
    single, uniform connector chaining independently-parseable terms
    (each already representable by the existing :class:`Comparison`), so
    that is all this composes.
    """

    connector: str  # "AND" | "OR"
    terms: tuple[Comparison, ...]
    raw: str


def strip_string_literal(text: str) -> str:
    """Strip a single/double-quote wrapper from *text* if present.

    Shared by :func:`parse_condition` (for a comparison's own literal) and
    by callers reading a level-88 condition-name's declared VALUE/VALUES
    literals straight off the AST (``ConditionNameNode.values`` — see
    ``app/behavioral/extraction/extractor.py``), so both sites strip
    quotes identically and a boundary value derived from either source
    looks the same. Text that is not quoted (e.g. a numeric literal, or
    a figurative constant like ``ZERO``) is returned unchanged.
    """
    sm = _STRING_LIT.match(text)
    if sm is None:
        return text
    return sm.group(1) if sm.group(1) is not None else sm.group(2)


def parse_condition(text: str) -> Comparison | None:
    stripped = text.strip()

    m = _COND_RE.match(stripped)
    if m is not None:
        lit = m.group("lit")
        is_numeric = bool(_NUMERIC.match(lit))
        if not is_numeric:
            lit = strip_string_literal(lit)
        return Comparison(
            variable=m.group("var").upper(),
            operator=m.group("op"),
            literal=lit,
            is_numeric=is_numeric,
            negated=bool(m.group("not")),
            raw=stripped,
        )

    m = _CONDITION_NAME_RE.match(stripped)
    if m is not None:
        var = m.group("var").upper()
        # The parser always renders a condition-name term with both
        # operands equal to the condition-name itself (see the module
        # docstring). A string where they differ is not a shape this
        # module's caller ever legitimately produces -- reject it rather
        # than guess which operand was "real" (do not invent semantics
        # for an unexpected shape).
        if m.group("var2").upper() != var:
            return None
        return Comparison(
            variable=var,
            operator=m.group("op").upper(),
            literal=var,
            is_numeric=False,
            negated=bool(m.group("not")),
            raw=stripped,
        )

    return None


# A single top-level parenthesized part of a compound condition: its
# content is either paren-free, or contains exactly one further
# paren-wrapped group (the ``NOT (...)`` case) -- matching precisely the
# one level of nesting app.modernization.business_rules.extractor's
# _render_condition ever produces (a NOT-wrapped term, itself wrapped in
# the compound's own per-part parens). Not a general balanced-parens
# matcher -- deeper nesting simply fails to match, which is correct: this
# module never claims to parse anything the business-rule engine cannot
# actually produce.
_COMPOUND_PART_RE = re.compile(r"\((?:[^()]|\([^()]*\))*\)")
_CONNECTOR_ONLY_RE = re.compile(r"^\s*(AND|OR)\s*$", re.IGNORECASE)


def parse_compound_condition(text: str) -> CompoundComparison | None:
    """Parse a compound condition string: ``(term) AND (term) [AND (term) ...]``
    or the ``OR`` equivalent -- the exact, uniform-connector,
    single-level-of-parenthesization shape
    ``app.modernization.business_rules.extractor._render_condition``
    produces for an ``IfStatementNode``-cascade-derived rule (see
    ``docs/MMIM_COMPOUND_CONDITION_FIX.md``).

    Each part, once its own wrapping parens are stripped, is handed to
    :func:`parse_condition` unchanged -- this function never re-implements
    comparison or condition-name grammar, only composes it. Terms are
    *not* required to share a variable, an operator, or a shape (a
    condition-name term and an ordinary comparison term can appear side
    by side in the same compound, exactly as real rules do).

    Returns ``None`` -- never partially -- for anything that is not
    *exactly* this shape: fewer than two parts, a connector other than a
    uniform ``AND``/``OR``, mixed ``AND``/``OR`` in the same expression
    (COBOL's own operator-precedence case this deliberately does not
    attempt to model), stray text outside the parenthesized parts, or any
    part whose *own* content :func:`parse_condition` cannot parse. A
    single (non-compound) condition is not this function's job -- call
    :func:`parse_condition` for that.
    """
    stripped = text.strip()
    matches = list(_COMPOUND_PART_RE.finditer(stripped))
    if len(matches) < 2:
        return None
    if stripped[: matches[0].start()].strip():
        return None
    if stripped[matches[-1].end() :].strip():
        return None

    connector: str | None = None
    terms: list[Comparison] = []
    for idx, m in enumerate(matches):
        inner = m.group(0)[1:-1]
        cmp = parse_condition(inner)
        if cmp is None:
            return None
        terms.append(cmp)
        if idx + 1 < len(matches):
            between = stripped[m.end() : matches[idx + 1].start()]
            cm = _CONNECTOR_ONLY_RE.match(between)
            if cm is None:
                return None
            conn = cm.group(1).upper()
            if connector is None:
                connector = conn
            elif conn != connector:
                return None

    if connector is None:
        return None
    return CompoundComparison(connector=connector, terms=tuple(terms), raw=stripped)


def _numeric_step(literal: str) -> Decimal:
    """The smallest increment implied by a literal's own precision.

    An integer literal (``100``) steps by ``1``, exactly as before. A
    decimal literal (``0.00``, ``7.25``) steps by one unit in its last
    place (``0.01``) — the finest boundary COBOL's fixed-point
    representation can actually distinguish, and nothing finer.
    """
    if "." in literal:
        frac_len = len(literal.split(".", 1)[1])
        return Decimal(1).scaleb(-frac_len)
    return Decimal(1)


def generate_boundary_values(
    cmp: Comparison, known_values: tuple[str, ...] = ()
) -> list[tuple[str, bool]]:
    """Deterministic ``[(value, condition_holds), ...]`` boundary partition.

    Uses :attr:`Comparison.effective_operator` so the result already
    reflects a ``NOT (...)`` wrapper — ``taken`` means "this comparison,
    as written, evaluates true for this value".

    Args:
        cmp: The parsed condition.
        known_values: For a level-88 condition-name comparison only
            (:attr:`Comparison.is_condition_name`) — the condition-name's
            declared ``VALUE``/``VALUES`` literals, already quote-stripped
            (see :func:`strip_string_literal`), read straight from the
            real DATA DIVISION AST by the caller (never fabricated here —
            see ``app/behavioral/extraction/extractor.py``). Ignored for
            every other comparison shape.
    """
    op = cmp.effective_operator
    if cmp.is_condition_name:
        return _generate_condition_name_boundary_values(op, known_values)
    if cmp.is_numeric:
        n = Decimal(cmp.literal)
        step = _numeric_step(cmp.literal)
        candidates = [n - step, n, n + step]
        out: list[tuple[str, bool]] = []
        seen: set[Decimal] = set()
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


def _generate_condition_name_boundary_values(
    op: str, known_values: tuple[str, ...]
) -> list[tuple[str, bool]]:
    """Boundary partition for a level-88 condition-name test.

    ``known_values`` is the condition-name's own declared domain — every
    field value that makes it hold is a legitimate "true" boundary point
    (not just one arbitrary member), and one deterministic value outside
    that domain is the "false" point. With no declared domain available
    (``known_values`` empty — the caller could not find the declaration
    in the AST), no boundary value is invented: an empty list means "no
    derivable test", the same honest outcome an unparseable condition
    already produces elsewhere in this module.
    """
    if not known_values:
        return []
    holds = op == "IS-TRUE"
    seen: set[str] = set()
    out: list[tuple[str, bool]] = []
    for v in known_values:
        if v in seen:
            continue
        seen.add(v)
        out.append((v, holds))
    other = "OTHER"
    suffix = 0
    while other in seen:
        suffix += 1
        other = f"OTHER{suffix}"
    out.append((other, not holds))
    return out


def _holds(v: Decimal, op: str, n: Decimal) -> bool:
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


_MAX_COMPOUND_ASSIGNMENTS = 4096


def _underlying_variable(term: Comparison, alias_of: dict[str, str]) -> str:
    """The real data item *term* reads: a level-88 condition-name is a
    condition on its parent data item, so several condition-names (and
    ordinary comparisons) can constrain one shared variable."""
    return alias_of.get(term.variable, term.variable)


def _term_outcomes(
    compound: CompoundComparison,
    values_by_variable: dict[str, str],
    known_values_by_variable: dict[str, tuple[str, ...]],
    alias_of: dict[str, str],
) -> tuple[bool, ...] | None:
    """Each term's truth under *values_by_variable* (keyed by underlying
    variable), or ``None`` if a term's variable is unassigned."""
    outcomes: list[bool] = []
    for term in compound.terms:
        value = values_by_variable.get(_underlying_variable(term, alias_of))
        if value is None:
            return None
        outcomes.append(
            evaluate_term(term, value, known_values_by_variable.get(term.variable, ()))
        )
    return tuple(outcomes)


def generate_compound_boundary_values(
    compound: CompoundComparison,
    known_values_by_variable: dict[str, tuple[str, ...]] | None = None,
    alias_of: dict[str, str] | None = None,
) -> list[tuple[dict[str, str], bool]]:
    """Deterministic ``[({variable: value, ...}, condition_holds), ...]``
    boundary partition for a compound ``AND``/``OR`` condition.

    Each case is a *complete* assignment of one value to every distinct
    underlying variable *compound*'s terms read. Candidate values per
    variable are the union of each term's own :func:`generate_boundary_values`
    output (never invented here); the cases are then found by searching the
    (small, capped) product of those candidates for an assignment whose
    per-term truth vector is the one a case needs, and every returned case
    is therefore verified by :func:`evaluate_term` -- a case that cannot be
    realised (e.g. two conditions on the same variable that contradict each
    other) is dropped, never fabricated.

    Semantics (per this task's own definition, not assumed):

    * **AND** -- the evidence must satisfy the whole conjunction: one case
      where *every* term holds (``True``), plus one case where exactly one
      term (the first one for which that is realisable) does not hold
      (``False``) -- a minimal "the guard fails when even one conjunct
      doesn't" demonstration.
    * **OR** -- the evidence may satisfy an appropriate branch: one case
      where *every* term does not hold (``False``), plus one case per term
      where *that* term alone holds (``True``).

    Args:
        compound: The parsed compound condition.
        known_values_by_variable: ``{condition-name: declared values}`` for
            every level-88 term (read from the real DATA DIVISION AST by
            the caller). A condition-name term with no declared values makes
            the whole compound underivable (``[]``): its truth cannot be
            evaluated, so it must not be guessed.
        alias_of: ``{condition-name: parent data item}``. Terms on
            condition-names sharing a parent constrain one variable, so the
            cases assign the *parent* (real COBOL has one storage location,
            not one per condition-name). Absent entries mean the term reads
            its own variable.
    """
    kvs = known_values_by_variable or {}
    aliases = alias_of or {}

    for term in compound.terms:
        if term.is_condition_name and not kvs.get(term.variable):
            return []

    candidates: dict[str, list[str]] = {}
    for term in compound.terms:
        bucket = candidates.setdefault(_underlying_variable(term, aliases), [])
        for value, _ in generate_boundary_values(term, kvs.get(term.variable, ())):
            if value not in bucket:
                bucket.append(value)

    variables = sorted(candidates)
    size = 1
    for var in variables:
        size *= len(candidates[var])
    if size == 0 or size > _MAX_COMPOUND_ASSIGNMENTS:
        return []

    by_vector: dict[tuple[bool, ...], dict[str, str]] = {}
    for combo in itertools.product(*(candidates[v] for v in variables)):
        assignment = dict(zip(variables, combo, strict=True))
        vector = _term_outcomes(compound, assignment, kvs, aliases)
        if vector is not None:
            by_vector.setdefault(vector, assignment)

    n = len(compound.terms)
    cases: list[tuple[dict[str, str], bool]] = []

    if compound.connector == "AND":
        all_true = (True,) * n
        if all_true not in by_vector:
            return []
        cases.append((dict(by_vector[all_true]), True))
        for i in range(n):
            one_false = tuple(j != i for j in range(n))
            if one_false in by_vector:
                cases.append((dict(by_vector[one_false]), False))
                break

    elif compound.connector == "OR":
        all_false = (False,) * n
        if all_false in by_vector:
            cases.append((dict(by_vector[all_false]), False))
        for i in range(n):
            one_true = tuple(j == i for j in range(n))
            if one_true in by_vector:
                cases.append((dict(by_vector[one_true]), True))

    return cases


def evaluate_compound(
    compound: CompoundComparison,
    values_by_variable: dict[str, str],
    known_values_by_variable: dict[str, tuple[str, ...]] | None = None,
    alias_of: dict[str, str] | None = None,
) -> bool:
    """Evaluate *compound* against a ``{underlying variable: value}``
    assignment, combining each term's own truth value (via
    :func:`evaluate_term`) with *compound*'s connector. A term whose
    variable is unassigned is treated as not holding.
    """
    kvs = known_values_by_variable or {}
    aliases = alias_of or {}
    results = []
    for term in compound.terms:
        value = values_by_variable.get(_underlying_variable(term, aliases))
        if value is None:
            results.append(False)
            continue
        results.append(evaluate_term(term, value, kvs.get(term.variable, ())))
    if compound.connector == "AND":
        return all(results)
    return any(results)


def evaluate_term(
    cmp: Comparison, value: str, known_values: tuple[str, ...] = ()
) -> bool:
    """Whether *value* satisfies single term *cmp* — the same evaluation
    :func:`generate_boundary_values`'s own candidates were generated to
    satisfy, exposed as its own function so both a single-term caller and
    :func:`evaluate_compound` share one implementation instead of two."""
    op = cmp.effective_operator
    if cmp.is_condition_name:
        return (value in known_values) == (op == "IS-TRUE")
    if cmp.is_numeric:
        v, n = Decimal(value), Decimal(cmp.literal)
        return _holds(v, op, n)
    return _holds_str(value, op, cmp.literal)
