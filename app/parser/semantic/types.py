"""
COBOL Semantic Type Hierarchy.

Purpose:
    Define an immutable, extensible type model for COBOL data items that is
    independent of the parser AST.  The type objects produced here are the
    *semantic* view of a data item's storage layout and interpretation —
    separate from the syntactic PIC clause string captured in
    :class:`~app.parser.semantic.symbols.VariableSymbol`.

    This module is consumed by
    :class:`~app.parser.semantic.type_builder.TypeBuilder` (pass 4 of the
    semantic pipeline) and by any downstream stage that needs type
    information (IR generation, Java type mapping, storage layout, etc.).

Responsibilities:
    - Provide :class:`UsageType` — enumeration of COBOL USAGE clause values
      that affect binary representation and storage width.
    - Provide :class:`CobolType` — abstract base for all COBOL semantic types.
    - Provide :class:`NumericType` — numeric data items described by a PIC 9
      (or PIC S9) clause.
    - Provide :class:`AlphanumericType` — character-string data items described
      by a PIC X clause.
    - Provide :class:`GroupType` — group (aggregate) records that have no PIC
      clause of their own.
    - Keep every type object immutable and hashable.

Non-responsibilities:
    - PIC clause parsing (delegated to
      :mod:`app.parser.semantic.type_builder`).
    - Type compatibility checking or coercion.
    - Expression typing or arithmetic validation.
    - Storage offset calculation.
    - Java / target-language type mapping.

Design for extensibility:
    The hierarchy is intentionally minimal.  Future COBOL features can be
    added by subclassing :class:`CobolType` without modifying existing types:

    * ``ArrayType``    — OCCURS … TIMES support.
    * ``RedefinesType`` — REDEFINES overlay.
    * ``PointerType``  — USAGE POINTER.
    * ``NationalType`` — PIC N (National / Unicode) characters.
    * ``Utf8Type``     — PIC U (UTF-8, COBOL 2023+).
    * ``IndexType``    — INDEXED BY items.
    * ``ObjectType``   — USAGE OBJECT REFERENCE (OO-COBOL).

    All existing code that accepts a :class:`CobolType` remains unchanged
    because it can use ``isinstance()`` or the :attr:`CobolType.category`
    attribute to dispatch.

Dependencies:
    - Python standard library only (``abc``, ``dataclasses``, ``enum``).

Examples:
    Creating semantic type objects::

        from app.parser.semantic.types import (
            AlphanumericType,
            NumericType,
            UsageType,
        )

        alpha = AlphanumericType(length=30)
        alpha.category  # 'alphanumeric'
        alpha.length    # 30

        signed_comp = NumericType(
            digits=9, signed=True, decimal_places=2, usage=UsageType.COMP
        )
        signed_comp.category  # 'numeric'
        signed_comp.is_integer  # False

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, unique

__all__ = [
    "AlphanumericType",
    "CobolType",
    "GroupType",
    "NumericType",
    "UsageType",
]


# ---------------------------------------------------------------------------
# UsageType — COBOL USAGE clause enumeration
# ---------------------------------------------------------------------------


@unique
class UsageType(Enum):
    """
    Enumeration of COBOL ``USAGE`` clause values.

    The ``USAGE`` clause specifies the internal binary representation of a
    data item, affecting its storage size and the operations that can be
    performed on it efficiently.

    Attributes:
        DISPLAY:
            Standard character-string representation.  This is the default
            when no USAGE clause is specified.  Each digit or character
            occupies exactly one byte.
        COMP:
            Binary representation (alias: ``COMP-4``, ``BINARY``).
            Integer numeric items are stored as two's-complement binary
            integers in 2, 4, or 8 bytes depending on the number of digits.
        COMP_1:
            Single-precision floating-point (IBM mainframe: ``COMP-1``).
            Stored as a 4-byte IEEE-754 float.
        COMP_2:
            Double-precision floating-point (IBM mainframe: ``COMP-2``).
            Stored as an 8-byte IEEE-754 double.
        COMP_3:
            Packed-decimal (BCD) representation (alias: ``PACKED-DECIMAL``).
            Two decimal digits occupy one byte; the final nibble holds the
            sign.
        COMP_5:
            Native binary (machine-native byte order).  Similar to ``COMP``
            but allows the full value range of the underlying integer type.
        INDEX:
            Used for index data items (``INDEXED BY`` operands).
        POINTER:
            Used for POINTER data items (address-sized binary integer).

    Examples:
        >>> UsageType.DISPLAY.value
        'DISPLAY'
        >>> UsageType.COMP.value
        'COMP'
        >>> UsageType.COMP_3.value
        'COMP-3'
    """

    DISPLAY = "DISPLAY"
    COMP = "COMP"
    COMP_1 = "COMP-1"
    COMP_2 = "COMP-2"
    COMP_3 = "COMP-3"
    COMP_5 = "COMP-5"
    INDEX = "INDEX"
    POINTER = "POINTER"


# ---------------------------------------------------------------------------
# CobolType — abstract base
# ---------------------------------------------------------------------------


class CobolType(ABC):
    """
    Abstract base class for all COBOL semantic type objects.

    Every concrete type class inherits from :class:`CobolType` and provides
    a :attr:`category` string and a human-readable :meth:`__repr__`.

    Subclasses must be **immutable** (implement as frozen dataclasses or
    use ``__slots__`` + ``__init__``).

    Attributes:
        category (str):
            A short string identifier for the type family:
            ``'numeric'``, ``'alphanumeric'``, or ``'group'``.

    Examples:
        >>> from app.parser.semantic.types import NumericType
        >>> t = NumericType(digits=5)
        >>> isinstance(t, CobolType)
        True
    """

    @property
    @abstractmethod
    def category(self) -> str:
        """
        Return a short string identifier for this type family.

        Returns:
            One of ``'numeric'``, ``'alphanumeric'``, or ``'group'`` for the
            built-in types; subclasses may return additional values.
        """


# ---------------------------------------------------------------------------
# NumericType
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NumericType(CobolType):
    """
    Semantic type for COBOL numeric data items (PIC 9 / PIC S9).

    A ``NumericType`` captures the numeric precision, sign, decimal-point
    placement, and USAGE of a data item declared with a digit-based PIC
    clause.

    Attributes:
        digits:
            Total number of decimal digits in the picture (excluding the
            sign and decimal point).  For ``PIC 9(5)`` this is ``5``; for
            ``PIC S9(7)V9(2)`` this is ``9``.
        signed:
            ``True`` when the PIC clause begins with ``S`` (e.g.
            ``PIC S9(5)``).  Defaults to ``False``.
        decimal_places:
            Number of digits to the right of the assumed decimal point (the
            ``V`` position).  For ``PIC 9(5)`` this is ``0``; for
            ``PIC 9(5)V9(2)`` this is ``2``.  Defaults to ``0``.
        usage:
            The :class:`UsageType` that governs the binary representation of
            this item.  Defaults to :attr:`UsageType.DISPLAY`.

    Examples:
        >>> from app.parser.semantic.types import NumericType, UsageType
        >>> t = NumericType(digits=5)
        >>> t.category
        'numeric'
        >>> t.is_integer
        True
        >>> t.signed
        False
        >>> NumericType(digits=7, signed=True, decimal_places=2).decimal_places
        2
    """

    digits: int
    signed: bool = False
    decimal_places: int = 0
    usage: UsageType = UsageType.DISPLAY

    @property
    def category(self) -> str:
        """Return ``'numeric'``."""
        return "numeric"

    @property
    def is_integer(self) -> bool:
        """
        Return ``True`` when this numeric type has no fractional digits.

        Examples:
            >>> NumericType(digits=5).is_integer
            True
            >>> NumericType(digits=5, decimal_places=2).is_integer
            False
        """
        return self.decimal_places == 0

    @property
    def total_digits(self) -> int:
        """
        Return the total number of digits including both integer and decimal.

        For ``PIC 9(5)`` this equals :attr:`digits`.  For ``PIC 9(5)V9(2)``
        this is ``7`` (``digits=7``, ``decimal_places=2``).

        Examples:
            >>> NumericType(digits=7, decimal_places=2).total_digits
            7
        """
        return self.digits

    def __repr__(self) -> str:  # pragma: no cover
        sign = "S" if self.signed else ""
        dec = f"V{self.decimal_places}" if self.decimal_places else ""
        return f"NumericType({sign}9({self.digits}){dec}, usage={self.usage.value})"


# ---------------------------------------------------------------------------
# AlphanumericType
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AlphanumericType(CobolType):
    """
    Semantic type for COBOL alphanumeric data items (PIC X).

    An ``AlphanumericType`` captures the fixed character-string width of
    a data item declared with a ``PIC X`` or ``PIC X(n)`` clause.

    Attributes:
        length:
            Number of characters in the item.  For ``PIC X`` this is ``1``;
            for ``PIC X(30)`` this is ``30``.
        usage:
            The :class:`UsageType` for this item.  For alphanumeric items
            this is always :attr:`UsageType.DISPLAY` in standard COBOL;
            the field is provided for completeness.  Defaults to
            :attr:`UsageType.DISPLAY`.

    Examples:
        >>> from app.parser.semantic.types import AlphanumericType
        >>> t = AlphanumericType(length=30)
        >>> t.category
        'alphanumeric'
        >>> t.length
        30
    """

    length: int
    usage: UsageType = UsageType.DISPLAY

    @property
    def category(self) -> str:
        """Return ``'alphanumeric'``."""
        return "alphanumeric"

    def __repr__(self) -> str:  # pragma: no cover
        return f"AlphanumericType(X({self.length}), usage={self.usage.value})"


# ---------------------------------------------------------------------------
# GroupType
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GroupType(CobolType):
    """
    Semantic type for COBOL group (aggregate) data items.

    A group item has no PIC clause of its own; its structure is entirely
    defined by its subordinate data items.  :class:`GroupType` records the
    group name and level number.  In standard COBOL, group items are always
    treated as ``USAGE DISPLAY`` alphanumeric strings when referenced as a
    whole.

    Attributes:
        member_names:
            Ordered tuple of the *names* of the direct subordinate items.
            This is a lightweight reference — the full type information for
            each member is stored in the :class:`~app.parser.semantic.context.SymbolTable`.
            Defaults to an empty tuple (unknown or not yet resolved).

    Examples:
        >>> from app.parser.semantic.types import GroupType
        >>> t = GroupType()
        >>> t.category
        'group'
        >>> t = GroupType(member_names=('CUSTOMER-ID', 'CUSTOMER-NAME'))
        >>> len(t.member_names)
        2
    """

    member_names: tuple[str, ...] = ()

    @property
    def category(self) -> str:
        """Return ``'group'``."""
        return "group"

    def __repr__(self) -> str:  # pragma: no cover
        return f"GroupType(members={list(self.member_names)})"
