"""
Symbol Hierarchy for the COBOL Semantic Analyser.

Purpose:
    Define the immutable, typed value objects that represent every kind of
    symbol the semantic analyser can register in the
    :class:`~app.parser.semantic.context.SymbolTable`.

    Symbols are pure data carriers — they hold the name, declared source
    position, and any kind-specific attributes needed for later analysis
    passes.  They carry *no* references to mutable state and can therefore
    be safely stored in sets, used as dict keys, or serialised.

Responsibilities:
    - Provide :class:`SymbolKind` — an enumeration of the supported symbol
      categories (program, variable, paragraph).
    - Provide :class:`Symbol` — the abstract base for all symbol records.
    - Provide :class:`ProgramSymbol` — represents the top-level program name
      declared by the PROGRAM-ID clause.
    - Provide :class:`VariableSymbol` — represents a data item declared in
      the WORKING-STORAGE SECTION.
    - Provide :class:`ParagraphSymbol` — represents a paragraph label
      declared in the PROCEDURE DIVISION.

Non-responsibilities:
    - Type checking or expression analysis.
    - Symbol resolution (references to other symbols).
    - Control-flow or data-flow analysis.

Dependencies:
    - :mod:`app.parser.lexer.position` — ``Position`` value type.
    - Python standard library only (``dataclasses``, ``enum``).

Examples:
    Creating a VariableSymbol::

        from app.parser.lexer.position import Position
        from app.parser.semantic.symbols import VariableSymbol, SymbolKind

        pos = Position(line=5, column=4, offset=80, filename="prog.cbl")
        sym = VariableSymbol(
            name="CUSTOMER-ID",
            declared_at=pos,
            level=5,
            picture="9(5)",
        )
        sym.kind is SymbolKind.VARIABLE  # True
        sym.name                         # "CUSTOMER-ID"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.parser.lexer.position import Position

__all__ = [
    "ParagraphSymbol",
    "ProgramSymbol",
    "Symbol",
    "SymbolKind",
    "VariableSymbol",
]


@unique
class SymbolKind(Enum):
    """
    Enumeration of the symbol categories supported by the semantic analyser.

    Attributes:
        PROGRAM:
            The top-level program unit declared by the PROGRAM-ID clause.
        VARIABLE:
            A data item declared in the WORKING-STORAGE SECTION.
        PARAGRAPH:
            A paragraph label declared in the PROCEDURE DIVISION.

    Examples:
        >>> SymbolKind.PROGRAM.value
        'program'
        >>> SymbolKind.VARIABLE.value
        'variable'
        >>> SymbolKind.PARAGRAPH.value
        'paragraph'
    """

    PROGRAM = "program"
    VARIABLE = "variable"
    PARAGRAPH = "paragraph"


@dataclass(frozen=True, slots=True)
class Symbol:
    """
    Abstract base for all symbol records.

    Every concrete symbol subclass inherits ``name`` and ``declared_at``
    from this base, and adds kind-specific attributes.

    Attributes:
        name:
            The symbol name as it appears in the COBOL source (uppercased).
        declared_at:
            The source position of the symbol's defining token.

    Examples:
        >>> # Symbol is not meant to be instantiated directly.
        >>> # Use ProgramSymbol, VariableSymbol, or ParagraphSymbol instead.
    """

    name: str
    declared_at: Position

    @property
    def kind(self) -> SymbolKind:
        """
        Return the :class:`SymbolKind` for this symbol.

        Concrete subclasses must override this property to return the
        appropriate enumeration member.

        Returns:
            The :class:`SymbolKind` value for this symbol type.

        Raises:
            NotImplementedError: If called on the abstract base class.
        """
        raise NotImplementedError  # pragma: no cover


@dataclass(frozen=True, slots=True)
class ProgramSymbol(Symbol):
    """
    Symbol representing the top-level COBOL program unit.

    A :class:`ProgramSymbol` is registered when the semantic analyser
    encounters the PROGRAM-ID clause in the IDENTIFICATION DIVISION.
    There is at most one program symbol per compilation unit.

    Attributes:
        name:
            The program name from the PROGRAM-ID clause (uppercased).
        declared_at:
            Source position of the program-name token.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=2, column=12, offset=40, filename="p.cbl")
        >>> sym = ProgramSymbol(name="PAYROLL", declared_at=pos)
        >>> sym.kind.value
        'program'
        >>> sym.name
        'PAYROLL'
    """

    @property
    def kind(self) -> SymbolKind:
        """Return :attr:`SymbolKind.PROGRAM`."""
        return SymbolKind.PROGRAM


@dataclass(frozen=True, slots=True)
class VariableSymbol(Symbol):
    """
    Symbol representing a COBOL data item in the WORKING-STORAGE SECTION.

    :class:`VariableSymbol` records are created for every
    :class:`~app.parser.ast.data_items.DataItemNode` encountered during
    semantic analysis of the DATA DIVISION.  The ``level`` and
    ``picture`` fields carry the structural attributes extracted from the
    AST without performing any type validation.

    Attributes:
        name:
            The data-name string (uppercased).
        declared_at:
            Source position of the data-name token.
        level:
            The COBOL level number (e.g. 1, 5, 77, 88).
        picture:
            The picture string (e.g. ``"9(5)"``), or ``None`` if the item
            is a group item or condition-name with no PIC clause.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=5, column=4, offset=80, filename="p.cbl")
        >>> sym = VariableSymbol(
        ...     name="CUSTOMER-ID", declared_at=pos, level=5, picture="9(5)"
        ... )
        >>> sym.kind.value
        'variable'
        >>> sym.level
        5
    """

    level: int
    picture: str | None = None

    @property
    def kind(self) -> SymbolKind:
        """Return :attr:`SymbolKind.VARIABLE`."""
        return SymbolKind.VARIABLE


@dataclass(frozen=True, slots=True)
class ParagraphSymbol(Symbol):
    """
    Symbol representing a COBOL paragraph label in the PROCEDURE DIVISION.

    :class:`ParagraphSymbol` records are created for every
    :class:`~app.parser.ast.paragraphs.ParagraphNode` encountered during
    semantic analysis of the PROCEDURE DIVISION.

    Attributes:
        name:
            The paragraph label string (uppercased).
        declared_at:
            Source position of the paragraph-label token.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=20, column=1, offset=400, filename="p.cbl")
        >>> sym = ParagraphSymbol(name="MAIN-PARA", declared_at=pos)
        >>> sym.kind.value
        'paragraph'
    """

    @property
    def kind(self) -> SymbolKind:
        """Return :attr:`SymbolKind.PARAGRAPH`."""
        return SymbolKind.PARAGRAPH
