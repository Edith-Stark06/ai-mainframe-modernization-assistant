"""
Stage 36 — CALL ... USING comma-separated argument list fix.

Purpose:
    ``ProcedureDivisionParser._parse_call``'s ``USING`` argument-list loop
    appended *every* token between ``USING`` and the statement boundary to
    ``arguments`` — including a literal COBOL argument-separator comma —
    so ``CALL 'X' USING A, B, C`` produced ``arguments = ("A", ",", "B",
    ",", "C")``, a phantom operand whose lexeme is the string ``","``.

    This was a pre-existing, independent bug (predating both Stage 35 and
    Stage 36), found while investigating Stage 36's own corpus javac
    regressions: every real corpus ``CALL ... USING`` with 1+
    comma-separated arguments always lived inside a paragraph that was,
    until Stage 36, *always* a ``BE009`` stub with no body at all — so the
    corrupted argument list was built but never actually reached
    generated Java. Once Stage 36 taught the backend to outline a real
    PERFORM target's body, these CALL statements were emitted for the
    first time, and the comma bug surfaced as a ``javac`` compile error
    (a bogus ``field`` argument -- ``to_java_field_name(",")``).

    Space-separated ``USING`` argument lists (COBOL's other legal form,
    already covered by ``tests/parser/test_statement_boundaries.py``) are
    unaffected — a comma is only skipped when the token is actually
    present, so this fix is purely additive.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.parser.ast.statements import CallStatementNode
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.program_parser import ProgramParser

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nPROCEDURE DIVISION.\nMAIN-PARA.\n"


def _parse_call(body: str) -> CallStatementNode:
    tokens = CobolLexer().tokenize(_ID + body, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    stmt = program.procedure_division.paragraphs[0].statements[0]
    assert isinstance(stmt, CallStatementNode)
    return stmt


class TestCommaSeparatedUsing:
    def test_two_comma_separated_arguments(self) -> None:
        """billing_engine.cbl's real shape: CALL 'DISCENG1' USING
        DISC-IN-TIER, DISC-IN-SUBTOTAL, DISC-OUT-DISCOUNT (3 args)."""
        call = _parse_call(
            "    CALL 'DISCENG1' USING DISC-IN-TIER, DISC-IN-SUBTOTAL, "
            "DISC-OUT-DISCOUNT.\n    STOP RUN.\n"
        )
        assert call.target == "'DISCENG1'"
        assert call.arguments == (
            "DISC-IN-TIER",
            "DISC-IN-SUBTOTAL",
            "DISC-OUT-DISCOUNT",
        )
        assert "," not in call.arguments

    def test_four_comma_separated_arguments(self) -> None:
        """billing_engine.cbl's real CALL 'TAXENG01' shape (4 args)."""
        call = _parse_call(
            "    CALL 'TAXENG01' USING TAX-IN-STATE, TAX-IN-AMOUNT, "
            "TAX-OUT-TAX-RATE, TAX-OUT-TAX-AMOUNT.\n    STOP RUN.\n"
        )
        assert call.arguments == (
            "TAX-IN-STATE",
            "TAX-IN-AMOUNT",
            "TAX-OUT-TAX-RATE",
            "TAX-OUT-TAX-AMOUNT",
        )

    def test_single_argument_no_comma_unaffected(self) -> None:
        call = _parse_call("    CALL 'S1' USING WS-A.\n    STOP RUN.\n")
        assert call.arguments == ("WS-A",)

    def test_space_separated_arguments_unaffected(self) -> None:
        """The pre-existing, already-tested space-separated form
        (tests/parser/test_statement_boundaries.py) must be byte-for-byte
        unchanged — this fix only skips a comma when one is actually
        present."""
        call = _parse_call("    CALL 'S1' USING WS-A WS-B.\n    STOP RUN.\n")
        assert call.arguments == ("WS-A", "WS-B")
