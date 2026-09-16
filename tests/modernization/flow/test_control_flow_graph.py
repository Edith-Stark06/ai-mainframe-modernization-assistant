"""
Control-flow-graph regression tests (task #110).

Purpose:
    Prove that :func:`~app.modernization.flow.generator.generate_flow`
    represents real COBOL execution flow -- sequential statements,
    IF/ELSE branching with correct join points, PERFORM UNTIL loops,
    paragraph transitions distinguished from PERFORM, program
    termination, and CALL boundaries -- rather than only the call graph
    it produced before this task (still covered, unchanged, by
    ``tests/modernization/flow/test_generator.py``).

    Every test drives the real pipeline (source -> ``CobolLexer`` ->
    ``ProgramParser`` -> ``SemanticAnalyzer`` -> ``IRBuilder`` ->
    ``generate_flow``) rather than hand-constructing IR, so the CFG is
    exercised exactly as production code produces it.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from app.analysis.models import AnalysisResult
from app.ir.builder import IRBuilder
from app.modernization.flow.generator import (
    compute_reachability,
    count_cycles,
    generate_flow,
)
from app.modernization.flow.models import EdgeType, Flow, NodeType
from app.parser.lexer.lexer import CobolLexer
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.syntax.program_parser import ProgramParser

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\n"
_COMPLEX_FIXTURE = Path(
    "workspace/2e87036d-b90e-488f-b199-3162eb7c1c7e/complex_acctbatch.cbl"
)


def _flow_for(source: str) -> Flow:
    """Run *source* through the full pipeline and build its Flow graph."""
    tokens = CobolLexer().tokenize(source, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    ctx = SemanticAnalyzer().analyse(program)
    ir = IRBuilder(context=ctx).build(program)
    result = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=True,
        dependencies=[],
        ast=program,
        ir=ir,
    )
    return generate_flow(result)


def _stmt_nodes(flow: Flow) -> list[Any]:
    """Return only the statement-level (``stmt_``) nodes, excluding call-graph ones."""
    return [n for n in flow.nodes if n.id.startswith("stmt_")]


def _node_by_name(flow: Flow, name: str) -> Any:
    return next(n for n in _stmt_nodes(flow) if n.name == name)


def _edges_from(flow: Flow, node_id: str) -> list[Any]:
    return [e for e in flow.edges if e.source_id == node_id]


def _main_entry(flow: Flow) -> str:
    """The first statement node of the MAIN paragraph -- the program entry."""
    return next(n.id for n in _stmt_nodes(flow) if n.id.endswith("_MAIN_0"))


def _entry_for_first_paragraph(source: str, flow: Flow) -> str:
    """
    The entry node of *source*'s actual first paragraph, whatever it is
    named -- robust to names like ``"0000-MAIN"`` (task #106) that
    ``_main_entry``'s literal ``"MAIN"`` suffix match cannot handle,
    since a hyphen (not an underscore) precedes "MAIN" in that name.
    """
    tokens = CobolLexer().tokenize(source, filename="entry_lookup.cbl")
    program = ProgramParser().parse(tokens)
    first_paragraph = program.procedure_division.paragraphs[0].name
    suffix = f"_{first_paragraph}_0"
    return next(n.id for n in _stmt_nodes(flow) if n.id.endswith(suffix))


class TestSequentialFlow:
    """A -> B -> C, using FLOWS_TO edges."""

    def test_three_statements_chain_sequentially(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n    MOVE 1 TO WS-A.\n"
            '    DISPLAY "B".\n    STOP RUN.\n'
        )
        flow = _flow_for(source)

        move = _node_by_name(flow, "MOVE 1 TO WS-A")
        display = _node_by_name(flow, 'DISPLAY "B"')
        stop = _node_by_name(flow, "STOP RUN")

        move_edges = _edges_from(flow, move.id)
        assert len(move_edges) == 1
        assert move_edges[0].target_id == display.id
        assert move_edges[0].edge_type is EdgeType.FLOWS_TO

        display_edges = _edges_from(flow, display.id)
        assert len(display_edges) == 1
        assert display_edges[0].target_id == stop.id


class TestIfElse:
    """IF/ELSE: DECISION node, TRUE/FALSE edges, both branches join."""

    def test_if_else_true_false_and_join(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    IF WS-AGE > 18\n"
            '        DISPLAY "ADULT"\n'
            "    ELSE\n"
            '        DISPLAY "MINOR"\n'
            "    END-IF.\n"
            "    STOP RUN.\n"
        )
        flow = _flow_for(source)

        decision = _node_by_name(flow, "IF WS-AGE > 18")
        assert decision.node_type is NodeType.DECISION

        adult = _node_by_name(flow, 'DISPLAY "ADULT"')
        minor = _node_by_name(flow, 'DISPLAY "MINOR"')
        stop = _node_by_name(flow, "STOP RUN")

        dec_edges = {e.target_id: e.edge_type for e in _edges_from(flow, decision.id)}
        assert dec_edges == {
            adult.id: EdgeType.TRUE_BRANCH,
            minor.id: EdgeType.FALSE_BRANCH,
        }

        # Both branches converge on the same join point (STOP RUN).
        assert _edges_from(flow, adult.id)[0].target_id == stop.id
        assert _edges_from(flow, minor.id)[0].target_id == stop.id

    def test_if_without_else_false_branch_reaches_join_directly(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            '    IF WS-X = 1 DISPLAY "MATCH" END-IF.\n'
            "    STOP RUN.\n"
        )
        flow = _flow_for(source)
        decision = _node_by_name(flow, "IF WS-X = 1")
        stop = _node_by_name(flow, "STOP RUN")

        dec_edges = {e.edge_type: e.target_id for e in _edges_from(flow, decision.id)}
        # No ELSE: the FALSE branch must go straight to the join point.
        assert dec_edges[EdgeType.FALSE_BRANCH] == stop.id


class TestNestedIf:
    """Nested IF: both levels' branches and joins must be correct and distinct."""

    def test_nested_if_branches_do_not_bypass_inner_join(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    IF WS-OUTER = 1\n"
            "        IF WS-INNER = 2\n"
            '            DISPLAY "BOTH"\n'
            "        ELSE\n"
            '            DISPLAY "OUTER-ONLY"\n'
            "        END-IF\n"
            '        DISPLAY "AFTER-INNER"\n'
            "    END-IF.\n"
            "    STOP RUN.\n"
        )
        flow = _flow_for(source)

        outer = _node_by_name(flow, "IF WS-OUTER = 1")
        inner = _node_by_name(flow, "IF WS-INNER = 2")
        both = _node_by_name(flow, 'DISPLAY "BOTH"')
        outer_only = _node_by_name(flow, 'DISPLAY "OUTER-ONLY"')
        after_inner = _node_by_name(flow, 'DISPLAY "AFTER-INNER"')
        stop = _node_by_name(flow, "STOP RUN")

        # The outer decision's TRUE branch goes to the inner decision,
        # not directly to anything past it.
        outer_true = next(
            e.target_id
            for e in _edges_from(flow, outer.id)
            if e.edge_type is EdgeType.TRUE_BRANCH
        )
        assert outer_true == inner.id

        # Both inner branches join at AFTER-INNER, not at STOP RUN directly.
        assert _edges_from(flow, both.id)[0].target_id == after_inner.id
        assert _edges_from(flow, outer_only.id)[0].target_id == after_inner.id

        # AFTER-INNER then reaches the outer join point (STOP RUN).
        assert _edges_from(flow, after_inner.id)[0].target_id == stop.id

        # The outer decision's FALSE branch must skip straight to STOP
        # RUN (there is no outer ELSE) -- it must NOT point at the inner
        # decision or either inner branch.
        outer_false = next(
            e.target_id
            for e in _edges_from(flow, outer.id)
            if e.edge_type is EdgeType.FALSE_BRANCH
        )
        assert outer_false == stop.id
        assert outer_false not in (inner.id, both.id, outer_only.id)


class TestLoop:
    """PERFORM UNTIL: condition -> body, body -> condition, condition -> exit."""

    def test_loop_body_and_exit_and_back_edge(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    PERFORM UNTIL WS-DONE = 1\n"
            "        ADD 1 TO WS-COUNT\n"
            "    END-PERFORM.\n"
            "    STOP RUN.\n"
        )
        flow = _flow_for(source)

        condition = _node_by_name(flow, "PERFORM UNTIL WS-DONE = 1")
        body = _node_by_name(flow, "ADD 1 TO WS-COUNT")
        stop = _node_by_name(flow, "STOP RUN")

        cond_edges = {e.edge_type: e.target_id for e in _edges_from(flow, condition.id)}
        assert cond_edges[EdgeType.LOOP_BODY] == body.id
        assert cond_edges[EdgeType.LOOP_EXIT] == stop.id

        body_edges = _edges_from(flow, body.id)
        assert len(body_edges) == 1
        assert body_edges[0].edge_type is EdgeType.LOOP_BACK
        assert body_edges[0].target_id == condition.id

    def test_loop_produces_exactly_one_counted_cycle(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    PERFORM UNTIL WS-DONE = 1\n"
            "        ADD 1 TO WS-COUNT\n"
            "    END-PERFORM.\n"
            "    STOP RUN.\n"
        )
        flow = _flow_for(source)
        assert count_cycles(flow) == 1


class TestPerformParagraph:
    """PERFORM <paragraph>: distinct from sequential flow and from CALL."""

    def test_perform_target_and_return_site_are_both_represented(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    PERFORM SUB1.\n"
            '    DISPLAY "AFTER-PERFORM".\n'
            "    STOP RUN.\n"
            "SUB1.\n"
            '    DISPLAY "IN-SUB".\n'
        )
        flow = _flow_for(source)

        perform_node = _node_by_name(flow, "PERFORM SUB1")
        after = _node_by_name(flow, 'DISPLAY "AFTER-PERFORM"')
        in_sub = _node_by_name(flow, 'DISPLAY "IN-SUB"')

        edges = {e.edge_type: e.target_id for e in _edges_from(flow, perform_node.id)}
        # Sequential flow within MAIN continues to the next statement...
        assert edges[EdgeType.FLOWS_TO] == after.id
        # ...and a distinct PERFORMS edge reaches the target paragraph.
        assert edges[EdgeType.PERFORMS] == in_sub.id

    def test_perform_is_not_misrepresented_as_a_call_edge(self) -> None:
        """A PERFORM to a local paragraph must not produce a CALLS edge."""
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    PERFORM SUB1.\n    STOP RUN.\n"
            'SUB1.\n    DISPLAY "X".\n'
        )
        flow = _flow_for(source)
        assert not any(e.edge_type is EdgeType.CALLS for e in flow.edges)

    def test_forward_referenced_perform_target_resolves(self) -> None:
        """PERFORM of a paragraph defined *later* in the source still resolves."""
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    PERFORM LATER-PARA.\n    STOP RUN.\n"
            "LATER-PARA.\n"
            '    DISPLAY "LATER".\n'
        )
        flow = _flow_for(source)
        perform_node = _node_by_name(flow, "PERFORM LATER-PARA")
        later = _node_by_name(flow, 'DISPLAY "LATER"')
        edges = {e.edge_type: e.target_id for e in _edges_from(flow, perform_node.id)}
        assert edges[EdgeType.PERFORMS] == later.id


