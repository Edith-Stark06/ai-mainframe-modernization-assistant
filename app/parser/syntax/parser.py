"""
COBOL Recursive Descent Parser.

Purpose:
    Consume a token stream produced by the COBOL lexer and return the
    root :class:`~app.parser.ast.program.ProgramNode` of the Abstract
    Syntax Tree.

    This module establishes the parser framework: the
    :class:`CobolParser` class, its entry-point :meth:`~CobolParser.parse`
    method, and the delegation chain to the
    :class:`~app.parser.syntax.token_stream.TokenStream` and
    :class:`~app.parser.syntax.parser_state.ParserState` helpers.

    No COBOL grammar is parsed in this task — ``parse()`` returns an
    empty :class:`~app.parser.ast.program.ProgramNode` (all divisions
    ``None``).  Concrete grammar rules for divisions, sections,
    paragraphs, and statements will be added in subsequent tasks.

Responsibilities:
    - Accept a ``list[Token]`` and wrap it in a
      :class:`~app.parser.syntax.token_stream.TokenStream`.
    - Create a :class:`~app.parser.syntax.parser_state.ParserState` to
      track navigation and error count.
    - Expose :meth:`~CobolParser.parse` returning a
      :class:`~app.parser.ast.program.ProgramNode`.
    - Satisfy :class:`~app.parser.syntax.parser_interfaces.ParserProtocol`
      so it can be used wherever the protocol is expected.

Non-responsibilities (out of scope for this task):
    - Identification Division parsing.
    - Data Division parsing.
    - Procedure Division parsing.
    - Statement or expression parsing.
    - COPY book expansion.
    - Semantic analysis.

Dependencies:
    - :mod:`app.parser.ast.program`           — ``ProgramNode``.
    - :mod:`app.parser.lexer.token`           — ``Token``.
    - :mod:`app.parser.lexer.position`        — ``Position``.
    - :mod:`app.parser.lexer.token_types`     — ``TokenType``.
    - :mod:`app.parser.syntax.token_stream`   — ``TokenStream``.
    - :mod:`app.parser.syntax.parser_state`   — ``ParserState``.
    - :mod:`app.parser.syntax.parser_errors`  — typed error classes.
    - Python standard library only.

Examples:
    Parsing an empty token stream (EOF-only)::

        from app.parser.syntax.parser import CobolParser
        from app.parser.lexer.token import Token
        from app.parser.lexer.token_types import TokenType
        from app.parser.lexer.position import Position

        pos = Position(line=1, column=1, offset=0, filename="prog.cbl")
        tokens = [Token(type=TokenType.EOF, lexeme="", position=pos)]
        parser = CobolParser()
        program = parser.parse(tokens)
        # ProgramNode with all divisions None

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.parser.ast.program import ProgramNode
from app.parser.lexer.token import Token
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.token_stream import TokenStream

__all__ = ["CobolParser"]


class CobolParser:
    """
    Recursive descent COBOL parser.

    :class:`CobolParser` is the primary entry point for converting a
    flat list of :class:`~app.parser.lexer.token.Token` objects into a
    tree of :class:`~app.parser.ast.node.ASTNode` objects rooted at a
    :class:`~app.parser.ast.program.ProgramNode`.

    The class satisfies
    :class:`~app.parser.syntax.parser_interfaces.ParserProtocol`
    structurally — any code that accepts ``ParserProtocol`` will accept
    a :class:`CobolParser` instance.

    Grammar rules are **not** implemented in this task.  Calling
    :meth:`parse` returns an empty ``ProgramNode`` (all four division
    fields are ``None``).  Grammar methods will be added as the project
    progresses through subsequent milestones.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> from app.parser.lexer.token import Token
        >>> from app.parser.lexer.token_types import TokenType
        >>> pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        >>> eof = Token(type=TokenType.EOF, lexeme="", position=pos)
        >>> parser = CobolParser()
        >>> program = parser.parse([eof])
        >>> program.identification_division is None
        True
    """

    def parse(self, tokens: list[Token]) -> ProgramNode:
        """
        Parse a token stream and return the root ``ProgramNode``.

        The token list *must* be non-empty and end with a
        ``TokenType.EOF`` sentinel.  The :class:`TokenStream` enforces
        this contract.

        In the current (framework-only) implementation no grammar rules
        are applied: the method validates that the stream contains at
        least an EOF token and returns an empty
        :class:`~app.parser.ast.program.ProgramNode` whose source span
        covers the entire token list.

        Args:
            tokens:
                Ordered list of :class:`~app.parser.lexer.token.Token`
                objects produced by
                :class:`~app.parser.lexer.lexer.CobolLexer`.
                Must not be empty and must end with ``TokenType.EOF``.

        Returns:
            The root :class:`~app.parser.ast.program.ProgramNode` with
            all four division fields set to ``None`` (no grammar yet).

        Raises:
            ValueError:
                If *tokens* is empty (propagated from
                :class:`~app.parser.syntax.token_stream.TokenStream`).
            UnexpectedEOFError:
                If the stream is exhausted before parsing is complete
                (will become relevant once grammar rules are added).
        """
        logger.debug("CobolParser.parse() called with {} token(s).", len(tokens))

        stream = TokenStream(tokens)
        state = ParserState(stream)

        program = self._parse_program(state)

        logger.debug("CobolParser.parse() completed. errors={}.", state.error_count)
        return program

    # ------------------------------------------------------------------
    # Internal grammar entry point (framework stub)
    # ------------------------------------------------------------------

    def _parse_program(self, state: ParserState) -> ProgramNode:
        """
        Parse the top-level COBOL program.

        Framework stub: does not parse any grammar.  Returns an empty
        :class:`~app.parser.ast.program.ProgramNode` whose
        ``start_position`` and ``end_position`` both reference the
        first token in the stream.

        Future tasks will add calls to ``_parse_identification_division``,
        ``_parse_environment_division``, etc. from this method.

        Args:
            state: The active :class:`~app.parser.syntax.parser_state.ParserState`.

        Returns:
            A :class:`~app.parser.ast.program.ProgramNode` with all
            division fields set to ``None``.
        """
        start = state.current_token.position
        end = state.current_token.position

        return ProgramNode(
            start_position=start,
            end_position=end,
        )
