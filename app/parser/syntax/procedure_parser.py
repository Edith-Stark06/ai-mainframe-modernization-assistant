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
    ConditionTerm,
    DisplayStatementNode,
    GobackStatementNode,
    GoToStatementNode,
    MoveStatementNode,
    StatementNode,
    StopRunStatementNode,
    AddStatementNode,
    SubtractStatementNode,
    MultiplyStatementNode,
    DivideStatementNode,
    CallStatementNode,
    IfStatementNode,
    PerformStatementNode,
)
from app.parser.diagnostics.recovery import RecoveryContext
from app.parser.grammar_words import matches_grammar_word
from app.parser.lexer.position import Position
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType
from app.parser.syntax.parser_exceptions import ParserError
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.token_stream import TokenStream

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
        "ADD",
        "SUBTRACT",
        "MULTIPLY",
        "DIVIDE",
        "CALL",
        "IF",
        "PERFORM",
        "GO",
    }
)

# ---------------------------------------------------------------------------
# Verbs that are real COBOL statements but have no parser and no AST node
# yet.  They are recognised only so that encountering one produces an
# explicit diagnostic and skips that single statement, instead of
# silently abandoning the rest of the paragraph.  Most reach the parser
# as IDENTIFIER (only COMPUTE is a reserved lexer word), so they are
# matched by lexeme.
#
# This list is deliberately explicit: an identifier that is not named
# here is still treated as it was before (a paragraph label, or the end
# of the statement list), so arbitrary data names are never mistaken for
# statements.
# ---------------------------------------------------------------------------
_UNSUPPORTED_STATEMENT_LEXEMES: frozenset[str] = frozenset(
    {
        "OPEN",
        "CLOSE",
        "READ",
        "WRITE",
        "REWRITE",
        "DELETE",
        "START",
        "EVALUATE",
        "COMPUTE",
        "STRING",
        "UNSTRING",
        "INSPECT",
        "INITIALIZE",
        "SEARCH",
        "SET",
        "SORT",
        "MERGE",
        "RETURN",
        "RELEASE",
        # GO (TO) moved to _STATEMENT_LEXEMES (task #stage17): a simple
        # GO TO paragraph-name is now parsed into GoToStatementNode --
        # see _parse_go_to_statement. The multi-target
        # "GO TO A B C DEPENDING ON X" form remains unimplemented (not
        # present anywhere in the real corpus); see that method's
        # docstring and docs/MMIM_GO_TO_FIX.md.
        # ACCEPT already has an AST node (AcceptStatementNode) and an IR
        # builder (build_accept_instruction), but no parser dispatch
        # path.  Task #108 explicitly asks that it be reported as
        # unsupported rather than implemented, so it moved here from
        # _STATEMENT_LEXEMES: routing it through the same
        # _skip_unsupported_statement mechanism as OPEN/READ/etc. gives
        # it a SYN100 "unsupported" diagnostic instead of the syntax-error
        # path _parse_statement's fallback used to raise (#108-10).
        "ACCEPT",
        # CONTINUE and EXIT are valid no-op statements this parser does
        # not model.  Both are almost always written as a single bare
        # word before the period ("CONTINUE." / "EXIT."), which is
        # exactly the shape the paragraph-label heuristic below also
        # matches -- so without being listed here they were silently
        # mistaken for the start of a new paragraph (#108-06).
        "CONTINUE",
        "EXIT",
    }
)


# ---------------------------------------------------------------------------
# Lexemes that close an enclosing scope.  An operand list ends here just as
# surely as it does at the start of the next statement.
# ---------------------------------------------------------------------------
_SCOPE_TERMINATOR_LEXEMES: frozenset[str] = frozenset(
    {
        "ELSE",
        "END-IF",
        "END-PERFORM",
        "WHEN",
        "END-EVALUATE",
    }
)

# ---------------------------------------------------------------------------
# Every lexeme that ends a statement's operand list.
#
# _UNSUPPORTED_STATEMENT_LEXEMES is included deliberately.  Operand
# accumulators used to stop only at _STATEMENT_LEXEMES, so a statement
# written without a period terminator absorbed the *unsupported* verb that
# followed it straight into its own operand:
#
#     MOVE 'X' TO WS-A
#     OPEN INPUT F1
#
# produced MoveStatementNode(target="WS-A OPEN INPUT F1") with no diagnostic
# at all -- a corrupt AST that looked like a clean parse (finding F-107-01).
# A statement never continues past the start of the next one, whether or not
# this parser can build an AST node for that next statement.
# ---------------------------------------------------------------------------
_OPERAND_BOUNDARY_LEXEMES: frozenset[str] = (
    _STATEMENT_LEXEMES | _UNSUPPORTED_STATEMENT_LEXEMES | _SCOPE_TERMINATOR_LEXEMES
)

# ---------------------------------------------------------------------------
# Unsupported verbs that open a scope terminated by an END-xxx word.  Their
# bodies legitimately contain other statements, so when one is skipped the
# skip must run to the statement's period rather than stopping at the first
# statement verb inside the body.
# ---------------------------------------------------------------------------
_SCOPE_OPENING_LEXEMES: frozenset[str] = frozenset(
    {
        "EVALUATE",
        "SEARCH",
    }
)

# ---------------------------------------------------------------------------
# The closing word that precisely bounds each scope-opening verb's body, for
# verbs where that word is known. ``_skip_unsupported_statement`` matches
# this word (honoring same-verb nesting) instead of scanning for the next
# period -- see its docstring. ``SEARCH`` has no entry: it keeps the
# original scan-to-next-period behavior, unchanged. ``READ`` is not here
# either -- its ``AT END``/``NOT AT END`` clauses may legitimately end with
# ``END-READ`` *or* a bare period (unlike ``EVALUATE``), so it has its own
# dedicated skip, :meth:`ProcedureDivisionParser._skip_read_statement`.
# ---------------------------------------------------------------------------
_SCOPE_CLOSE_WORDS: dict[str, str] = {
    "EVALUATE": "END-EVALUATE",
}

