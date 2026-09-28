"""
Dependency analysis tests for task #stage37 —
``PerformTargetUntilStatementNode`` dependency extraction.

Purpose:
    ``DependencyAnalyzer.visit_perform_target_until_statement`` registers
    exactly the union of what
    :meth:`~app.analysis.dependencies.analyzer.DependencyAnalyzer.visit_perform_statement`
    and
    :meth:`~app.analysis.dependencies.analyzer.DependencyAnalyzer.visit_perform_until_statement`
    each register on their own:

    * a ``PERFORM`` dependency on the named target (the same paragraph
      transition a plain ``PERFORM`` records);
    * a ``CONDITION`` dependency on each ``UNTIL`` condition operand (the
      same read the inline form records for its own ``UNTIL``).

    There is no loop body to recurse into (unlike the inline form) --
    the target paragraph's own statements are visited separately, when
    the analyzer reaches that paragraph in source order.

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
    "01 WS-EOF PIC X(1) VALUE SPACE.\n"
)


def _deps(body: str, header: str = _HEADER) -> list:
    source = header + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body
    tokens = CobolLexer().tokenize(source, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    return DependencyAnalyzer().analyze(program)


def _targets(deps, dep_type: DependencyType) -> set[str]:
    return {d.target for d in deps if d.type is dep_type}


_BODY = (
    "    PERFORM 2000-PROCESS-RECORDS UNTIL WS-EOF = 'Y'.\n"
    "    GOBACK.\n"
    "2000-PROCESS-RECORDS.\n"
    "    DISPLAY WS-EOF.\n"
)


class TestPerformDependency:
    def test_target_paragraph_is_a_perform_dependency(self) -> None:
        deps = _deps(_BODY)
        performs = _targets(deps, DependencyType.PERFORM)
        assert "2000-PROCESS-RECORDS" in performs


class TestConditionOperandDependency:
    def test_condition_left_is_a_condition_dependency(self) -> None:
        deps = _deps(_BODY)
        conditions = _targets(deps, DependencyType.CONDITION)
        assert "WS-EOF" in conditions

    def test_literal_condition_operand_contributes_no_dependency(self) -> None:
        deps = _deps(_BODY)
        all_targets = {d.target for d in deps}
        assert "'Y'" not in all_targets
        assert "Y" not in all_targets


class TestSourceAttribution:
    def test_perform_dependency_is_attributed_to_the_entry_paragraph(self) -> None:
        deps = _deps(_BODY)
        (perform_dep,) = [d for d in deps if d.type is DependencyType.PERFORM]
        assert perform_dep.source == "MAIN-PARA"


class TestOtherRealSourceNames:
    def test_batch_acct_update_shape(self) -> None:
        deps = _deps(
            "    PERFORM 3000-PROCESS-LOOP UNTIL WS-EOF-FLAG = 'Y'.\n"
            "    GOBACK.\n"
            "3000-PROCESS-LOOP.\n"
            "    DISPLAY 'X'.\n",
            header=_HEADER + "01 WS-EOF-FLAG PIC X(1) VALUE SPACE.\n",
        )
        assert "3000-PROCESS-LOOP" in _targets(deps, DependencyType.PERFORM)
        assert "WS-EOF-FLAG" in _targets(deps, DependencyType.CONDITION)


class TestScalarRegression:
    def test_plain_perform_dependencies_unaffected(self) -> None:
        deps = _deps(
            "    PERFORM SUB-PARA.\n    GOBACK.\nSUB-PARA.\n    DISPLAY 'X'.\n"
        )
        assert "SUB-PARA" in _targets(deps, DependencyType.PERFORM)

    def test_inline_perform_until_dependencies_unaffected(self) -> None:
        deps = _deps(
            "    PERFORM UNTIL WS-EOF = 'Y'\n"
            "        DISPLAY 'X'\n"
            "    END-PERFORM.\n    GOBACK.\n"
        )
        assert "WS-EOF" in _targets(deps, DependencyType.CONDITION)
