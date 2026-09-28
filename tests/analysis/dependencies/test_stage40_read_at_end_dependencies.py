"""
Dependency analysis tests for task #stage40 — ``ReadStatementNode``
dependency extraction.

Purpose:
    ``DependencyAnalyzer.visit_read_statement`` recurses into
    ``at_end_statements`` only, mirroring exactly what
    ``IRBuilder.build_read_statement`` itself lowers. ``READ (A + B)...``
    -- er, rather: for ``READ F1 AT END MOVE 'Y' TO WS-EOF``, this
    registers a ``VARIABLE_WRITE`` on ``WS-EOF`` (the same dependency an
    ordinary top-level ``MOVE`` would). ``not_at_end_statements`` is
    provably unreachable under this backend's always-end-of-file READ
    model (no file-reading runtime exists) and contributes no
    dependency at all -- matching the IR precisely, confirmed directly.

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
    "01 WS-EOF PIC X(1) VALUE 'N'.\n"
    "01 WS-COUNT PIC 9(3) VALUE 0.\n"
)


def _deps(body: str) -> list:
    source = _HEADER + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body
    tokens = CobolLexer().tokenize(source, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    return DependencyAnalyzer().analyze(program)


def _targets(deps, dep_type: DependencyType) -> set[str]:
    return {d.target for d in deps if d.type is dep_type}


class TestAtEndDependencies:
    def test_at_end_move_target_is_variable_write(self) -> None:
        deps = _deps(
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n    END-READ.\n    STOP RUN.\n"
        )
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert "WS-EOF" in writes

    def test_at_end_multiple_statements_all_registered(self) -> None:
        deps = _deps(
            "    READ F1\n"
            "        AT END MOVE 'Y' TO WS-EOF\n"
            "                ADD 1 TO WS-COUNT\n"
            "    END-READ.\n    STOP RUN.\n"
        )
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        assert "WS-EOF" in writes
        assert "WS-COUNT" in writes
        assert "WS-COUNT" in reads  # ADD's pre-increment read


class TestNotAtEndContributesNoDependency:
    def test_not_at_end_alone_contributes_nothing(self) -> None:
        deps = _deps(
            "    READ F1 NOT AT END ADD 1 TO WS-COUNT\n    END-READ.\n    STOP RUN.\n"
        )
        assert deps == []

    def test_at_end_and_not_at_end_together_only_at_end_counted(self) -> None:
        """The real corpus shape (t_batch_acct_update)."""
        deps = _deps(
            "    READ F1 INTO R\n"
            "        AT END MOVE 'Y' TO WS-EOF\n"
            "        NOT AT END ADD 1 TO WS-COUNT\n"
            "    END-READ.\n    STOP RUN.\n"
        )
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert writes == {"WS-EOF"}


class TestReadItselfContributesNoDependency:
    def test_bare_read_no_clause_contributes_nothing(self) -> None:
        deps = _deps("    READ F1.\n    STOP RUN.\n")
        assert deps == []

    def test_into_target_not_registered(self) -> None:
        deps = _deps("    READ F1 INTO WS-COUNT.\n    STOP RUN.\n")
        assert deps == []


class TestScalarRegression:
    def test_ordinary_move_dependencies_unaffected(self) -> None:
        deps = _deps("    MOVE 'Y' TO WS-EOF.\n    STOP RUN.\n")
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert "WS-EOF" in writes