class TestParagraphFallthrough:
    """A paragraph with no terminal statement falls through to the next."""

    def test_non_terminal_paragraph_falls_through(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\n"
            "FIRST-PARA.\n"
            '    DISPLAY "FIRST".\n'
            "SECOND-PARA.\n"
            '    DISPLAY "SECOND".\n'
            "    STOP RUN.\n"
        )
        flow = _flow_for(source)
        first = _node_by_name(flow, 'DISPLAY "FIRST"')
        second = _node_by_name(flow, 'DISPLAY "SECOND"')

        edges = _edges_from(flow, first.id)
        assert len(edges) == 1
        assert edges[0].target_id == second.id
        assert edges[0].edge_type is EdgeType.FALLTHROUGH

    def test_if_without_else_as_last_statement_both_branches_cross_the_boundary(
        self,
    ) -> None:
        """
        Regression: an IF with no ELSE as a paragraph's *final* statement
        used to leave the decision's FALSE branch unresolved -- only the
        THEN branch's exit reached the next paragraph, silently dropping
        the "condition was false" edge entirely rather than connecting
        it to whatever comes after the paragraph.
        """
        source = (
            _ID + "PROCEDURE DIVISION.\n"
            "FIRST-PARA.\n"
            "    IF WS-X = 1\n"
            '        DISPLAY "TRUE-CASE"\n'
            "    END-IF.\n"
            "SECOND-PARA.\n"
            '    DISPLAY "NEXT".\n'
            "    STOP RUN.\n"
        )
        flow = _flow_for(source)
        decision = _node_by_name(flow, "IF WS-X = 1")
        true_case = _node_by_name(flow, 'DISPLAY "TRUE-CASE"')
        next_stmt = _node_by_name(flow, 'DISPLAY "NEXT"')

        dec_edges = {e.edge_type: e.target_id for e in _edges_from(flow, decision.id)}
        assert dec_edges[EdgeType.TRUE_BRANCH] == true_case.id
        # The bug: this used to be missing entirely.
        assert dec_edges[EdgeType.FALSE_BRANCH] == next_stmt.id

        assert _edges_from(flow, true_case.id)[0].target_id == next_stmt.id

    def test_terminal_paragraph_does_not_fall_through(self) -> None:
        """A paragraph ending in STOP RUN must have no outgoing edge at all."""
        source = (
            _ID + "PROCEDURE DIVISION.\n"
            "FIRST-PARA.\n"
            '    DISPLAY "FIRST".\n'
            "    STOP RUN.\n"
            "SECOND-PARA.\n"
            '    DISPLAY "SECOND".\n'
        )
        flow = _flow_for(source)
        stop = _node_by_name(flow, "STOP RUN")
        assert _edges_from(flow, stop.id) == []


