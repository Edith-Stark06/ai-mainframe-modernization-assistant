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
    - COPY book expansion -- happens upstream of this parser entirely
      (task #stage45, :class:`~app.parser.resolver.copybook.CopybookExpander`,
      run by ``AnalysisService.analyze_file`` before the lexer even sees
      the source), so no ``COPY`` token ever reaches this class.
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

from collections.abc import Callable

from loguru import logger

from app.parser.ast.paragraphs import ParagraphNode
from app.parser.ast.procedure import ProcedureDivisionNode
from app.parser.ast.statements import (
    ArithmeticExpression,
    BinaryExpression,
    ConditionTerm,
    ComputeStatementNode,
    DisplayStatementNode,
    GobackStatementNode,
    GoToStatementNode,
    MoveStatementNode,
    OperandExpression,
    StatementNode,
    StopRunStatementNode,
    AddStatementNode,
    SubtractStatementNode,
    MultiplyStatementNode,
    DivideStatementNode,
    CallStatementNode,
    IfStatementNode,
    PerformStatementNode,
    ReadStatementNode,
    Subscript,
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
        "COMPUTE",
        "MULTIPLY",
        "DIVIDE",
        "CALL",
        "IF",
        "PERFORM",
        "GO",
        "READ",
    }
)

# ---------------------------------------------------------------------------
# Verbs that are real COBOL statements but have no parser and no AST node
# yet.  They are recognised only so that encountering one produces an
# explicit diagnostic and skips that single statement, instead of
# silently abandoning the rest of the paragraph.  Most reach the parser
# as IDENTIFIER; a few (EVALUATE, ...) are reserved lexer words, so they
# are matched by lexeme either way.
#
# COMPUTE moved out of this set (task #stage35): it now has a parser and
# an AST node (ComputeStatementNode) and is dispatched via
# _STATEMENT_LEXEMES/_parse_compute like ADD/SUBTRACT/MULTIPLY/DIVIDE.
# A COMPUTE using syntax this parser does not implement -- ROUNDED or an
# intrinsic FUNCTION operand, neither present in the 45-source training
# corpus -- is still routed here via the dedicated pre-check
# _compute_has_supported_syntax, so it still gets the same graceful
# SYN100 skip every other unsupported verb gets, never a hard ParserError
# that could unwind an enclosing IF/PERFORM block.
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
        # READ moved to _STATEMENT_LEXEMES (task #stage40): it now has a
        # parser and an AST node (ReadStatementNode) and is dispatched via
        # _parse_read_statement, mirroring exactly how COMPUTE moved out
        # of this set at task #stage35. OPEN/CLOSE/WRITE remain here --
        # not evidenced as needed for the Stage 40 vertical slice (see
        # the Stage 40 discovery report).
        "WRITE",
        "REWRITE",
        "DELETE",
        "START",
        "EVALUATE",
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
        # task #stage40: READ's own closing word, and the bare word that
        # introduces its "NOT AT END" clause. Without these, a nested
        # statement's own operand reader (e.g. MOVE's target-accumulation
        # loop, called for real now that READ's AT END/NOT AT END clauses
        # are actually parsed instead of discarded) does not know either
        # word ends *its* operand -- reproducing, inside real parsing,
        # exactly the corruption class docs/MMIM_READ_AT_END_PARSING_FIX.md
        # already fixed once for the discard-only skip path (a
        # MoveStatementNode with target "WS-EOF-FLAG NOT AT END" or
        # "WS-EOF END-READ"). "NOT" is safe to add globally: it is never
        # legitimate mid-operand text (COBOL's own condition-level "NOT"
        # is always consumed explicitly, before reaching the generic
        # operand reader -- see _parse_condition_term/_parse_simple_condition,
        # neither of which goes through this boundary set at all).
        "END-READ",
        "NOT",
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


# ---------------------------------------------------------------------------
# Arithmetic-operator token recognition, for COMPUTE expressions (task
# #stage35). The lexer deliberately emits '+'/'-'/'*'/'/' as their own
# UNKNOWN tokens everywhere (see data_parser._NUMERIC_SIGNS and
# _read_perform_from_by_operand's identical '+'/'-' handling) rather than
# promoting them to dedicated token types, precisely so that a COMPUTE
# expression's operators are recognised here by lexeme, the same
# established way every other '+'/'-' consumer in this codebase already
# does, instead of the lexer needing to know in advance which meaning a
# given '+'/'-' will turn out to have.
# ---------------------------------------------------------------------------
_ARITHMETIC_OPERATOR_LEXEMES: frozenset[str] = frozenset({"+", "-", "*", "/"})


