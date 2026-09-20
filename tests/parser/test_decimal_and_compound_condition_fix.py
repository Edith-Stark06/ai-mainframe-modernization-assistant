"""
Regression tests: decimal-literal lexer fix + compound AND/OR IF-condition
parsing (docs/MMIM_PARSER_VALIDATION_FIX.md).

Purpose:
    Two related, previously undocumented (beyond the corpus-expansion
    report's narrower DATA-DIVISION-only note) defects:

    1. Any numeric literal with a decimal point used inside the PROCEDURE
       DIVISION (an IF condition, a MOVE, a COMPUTE expression — not only
       a DATA DIVISION VALUE clause) was mis-tokenized: the lexer split
       ``12.50`` into ``NUMBER('12')``, ``PERIOD('.')``, ``NUMBER('50')``
       because it had no decimal-point handling at all.
    2. The IF-condition parser never supported ``AND``/``OR`` — a compound
       condition raised a ParserError, and the parser's own statement-level
       recovery (synchronise to the next PERIOD) then silently swallowed
       everything up to the next real terminator, which for a structured
       IF/END-IF with no interior periods usually meant the rest of the
       paragraph.

    Fixed at the narrowest possible point in each case:
    ``CobolLexer._read_number``/``_at_decimal_point`` (lexer.py) and
    ``ProcedureDivisionParser._parse_if_statement``/``_parse_simple_condition``
    (procedure_parser.py) + the new ``ConditionTerm``/``IfStatementNode.
    extra_conditions`` AST fields (statements.py).

Non-responsibilities:
    - Parenthesised conditions (``A AND (B OR C)``) — deliberately left
      unsupported; tested here only to confirm the failure mode did not
      get *worse* (whole-paragraph loss), not to make it succeed.
    - ``NOT =`` — a separate, pre-existing, out-of-scope parser gap.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.analysis.service import AnalysisService
from app.parser.ast.statements import IfStatementNode
from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.token_types import TokenType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def lex(source: str) -> list:
    tokens = CobolLexer().tokenize(source, filename="probe.cbl")
    return [t for t in tokens if t.type is not TokenType.EOF]


def _analyze(source: str, tmp_path, name: str = "probe.cbl"):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(str(path))


def _paragraph_statement_counts(result) -> dict[str, int]:
    pd = result.ast.procedure_division
    return {p.name: len(p.statements) for p in pd.paragraphs}


# ---------------------------------------------------------------------------
# 1-2. integer literal / decimal literal tokenization
# ---------------------------------------------------------------------------


def test_integer_literal_unaffected():
    toks = lex("12345")
    assert [(t.type, t.lexeme) for t in toks] == [(TokenType.NUMBER, "12345")]


def test_decimal_literal_is_a_single_number_token():
    for src in ("12.50", "0.75", "99.95"):
        toks = lex(src)
        assert len(toks) == 1, f"{src!r} produced {toks!r}"
        assert toks[0].type is TokenType.NUMBER
        assert toks[0].lexeme == src


# ---------------------------------------------------------------------------
# 3. multiple decimal literals in one statement/paragraph
# ---------------------------------------------------------------------------


def test_multiple_decimal_literals_in_one_paragraph():
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. MULTIDEC.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(3)V99 VALUE 0.
       01 WS-B PIC 9(3)V99 VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE 12.50 TO WS-A
           MOVE 0.75 TO WS-B
           DISPLAY WS-A.
"""
    toks = lex(src)
    numbers = [t.lexeme for t in toks if t.type is TokenType.NUMBER]
    assert "12.50" in numbers
    assert "0.75" in numbers


# ---------------------------------------------------------------------------
# 4. decimal literal inside arithmetic (adjacent to operators)
# ---------------------------------------------------------------------------


def test_decimal_literal_adjacent_to_comparison_operator():
    toks = lex("WS-A <= 11000.00")
    lexemes = [(t.type, t.lexeme) for t in toks]
    assert (TokenType.NUMBER, "11000.00") in lexemes
    # no stray fragment of the literal survives as its own token
    assert not any(t.lexeme in ("00", "11000") for t in toks)


def test_decimal_literal_in_compute_style_expression():
    toks = lex("(WS-A - WS-B) * 0.10")
    lexemes = [t.lexeme for t in toks]
    assert "0.10" in lexemes
    assert "10" not in lexemes  # not split into '0', '.', '10'


