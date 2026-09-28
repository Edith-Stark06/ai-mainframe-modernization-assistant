"""
Stage 32 — dependency analysis for subscripted table references.

Purpose:
    Before this stage, ``MOVE WS-ITEM(WS-I) TO WS-TOTAL`` corrupted the
    dependency graph two ways: (1) the flattened AST operand
    (``"WS-ITEM ( WS-I )"``) produced a bogus ``VARIABLE_READ`` node for
    a variable that does not exist, and (2) the index variable
    (``WS-I``) was invisible -- embedded inside that same garbled
    string -- so no dependency was ever registered for it at all.

    Fixing the AST layer (task #stage32's main representation fix)
    already resolves (1): ``node.source``/``node.target``/etc. are the
    clean base name, so the pre-existing dependency-extraction code
    registers the *correct* variable without any change of its own. This
    file locks in (2): the dependency analyzer now also reads the index
    variable, exactly once, only when it is an identifier (never for a
    literal subscript, which reads nothing).

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
    "01 WS-TABLE.\n"
    "   05 WS-ITEM PIC 9(5) OCCURS 5 TIMES.\n"
    "   05 WS-I PIC 9(2) VALUE 1.\n"
    "01 WS-TOTAL PIC 9(5).\n"
)


def _deps(body: str) -> list:
    source = _TABLE_HEADER + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body
    tokens = CobolLexer().tokenize(source, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    return DependencyAnalyzer().analyze(program)


def _targets(deps, dep_type: DependencyType) -> set[str]:
    return {d.target for d in deps if d.type is dep_type}


class TestMoveIdentifierSubscriptDependency:
    def test_read_of_table_read_of_index_write_of_target(self) -> None:
        """The task's own explicit example: MOVE WS-ITEM(WS-I) TO WS-TOTAL
        must distinguish read of WS-ITEM, read of WS-I, write of
        WS-TOTAL."""
        deps = _deps("    MOVE WS-ITEM(WS-I) TO WS-TOTAL.\n    STOP RUN.\n")
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert reads == {"WS-ITEM", "WS-I"}
        assert writes == {"WS-TOTAL"}
        # No corrupted combined name anywhere.
        all_targets = {d.target for d in deps}
        assert not any("(" in t or " " in t for t in all_targets)

    def test_no_index_dependency_for_a_literal_subscript(self) -> None:
        """The task's own explicit example: MOVE 123 TO WS-ITEM(2) has no
        index-variable dependency -- there is no variable to read."""
        deps = _deps("    MOVE 123 TO WS-ITEM(2).\n    STOP RUN.\n")
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert reads == set()
        assert writes == {"WS-ITEM"}

    def test_subscripted_write_target_also_reads_its_index(self) -> None:
        deps = _deps("    MOVE WS-TOTAL TO WS-ITEM(WS-I).\n    STOP RUN.\n")
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert reads == {"WS-TOTAL", "WS-I"}
        assert writes == {"WS-ITEM"}


class TestArithmeticSubscriptDependency:
    def test_add_identifier_subscript_reads_index_once(self) -> None:
        deps = _deps("    ADD 1 TO WS-ITEM(WS-I).\n    STOP RUN.\n")
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert "WS-I" in reads
        assert "WS-ITEM" in reads  # right is both read and written
        assert writes == {"WS-ITEM"}
        # exactly one VARIABLE_READ dependency for the index variable
        index_reads = [
            d
            for d in deps
            if d.type is DependencyType.VARIABLE_READ and d.target == "WS-I"
        ]
        assert len(index_reads) == 1

    def test_add_literal_subscript_has_no_index_dependency(self) -> None:
        deps = _deps("    ADD 1 TO WS-ITEM(3).\n    STOP RUN.\n")
        all_targets = {d.target for d in deps}
        assert "3" not in all_targets
        assert all("(" not in t for t in all_targets)


class TestConditionSubscriptDependency:
    def test_if_condition_subscript_registers_index_read(self) -> None:
        deps = _deps(
            "    IF WS-ITEM(WS-I) > 100\n"
            "        DISPLAY 'HIGH'\n"
            "    END-IF.\n    STOP RUN.\n"
        )
        conditions = _targets(deps, DependencyType.CONDITION)
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        assert "WS-ITEM" in conditions
        assert "WS-I" in reads


class TestScalarDependencyRegression:
    def test_plain_move_dependencies_unchanged(self) -> None:
        deps = _deps("    MOVE WS-TOTAL TO WS-I.\n    STOP RUN.\n")
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert reads == {"WS-TOTAL"}
        assert writes == {"WS-I"}
