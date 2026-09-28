"""
Dependency analysis tests for task #stage34 —
``PerformVaryingStatementNode`` dependency extraction.

Purpose:
    ``DependencyAnalyzer.visit_perform_varying_statement`` registers:

    * a ``VARIABLE_WRITE`` for the varying variable (its own FROM
      initialisation and every iteration's BY increment assign to it);
    * a ``VARIABLE_READ`` for ``FROM``/``BY`` when either names a
      variable (a literal -- the shape every real corpus occurrence
      actually uses -- contributes nothing, the same literal-filtering
      rule every other operand dependency already applies);
    * a ``CONDITION`` dependency (plus any subscript index variable) for
      the ``UNTIL`` condition's operands, exactly like ``PERFORM UNTIL``/
      ``IF``;
    * every body statement's own dependencies, recursively, exactly like
      ``PERFORM UNTIL``.

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

_TABLE_HEADER = (
    "IDENTIFICATION DIVISION.\n"
    "PROGRAM-ID. T.\n"
    "DATA DIVISION.\n"
    "WORKING-STORAGE SECTION.\n"
    "01 CURRENT-IDX PIC 9(2) VALUE 1.\n"
    "01 WS-START PIC 9(2) VALUE 1.\n"
    "01 WS-STEP PIC 9(2) VALUE 1.\n"
    "01 WS-TABLE.\n"
    "   05 WS-ITEM PIC 9(3) OCCURS 4.\n"
    "01 WS-TOTAL PIC 9(5).\n"
)


def _deps(body: str) -> list:
    source = _TABLE_HEADER + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body
    tokens = CobolLexer().tokenize(source, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    return DependencyAnalyzer().analyze(program)


def _targets(deps, dep_type: DependencyType) -> set[str]:
    return {d.target for d in deps if d.type is dep_type}


class TestVaryingVariableWrite:
    def test_varying_variable_is_a_write(self) -> None:
        deps = _deps(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert "CURRENT-IDX" in writes


class TestFromByRead:
    def test_literal_from_by_contribute_no_dependency(self) -> None:
        deps = _deps(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        all_targets = {d.target for d in deps}
        assert "1" not in all_targets

    def test_identifier_from_is_read(self) -> None:
        deps = _deps(
            "    PERFORM VARYING CURRENT-IDX FROM WS-START BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        assert "WS-START" in reads

    def test_identifier_by_is_read(self) -> None:
        deps = _deps(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY WS-STEP\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        assert "WS-STEP" in reads


class TestUntilConditionDependency:
    def test_until_operand_is_a_condition_dependency(self) -> None:
        deps = _deps(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        conditions = _targets(deps, DependencyType.CONDITION)
        assert "CURRENT-IDX" in conditions

    def test_subscripted_until_condition_reads_its_index(self) -> None:
        deps = _deps(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL WS-ITEM(CURRENT-IDX) > 100\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        conditions = _targets(deps, DependencyType.CONDITION)
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        assert "WS-ITEM" in conditions
        assert "CURRENT-IDX" in reads


class TestBodyDependenciesRecurse:
    def test_body_move_dependencies_are_present(self) -> None:
        deps = _deps(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        MOVE CURRENT-IDX TO WS-ITEM(CURRENT-IDX)\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert "CURRENT-IDX" in reads  # the MOVE source and the subscript index
        assert "WS-ITEM" in writes

    def test_body_condition_and_arithmetic_dependencies_are_present(self) -> None:
        deps = _deps(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        IF WS-ITEM(CURRENT-IDX) > 100\n"
            "            ADD 1 TO WS-TOTAL\n"
            "        END-IF\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        conditions = _targets(deps, DependencyType.CONDITION)
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert "WS-ITEM" in conditions
        assert "WS-TOTAL" in writes

    def test_no_corrupted_combined_name_anywhere(self) -> None:
        deps = _deps(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL WS-ITEM(CURRENT-IDX) > 100\n"
            "        MOVE CURRENT-IDX TO WS-ITEM(CURRENT-IDX)\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        all_targets = {d.target for d in deps}
        assert not any("(" in t or " " in t for t in all_targets)


class TestScalarRegression:
    def test_plain_perform_until_dependencies_unaffected(self) -> None:
        deps = _deps(
            "    PERFORM UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "        ADD 1 TO CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        conditions = _targets(deps, DependencyType.CONDITION)
        assert "CURRENT-IDX" in conditions
