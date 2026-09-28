"""
Stage 35 — COMPUTE statement parsing.

Purpose:
    Lock in ``ComputeStatementNode``/``BinaryExpression``/
    ``OperandExpression`` parsing for exactly the grammar evidenced by
    the 45-source training corpus (see the Stage 35 investigation
    report): ``COMPUTE target = expression`` where ``expression`` is
    built from numeric literals, (optionally subscripted) identifiers,
    ``+ - * /``, and parentheses. Every test drives the real pipeline
    (lexer -> parser -> AST), because COMPUTE's statement-list wiring
    (paragraph level, IF then/else, PERFORM body) is exactly as easy to
    get subtly wrong as ADD/SUBTRACT/EVALUATE's own history here shows.

    Explicitly NOT covered here (out of this stage's scope, per the
    Stage 35 investigation report -- neither is anywhere in the
    45-source training corpus):
    - ``COMPUTE ... ROUNDED``.
    - ``COMPUTE`` with an intrinsic ``FUNCTION`` operand.
    - Multi-dimensional or arithmetic subscripts, ``ON SIZE ERROR``,
      exponentiation.

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
    ComputeStatementNode,
    IfStatementNode,
    OperandExpression,
    Subscript,
)

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nDATA DIVISION.\nWORKING-STORAGE SECTION.\n"


def _analyze(tmp_path: Path, body: str, header: str = ""):
    source = _ID + header + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body
    path = tmp_path / "t.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _first_statement(result):
    return result.ast.procedure_division.paragraphs[0].statements[0]


# ===========================================================================
# 1. Real-corpus expression shapes
# ===========================================================================


class TestRealCorpusShapes:
    """Every shape here is one of the 67 real COMPUTE statements catalogued
    in the Stage 35 investigation, or a direct minimization of one."""

    def test_simple_sum(self, tmp_path: Path) -> None:
        """daily_trans_report.cbl:60 -- self-referencing accumulator."""
        result = _analyze(
            tmp_path,
            "    COMPUTE WS-TOTAL = WS-TOTAL + WS-VAL.\n    STOP RUN.\n",
            "01 WS-TOTAL PIC 9(7)V99.\n01 WS-VAL PIC 9(7)V99.\n",
        )
        assert result.syntax_diagnostics == []
        stmt = _first_statement(result)
        assert isinstance(stmt, ComputeStatementNode)
        assert stmt.target == "WS-TOTAL"
        assert stmt.expression == BinaryExpression(
            operator="+",
            left=OperandExpression(value="WS-TOTAL"),
            right=OperandExpression(value="WS-VAL"),
        )

    def test_literal_multiply(self, tmp_path: Path) -> None:
        """credit_approval.cbl:59 -- identifier * decimal literal."""
        result = _analyze(
            tmp_path,
            "    COMPUTE WS-LIMIT = WS-INCOME * 3.50.\n    STOP RUN.\n",
            "01 WS-LIMIT PIC 9(7)V99.\n01 WS-INCOME PIC 9(7)V99.\n",
        )
        assert result.syntax_diagnostics == []
        stmt = _first_statement(result)
        assert stmt.expression == BinaryExpression(
            operator="*",
            left=OperandExpression(value="WS-INCOME"),
            right=OperandExpression(value="3.50"),
        )

    def test_mixed_precedence_no_parens(self, tmp_path: Path) -> None:
        """billing_engine.cbl:53 -- A - B + C, left-to-right, no parens."""
        result = _analyze(
            tmp_path,
            "    COMPUTE WS-DUE = WS-BASE - WS-DISC + WS-TAX.\n    STOP RUN.\n",
            "01 WS-DUE PIC 9(7)V99.\n01 WS-BASE PIC 9(7)V99.\n"
            "01 WS-DISC PIC 9(7)V99.\n01 WS-TAX PIC 9(7)V99.\n",
        )
        assert result.syntax_diagnostics == []
        stmt = _first_statement(result)
        # (WS-BASE - WS-DISC) + WS-TAX
        assert isinstance(stmt.expression, BinaryExpression)
        assert stmt.expression.operator == "+"
        assert stmt.expression.left == BinaryExpression(
            operator="-",
            left=OperandExpression(value="WS-BASE"),
            right=OperandExpression(value="WS-DISC"),
        )
        assert stmt.expression.right == OperandExpression(value="WS-TAX")

    def test_one_level_parens_mixed_precedence(self, tmp_path: Path) -> None:
        """mortgage_service.cbl:43 -- (A / B) * 100.00."""
        result = _analyze(
            tmp_path,
            "    COMPUTE WS-RATIO = (WS-PRINCIPAL / WS-VALUE) * 100.00.\n"
            "    STOP RUN.\n",
            "01 WS-RATIO PIC 9(3)V99.\n01 WS-PRINCIPAL PIC 9(9)V99.\n"
            "01 WS-VALUE PIC 9(9)V99.\n",
        )
        assert result.syntax_diagnostics == []
        stmt = _first_statement(result)
        assert stmt.expression == BinaryExpression(
            operator="*",
            left=BinaryExpression(
                operator="/",
                left=OperandExpression(value="WS-PRINCIPAL"),
                right=OperandExpression(value="WS-VALUE"),
            ),
            right=OperandExpression(value="100.00"),
        )

    def test_doubly_nested_parens(self, tmp_path: Path) -> None:
        """payroll_deduct.cbl:55 -- the most complex expression in the
        corpus: A * (lit + ((B - lit) * lit / lit))."""
        result = _analyze(
            tmp_path,
            "    COMPUTE WS-MATCH ="
            " WS-SALARY * (0.03 + ((WS-PCT - 3.00) * 0.50 / 100.00)).\n"
            "    STOP RUN.\n",
            "01 WS-MATCH PIC 9(7)V99.\n01 WS-SALARY PIC 9(7)V99.\n"
            "01 WS-PCT PIC 9(3)V99.\n",
        )
        assert result.syntax_diagnostics == []
        stmt = _first_statement(result)
        assert isinstance(stmt.expression, BinaryExpression)
        assert stmt.expression.operator == "*"
        assert stmt.expression.left == OperandExpression(value="WS-SALARY")
        inner_add = stmt.expression.right
        assert isinstance(inner_add, BinaryExpression)
        assert inner_add.operator == "+"
        assert inner_add.left == OperandExpression(value="0.03")

    def test_subscripted_target_and_operands_literal_subscript(
        self, tmp_path: Path
    ) -> None:
        """order_hierarchy.cbl:55 -- COMPUTE EXTENDED-LINE-VAL(1) =
        QUANTITY-ORDERED(1) * UNIT-COST-AMOUNT(1). Target and both RHS
        operands carry the same literal subscript."""
        header = (
            "01 QUANTITY-ORDERED PIC 9(5) OCCURS 3.\n"
            "01 UNIT-COST-AMOUNT PIC 9(5)V99 OCCURS 3.\n"
            "01 EXTENDED-LINE-VAL PIC 9(5)V99 OCCURS 3.\n"
        )
        result = _analyze(
            tmp_path,
            "    COMPUTE EXTENDED-LINE-VAL(1) ="
            " QUANTITY-ORDERED(1) * UNIT-COST-AMOUNT(1).\n    STOP RUN.\n",
            header,
        )
        # OCCURS itself is unrelated, pre-existing SYN200 noise (not
        # represented in the AST -- Stage 32/33 concern, not Stage 35's);
        # only SYN100 ("unsupported statement") is this test's subject.
        assert "SYN100" not in [d.code for d in result.syntax_diagnostics]
        stmt = _first_statement(result)
        assert stmt.target == "EXTENDED-LINE-VAL"
        assert stmt.target_subscript == (Subscript(kind="literal", value="1"),)
        assert stmt.expression == BinaryExpression(
            operator="*",
            left=OperandExpression(
                value="QUANTITY-ORDERED",
                subscript=(Subscript(kind="literal", value="1"),),
            ),
            right=OperandExpression(
                value="UNIT-COST-AMOUNT",
                subscript=(Subscript(kind="literal", value="1"),),
            ),
        )

    def test_subscripted_operand_identifier_subscript_inside_loop(
        self, tmp_path: Path
    ) -> None:
        """table_indexed.cbl:41 -- COMPUTE ANNUAL-TOTAL-REVENUE =
        ANNUAL-TOTAL-REVENUE + REVENUE-AMOUNT(CURRENT-IDX), the running-
        total aggregation inside a PERFORM VARYING body."""
        header = (
            "01 CURRENT-IDX PIC 9(2) VALUE 1.\n"
            "01 REVENUE-AMOUNT PIC 9(7)V99 OCCURS 12.\n"
            "01 ANNUAL-TOTAL-REVENUE PIC 9(9)V99.\n"
        )
        result = _analyze(
            tmp_path,
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1 UNTIL CURRENT-IDX > 4\n"
            "        COMPUTE ANNUAL-TOTAL-REVENUE ="
            " ANNUAL-TOTAL-REVENUE + REVENUE-AMOUNT(CURRENT-IDX)\n"
            "    END-PERFORM.\n    STOP RUN.\n",
            header,
        )
        assert "SYN100" not in [d.code for d in result.syntax_diagnostics]
        loop = _first_statement(result)
        (compute,) = loop.statements
        assert isinstance(compute, ComputeStatementNode)
        assert compute.target_subscript == ()
        assert compute.expression == BinaryExpression(
            operator="+",
            left=OperandExpression(value="ANNUAL-TOTAL-REVENUE"),
            right=OperandExpression(
                value="REVENUE-AMOUNT",
                subscript=(Subscript(kind="identifier", value="CURRENT-IDX"),),
            ),
        )

    def test_bare_literal_rhs(self, tmp_path: Path) -> None:
        """Synthetic only -- not present in the real corpus, but a valid
        single-token expression per the grammar."""
        result = _analyze(
            tmp_path,
            "    COMPUTE WS-A = 123.\n    STOP RUN.\n",
            "01 WS-A PIC 9(5).\n",
        )
        assert result.syntax_diagnostics == []
        stmt = _first_statement(result)
        assert stmt.expression == OperandExpression(value="123")

    def test_three_operand_chain_no_parens(self, tmp_path: Path) -> None:
        """payroll_deduct.cbl:78 -- A + B + C + D, left-associative."""
        result = _analyze(
            tmp_path,
            "    COMPUTE WS-TOTAL = WS-A + WS-B + WS-C + WS-D.\n    STOP RUN.\n",
            "01 WS-TOTAL PIC 9(7)V99.\n01 WS-A PIC 9(7)V99.\n"
            "01 WS-B PIC 9(7)V99.\n01 WS-C PIC 9(7)V99.\n01 WS-D PIC 9(7)V99.\n",
        )
        assert result.syntax_diagnostics == []
        stmt = _first_statement(result)
        # ((WS-A + WS-B) + WS-C) + WS-D
        assert stmt.expression.operator == "+"
        assert stmt.expression.right == OperandExpression(value="WS-D")
        assert stmt.expression.left.right == OperandExpression(value="WS-C")
        assert stmt.expression.left.left == BinaryExpression(
            operator="+",
            left=OperandExpression(value="WS-A"),
            right=OperandExpression(value="WS-B"),
        )


# ===========================================================================
# 2. Statement-list wiring: paragraph level, IF then/else, PERFORM body
# ===========================================================================


class TestStatementListWiring:
    def test_paragraph_level(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    COMPUTE WS-A = WS-A + 1.\n    DISPLAY WS-A.\n    STOP RUN.\n",
            "01 WS-A PIC 9(5).\n",
        )
        assert result.syntax_diagnostics == []
        types = [
            s.__class__.__name__
            for s in result.ast.procedure_division.paragraphs[0].statements
        ]
        assert types == [
            "ComputeStatementNode",
            "DisplayStatementNode",
            "StopRunStatementNode",
        ]

    def test_if_then_and_else_branches(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    IF WS-A > 0\n"
            "        COMPUTE WS-B = WS-A * 2\n"
            "    ELSE\n"
            "        COMPUTE WS-B = WS-A * 3\n"
            "    END-IF\n"
            "    STOP RUN.\n",
            "01 WS-A PIC 9(5).\n01 WS-B PIC 9(5).\n",
        )
        assert result.syntax_diagnostics == []
        if_stmt = _first_statement(result)
        assert isinstance(if_stmt, IfStatementNode)
        assert isinstance(if_stmt.then_statements[0], ComputeStatementNode)
        assert isinstance(if_stmt.else_statements[0], ComputeStatementNode)

    def test_nested_if_any_depth(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    IF WS-A > 0\n"
            "        IF WS-B > 0\n"
            "            COMPUTE WS-C = WS-A + WS-B\n"
            "        END-IF\n"
            "    END-IF\n"
            "    STOP RUN.\n",
            "01 WS-A PIC 9(5).\n01 WS-B PIC 9(5).\n01 WS-C PIC 9(5).\n",
        )
        assert result.syntax_diagnostics == []
        outer = _first_statement(result)
        inner = outer.then_statements[0]
        assert isinstance(inner.then_statements[0], ComputeStatementNode)

    def test_perform_until_body(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    PERFORM UNTIL WS-A >= 3\n"
            "        COMPUTE WS-A = WS-A + 1\n"
            "    END-PERFORM\n"
            "    STOP RUN.\n",
            "01 WS-A PIC 9(3).\n",
        )
        assert result.syntax_diagnostics == []
        loop = _first_statement(result)
        assert isinstance(loop.statements[0], ComputeStatementNode)

    def test_statement_after_compute_survives(self, tmp_path: Path) -> None:
        """Critical regression shape (matches the COMPUTE/EVALUATE-in-IF
        history): a statement written after COMPUTE, with no period of
        its own between them, must not be swallowed."""
        result = _analyze(
            tmp_path,
            "    IF WS-A > 0\n"
            "        COMPUTE WS-B = WS-A + 1\n"
            "    END-IF\n"
            "    DISPLAY WS-B\n"
            "    DISPLAY WS-A.\n",
            "01 WS-A PIC 9(5).\n01 WS-B PIC 9(5).\n",
        )
        assert result.syntax_diagnostics == []
        types = [
            s.__class__.__name__
            for s in result.ast.procedure_division.paragraphs[0].statements
        ]
        assert types == [
            "IfStatementNode",
            "DisplayStatementNode",
            "DisplayStatementNode",
        ]


# ===========================================================================
# 3. Out-of-scope forms (ROUNDED, FUNCTION) still degrade gracefully
# ===========================================================================


class TestUnsupportedFormsDegradeGracefully:
    """Neither ROUNDED nor an intrinsic FUNCTION operand is anywhere in
    the 45-source training corpus (found only in
    tests/fixtures/complex_acctbatch.cbl during the Stage 35
    investigation). Both must still be recognised and gracefully skipped
    (SYN100), never mis-parsed and never a hard ParserError that could
    unwind an enclosing IF/PERFORM -- the exact defect class
    docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md fixed for the plain skip path."""

    def test_rounded_clause_is_skipped_not_misparsed(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    COMPUTE WS-FEE ROUNDED = WS-AMT * WS-RATE.\n    STOP RUN.\n",
            "01 WS-FEE PIC 9(5)V99.\n01 WS-AMT PIC 9(5)V99.\n"
            "01 WS-RATE PIC 9V9999.\n",
        )
        codes = [d.code for d in result.syntax_diagnostics]
        assert codes == ["SYN100"]
        assert "COMPUTE" in result.syntax_diagnostics[0].message
        types = [
            s.__class__.__name__
            for s in result.ast.procedure_division.paragraphs[0].statements
        ]
        assert types == ["StopRunStatementNode"]

    def test_function_operand_is_skipped_not_misparsed(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    COMPUTE WS-MONTH = FUNCTION MOD(WS-DATE / 100, 100).\n"
            "    STOP RUN.\n",
            "01 WS-MONTH PIC 9(2).\n01 WS-DATE PIC 9(8).\n",
        )
        codes = [d.code for d in result.syntax_diagnostics]
        assert codes == ["SYN100"]

    def test_rounded_inside_if_does_not_corrupt_enclosing_block(
        self, tmp_path: Path
    ) -> None:
        """The exact regression class this stage must not reintroduce:
        an unsupported COMPUTE sub-form inside an IF must not raise a
        ParserError that swallows the rest of the block."""
        result = _analyze(
            tmp_path,
            "    IF WS-A > 0\n"
            "        COMPUTE WS-FEE ROUNDED = WS-A * WS-RATE\n"
            "    END-IF\n"
            "    DISPLAY WS-FEE\n"
            "    DISPLAY WS-A.\n",
            "01 WS-A PIC 9(5)V99.\n01 WS-FEE PIC 9(5)V99.\n" "01 WS-RATE PIC 9V9999.\n",
        )
        codes = [d.code for d in result.syntax_diagnostics]
        assert codes == ["SYN100"]
        types = [
            s.__class__.__name__
            for s in result.ast.procedure_division.paragraphs[0].statements
        ]
        assert types == [
            "IfStatementNode",
            "DisplayStatementNode",
            "DisplayStatementNode",
        ]
