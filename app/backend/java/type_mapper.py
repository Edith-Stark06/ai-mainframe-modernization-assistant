"""
COBOL → Java Type Mapper.

Purpose:
    Map COBOL semantic type objects (:class:`~app.parser.semantic.types.CobolType`)
    to their Java type equivalents.

    This module is the authoritative source of truth for the
    ``CobolType → Java type string`` mapping used during backend code generation.

Type Mapping Table:

    +-----------------------+-----------+----------------------------------+
    | COBOL Type            | Java Type | Notes                            |
    +=======================+===========+==================================+
    | ``AlphanumericType``  | ``String``| PIC X items                      |
    +-----------------------+-----------+----------------------------------+
    | ``NumericType``       | ``int``   | Integer (``decimal_places == 0``)|
    | (integer)             |           |                                  |
    +-----------------------+-----------+----------------------------------+
    | ``NumericType``       | ``double``| Decimal (``decimal_places > 0``) |
    | (decimal)             |           |                                  |
    +-----------------------+-----------+----------------------------------+
    | ``GroupType``         | ``String``| Treated as alphanumeric aggregate|
    +-----------------------+-----------+----------------------------------+

Responsibilities:
    - Provide :func:`map_cobol_type` — maps a ``CobolType`` to a Java type string.
    - Return ``None`` with a diagnostic message for unsupported types.

Non-responsibilities:
    - PIC clause parsing.
    - Field naming.
    - Code emission.

Dependencies:
    - :mod:`app.parser.semantic.types` — ``CobolType``, ``NumericType``,
      ``AlphanumericType``, ``GroupType``.
    - Python standard library only.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.parser.semantic.types import CobolType

__all__ = ["map_cobol_type"]

# Java type constants
_JAVA_STRING = "String"
_JAVA_INT = "int"
_JAVA_DOUBLE = "double"
_JAVA_BOOLEAN = "boolean"


def map_cobol_type(cobol_type: CobolType) -> tuple[str | None, str | None]:
    """
    Map *cobol_type* to a Java type string.

    Args:
        cobol_type:
            A concrete :class:`~app.parser.semantic.types.CobolType` instance.

    Returns:
        A tuple ``(java_type, diagnostic_message)`` where:

        - ``java_type`` is a non-empty string such as ``"String"`` or ``"int"``
          when mapping succeeds, or ``None`` when the type is unsupported.
        - ``diagnostic_message`` is ``None`` on success or a human-readable
          error string when the type could not be mapped.

    Examples:
        >>> from app.parser.semantic.types import AlphanumericType, NumericType
        >>> from app.backend.java.type_mapper import map_cobol_type
        >>> map_cobol_type(AlphanumericType(length=20))
        ('String', None)
        >>> map_cobol_type(NumericType(digits=5))
        ('int', None)
        >>> map_cobol_type(NumericType(digits=7, decimal_places=2))
        ('double', None)
    """
    from app.parser.semantic.types import (
        AlphanumericType,
        GroupType,
        NumericType,
    )

    if isinstance(cobol_type, AlphanumericType):
        return _JAVA_STRING, None

    if isinstance(cobol_type, NumericType):
        if cobol_type.is_integer:
            return _JAVA_INT, None
        return _JAVA_DOUBLE, None

    if isinstance(cobol_type, GroupType):
        # Group items are represented as String for now
        return _JAVA_STRING, None

    category = getattr(cobol_type, "category", type(cobol_type).__name__)
    return None, (
        f"unsupported COBOL type '{category}'; "
        f"no Java type mapping defined for {type(cobol_type).__name__}"
    )