# ---------------------------------------------------------------------------
# 5. decimal literal followed by the paragraph/statement-terminating period
# ---------------------------------------------------------------------------


def test_decimal_literal_followed_by_statement_period():
    toks = lex("MOVE 12.50 TO WS-A.")
    types_and_lex = [(t.type, t.lexeme) for t in toks]
    assert (TokenType.NUMBER, "12.50") in types_and_lex
    assert types_and_lex[-1] == (TokenType.PERIOD, ".")


def test_integer_literal_followed_by_period_is_still_a_terminator():
    """The narrowest-possible-rule guarantee: a period NOT immediately
    followed by a digit is never consumed into the literal."""
    toks = lex("MOVE 12 TO WS-A.")
    assert [(t.type, t.lexeme) for t in toks] == [
        (TokenType.KEYWORD, "MOVE"),
        (TokenType.NUMBER, "12"),
        (TokenType.IDENTIFIER, "TO"),
        (TokenType.IDENTIFIER, "WS-A"),
        (TokenType.PERIOD, "."),
    ]


def test_decimal_literal_immediately_followed_by_terminator_period():
    """'12.50.' -- decimal point consumed, real terminator left alone."""
    toks = lex("12.50.")
    assert [(t.type, t.lexeme) for t in toks] == [
        (TokenType.NUMBER, "12.50"),
        (TokenType.PERIOD, "."),
    ]


def test_paragraph_name_numeric_prefix_still_works():
    """Regression guard: the existing '0000-MAIN' paragraph-name rule
    (digits + hyphen + letter) must be completely unaffected by decimal
    point handling (different character: '-' vs '.')."""
    toks = lex("0000-MAIN.")
    assert [(t.type, t.lexeme) for t in toks] == [
        (TokenType.IDENTIFIER, "0000-MAIN"),
        (TokenType.PERIOD, "."),
    ]


# ---------------------------------------------------------------------------
# 6-8. compound IF conditions: AND / OR / AND+OR
# ---------------------------------------------------------------------------

_AND_SOURCE = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. ANDTEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC X(10) VALUE 'CITIZEN'.
       01 WS-C PIC 9(3) VALUE 5.
       01 WS-B PIC X(1) VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A = 'CITIZEN' AND WS-C = 5
               MOVE 'Y' TO WS-B
           END-IF
           DISPLAY WS-B
           DISPLAY WS-A.
"""

_OR_SOURCE = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. ORTEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(3) VALUE 1.
       01 WS-C PIC 9(3) VALUE 5.
       01 WS-B PIC X(1) VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A = 1 OR WS-C = 2
               MOVE 'Y' TO WS-B
           END-IF
           DISPLAY WS-B.
"""

_AND_OR_SOURCE = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. ANDORTST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(3) VALUE 1.
       01 WS-D PIC 9(3) VALUE 2.
       01 WS-C PIC 9(3) VALUE 3.
       01 WS-OUT PIC X(1) VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A = 1 AND WS-D = 2 OR WS-C = 9
               MOVE 'Y' TO WS-OUT
           END-IF
           DISPLAY WS-OUT.
"""

_PAREN_SOURCE = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. PARENTST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(3) VALUE 1.
       01 WS-D PIC 9(3) VALUE 2.
       01 WS-C PIC 9(3) VALUE 3.
       01 WS-OUT PIC X(1) VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A = 1 AND (WS-D = 2 OR WS-C = 3)
               MOVE 'Y' TO WS-OUT
           END-IF
           DISPLAY WS-OUT.
       NEXT-PARA.
           DISPLAY 'REACHED'.
"""


def test_if_with_and_parses_with_no_diagnostics(tmp_path):
    result = _analyze(_AND_SOURCE, tmp_path)
    assert result.syntax_diagnostics == []
    if_stmt = result.ast.procedure_division.paragraphs[0].statements[0]
    assert isinstance(if_stmt, IfStatementNode)
    assert (
        if_stmt.condition_left,
        if_stmt.condition_operator,
        if_stmt.condition_right,
    ) == (
        "WS-A",
        "=",
        "'CITIZEN'",
    )
    assert len(if_stmt.extra_conditions) == 1
    term = if_stmt.extra_conditions[0]
    assert (term.connector, term.left, term.operator, term.right) == (
        "AND",
        "WS-C",
        "=",
        "5",
    )


