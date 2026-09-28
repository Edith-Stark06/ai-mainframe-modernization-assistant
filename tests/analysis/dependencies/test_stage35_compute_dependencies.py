"""
Stage 35 — dependency analysis for COMPUTE.

Purpose:
    ``DependencyAnalyzer.visit_compute_statement`` registers the target
    as ``VARIABLE_WRITE`` (plus its own subscript as a read, task
    #stage32) and every operand leaf in the expression tree as
    ``VARIABLE_READ`` (plus each leaf's own subscript) -- a recursive
    generalization of ``_visit_arithmetic``'s existing two-operand
    read/write model to COMPUTE's N-ary expression tree, never a
    flattened combined name like ``"PRICE ( WS-I )"``.

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
    "01 WS-I PIC 9(2) VALUE 1.\n"
    "01 TOTAL PIC 9(7)V99 OCCURS 5.\n"
    "01 PRICE PIC 9(7)V99 OCCURS 5.\n"
    "01 QUANTITY PIC 9(5) OCCURS 5.\n"
    "01 WS-A PIC 9(7)V99.\n"
    "01 WS-B PIC 9(7)V99.\n"
    "01 WS-C PIC 9(7)V99.\n"
    "01 WS-D PIC 9(7)V99.\n"
)


def _deps(body: str) -> list:
    source = _TABLE_HEADER + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body
    tokens = CobolLexer().tokenize(source, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    return DependencyAnalyzer().analyze(program)


def _targets(deps, dep_type: DependencyType) -> set[str]:
    return {d.target for d in deps if d.type is dep_type}


class TestTaskWorkedExample:
    def test_price_quantity_ws_i_read_total_write(self) -> None:
        """The task's own explicit example:
        COMPUTE TOTAL(WS-I) = PRICE(WS-I) * QUANTITY(WS-I)
        must produce reads on PRICE, QUANTITY, WS-I and a write on
        TOTAL -- never a flattened garbage name like
        'PRICE ( WS-I )'."""
        deps = _deps(
            "    COMPUTE TOTAL(WS-I) = PRICE(WS-I) * QUANTITY(WS-I).\n"
            "    STOP RUN.\n"
        )
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert reads == {"PRICE", "QUANTITY", "WS-I"}
        assert writes == {"TOTAL"}
        all_targets = {d.target for d in deps}
        assert not any("(" in t or " " in t for t in all_targets)


class TestExpressionTreeWalk:
    def test_every_leaf_in_a_deep_tree_is_read(self) -> None:
        """A doubly-nested expression (mirrors payroll_deduct.cbl:55's
        shape) must surface every leaf, however deeply nested, not just
        the top-level pair."""
        deps = _deps(
            "    COMPUTE WS-A = WS-B * (0.03 + ((WS-C - 3.00) * 0.50 / 100.00)).\n"
            "    STOP RUN.\n"
        )
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert reads == {"WS-B", "WS-C"}
        assert writes == {"WS-A"}

    def test_numeric_literals_are_never_reported_as_variables(self) -> None:
        deps = _deps("    COMPUTE WS-A = WS-B * 3.50.\n    STOP RUN.\n")
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        assert reads == {"WS-B"}

    def test_three_operand_chain_reads_all_three(self) -> None:
        """payroll_deduct.cbl:78's shape: A + B + C + D."""
        deps = _deps("    COMPUTE WS-A = WS-B + WS-C + WS-D.\n    STOP RUN.\n")
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        assert reads == {"WS-B", "WS-C", "WS-D"}


class TestSelfReferencingAccumulator:
    def test_target_appears_as_both_read_and_write(self) -> None:
        """daily_trans_report.cbl:60's shape: COMPUTE X = X + Y --
        equivalent in effect to ADD Y TO X, so X is both read (its prior
        value participates) and written (the result replaces it),
        matching _visit_arithmetic's existing rule for ADD/SUBTRACT/
        MULTIPLY/DIVIDE's own accumulator operand."""
        deps = _deps("    COMPUTE WS-A = WS-A + WS-B.\n    STOP RUN.\n")
        reads = _targets(deps, DependencyType.VARIABLE_READ)
        writes = _targets(deps, DependencyType.VARIABLE_WRITE)
        assert reads == {"WS-A", "WS-B"}
        assert writes == {"WS-A"}


class TestSubscriptDeduplication:
    def test_repeated_index_variable_reported_once(self) -> None:
        """order_hierarchy.cbl's shape: the same index variable used as a
        subscript multiple times within one statement is still one
        dependency (deduplicated by DependencyAnalyzer's own
        (source, type, target) key), not double-counted."""
        deps = _deps(
            "    COMPUTE TOTAL(WS-I) = PRICE(WS-I) + PRICE(WS-I).\n" "    STOP RUN.\n"
        )
        ws_i_reads = [
            d
            for d in deps
            if d.type is DependencyType.VARIABLE_READ and d.target == "WS-I"
        ]
        assert len(ws_i_reads) == 1
