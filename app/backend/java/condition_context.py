"""
Type-aware Java comparison and level-88 condition translation.

Purpose:
    :func:`app.backend.java.control_flow_emitter._build_condition` used to turn
    every COBOL comparison into ``<left> <op> <right>`` with no idea what the
    operands *are*.  That is right for numbers and wrong for text: for
    ``IF WS-CODE = 'AUTO'`` it produced ``wsCode == "AUTO"``, and Java ``==`` on
    two ``String`` references asks "same object?", not "same characters?".  It
    happened to be true for a field still holding its compile-time literal
    (both sides are the same interned constant) and false for an equal string
    that came from anywhere else -- a ``MOVE`` from another field, runtime
    input, reflection.

    This module holds the two pieces of knowledge the emitter lacked, and the
    translation that uses them:

    * :class:`ConditionContext` -- the Java type of every declared field and
      the level-88 condition-names (name -> parent item + declared values).
      Both come from information the pipeline already produces (the field list
      the generator is given, and the ``ConditionNameNode`` entries of the
      AST); nothing in the IR changes.
    * :func:`translate_comparison` -- ``=`` / ``!=`` between two operands that
      are *known* to be text becomes a COBOL alphanumeric comparison.
    * :func:`translate_condition_name` -- ``IF condition-name`` becomes a
      comparison of the parent item with each declared value.
    * :func:`translate_figurative_operand` -- a figurative-constant operand
      (``ZERO``/``ZEROS``/``ZEROES``, ``SPACE``/``SPACES``) becomes a
      type-compatible Java literal instead of an undeclared identifier
      reference (task #stage31; see that function's docstring).
    * :attr:`ConditionContext.fields` -- the full
      :class:`~app.backend.java.field_model.JavaField` of every declared
      field, keyed by its Java name.  ``field_types`` above is the flat Java
      type string a comparison needs; ``fields`` is the whole object, which
      also carries the declared PICTURE width/scale a *DISPLAY* needs to
      reproduce COBOL's implicit zero-/space-padding (task #stage31;
      :func:`~app.backend.java.statement_emitter.emit_display` is the
      consumer). Reusing this same context object -- rather than adding a
      second, parallel context type -- keeps one "what do we know about this
      field" carrier threaded through the pipeline.

COBOL alphanumeric comparison
-----------------------------
The shorter operand is padded with spaces, so trailing spaces never matter
(``'AUTO'`` equals ``'AUTO  '``); a field that was never given a value is
blank.  That is what the generated ``_cobolEquals`` helper implements.  Only
*equality* is translated: ordering (``<``/``>``) on text depends on the
collating sequence and is left exactly as before.

Nothing is guessed
------------------
A comparison is treated as text only when **both** operands are known text (a
quoted literal, a ``String`` field, or -- task #stage31 -- a
``SPACE``/``SPACES`` figurative constant, which is text regardless of
context).  A numeric operand, an operand of unknown type (a FILE SECTION
field the backend never declares) or an ordering operator leaves the
comparison exactly as it was.  A condition-name that cannot be translated
safely -- unknown parent, a value of the wrong kind for the parent, a
figurative constant with no proven Java equivalent -- is reported (``BE007``)
and its ``IF`` omitted, as before.

Figurative-constant operands (task #stage31)
---------------------------------------------
``IF WS-BALANCE < ZEROS`` used to translate ``ZEROS`` the same way as any
COBOL identifier -- lowerCamelCase, ``zeros`` -- an undeclared Java field
reference that could never compile.  :func:`translate_figurative_operand`
translates a ``ZERO``/``ZEROS``/``ZEROES`` or ``SPACE``/``SPACES`` operand
using the *other* operand's already-known Java type (a field's declared type,
a quoted literal, or a numeric literal's own shape) via the exact same
:func:`~app.backend.java.value_initializer.translate_value_literal` this
module already uses for ``VALUE`` clauses and level-88 values -- so ``ZERO``
against an ``int`` field is ``0``, against a ``double`` field is ``0.0``, and
``SPACES`` against a ``String`` field is ``""``.  When the other operand's
type cannot be proven, or is the wrong family (``ZERO`` against text,
``SPACES`` against a number), nothing is translated -- the comparison keeps
its old, already-uncompilable shape rather than guess.  ``HIGH-VALUE(S)`` and
``LOW-VALUE(S)`` are deliberately not translated: :mod:`value_initializer`
has no Java representation for them either (a field declared ``VALUE
HIGH-VALUES`` is left uninitialized today), so there is no existing,
provably-correct Java equivalent to reuse, and inventing one (a sentinel
sized to the field's ``PICTURE``) is a separate, unscoped feature.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.backend.java.field_model import JavaField
from app.backend.java.naming import to_java_field_name
from app.backend.java.value_initializer import (
    SPACE_FIGURATIVES,
    ZERO_FIGURATIVES,
    translate_value_literal,
)

__all__ = [
    "COBOL_EQUALS",
    "COBOL_EQUALS_HELPER",
    "ConditionContext",
    "ConditionName",
    "build_condition_context",
    "build_condition_names",
    "translate_comparison",
    "translate_condition_name",
    "translate_figurative_operand",
]

#: Name of the generated alphanumeric-equality helper.  It contains an
#: underscore, which :func:`~app.backend.java.naming.to_java_field_name` can
#: never produce, so it cannot collide with a COBOL-derived name.
COBOL_EQUALS = "_cobolEquals"

#: The helper, emitted (once, after ``run()``) only by a class that uses it.
#: It is deliberately *package-private*: the scanners that read method names
#: back out of generated Java (behavioral extraction, the Java project
#: generator, the chunker) only look at ``public``/``private``/``protected``
#: methods and treat each as a COBOL paragraph -- this is not one.
COBOL_EQUALS_HELPER: tuple[str, ...] = (
    "    // COBOL alphanumeric equality: the shorter operand is padded with spaces,",
    "    // so trailing spaces never matter; a field that was never set is blank.",
    f"    static boolean {COBOL_EQUALS}(String a, String b) {{",
    '        String x = a == null ? "" : a;',
    '        String y = b == null ? "" : b;',
    "        int m = x.length();",
    "        while (m > 0 && x.charAt(m - 1) == ' ') {",
    "            m--;",
    "        }",
    "        int n = y.length();",
    "        while (n > 0 && y.charAt(n - 1) == ' ') {",
    "            n--;",
    "        }",
    "        return x.substring(0, m).equals(y.substring(0, n));",
    "    }",
)

_EQUALITY_OPERATORS = frozenset({"==", "!="})


@dataclass(frozen=True)
class ConditionName:
    """A level-88 entry: a named condition on its parent data item."""

    name: str
    parent: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class ConditionContext:
    """What the emitter needs to know beyond the IR.

    Attributes:
        field_types: ``{java field name: java type}`` of every declared field.
        condition_names: ``{COBOL condition-name (upper case): entry}``.
        fields: ``{java field name: JavaField}`` of every declared field --
            the full object, including the declared PICTURE width/scale
            (task #stage31; see this module's docstring, "Purpose" section,
            fourth bullet).
    """

    field_types: Mapping[str, str] = field(default_factory=dict)
    condition_names: Mapping[str, ConditionName] = field(default_factory=dict)
    fields: Mapping[str, JavaField] = field(default_factory=dict)


def build_condition_context(
    fields: Sequence[JavaField],
    condition_names: Mapping[str, ConditionName] | None = None,
) -> ConditionContext:
    """Build the context for a generation run from its field list."""
    return ConditionContext(
        field_types={f.java_name: f.java_type for f in fields},
        condition_names=dict(condition_names or {}),
        fields={f.java_name: f for f in fields},
    )


def build_condition_names(ast: Any) -> dict[str, ConditionName]:
    """
    Collect every level-88 entry of *ast*'s WORKING-STORAGE SECTION and
    FILE SECTION (task #stage27).

    A level-88 entry is subordinate to the nearest preceding non-88 item (the
    same rule the behavioral extractor applies to the serialized AST), and its
    ``values`` are the literals its ``VALUE``/``VALUES`` clause declared.  An
    entry with no preceding item, or no values, is omitted: there is nothing
    safe to translate. FILE SECTION records are walked the same way, each
    starting its own parent chain (none of the real corpus's FD records
    declares an 88-level today).

    Args:
        ast: A :class:`~app.parser.ast.program.ProgramNode` (or ``None``).

    Returns:
        ``{NAME: ConditionName}``; empty when there is no DATA DIVISION.
    """
    from app.parser.ast.data_items import ConditionNameNode

    data = getattr(ast, "data_division", None)
    working_storage = getattr(data, "working_storage", None)
    file_section = getattr(data, "file_section", None)
    if working_storage is None and file_section is None:
        return {}

    out: dict[str, ConditionName] = {}
    parent: str | None = None

    def walk(items: Sequence[Any]) -> None:
        nonlocal parent
        for item in items:
            if isinstance(item, ConditionNameNode):
                if parent and item.values:
                    name = item.name.upper()
                    out.setdefault(
                        name, ConditionName(name, parent, tuple(item.values))
                    )
            else:
                parent = item.name.upper()
            walk(getattr(item, "children", ()) or ())

    if working_storage is not None:
        walk(working_storage.items)
    if file_section is not None:
        for record in file_section.records:
            parent = None
            walk(record.items)
    return out


# ---------------------------------------------------------------------------
# operand classification
# ---------------------------------------------------------------------------


_NUMERIC_LITERAL_RE = re.compile(r"^[+-]?\d+(\.\d+)?$")


def _is_quoted(operand: str) -> bool:
    return len(operand) >= 2 and operand[0] in "'\"" and operand[-1] == operand[0]


def _is_text(operand: str, context: ConditionContext) -> bool:
    """``True`` for a quoted literal, a field known to be a ``String``, or
    (task #stage31) a ``SPACE``/``SPACES`` figurative constant -- always
    text, independent of *context*."""
    if _is_quoted(operand):
        return True
    if operand.upper() in SPACE_FIGURATIVES:
        return True
    return context.field_types.get(to_java_field_name(operand)) == "String"


def _operand_java_type(operand: str, context: ConditionContext) -> str | None:
    """
    The Java type *operand* is already known to be, for deciding what a
    figurative constant being compared against it should become.

    Returns ``"String"`` for a quoted literal, ``"int"``/``"double"`` for a
    bare numeric literal (matching its own shape, never guessed from a
    ``PICTURE`` this function has no access to), the declared type of a known
    field, or ``None`` when nothing here proves a type -- an undeclared
    field, a paragraph name, or another figurative constant.
    """
    if _is_quoted(operand):
        return "String"
    match = _NUMERIC_LITERAL_RE.match(operand)
    if match is not None:
        return "double" if match.group(1) else "int"
    return context.field_types.get(to_java_field_name(operand))


def translate_figurative_operand(
    operand: str,
    other: str,
    java_operator: str,
    context: ConditionContext | None,
) -> str | None:
    """
    Translate a figurative-constant *operand* into a Java literal, using
    *other* -- the operand it is being compared with -- to pick a
    type-compatible value.

    See the "Figurative-constant operands" section of this module's
    docstring for the full rationale.

    Args:
        operand: The IR operand string that may be a figurative constant.
        other: The IR string of the *other* side of the comparison.
        java_operator: The Java operator (``==``, ``!=``, ``<`` ...) --
            ``SPACE``/``SPACES`` is only translated for an equality
            operator, matching :func:`translate_comparison`'s own
            equality-only restriction on text (ordering on text is COBOL
            collating-sequence semantics this backend does not model).
        context: What is known about the operands' types, or ``None`` --
            with no context nothing is translated, exactly as every other
            optional-context translation in this module.

    Returns:
        A Java literal (``"0"``, ``"0.0"``, ``'""'``), or ``None`` when
        *operand* is not one of the two translated figurative-constant
        families, or *other*'s type cannot be proven compatible with it.
    """
    if context is None:
        return None
    upper = operand.upper()
    other_type = _operand_java_type(other, context)
    if upper in ZERO_FIGURATIVES:
        if other_type in ("int", "double"):
            return translate_value_literal(operand, other_type)
        return None
    if upper in SPACE_FIGURATIVES:
        if other_type == "String" and java_operator in _EQUALITY_OPERATORS:
            return translate_value_literal(operand, "String")
        return None
    return None


# ---------------------------------------------------------------------------
# ordinary comparison
# ---------------------------------------------------------------------------


def translate_comparison(
    left: str,
    java_operator: str,
    right: str,
    context: ConditionContext | None,
) -> str | None:
    """
    Translate ``left <op> right`` as a COBOL text comparison, if it is one.

    Args:
        left / right: IR operand strings.
        java_operator: The Java operator (``==``, ``!=``, ``<`` ...).
        context: What is known about the operands' types, or ``None``.

    Returns:
        ``_cobolEquals(l, r)`` / ``!_cobolEquals(l, r)`` when the operator is
        an equality test and *both* operands are known text; otherwise
        ``None`` -- the caller keeps its unchanged translation (numbers,
        mixed or unknown operands, ordering operators).
    """
    if context is None or java_operator not in _EQUALITY_OPERATORS:
        return None
    if not (_is_text(left, context) and _is_text(right, context)):
        return None

    # Deferred: statement_emitter -> control_flow_emitter -> this module.
    from app.backend.java.statement_emitter import _translate_operand

    def _operand(operand: str) -> str:
        # A SPACE/SPACES operand is why _is_text let this comparison through
        # in the first place when it has no declared field of its own --
        # the generic identifier translator has no idea it means "".
        if operand.upper() in SPACE_FIGURATIVES:
            literal = translate_value_literal(operand, "String")
            if literal is not None:
                return literal
        return _translate_operand(operand)

    call = f"{COBOL_EQUALS}({_operand(left)}, {_operand(right)})"
    return call if java_operator == "==" else f"!{call}"


# ---------------------------------------------------------------------------
# level-88 condition-name
# ---------------------------------------------------------------------------


def translate_condition_name(
    name: str,
    holds: bool,
    context: ConditionContext,
) -> tuple[str | None, str]:
    """
    Translate ``IF <condition-name>`` (``holds=True``) or ``IF NOT
    <condition-name>`` (``holds=False``).

    The condition is true when the parent item equals *any* of the declared
    values, so it becomes a disjunction of comparisons of the parent with each
    value -- text values through the COBOL text comparison, numeric values
    through ``==`` -- and its negation the conjunction of the inequalities.

    Returns:
        ``(java_expression, "")`` on success, ``(None, reason)`` when the
        condition cannot be translated *provably correctly*.
    """
    entry = context.condition_names.get(name.upper())
    if entry is None:
        return None, f"condition-name '{name}' has no declared VALUE/VALUES"

    parent = to_java_field_name(entry.parent)
    parent_type = context.field_types.get(parent)
    if parent_type is None:
        return None, (
            f"the parent item '{entry.parent}' of condition-name '{name}' is not a "
            "declared field"
        )
    if parent_type not in ("String", "int", "double"):
        return None, f"unsupported parent type '{parent_type}' for '{name}'"

    terms: list[str] = []
    for value in entry.values:
        literal = translate_value_literal(value, parent_type)
        if literal is None:
            return None, (
                f"value {value} of condition-name '{name}' has no proven Java "
                f"equivalent for its {parent_type} parent '{entry.parent}'"
            )
        if parent_type == "String":
            call = f"{COBOL_EQUALS}({parent}, {literal})"
            terms.append(call if holds else f"!{call}")
        else:
            terms.append(f"{parent} {'==' if holds else '!='} {literal}")

    joiner = " || " if holds else " && "
    expression = terms[0] if len(terms) == 1 else "(" + joiner.join(terms) + ")"
    return expression, ""