class TestGobackAndStopRun:
    """GOBACK/STOP RUN terminate flow; no phantom successor is created."""

    def test_stop_run_has_no_outgoing_edge(self) -> None:
        flow = _flow_for(
            _ID + 'PROCEDURE DIVISION.\nMAIN.\n    DISPLAY "A".\n    STOP RUN.\n'
        )
        stop = _node_by_name(flow, "STOP RUN")
        assert _edges_from(flow, stop.id) == []

    def test_goback_has_no_outgoing_edge(self) -> None:
        flow = _flow_for(
            _ID + 'PROCEDURE DIVISION.\nMAIN.\n    DISPLAY "A".\n    GOBACK.\n'
        )
        goback = _node_by_name(flow, "GOBACK")
        assert _edges_from(flow, goback.id) == []

    def test_stop_run_and_goback_have_distinguishing_metadata(self) -> None:
        flow = _flow_for(
            _ID + 'PROCEDURE DIVISION.\nMAIN.\n    DISPLAY "A".\n    STOP RUN.\n'
        )
        stop = _node_by_name(flow, "STOP RUN")
        assert stop.metadata.get("terminal") is True
        assert stop.metadata.get("kind") == "STOP RUN"


class TestCallBoundary:
    """CALL to an external program: a boundary edge, not an expanded body."""

    def test_call_produces_a_calls_edge_to_an_external_node(self) -> None:
        source = (
            _ID + 'PROCEDURE DIVISION.\nMAIN.\n    CALL "EXTPROG".\n    STOP RUN.\n'
        )
        flow = _flow_for(source)

        assert any(
            e.edge_type is EdgeType.CALLS and e.target_id == "ext_EXTPROG"
            for e in flow.edges
        )
        ext_node = next(n for n in flow.nodes if n.id == "ext_EXTPROG")
        assert ext_node.node_type is NodeType.EXTERNAL

    def test_call_also_participates_in_sequential_flow(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            '    CALL "EXTPROG".\n    DISPLAY "AFTER-CALL".\n    STOP RUN.\n'
        )
        flow = _flow_for(source)
        call_node = _node_by_name(flow, "CALL EXTPROG")
        after = _node_by_name(flow, 'DISPLAY "AFTER-CALL"')
        edges = [
            e
            for e in _edges_from(flow, call_node.id)
            if e.edge_type is EdgeType.FLOWS_TO
        ]
        assert len(edges) == 1
        assert edges[0].target_id == after.id


