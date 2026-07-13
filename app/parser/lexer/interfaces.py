"""
Lexer Interfaces.

Purpose:
    Define the structural contract that every COBOL lexer implementation
    must satisfy.  Using :class:`typing.Protocol` keeps the interface
    definition entirely decoupled from any concrete implementation,
    enabling structural sub-typing and straightforward test doubles.

Responsibilities:
    - Declare the :class:`ILexer` protocol with its single public
      method :meth:`ILexer.tokenize`.
    - Enforce that the protocol is runtime-checkable so that
      ``isinstance`` guards may be used in diagnostic code.
    - Remain free of any implementation detail; this module contains
      no scanning, regex, or COBOL knowledge.

Dependencies:
    - :mod:`app.parser.lexer.token`       — ``Token`` value type.
    - Python standard library only (``typing``).

Examples:
    Implementing the protocol in a concrete class::

        from app.parser.lexer.interfaces import ILexer
        from app.parser.lexer.token import Token

        class MyLexer:
            def tokenize(self, source: str, filename: str) -> list[Token]:
                ...  # concrete implementation

        # Structural compatibility — no explicit inheritance required.
        def lex(lexer: ILexer, src: str) -> list[Token]:
            return lexer.tokenize(src, filename="<stdin>")

    Verifying protocol conformance at runtime::

        lexer = MyLexer()
        assert isinstance(lexer, ILexer)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.parser.lexer.token import Token

__all__ = ["ILexer"]


@runtime_checkable
class ILexer(Protocol):
    """
    Structural protocol for COBOL lexer implementations.

    Any class that provides a ``tokenize`` method with the correct
    signature satisfies this protocol without requiring explicit
    inheritance.  This allows concrete lexers to remain independent
    of this module and simplifies testing with lightweight fakes.

    Methods:
        tokenize:
            Convert a COBOL source string into an ordered sequence of
            :class:`~app.parser.lexer.token.Token` instances.

    Examples:
        >>> class NullLexer:
        ...     def tokenize(self, source: str, filename: str) -> list[Token]:
        ...         return []
        >>> isinstance(NullLexer(), ILexer)
        True
    """

    def tokenize(self, source: str, filename: str) -> list[Token]:
        """
        Tokenise a COBOL source string.

        Convert the raw COBOL ``source`` text into an ordered list of
        :class:`~app.parser.lexer.token.Token` objects.  The returned
        list must always terminate with a token whose type is
        :attr:`~app.parser.lexer.token_types.TokenType.EOF`.

        Args:
            source:
                The full text of the COBOL source unit to be
                tokenised.  Callers are responsible for decoding the
                source bytes to a Python ``str`` before invoking this
                method.
            filename:
                The name or path of the source file.  Used to populate
                the ``filename`` field of every :class:`Position`
                attached to the returned tokens.

        Returns:
            An ordered :class:`list` of :class:`Token` instances
            covering every character in ``source``, always ending with
            an ``EOF`` token.
        """
        ...
