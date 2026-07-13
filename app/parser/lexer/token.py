"""
Token Model.

Purpose:
    Define the immutable ``Token`` value type that carries the result
    of every lexical classification decision.  A ``Token`` is the
    atomic unit of information exchanged between the lexer and all
    downstream components (parser, semantic analyser, diagnostics
    engine, and IDE services).

Responsibilities:
    - Bind a ``TokenType`` classification, a raw source lexeme, and a
      ``Position`` into a single, indivisible, hashable value.
    - Guarantee immutability so that tokens may be stored in sets,
      used as dict keys, and shared freely across threads without
      defensive copying.
    - Remain free of business logic; the token is a pure data carrier.

Dependencies:
    - :mod:`app.parser.lexer.token_types` — ``TokenType`` enumeration.
    - :mod:`app.parser.lexer.position`    — ``Position`` value type.
    - Python standard library only (``dataclasses``).

Examples:
    Creating a keyword token::

        from app.parser.lexer.token import Token
        from app.parser.lexer.token_types import TokenType
        from app.parser.lexer.position import Position

        pos = Position(line=1, column=8, offset=7, filename="PAYROLL.cbl")
        token = Token(
            type=TokenType.KEYWORD,
            lexeme="IDENTIFICATION",
            position=pos,
        )
        print(token)
        # Token(type=<TokenType.KEYWORD: 'keyword'>, lexeme='IDENTIFICATION',
        #       position=Position(line=1, column=8, offset=7,
        #                        filename='PAYROLL.cbl'))

    Tokens support equality and hashing::

        t1 = Token(type=TokenType.EOF, lexeme="", position=pos)
        t2 = Token(type=TokenType.EOF, lexeme="", position=pos)
        assert t1 == t2

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass

from app.parser.lexer.position import Position
from app.parser.lexer.token_types import TokenType

__all__ = ["Token"]


@dataclass(frozen=True, slots=True)
class Token:
    """
    Immutable lexical token produced by the COBOL lexer.

    A ``Token`` instance is the smallest unit of meaningful source
    information passed between compiler stages.  Its three fields
    together capture *what* the token is (``type``), *what text it
    was* in the source (``lexeme``), and *where* it appeared
    (``position``).

    Because the dataclass is frozen, ``Token`` objects are hashable
    and safe to store in sets or use as dictionary keys.

    Attributes:
        type:
            The syntactic category of this token as defined by
            :class:`~app.parser.lexer.token_types.TokenType`.
        lexeme:
            The exact sequence of characters from the source text that
            produced this token, preserving original casing and
            whitespace-free form.
        position:
            The :class:`~app.parser.lexer.position.Position` of the
            first character of the lexeme within the source file.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> from app.parser.lexer.token_types import TokenType
        >>> pos = Position(line=5, column=12, offset=120, filename="X.cbl")
        >>> tok = Token(type=TokenType.NUMBER, lexeme="42", position=pos)
        >>> tok.type
        <TokenType.NUMBER: 'number'>
        >>> tok.lexeme
        '42'
        >>> tok.position.line
        5
    """

    type: TokenType
    lexeme: str
    position: Position