# ---------------------------------------------------------------------------
# Relational-operator token recognition, shared between the plain-comparison
# grammar in _parse_simple_condition and the condition-name lookahead in
# _parse_condition_term (both need to answer "is the token after this
# operand a comparison operator, or something else?").
# ---------------------------------------------------------------------------
_COMPARISON_OPERATOR_TYPE_NAMES: frozenset[str] = frozenset(
    {
        "OPERATOR_EQ",
        "OPERATOR_GT",
        "OPERATOR_LT",
        "OPERATOR_GE",
        "OPERATOR_LE",
        "OPERATOR_NEQ",
    }
)
_COMPARISON_OPERATOR_LEXEMES: frozenset[str] = frozenset(
    {"=", ">", "<", ">=", "<=", "!=", "==", "<>"}
)


def _is_comparison_operator_token(token: Token) -> bool:
    """``True`` if *token* is a relational-comparison operator."""
    return (
        token.type.name in _COMPARISON_OPERATOR_TYPE_NAMES
        or token.lexeme in _COMPARISON_OPERATOR_LEXEMES
    )


# COBOL's ``relational-operator ::= [NOT] { = | > | < | >= | <= | <> }``
# (task #stage25): a ``NOT`` directly between the two operands of a simple
# condition (``IF WS-CODE NOT = 'AUTO'``) negates the operator, not the
# operand. Every key here is a lexeme :func:`_is_comparison_operator_token`
# accepts, so a comparison operator that passed that check always resolves;
# every value is itself an accepted lexeme, so the negated operator needs no
# further translation downstream (``NOT =`` becomes ``<>``, already aliased
# to Java ``!=`` in :data:`app.backend.java.control_flow_emitter
# .OPERATOR_ALIASES`; ``NOT >`` becomes ``<=``, already in
# :data:`~app.backend.java.control_flow_emitter.SUPPORTED_OPERATORS`, and so
# on). ``==``/``!=`` are this parser's own non-standard spellings (accepted
# unchanged elsewhere in this grammar); their negations are included too, for
# the same reason every other accepted operator's negation is: a comparison
# operator token that passed :func:`_is_comparison_operator_token` must
# never hit the "NOT is not supported before" fallback error.
_NEGATED_OPERATOR: dict[str, str] = {
    "=": "<>",
    "==": "!=",
    "<>": "=",
    "!=": "==",
    ">": "<=",
    "<": ">=",
    ">=": "<",
    "<=": ">",
}


# ---------------------------------------------------------------------------
# task #stage26: the comparison-operand check in _parse_simple_condition only
# ever accepted TokenType.IDENTIFIER/NUMBER/STRING, so a figurative-constant
# operand (``IF WS-CODE = SPACES``) failed with "expected operand for IF
# condition" -- but only for *some* spellings. app.parser.lexer.keywords
# .KEYWORDS reserves just two of COBOL's figurative-constant words --
# "ZEROS" and "SPACES" -- so only those two lex as TokenType.KEYWORD and hit
# the rejection; every other spelling (ZERO, SPACE, ZEROES, HIGH-VALUE(S),
# LOW-VALUE(S)) is not a reserved word here, lexes as a plain
# TokenType.IDENTIFIER, and already parsed successfully. This set names
# exactly the two words that need the operand check widened; every other
# figurative constant needs no change, since IDENTIFIER is already accepted.
# The analogous level-88 VALUE-literal grammar (data_parser
# ._read_condition_literal) already accepts this same
# {STRING, NUMBER, IDENTIFIER, KEYWORD} shape for exactly this reason.
_FIGURATIVE_CONSTANT_KEYWORDS: frozenset[str] = frozenset({"ZEROS", "SPACES"})


def _is_comparison_operand_token(token: Token) -> bool:
    """``True`` if *token* may stand as one side of an IF-condition comparison."""
    return (
        token.type is TokenType.IDENTIFIER
        or token.type is TokenType.NUMBER
        or token.type is TokenType.STRING
        or (
            token.type is TokenType.KEYWORD
            and token.lexeme in _FIGURATIVE_CONSTANT_KEYWORDS
        )
    )


# ---------------------------------------------------------------------------
# Sentinel condition_operator values for a level-88 condition-name reference
# used bare as an IF condition (``IF TX-DEPOSIT``) or negated
# (``IF NOT TX-VALID-KIND``), as opposed to an ordinary
# ``<operand> <relational-operator> <operand>`` comparison. Neither string
# can collide with a real comparison operator (see
# _COMPARISON_OPERATOR_LEXEMES above), so a consumer can distinguish a
# condition-name term from a comparison term by checking
# ``operator in (_CONDITION_NAME_TRUE_OPERATOR, _CONDITION_NAME_FALSE_OPERATOR)``.
# left and right both hold the condition-name itself (not two different
# operands, since a condition-name reference is a unary test) -- this keeps
# the existing three-string ConditionTerm/IfStatementNode shape exactly as
# it is, with no new AST fields, and keeps both fields truthy so existing
# business-rule extraction (which requires ``left and op and right`` to
# recognise a comparison) picks the term up without needing any change
# itself.
# ---------------------------------------------------------------------------
_CONDITION_NAME_TRUE_OPERATOR = "IS-TRUE"
_CONDITION_NAME_FALSE_OPERATOR = "IS-FALSE"


