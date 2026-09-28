"""
Stage 38 — IF condition with a parenthesized arithmetic-expression operand.

Purpose:
    Before this stage, ``_parse_simple_condition``'s operand read was a
    single token: a leading ``(`` (once the narrow single-dimension
    subscripted-reference shape, task #stage32, was ruled out) failed the
    "expected operand for IF condition" check and raised ``SYN005``. A
    structured ``IF``/``END-IF`` has no interior period to resynchronise
    on, so panic-mode recovery discarded the entire enclosing paragraph --
    confirmed directly against the real corpus: ``t_inventory_reorder``'s
    ``3000-CALCULATE-ORDER-QUANTITY`` and ``4000-EVALUATE-EXPEDITE-NEED``
    both measured 0 statements before this stage.

    ``_parse_simple_condition`` now recognises a bare leading ``(`` at
    either operand-read position and parses it via
    :meth:`~app.parser.syntax.procedure_parser.ProcedureDivisionParser
    ._parse_compute_expression` -- the exact Stage 35 ``COMPUTE``
    expression grammar, reused verbatim, never duplicated -- producing a
    structured :class:`~app.parser.ast.statements.ArithmeticExpression`
    tree on :attr:`~app.parser.ast.statements.IfStatementNode
    .condition_left_expression`/``condition_right_expression`` rather
    than a flattened string.

    Explicitly NOT covered here (out of this stage's scope -- neither is
    anywhere in the 45-source training corpus):
    - Parenthesized *boolean* grouping (``(A = B) OR (C = D)``).
    - Exponentiation, intrinsic ``FUNCTION`` operands, ``ON SIZE ERROR``.
    - A parenthesized expression combined with ``THRU``/multidimensional/
      arithmetic subscripts.
    - The unrelated, already-known ``t_inventory_reorder`` COMPUTE
      double/int narrowing ``javac`` failure (a different statement, a
      different mechanism -- deliberately not fixed here).

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.service import AnalysisService
from app.parser.ast.statements import (
    BinaryExpression,
    IfStatementNode,
    OperandExpression,
    PerformVaryingStatementNode,
)

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nDATA DIVISION.\nWORKING-STORAGE SECTION.\n"

_HEADER = (
    "01 CURRENT-STOCK-QTY PIC 9(5) VALUE 120.\n"
    "01 SUGGESTED-ORDER-QTY PIC 9(5) VALUE 0.\n"
    "01 WAREHOUSE-CAPACITY PIC 9(5) VALUE 2000.\n"
    "01 SAFETY-STOCK-LEVEL PIC 9(5) VALUE 150.\n"
)


def _analyze(tmp_path: Path, body: str, header: str = _HEADER):
    source = _ID + header + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body
    path = tmp_path / "t.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _first_statement(result):
    return result.ast.procedure_division.paragraphs[0].statements[0]


# ===========================================================================
# A. Parser
# ===========================================================================


class TestRealCorpusShapes:
    """Both real occurrences (t_inventory_reorder.cbl lines 47 and 56)."""

    def test_parenthesized_addition_on_the_left(self, tmp_path: Path) -> None:
        """inventory_reorder.cbl:47 -- ``IF (CURRENT-STOCK-QTY +
        SUGGESTED-ORDER-QTY) > WAREHOUSE-CAPACITY``."""
        result = _analyze(
            tmp_path,
            "    IF (CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY) > "
            "WAREHOUSE-CAPACITY\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        assert result.syntax_diagnostics == []
        stmt = _first_statement(result)
        assert isinstance(stmt, IfStatementNode)
        assert stmt.condition_left == ""
        assert stmt.condition_left_expression == BinaryExpression(
            operator="+",
            left=OperandExpression(value="CURRENT-STOCK-QTY"),
            right=OperandExpression(value="SUGGESTED-ORDER-QTY"),
        )
        assert stmt.condition_operator == ">"
        assert stmt.condition_right == "WAREHOUSE-CAPACITY"
        assert stmt.condition_right_expression is None
        assert len(stmt.then_statements) == 1

    def test_parenthesized_division_on_the_right(self, tmp_path: Path) -> None:
        """inventory_reorder.cbl:56 -- ``IF CURRENT-STOCK-QTY <
        (SAFETY-STOCK-LEVEL / 2)``."""
        result = _analyze(
            tmp_path,
            "    IF CURRENT-STOCK-QTY < (SAFETY-STOCK-LEVEL / 2)\n"
            "        MOVE 'Y' TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        assert result.syntax_diagnostics == []
        stmt = _first_statement(result)
        assert isinstance(stmt, IfStatementNode)
        assert stmt.condition_left == "CURRENT-STOCK-QTY"
        assert stmt.condition_left_expression is None
        assert stmt.condition_operator == "<"
        assert stmt.condition_right == ""
        assert stmt.condition_right_expression == BinaryExpression(
            operator="/",
            left=OperandExpression(value="SAFETY-STOCK-LEVEL"),
            right=OperandExpression(value="2"),
        )
        assert len(stmt.then_statements) == 1


class TestFollowingStatementsPreserved:
    """The exact defect: statements after the malformed IF used to vanish
    with the entire enclosing paragraph."""

    def test_statements_after_the_if_are_not_swallowed(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    IF (CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY) > "
            "WAREHOUSE-CAPACITY\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n"
            "    DISPLAY 'DONE'.\n"
            "    GOBACK.\n",
        )
        paragraph = result.ast.procedure_division.paragraphs[0]
        assert [type(s).__name__ for s in paragraph.statements] == [
            "IfStatementNode",
            "DisplayStatementNode",
            "GobackStatementNode",
        ]

    def test_paragraph_after_is_still_parsed(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    IF (CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY) > "
            "WAREHOUSE-CAPACITY\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n"
            "    GOBACK.\n"
            "NEXT-PARA.\n"
            "    DISPLAY 'X'.\n",
        )
        paragraphs = result.ast.procedure_division.paragraphs
        assert paragraphs[1].name == "NEXT-PARA"
        assert len(paragraphs[1].statements) == 1


class TestNestedAndCombinedArithmetic:
    """Already-supported Stage 35 combinations (nested parens, mixed
    precedence) inside an IF operand, for free from reusing the same
    expression parser."""

    def test_nested_parenthesized_expression(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    IF (CURRENT-STOCK-QTY + (SUGGESTED-ORDER-QTY * 2)) > "
            "WAREHOUSE-CAPACITY\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        assert result.syntax_diagnostics == []
        stmt = _first_statement(result)
        assert isinstance(stmt, IfStatementNode)
        assert stmt.condition_left_expression == BinaryExpression(
            operator="+",
            left=OperandExpression(value="CURRENT-STOCK-QTY"),
            right=BinaryExpression(
                operator="*",
                left=OperandExpression(value="SUGGESTED-ORDER-QTY"),
                right=OperandExpression(value="2"),
            ),
        )

    def test_mixed_precedence_without_extra_parens(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    IF (CURRENT-STOCK-QTY * 2 + SUGGESTED-ORDER-QTY) > "
            "WAREHOUSE-CAPACITY\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        assert result.syntax_diagnostics == []
        stmt = _first_statement(result)
        assert stmt.condition_left_expression == BinaryExpression(
            operator="+",
            left=BinaryExpression(
                operator="*",
                left=OperandExpression(value="CURRENT-STOCK-QTY"),
                right=OperandExpression(value="2"),
            ),
            right=OperandExpression(value="SUGGESTED-ORDER-QTY"),
        )


class TestRegressionExistingIfBehavior:
    """Every pre-existing IF condition shape must stay byte-for-byte
    unchanged."""

    def test_plain_scalar_if_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    IF CURRENT-STOCK-QTY > 0\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        stmt = _first_statement(result)
        assert isinstance(stmt, IfStatementNode)
        assert stmt.condition_left == "CURRENT-STOCK-QTY"
        assert stmt.condition_left_expression is None
        assert stmt.condition_right == "0"
        assert stmt.condition_right_expression is None

    def test_subscripted_operand_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    IF WS-ITEM(WS-I) > 100\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
            header=_HEADER
            + "01 WS-I PIC 9(2) VALUE 1.\n"
            + "01 WS-TABLE.\n    05 WS-ITEM PIC 9(3) OCCURS 4.\n",
        )
        stmt = _first_statement(result)
        assert stmt.condition_left == "WS-ITEM"
        assert stmt.condition_left_expression is None
        assert stmt.condition_left_subscript

    def test_and_or_compound_condition_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    IF CURRENT-STOCK-QTY > 0 AND WAREHOUSE-CAPACITY > 0\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        stmt = _first_statement(result)
        assert len(stmt.extra_conditions) == 1
        assert stmt.extra_conditions[0].left == "WAREHOUSE-CAPACITY"
        assert stmt.extra_conditions[0].left_expression is None

    def test_perform_varying_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-STOCK-QTY FROM 1 BY 1 "
            "UNTIL CURRENT-STOCK-QTY > 4\n"
            "        DISPLAY CURRENT-STOCK-QTY\n"
            "    END-PERFORM.\n"
            "    GOBACK.\n",
        )
        stmt = _first_statement(result)
        assert isinstance(stmt, PerformVaryingStatementNode)
        assert stmt.condition_left == "CURRENT-STOCK-QTY"


class TestUnsupportedFormsRemainUnsupported:
    """Every form explicitly out of Stage 38's scope stays exactly as
    unsupported as before -- no accidental widening."""

    def test_compound_arithmetic_and_condition_in_and_or_term_still_works(
        self, tmp_path: Path
    ) -> None:
        """Not evidenced in the real corpus, but reachable "for free"
        through the same shared _parse_condition_term/_parse_simple_
        condition machinery every AND/OR term already goes through
        (exactly like Stage 32's subscript support flowed to PERFORM
        VARYING's UNTIL "for free") -- verified directly here rather
        than assumed."""
        result = _analyze(
            tmp_path,
            "    IF CURRENT-STOCK-QTY > 0 AND (SUGGESTED-ORDER-QTY + 1) > 5\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        assert result.syntax_diagnostics == []
        stmt = _first_statement(result)
        assert stmt.extra_conditions[0].left_expression == BinaryExpression(
            operator="+",
            left=OperandExpression(value="SUGGESTED-ORDER-QTY"),
            right=OperandExpression(value="1"),
        )

    def test_exponentiation_inside_parens_still_unsupported(
        self, tmp_path: Path
    ) -> None:
        """The inner grammar is still exactly Stage 35's -- '**' is not an
        arithmetic-operator token, so this still fails to parse, exactly
        as a bare (non-parenthesized) exponentiation already did."""
        result = _analyze(
            tmp_path,
            "    IF (CURRENT-STOCK-QTY ** 2) > 100\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n"
            "    DISPLAY 'AFTER'.\n"
            "    GOBACK.\n",
        )
        # Graceful degrade: the malformed IF is skipped by panic-mode
        # recovery (a real diagnostic is recorded), but -- unlike the
        # pre-Stage-38 defect this stage fixes -- forward progress is not
        # otherwise this test's concern; it only asserts this remains
        # unsupported, not swallowed silently with zero diagnostic.
        assert any(d.code for d in result.syntax_diagnostics)