def test_if_with_or_parses_with_no_diagnostics(tmp_path):
    result = _analyze(_OR_SOURCE, tmp_path)
    assert result.syntax_diagnostics == []
    if_stmt = result.ast.procedure_division.paragraphs[0].statements[0]
    assert len(if_stmt.extra_conditions) == 1
    assert if_stmt.extra_conditions[0].connector == "OR"


def test_if_with_and_then_or_preserves_precedence_structure(tmp_path):
    """'A AND B OR C' must be represented as [AND B, OR C] in source
    order (== (A AND B) OR C under the documented AND-before-OR
    convention) -- never flattened or silently reordered."""
    result = _analyze(_AND_OR_SOURCE, tmp_path)
    assert result.syntax_diagnostics == []
    if_stmt = result.ast.procedure_division.paragraphs[0].statements[0]
    assert (
        if_stmt.condition_left,
        if_stmt.condition_operator,
        if_stmt.condition_right,
    ) == (
        "WS-A",
        "=",
        "1",
    )
    assert len(if_stmt.extra_conditions) == 2
    first, second = if_stmt.extra_conditions
    assert (first.connector, first.left, first.operator, first.right) == (
        "AND",
        "WS-D",
        "=",
        "2",
    )
    assert (second.connector, second.left, second.operator, second.right) == (
        "OR",
        "WS-C",
        "=",
        "9",
    )


# ---------------------------------------------------------------------------
# 9. parenthesized compound condition -- explicitly tested, NOT assumed
# ---------------------------------------------------------------------------


def test_parenthesized_condition_is_not_silently_supported(tmp_path):
    """Parens are out of scope; this must fail as a clean, single
    diagnostic on the current paragraph, never as a silent misparse and
    never by discarding a *different* paragraph."""
    result = _analyze(_PAREN_SOURCE, tmp_path)
    codes = [d.code for d in result.syntax_diagnostics]
    assert "SYN005" in codes
    counts = _paragraph_statement_counts(result)
    # the paren IF's own paragraph loses its (unsupported) body -- the
    # same class of loss every other unsupported construct in this
    # parser already produces, not a new or worse failure mode
    assert counts["MAIN-PARA"] == 0
    # critically, recovery is paragraph-scoped: the *next* paragraph is
    # completely unaffected
    assert counts["NEXT-PARA"] == 1


# ---------------------------------------------------------------------------
# 10. statements after the IF / critical regression fixture
# ---------------------------------------------------------------------------


def test_statements_after_compound_if_are_preserved(tmp_path):
    """The exact previously-reported failure mode: statements textually
    after a compound-condition IF used to vanish along with the IF's own
    body. Assert they are present now."""
    result = _analyze(_AND_SOURCE, tmp_path)
    para = result.ast.procedure_division.paragraphs[0]
    assert len(para.statements) == 3  # IF, DISPLAY, DISPLAY
    assert para.statements[1].__class__.__name__ == "DisplayStatementNode"
    assert para.statements[2].__class__.__name__ == "DisplayStatementNode"


def test_critical_regression_decimal_and_compound_condition_together(tmp_path):
    """The exact shape the MMIM corpus sources hit: a paragraph with a
    decimal-literal comparison AND a compound AND/OR condition AND
    statements after both. Before this fix, this paragraph parsed to
    zero statements with zero diagnostics -- a silent, undiagnosed loss.
    """
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. CRITICAL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-INCOME PIC 9(8)V99 VALUE 65000.00.
       01 WS-SCORE  PIC 9(3) VALUE 700.
       01 WS-FLAG   PIC X(1) VALUE 'N'.
       01 WS-NOTE   PIC X(10) VALUE SPACES.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-INCOME >= 50000.00 AND WS-SCORE = 700
               MOVE 'Y' TO WS-FLAG
           END-IF
           MOVE 'DONE' TO WS-NOTE
           DISPLAY WS-FLAG
           DISPLAY WS-NOTE.
"""
    result = _analyze(src, tmp_path)
    assert result.syntax_diagnostics == []
    para = result.ast.procedure_division.paragraphs[0]
    # IF, MOVE, DISPLAY, DISPLAY -- nothing lost
    assert len(para.statements) == 4
    if_stmt = para.statements[0]
    assert if_stmt.condition_right == "50000.00"
    assert if_stmt.extra_conditions[0].right == "700"
