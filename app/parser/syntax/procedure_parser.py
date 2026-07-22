"""
Procedure Division Parser.

Purpose:
    Implement the recursive-descent grammar rules that recognise the
    COBOL PROCEDURE DIVISION, its paragraph labels, and the supported
    executable statements within each paragraph.

    The PROCEDURE DIVISION has this general structure (subset supported
    here)::

        PROCEDURE DIVISION.

        MAIN-PARA.
            DISPLAY "HELLO".
            MOVE 1 TO WS-COUNT.
            STOP RUN.

        CLEANUP-PARA.
            GOBACK.

Responsibilities:
    - Recognise the ``PROCEDURE DIVISION .`` header.
    - Recognise paragraph labels (``name .``).
    - Parse supported statement keywords per paragraph:

      - ``DISPLAY operand .``
      - ``MOVE source TO target .``
      - ``STOP RUN .``
      - ``GOBACK .``

    - Recover from missing periods, unsupported statements, and malformed
      statement syntax using panic-mode synchronisation via
      :class:`~app.parser.syntax.parser_state.ParserState`.
    - Construct and return a
      :class:`~app.parser.ast.procedure.ProcedureDivisionNode` populated
      with :class:`~app.parser.ast.paragraphs.ParagraphNode` and their
      :class:`~app.parser.ast.statements.StatementNode` children.
    - Raise :class:`~app.parser.syntax.parser_exceptions.ParserError`
      only for fatal conditions (e.g. malformed division header).

Non-responsibilities:
    - IF, EVALUATE, PERFORM, GO TO, CALL, COMPUTE, ADD, SUBTRACT,
      MULTIPLY, DIVIDE, STRING, UNSTRING, SEARCH, INSPECT statements.
    - SECTION header parsing.
    - DECLARATIVES parsing.
    - Nested program parsing.
    - COPY book expansion.
    - Semantic analysis.

Dependencies:
    - :mod:`app.parser.ast.procedure`    — ``ProcedureDivisionNode``.
    - :mod:`app.parser.ast.paragraphs`   — ``ParagraphNode``.
    - :mod:`app.parser.ast.statements`   — statement node types.
    - :mod:`app.parser.lexer.position`   — ``Position``.
    - :mod:`app.parser.lexer.token`      — ``Token``.
    - :mod:`app.parser.lexer.token_types` — ``TokenType``.
    - :mod:`app.parser.syntax.parser_state`      — ``ParserState``.
    - :mod:`app.parser.syntax.parser_exceptions` — ``ParserError``.
    - :mod:`app.parser.diagnostics.recovery`     — ``RecoveryContext``.
    - Python standard library only.

Examples:
    Parsing a PROCEDURE DIVISION from a token stream::

        from app.parser.syntax.procedure_parser import ProcedureDivisionParser

        parser = ProcedureDivisionParser()
        node = parser.parse(state)
        # node is ProcedureDivisionNode
        # state.diagnostics contains any recovered errors

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.parser.ast.paragraphs import ParagraphNode
from app.parser.ast.procedure import ProcedureDivisionNode
from app.parser.ast.statements import (
    DisplayStatementNode,
    GobackStatementNode,
    MoveStatementNode,
    StatementNode,
    StopRunStatementNode,
    AddStatementNode,
    SubtractStatementNode,
    MultiplyStatementNode,
    DivideStatementNode,
    CallStatementNode,
)
from app.parser.diagnostics.recovery import RecoveryContext
from app.parser.lexer.position import Position
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType
from app.parser.syntax.parser_exceptions import ParserError
from app.parser.syntax.parser_state import ParserState

__all__ = ["ProcedureDivisionParser"]

# ---------------------------------------------------------------------------
# Division boundary keywords — stop parsing when these are seen at the
# PROCEDURE DIVISION level (i.e. another division begins).
# ---------------------------------------------------------------------------
_DIVISION_KEYWORDS: frozenset[str] = frozenset(
    {
        "IDENTIFICATION",
        "ENVIRONMENT",
        "DATA",
    }
)

# ---------------------------------------------------------------------------
# Statement dispatch keywords — these can appear at the statement level
# inside a paragraph.  GOBACK is NOT in the lexer keyword set so it is
# emitted as an IDENTIFIER; we still match it by uppercased lexeme.
# ---------------------------------------------------------------------------
_STATEMENT_LEXEMES: frozenset[str] = frozenset(
    {
        "DISPLAY",
        "MOVE",
        "STOP",
        "GOBACK",
        "ACCEPT",
        "ADD",
        "SUBTRACT",
        "MULTIPLY",
        "DIVIDE",
        "CALL",
    }
)


class ProcedureDivisionParser:
    """
    Recursive-descent parser for the COBOL PROCEDURE DIVISION.

    Instantiate once and call :meth:`parse` with the active
    :class:`~app.parser.syntax.parser_state.ParserState`.  The state's
    token-stream cursor must be positioned on the ``PROCEDURE`` keyword
    when :meth:`parse` is called.

    The parser constructs and returns a
    :class:`~app.parser.ast.procedure.ProcedureDivisionNode` containing
    the parsed paragraphs and their statements.

    Recovery behaviour:
        - Missing period after paragraph label: recorded as diagnostic,
          stream synchronised to next period or paragraph boundary.
        - Unsupported statement keyword: recorded as diagnostic, stream
          synchronised to next period.
        - Malformed statement (e.g. missing operand): recorded as
          diagnostic, stream synchronised to next period.
        - The ``PROCEDURE DIVISION .`` header still raises
          :class:`~app.parser.syntax.parser_exceptions.ParserError` on
          fatal mismatches.

    Examples:
        >>> parser = ProcedureDivisionParser()
        >>> isinstance(parser, ProcedureDivisionParser)
        True
    """

    def parse(self, state: ParserState) -> ProcedureDivisionNode:
        """
        Parse the PROCEDURE DIVISION from the current stream position.

        Grammar rule (supported subset)::

            procedure-division ::=
                PROCEDURE DIVISION PERIOD
                paragraph*

            paragraph ::=
                paragraph-label PERIOD
                statement*

            statement ::=
                display-statement
              | move-statement
              | stop-run-statement
              | goback-statement

        Recoverable errors (recorded as diagnostics, parsing continues):
            - Missing period after paragraph label.
            - Unsupported statement keyword.
            - Malformed statement syntax.

        Fatal errors (raise :class:`~app.parser.syntax.parser_exceptions.ParserError`):
            - ``PROCEDURE`` keyword missing.
            - ``DIVISION`` keyword missing after ``PROCEDURE``.
            - Period missing after ``PROCEDURE DIVISION``.

        Args:
            state:
                The active :class:`~app.parser.syntax.parser_state.ParserState`.
                The cursor must be on the ``PROCEDURE`` keyword.

        Returns:
            A fully populated, immutable
            :class:`~app.parser.ast.procedure.ProcedureDivisionNode`.

        Raises:
            ParserError:
                If the division header is fatally malformed.
        """
        stream = state.stream
        start: Position = stream.current().position

        logger.debug("Parsing PROCEDURE DIVISION at {}.", start)

        # ----------------------------------------------------------------
        # PROCEDURE DIVISION .
        # ----------------------------------------------------------------
        self._expect_keyword(stream.advance(), "PROCEDURE")
        self._expect_keyword(stream.advance(), "DIVISION")
        stream.expect(TokenType.PERIOD)

        # ----------------------------------------------------------------
        # Parse paragraphs
        # ----------------------------------------------------------------
        paragraphs: list[ParagraphNode] = self._parse_paragraphs(state)

        end: Position = stream.current().position

        return ProcedureDivisionNode(
            start_position=start,
            end_position=end,
            paragraphs=tuple(paragraphs),
        )

    # ------------------------------------------------------------------
    # Paragraph-list parser
    # ------------------------------------------------------------------

    def _parse_paragraphs(self, state: ParserState) -> list[ParagraphNode]:
        """
        Parse a sequence of paragraphs from the token stream.

        Continues until a division keyword, EOF, or an unrecognised
        token is encountered at the paragraph level.

        Args:
            state: The active parser state.

        Returns:
            Ordered list of :class:`~app.parser.ast.paragraphs.ParagraphNode`
            instances.
        """
        stream = state.stream
        paragraphs: list[ParagraphNode] = []

        while not stream.eof():
            tok = stream.current()

            if tok.type is TokenType.EOF:
                break

            # Stop if we hit another division header
            if (
                tok.type is TokenType.KEYWORD
                and tok.lexeme.upper() in _DIVISION_KEYWORDS
            ):
                # Confirm by peeking that the next token is DIVISION
                next_tok = stream.peek()
                if (
                    next_tok.type is TokenType.KEYWORD
                    and next_tok.lexeme.upper() == "DIVISION"
                ):
                    break

            # A paragraph label is an IDENTIFIER or KEYWORD that is NOT a
            # statement-level lexeme AND NOT a division-boundary keyword.
            # Attempt to parse it as a paragraph; recover on error.
            if tok.type in (TokenType.IDENTIFIER, TokenType.KEYWORD):
                upper = tok.lexeme.upper()
                if upper not in _STATEMENT_LEXEMES:
                    try:
                        para = self._parse_paragraph(state)
                        paragraphs.append(para)
                    except ParserError as exc:
                        logger.debug(
                            "ProcedureDivisionParser: recovering from paragraph "
                            "error: {}",
                            exc.message,
                        )
                        state.record_and_synchronise(
                            message=exc.message,
                            error_token=stream.current(),
                            context=RecoveryContext.PROCEDURE_DIVISION,
                        )
                    continue

            # Log and break on anything unexpected at paragraph level
            logger.debug(
                "ProcedureDivisionParser: stopping paragraph loop at token {!r}.",
                tok.lexeme,
            )
            break

        return paragraphs

    # ------------------------------------------------------------------
    # Single-paragraph parser
    # ------------------------------------------------------------------

    def _parse_paragraph(self, state: ParserState) -> ParagraphNode:
        """
        Parse a single paragraph entry.

        Grammar rule::

            paragraph ::=
                paragraph-label PERIOD
                statement*

        The cursor must be positioned on the paragraph-label token when
        this method is called.

        Args:
            state:
                The active parser state.

        Returns:
            An immutable :class:`~app.parser.ast.paragraphs.ParagraphNode`.

        Raises:
            ParserError:
                If the paragraph label is not followed by a period.
        """
        stream = state.stream
        start: Position = stream.current().position

        # Consume paragraph label
        label_tok = stream.current()
        name: str = label_tok.lexeme.upper()
        stream.advance()  # consume label

        # Consume the period that terminates the paragraph label
        period_tok = stream.current()
        if period_tok.type is not TokenType.PERIOD:
            raise ParserError(
                f"expected '.' after paragraph label {name!r}, "
                f"got {period_tok.lexeme!r}",
                line=period_tok.position.line,
                column=period_tok.position.column,
                offset=period_tok.position.offset,
            )
        stream.advance()  # consume period

        logger.debug("Parsing paragraph {!r} at {}.", name, start)

        # Parse statements belonging to this paragraph
        statements: list[StatementNode] = self._parse_statements(state)

        end: Position = stream.current().position

        return ParagraphNode(
            start_position=start,
            end_position=end,
            name=name,
            statements=tuple(statements),
        )

    # ------------------------------------------------------------------
    # Statement-list parser
    # ------------------------------------------------------------------

    def _parse_statements(self, state: ParserState) -> list[StatementNode]:
        """
        Parse the sequence of statements that belong to the current paragraph.

        Stops when:
        - EOF is reached.
        - A paragraph label is detected (IDENTIFIER/KEYWORD + PERIOD where
          the keyword is not a statement keyword).
        - A division boundary keyword is detected.

        Recoverable errors within individual statements are caught,
        recorded as diagnostics, and the stream is synchronised to the
        next period before attempting the next statement.

        Args:
            state: The active parser state.

        Returns:
            Ordered list of :class:`~app.parser.ast.statements.StatementNode`
            instances.
        """
        stream = state.stream
        statements: list[StatementNode] = []

        while not stream.eof():
            tok = stream.current()

            if tok.type is TokenType.EOF:
                break

            # Stop at next division boundary
            if (
                tok.type is TokenType.KEYWORD
                and tok.lexeme.upper() in _DIVISION_KEYWORDS
            ):
                next_tok = stream.peek()
                if (
                    next_tok.type is TokenType.KEYWORD
                    and next_tok.lexeme.upper() == "DIVISION"
                ):
                    break

            # Detect a paragraph label (name followed by period where the
            # name is not a recognised statement lexeme)
            if tok.type in (TokenType.IDENTIFIER, TokenType.KEYWORD):
                upper = tok.lexeme.upper()
                next_tok = stream.peek()
                if (
                    next_tok.type is TokenType.PERIOD
                    and upper not in _STATEMENT_LEXEMES
                ):
                    # Next paragraph starts — stop collecting statements
                    break

                if upper in _STATEMENT_LEXEMES:
                    try:
                        stmt = self._parse_statement(state)
                        statements.append(stmt)
                    except ParserError as exc:
                        logger.debug(
                            "ProcedureDivisionParser: recovering from statement "
                            "error: {}",
                            exc.message,
                        )
                        state.record_and_synchronise(
                            message=exc.message,
                            error_token=stream.current(),
                            context=RecoveryContext.STATEMENT,
                        )
                    continue

            # Anything else at statement level — unexpected; stop
            logger.debug(
                "ProcedureDivisionParser: stopping statement loop at token {!r}.",
                tok.lexeme,
            )
            break

        return statements

    # ------------------------------------------------------------------
    # Statement dispatcher
    # ------------------------------------------------------------------

    def _parse_statement(self, state: ParserState) -> StatementNode:
        """
        Dispatch to the appropriate statement-level parse method.

        ``GOBACK`` is emitted by the lexer as an ``IDENTIFIER`` token
        (it is not in the COBOL keyword set); this method matches it by
        uppercased lexeme regardless of token type.

        Args:
            state:
                The active parser state; cursor on the statement token.

        Returns:
            A concrete :class:`~app.parser.ast.statements.StatementNode`.

        Raises:
            ParserError:
                If the statement lexeme is recognised but its syntax is
                malformed, or if an unsupported keyword is encountered.
        """
        tok = state.stream.current()
        upper = tok.lexeme.upper()

        if upper == "DISPLAY":
            return self._parse_display(state)
        if upper == "MOVE":
            return self._parse_move(state)
        if upper == "STOP":
            return self._parse_stop_run(state)
        if upper == "GOBACK":
            return self._parse_goback(state)
        if upper == "ADD":
            return self._parse_add(state)
        if upper == "SUBTRACT":
            return self._parse_subtract(state)
        if upper == "MULTIPLY":
            return self._parse_multiply(state)
        if upper == "DIVIDE":
            return self._parse_divide(state)
        if upper == "CALL":
            return self._parse_call(state)

        raise ParserError(
            f"unsupported statement keyword {upper!r}",
            line=tok.position.line,
            column=tok.position.column,
            offset=tok.position.offset,
        )

    # ------------------------------------------------------------------
    # Individual statement parsers
    # ------------------------------------------------------------------

    def _parse_display(self, state: ParserState) -> DisplayStatementNode:
        """
        Parse a ``DISPLAY`` statement.

        Grammar rule::

            display-statement ::= DISPLAY operand PERIOD

        The operand is accumulated as all tokens between ``DISPLAY`` and
        the terminating period, joined with a single space.

        Args:
            state: Active parser state; cursor on ``DISPLAY``.

        Returns:
            An immutable :class:`~app.parser.ast.statements.DisplayStatementNode`.

        Raises:
            ParserError: If no operand or period is found.
        """
        stream = state.stream
        start: Position = stream.current().position

        stream.advance()  # consume DISPLAY

        operand_parts: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.PERIOD:
                break
            operand_parts.append(tok.lexeme)
            stream.advance()

        if not operand_parts:
            tok = stream.current()
            raise ParserError(
                "expected operand after DISPLAY",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        operand = " ".join(operand_parts)
        end: Position = stream.current().position
        self._consume_period(state, "DISPLAY")

        return DisplayStatementNode(
            start_position=start,
            end_position=end,
            operand=operand,
        )

    def _parse_move(self, state: ParserState) -> MoveStatementNode:
        """
        Parse a ``MOVE ... TO ...`` statement.

        Grammar rule::

            move-statement ::= MOVE source TO target PERIOD

        Tokens between ``MOVE`` and ``TO`` are joined as the source;
        tokens between ``TO`` and the period are joined as the target.

        Args:
            state: Active parser state; cursor on ``MOVE``.

        Returns:
            An immutable :class:`~app.parser.ast.statements.MoveStatementNode`.

        Raises:
            ParserError:
                If the source operand, ``TO`` keyword, target operand,
                or period is missing.
        """
        stream = state.stream
        start: Position = stream.current().position

        stream.advance()  # consume MOVE

        # Collect source tokens up to TO — TO is emitted as an IDENTIFIER
        # by the lexer (it is not in the keyword set) so we compare by
        # uppercased lexeme regardless of token type.
        source_parts: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.PERIOD:
                break
            if tok.lexeme.upper() == "TO":
                break
            source_parts.append(tok.lexeme)
            stream.advance()

        if not source_parts:
            tok = stream.current()
            raise ParserError(
                "expected source operand after MOVE",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        # Consume TO keyword — the lexer emits TO as IDENTIFIER since it is
        # not in the COBOL keyword set for this milestone.
        to_tok = stream.current()
        if to_tok.lexeme.upper() != "TO":
            raise ParserError(
                f"expected 'TO' in MOVE statement, got {to_tok.lexeme!r}",
                line=to_tok.position.line,
                column=to_tok.position.column,
                offset=to_tok.position.offset,
            )
        stream.advance()  # consume TO

        # Collect target tokens up to period
        target_parts: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.PERIOD:
                break
            target_parts.append(tok.lexeme)
            stream.advance()

        if not target_parts:
            tok = stream.current()
            raise ParserError(
                "expected target operand after TO in MOVE statement",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        source = " ".join(source_parts)
        target = " ".join(target_parts)
        end: Position = stream.current().position
        self._consume_period(state, "MOVE")

        return MoveStatementNode(
            start_position=start,
            end_position=end,
            source=source,
            target=target,
        )

    def _parse_stop_run(self, state: ParserState) -> StopRunStatementNode:
        """
        Parse a ``STOP RUN`` statement.

        Grammar rule::

            stop-run-statement ::= STOP RUN PERIOD

        Args:
            state: Active parser state; cursor on ``STOP``.

        Returns:
            An immutable :class:`~app.parser.ast.statements.StopRunStatementNode`.

        Raises:
            ParserError:
                If ``RUN`` keyword or the terminating period is absent.
        """
        stream = state.stream
        start: Position = stream.current().position

        stream.advance()  # consume STOP

        run_tok = stream.current()
        if run_tok.type is not TokenType.KEYWORD or run_tok.lexeme.upper() != "RUN":
            raise ParserError(
                f"expected 'RUN' after STOP, got {run_tok.lexeme!r}",
                line=run_tok.position.line,
                column=run_tok.position.column,
                offset=run_tok.position.offset,
            )
        stream.advance()  # consume RUN

        end: Position = stream.current().position
        self._consume_period(state, "STOP RUN")

        return StopRunStatementNode(
            start_position=start,
            end_position=end,
        )

    def _parse_goback(self, state: ParserState) -> GobackStatementNode:
        """
        Parse a ``GOBACK`` statement.

        Grammar rule::

            goback-statement ::= GOBACK PERIOD

        Args:
            state: Active parser state; cursor on ``GOBACK``.

        Returns:
            An immutable :class:`~app.parser.ast.statements.GobackStatementNode`.

        Raises:
            ParserError: If the terminating period is absent.
        """
        stream = state.stream
        start: Position = stream.current().position

        stream.advance()  # consume GOBACK

        end: Position = stream.current().position
        self._consume_period(state, "GOBACK")

        return GobackStatementNode(
            start_position=start,
            end_position=end,
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _parse_add(self, state: ParserState) -> AddStatementNode:
        stream = state.stream
        start: Position = stream.current().position
        stream.advance()  # consume ADD

        left_parts: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.PERIOD or tok.lexeme.upper() == "TO":
                break
            left_parts.append(tok.lexeme)
            stream.advance()

        if not left_parts:
            tok = stream.current()
            raise ParserError(
                "expected operand after ADD",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        to_tok = stream.current()
        if to_tok.lexeme.upper() != "TO":
            raise ParserError(
                f"expected 'TO' in ADD statement, got {to_tok.lexeme!r}",
                line=to_tok.position.line,
                column=to_tok.position.column,
                offset=to_tok.position.offset,
            )
        stream.advance()

        right_parts: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.PERIOD:
                break
            right_parts.append(tok.lexeme)
            stream.advance()

        if not right_parts:
            tok = stream.current()
            raise ParserError(
                "expected target operand after TO",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        left = " ".join(left_parts)
        right = " ".join(right_parts)
        end: Position = stream.current().position
        self._consume_period(state, "ADD")

        return AddStatementNode(
            start_position=start, end_position=end, left=left, right=right
        )

    def _parse_subtract(self, state: ParserState) -> SubtractStatementNode:
        stream = state.stream
        start: Position = stream.current().position
        stream.advance()  # consume SUBTRACT

        left_parts: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.PERIOD or tok.lexeme.upper() == "FROM":
                break
            left_parts.append(tok.lexeme)
            stream.advance()

        if not left_parts:
            tok = stream.current()
            raise ParserError(
                "expected operand after SUBTRACT",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        from_tok = stream.current()
        if from_tok.lexeme.upper() != "FROM":
            raise ParserError(
                f"expected 'FROM' in SUBTRACT statement, got {from_tok.lexeme!r}",
                line=from_tok.position.line,
                column=from_tok.position.column,
                offset=from_tok.position.offset,
            )
        stream.advance()

        right_parts: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.PERIOD:
                break
            right_parts.append(tok.lexeme)
            stream.advance()

        if not right_parts:
            tok = stream.current()
            raise ParserError(
                "expected target operand after FROM",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        left = " ".join(left_parts)
        right = " ".join(right_parts)
        end: Position = stream.current().position
        self._consume_period(state, "SUBTRACT")

        return SubtractStatementNode(
            start_position=start, end_position=end, left=left, right=right
        )

    def _parse_multiply(self, state: ParserState) -> MultiplyStatementNode:
        stream = state.stream
        start: Position = stream.current().position
        stream.advance()  # consume MULTIPLY

        left_parts: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.PERIOD or tok.lexeme.upper() == "BY":
                break
            left_parts.append(tok.lexeme)
            stream.advance()

        if not left_parts:
            tok = stream.current()
            raise ParserError(
                "expected operand after MULTIPLY",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        by_tok = stream.current()
        if by_tok.lexeme.upper() != "BY":
            raise ParserError(
                f"expected 'BY' in MULTIPLY statement, got {by_tok.lexeme!r}",
                line=by_tok.position.line,
                column=by_tok.position.column,
                offset=by_tok.position.offset,
            )
        stream.advance()

        right_parts: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.PERIOD:
                break
            right_parts.append(tok.lexeme)
            stream.advance()

        if not right_parts:
            tok = stream.current()
            raise ParserError(
                "expected target operand after BY",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        left = " ".join(left_parts)
        right = " ".join(right_parts)
        end: Position = stream.current().position
        self._consume_period(state, "MULTIPLY")

        return MultiplyStatementNode(
            start_position=start, end_position=end, left=left, right=right
        )

    def _parse_divide(self, state: ParserState) -> DivideStatementNode:
        stream = state.stream
        start: Position = stream.current().position
        stream.advance()  # consume DIVIDE

        left_parts: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.PERIOD or tok.lexeme.upper() == "INTO":
                break
            left_parts.append(tok.lexeme)
            stream.advance()

        if not left_parts:
            tok = stream.current()
            raise ParserError(
                "expected operand after DIVIDE",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        into_tok = stream.current()
        if into_tok.lexeme.upper() != "INTO":
            raise ParserError(
                f"expected 'INTO' in DIVIDE statement, got {into_tok.lexeme!r}",
                line=into_tok.position.line,
                column=into_tok.position.column,
                offset=into_tok.position.offset,
            )
        stream.advance()

        right_parts: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.PERIOD:
                break
            right_parts.append(tok.lexeme)
            stream.advance()

        if not right_parts:
            tok = stream.current()
            raise ParserError(
                "expected target operand after INTO",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        left = " ".join(left_parts)
        right = " ".join(right_parts)
        end: Position = stream.current().position
        self._consume_period(state, "DIVIDE")

        return DivideStatementNode(
            start_position=start, end_position=end, left=left, right=right
        )

    def _parse_call(self, state: ParserState) -> CallStatementNode:
        stream = state.stream
        start: Position = stream.current().position
        stream.advance()  # consume CALL

        target_parts: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.PERIOD or tok.lexeme.upper() == "USING":
                break
            target_parts.append(tok.lexeme)
            stream.advance()

        if not target_parts:
            tok = stream.current()
            raise ParserError(
                "expected target after CALL",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        target = " ".join(target_parts)
        arguments: list[str] = []

        tok = stream.current()
        if tok.lexeme.upper() == "USING":
            stream.advance()  # consume USING
            while not stream.eof():
                tok = stream.current()
                if tok.type is TokenType.PERIOD:
                    break
                arguments.append(tok.lexeme)
                stream.advance()

        end: Position = stream.current().position
        self._consume_period(state, "CALL")

        return CallStatementNode(
            start_position=start,
            end_position=end,
            target=target,
            arguments=tuple(arguments),
        )

    def _consume_period(self, state: ParserState, context: str) -> None:
        """
        Consume the terminating period for a statement or paragraph header.

        Args:
            state:   The active parser state.
            context: A human-readable name used in error messages.

        Raises:
            ParserError:
                If the current token is not a period.
        """
        stream = state.stream
        tok = stream.current()
        if tok.type is TokenType.EOF:
            raise ParserError(
                f"expected '.' after {context}, got EOF",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )
        if tok.type is not TokenType.PERIOD:
            raise ParserError(
                f"expected '.' after {context}, got {tok.lexeme!r}",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )
        stream.advance()  # consume period

    @staticmethod
    def _expect_keyword(tok: Token, keyword: str) -> None:
        """
        Assert that *tok* is a ``KEYWORD`` token with lexeme *keyword*.

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