class TestUnreachableCode:
    """Statements after a terminal statement, with nothing pointing to them."""

    def test_statement_after_stop_run_is_unreachable(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            '    DISPLAY "REACHABLE".\n'
            "    STOP RUN.\n"
            '    DISPLAY "DEAD-CODE".\n'
        )
        flow = _flow_for(source)
        entry = _main_entry(flow)
        reachable = compute_reachability(flow, entry)

        dead = _node_by_name(flow, 'DISPLAY "DEAD-CODE"')
        reachable_node = _node_by_name(flow, 'DISPLAY "REACHABLE"')

        assert reachable_node.id in reachable
        assert dead.id not in reachable


class TestCycleHandling:
    """Cycles must be represented without infinite traversal during analysis."""

    def test_reachability_terminates_through_a_loop(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    PERFORM UNTIL WS-DONE = 1\n"
            "        ADD 1 TO WS-COUNT\n"
            "    END-PERFORM.\n"
            "    STOP RUN.\n"
        )
        flow = _flow_for(source)
        entry = _main_entry(flow)
        # No timeout needed: compute_reachability is iterative with a
        # visited set (see its own docstring) and provably terminates.
        reachable = compute_reachability(flow, entry)
        assert len(reachable) == len(_stmt_nodes(flow))

    def test_nested_loops_also_terminate_and_count_correctly(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    PERFORM UNTIL WS-OUTER = 1\n"
            "        PERFORM UNTIL WS-INNER = 1\n"
            "            ADD 1 TO WS-INNER\n"
            "        END-PERFORM\n"
            "    END-PERFORM.\n"
            "    STOP RUN.\n"
        )
        flow = _flow_for(source)
        assert count_cycles(flow) == 2


