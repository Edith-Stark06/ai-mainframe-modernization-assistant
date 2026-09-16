"""
Regression tests for statement-boundary handling (finding F-107-01).

Purpose:
    A statement written without a period terminator used to absorb the
    verb that followed it straight into its own operand list.  Operand
    accumulators stopped only at ``_STATEMENT_LEXEMES``, so a verb this
    parser cannot yet build an AST node for was treated as operand text::

        MOVE 'X' TO WS-A
        OPEN INPUT F1

    produced ``MoveStatementNode(target="WS-A OPEN INPUT F1")`` with **no
    diagnostic at all** — a corrupt AST that looked like a clean parse.

    Every supported statement parser that accumulates operands had the
    same defect: DISPLAY, MOVE, ADD, SUBTRACT, MULTIPLY, DIVIDE and CALL
    (both its target and its USING arguments).

    These tests drive real COBOL source through ``CobolLexer`` into
    ``ProgramParser`` and assert on the resulting AST, because the
    corruption is only observable in the operand values.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any

import pytest

from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.program_parser import ProgramParser
from app.parser.syntax.token_stream import TokenStream

_HEADER = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nPROCEDURE DIVISION.\n"


def _parse(body: str, *, paragraph: str = "MAIN") -> tuple[Any, ParserState]:
    """Parse a PROCEDURE DIVISION *body* end to end."""
    source = f"{_HEADER}{paragraph}.\n{body}"
    state = ParserState(TokenStream(CobolLexer().tokenize(source, filename="t.cbl")))
    return ProgramParser()._parse_program(state), state


def _statements(program: Any) -> list[Any]:
    """Return every statement of every paragraph, in order."""
    return [
        stmt
        for para in program.procedure_division.paragraphs
        for stmt in para.statements
    ]


def _names(program: Any) -> list[str]:
    """Return statement class names without the ``StatementNode`` suffix."""
    return [type(s).__name__.replace("StatementNode", "") for s in _statements(program)]


# ===========================================================================
# TEST 1 — a following unsupported statement is never absorbed
# ===========================================================================


class TestUnsupportedStatementNotAbsorbed:
    """
    The motivating case.  The unsupported verb must be diagnosed in its
    own right, and the statements around it must survive intact.
    """

    def test_move_target_is_not_corrupted(self) -> None:
        """``MOVE`` keeps only its real target operand."""
        program, _ = _parse("    MOVE 'X' TO WS-A\n    OPEN INPUT F1\n    STOP RUN.\n")
        move = _statements(program)[0]

        assert move.source == "'X'"
        assert move.target == "WS-A"

    def test_following_statements_survive(self) -> None:
        """``STOP RUN`` is still parsed, not swallowed with the skip."""
        program, _ = _parse("    MOVE 'X' TO WS-A\n    OPEN INPUT F1\n    STOP RUN.\n")

        assert _names(program) == ["Move", "StopRun"]

    def test_unsupported_verb_is_diagnosed(self) -> None:
        """The absorbed verb now gets the normal unsupported diagnostic."""
        _, state = _parse("    MOVE 'X' TO WS-A\n    OPEN INPUT F1\n    STOP RUN.\n")

        assert len(state.diagnostics) == 1
        assert "OPEN" in state.diagnostics[0].message

    def test_consecutive_unsupported_verbs_each_diagnosed(self) -> None:
        """Each period-less unsupported verb is reported separately."""
        program, state = _parse("    OPEN INPUT F1\n    READ F1\n    STOP RUN.\n")

        assert _names(program) == ["StopRun"]
        assert len(state.diagnostics) == 2

    def test_supported_statement_after_unsupported_is_parsed(self) -> None:
        """A period-less unsupported verb does not hide the next statement."""
        program, _ = _parse(
            "    OPEN INPUT F1\n    IF A = B DISPLAY 'x' END-IF.\n    STOP RUN.\n"
        )

        assert "If" in _names(program)


# ===========================================================================
# TEST 2 — a following supported statement still separates correctly
# ===========================================================================


class TestSupportedStatementSeparation:
    """Period-less sequences of supported statements were already correct."""

    def test_three_statements_without_periods(self) -> None:
        """MOVE / DISPLAY / STOP RUN remain three separate statements."""
        program, state = _parse(
            "    MOVE 'X' TO WS-A\n    DISPLAY WS-A\n    STOP RUN.\n"
        )

        assert _names(program) == ["Move", "Display", "StopRun"]
        assert state.diagnostics == []

    def test_operands_are_not_merged(self) -> None:
        """Neither statement's operand picks up the other's tokens."""
        program, _ = _parse("    MOVE 'X' TO WS-A\n    DISPLAY WS-A\n    STOP RUN.\n")
        move, display, _ = _statements(program)

        assert move.target == "WS-A"
        assert display.operand == "WS-A"


# ===========================================================================
# TEST 3 & 4 — existing well-formed behaviour is unchanged
# ===========================================================================


class TestWellFormedMoveUnchanged:
    """The fix must not disturb ordinary, period-terminated statements."""

    def test_period_terminated_move(self) -> None:
        """A normal MOVE parses exactly as before."""
        program, state = _parse("    MOVE 'X' TO WS-A.\n    STOP RUN.\n")
        move = _statements(program)[0]

        assert (move.source, move.target) == ("'X'", "WS-A")
        assert state.diagnostics == []

    def test_hyphenated_operands_are_not_truncated(self) -> None:
        """Multi-token-looking names are single identifiers and survive."""
        program, state = _parse("    MOVE CUSTOMER-NAME TO WS-NAME.\n    STOP RUN.\n")
        move = _statements(program)[0]

        assert move.source == "CUSTOMER-NAME"
        assert move.target == "WS-NAME"
        assert state.diagnostics == []

    def test_period_terminated_unsupported_statement_unchanged(self) -> None:
        """With a period present, behaviour matches the #105 baseline."""
        program, state = _parse(
            "    MOVE 'X' TO WS-A.\n    OPEN INPUT F1.\n    STOP RUN.\n"
        )

        assert _names(program) == ["Move", "StopRun"]
        assert len(state.diagnostics) == 1

    def test_scope_delimited_construct_still_skipped_whole(self) -> None:
        """
        A scope-opening verb is still skipped to its period, so the
        statements inside its body are not mistaken for a continuation.
        """
        program, state = _parse(
            "    EVALUATE X\n    WHEN 1 MOVE A TO B\n"
            "    END-EVALUATE.\n    STOP RUN.\n"
        )

        assert _names(program) == ["StopRun"]
        assert len(state.diagnostics) == 1

    def test_verb_inside_a_literal_is_not_a_boundary(self) -> None:
        """
        Negative case: a statement verb appearing inside a quoted literal
        is operand text.  Boundary matching only accepts word tokens, so
        a STRING token can never terminate an operand list.
        """
        program, state = _parse("    DISPLAY 'CUSTOMER OPEN ERROR' WS-A.\n")
        display = _statements(program)[0]

        assert "OPEN" in display.operand
        assert state.diagnostics == []