def _is_arithmetic_operator_token(token: Token) -> bool:
    """``True`` if *token* is a COMPUTE expression arithmetic operator."""
    return (
        token.type is TokenType.UNKNOWN and token.lexeme in _ARITHMETIC_OPERATOR_LEXEMES
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


#: Words that begin a ``DISPLAY`` clause this parser does not model
#: (``DISPLAY x UPON CONSOLE``, ``DISPLAY x WITH NO ADVANCING``). A
#: statement containing one keeps the pre-existing single joined operand
#: rather than being split into per-operand pieces that would then
#: include the clause words as if they were data.
_DISPLAY_CLAUSE_WORDS: frozenset[str] = frozenset({"UPON", "WITH", "NO", "ADVANCING"})


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

                # COMPUTE ROUNDED / COMPUTE ... FUNCTION ... (task #stage35):
                # recognised but not implemented -- neither is present in the
                # 45-source training corpus.  Checked here, before the
                # _STATEMENT_LEXEMES branch below, via pure lookahead (no
                # tokens consumed), so such a COMPUTE gets the same graceful
                # SYN100 skip every other unsupported verb gets, uniformly
                # regardless of nesting -- never a ParserError, even though
                # this particular loop could otherwise recover from one.
                if upper == "COMPUTE" and not self._compute_has_supported_syntax(state):
                    self._skip_unsupported_statement_auto(state)
                    continue

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
                    self._skip_unsupported_statement_auto(state)
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

    def _skip_unsupported_statement_auto(self, state: ParserState) -> None:
        """
        Skip one unsupported statement, detecting the one multi-word
        exception :data:`_UNSUPPORTED_STATEMENT_LEXEMES` itself needs
        (task #stage34): ``EXIT PERFORM``.

        ``EXIT`` alone (a bare ``EXIT.`` statement) is exactly the
        single-token shape :meth:`_skip_unsupported_statement`'s default
        ``word_count=1`` already handles correctly. ``EXIT PERFORM`` is a
        distinct, two-word COBOL statement (found directly in the real
        corpus, nested inside an ``IF`` inside a ``PERFORM VARYING`` loop
        -- ``complex_acctbatch.cbl``'s ``4100-FIND-ACCOUNT``/
        ``4200-FIND-CUSTOMER``); without this, skipping only ``EXIT``
        left ``PERFORM`` on the stream, which every statement-list loop's
        own dispatch (``_STATEMENT_LEXEMES`` includes ``"PERFORM"``) then
        misread as the *start of a new PERFORM statement* -- reading
        whatever followed (here, ``END-IF``) as a supposed paragraph
        target and raising ``ParserError("expected paragraph name for
        PERFORM")``, which unwound the parse of the *entire* enclosing
        construct (not merely the ``EXIT`` statement) up to the nearest
        recovery point. This is a plain token-boundary correction --
        consuming ``EXIT PERFORM`` as the one statement it actually is --
        not an implementation of its true "leave the loop early"
        semantics, which remain unsupported exactly as before (no
        ``AST``/``IR`` node is produced for it either way).

        Used everywhere :meth:`_skip_unsupported_statement` was called
        with its implicit single-word default, so ``EXIT PERFORM``
        parses correctly regardless of which statement-list loop
        (paragraph-level, ``IF`` then/else, ``PERFORM`` body) it appears
        in -- one shared check, not duplicated at each call site.
        """
        stream = state.stream
        tok = stream.current()
        if tok.lexeme.upper() == "EXIT" and stream.peek(1).lexeme.upper() == "PERFORM":
            self._skip_unsupported_statement(state, word_count=2)
        else:
            self._skip_unsupported_statement(state)

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

    # `_skip_read_statement` (the dedicated AT/END-READ-aware boundary
    # skip from task's docs/MMIM_READ_AT_END_PARSING_FIX.md) was removed
    # at task #stage40: READ moved out of _UNSUPPORTED_STATEMENT_LEXEMES
    # entirely, so `_skip_unsupported_statement` -- and this method with
    # it -- is never reached for READ any more. Its AT-token-tracking
    # boundary technique lives on, generalised into real parsing, in
    # `_parse_read_clause_body` below.

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
        if upper == "COMPUTE":
            return self._parse_compute(state)
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
        if upper == "READ":
            return self._parse_read_statement(state)

        raise ParserError(
            f"unsupported statement keyword {upper!r}",
            line=tok.position.line,
            column=tok.position.column,
            offset=tok.position.offset,
        )

    # ------------------------------------------------------------------
    # Subscripted operand recognition (task #stage32)
    # ------------------------------------------------------------------

    def _try_read_subscripted_reference(
        self,
        state: ParserState,
        is_valid_after: Callable[[Token], bool],
    ) -> tuple[str, tuple[Subscript, ...]] | None:
        """
        Recognise the single-dimension subscripted-reference shape
        ``IDENTIFIER ( NUMBER|IDENTIFIER )`` at the current cursor
        position, consuming it only if it is immediately followed by a
        token *is_valid_after* accepts.

        This is the one place the structure of ``WS-ITEM(2)`` /
        ``WS-ITEM(WS-I)`` is recognised. Every caller below (the shared
        operand reader and the IF-condition parsers) goes through this
        method rather than each re-deriving the same four-token shape,
        so there is exactly one definition of "what counts as a
        subscripted reference" in this parser.

        Returns ``None`` (consuming nothing, leaving the cursor
        untouched) for every other shape — including a comma-separated
        multi-dimensional subscript (``WS-TABLE(I, J)``) and an
        arithmetic subscript expression (``WS-ITEM(WS-I + 1)``), both
        deliberately out of this stage's scope — so the caller falls
        back to the pre-existing flat-token-accumulation behaviour,
        completely unchanged from before this stage.

        Args:
            state: Active parser state.
            is_valid_after: Predicate the token immediately following the
                closing ``)`` must satisfy for this to count as a
                subscripted reference. For an operand read by MOVE/ADD/
                SUBTRACT/MULTIPLY/DIVIDE/DISPLAY this is "is it a
                statement-boundary token (or this statement's own
                keyword, e.g. ``TO``)"; for an IF condition's left
                operand it is "is it a comparison operator"; for the
                right operand of a condition (which is always exactly
                one token/reference, nothing ever follows it within the
                condition grammar) it is unconditionally ``True``,
                matching that the pre-existing code never looked ahead
                after the right operand either.

        Returns:
            ``(base_name, (Subscript,))`` and the four tokens consumed,
            or ``None`` with nothing consumed.
        """
        stream = state.stream
        base_tok = stream.current()
        if base_tok.type is not TokenType.IDENTIFIER:
            return None
        if stream.peek(1).type is not TokenType.LPAREN:
            return None
        sub_tok = stream.peek(2)
        if sub_tok.type is TokenType.NUMBER:
            kind = "literal"
        elif sub_tok.type is TokenType.IDENTIFIER:
            kind = "identifier"
        else:
            return None
        if stream.peek(3).type is not TokenType.RPAREN:
            return None
        if not is_valid_after(stream.peek(4)):
            return None

        stream.advance()  # base identifier
        stream.advance()  # (
        stream.advance()  # subscript
        stream.advance()  # )
        return base_tok.lexeme, (Subscript(kind=kind, value=sub_tok.lexeme),)

    def _read_operand(
        self,
        state: ParserState,
        extra_stop_words: frozenset[str] = frozenset(),
    ) -> tuple[str, tuple[Subscript, ...]]:
        """
        Read one COBOL operand starting at the current token, for MOVE/
        ADD/SUBTRACT/MULTIPLY/DIVIDE/DISPLAY (task #stage32).

        Two shapes are recognised:

        1. A single subscripted reference — ``NAME ( literal-or-identifier )``
           immediately followed by a genuine operand-list boundary —
           returns ``(base_name, (Subscript,))``, consuming exactly
           those four tokens. This is a *structural* result: the base
           name and the subscript are kept apart rather than joined into
           one flattened string (``"WS-ITEM ( WS-I )"``), so nothing
           downstream has to re-parse text to recover them.
        2. Anything else — the pre-existing behaviour, completely
           unchanged: every token up to the first boundary (an
           operand-list boundary, per :func:`_at_operand_boundary`, or
           any lexeme in *extra_stop_words*) is joined with a single
           space and returned as one flat string, with an empty
           subscript tuple. This is also the fallback for a subscript
           shape this stage does not represent structurally (a
           multi-dimensional or arithmetic subscript) — it keeps
           producing exactly today's (already-imperfect, pre-existing)
           flattened text rather than a new, different kind of result.

        Args:
            state: Active parser state.
            extra_stop_words: Extra uppercased lexemes that end the
                operand list beyond what :func:`_at_operand_boundary`
                already recognises (e.g. ``{"TO"}`` for MOVE's source,
                ``{"FROM"}`` for SUBTRACT, ``{"BY"}`` for MULTIPLY,
                ``{"INTO"}`` for DIVIDE).

        Returns:
            ``(text, subscripts)`` — ``subscripts`` is empty for every
            operand shape this stage does not specifically model.
        """
        stream = state.stream

        def _is_boundary(tok: Token) -> bool:
            return _at_operand_boundary(tok) or tok.lexeme.upper() in extra_stop_words

        subscripted = self._try_read_subscripted_reference(state, _is_boundary)
        if subscripted is not None:
            return subscripted

        parts: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if _is_boundary(tok):
                break
            parts.append(tok.lexeme)
            stream.advance()
        return " ".join(parts), ()

    # ------------------------------------------------------------------
    # Individual statement parsers
    # ------------------------------------------------------------------

    def _read_display_operands(
        self, state: ParserState
    ) -> tuple[str, tuple[Subscript, ...], tuple[str, ...]]:
        """
        Read a ``DISPLAY`` statement's operand list.

        Returns ``(operand, subscripts, operands)``:

        * A lone subscripted reference keeps its structural form
          (``subscripts`` populated, ``operands`` empty) -- unchanged.
        * One operand: ``operand`` is its text, ``operands`` is empty --
          exactly the pre-existing shape.
        * Two or more operands (``DISPLAY 'TOTAL: ' WS-TOTAL``):
          ``operand`` is still the space-joined text so nothing that
          already reads it changes, and ``operands`` additionally holds
          each operand separately. A parenthesised subscript stays
          attached to the name it follows, as one flattened operand.
        * A statement using ``UPON`` / ``WITH NO ADVANCING`` is left as
          the single joined operand it always was (see
          :data:`_DISPLAY_CLAUSE_WORDS`).
        """
        stream = state.stream

        subscripted = self._try_read_subscripted_reference(state, _at_operand_boundary)
        if subscripted is not None:
            return subscripted[0], subscripted[1], ()

        pieces: list[str] = []
        while not stream.eof():
            tok = stream.current()
            if _at_operand_boundary(tok):
                break
            piece = [tok.lexeme]
            stream.advance()
            if not stream.eof() and stream.current().lexeme == "(":
                depth = 0
                while not stream.eof():
                    inner = stream.current()
                    piece.append(inner.lexeme)
                    stream.advance()
                    if inner.lexeme == "(":
                        depth += 1
                    elif inner.lexeme == ")":
                        depth -= 1
                        if depth == 0:
                            break
            pieces.append(" ".join(piece))

        joined = " ".join(pieces)
        if len(pieces) < 2 or any(p.upper() in _DISPLAY_CLAUSE_WORDS for p in pieces):
            return joined, (), ()
        return joined, (), tuple(pieces)

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

        operand, operand_subscript, operands = self._read_display_operands(state)

        if not operand:
            tok = stream.current()
            raise ParserError(
                "expected operand after DISPLAY",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        end: Position = stream.current().position
        self._consume_optional_period(state)

        return DisplayStatementNode(
            start_position=start,
            end_position=end,
            operand=operand,
            operand_subscript=operand_subscript,
            operands=operands,
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
        source, source_subscript = self._read_operand(state, frozenset({"TO"}))

        if not source:
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
        target, target_subscript = self._read_operand(state)

        if not target:
            tok = stream.current()
            raise ParserError(
                "expected target operand after TO in MOVE statement",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        end: Position = stream.current().position
        self._consume_optional_period(state)

        return MoveStatementNode(
            start_position=start,
            end_position=end,
            source=source,
            target=target,
            source_subscript=source_subscript,
            target_subscript=target_subscript,
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

        left, left_subscript = self._read_operand(state, frozenset({"TO"}))

        if not left:
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

        right, right_subscript = self._read_operand(state)

        if not right:
            tok = stream.current()
            raise ParserError(
                "expected target operand after TO",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        end: Position = stream.current().position
        self._consume_optional_period(state)

        return AddStatementNode(
            start_position=start,
            end_position=end,
            left=left,
            right=right,
            left_subscript=left_subscript,
            right_subscript=right_subscript,
        )

    def _parse_subtract(self, state: ParserState) -> SubtractStatementNode:
        stream = state.stream
        start: Position = stream.current().position
        stream.advance()  # consume SUBTRACT

        left, left_subscript = self._read_operand(state, frozenset({"FROM"}))

        if not left:
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

        right, right_subscript = self._read_operand(state)

        if not right:
            tok = stream.current()
            raise ParserError(
                "expected target operand after FROM",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        end: Position = stream.current().position
        self._consume_optional_period(state)

        return SubtractStatementNode(
            start_position=start,
            end_position=end,
            left=left,
            right=right,
            left_subscript=left_subscript,
            right_subscript=right_subscript,
        )

    def _parse_multiply(self, state: ParserState) -> MultiplyStatementNode:
        stream = state.stream
        start: Position = stream.current().position
        stream.advance()  # consume MULTIPLY

        left, left_subscript = self._read_operand(state, frozenset({"BY"}))

        if not left:
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

        right, right_subscript = self._read_operand(state)

        if not right:
            tok = stream.current()
            raise ParserError(
                "expected target operand after BY",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        end: Position = stream.current().position
        self._consume_optional_period(state)

        return MultiplyStatementNode(
            start_position=start,
            end_position=end,
            left=left,
            right=right,
            left_subscript=left_subscript,
            right_subscript=right_subscript,
        )

    def _parse_divide(self, state: ParserState) -> DivideStatementNode:
        stream = state.stream
        start: Position = stream.current().position
        stream.advance()  # consume DIVIDE

        left, left_subscript = self._read_operand(state, frozenset({"INTO"}))

        if not left:
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

        right, right_subscript = self._read_operand(state)

        if not right:
            tok = stream.current()
            raise ParserError(
                "expected target operand after INTO",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

        end: Position = stream.current().position
        self._consume_optional_period(state)

        return DivideStatementNode(
            start_position=start,
            end_position=end,
            left=left,
            right=right,
            left_subscript=left_subscript,
            right_subscript=right_subscript,
        )

    # ------------------------------------------------------------------
    # COMPUTE (task #stage35)
    # ------------------------------------------------------------------

    def _compute_has_supported_syntax(self, state: ParserState) -> bool:
        """
        ``True`` if the ``COMPUTE`` statement at the cursor uses only the
        grammar :meth:`_parse_compute` implements (task #stage35): a
        target, ``=``, and an expression built from ``+ - * /``,
        parentheses, numeric literals, and (optionally subscripted)
        identifiers.

        ``ROUNDED`` and an intrinsic ``FUNCTION`` operand are real COBOL
        ``COMPUTE`` syntax -- found in ``tests/fixtures/complex_acctbatch.cbl``
        (task #stage35's investigation) -- but not anywhere in the
        45-source training corpus, so neither is implemented. A COMPUTE
        using either must still be recognised and rejected *before*
        :meth:`_parse_compute` commits to parsing it, so it falls back to
        the ordinary :meth:`_skip_unsupported_statement_auto` path (a
        ``SYN100`` diagnostic) instead of :meth:`_parse_compute` raising a
        hard ``ParserError`` partway through -- which, raised from inside
        an ``IF``/``ELSE``/``PERFORM`` body, could unwind the entire
        enclosing construct (the exact defect class
        docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md fixed for the
        unsupported-statement path; this COMPUTE-specific pre-check keeps
        that same safety for the two sub-forms this stage does not
        implement).

        This is pure lookahead: the cursor must be on the ``COMPUTE``
        token itself, and nothing is consumed regardless of the result.

        Args:
            state: Active parser state, positioned on ``COMPUTE``.

        Returns:
            ``False`` if ``ROUNDED`` or ``FUNCTION`` appears anywhere
            before the statement ends; ``True`` otherwise.
        """
        stream = state.stream
        offset = 1
        while True:
            tok = stream.peek(offset)
            if tok.type is TokenType.EOF:
                return True
            if _at_operand_boundary(tok):
                return True
            if tok.lexeme.upper() in ("ROUNDED", "FUNCTION"):
                return False
            offset += 1

    def _is_valid_after_compute_operand(self, token: Token) -> bool:
        """
        ``True`` if *token* may legally follow a COMPUTE expression
        operand -- used as the ``is_valid_after`` predicate for
        :meth:`_try_read_subscripted_reference` when reading an operand
        inside a COMPUTE expression (task #stage35).

        Beyond the operand-list boundary shape :func:`_at_operand_boundary`
        already recognises, an expression operand may also be followed by
        an arithmetic operator (``B(I) * C``) or a closing parenthesis
        that ends an enclosing group (``(A(I) + B)``).
        """
        return (
            token.type is TokenType.RPAREN
            or _is_arithmetic_operator_token(token)
            or _at_operand_boundary(token)
        )

    def _parse_compute_factor(self, state: ParserState) -> ArithmeticExpression:
        """
        Parse one COMPUTE expression factor: a parenthesized
        sub-expression, a subscripted reference, or a bare literal/
        identifier (task #stage35's expression grammar, innermost level).
        """
        stream = state.stream
        tok = stream.current()

        if tok.type is TokenType.LPAREN:
            stream.advance()  # consume (
            expression = self._parse_compute_expression(state)
            close_tok = stream.current()
            if close_tok.type is not TokenType.RPAREN:
                raise ParserError(
                    "expected ')' in COMPUTE expression",
                    line=close_tok.position.line,
                    column=close_tok.position.column,
                    offset=close_tok.position.offset,
                )
            stream.advance()  # consume )
            return expression

        subscripted = self._try_read_subscripted_reference(
            state, self._is_valid_after_compute_operand
        )
        if subscripted is not None:
            name, subscript = subscripted
            return OperandExpression(value=name, subscript=subscript)

        if tok.type in (TokenType.NUMBER, TokenType.IDENTIFIER):
            stream.advance()
            return OperandExpression(value=tok.lexeme)

        raise ParserError(
            f"expected operand in COMPUTE expression, got {tok.lexeme!r}",
            line=tok.position.line,
            column=tok.position.column,
            offset=tok.position.offset,
        )

    def _parse_compute_term(self, state: ParserState) -> ArithmeticExpression:
        """Parse a COMPUTE expression term: factors joined by ``*``/``/``,
        which bind tighter than ``+``/``-`` (task #stage35)."""
        stream = state.stream
        left = self._parse_compute_factor(state)
        while True:
            tok = stream.current()
            if not (_is_arithmetic_operator_token(tok) and tok.lexeme in ("*", "/")):
                break
            stream.advance()
            right = self._parse_compute_factor(state)
            left = BinaryExpression(operator=tok.lexeme, left=left, right=right)
        return left

    def _parse_compute_expression(self, state: ParserState) -> ArithmeticExpression:
        """Parse a full COMPUTE expression: terms joined by ``+``/``-``
        (task #stage35, outermost precedence level)."""
        stream = state.stream
        left = self._parse_compute_term(state)
        while True:
            tok = stream.current()
            if not (_is_arithmetic_operator_token(tok) and tok.lexeme in ("+", "-")):
                break
            stream.advance()
            right = self._parse_compute_term(state)
            left = BinaryExpression(operator=tok.lexeme, left=left, right=right)
        return left

    def _parse_compute(self, state: ParserState) -> ComputeStatementNode:
        """
        Parse ``COMPUTE target = expression`` (task #stage35).

        The cursor must be on ``COMPUTE``, and
        :meth:`_compute_has_supported_syntax` must already have confirmed
        this statement uses only the supported grammar -- this method
        does not itself guard against ``ROUNDED``/``FUNCTION``, since
        every caller checks that first.
        """
        stream = state.stream
        start: Position = stream.current().position
        stream.advance()  # consume COMPUTE

        def _is_valid_target_boundary(tok: Token) -> bool:
            return tok.type is TokenType.OPERATOR_EQ

        subscripted_target = self._try_read_subscripted_reference(
            state, _is_valid_target_boundary
        )
        if subscripted_target is not None:
            target, target_subscript = subscripted_target
        else:
            target_tok = stream.current()
            if target_tok.type is not TokenType.IDENTIFIER:
                raise ParserError(
                    "expected target identifier after COMPUTE",
                    line=target_tok.position.line,
                    column=target_tok.position.column,
                    offset=target_tok.position.offset,
                )
            target = target_tok.lexeme
            target_subscript = ()
            stream.advance()

        eq_tok = stream.current()
        if eq_tok.type is not TokenType.OPERATOR_EQ:
            raise ParserError(
                f"expected '=' in COMPUTE statement, got {eq_tok.lexeme!r}",
                line=eq_tok.position.line,
                column=eq_tok.position.column,
                offset=eq_tok.position.offset,
            )
        stream.advance()  # consume =

        expression = self._parse_compute_expression(state)

        end: Position = stream.current().position
        self._consume_optional_period(state)

        return ComputeStatementNode(
            start_position=start,
            end_position=end,
            target=target,
            expression=expression,
            target_subscript=target_subscript,
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
                if tok.type is TokenType.COMMA:
                    # A COBOL argument-list separator, never an argument
                    # itself (task #stage36's PERFORM/paragraph-outlining
                    # investigation: this was a pre-existing, independent
                    # bug -- every comma between two real USING operands
                    # was appended to `arguments` as if it were its own
                    # operand, so `CALL 'X' USING A, B` produced a bogus
                    # 3rd/5th/... argument whose lexeme is the literal text
                    # ",", silently latent because no corpus source's
                    # multi-argument CALL previously reached the Java
                    # backend at all -- every one lived in a paragraph that
                    # was always a PERFORM-target BE009 stub until that
                    # stage taught the backend to emit a paragraph's real
                    # body. Skipping the separator here is the same fix
                    # `_read_operand`'s siblings never needed, since COBOL's
                    # other operand lists (ADD/SUBTRACT/MULTIPLY/DIVIDE/
                    # MOVE) are never comma-separated.
                    stream.advance()
                    continue
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

    def _parse_simple_condition(self, state: ParserState) -> tuple[
        str,
        str,
        str,
        tuple[Subscript, ...],
        tuple[Subscript, ...],
        ArithmeticExpression | None,
        ArithmeticExpression | None,
    ]:
        """
        Parse one ``<operand> [NOT] <comparison-operator> <operand>`` triple —
        the shape both a plain ``IF`` condition and each ``AND``/``OR``-
        joined term of a compound one share. Does not consume a *leading*
        ``AND``/``OR``/``NOT`` or ``(``/``)`` — a compound or parenthesised
        condition is assembled by the caller from repeated calls to this
        method (see :meth:`_parse_if_statement`).

        Either operand may also be a parenthesized arithmetic expression
        (task #stage38, e.g. ``IF (CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY)
        > WAREHOUSE-CAPACITY``) — recognised by a leading ``(`` that is
        *not* the narrow subscripted-reference shape
        :meth:`_try_read_subscripted_reference` already claims (that method
        requires an identifier immediately before the ``(``, so a bare
        leading ``(`` always falls through to here untouched). Parsed via
        :meth:`_parse_compute_expression` — the exact Stage 35 ``COMPUTE``
        expression grammar, reused verbatim, never duplicated — which
        itself consumes the matching closing ``)`` (see
        :meth:`_parse_compute_factor`'s own parenthesized-factor branch),
        leaving the cursor positioned exactly where a single-token operand
        read would have left it. When an expression is parsed this way,
        the returned flat ``left``/``right`` string for that side is
        ``""`` — the expression tree is the operand's only representation,
        mirroring :class:`~app.parser.ast.statements.ComputeStatementNode`,
        which likewise has no parallel flattened-string field alongside its
        own ``expression``.

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

        Either operand may also be a single-dimension subscripted table
        reference (``IF WS-ITEM(WS-I) > 100``, task #stage32) — see
        :meth:`_try_read_subscripted_reference`. Before this stage, the
        left operand's own single-token read never looked past that
        token, so a following ``(`` immediately failed the "expected
        comparison operator" check below, dropping the *entire*
        enclosing ``IF``/``END-IF`` from the AST (recovery had no
        interior period to resynchronise on). The right operand is
        accepted unconditionally when the four-token shape matches —
        nothing has ever looked ahead past it either, matching the
        pre-existing single-token read it replaces.
        """
        stream = state.stream

        left_expression: ArithmeticExpression | None = None
        subscripted_left = self._try_read_subscripted_reference(
            state, _is_comparison_operator_token
        )
        if subscripted_left is not None:
            left, left_subscript = subscripted_left
        elif stream.current().type is TokenType.LPAREN:
            # Parenthesized arithmetic-expression operand (task #stage38).
            # _try_read_subscripted_reference above already ruled out the
            # narrow "IDENTIFIER(subscript)" shape (it requires an
            # identifier immediately before the '(', which a bare leading
            # '(' never is), so reaching here means a genuine grouped
            # expression, not a subscript.
            left_expression = self._parse_compute_expression(state)
            left = ""
            left_subscript = ()
        else:
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
            left_subscript = ()

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

        right_expression: ArithmeticExpression | None = None
        subscripted_right = self._try_read_subscripted_reference(
            state, lambda _tok: True
        )
        if subscripted_right is not None:
            right, right_subscript = subscripted_right
        elif stream.current().type is TokenType.LPAREN:
            # See the matching left-operand branch above (task #stage38).
            right_expression = self._parse_compute_expression(state)
            right = ""
            right_subscript = ()
        else:
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
            right_subscript = ()

        return (
            left,
            operator,
            right,
            left_subscript,
            right_subscript,
            left_expression,
            right_expression,
        )

    def _parse_condition_term(self, state: ParserState) -> tuple[
        str,
        str,
        str,
        tuple[Subscript, ...],
        tuple[Subscript, ...],
        ArithmeticExpression | None,
        ArithmeticExpression | None,
    ]:
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
            A ``(left, operator, right, left_subscript, right_subscript,
            left_expression, right_expression)`` 7-tuple (task #stage38
            added the last two). For a condition-name term, ``operator``
            is :data:`_CONDITION_NAME_TRUE_OPERATOR` or
            :data:`_CONDITION_NAME_FALSE_OPERATOR`, ``left``/``right``
            both hold the condition-name itself (see the module-level
            comment above those constants for why), both subscript
            tuples are empty — a condition-name is never subscripted —
            and both expression fields are ``None`` — a condition-name is
            never a parenthesized expression either.
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
                return name, operator, name, (), (), None, None

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
        (
            left,
            operator,
            right,
            left_subscript,
            right_subscript,
            left_expression,
            right_expression,
        ) = self._parse_condition_term(state)

        # Compound condition: zero or more further AND/OR-joined terms.
        # AND binds tighter than OR (COBOL's own precedence rule); see
        # ConditionTerm's docstring. Parenthesised *sub-conditions*
        # (grouping, e.g. "(A = B) OR (C = D)") are still deliberately
        # not handled here — a leading '(' at a *term* boundary (where
        # AND/OR/a whole new condition would start) is never reached by
        # this loop at all, since the loop only fires on a literal AND/OR
        # lexeme. Two narrower exceptions to a leading '(' *inside* one
        # term's own operand position are recognised: a single-dimension
        # subscripted table reference (task #stage32) — see
        # _try_read_subscripted_reference — and, task #stage38, a
        # parenthesized arithmetic expression — see
        # _parse_simple_condition. Neither is "the start of a grouped
        # sub-condition"; both are one operand, structurally.
        extra_conditions: list[ConditionTerm] = []
        while stream.current().lexeme.upper() in ("AND", "OR"):
            connector = stream.current().lexeme.upper()
            stream.advance()  # consume AND/OR
            (
                term_left,
                term_operator,
                term_right,
                term_left_sub,
                term_right_sub,
                term_left_expr,
                term_right_expr,
            ) = self._parse_condition_term(state)
            extra_conditions.append(
                ConditionTerm(
                    connector=connector,
                    left=term_left,
                    operator=term_operator,
                    right=term_right,
                    left_subscript=term_left_sub,
                    right_subscript=term_right_sub,
                    left_expression=term_left_expr,
                    right_expression=term_right_expr,
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
            upper = tok.lexeme.upper()
            if upper == "COMPUTE" and not self._compute_has_supported_syntax(state):
                self._skip_unsupported_statement_auto(state)
            elif upper in _STATEMENT_LEXEMES:
                then_statements.append(self._parse_statement(state))
            elif upper in _UNSUPPORTED_STATEMENT_LEXEMES:
                self._skip_unsupported_statement_auto(state)
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
                upper = tok.lexeme.upper()
                if upper == "COMPUTE" and not self._compute_has_supported_syntax(state):
                    self._skip_unsupported_statement_auto(state)
                elif upper in _STATEMENT_LEXEMES:
                    else_statements.append(self._parse_statement(state))
                elif upper in _UNSUPPORTED_STATEMENT_LEXEMES:
                    self._skip_unsupported_statement_auto(state)
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
            condition_left_subscript=left_subscript,
            condition_right_subscript=right_subscript,
            condition_left_expression=left_expression,
            condition_right_expression=right_expression,
        )

    def _parse_perform_body(self, state: ParserState) -> list[StatementNode]:
        """
        Parse the statement list of a structured ``PERFORM``
        (``PERFORM UNTIL`` or, task #stage34, ``PERFORM VARYING``) block,
        stopping at ``END-PERFORM``.

        An unsupported verb (READ, COMPUTE, EVALUATE, ...) here used to
        raise a hard ``ParserError``, which the caller's statement-level
        recovery resolves by synchronising to the next PERIOD -- and a
        structured PERFORM/END-PERFORM has no interior periods of its own
        guaranteed, so that could swallow the rest of the paragraph,
        exactly the defect class
        docs/MMIM_PARSER_VALIDATION_FIX.md §7 fixed for IF/ELSE blocks
        (task #stage28; the identical gap was found but left unfixed
        there, docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md §8). This mirrors that
        fix exactly: the same graceful
        :meth:`_skip_unsupported_statement_auto` path
        ``_parse_if_statement``'s then/else loops now also use (task
        #stage34) -- including ``EXIT PERFORM`` (found directly in the
        real corpus, nested inside an ``IF`` inside a ``PERFORM VARYING``
        body: ``complex_acctbatch.cbl``'s ``4100-FIND-ACCOUNT``/
        ``4200-FIND-CUSTOMER``), which needed that method's two-word fix
        precisely because it is unavoidable for this loop body to parse
        at all -- see its own docstring.

        Args:
            state: The active parser state, positioned just after the
                ``UNTIL <condition>`` (or, task #stage34, the
                ``VARYING ... UNTIL <condition>``) header.

        Returns:
            The body's statements, in source order. Does **not** consume
            ``END-PERFORM`` itself -- the caller does, so it can report
            "missing END-PERFORM" at the right position for either form.
        """
        stream = state.stream
        statements: list[StatementNode] = []
        while not stream.eof():
            tok = stream.current()
            if tok.lexeme.upper() == "END-PERFORM":
                break
            upper = tok.lexeme.upper()
            if upper == "COMPUTE" and not self._compute_has_supported_syntax(state):
                self._skip_unsupported_statement_auto(state)
            elif upper in _STATEMENT_LEXEMES:
                statements.append(self._parse_statement(state))
            elif upper in _UNSUPPORTED_STATEMENT_LEXEMES:
                self._skip_unsupported_statement_auto(state)
            else:
                raise ParserError(
                    "expected statement in PERFORM block",
                    line=tok.position.line,
                    column=tok.position.column,
                    offset=tok.position.offset,
                )
        return statements

    def _consume_end_perform(self, state: ParserState) -> None:
        """Consume ``END-PERFORM``, or raise ``ParserError`` if missing."""
        stream = state.stream
        if stream.current().lexeme.upper() == "END-PERFORM":
            stream.advance()
        else:
            tok = stream.current()
            raise ParserError(
                "missing END-PERFORM",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )

    def _read_perform_from_by_operand(self, state: ParserState) -> str:
        """
        Read one ``PERFORM VARYING`` ``FROM``/``BY`` operand token (task
        #stage34), joining a leading sign directly against an
        immediately-following ``NUMBER`` into one literal (``BY -1``).

        Mirrors the established signed-numeric-literal joining rule in
        :mod:`app.parser.syntax.data_parser` (its own ``VALUE`` clause
        does the identical join for the identical reason: the lexer
        always emits ``+``/``-`` as their own ``UNKNOWN`` token, since
        they are also the arithmetic operators). A sign not directly
        adjacent to a number (``BY - 1``) is left unjoined -- the same
        token-by-token behavior as before, not a new form accepted.

        Returns:
            The operand text: a plain identifier, an unsigned literal, or
            a joined signed literal (e.g. ``"-1"``).
        """
        stream = state.stream
        tok = stream.current()
        if tok.type is TokenType.UNKNOWN and tok.lexeme in ("+", "-"):
            nxt = stream.peek(1)
            if (
                nxt.type is TokenType.NUMBER
                and nxt.position.line == tok.position.line
                and nxt.position.offset == tok.position.offset + len(tok.lexeme)
            ):
                stream.advance()  # the sign
                stream.advance()  # the digits
                return tok.lexeme + nxt.lexeme
        stream.advance()
        return tok.lexeme

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

            statements = self._parse_perform_body(state)
            self._consume_end_perform(state)

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
        elif tok.lexeme.upper() == "VARYING":
            return self._parse_perform_varying_statement(state, start)
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

            tok = stream.current()
            if tok.lexeme.upper() == "UNTIL":
                # Out-of-line PERFORM target UNTIL condition (task
                # #stage37): no THRU, no body, no END-PERFORM -- COBOL
                # repeatedly transfers control to `target` and re-tests
                # the condition after each execution. Recognised here,
                # before the THRU/THROUGH check below, so a THRU'd range
                # immediately followed by UNTIL (not present anywhere in
                # the real corpus) is deliberately left to fall through
                # unchanged to the ordinary THRU branch below, rather
                # than being guessed at.
                #
                # Before this stage, this branch did not exist: the
                # bare-target parse below consumed only `target`,
                # leaving `UNTIL <condition>` on the stream, which the
                # next statement-level parse attempt rejected with
                # SYN001 -- and since these paragraphs have no period
                # between statements, panic-mode recovery resynchronised
                # to the next PERIOD, silently discarding every
                # remaining statement in the paragraph (including its
                # own closing PERFORM/GOBACK). See the corpus evidence
                # in tests/parser/test_stage37_perform_target_until.py.
                stream.advance()  # consume UNTIL
                (
                    cond_left,
                    cond_operator,
                    cond_right,
                    _,
                    _,
                    _cond_left_expr,
                    _cond_right_expr,
                ) = self._parse_condition_term(state)
                # A parenthesized arithmetic-expression condition (task
                # #stage38) is deliberately not represented on
                # PerformTargetUntilStatementNode -- not evidenced
                # anywhere in the corpus for this out-of-line PERFORM
                # form, and out of both this stage's and Stage 37's own
                # scope; discarded here for the same reason the PERFORM
                # VARYING UNTIL call site above discards it.

                # Same stray-trailing-period fix _parse_if_statement and
                # the inline PERFORM UNTIL branch above already apply
                # (#108-05): without it, a lone PERIOD after this
                # statement -- when nested inside an IF/PERFORM body
                # whose own statement loop has no generic PERIOD-skip --
                # would fall into that loop's "expected statement"
                # abandonment path.
                self._consume_optional_period(state)

                from app.parser.ast.statements import (
                    PerformTargetUntilStatementNode,
                )

                return PerformTargetUntilStatementNode(
                    start_position=start,
                    end_position=stream.current().position,
                    target=target,
                    condition_left=cond_left,
                    condition_operator=cond_operator,
                    condition_right=cond_right,
                )

            thru_target = ""
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

    def _parse_perform_varying_statement(
        self, state: ParserState, start: Position
    ) -> StatementNode:
        """
        Parse ``PERFORM VARYING identifier FROM ... BY ... UNTIL ...
        <body> END-PERFORM`` (task #stage34).

        Grammar consumed exactly, token by token::

            PERFORM VARYING identifier-1
                FROM {identifier-2 | literal-1}
                BY {identifier-3 | literal-2}
                UNTIL condition-1
                <body>
            END-PERFORM

        Before this stage, the token right after ``PERFORM`` being
        ``VARYING`` (not ``UNTIL``) fell into the plain inline-PERFORM
        branch below, which -- finding an ``IDENTIFIER``-shaped token
        (``VARYING`` is not a reserved lexer word) -- misread the whole
        construct as ``PERFORM VARYING`` (a paragraph literally named
        "VARYING"), discarding everything after it including the loop
        body. This method replaces that misparse with the real grammar.

        Neither ``VARYING``, ``FROM``, ``BY``, nor ``UNTIL`` is a reserved
        lexer word (each arrives as a plain ``IDENTIFIER`` token, exactly
        like this same method's caller already treats ``THRU``/
        ``THROUGH``), so each is recognised here by lexeme, not token
        type -- consistent with every other multi-keyword clause this
        parser already handles that way.

        The ``UNTIL`` condition is parsed via :meth:`_parse_condition_term`
        -- the exact same machinery ``IF`` uses -- so a subscripted
        condition operand (task #stage32) is supported here too, for
        free, with no second condition parser. The loop body is parsed
        via :meth:`_parse_perform_body`, the same statement-list mechanism
        ``PERFORM UNTIL`` already uses, so nested ``IF``, ``EXIT PERFORM``,
        ``COMPUTE``, and subscripted table references are all handled
        exactly as they already are elsewhere.

        Args:
            state: Active parser state, cursor on ``VARYING`` (``PERFORM``
                already consumed by the caller).
            start: Source position of the ``PERFORM`` token, for the
                returned node's span.

        Returns:
            An immutable
            :class:`~app.parser.ast.statements.PerformVaryingStatementNode`.

        Raises:
            ParserError: If the varying variable, ``FROM``, ``BY``,
                ``UNTIL``, or ``END-PERFORM`` is missing/malformed.
        """
        stream = state.stream
        stream.advance()  # consume VARYING

        var_tok = stream.current()
        if var_tok.type is not TokenType.IDENTIFIER:
            raise ParserError(
                "expected varying variable name after PERFORM VARYING",
                line=var_tok.position.line,
                column=var_tok.position.column,
                offset=var_tok.position.offset,
            )
        varying_variable = var_tok.lexeme
        stream.advance()

        if stream.current().lexeme.upper() != "FROM":
            tok = stream.current()
            raise ParserError(
                "expected FROM after PERFORM VARYING variable",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )
        stream.advance()  # consume FROM
        from_value = self._read_perform_from_by_operand(state)

        if stream.current().lexeme.upper() != "BY":
            tok = stream.current()
            raise ParserError(
                "expected BY after PERFORM VARYING ... FROM ...",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )
        stream.advance()  # consume BY
        by_value = self._read_perform_from_by_operand(state)

        if stream.current().lexeme.upper() != "UNTIL":
            tok = stream.current()
            raise ParserError(
                "expected UNTIL after PERFORM VARYING ... BY ...",
                line=tok.position.line,
                column=tok.position.column,
                offset=tok.position.offset,
            )
        stream.advance()  # consume UNTIL

        (
            cond_left,
            cond_operator,
            cond_right,
            cond_left_sub,
            cond_right_sub,
            _cond_left_expr,
            _cond_right_expr,
        ) = self._parse_condition_term(state)
        # A parenthesized arithmetic-expression UNTIL condition (task
        # #stage38) is deliberately not represented on
        # PerformVaryingStatementNode/IRPerformVarying -- not evidenced
        # anywhere in the corpus for this form, and out of this stage's
        # scope. _parse_condition_term now returns it uniformly (the same
        # shared method IF and PERFORM VARYING's UNTIL both call), but it
        # is discarded here rather than silently corrupting cond_left/
        # cond_right with an empty string that a downstream consumer
        # would misread as a real (if blank) operand.

        statements = self._parse_perform_body(state)
        self._consume_end_perform(state)
        self._consume_optional_period(state)

        from app.parser.ast.statements import PerformVaryingStatementNode

        return PerformVaryingStatementNode(
            start_position=start,
            end_position=stream.current().position,
            varying_variable=varying_variable,
            from_value=from_value,
            by_value=by_value,
            condition_left=cond_left,
            condition_operator=cond_operator,
            condition_right=cond_right,
            statements=tuple(statements),
            condition_left_subscript=cond_left_sub,
            condition_right_subscript=cond_right_sub,
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

    def _parse_read_statement(self, state: ParserState) -> ReadStatementNode:
        """
        Parse ``READ file-name [INTO identifier] [AT END stmts]
        [NOT AT END stmts] [END-READ]`` (task #stage40).

        Replaces the former ``_skip_read_statement`` opaque skip with
        real, structural parsing, reusing the exact same ``AT``-token
        boundary-tracking insight that method's own docstring already
        established (see ``docs/MMIM_READ_AT_END_PARSING_FIX.md``):
        without ``END-READ``, real COBOL closes the ``AT END``/``NOT AT
        END`` clause at the sentence's own terminating period, so at most
        one sentence's worth of statements is collected in that form.
        :meth:`_parse_read_clause_body` detects this the same way that
        method did -- by tracking whether the current clause is still
        "before the first ``AT``" (a statement-boundary token ends the
        clause early there, exactly as it always did) -- plus one new
        check this method needs that the discard-only skip never did:
        whether the *last statement actually parsed* already consumed
        the sentence's terminating period itself (every individual
        statement parser, e.g. ``_parse_move``, already calls
        :meth:`_consume_optional_period`), which is what tells a
        real-statement collector "stop -- the sentence, and therefore
        this whole READ, is over" in the no-``END-READ`` form.

        Neither ``INTO`` nor ``AT``/``END``/``NOT``/``END-READ`` is a
        reserved lexer word (each arrives as a plain ``IDENTIFIER``
        token, exactly like every other multi-word clause marker this
        parser already recognises by lexeme -- ``PERFORM``'s ``THRU``,
        ``GO``'s ``TO``).

        This backend has no file-reading runtime (task #stage40's own
        explicit scope decision -- nothing in the corpus demands one).
        Both clauses' statement lists are still captured in full here,
        for AST fidelity; only ``at_end_statements`` is ever lowered to
        IR (:meth:`~app.ir.builder.IRBuilder.build_read_statement`) --
        see that method and :class:`~app.parser.ast.statements
        .ReadStatementNode`'s own docstring for why.

        Args:
            state: Active parser state; cursor on ``READ``.

        Returns:
            An immutable :class:`~app.parser.ast.statements.ReadStatementNode`.

        Raises:
            ParserError: If the file name, or an identifier after
                ``INTO``, is missing.
        """
        stream = state.stream
        start = stream.current().position
        stream.advance()  # consume READ

        target_tok = stream.current()
        if target_tok.type is not TokenType.IDENTIFIER:
            raise ParserError(
                "expected file name after READ",
                line=target_tok.position.line,
                column=target_tok.position.column,
                offset=target_tok.position.offset,
            )
        target = target_tok.lexeme
        stream.advance()

        into_target = ""
        if matches_grammar_word(stream.current(), {"INTO"}):
            stream.advance()  # consume INTO
            into_tok = stream.current()
            if into_tok.type is not TokenType.IDENTIFIER:
                raise ParserError(
                    "expected identifier after INTO in READ",
                    line=into_tok.position.line,
                    column=into_tok.position.column,
                    offset=into_tok.position.offset,
                )
            into_target = into_tok.lexeme
            stream.advance()

        at_end_statements: list[StatementNode] = []
        not_at_end_statements: list[StatementNode] = []
        sentence_ended = False

        if matches_grammar_word(stream.current(), {"AT"}):
            stream.advance()  # consume AT
            tok = stream.current()
            if not matches_grammar_word(tok, {"END"}):
                raise ParserError(
                    "expected END after AT in READ",
                    line=tok.position.line,
                    column=tok.position.column,
                    offset=tok.position.offset,
                )
            stream.advance()  # consume END
            at_end_statements, sentence_ended = self._parse_read_clause_body(state)

        if not sentence_ended and matches_grammar_word(stream.current(), {"NOT"}):
            stream.advance()  # consume NOT
            tok = stream.current()
            if not matches_grammar_word(tok, {"AT"}):
                raise ParserError(
                    "expected AT after NOT in READ",
                    line=tok.position.line,
                    column=tok.position.column,
                    offset=tok.position.offset,
                )
            stream.advance()  # consume AT
            tok = stream.current()
            if not matches_grammar_word(tok, {"END"}):
                raise ParserError(
                    "expected END after NOT AT in READ",
                    line=tok.position.line,
                    column=tok.position.column,
                    offset=tok.position.offset,
                )
            stream.advance()  # consume END
            not_at_end_statements, sentence_ended = self._parse_read_clause_body(state)

        if not sentence_ended and matches_grammar_word(stream.current(), {"END-READ"}):
            stream.advance()

        end = stream.current().position
        self._consume_optional_period(state)

        return ReadStatementNode(
            start_position=start,
            end_position=end,
            target=target,
            into_target=into_target,
            at_end_statements=tuple(at_end_statements),
            not_at_end_statements=tuple(not_at_end_statements),
        )

    def _parse_read_clause_body(
        self, state: ParserState
    ) -> tuple[list[StatementNode], bool]:
        """
        Parse the statement list of one ``READ`` ``AT END``/``NOT AT
        END`` clause (task #stage40), stopping at ``END-READ``, the
        start of a ``NOT AT END`` clause, or -- for the no-``END-READ``
        form -- the sentence's own terminating period.

        Mirrors :meth:`_parse_perform_body`'s statement-collection loop
        exactly (same ``_STATEMENT_LEXEMES``/``_UNSUPPORTED_STATEMENT_LEXEMES``/
        ``COMPUTE``-pre-check dispatch, so nested ``IF``, ``COMPUTE``, and
        any other already-supported statement are handled identically
        inside a READ clause), with one addition this clause shape alone
        needs: after each statement is parsed, checking whether *that
        statement itself* just consumed the sentence's terminating period
        (every statement parser already calls
        :meth:`_consume_optional_period`). If it did, the clause -- and
        the whole enclosing ``READ`` sentence -- is over: real COBOL's
        own rule for the ``END-READ``-less form (at most one sentence's
        worth of statements). The caller uses the returned ``bool`` to
        skip checking for a further ``NOT AT END`` clause or ``END-READ``
        in that case, exactly as `_skip_read_statement`'s own bare-period
        handling always did.

        Args:
            state: Active parser state, positioned just after the
                clause's ``END``/``END`` marker.

        Returns:
            ``(statements, sentence_ended)`` -- ``sentence_ended`` is
            ``True`` only when a lone period (with no ``END-READ``) was
            what ended this clause.
        """
        stream = state.stream
        statements: list[StatementNode] = []
        while not stream.eof():
            tok = stream.current()
            upper = tok.lexeme.upper()
            if upper in ("END-READ", "NOT"):
                break
            if tok.type is TokenType.PERIOD:
                # A lone period with nothing parsed yet -- an empty
                # clause immediately closed by the sentence's own
                # terminator (COBOL-legal, not present in the corpus).
                stream.advance()
                return statements, True
            if (
                tok.type is TokenType.KEYWORD
                and upper in _DIVISION_KEYWORDS
                and stream.peek().type is TokenType.KEYWORD
                and stream.peek().lexeme.upper() == "DIVISION"
            ):
                break
            if upper == "COMPUTE" and not self._compute_has_supported_syntax(state):
                self._skip_unsupported_statement_auto(state)
            elif upper in _STATEMENT_LEXEMES:
                statements.append(self._parse_statement(state))
                if stream.peek(-1).type is TokenType.PERIOD:
                    return statements, True
                continue
            elif upper in _UNSUPPORTED_STATEMENT_LEXEMES:
                self._skip_unsupported_statement_auto(state)
            else:
                break
            if stream.peek(-1).type is TokenType.PERIOD:
                return statements, True
        return statements, False
