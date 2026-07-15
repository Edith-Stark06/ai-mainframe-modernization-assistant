"""
Parser Protocol / Interface.

Purpose:
    Define the structural contract that any COBOL parser implementation
    must satisfy.  Using a :class:`typing.Protocol` keeps the AST layer
    independent of any concrete parser implementation.

Responsibilities:
    - Provide :class:`ParserProtocol` — the structural type that
      all parser implementations must satisfy.
    - Keep the interface minimal: a single ``parse()`` method.

Non-responsibilities:
    - Concrete parsing logic (implemented in future tasks).
    - Lexical analysis.
    - Semantic analysis.

Dependencies:
    - :mod:`app.parser.ast.program`    — ``ProgramNode`` return type.
    - :mod:`app.parser.lexer.token`    — ``Token`` input type.
    - Python standard library only (``typing``).

Examples:
    Annotating a function that accepts any parser::

        from app.parser.syntax.parser_interfaces import ParserProtocol

        def analyse(parser: ParserProtocol, tokens: list[Token]) -> None:
            program = parser.parse(tokens)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.parser.ast.program import ProgramNode
    from app.parser.lexer.token import Token

__all__ = ["ParserProtocol"]


@runtime_checkable
class ParserProtocol(Protocol):
    """
    Structural protocol for COBOL parser implementations.

    Any class that provides a ``parse(tokens)`` method returning a
    :class:`~app.parser.ast.program.ProgramNode` implicitly satisfies
    this protocol, whether or not it explicitly inherits from it.

    The ``@runtime_checkable`` decorator allows ``isinstance()`` checks:

    .. code-block:: python

        assert isinstance(my_parser, ParserProtocol)

    Methods:
        parse:
            Convert a list of :class:`~app.parser.lexer.token.Token`
            objects into a :class:`~app.parser.ast.program.ProgramNode`.

    Examples:
        >>> class ConcreteParser:
        ...     def parse(self, tokens: list) -> object:
        ...         ...
        >>> isinstance(ConcreteParser(), ParserProtocol)
        True
    """

    def parse(self, tokens: list[Token]) -> ProgramNode:
        """
        Parse a token stream into a COBOL program AST.

        Args:
            tokens:
                Ordered :class:`list` of :class:`~app.parser.lexer.token.Token`
                objects produced by :class:`~app.parser.lexer.lexer.CobolLexer`.
                Must end with a ``TokenType.EOF`` token.

        Returns:
            The root :class:`~app.parser.ast.program.ProgramNode` of the
            parsed program.

        Raises:
            :class:`~app.parser.syntax.parser_exceptions.ParserError`:
                If the token stream cannot be parsed according to COBOL
                grammar rules.
        """
        ...