def _at_operand_boundary(token: Token) -> bool:
    """
    Return ``True`` if *token* ends the operand list of a statement.

    An operand list is terminated by the sentence-ending period, by the
    start of the next statement (supported or not), or by the close of an
    enclosing scope.

    Matching goes through
    :func:`~app.parser.grammar_words.matches_grammar_word`, so only
    ``KEYWORD`` and ``IDENTIFIER`` tokens can be boundaries.  A quoted
    literal such as ``'OPEN ERROR: '`` is a ``STRING`` token and is
    therefore operand text, never a boundary.

    Args:
        token: The token currently under the cursor.

    Returns:
        ``True`` if the operand list ends at *token*.
    """
    if token.type is TokenType.PERIOD:
        return True
    return matches_grammar_word(token, _OPERAND_BOUNDARY_LEXEMES)


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

        self._diagnose_unterminated_final_sentence(
            state, has_paragraphs=bool(paragraphs)
        )

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
                if (
                    upper not in _STATEMENT_LEXEMES
                    and upper not in _UNSUPPORTED_STATEMENT_LEXEMES
                ):
                    try:
                        para = self._parse_paragraph(state)
                        paragraphs.append(para)
                    except ParserError as exc:
                        logger.debug(
                            "ProcedureDivisionParser: recovering from paragraph "
                            "error: {}",
                            exc.message,
                        )
                        before = stream.position
                        state.record_and_synchronise(
                            message=exc.message,
                            error_token=stream.current(),
                            context=RecoveryContext.PROCEDURE_DIVISION,
                            code="SYN005",
                        )
                        # Guarantee forward progress (#108-12):
                        # synchronise() can anchor without consuming.
                        if stream.position == before:
                            stream.advance()
                    continue

            # A lone PERIOD is a stray sentence terminator (the same
            # situation data_parser already handles for the DATA
            # DIVISION); consume it and keep looking for the next
            # paragraph rather than treating it as a problem.
            if tok.type is TokenType.PERIOD:
                stream.advance()
                continue

            # An unrecognised token at paragraph level.  Previously this
            # silently abandoned every remaining paragraph in the
            # PROCEDURE DIVISION with only a DEBUG log (#108-01).
            # Diagnose it explicitly, then try to recover to the next
            # paragraph or division boundary instead of stopping
            # outright, so paragraphs further in the file are not lost
            # needlessly.
            before = stream.position
            state.record_and_synchronise(
                message=(
                    f"unexpected token {tok.lexeme!r} at PROCEDURE DIVISION "
                    "paragraph level; attempting to resume at the next "
                    "paragraph"
                ),
                error_token=tok,
                context=RecoveryContext.PROCEDURE_DIVISION,
                code="SYN001",
            )
            # Guarantee forward progress: synchronise() can anchor on a
            # section/division header without consuming it (#108-12).
            if stream.position == before:
                stream.advance()

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

            # NEXT SENTENCE is two words, so it cannot be recognised by
            # the single-lexeme matching every other statement uses.
            # Checked before the paragraph-label heuristic below because
            # "NEXT" followed by "SENTENCE" would otherwise reach that
            # heuristic's peek() and (SENTENCE is not a period) simply
            # fall through as an unrecognised token (#108-06).
            if (
                tok.type is TokenType.IDENTIFIER
                and tok.lexeme.upper() == "NEXT"
                and stream.peek().type is TokenType.IDENTIFIER
                and stream.peek().lexeme.upper() == "SENTENCE"
            ):
                self._skip_unsupported_statement(state, word_count=2)
                continue

            # Detect a paragraph label (name followed by period where the
            # name is not a recognised statement lexeme).  An
            # UNSUPPORTED_STATEMENT_LEXEMES verb must be excluded here
            # too: CONTINUE and EXIT are almost always written as a bare
            # word before the period ("CONTINUE." / "EXIT."), which is
            # exactly this shape, so without this check they were
            # silently mistaken for the start of a new paragraph
            # (#108-06) instead of reaching the unsupported-statement
            # handling below.
            if tok.type in (TokenType.IDENTIFIER, TokenType.KEYWORD):
                upper = tok.lexeme.upper()
                next_tok = stream.peek()
                if (
                    next_tok.type is TokenType.PERIOD
                    and upper not in _STATEMENT_LEXEMES
                    and upper not in _UNSUPPORTED_STATEMENT_LEXEMES
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
                        before = stream.position
                        state.record_and_synchronise(
                            message=exc.message,
                            error_token=stream.current(),
                            context=RecoveryContext.STATEMENT,
                            code="SYN005",
                        )
                        # Guarantee forward progress (#108-12):
                        # synchronise() can anchor without consuming.
                        if stream.position == before:
                            stream.advance()
                    continue

                # A COBOL verb this parser does not implement yet.
                # Previously the loop simply broke here with no
                # diagnostic, silently discarding every remaining
                # statement in the paragraph (task #104, §11).  Report it
                # and skip just that statement so the ones after it are
                # still parsed.
                if upper in _UNSUPPORTED_STATEMENT_LEXEMES:
                    self._skip_unsupported_statement(state)
                    continue

            # A lone PERIOD here is a stray sentence terminator -- the
            # same situation data_parser already handles for the DATA
            # DIVISION ("Silently consume stray PERIOD tokens left
            # behind by panic-mode recovery").  It is not itself a
            # problem to diagnose; consuming it lets the loop reach the
            # statement or paragraph that follows.
            if tok.type is TokenType.PERIOD:
                stream.advance()
                continue

            # An unrecognised token at statement level.  Previously this
            # silently discarded every remaining statement in the
            # paragraph with only a DEBUG log (#108-05).  Diagnose it
            # explicitly, then try to recover to the next statement or
            # paragraph boundary instead of abandoning outright, so
            # valid content further in the paragraph is not lost
            # needlessly.
            before = stream.position
            state.record_and_synchronise(
                message=(
                    f"unexpected token {tok.lexeme!r} at statement level; "
                    "attempting to resume at the next statement or "
                    "paragraph"
                ),
                error_token=tok,
                context=RecoveryContext.STATEMENT,
                code="SYN001",
            )
            # Guarantee forward progress: synchronise() can anchor on a
            # section/division header without consuming it (#108-12).
            if stream.position == before:
                stream.advance()

        return statements

    # ------------------------------------------------------------------
    # Unsupported statement handling
    # ------------------------------------------------------------------

    def _skip_unsupported_statement(
        self, state: ParserState, word_count: int = 1
    ) -> None:
        """
        Record and skip one statement whose verb has no parser yet.

        The cursor must be on the verb's first token. Everything up to and
        including the statement's terminating period is consumed. The scan
        stops short at EOF or at the next division header so it can never
        run past the procedure division.

        An unsupported statement written *without* a period terminator
        also stops at the start of the next statement, so that the
        statements after it are still parsed rather than swallowed along
        with it (finding F-107-01)::

            MOVE 'X' TO WS-A
            OPEN INPUT F1
            STOP RUN.

        Here the skip ends at ``STOP`` instead of running on to the
        period that terminates ``STOP RUN``.

        Scope-opening verbs with a known closing word (currently only
        ``EVALUATE`` -> ``END-EVALUATE``) are skipped by matching that
        closing word, honoring same-verb nesting, rather than by scanning
        for the next period. This matters because a scope-opening
        construct used as the *last* statement inside an enclosing
        ``IF``/``ELSE`` block legitimately has no period of its own — its
        end is implied by the enclosing block's own ``END-IF`` — and a
        naive "scan to next period" would run straight past that
        ``END-IF`` and consume whatever real statement follows it
        (docs/MMIM_PARSER_VALIDATION_FIX.md, COMPUTE/EVALUATE-inside-IF
        follow-up). Once the matching closing word is found, one
        immediately-following period is consumed if present, and the skip
        always stops there — never continuing to hunt for a later period.

        ``SEARCH`` (the other scope-opening verb) has no matching entry in
        ``_SCOPE_CLOSE_WORDS`` and keeps the original, unbounded
        scan-to-next-period behavior unchanged — out of scope here since
        the paragraph-level case this exists for was never affected and
        no test exercises ``SEARCH`` inside an ``IF``/``ELSE`` block.

        Args:
            state: Active parser state, positioned on the verb.
            word_count:
                Number of leading tokens that make up the verb, for
                multi-word statements this parser has no single lexeme
                for (``NEXT SENTENCE`` is two tokens).  Defaults to 1.
        """
        stream = state.stream
        verb_token = stream.advance()
        words = [verb_token.lexeme]
        for _ in range(word_count - 1):
            words.append(stream.advance().lexeme)
        verb_text = " ".join(words).upper()
        open_word = verb_token.lexeme.upper()
        opens_scope = open_word in _SCOPE_OPENING_LEXEMES
        close_word = _SCOPE_CLOSE_WORDS.get(open_word)

        logger.debug(
            "ProcedureDivisionParser: skipping unsupported statement {!r}.",
            verb_text,
        )
        state.recovery_manager.record_error(
            message=(
                f"unsupported statement {verb_text!r}; skipped to the "
                "end of the statement"
            ),
            error_token=verb_token,
            context=RecoveryContext.STATEMENT,
            code="SYN100",
        )

        if open_word == "READ":
            self._skip_read_statement(stream)
            return

        if opens_scope and close_word is not None:
            self._skip_to_matching_close_word(stream, open_word, close_word)
            return

        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.EOF:
                break
            if tok.type is TokenType.PERIOD:
                stream.advance()  # consume the terminator
                break
            if not opens_scope and _at_operand_boundary(tok):
                # The unsupported statement had no period; the next
                # statement starts here and must not be consumed too.
                break
            if (
                tok.type is TokenType.KEYWORD
                and tok.lexeme.upper() in _DIVISION_KEYWORDS
                and stream.peek().type is TokenType.KEYWORD
                and stream.peek().lexeme.upper() == "DIVISION"
            ):
                break
            stream.advance()

    @staticmethod
    def _skip_to_matching_close_word(
        stream: TokenStream, open_word: str, close_word: str
    ) -> None:
        """
        Consume tokens up to and including the ``close_word`` that matches
        the already-consumed ``open_word``, honoring same-verb nesting
        (an ``open_word`` seen again before the matching ``close_word``
        increments the nesting depth). One immediately-following period is
        then consumed if present. Stops early at EOF or a division header,
        exactly like the generic skip path — never reads past that.
        """
        depth = 1
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.EOF:
                return
            if tok.type in (TokenType.KEYWORD, TokenType.IDENTIFIER):
                upper = tok.lexeme.upper()
                if upper == open_word:
                    depth += 1
                    stream.advance()
                    continue
                if upper == close_word:
                    depth -= 1
                    stream.advance()
                    if depth <= 0:
                        if stream.current().type is TokenType.PERIOD:
                            stream.advance()
                        return
                    continue
                if (
                    tok.type is TokenType.KEYWORD
                    and upper in _DIVISION_KEYWORDS
                    and stream.peek().type is TokenType.KEYWORD
                    and stream.peek().lexeme.upper() == "DIVISION"
                ):
                    return
            stream.advance()

    @staticmethod
    def _skip_read_statement(stream: TokenStream) -> None:
        """
        Skip an unsupported ``READ`` statement (the cursor is positioned
        just past the already-consumed ``READ`` verb token).

        ``READ`` has no AST node or parser of its own (:data:`SYN100`,
        same as every other verb in :data:`_UNSUPPORTED_STATEMENT_LEXEMES`).
        Its ``AT END`` / ``NOT AT END`` clauses legitimately contain full
        imperative statements (``MOVE``, ``ADD``, ...) — real COBOL grammar,
        confirmed against the corpus (e.g. ``READ F INTO R AT END MOVE 'Y'
        TO EOF-FLAG NOT AT END ADD 1 TO COUNT END-READ.``). Before this
        method existed, the generic "scan to next period, but stop at the
        first statement-verb token" skip (below, still used for every other
        unsupported verb without a known closing word) treated that nested
        ``MOVE``/``ADD`` as the *next real statement* — ending the READ's
        skip early and leaving the clause's tail (e.g. ``TO WS-EOF-FLAG NOT
        AT END``) to be absorbed as part of that nested statement's own
        operand text by the ordinary statement parser, corrupting it (a
        ``MoveStatementNode`` with target ``"WS-EOF-FLAG NOT AT END"``,
        traced directly to this mechanism; see
        ``docs/MMIM_READ_AT_END_PARSING_FIX.md``).

        This method instead tracks whether an ``AT`` token (the only word
        that introduces ``AT END``/``NOT AT END`` in this grammar) has been
        seen yet:

        * **Before** the first ``AT``: behaves exactly like the generic
          skip — a statement-boundary token (:func:`_at_operand_boundary`)
          still ends the skip early, so a bare ``READ F1`` with no clause at
          all, immediately followed by another period-less unsupported or
          supported statement, is completely unaffected (this is the shape
          ``tests/parser/test_statement_boundaries.py`` and
          ``tests/parser/test_token_type_regressions.py`` already pin).
        * **From** the first ``AT`` onward: statement-boundary tokens no
          longer end the skip (they are legitimately part of a clause's
          nested statement) — only ``END-READ`` or a bare period does.

        A bare period always ends the READ, at any point (real COBOL: a
        ``READ`` with no ``END-READ`` is closed by the sentence's own
        terminating period — verified against
        ``tests/fixtures/phase5/file_processing.cbl``,
        ``READ CUST-FILE AT END MOVE 'Y' TO WS-EOF.``, which has no
        ``END-READ`` at all). ``END-READ`` is still recognised even before
        any ``AT`` is seen, for a (COBOL-legal but corpus-unseen) ``READ F1
        END-READ.`` with no clause. Stops early at EOF or a division header,
        matching every other skip path in this class.

        Scope note: only ``AT END``/``NOT AT END`` are recognised. A READ
        using ``INVALID KEY``/``NOT INVALID KEY`` instead (random access)
        has no ``AT`` token, so it is not protected by this method and keeps
        the pre-existing generic-skip behavior — not present anywhere in the
        current corpus or test fixtures, and deliberately out of this
        task's scope (see the fix doc's "remaining gaps").
        """
        seen_at = False
        while not stream.eof():
            tok = stream.current()
            if tok.type is TokenType.EOF:
                return
            if tok.type is TokenType.PERIOD:
                stream.advance()
                return
            if tok.type in (TokenType.KEYWORD, TokenType.IDENTIFIER):
                upper = tok.lexeme.upper()
                if upper == "END-READ":
                    stream.advance()
                    if stream.current().type is TokenType.PERIOD:
                        stream.advance()
                    return
                if upper == "AT":
                    seen_at = True
                elif not seen_at and _at_operand_boundary(tok):
                    return
                elif (
                    tok.type is TokenType.KEYWORD
                    and upper in _DIVISION_KEYWORDS
                    and stream.peek().type is TokenType.KEYWORD
                    and stream.peek().lexeme.upper() == "DIVISION"
                ):
                    return
            stream.advance()

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
        if upper == "IF":
            return self._parse_if_statement(state)
        if upper == "PERFORM":
            return self._parse_perform_statement(state)
        if upper == "GO":
            return self._parse_go_to_statement(state)

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
            if _at_operand_boundary(tok):
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
        self._consume_optional_period(state)

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
            if _at_operand_boundary(tok):
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
            if _at_operand_boundary(tok):
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
        self._consume_optional_period(state)

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
        self._consume_optional_period(state)

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
        self._consume_optional_period(state)

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
            if _at_operand_boundary(tok) or tok.lexeme.upper() == "TO":
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
            if _at_operand_boundary(tok):
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
        self._consume_optional_period(state)

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
            if _at_operand_boundary(tok) or tok.lexeme.upper() == "FROM":
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
            if _at_operand_boundary(tok):
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
        self._consume_optional_period(state)

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
            if _at_operand_boundary(tok) or tok.lexeme.upper() == "BY":
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
            if _at_operand_boundary(tok):
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
        self._consume_optional_period(state)

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
            if _at_operand_boundary(tok) or tok.lexeme.upper() == "INTO":
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
            if _at_operand_boundary(tok):
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
        self._consume_optional_period(state)

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
            if _at_operand_boundary(tok) or tok.lexeme.upper() == "USING":
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
                if _at_operand_boundary(tok):
                    break
                arguments.append(tok.lexeme)
                stream.advance()

        end: Position = stream.current().position
        self._consume_optional_period(state)

        return CallStatementNode(
            start_position=start,
            end_position=end,
            target=target,
            arguments=tuple(arguments),
        )

    def _consume_optional_period(self, state: ParserState) -> None:
        if state.stream.current().type is TokenType.PERIOD:
            state.stream.advance()

    def _diagnose_unterminated_final_sentence(
        self, state: ParserState, *, has_paragraphs: bool
    ) -> None:
        """
        Record ``SYN002`` when the PROCEDURE DIVISION ends without a period.

        Statement parsers treat their trailing period as optional
        (:meth:`_consume_optional_period`), because a statement nested in
        ``IF``/``PERFORM UNTIL`` legitimately has none and a bare statement
        parser cannot know its context. That leniency also silently
        accepted the one place a period is always required -- the final
        sentence of the program -- so ``MOVE 1 TO X`` ending the source
        produced no diagnostic at all, although the diagnostic taxonomy
        (``SYN002 "Missing period"``) and this method's documented
        contract both promise one. Only end-of-input is checked here: a
        period-less statement followed by more statements is idiomatic
        COBOL and stays accepted.

        Args:
            state: The active parser state, positioned after the last
                paragraph.
            has_paragraphs: Whether at least one paragraph was parsed;
                an empty division has no sentence to terminate.
        """
        stream = state.stream
        if not has_paragraphs or not stream.eof() or stream.position == 0:
            return
        last = stream.peek(-1)
        if last.type is TokenType.PERIOD:
            return
        state.recovery_manager.record_error(
            message=(
                f"expected '.' to end the last sentence, got end of input "
                f"after {last.lexeme!r}"
            ),
            error_token=last,
            context=RecoveryContext.PROCEDURE_DIVISION,
            code="SYN002",
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

    # ------------------------------------------------------------------
    # Control flow statement parsers
    # ------------------------------------------------------------------

    def _parse_simple_condition(self, state: ParserState) -> tuple[str, str, str]:
        """
        Parse one ``<operand> [NOT] <comparison-operator> <operand>`` triple —
        the shape both a plain ``IF`` condition and each ``AND``/``OR``-
        joined term of a compound one share. Does not consume a *leading*
        ``AND``/``OR``/``NOT`` or ``(``/``)`` — a compound or parenthesised
        condition is assembled by the caller from repeated calls to this
        method (see :meth:`_parse_if_statement`).

        A ``NOT`` sitting *between* the two operands (COBOL's own
        ``relational-operator ::= [NOT] { = | > | < | >= | <= | <> }``
        grammar, e.g. ``IF WS-CODE NOT = 'AUTO'``) negates the operator that
        follows it (task #stage25): it is consumed here and the operator is
        replaced by its negation from :data:`_NEGATED_OPERATOR` before the
        triple is returned, so every caller -- and everything downstream:
        the IR, the Java backend, business-rule/behavioral text -- sees the
        already-supported plain spelling (``NOT =`` becomes ``<>``) and
        needs no further change. This is a different position from the
        *leading* ``NOT`` before an entire condition (``IF NOT WS-CODE =
        'AUTO'``, or a level-88 reference), which :meth:`_parse_condition_term`
        handles for a known condition-name and otherwise deliberately leaves
        unconsumed -- that remains the separate, out-of-scope gap its own
        docstring names.

        Callers needing to admit a bare level-88 condition-name reference
        alongside an ordinary comparison should call
        :meth:`_parse_condition_term` instead, which dispatches here only
        once it has ruled that out.

        Either operand may also be a figurative constant (task #stage26,
        e.g. ``IF WS-CODE = SPACES``) — see
        :func:`_is_comparison_operand_token` and :data:`_FIGURATIVE_CONSTANT_KEYWORDS`
        for exactly which spellings that widens acceptance for and why.
        """
        stream = state.stream

        tok = stream.current()
        if not _is_comparison_operand_token(tok):
            raise ParserError(
                "expected operand for IF condition",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )
        left = tok.lexeme
        stream.advance()

        negated = False
        if matches_grammar_word(stream.current(), {"NOT"}):
            negated = True
            stream.advance()  # consume NOT; the operator it negates follows

        tok = stream.current()
        if not _is_comparison_operator_token(tok):
            raise ParserError(
                "expected comparison operator in IF condition",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )
        if negated:
            negation = _NEGATED_OPERATOR.get(tok.lexeme)
            if negation is None:  # pragma: no cover — every accepted lexeme is mapped
                raise ParserError(
                    f"NOT is not supported before comparison operator {tok.lexeme!r}",
                    line=tok.position.line,
                    column=tok.position.column,
                    offset=tok.position.offset,
                )
            operator = negation
        else:
            operator = tok.lexeme
        stream.advance()

        tok = stream.current()
        if not _is_comparison_operand_token(tok):
            raise ParserError(
                "expected operand for IF condition",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )
        right = tok.lexeme
        stream.advance()

        return left, operator, right

    def _parse_condition_term(self, state: ParserState) -> tuple[str, str, str]:
        """
        Parse one ``IF``-condition term, admitting a bare level-88
        condition-name reference (optionally ``NOT``-prefixed) in addition
        to the ordinary ``<operand> <comparison-operator> <operand>``
        shape :meth:`_parse_simple_condition` already handles. This is the
        entry point :meth:`_parse_if_statement` calls for the leading term
        and every ``AND``/``OR``-joined one; :meth:`_parse_simple_condition`
        itself is unchanged and still does the actual comparison parsing.

        A bare identifier is only ever treated as a condition-name
        reference when it is one of ``state.known_condition_names`` —
        collected from the program's own DATA DIVISION AST by
        :class:`~app.parser.syntax.program_parser.ProgramParser` before
        the PROCEDURE DIVISION is parsed (empty if there is no such
        state, e.g. a procedure-division-only unit test that never set
        it). An identifier the DATA DIVISION never declared as level-88
        is never guessed at — it falls through to
        :meth:`_parse_simple_condition`, which raises the same
        "expected comparison operator" error as before this method
        existed, preserving that diagnostic for every other case
        (including the unrelated ``NOT =`` negated-equality gap, which
        this method does not attempt to handle: ``NOT`` here is accepted
        only immediately before a *known* condition-name).

        Returns:
            A ``(left, operator, right)`` triple. For a condition-name
            term, ``operator`` is :data:`_CONDITION_NAME_TRUE_OPERATOR` or
            :data:`_CONDITION_NAME_FALSE_OPERATOR` and ``left``/``right``
            both hold the condition-name itself (see the module-level
            comment above those constants for why).
        """
        stream = state.stream
        known = state.known_condition_names

        negated = False
        lookahead_index = 0
        if matches_grammar_word(stream.current(), {"NOT"}):
            negated = True
            lookahead_index = 1

        candidate = stream.peek(lookahead_index)
        if candidate.type is TokenType.IDENTIFIER and candidate.lexeme.upper() in known:
            following = stream.peek(lookahead_index + 1)
            if not _is_comparison_operator_token(following):
                if negated:
                    stream.advance()  # consume NOT
                name = candidate.lexeme.upper()
                stream.advance()  # consume the condition-name identifier
                operator = (
                    _CONDITION_NAME_FALSE_OPERATOR
                    if negated
                    else _CONDITION_NAME_TRUE_OPERATOR
                )
                return name, operator, name

        # Not a recognised condition-name reference (negated or not) --
        # fall through to the ordinary comparison grammar, unchanged. A
        # leading NOT that turned out not to precede a known
        # condition-name is deliberately left unconsumed here: it is the
        # unrelated, out-of-scope "NOT <comparison>" gap, and
        # _parse_simple_condition's existing "expected operand"/"expected
        # comparison operator" diagnostics on the NOT token itself are the
        # same honest failure this whole grammar already gave it.
        return self._parse_simple_condition(state)

    def _parse_if_statement(self, state: ParserState) -> IfStatementNode:
        stream = state.stream
        start = stream.current().position
        stream.advance()  # consume IF

        # Parse the first (and, for a plain IF, only) condition term --
        # either an ordinary comparison or a level-88 condition-name
        # reference (see _parse_condition_term).
        left, operator, right = self._parse_condition_term(state)

        # Compound condition: zero or more further AND/OR-joined terms.
        # AND binds tighter than OR (COBOL's own precedence rule); see
        # ConditionTerm's docstring. Parenthesised sub-conditions are
        # deliberately not handled here — the operand check inside
        # _parse_simple_condition rejects a leading '(' with a clear
        # ParserError rather than silently misparsing it.
        extra_conditions: list[ConditionTerm] = []
        while stream.current().lexeme.upper() in ("AND", "OR"):
            connector = stream.current().lexeme.upper()
            stream.advance()  # consume AND/OR
            term_left, term_operator, term_right = self._parse_condition_term(state)
            extra_conditions.append(
                ConditionTerm(
                    connector=connector,
                    left=term_left,
                    operator=term_operator,
                    right=term_right,
                )
            )

        # Parse statements until ELSE or END-IF
        #
        # An unsupported verb (COMPUTE, EVALUATE, ...) here used to raise a
        # hard ParserError, which the caller's statement-level recovery
        # resolves by synchronising to the next PERIOD -- and a structured
        # IF/END-IF has no interior periods, so that swallowed the rest of
        # the paragraph (docs/MMIM_PARSER_VALIDATION_FIX.md §7). The
        # paragraph-level statement loop already has a graceful path for
        # exactly this case (_skip_unsupported_statement, tested in
        # tests/parser/test_statement_boundaries.py::
        # test_scope_delimited_construct_still_skipped_whole); this mirrors
        # it here instead of inventing new recovery behavior.
        then_statements = []
        while not stream.eof():
            tok = stream.current()
            if tok.lexeme.upper() in ("ELSE", "END-IF"):
                break
            if tok.lexeme.upper() in _STATEMENT_LEXEMES:
                then_statements.append(self._parse_statement(state))
            elif tok.lexeme.upper() in _UNSUPPORTED_STATEMENT_LEXEMES:
                self._skip_unsupported_statement(state)
            else:
                raise ParserError(
                    "expected statement in IF block",
                    line=tok.position.line,
                    column=tok.position.column,
                    offset=tok.position.offset,
                )

        else_statements = []
        if stream.current().lexeme.upper() == "ELSE":
            stream.advance()  # consume ELSE
            while not stream.eof():
                tok = stream.current()
                if tok.lexeme.upper() == "END-IF":
                    break
                if tok.lexeme.upper() in _STATEMENT_LEXEMES:
                    else_statements.append(self._parse_statement(state))
                elif tok.lexeme.upper() in _UNSUPPORTED_STATEMENT_LEXEMES:
                    self._skip_unsupported_statement(state)
                else:
                    raise ParserError(
                        "expected statement in ELSE block",
                        line=tok.position.line,
                        column=tok.position.column,
                        offset=tok.position.offset,
                    )

        if stream.current().lexeme.upper() == "END-IF":
            stream.advance()  # consume END-IF
        else:
            tok = stream.current()
            raise ParserError(
                "missing END-IF",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        # Every other statement parser consumes its own trailing period
        # via _consume_optional_period; this one did not, leaving a
        # stray PERIOD for the caller.  _parse_statements has no
        # "skip a lone period" case, so that stray token fell into the
        # silent "anything else -- unexpected; stop" abandonment path
        # (#108-05): a single well-formed `IF ... END-IF.` followed by
        # any further statement discarded that statement and everything
        # after it, with zero diagnostics.
        self._consume_optional_period(state)

        return IfStatementNode(
            start_position=start,
            end_position=stream.current().position,
            condition_left=left,
            condition_operator=operator,
            condition_right=right,
            then_statements=tuple(then_statements),
            else_statements=tuple(else_statements),
            extra_conditions=tuple(extra_conditions),
        )

    def _parse_perform_statement(self, state: ParserState) -> StatementNode:
        stream = state.stream
        start = stream.current().position
        stream.advance()  # consume PERFORM

        tok = stream.current()
        if tok.lexeme.upper() == "UNTIL":
            stream.advance()  # consume UNTIL

            # Parse condition
            tok = stream.current()
            left = tok.lexeme
            stream.advance()

            tok = stream.current()
            operator = tok.lexeme
            stream.advance()

            tok = stream.current()
            right = tok.lexeme
            stream.advance()

            # An unsupported verb (READ, COMPUTE, EVALUATE, ...) here used to
            # raise a hard ParserError, which the caller's statement-level
            # recovery resolves by synchronising to the next PERIOD -- and a
            # structured PERFORM UNTIL/END-PERFORM has no interior periods of
            # its own guaranteed, so that could swallow the rest of the
            # paragraph, exactly the defect class
            # docs/MMIM_PARSER_VALIDATION_FIX.md §7 fixed for IF/ELSE blocks
            # (task #stage28; the identical gap was found but left
            # unfixed there, docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md §8). This
            # mirrors that fix exactly: the same graceful
            # _skip_unsupported_statement path _parse_if_statement's
            # then/else loops already use.
            statements = []
            while not stream.eof():
                tok = stream.current()
                if tok.lexeme.upper() == "END-PERFORM":
                    break
                if tok.lexeme.upper() in _STATEMENT_LEXEMES:
                    statements.append(self._parse_statement(state))
                elif tok.lexeme.upper() in _UNSUPPORTED_STATEMENT_LEXEMES:
                    self._skip_unsupported_statement(state)
                else:
                    raise ParserError(
                        "expected statement in PERFORM block",
                        line=tok.position.line,
                        column=tok.position.column,
                        offset=tok.position.offset,
                    )

            if stream.current().lexeme.upper() == "END-PERFORM":
                stream.advance()  # consume END-PERFORM
            else:
                tok = stream.current()
                raise ParserError(
                    "missing END-PERFORM",
                    line=tok.position.line,
                    column=tok.position.column,
                    offset=tok.position.offset,
                )

            # Consume the same stray trailing period _parse_if_statement
            # was fixed to consume (#108-05): every other statement
            # parser calls _consume_optional_period, and without it here
            # a lone PERIOD after END-PERFORM fell into the silent
            # statement-loop abandonment path.
            self._consume_optional_period(state)

            from app.parser.ast.statements import PerformUntilStatementNode

            return PerformUntilStatementNode(
                start_position=start,
                end_position=stream.current().position,
                condition_left=left,
                condition_operator=operator,
                condition_right=right,
                statements=tuple(statements),
            )
        else:
            # Inline PERFORM with just a target (e.g. PERFORM PARAGRAPH-NAME),
            # optionally followed by a THRU/THROUGH range end (task
            # #stage16: PERFORM A THRU C). Neither "THRU" nor "THROUGH" is a
            # reserved word in this lexer -- both arrive as a bare
            # IDENTIFIER token, exactly like READ's "AT" marker
            # (_skip_read_statement) -- so it is recognised here by lexeme,
            # not token type.
            if tok.type is not TokenType.IDENTIFIER:
                raise ParserError(
                    "expected paragraph name for PERFORM",
                    line=tok.position.line,
                    column=tok.position.column,
                    offset=tok.position.offset,
                )
            target = tok.lexeme
            stream.advance()

            thru_target = ""
            tok = stream.current()
            if tok.lexeme.upper() in ("THRU", "THROUGH"):
                stream.advance()  # consume THRU/THROUGH
                tok = stream.current()
                if tok.type is not TokenType.IDENTIFIER:
                    raise ParserError(
                        "expected paragraph name after THRU/THROUGH in PERFORM",
                        line=tok.position.line,
                        column=tok.position.column,
                        offset=tok.position.offset,
                    )
                thru_target = tok.lexeme
                stream.advance()

            return PerformStatementNode(
                start_position=start,
                end_position=stream.current().position,
                target=target,
                thru_target=thru_target,
            )

    def _parse_go_to_statement(self, state: ParserState) -> GoToStatementNode:
        """
        Parse a simple ``GO TO paragraph-name`` statement (task #stage17).

        Grammar rule::

            go-to-statement ::= GO TO paragraph-name PERIOD

        Neither ``GO`` nor ``TO`` is a reserved word in this lexer (both
        arrive as ordinary ``IDENTIFIER`` tokens), so ``TO`` is recognised
        here by lexeme, the same way ``PERFORM``'s ``THRU``/``THROUGH`` and
        ``READ``'s ``AT`` markers already are.

        Only the single-target form is implemented. Real COBOL also allows
        ``GO TO A B C ... DEPENDING ON identifier`` (a computed multi-way
        jump); this corpus contains no such usage (confirmed by direct
        search across all 45 sources -- only ever ``GO TO`` a single
        paragraph name), so it is deliberately not implemented here rather
        than guessed at. If a second identifier follows the target instead
        of a period (i.e. something resembling that form), it is left on
        the stream: the paragraph-level statement loop's existing
        unexpected-token recovery reports and safely skips it, exactly as
        it already does for any other not-yet-supported clause extension
        -- this method never silently narrows a multi-target jump down to
        "always go to the first name".

        Args:
            state: Active parser state; cursor on ``GO``.

        Returns:
            An immutable :class:`~app.parser.ast.statements.GoToStatementNode`.

        Raises:
            ParserError: If ``TO`` or the target paragraph name is missing.
        """
        stream = state.stream
        start = stream.current().position
        stream.advance()  # consume GO

        tok = stream.current()
        if tok.lexeme.upper() != "TO":
            raise ParserError(
                "expected TO after GO",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )
        stream.advance()  # consume TO

        tok = stream.current()
        if tok.type is not TokenType.IDENTIFIER:
            raise ParserError(
                "expected paragraph name after GO TO",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )
        target = tok.lexeme
        stream.advance()

        end = stream.current().position
        self._consume_optional_period(state)

        return GoToStatementNode(
            start_position=start,
            end_position=end,
            target=target,
        )
