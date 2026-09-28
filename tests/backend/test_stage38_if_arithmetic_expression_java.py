"""
Java backend + integration tests for task #stage38 — IF condition
parenthesized arithmetic-expression operand.

Purpose:
    ``_build_condition`` renders an ``IRIf.left_expression``/
    ``right_expression`` via ``_translate_expression`` -- the exact
    same Java expression renderer ``emit_compute`` already uses for
    ``COMPUTE``, reused unchanged -- and skips the COBOL-text-equality/
    figurative-constant paths entirely for that side (an arithmetic
    expression is always numeric). No change was needed to
    ``app/backend/java/generator.py`` for this stage; ``emit_if`` and
    the surrounding paragraph-outlining/dispatch machinery already
    compose with the new ``IRIf`` fields unmodified.

    The integration tests target
    ``data/sources/phase6-v2/inventory_reorder.cbl`` directly -- the
    real corpus source this whole stage exists to fix -- confirming its
    two previously-empty paragraphs (``3000-CALCULATE-ORDER-QUANTITY``,
    ``4000-EVALUATE-EXPEDITE-NEED``) are restored. This source's own,
    separate, already-known COMPUTE double/int narrowing ``javac``
    failure (``REORDER-POINT-QTY``, a different statement entirely) is
    NOT fixed here and is not expected to be -- these tests assert at
    the AST/IR/generated-Java-text level for that reason, never
    requiring this specific source to fully compile.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.analysis.service import AnalysisService

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nDATA DIVISION.\nWORKING-STORAGE SECTION.\n"

_HEADER = (
    "01 CURRENT-STOCK-QTY PIC 9(5) VALUE 120.\n"
    "01 SUGGESTED-ORDER-QTY PIC 9(5) VALUE 0.\n"
    "01 WAREHOUSE-CAPACITY PIC 9(5) VALUE 2000.\n"
    "01 SAFETY-STOCK-LEVEL PIC 9(5) VALUE 150.\n"
)


def _analyze(tmp_path: Path, body: str, header: str = _HEADER):
    source = _ID + header + "PROCEDURE DIVISION.\n" + body
    path = tmp_path / "t.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


_BODY = (
    "MAIN-PARA.\n"
    "    IF (CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY) > WAREHOUSE-CAPACITY\n"
    "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
    "    END-IF.\n    STOP RUN.\n"
)


class TestJavaGeneration:
    def test_no_diagnostics(self, tmp_path: Path) -> None:
        result = _analyze(tmp_path, _BODY)
        assert not result.backend_diagnostics

    def test_generated_java_contains_the_expression(self, tmp_path: Path) -> None:
        """No extra parentheses around the top-level '+' -- Java's own
        precedence already makes ``a + b > c`` unambiguous, exactly like
        Stage 35's COMPUTE renderer already omits them wherever
        semantically unnecessary."""
        result = _analyze(tmp_path, _BODY)
        assert (
            "if (currentStockQty + suggestedOrderQty > warehouseCapacity) {"
            in result.java_source
        )

    def test_right_side_expression_rendered_correctly(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    IF CURRENT-STOCK-QTY < (SAFETY-STOCK-LEVEL / 2)\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        assert not result.backend_diagnostics
        assert "if (currentStockQty < safetyStockLevel / 2) {" in result.java_source

    def test_generated_java_compiles(self, tmp_path: Path) -> None:
        result = _analyze(tmp_path, _BODY)
        java_file = tmp_path / "T.java"
        java_file.write_text(result.java_source, encoding="utf-8")
        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr


class TestRegressionOtherIfForms:
    def test_plain_if_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    IF CURRENT-STOCK-QTY > 0\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        assert not result.backend_diagnostics
        assert "if (currentStockQty > 0) {" in result.java_source

    def test_compute_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    COMPUTE SUGGESTED-ORDER-QTY = CURRENT-STOCK-QTY + 1.\n"
            "    STOP RUN.\n",
        )
        assert not result.backend_diagnostics
        assert "suggestedOrderQty = currentStockQty + 1;" in result.java_source

    def test_and_or_compound_condition_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    IF CURRENT-STOCK-QTY > 0 AND WAREHOUSE-CAPACITY > 0\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n",
        )
        assert not result.backend_diagnostics
        assert (
            "if (currentStockQty > 0 && warehouseCapacity > 0) {" in result.java_source
        )


class TestRuntimeExecution:
    """javac success alone does not prove the condition evaluates
    correctly -- these actually run the generated program."""

    def test_expression_condition_evaluates_correctly_true_branch(
        self, tmp_path: Path
    ) -> None:
        header = (
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. TEXE5.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-A PIC 9(3) VALUE 7.\n"
            "01 WS-B PIC 9(3) VALUE 8.\n"
            "01 WS-C PIC 9(3) VALUE 10.\n"
            "01 WS-RESULT PIC X(1) VALUE 'N'.\n"
        )
        source = (
            header + "PROCEDURE DIVISION.\n"
            "MAIN-PARA.\n"
            "    IF (WS-A + WS-B) > WS-C\n"
            "        MOVE 'Y' TO WS-RESULT\n"
            "    END-IF.\n"
            "    DISPLAY WS-RESULT.\n"
            "    STOP RUN.\n"
        )
        path = tmp_path / "t.cbl"
        path.write_text(source, encoding="utf-8")
        result = AnalysisService().analyze_file(path)
        assert not result.backend_diagnostics

        java_file = tmp_path / "Texe5.java"
        java_file.write_text(result.java_source, encoding="utf-8")
        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr

        run = subprocess.run(
            ["java", "-cp", str(tmp_path), "Texe5"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert run.returncode == 0, run.stderr
        # 7 + 8 = 15 > 10 -> true branch taken.
        assert run.stdout.strip() == "Y"

    def test_expression_condition_evaluates_correctly_false_branch(
        self, tmp_path: Path
    ) -> None:
        header = (
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. TEXE6.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-A PIC 9(3) VALUE 1.\n"
            "01 WS-B PIC 9(3) VALUE 2.\n"
            "01 WS-C PIC 9(3) VALUE 10.\n"
            "01 WS-RESULT PIC X(1) VALUE 'N'.\n"
        )
        source = (
            header + "PROCEDURE DIVISION.\n"
            "MAIN-PARA.\n"
            "    IF (WS-A + WS-B) > WS-C\n"
            "        MOVE 'Y' TO WS-RESULT\n"
            "    END-IF.\n"
            "    DISPLAY WS-RESULT.\n"
            "    STOP RUN.\n"
        )
        path = tmp_path / "t.cbl"
        path.write_text(source, encoding="utf-8")
        result = AnalysisService().analyze_file(path)
        assert not result.backend_diagnostics

        java_file = tmp_path / "Texe6.java"
        java_file.write_text(result.java_source, encoding="utf-8")
        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr

        run = subprocess.run(
            ["java", "-cp", str(tmp_path), "Texe6"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert run.returncode == 0, run.stderr
        # 1 + 2 = 3, not > 10 -> false branch (WS-RESULT stays 'N').
        assert run.stdout.strip() == "N"


class TestRealCorpusIntegration:
    """Direct integration against the real, unmodified corpus source this
    stage exists to fix."""

    _PATH = Path("data/sources/phase6-v2/inventory_reorder.cbl")

    def test_no_syntax_diagnostics(self) -> None:
        result = AnalysisService().analyze_file(self._PATH)
        assert result.syntax_diagnostics == []

    def test_both_previously_empty_paragraphs_now_have_statements(self) -> None:
        result = AnalysisService().analyze_file(self._PATH)
        by_name = {p.name: p for p in result.ast.procedure_division.paragraphs}
        assert len(by_name["3000-CALCULATE-ORDER-QUANTITY"].statements) > 0
        assert len(by_name["4000-EVALUATE-EXPEDITE-NEED"].statements) > 0

    def test_first_affected_if_survives(self) -> None:
        """Line 47: IF (CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY) >
        WAREHOUSE-CAPACITY, nested inside 3000-CALCULATE-ORDER-QUANTITY."""
        from app.parser.ast.statements import IfStatementNode

        result = AnalysisService().analyze_file(self._PATH)
        by_name = {p.name: p for p in result.ast.procedure_division.paragraphs}
        outer_if = by_name["3000-CALCULATE-ORDER-QUANTITY"].statements[0]
        assert isinstance(outer_if, IfStatementNode)

        def _find_expression_if(node):
            if not isinstance(node, IfStatementNode):
                return None
            if (
                node.condition_left_expression is not None
                or node.condition_right_expression is not None
            ):
                return node
            for stmt in list(node.then_statements) + list(node.else_statements):
                found = _find_expression_if(stmt)
                if found is not None:
                    return found
            return None

        found = _find_expression_if(outer_if)
        assert found is not None
        assert found.condition_operator == ">"
        assert found.condition_right == "WAREHOUSE-CAPACITY"

    def test_second_affected_if_survives(self) -> None:
        """Line 56: IF CURRENT-STOCK-QTY < (SAFETY-STOCK-LEVEL / 2),
        directly inside 4000-EVALUATE-EXPEDITE-NEED."""
        from app.parser.ast.statements import IfStatementNode

        result = AnalysisService().analyze_file(self._PATH)
        by_name = {p.name: p for p in result.ast.procedure_division.paragraphs}
        outer_if = by_name["4000-EVALUATE-EXPEDITE-NEED"].statements[0]
        assert isinstance(outer_if, IfStatementNode)
        inner_if = outer_if.then_statements[0]
        assert isinstance(inner_if, IfStatementNode)
        assert inner_if.condition_left == "CURRENT-STOCK-QTY"
        assert inner_if.condition_operator == "<"
        assert inner_if.condition_right_expression is not None

    def test_dependencies_present_for_both_paragraphs(self) -> None:
        result = AnalysisService().analyze_file(self._PATH)
        by_para: dict[str, set[str]] = {}
        for dep in result.dependencies:
            by_para.setdefault(dep.source, set()).add(dep.target)
        assert "CURRENT-STOCK-QTY" in by_para.get(
            "3000-CALCULATE-ORDER-QUANTITY", set()
        )
        assert "WAREHOUSE-CAPACITY" in by_para.get(
            "3000-CALCULATE-ORDER-QUANTITY", set()
        )
        assert "SAFETY-STOCK-LEVEL" in by_para.get("4000-EVALUATE-EXPEDITE-NEED", set())

    def test_cfg_decision_nodes_are_sensible(self) -> None:
        from app.modernization.flow.generator import generate_flow
        from app.modernization.flow.models import NodeType

        result = AnalysisService().analyze_file(self._PATH)
        flow = generate_flow(result)
        decision_names = [
            n.name for n in flow.nodes if n.node_type is NodeType.DECISION
        ]
        assert any(
            "CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY" in name for name in decision_names
        )
        assert any("SAFETY-STOCK-LEVEL / 2" in name for name in decision_names)

    def test_generated_java_contains_both_conditions(self) -> None:
        result = AnalysisService().analyze_file(self._PATH)
        java = result.java_source
        assert "if (currentStockQty + suggestedOrderQty > warehouseCapacity) {" in java
        assert "if (currentStockQty < safetyStockLevel / 2) {" in java

    def test_javac_now_succeeds_with_stage38_conditions_intact(
        self, tmp_path: Path
    ) -> None:
        """task #stage42: the pre-existing, unrelated ``COMPUTE`` narrowing
        bug this test used to work around (a ``double``-valued expression
        assigned to an ``int`` field, "possible lossy conversion from
        double to int") is now fixed -- an explicit ``(int)`` cast is
        emitted (see ``tests/backend/test_stage42_compute_narrowing_cast.py``
        for the dedicated tests). This source now compiles cleanly, with
        Stage 38's own two IF conditions still present and correct."""
        result = AnalysisService().analyze_file(self._PATH)
        java_file = tmp_path / "Invro01.java"
        java_file.write_text(result.java_source, encoding="utf-8")
        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr
        assert (
            "if (currentStockQty + suggestedOrderQty > warehouseCapacity) {"
            in result.java_source
        )
        assert "if (currentStockQty < safetyStockLevel / 2) {" in result.java_source