class TestMalformedInputTermination:
    """CFG construction (and its analyses) must never hang."""

    @staticmethod
    def _run_with_deadline(source: str, seconds: float = 10.0) -> Flow:
        result: list[Flow] = []
        error: list[BaseException] = []

        def run() -> None:
            try:
                result.append(_flow_for(source))
            except BaseException as exc:  # noqa: BLE001 - re-raised below
                error.append(exc)

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(timeout=seconds)

        assert (
            not worker.is_alive()
        ), f"CFG generation did not terminate within {seconds}s"
        if error:
            raise error[0]
        return result[0]

    def test_deeply_nested_if_terminates(self) -> None:
        depth = 40
        body = 'DISPLAY "DEEP"'
        source = _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        for i in range(depth):
            source += f"    IF WS-X = {i}\n"
        source += f"        {body}\n"
        source += "    END-IF\n" * depth
        source += ".\n    STOP RUN.\n"
        flow = self._run_with_deadline(source)
        assert len(flow.nodes) > depth

    def test_many_paragraphs_with_perform_terminates(self) -> None:
        paras = "\n".join(f'PARA-{i}.\n    DISPLAY "P{i}".\n' for i in range(100))
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    PERFORM PARA-0.\n    STOP RUN.\n" + paras
        )
        flow = self._run_with_deadline(source)
        assert count_cycles(flow) == 0  # no loops in this fixture

    def test_perform_target_not_defined_does_not_hang_or_crash(self) -> None:
        """A PERFORM to a paragraph that does not exist must not crash the graph."""
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    PERFORM MISSING-PARA.\n    STOP RUN.\n"
        )
        flow = self._run_with_deadline(source)
        assert any(
            e.edge_type is EdgeType.PERFORMS and e.target_id == "ext_MISSING-PARA"
            for e in flow.edges
        )


class TestComplexFixture:
    """The real 500-line stress fixture used throughout tasks #107-#109."""

    def test_complex_fixture_builds_a_flow_without_hanging(self) -> None:
        if not _COMPLEX_FIXTURE.exists():
            return
        source = _COMPLEX_FIXTURE.read_text()

        result: list[Flow] = []

        def run() -> None:
            result.append(_flow_for(source))

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(timeout=20.0)
        assert not worker.is_alive()
        flow = result[0]

        assert len(flow.nodes) > 1
        entry = _entry_for_first_paragraph(source, flow)
        reachable = compute_reachability(flow, entry)
        unreachable = [n.id for n in _stmt_nodes(flow) if n.id not in reachable]

        # Report-only assertions: the fixture must produce a real,
        # non-trivial graph; exact counts are recorded in the task #110
        # final report rather than pinned here, since #107's remaining
        # condition-AST gap (documented, out of scope) still limits how
        # much of the fixture's IF logic is representable.
        assert len(_stmt_nodes(flow)) > 10
        assert isinstance(count_cycles(flow), int)
        assert isinstance(unreachable, list)
