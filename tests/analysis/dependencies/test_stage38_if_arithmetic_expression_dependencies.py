"""
Dependency analysis tests for task #stage38 — IF condition parenthesized
arithmetic-expression operand dependency extraction.

Purpose:
    ``DependencyAnalyzer._visit_condition_operand`` registers every
    identifier leaf of a parenthesized arithmetic-expression operand as
    a ``VARIABLE_READ`` -- reusing :meth:`_visit_expression`, the exact
    walker :meth:`visit_compute_statement` already uses for ``COMPUTE``,
    unchanged -- while a plain (non-expression) operand keeps its
    pre-existing ``CONDITION`` dependency exactly as before this stage.

    For ``IF (A + B) > C`` this registers reads of ``A`` and ``B`` (via
    the expression walker) and a ``CONDITION`` dependency on ``C`` (the
    plain right operand) -- matching the task's own example exactly.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.analysis.dependencies.analyzer import DependencyAnalyzer
from app.analysis.dependencies.models import DependencyType
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.program_parser import ProgramParser

_HEADER = (
    "IDENTIFICATION DIVISION.\n"
    "PROGRAM-ID. T.\n"
    "DATA DIVISION.\n"
    "WORKING-STORAGE SECTION.\n"
    "01 CURRENT-STOCK-QTY PIC 9(5) VALUE 120.\n"
    "01 SUGGESTED-ORDER-QTY PIC 9(5) VALUE 0.\n"
    "01 WAREHOUSE-CAPACITY PIC 9(5) VALUE 2000.\n"
    "01 SAFETY-STOCK-LEVEL PIC 9(5) VALUE 150.\n"
)


def _deps(body: str) -> list:
    source = _HEADER + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body
    tokens = CobolLexer().tokenize(source, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    return DependencyAnalyzer().analyze(program)


def _targets(deps, dep_type: DependencyType) -> set[str]:
    return {d.target for d in deps if d.type is dep_type}


_BODY = (
    "    IF (CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY) > WAREHOUSE-CAPACITY\n"
    "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
    "    END-IF.\n    STOP RUN.\n"
)


class TestExpressionOperandReads:
    """IF (A + B) > C -- reads of A and B, task's own example."""

    def test_left_expression_leaves_are_variable_reads(self) -> None:
        deps = _deps(_BODY)
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        assert "CURRENT-STOCK-QTY" in reads
        assert "SUGGESTED-ORDER-QTY" in reads

    def test_plain_right_operand_is_still_a_condition_dependency(self) -> None:
        deps = _deps(_BODY)
        conditions = _targets(deps, DependencyType.CONDITION)
        assert "WAREHOUSE-CAPACITY" in conditions

    def test_right_expression_leaves_are_variable_reads(self) -> None:
        deps = _deps(
            "    IF CURRENT-STOCK-QTY < (SAFETY-STOCK-LEVEL / 2)\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n"
        )
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        conditions = _targets(deps, DependencyType.CONDITION)
        assert "SAFETY-STOCK-LEVEL" in reads
        assert "CURRENT-STOCK-QTY" in conditions


class TestNoFalseWrites:
    def test_expression_operands_never_registered_as_writes(self) -> None:
        deps = _deps(_BODY)
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        # Only the MOVE target inside the THEN branch is a write --
        # never CURRENT-STOCK-QTY/WAREHOUSE-CAPACITY, which are only read.
        assert writes == {"SUGGESTED-ORDER-QTY"}
        assert "CURRENT-STOCK-QTY" not in writes
        assert "WAREHOUSE-CAPACITY" not in writes


class TestNoDuplicateOrCorruptedEntries:
    def test_no_corrupted_combined_name(self) -> None:
        deps = _deps(_BODY)
        all_targets = {d.target for d in deps}
        assert not any("(" in t or " " in t for t in all_targets)

    def test_literal_expression_operand_contributes_no_dependency(self) -> None:
        deps = _deps(
            "    IF (CURRENT-STOCK-QTY + 1) > WAREHOUSE-CAPACITY\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n"
        )
        all_targets = {d.target for d in deps}
        assert "1" not in all_targets


class TestScalarRegression:
    def test_plain_if_condition_dependency_unaffected(self) -> None:
        deps = _deps(
            "    IF CURRENT-STOCK-QTY > 0\n"
            "        MOVE 1 TO SUGGESTED-ORDER-QTY\n"
            "    END-IF.\n    STOP RUN.\n"
        )
        conditions = _targets(deps, DependencyType.CONDITION)
        assert "CURRENT-STOCK-QTY" in conditions

    def test_compute_dependencies_unaffected(self) -> None:
        deps = _deps(
            "    COMPUTE SUGGESTED-ORDER-QTY = CURRENT-STOCK-QTY + 1.\n"
            "    STOP RUN.\n"
        )
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert "CURRENT-STOCK-QTY" in reads
        assert "SUGGESTED-ORDER-QTY" in writes
