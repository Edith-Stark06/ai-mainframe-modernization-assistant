"""
COBOL ``VALUE`` clause → Java field initializer expression.

A COBOL data item's ``VALUE`` clause gives it its initial contents.  The
parser captures the clause's literal verbatim (``"'INITIAL'"``, ``"01"``,
``"00065000.00"``, ``"SPACES"``); this module turns that raw literal into the
Java expression that initializes the corresponding field, or reports that no
*provably correct* initializer exists so the field is left uninitialized
exactly as it was before ``VALUE`` clauses were translated.

Why the literal cannot simply be pasted into the Java source
------------------------------------------------------------
* **Leading zeros are octal in Java.**  COBOL numeric literals are routinely
  zero-padded to the picture width (``VALUE 035``, ``VALUE 00500``).  Java
  reads ``035`` as octal 29 and ``00500`` as octal 320 (silently wrong), and
  refuses to compile ``028``/``09`` at all.  Integers are therefore re-emitted
  from their numeric value, never from their spelling.
* **Quotes.**  A COBOL literal is delimited by ``'``; a Java string by ``"``,
  so the content is re-escaped.
* **Figurative constants** (``SPACES``, ``ZERO``) are not values in Java.
* **Range.**  A COBOL integer picture maps to Java ``int``; a literal that
  does not fit an ``int`` would not compile.

String initializers follow the convention the statement emitter already uses
for ``MOVE 'X' TO FIELD`` — the literal is stored as written, without padding
to the picture width — so a freshly initialized field and a field assigned by
``MOVE`` are represented identically.  ``SPACE``/``SPACES`` are therefore the
empty string under that same trailing-blank-insensitive convention.

Nothing is guessed: any literal/type combination not handled here yields
``None`` and the field keeps no initializer.
"""

from __future__ import annotations

import re

__all__ = ["SPACE_FIGURATIVES", "ZERO_FIGURATIVES", "translate_value_literal"]

_JAVA_INT_MAX = 2**31 - 1
_JAVA_INT_MIN = -(2**31)

_INTEGER_RE = re.compile(r"^([+-]?)(\d+)$")
_DECIMAL_RE = re.compile(r"^([+-]?)(\d*)\.(\d+)$")

#: Public so other operand-translation call sites (condition operands in
#: ``app.backend.java.condition_context``, task #stage31) can recognise the
#: same two spelling families this module already translates for ``VALUE``
#: clauses and level-88 values, instead of maintaining a second copy.
SPACE_FIGURATIVES = frozenset({"SPACE", "SPACES"})
ZERO_FIGURATIVES = frozenset({"ZERO", "ZEROS", "ZEROES"})


def _quoted_content(literal: str) -> str | None:
    """Return the text between the delimiters of a quoted COBOL literal."""
    if len(literal) >= 2 and literal[0] == literal[-1] and literal[0] in "'\"":
        return literal[1:-1]
    return None


def _integer_initializer(literal: str) -> str | None:
    """A Java ``int`` initializer, or ``None`` if there is no safe one."""
    if literal.upper() in ZERO_FIGURATIVES:
        return "0"
    match = _INTEGER_RE.match(literal)
    if match is None:
        return None
    number = int(match.group(2))
    if match.group(1) == "-":
        number = -number
    if not _JAVA_INT_MIN <= number <= _JAVA_INT_MAX:
        return None
    return str(number)


def _double_initializer(literal: str) -> str | None:
    """A Java ``double`` initializer, or ``None`` if there is no safe one."""
    if literal.upper() in ZERO_FIGURATIVES:
        return "0.0"
    match = _INTEGER_RE.match(literal)
    if match is not None:
        sign, whole, fraction = match.group(1), match.group(2), "0"
    else:
        match = _DECIMAL_RE.match(literal)
        if match is None:
            return None
        sign, whole, fraction = match.group(1), match.group(2), match.group(3)
    whole = whole.lstrip("0") or "0"
    if sign == "-" and (whole.strip("0") or fraction.strip("0")):
        return f"-{whole}.{fraction}"
    return f"{whole}.{fraction}"


def _string_initializer(literal: str) -> str | None:
    """A Java ``String`` initializer, or ``None`` if there is no safe one."""
    if literal.upper() in SPACE_FIGURATIVES:
        return '""'
    content = _quoted_content(literal)
    if content is None:
        return None
    # Deferred: statement_emitter -> control_flow_emitter -> generator, and
    # generator imports this module, so a top-level import would be circular.
    from app.backend.java.statement_emitter import _escape_java_string_content

    return f'"{_escape_java_string_content(content)}"'


def translate_value_literal(literal: str | None, java_type: str) -> str | None:
    """
    Translate a raw COBOL ``VALUE`` literal into a Java initializer expression.

    Args:
        literal:
            The literal exactly as captured from the ``VALUE`` clause
            (``"'INITIAL'"``, ``"035"``, ``"00065000.00"``, ``"SPACES"``), or
            ``None`` when the item has no ``VALUE`` clause.
        java_type:
            The Java type the backend chose for the field (``"String"``,
            ``"int"`` or ``"double"``).

    Returns:
        The Java expression to place after ``=`` in the field declaration, or
        ``None`` when the item has no ``VALUE`` clause or the literal cannot
        be translated *provably correctly* for *java_type* (a mismatched
        literal kind, an ``int`` overflow, an unsupported figurative constant,
        or an unsupported Java type).

    Examples:
        >>> translate_value_literal("'INITIAL'", "String")
        '"INITIAL"'
        >>> translate_value_literal("SPACES", "String")
        '""'
        >>> translate_value_literal("035", "int")
        '35'
        >>> translate_value_literal("028", "int")
        '28'
        >>> translate_value_literal("00065000.00", "double")
        '65000.00'
        >>> translate_value_literal("0", "double")
        '0.0'
        >>> translate_value_literal("'X'", "int") is None
        True
        >>> translate_value_literal(None, "int") is None
        True
    """
    if literal is None:
        return None
    text = literal.strip()
    if not text:
        return None
    if java_type == "String":
        return _string_initializer(text)
    if java_type == "int":
        return _integer_initializer(text)
    if java_type == "double":
        return _double_initializer(text)
    return None