# ===========================================================================
# Arithmetic and CALL — the same accumulator defect
# ===========================================================================


class TestArithmeticAndCallBoundaries:
    """
    ADD, SUBTRACT, MULTIPLY, DIVIDE and CALL used the identical operand
    loop and absorbed a following unsupported verb in exactly the same
    way.  Verified before the fix: every one produced an operand of
    ``'WS-A OPEN INPUT F1'`` with zero diagnostics.
    """

    @pytest.mark.parametrize(
        ("body", "attribute"),
        [
            ("    ADD 1 TO WS-A\n", "right"),
            ("    SUBTRACT 1 FROM WS-A\n", "right"),
            ("    MULTIPLY 2 BY WS-A\n", "right"),
            ("    DIVIDE 2 INTO WS-A\n", "right"),
        ],
    )
    def test_arithmetic_operand_not_corrupted(self, body: str, attribute: str) -> None:
        """The right operand stops at the following unsupported verb."""
        program, state = _parse(f"{body}    OPEN INPUT F1\n    STOP RUN.\n")
        statements = _statements(program)

        assert getattr(statements[0], attribute) == "WS-A"
        assert statements[-1].__class__.__name__ == "StopRunStatementNode"
        assert len(state.diagnostics) == 1

    def test_call_target_not_corrupted(self) -> None:
        """A CALL target stops at the following unsupported verb."""
        program, state = _parse("    CALL 'S1'\n    OPEN INPUT F1\n    STOP RUN.\n")
        call = _statements(program)[0]

        assert call.target == "'S1'"
        assert len(state.diagnostics) == 1

    def test_call_using_arguments_not_corrupted(self) -> None:
        """CALL USING arguments stop at the following unsupported verb."""
        program, _ = _parse(
            "    CALL 'S1' USING WS-A\n    OPEN INPUT F1\n    STOP RUN.\n"
        )
        call = _statements(program)[0]

        assert list(call.arguments) == ["WS-A"]

    def test_well_formed_call_using_unchanged(self) -> None:
        """A period-terminated CALL USING keeps every argument."""
        program, state = _parse("    CALL 'S1' USING WS-A WS-B.\n    STOP RUN.\n")
        call = _statements(program)[0]

        assert call.target == "'S1'"
        assert list(call.arguments) == ["WS-A", "WS-B"]
        assert state.diagnostics == []


# ===========================================================================
# TEST 5 — numeric-prefixed paragraph names (task #106) still work
# ===========================================================================


class TestNumericPrefixedParagraphRegression:
    """The boundary change must not disturb paragraph identification."""

    def test_statements_stay_attached_to_numeric_paragraph(self) -> None:
        """``0000-MAIN`` keeps its name and all three statements."""
        program, state = _parse(
            "    MOVE 'X' TO WS-A\n    DISPLAY WS-A\n    STOP RUN.\n",
            paragraph="0000-MAIN",
        )
        paragraphs = program.procedure_division.paragraphs

        assert [p.name for p in paragraphs] == ["0000-MAIN"]
        assert _names(program) == ["Move", "Display", "StopRun"]
        assert state.diagnostics == []

    def test_numeric_paragraph_with_unsupported_verb(self) -> None:
        """Skipping does not consume the following paragraph label."""
        source = (
            f"{_HEADER}0000-MAIN.\n    OPEN INPUT F1\n    STOP RUN.\n"
            "1000-INIT.\n    DISPLAY 'B'.\n"
        )
        state = ParserState(
            TokenStream(CobolLexer().tokenize(source, filename="t.cbl"))
        )
        program = ProgramParser()._parse_program(state)

        assert [p.name for p in program.procedure_division.paragraphs] == [
            "0000-MAIN",
            "1000-INIT",
        ]
