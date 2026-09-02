"""
Environment Division Parser.

Purpose:
    Implement the recursive-descent grammar rule that recognises the
    COBOL ENVIRONMENT DIVISION so that a program containing one can
    continue parsing into its DATA and PROCEDURE divisions.

    The ENVIRONMENT DIVISION has this general structure::

        ENVIRONMENT DIVISION.

        CONFIGURATION SECTION.
        SOURCE-COMPUTER. IBM-Z.
        OBJECT-COMPUTER. IBM-Z.

        INPUT-OUTPUT SECTION.
        FILE-CONTROL.
            SELECT ACCOUNT-FILE ASSIGN TO ACCTIN
                ORGANIZATION IS SEQUENTIAL
                FILE STATUS IS WS-ACCT-STATUS.

Scope (deliberately limited — see *Non-responsibilities*):
    No part of the pipeline downstream of the parser (semantic analysis,
    IR construction, flow extraction, modernization scoring) reads
    ENVIRONMENT DIVISION metadata today, so this parser deliberately
    does **not** model the division's contents.  It recognises the
    division and its *section structure*, and represents the result as a
    single :class:`~app.parser.ast.division.DivisionNode` named
    ``"ENVIRONMENT"`` with no children.

    This is a representation boundary, not a parsing shortcut.  The
    parser does not blindly discard tokens until ``DATA DIVISION``: it
    validates that the division contains recognised section headers and
    records a
    :class:`~app.parser.diagnostics.recovery.SyntaxDiagnostic` for
    content that is not a recognised section, so malformed input is
    never silently swallowed.  Section *bodies* are consumed without
    detailed validation; when a downstream consumer needs SELECT/ASSIGN
    or SOURCE-COMPUTER metadata, the body grammar can be added behind
    :meth:`EnvironmentDivisionParser._parse_section` without changing
    the division-level contract.

Responsibilities:
    - Recognise the ``ENVIRONMENT DIVISION .`` header.
    - Recognise the ``CONFIGURATION SECTION .`` and
      ``INPUT-OUTPUT SECTION .`` headers.
    - Consume each recognised section's body up to the next section
      header, the next division header, or end of file.
    - Record a diagnostic for an unsupported section name, and for any
      division-level content that is not a section header at all.
    - Leave the stream positioned exactly on the next division header
      so :class:`~app.parser.syntax.program_parser.ProgramParser` can
      continue with the DATA and PROCEDURE divisions.
    - Return a :class:`~app.parser.ast.division.DivisionNode`.

Non-responsibilities:
    - Modelling CONFIGURATION SECTION paragraphs (SOURCE-COMPUTER,
      OBJECT-COMPUTER, SPECIAL-NAMES, REPOSITORY).
    - Modelling INPUT-OUTPUT SECTION paragraphs (FILE-CONTROL,
      I-O-CONTROL) or SELECT / ASSIGN / ORGANIZATION / FILE STATUS
      clauses.
    - Semantic validation of environment metadata (e.g. checking that a
      ``FILE STATUS`` data name is declared in the DATA DIVISION).

Dependencies:
    - :mod:`app.parser.ast.division`                — ``DivisionNode``.
    - :mod:`app.parser.diagnostics.recovery`        — ``RecoveryContext``.
    - :mod:`app.parser.lexer.token`                 — ``Token``.
    - :mod:`app.parser.lexer.token_types`           — ``TokenType``.
    - :mod:`app.parser.syntax.parser_exceptions`    — ``ParserError``.
    - :mod:`app.parser.syntax.parser_state`         — ``ParserState``.
    - Python standard library only.

Examples:
    Parsing an ENVIRONMENT DIVISION::

        from app.parser.lexer.lexer import CobolLexer
        from app.parser.syntax.environment_parser import EnvironmentDivisionParser
        from app.parser.syntax.parser_state import ParserState
        from app.parser.syntax.token_stream import TokenStream

        source = " ENVIRONMENT DIVISION.\\n CONFIGURATION SECTION.\\n"
        state = ParserState(TokenStream(CobolLexer().tokenize(source)))
        division = EnvironmentDivisionParser().parse(state)
        division.name  # "ENVIRONMENT"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.parser.ast.division import DivisionNode
from app.parser.diagnostics.recovery import RecoveryContext
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType
from app.parser.syntax.parser_exceptions import ParserError
from app.parser.syntax.parser_state import ParserState

__all__ = ["EnvironmentDivisionParser"]

# ---------------------------------------------------------------------------
# Section names recognised inside the ENVIRONMENT DIVISION
# ---------------------------------------------------------------------------
#: These are the only two sections the COBOL standard defines for this
#: division.  They are matched by uppercased lexeme rather than by token
#: type because neither ``CONFIGURATION`` nor ``INPUT-OUTPUT`` is in the
#: lexer's reserved-keyword set, so both are emitted as
#: ``TokenType.IDENTIFIER`` — the same lexeme-matching approach
#: :mod:`app.parser.syntax.data_parser` already uses for ``SECTION``.
_KNOWN_SECTIONS: frozenset[str] = frozenset(
    {
        "CONFIGURATION",
        "INPUT-OUTPUT",
    }
)

# Keywords that signal the start of another division (terminates this one)
_DIVISION_HEADERS: frozenset[str] = frozenset(
    {
        "IDENTIFICATION",
        "DATA",
        "PROCEDURE",
    }
)


class EnvironmentDivisionParser:
    """
    Recursive descent parser for the COBOL ENVIRONMENT DIVISION.

    Instantiate once and call :meth:`parse` with the active
    :class:`~app.parser.syntax.parser_state.ParserState`.  The state's
    :class:`~app.parser.syntax.token_stream.TokenStream` cursor must be
    positioned on the ``ENVIRONMENT`` keyword when :meth:`parse` is
    called.

    Recovery behaviour:
        - Division-level content that is not a recognised section header
          is recorded as a
          :class:`~app.parser.diagnostics.recovery.SyntaxDiagnostic` and
          the stream is synchronised.  Parsing then continues.
        - A section header whose name is not a recognised ENVIRONMENT
          DIVISION section is recorded as a diagnostic; its body is then
          consumed so that a single unsupported section produces one
          diagnostic rather than one per body token.
        - If the ``ENVIRONMENT DIVISION .`` header itself is malformed a
          :class:`~app.parser.syntax.parser_exceptions.ParserError` is
          raised immediately (fatal — we cannot continue without the
          header).  This matches
          :class:`~app.parser.syntax.identification_parser.IdentificationDivisionParser`.

    Examples:
        >>> parser = EnvironmentDivisionParser()
        >>> isinstance(parser, EnvironmentDivisionParser)
        True
    """

    def parse(self, state: ParserState) -> DivisionNode:
        """
        Parse the ENVIRONMENT DIVISION from the current stream position.

        Grammar rule::

            environment-division ::=
                ENVIRONMENT DIVISION PERIOD
                environment-section*

            environment-section ::=
                section-name SECTION PERIOD section-body

            section-name ::= CONFIGURATION | INPUT-OUTPUT

            section-body ::=
                <any tokens up to the next section header,
                 the next division header, or EOF>

        Recoverable errors (recorded as diagnostics, parsing continues):
            - Division-level content that is not a section header.
            - An unsupported section name.

        Fatal errors (raise :class:`~app.parser.syntax.parser_exceptions.ParserError`):
            - ``ENVIRONMENT`` keyword missing.
            - ``DIVISION`` keyword missing after ``ENVIRONMENT``.
            - Period missing after ``ENVIRONMENT DIVISION``.

        Args:
            state:
                The active :class:`~app.parser.syntax.parser_state.ParserState`.
                The cursor must be on the ``ENVIRONMENT`` keyword.

        Returns:
            A :class:`~app.parser.ast.division.DivisionNode` named
            ``"ENVIRONMENT"`` spanning the division.  ``children`` is
            always empty — see the module docstring for why this
            representation is deliberately limited.

        Raises:
            ParserError:
                If the division header is fatally malformed.
        """
        stream = state.stream
        start = stream.current().position

        logger.debug("Parsing ENVIRONMENT DIVISION at {}.", start)

        # ----------------------------------------------------------------
        # ENVIRONMENT DIVISION .  (fatal if header is wrong)
        # ----------------------------------------------------------------
        self._expect_keyword(stream.advance(), "ENVIRONMENT")
        self._expect_keyword(stream.advance(), "DIVISION")
        stream.expect(TokenType.PERIOD)

        # ----------------------------------------------------------------
        # Section collection
        # ----------------------------------------------------------------
        while not stream.eof():
            tok = stream.current()

            if tok.type is TokenType.EOF:
                break

            # Stop cleanly on the next division header, leaving it in the
            # stream for ProgramParser.
            if self._at_division_header(state):
                break

            # Silently consume stray PERIOD tokens.  These appear after
            # panic-mode recovery synchronises to a paragraph boundary
            # (which leaves the period in the stream for the caller).
            if tok.type is TokenType.PERIOD:
                stream.advance()
                continue

            if self._at_section_header(state):
                self._parse_section(state)
                continue

            # Anything else at division level is unexpected.  Record it
            # rather than swallowing it, then synchronise.
            logger.debug(
                "EnvironmentDivisionParser: unexpected token {!r} at division "
                "level; recovering.",
                tok.lexeme,
            )
            before = stream.position
            state.record_and_synchronise(
                message=(
                    "expected an ENVIRONMENT DIVISION section header, "
                    f"got {tok.lexeme!r}"
                ),
                error_token=tok,
                context=RecoveryContext.ENVIRONMENT_DIVISION,
            )
            # Guarantee forward progress.  ``synchronise()`` anchors on a
            # section keyword *without consuming it*, so a token such as
            # WORKING-STORAGE (a lexer keyword listed as a section
            # anchor) would otherwise leave the cursor where it was and
            # spin this loop forever.
            if stream.position == before:
                stream.advance()

        end = stream.current().position

        logger.debug("ENVIRONMENT DIVISION parsed; ends at {}.", end)

        return DivisionNode(
            start_position=start,
            end_position=end,
            name="ENVIRONMENT",
            children=(),
        )

    # ------------------------------------------------------------------
    # Section parsing
    # ------------------------------------------------------------------

    def _parse_section(self, state: ParserState) -> None:
        """
        Consume one ``<name> SECTION .`` header and its body.

        The cursor must be positioned on the section-name token (see
        :meth:`_at_section_header`).  An unrecognised section name is
        recorded as a diagnostic before its body is consumed, so an
        unsupported section costs exactly one diagnostic instead of one
        per body token.

        The body is consumed without detailed validation up to the next
        section header, the next division header, or EOF.

        Args:
            state: The active :class:`~app.parser.syntax.parser_state.ParserState`.
        """
        stream = state.stream
        name_token = stream.advance()  # section name
        stream.advance()  # SECTION
        name = name_token.lexeme.upper()

        if name not in _KNOWN_SECTIONS:
            logger.debug(
                "EnvironmentDivisionParser: unsupported section {!r}; "
                "recording diagnostic and skipping its body.",
                name,
            )
            state.record_and_synchronise(
                message=(
                    f"unsupported ENVIRONMENT DIVISION section: {name_token.lexeme!r}"
                ),
                error_token=name_token,
                context=RecoveryContext.ENVIRONMENT_DIVISION,
            )
        elif stream.current().type is TokenType.PERIOD:
            stream.advance()

        # Consume the section body.
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.EOF:
                break
            if self._at_division_header(state):
                break
            if self._at_section_header(state):
                break
            stream.advance()

    # ------------------------------------------------------------------
    # Boundary detection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _at_section_header(state: ParserState) -> bool:
        """
        Return ``True`` if the cursor is on a ``<name> SECTION`` header.

        Matches *any* section name, not only the supported ones, so that
        an unsupported section still terminates the preceding section's
        body instead of being absorbed into it.  ``SECTION`` is matched
        by lexeme because it is not a reserved lexer keyword.

        Args:
            state: The active :class:`~app.parser.syntax.parser_state.ParserState`.

        Returns:
            ``True`` if the next two tokens are ``<name> SECTION``.
        """
        stream = state.stream
        tok = stream.current()
        if tok.type not in (TokenType.IDENTIFIER, TokenType.KEYWORD):
            return False
        return stream.peek().lexeme.upper() == "SECTION"

    @staticmethod
    def _at_division_header(state: ParserState) -> bool:
        """
        Return ``True`` if the cursor is on another division's header.

        Args:
            state: The active :class:`~app.parser.syntax.parser_state.ParserState`.

        Returns:
            ``True`` if the next two tokens are ``<division> DIVISION``.
        """
        stream = state.stream
        tok = stream.current()
        if tok.type is not TokenType.KEYWORD:
            return False
        if tok.lexeme.upper() not in _DIVISION_HEADERS:
            return False
        next_tok = stream.peek()
        if next_tok.type is not TokenType.KEYWORD:
            return False
        return next_tok.lexeme.upper() == "DIVISION"

    # ------------------------------------------------------------------
    # Header helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _expect_keyword(token: Token, expected: str) -> None:
        """
        Raise :class:`ParserError` unless *token* is the expected keyword.

        Args:
            token: The token to check.
            expected: The expected keyword lexeme (uppercase).

        Raises:
            ParserError: If *token* is not the expected keyword.
        """
        if token.type is not TokenType.KEYWORD or token.lexeme.upper() != expected:
            raise ParserError(
                f"expected {expected!r}, got {token.lexeme!r}",
                line=token.position.line,
                column=token.position.column,
                offset=token.position.offset,
            )
