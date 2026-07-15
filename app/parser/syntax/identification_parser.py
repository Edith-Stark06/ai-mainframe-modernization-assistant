"""
Identification Division Parser.

Purpose:
    Implement the recursive descent grammar rules that recognise the
    COBOL IDENTIFICATION DIVISION and its clauses.

    The IDENTIFICATION DIVISION has this general structure::

        IDENTIFICATION DIVISION.
        PROGRAM-ID. <program-name> .
        [AUTHOR. <comment-entry> .]
        [INSTALLATION. <comment-entry> .]
        [DATE-WRITTEN. <comment-entry> .]
        [DATE-COMPILED. <comment-entry> .]
        [SECURITY. <comment-entry> .]

Responsibilities:
    - Recognise the ``IDENTIFICATION DIVISION .`` header.
    - Parse the mandatory PROGRAM-ID clause.
    - Parse optional AUTHOR, INSTALLATION, DATE-WRITTEN, DATE-COMPILED,
      and SECURITY clauses.
    - Raise :class:`~app.parser.syntax.parser_exceptions.ParserError`
      for malformed input or unknown clauses.
    - Return an immutable
      :class:`~app.parser.ast.identification.IdentificationDivisionNode`.

Non-responsibilities:
    - Data Division parsing.
    - Procedure Division parsing.
    - Statement or expression parsing.
    - Semantic analysis.
    - COPY book expansion.

Dependencies:
    - :mod:`app.parser.ast.identification` — ``IdentificationDivisionNode``.
    - :mod:`app.parser.ast.clauses`        — clause node types.
    - :mod:`app.parser.lexer.token_types`  — ``TokenType``.
    - :mod:`app.parser.syntax.parser_state`   — ``ParserState``.
    - :mod:`app.parser.syntax.parser_exceptions` — ``ParserError``.
    - Python standard library only.

Examples:
    Parsing an IDENTIFICATION DIVISION from tokens::

        from app.parser.syntax.identification_parser import IdentificationDivisionParser

        parser = IdentificationDivisionParser()
        node = parser.parse(state)
        # node is IdentificationDivisionNode

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.parser.ast.clauses import (
    AuthorClauseNode,
    DateCompiledClauseNode,
    DateWrittenClauseNode,
    InstallationClauseNode,
    ProgramIdClauseNode,
    SecurityClauseNode,
)
from app.parser.ast.identification import IdentificationDivisionNode
from app.parser.lexer.position import Position
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType
from app.parser.syntax.parser_exceptions import ParserError
from app.parser.syntax.parser_state import ParserState

__all__ = ["IdentificationDivisionParser"]

# ---------------------------------------------------------------------------
# Known clause header keywords in the IDENTIFICATION DIVISION
# ---------------------------------------------------------------------------
_CLAUSE_KEYWORDS: frozenset[str] = frozenset(
    {
        "PROGRAM-ID",
        "AUTHOR",
        "INSTALLATION",
        "DATE-WRITTEN",
        "DATE-COMPILED",
        "SECURITY",
    }
)

# Keywords that signal the start of another division (terminates this one)
_DIVISION_HEADERS: frozenset[str] = frozenset(
    {
        "ENVIRONMENT",
        "DATA",
        "PROCEDURE",
    }
)


class IdentificationDivisionParser:
    """
    Recursive descent parser for the COBOL IDENTIFICATION DIVISION.

    Instantiate once and call :meth:`parse` with the active
    :class:`~app.parser.syntax.parser_state.ParserState`.  The state's
    :class:`~app.parser.syntax.token_stream.TokenStream` cursor must be
    positioned on the ``IDENTIFICATION`` keyword when :meth:`parse` is
    called.

    Examples:
        >>> # (see module docstring for full usage)
        >>> parser = IdentificationDivisionParser()
        >>> isinstance(parser, IdentificationDivisionParser)
        True
    """

    def parse(self, state: ParserState) -> IdentificationDivisionNode:
        """
        Parse the IDENTIFICATION DIVISION from the current stream position.

        Grammar rule::

            identification-division ::=
                IDENTIFICATION DIVISION PERIOD
                program-id-clause
                ( author-clause
                | installation-clause
                | date-written-clause
                | date-compiled-clause
                | security-clause )*

        Args:
            state:
                The active :class:`~app.parser.syntax.parser_state.ParserState`.
                The cursor must be on the ``IDENTIFICATION`` keyword.

        Returns:
            A fully populated, immutable
            :class:`~app.parser.ast.identification.IdentificationDivisionNode`.

        Raises:
            ParserError:
                If the header is malformed, a required token is missing,
                or an unknown clause keyword is encountered.
        """
        stream = state.stream
        start = stream.current().position

        logger.debug("Parsing IDENTIFICATION DIVISION at {}.", start)

        # ----------------------------------------------------------------
        # IDENTIFICATION DIVISION .
        # ----------------------------------------------------------------
        self._expect_keyword(stream.advance(), "IDENTIFICATION")
        self._expect_keyword(stream.advance(), "DIVISION")
        stream.expect(TokenType.PERIOD)

        # ----------------------------------------------------------------
        # Clause collection
        # ----------------------------------------------------------------
        program_id: ProgramIdClauseNode | None = None
        author: AuthorClauseNode | None = None
        installation: InstallationClauseNode | None = None
        date_written: DateWrittenClauseNode | None = None
        date_compiled: DateCompiledClauseNode | None = None
        security: SecurityClauseNode | None = None

        while not stream.eof():
            tok = stream.current()

            # Stop when we reach the next division header or end of file
            if tok.type is TokenType.KEYWORD:
                upper = tok.lexeme.upper()
                if upper in _DIVISION_HEADERS:
                    break
                if upper == "DIVISION":
                    # A bare DIVISION keyword means the previous keyword
                    # was a division name — we've overshot; stop.
                    break

            if tok.type is TokenType.EOF:
                break

            # Only KEYWORD tokens can open a clause
            if tok.type is not TokenType.KEYWORD:
                raise ParserError(
                    f"expected a clause keyword, got {tok.lexeme!r}",
                    line=tok.position.line,
                    column=tok.position.column,
                    offset=tok.position.offset,
                )

            keyword = tok.lexeme.upper()

            if keyword not in _CLAUSE_KEYWORDS:
                raise ParserError(
                    f"unknown IDENTIFICATION DIVISION clause: {tok.lexeme!r}",
                    line=tok.position.line,
                    column=tok.position.column,
                    offset=tok.position.offset,
                )

            if keyword == "PROGRAM-ID":
                program_id = self._parse_program_id(state)
            elif keyword == "AUTHOR":
                author = self._parse_author(state)
            elif keyword == "INSTALLATION":
                installation = self._parse_installation(state)
            elif keyword == "DATE-WRITTEN":
                date_written = self._parse_date_written(state)
            elif keyword == "DATE-COMPILED":
                date_compiled = self._parse_date_compiled(state)
            elif keyword == "SECURITY":
                security = self._parse_security(state)

        end = stream.current().position

        return IdentificationDivisionNode(
            start_position=start,
            end_position=end,
            program_id=program_id,
            author=author,
            installation=installation,
            date_written=date_written,
            date_compiled=date_compiled,
            security=security,
        )

    # ------------------------------------------------------------------
    # Clause parsers
    # ------------------------------------------------------------------

    def _parse_program_id(self, state: ParserState) -> ProgramIdClauseNode:
        """
        Parse ``PROGRAM-ID . <name> .``

        Args:
            state: Active parser state; cursor on the PROGRAM-ID keyword.

        Returns:
            :class:`~app.parser.ast.clauses.ProgramIdClauseNode`.

        Raises:
            ParserError: If the clause is malformed.
        """
        stream = state.stream
        start = stream.current().position
        stream.advance()  # consume PROGRAM-ID
        stream.expect(TokenType.PERIOD)  # consume .

        name_tok = stream.current()
        if name_tok.type is TokenType.EOF:
            raise ParserError(
                "expected program name after PROGRAM-ID.",
                line=name_tok.position.line,
                column=name_tok.position.column,
                offset=name_tok.position.offset,
            )
        if name_tok.type not in (TokenType.IDENTIFIER, TokenType.KEYWORD):
            raise ParserError(
                f"expected program name, got {name_tok.lexeme!r}",
                line=name_tok.position.line,
                column=name_tok.position.column,
                offset=name_tok.position.offset,
            )
        value = name_tok.lexeme
        stream.advance()  # consume name

        end = stream.current().position
        stream.expect(TokenType.PERIOD)  # consume trailing .

        return ProgramIdClauseNode(
            start_position=start,
            end_position=end,
            value=value,
        )

    def _parse_comment_clause(
        self, state: ParserState, clause_name: str
    ) -> tuple[str, Position, Position]:
        """
        Parse a comment-entry clause: ``<KEYWORD> . <value-tokens> .``

        Comment-entry clauses (AUTHOR, INSTALLATION, DATE-WRITTEN,
        DATE-COMPILED, SECURITY) follow the same pattern: a keyword,
        a period, one or more value tokens, and a closing period.

        Args:
            state:       Active parser state.
            clause_name: The keyword name (for error messages).

        Returns:
            A ``(value, start_pos, end_pos)`` triple.

        Raises:
            ParserError: If the period or value is missing.
        """
        stream = state.stream
        start = stream.current().position
        stream.advance()  # consume keyword
        stream.expect(TokenType.PERIOD)  # consume .

        # Collect all tokens up to (but not including) the next period
        parts: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.PERIOD:
                break
            if tok.type is TokenType.KEYWORD and tok.lexeme.upper() in (
                _CLAUSE_KEYWORDS | _DIVISION_HEADERS | {"DIVISION"}
            ):
                # Next clause / division started without a closing period
                raise ParserError(
                    f"missing period after {clause_name} value",
                    line=tok.position.line,
                    column=tok.position.column,
                    offset=tok.position.offset,
                )
            parts.append(tok.lexeme)
            stream.advance()

        end = stream.current().position

        if not parts:
            # Allow empty comment entries (AUTHOR. .) — value is empty string
            pass

        stream.expect(TokenType.PERIOD)  # consume closing .

        return " ".join(parts), start, end

    def _parse_author(self, state: ParserState) -> AuthorClauseNode:
        """Parse ``AUTHOR . <value> .``"""
        value, start, end = self._parse_comment_clause(state, "AUTHOR")
        return AuthorClauseNode(start_position=start, end_position=end, value=value)

    def _parse_installation(self, state: ParserState) -> InstallationClauseNode:
        """Parse ``INSTALLATION . <value> .``"""
        value, start, end = self._parse_comment_clause(state, "INSTALLATION")
        return InstallationClauseNode(
            start_position=start, end_position=end, value=value
        )

    def _parse_date_written(self, state: ParserState) -> DateWrittenClauseNode:
        """Parse ``DATE-WRITTEN . <value> .``"""
        value, start, end = self._parse_comment_clause(state, "DATE-WRITTEN")
        return DateWrittenClauseNode(
            start_position=start, end_position=end, value=value
        )

    def _parse_date_compiled(self, state: ParserState) -> DateCompiledClauseNode:
        """Parse ``DATE-COMPILED . <value> .``"""
        value, start, end = self._parse_comment_clause(state, "DATE-COMPILED")
        return DateCompiledClauseNode(
            start_position=start, end_position=end, value=value
        )

    def _parse_security(self, state: ParserState) -> SecurityClauseNode:
        """Parse ``SECURITY . <value> .``"""
        value, start, end = self._parse_comment_clause(state, "SECURITY")
        return SecurityClauseNode(start_position=start, end_position=end, value=value)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _expect_keyword(tok: Token, keyword: str) -> None:
        """
        Assert that *tok* is a KEYWORD token with lexeme *keyword*.

        Args:
            tok:     The token to inspect.
            keyword: The expected uppercase keyword string.

        Raises:
            ParserError: If the token does not match.
        """
        if tok.type is not TokenType.KEYWORD or tok.lexeme.upper() != keyword:
            raise ParserError(
                f"expected {keyword!r}, got {tok.lexeme!r}",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )
