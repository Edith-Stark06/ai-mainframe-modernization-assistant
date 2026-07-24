"""
Data Division Parser.

Purpose:
    Implement the recursive-descent grammar rules that recognise the
    COBOL DATA DIVISION, its WORKING-STORAGE SECTION, and the supported
    data-item declarations within that section.

    The DATA DIVISION has this general structure (subset supported here)::

        DATA DIVISION.

        WORKING-STORAGE SECTION.

        01 CUSTOMER-REC.
           05 CUSTOMER-ID     PIC 9(5).
           05 CUSTOMER-NAME   PIC X(30).

        77 WS-COUNT           PIC 9(4).

        88 END-OF-FILE        VALUE 'Y'.

Responsibilities:
    - Recognise the ``DATA DIVISION .`` header.
    - Recognise the ``WORKING-STORAGE SECTION .`` header.
    - Parse top-level data-item declarations (level 01, 05, 77, 88).
    - Parse PIC clauses for elementary items.
    - Parse simple VALUE clauses for 88-level condition-name items.
    - Recover from invalid level numbers, missing periods, and malformed
      data items using panic-mode synchronisation via
      :class:`~app.parser.syntax.parser_state.ParserState`.
    - Construct and return a
      :class:`~app.parser.ast.data.DataDivisionNode` populated with
      :class:`~app.parser.ast.working_storage.WorkingStorageSectionNode`
      and its :class:`~app.parser.ast.data_items.DataItemNode` children.
    - Raise :class:`~app.parser.syntax.parser_exceptions.ParserError`
      only for fatal conditions (e.g. malformed division header).

Non-responsibilities:
    - FILE SECTION, LINKAGE SECTION, LOCAL-STORAGE, SCREEN SECTION,
      REPORT SECTION parsing.
    - OCCURS, REDEFINES, RENAMES (66), COMP, COMP-3, INDEXED BY,
      JUSTIFIED, SYNCHRONIZED clauses.
    - COPY book expansion.
    - Semantic analysis.
    - Statement or expression parsing.

Dependencies:
    - :mod:`app.parser.ast.data`          — ``DataDivisionNode``.
    - :mod:`app.parser.ast.working_storage` — ``WorkingStorageSectionNode``.
    - :mod:`app.parser.ast.data_items`    — item node types.
    - :mod:`app.parser.lexer.token_types` — ``TokenType``.
    - :mod:`app.parser.syntax.parser_state`      — ``ParserState``.
    - :mod:`app.parser.syntax.parser_exceptions` — ``ParserError``.
    - :mod:`app.parser.diagnostics.recovery`     — ``RecoveryContext``.
    - Python standard library only.

Examples:
    Parsing a DATA DIVISION from a token stream::

        from app.parser.syntax.data_parser import DataDivisionParser

        parser = DataDivisionParser()
        node = parser.parse(state)
        # node is DataDivisionNode
        # state.diagnostics contains any recovered errors

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.parser.ast.data import DataDivisionNode
from app.parser.ast.data_items import (
    ConditionNameNode,
    DataItemNode,
    ElementaryItemNode,
    GroupItemNode,
)
from app.parser.ast.working_storage import WorkingStorageSectionNode
from app.parser.diagnostics.recovery import RecoveryContext
from app.parser.lexer.position import Position
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType
from app.parser.syntax.parser_exceptions import ParserError
from app.parser.syntax.parser_state import ParserState

__all__ = ["DataDivisionParser"]

# ---------------------------------------------------------------------------
# Supported level numbers
# ---------------------------------------------------------------------------
_SUPPORTED_LEVELS: frozenset[int] = frozenset(
    {
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        20,
        21,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
        29,
        30,
        31,
        32,
        33,
        34,
        35,
        36,
        37,
        38,
        39,
        40,
        41,
        42,
        43,
        44,
        45,
        46,
        47,
        48,
        49,
        66,
        77,
        78,
        88,
    }
)

# Keywords that signal the start of the next COBOL division — stop parsing
# the DATA DIVISION when we see one of these.
_NEXT_DIVISION_KEYWORDS: frozenset[str] = frozenset(
    {
        "ENVIRONMENT",
        "PROCEDURE",
        "IDENTIFICATION",
    }
)

# Keywords that signal an unsupported DATA DIVISION section — skip gracefully
# (we stop and return what we have so far).
_UNSUPPORTED_SECTION_KEYWORDS: frozenset[str] = frozenset(
    {
        "FILE",
        "LINKAGE",
        "LOCAL-STORAGE",
        "SCREEN",
        "REPORT",
        "COMMUNICATION",
    }
)


class DataDivisionParser:
    """
    Recursive-descent parser for the COBOL DATA DIVISION.

    Instantiate once and call :meth:`parse` with the active
    :class:`~app.parser.syntax.parser_state.ParserState`.  The state's
    :class:`~app.parser.syntax.token_stream.TokenStream` cursor must be
    positioned on the ``DATA`` keyword when :meth:`parse` is called.

    The parser constructs and returns a
    :class:`~app.parser.ast.data.DataDivisionNode` containing the parsed
    sections and items.

    Recovery behaviour:
        - Invalid level numbers, missing data-names, missing periods, and
          unsupported clause tokens are recorded as diagnostics and the
          stream is synchronised to the next period or section/division
          boundary before resuming.
        - The division header (``DATA DIVISION .``) and section header
          (``WORKING-STORAGE SECTION .``) still raise
          :class:`~app.parser.syntax.parser_exceptions.ParserError` on
          fatal mismatches.

    Examples:
        >>> # (see module docstring for full usage)
        >>> parser = DataDivisionParser()
        >>> isinstance(parser, DataDivisionParser)
        True
    """

    def parse(self, state: ParserState) -> DataDivisionNode:
        """
        Parse the DATA DIVISION from the current stream position.

        Grammar rule (supported subset)::

            data-division ::=
                DATA DIVISION PERIOD
                [ working-storage-section ]

            working-storage-section ::=
                WORKING-STORAGE SECTION PERIOD
                data-item*

            data-item ::=
                level-number data-name
                [ PIC picture-string ]
                [ VALUE literal ]
                PERIOD

        Recoverable errors (recorded as diagnostics, parsing continues):
            - Invalid level number.
            - Missing data-name.
            - Missing period at end of data item.
            - Unexpected token at division or section level.

        Fatal errors (raise :class:`~app.parser.syntax.parser_exceptions.ParserError`):
            - ``DATA`` keyword missing.
            - ``DIVISION`` keyword missing after ``DATA``.
            - Period missing after ``DATA DIVISION``.

        Args:
            state:
                The active :class:`~app.parser.syntax.parser_state.ParserState`.
                The cursor must be on the ``DATA`` keyword.

        Returns:
            A fully populated, immutable
            :class:`~app.parser.ast.data.DataDivisionNode`.

        Raises:
            ParserError:
                If the division header is fatally malformed.
        """
        stream = state.stream
        start: Position = stream.current().position

        logger.debug("Parsing DATA DIVISION at {}.", start)

        # ----------------------------------------------------------------
        # DATA DIVISION .
        # ----------------------------------------------------------------
        self._expect_keyword(stream.advance(), "DATA")
        self._expect_keyword(stream.advance(), "DIVISION")
        stream.expect(TokenType.PERIOD)

        # ----------------------------------------------------------------
        # Optional sections
        # ----------------------------------------------------------------
        working_storage: WorkingStorageSectionNode | None = None

        while not stream.eof():
            tok = stream.current()

            # Stop at next major division
            if tok.type is TokenType.KEYWORD:
                upper = tok.lexeme.upper()
                if upper in _NEXT_DIVISION_KEYWORDS:
                    break
                if upper == "WORKING-STORAGE":
                    working_storage = self._parse_working_storage(state)
                    continue
                if upper in _UNSUPPORTED_SECTION_KEYWORDS:
                    # Unsupported section — stop here; let ProgramParser handle
                    logger.debug(
                        "DataDivisionParser: encountered unsupported section "
                        "{!r}; stopping DATA DIVISION parse.",
                        upper,
                    )
                    break

            # A numeric token could be an orphaned level number appearing
            # before a WORKING-STORAGE SECTION header is seen.  This is
            # technically a syntax error but we stop gracefully.
            if tok.type is TokenType.NUMBER:
                logger.debug(
                    "DataDivisionParser: numeric token {!r} before any section; "
                    "stopping.",
                    tok.lexeme,
                )
                break

            if tok.type is TokenType.EOF:
                break

            # Any other token at the division level is unexpected —
            # record a diagnostic and synchronise.
            logger.debug(
                "DataDivisionParser: unexpected token {!r} at division level; "
                "recovering.",
                tok.lexeme,
            )
            state.record_and_synchronise(
                message=(f"unexpected token {tok.lexeme!r} at DATA DIVISION level"),
                error_token=tok,
                context=RecoveryContext.DATA_DIVISION,
            )

        end: Position = stream.current().position

        return DataDivisionNode(
            start_position=start,
            end_position=end,
            working_storage=working_storage,
        )

    # ------------------------------------------------------------------
    # Section parsers
    # ------------------------------------------------------------------

    def _parse_working_storage(self, state: ParserState) -> WorkingStorageSectionNode:
        """
        Parse the WORKING-STORAGE SECTION.

        Grammar rule::

            working-storage-section ::=
                WORKING-STORAGE SECTION PERIOD
                data-item*

        The cursor must be on the ``WORKING-STORAGE`` keyword when this
        method is called.

        Args:
            state: The active parser state.

        Returns:
            An immutable :class:`~app.parser.ast.working_storage.WorkingStorageSectionNode`.

        Raises:
            ParserError: If the section header is fatally malformed.
        """
        stream = state.stream
        start: Position = stream.current().position

        logger.debug("Parsing WORKING-STORAGE SECTION at {}.", start)

        # WORKING-STORAGE SECTION .
        self._expect_keyword(stream.advance(), "WORKING-STORAGE")
        section = stream.advance()
        if section.lexeme.upper() != "SECTION":
            raise ParserError(
                f"expected 'SECTION', got {section.lexeme!r}",
                line=section.position.line,
                column=section.position.column,
                offset=section.position.offset,
            )

        stream.expect(TokenType.PERIOD)

        items: list[DataItemNode] = self._parse_data_items(state)

        end: Position = stream.current().position

        return WorkingStorageSectionNode(
            start_position=start,
            end_position=end,
            items=tuple(items),
        )

    # ------------------------------------------------------------------
    # Data-item list parser
    # ------------------------------------------------------------------

    def _parse_data_items(self, state: ParserState) -> list[DataItemNode]:
        """
        Parse a sequence of data-item declarations.

        Continues until a non-numeric / non-data-item token is encountered,
        signalling the end of the current section.  Malformed individual
        items are recovered and parsing resumes with the next level number.

        Args:
            state: The active parser state.

        Returns:
            Ordered list of :class:`~app.parser.ast.data_items.DataItemNode`
            instances.
        """
        stream = state.stream
        items: list[DataItemNode] = []

        while not stream.eof():
            tok = stream.current()

            # Stop when we see a keyword that starts the next section/division
            if tok.type is TokenType.KEYWORD:
                upper = tok.lexeme.upper()
                if (
                    upper in _NEXT_DIVISION_KEYWORDS
                    or upper in _UNSUPPORTED_SECTION_KEYWORDS
                    or upper == "WORKING-STORAGE"
                ):
                    break
                # Any other keyword at item level is unexpected — stop
                break

            if tok.type is TokenType.EOF:
                break

            # Silently consume stray PERIOD tokens that result from
            # panic-mode recovery synchronising to a paragraph boundary
            # (which leaves the period in the stream).
            if tok.type is TokenType.PERIOD:
                stream.advance()
                continue

            # A NUMBER token is the level number for the next data item
            if tok.type is TokenType.NUMBER:
                try:
                    item = self._parse_data_item(state)
                    items.append(item)
                except ParserError as exc:
                    logger.debug(
                        "DataDivisionParser: recovering from data-item error: {}",
                        exc.message,
                    )
                    state.record_and_synchronise(
                        message=exc.message,
                        error_token=stream.current(),
                        context=RecoveryContext.WORKING_STORAGE_SECTION,
                    )
                continue

            # Anything else — unexpected; stop the section
            break

        return items

    # ------------------------------------------------------------------
    # Single data-item parser
    # ------------------------------------------------------------------

    def _parse_data_item(self, state: ParserState) -> DataItemNode:
        """
        Parse a single data-item entry.

        Dispatches to the appropriate specialised parse method based on
        the level number (88 → condition name, others → elementary or
        group item).

        Grammar rule (supported)::

            data-item ::=
                level-number data-name
                ( PIC picture-string [ VALUE literal ] | ε )
                PERIOD

            condition-name ::=
                88 condition-name VALUE literal PERIOD

        Args:
            state:
                The active parser state; cursor on the level-number token.

        Returns:
            A :class:`~app.parser.ast.data_items.DataItemNode` subclass.

        Raises:
            ParserError:
                If the level number is invalid, the data-name is missing,
                or a required clause token is absent.
        """
        stream = state.stream
        level_tok = stream.current()
        start: Position = level_tok.position

        level = self._parse_level_number(level_tok)
        stream.advance()  # consume level number

        # Data-name / condition-name
        name_tok = stream.current()
        if name_tok.type is TokenType.EOF:
            raise ParserError(
                f"expected data-name after level number {level}",
                line=name_tok.position.line,
                column=name_tok.position.column,
                offset=name_tok.position.offset,
            )
        if name_tok.type not in (
            TokenType.IDENTIFIER,
            TokenType.KEYWORD,
        ):
            raise ParserError(
                f"expected data-name after level {level}, " f"got {name_tok.lexeme!r}",
                line=name_tok.position.line,
                column=name_tok.position.column,
                offset=name_tok.position.offset,
            )
        name = name_tok.lexeme.upper()
        stream.advance()  # consume name

        # Dispatch by level
        if level == 88:
            return self._parse_condition_name(state, start, name)

        return self._parse_elementary_or_group(state, start, level, name)

    def _parse_condition_name(
        self,
        state: ParserState,
        start: Position,
        name: str,
    ) -> ConditionNameNode:
        """
        Parse a level-88 condition-name entry.

        Grammar rule::

            88 condition-name VALUE literal PERIOD

        The cursor must be positioned immediately after the condition name
        when this method is called.

        Args:
            state: Active parser state.
            start: Source position of the level-88 token.
            name:  The uppercased condition-name string.

        Returns:
            An immutable :class:`~app.parser.ast.data_items.ConditionNameNode`.

        Raises:
            ParserError: If the VALUE keyword or literal is missing.
        """
        stream = state.stream
        value: str | None = None

        tok = stream.current()

        # VALUE clause is expected for 88-level items
        if tok.type is TokenType.KEYWORD and tok.lexeme.upper() == "VALUE":
            stream.advance()  # consume VALUE
            value_tok = stream.current()
            if value_tok.type is TokenType.EOF:
                raise ParserError(
                    f"expected literal after VALUE for condition {name!r}",
                    line=value_tok.position.line,
                    column=value_tok.position.column,
                    offset=value_tok.position.offset,
                )
            if value_tok.type not in (
                TokenType.STRING,
                TokenType.NUMBER,
                TokenType.IDENTIFIER,
                TokenType.KEYWORD,
            ):
                raise ParserError(
                    f"expected literal after VALUE for condition {name!r}, "
                    f"got {value_tok.lexeme!r}",
                    line=value_tok.position.line,
                    column=value_tok.position.column,
                    offset=value_tok.position.offset,
                )
            value = value_tok.lexeme
            stream.advance()  # consume literal

        # Consume terminating period
        end: Position = stream.current().position
        self._expect_period(state)

        return ConditionNameNode(
            start_position=start,
            end_position=end,
            level=88,
            name=name,
            value=value,
        )

    def _parse_elementary_or_group(
        self,
        state: ParserState,
        start: Position,
        level: int,
        name: str,
    ) -> DataItemNode:
        """
        Parse an elementary or group data item.

        If a PIC (or PICTURE) clause follows the data name, the item is
        elementary.  If the next token is a period, the item is a group
        record.

        Grammar rules::

            elementary-item ::=
                level data-name PIC picture-string
                [ VALUE literal ]
                PERIOD

            group-item ::=
                level data-name PERIOD

        The cursor must be positioned immediately after the data-name
        when this method is called.

        Args:
            state: Active parser state.
            start: Source position of the level-number token.
            level: The integer level number.
            name:  The uppercased data-name string.

        Returns:
            Either an :class:`~app.parser.ast.data_items.ElementaryItemNode`
            or a :class:`~app.parser.ast.data_items.GroupItemNode`.

        Raises:
            ParserError: If a required clause token is absent.
        """
        stream = state.stream
        tok = stream.current()

        picture: str | None = None
        value: str | None = None

        # Check for PIC / PICTURE keyword
        if tok.type is TokenType.KEYWORD and tok.lexeme.upper() in ("PIC", "PICTURE"):
            stream.advance()  # consume PIC/PICTURE

            # IS keyword is optional between PIC and picture string
            if (
                stream.current().type is TokenType.KEYWORD
                and stream.current().lexeme.upper() == "IS"
            ):
                stream.advance()  # consume IS

            pic_tok = stream.current()
            if pic_tok.type is TokenType.EOF:
                raise ParserError(
                    f"expected picture string after PIC for {name!r}",
                    line=pic_tok.position.line,
                    column=pic_tok.position.column,
                    offset=pic_tok.position.offset,
                )
            if pic_tok.type not in (
                TokenType.IDENTIFIER,
                TokenType.KEYWORD,
                TokenType.PIC,
                TokenType.NUMBER,
            ):
                raise ParserError(
                    f"expected picture string after PIC for {name!r}, "
                    f"got {pic_tok.lexeme!r}",
                    line=pic_tok.position.line,
                    column=pic_tok.position.column,
                    offset=pic_tok.position.offset,
                )
            picture = self._read_picture_string(state)

        # Check for VALUE clause (only meaningful for elementary items)
        if (
            stream.current().type is TokenType.KEYWORD
            and stream.current().lexeme.upper() == "VALUE"
        ):
            stream.advance()  # consume VALUE

            # IS keyword is optional
            if (
                stream.current().type is TokenType.KEYWORD
                and stream.current().lexeme.upper() == "IS"
            ):
                stream.advance()  # consume IS

            val_tok = stream.current()
            if val_tok.type is TokenType.EOF:
                raise ParserError(
                    f"expected literal after VALUE for {name!r}",
                    line=val_tok.position.line,
                    column=val_tok.position.column,
                    offset=val_tok.position.offset,
                )
            value = val_tok.lexeme
            stream.advance()  # consume literal

        # Consume terminating period
        end: Position = stream.current().position
        self._expect_period(state)

        if picture is not None:
            return ElementaryItemNode(
                start_position=start,
                end_position=end,
                level=level,
                name=name,
                picture=picture,
                value=value,
            )

        # No PIC → group item
        return GroupItemNode(
            start_position=start,
            end_position=end,
            level=level,
            name=name,
        )

    # ------------------------------------------------------------------
    # Picture-string accumulator
    # ------------------------------------------------------------------

    def _read_picture_string(self, state: ParserState) -> str:
        """
        Consume and return the picture string tokens.

        COBOL picture strings may consist of multiple adjacent tokens
        (e.g. ``X(30)`` is scanned as ``X``, ``(``, ``30``, ``)``)
        This method collects them into a single string until it
        encounters a terminal token (period, ``VALUE``, ``OCCURS``, or
        another recognised clause keyword).

        Args:
            state: The active parser state.

        Returns:
            The concatenated picture string (e.g. ``"9(5)"``).
        """
        stream = state.stream
        parts: list[str] = []

        _STOP_KEYWORDS: frozenset[str] = frozenset(
            {"VALUE", "OCCURS", "REDEFINES", "JUSTIFIED", "SYNCHRONIZED"}
        )

        depth: int = 0  # parenthesis nesting depth

        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.PERIOD:
                break
            if tok.type is TokenType.KEYWORD and tok.lexeme.upper() in _STOP_KEYWORDS:
                break
            # A NUMBER token at nesting depth 0 signals the start of the
            # next data item's level number — stop the picture string here.
            # Inside parentheses (depth > 0) numbers are valid (e.g. 9(5)).
            if tok.type is TokenType.NUMBER and depth == 0 and parts:
                break
            # Track parenthesis depth so we know when a number is a
            # picture repeat count vs. a data-item level number.
            if tok.type is TokenType.LPAREN:
                depth += 1
            elif tok.type is TokenType.RPAREN:
                depth = max(0, depth - 1)
            # Accumulate picture characters — including (, ), digits inside parens
            parts.append(tok.lexeme)
            stream.advance()

        return "".join(parts)

    # ------------------------------------------------------------------
    # Level-number parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_level_number(tok: Token) -> int:
        """
        Validate and return the integer level number from *tok*.

        Level numbers must be numeric tokens whose integer value is in
        the set of supported COBOL data-division level numbers.

        Args:
            tok: The token to interpret as a level number.

        Returns:
            The validated integer level number.

        Raises:
            ParserError:
                If *tok* is not a NUMBER token, or if its integer value
                is not a recognised level number.
        """
        if tok.type is not TokenType.NUMBER:
            raise ParserError(
                f"expected level number, got {tok.lexeme!r}",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        try:
            level = int(tok.lexeme)
        except ValueError:
            raise ParserError(
                f"level number {tok.lexeme!r} is not an integer",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        if level not in _SUPPORTED_LEVELS:
            raise ParserError(
                f"invalid level number {level}; " "supported: 01–49, 66, 77, 78, 88",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        return level

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _expect_period(self, state: ParserState) -> None:
        """
        Consume a terminating period from the stream.

        Args:
            state: The active parser state.

        Raises:
            ParserError: If the current token is not a period.
        """
        stream = state.stream
        tok = stream.current()
        if tok.type is TokenType.EOF:
            raise ParserError(
                "expected '.' to terminate data item, got EOF",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )
        if tok.type is not TokenType.PERIOD:
            raise ParserError(
                f"expected '.' to terminate data item, got {tok.lexeme!r}",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )
        stream.advance()  # consume period

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
