"""
Program Parser.

Purpose:
    Coordinate top-level COBOL program parsing.  The
    :class:`ProgramParser` is the primary entry point that orchestrates
    division-level parsers and assembles the final
    :class:`~app.parser.ast.program.ProgramNode`.

    In this milestone the IDENTIFICATION DIVISION and DATA DIVISION are
    parsed.  Future tasks will add ENVIRONMENT and PROCEDURE division
    parsers that are invoked from here.

Responsibilities:
    - Accept a ``list[Token]`` and return a
      :class:`~app.parser.ast.program.ProgramNode`.
    - Detect whether an IDENTIFICATION DIVISION is present and delegate
      to :class:`~app.parser.syntax.identification_parser.IdentificationDivisionParser`.
    - Satisfy :class:`~app.parser.syntax.parser_interfaces.ParserProtocol`
      structurally.

Non-responsibilities:
    - Procedure Division parsing (future task).
    - Statement or expression parsing.
    - COPY book expansion.
    - Semantic analysis.

Dependencies:
    - :mod:`app.parser.ast.program`                    — ``ProgramNode``.
    - :mod:`app.parser.ast.identification`             — ``IdentificationDivisionNode``.
    - :mod:`app.parser.ast.data`                       — ``DataDivisionNode``.
    - :mod:`app.parser.lexer.token`                    — ``Token``.
    - :mod:`app.parser.lexer.token_types`              — ``TokenType``.
    - :mod:`app.parser.syntax.token_stream`            — ``TokenStream``.
    - :mod:`app.parser.syntax.parser_state`            — ``ParserState``.
    - :mod:`app.parser.syntax.identification_parser`   — ``IdentificationDivisionParser``.
    - :mod:`app.parser.syntax.data_parser`             — ``DataDivisionParser``.
    - Python standard library only.

Examples:
    Parsing a minimal COBOL program::

        from app.parser.syntax.program_parser import ProgramParser
        from app.parser.lexer.token import Token
        from app.parser.lexer.token_types import TokenType
        from app.parser.lexer.position import Position

        pos = Position(line=1, column=1, offset=0, filename="prog.cbl")
        tokens = [Token(type=TokenType.EOF, lexeme="", position=pos)]
        parser = ProgramParser()
        program = parser.parse(tokens)
        # ProgramNode with identification_division=None

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.parser.ast.data import DataDivisionNode
from app.parser.ast.identification import IdentificationDivisionNode
from app.parser.ast.program import ProgramNode
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType
from app.parser.syntax.data_parser import DataDivisionParser
from app.parser.syntax.identification_parser import IdentificationDivisionParser
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.token_stream import TokenStream

__all__ = ["ProgramParser"]


class ProgramParser:
    """
    Top-level COBOL program parser.

    :class:`ProgramParser` coordinates parsing of all four COBOL
    divisions.  Currently the IDENTIFICATION DIVISION and DATA DIVISION
    are implemented; the remaining divisions are left to future tasks.

    The class satisfies
    :class:`~app.parser.syntax.parser_interfaces.ParserProtocol`
    structurally, so it can be used wherever the protocol is expected.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> from app.parser.lexer.token import Token
        >>> from app.parser.lexer.token_types import TokenType
        >>> pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        >>> eof = Token(type=TokenType.EOF, lexeme="", position=pos)
        >>> parser = ProgramParser()
        >>> program = parser.parse([eof])
        >>> program.identification_division is None
        True
    """

    def __init__(self) -> None:
        """Initialise the parser and its division sub-parsers."""
        self._identification_parser = IdentificationDivisionParser()
        self._data_parser = DataDivisionParser()

    def parse(self, tokens: list[Token]) -> ProgramNode:
        """
        Parse a token stream and return the root ``ProgramNode``.

        The token list must be non-empty and must end with a
        ``TokenType.EOF`` sentinel.

        Args:
            tokens:
                Ordered list of :class:`~app.parser.lexer.token.Token`
                objects produced by the COBOL lexer.  Must end with
                ``TokenType.EOF``.

        Returns:
            A :class:`~app.parser.ast.program.ProgramNode` populated
            with any divisions found in the token stream.

        Raises:
            ValueError:
                If *tokens* is empty (propagated from
                :class:`~app.parser.syntax.token_stream.TokenStream`).
            ParserError:
                If the token stream contains a syntactic error.
        """
        logger.debug("ProgramParser.parse() called with {} token(s).", len(tokens))

        stream = TokenStream(tokens)
        state = ParserState(stream)
        program = self._parse_program(state)

        logger.debug("ProgramParser.parse() completed. errors={}.", state.error_count)
        return program

    # ------------------------------------------------------------------
    # Top-level grammar rule
    # ------------------------------------------------------------------

    def _parse_program(self, state: ParserState) -> ProgramNode:
        """
        Parse the top-level program rule.

        Grammar (this task)::

            program ::=
                [ identification-division ]
                [ data-division ]
                EOF

        Args:
            state: The active :class:`~app.parser.syntax.parser_state.ParserState`.

        Returns:
            A populated :class:`~app.parser.ast.program.ProgramNode`.
        """
        stream = state.stream
        start = stream.current().position

        identification: IdentificationDivisionNode | None = None
        data: DataDivisionNode | None = None

        # Detect IDENTIFICATION DIVISION
        if self._is_identification_division(state):
            identification = self._identification_parser.parse(state)

        # Detect DATA DIVISION
        if self._is_data_division(state):
            data = self._data_parser.parse(state)

        end = stream.current().position

        return ProgramNode(
            start_position=start,
            end_position=end,
            identification_division=identification,
            data_division=data,
        )

    # ------------------------------------------------------------------
    # Division detection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_identification_division(state: ParserState) -> bool:
        """
        Return ``True`` if the stream is positioned on an IDENTIFICATION DIVISION header.

        Looks at the current token (``IDENTIFICATION``) and the next
        token (``DIVISION``) without consuming either.

        Args:
            state: The active :class:`~app.parser.syntax.parser_state.ParserState`.

        Returns:
            ``True`` if the next two tokens are ``IDENTIFICATION DIVISION``.
        """
        stream = state.stream
        tok = stream.current()
        if tok.type is not TokenType.KEYWORD:
            return False
        if tok.lexeme.upper() != "IDENTIFICATION":
            return False
        next_tok = stream.peek()
        if next_tok.type is not TokenType.KEYWORD:
            return False
        return next_tok.lexeme.upper() == "DIVISION"

    @staticmethod
    def _is_data_division(state: ParserState) -> bool:
        """
        Return ``True`` if the stream is positioned on a DATA DIVISION header.

        Looks at the current token (``DATA``) and the next token
        (``DIVISION``) without consuming either.

        Args:
            state: The active :class:`~app.parser.syntax.parser_state.ParserState`.

        Returns:
            ``True`` if the next two tokens are ``DATA DIVISION``.
        """
        stream = state.stream
        tok = stream.current()
        if tok.type is not TokenType.KEYWORD:
            return False
        if tok.lexeme.upper() != "DATA":
            return False
        next_tok = stream.peek()
        if next_tok.type is not TokenType.KEYWORD:
            return False
        return next_tok.lexeme.upper() == "DIVISION"
