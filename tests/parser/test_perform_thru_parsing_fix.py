"""
Regression tests for the ``PERFORM A THRU C`` parsing defect identified in
the Stage 15 (``mmim-gen-v15``) audit.

Purpose:
    ``ProcedureDivisionParser._parse_perform_statement``'s inline-PERFORM
    branch read exactly one identifier as ``target`` and returned
    immediately, never checking for a following ``THRU``/``THROUGH``
    clause. Neither word is reserved in this lexer, so ``THRU``/the range
    end arrived as ordinary trailing tokens the statement loop did not
    recognise, producing a ``SYN001`` recovery diagnostic that discarded
    them -- the range end was never represented anywhere in the AST.

    The fix adds an optional ``THRU``/``THROUGH`` clause to the inline
    PERFORM branch only (``PERFORM UNTIL`` is untouched): after the first
    identifier, if the next token's lexeme is ``THRU`` or ``THROUGH``
    (case-insensitive), it is consumed and the identifier that follows
    becomes ``PerformStatementNode.thru_target``. An ordinary
    ``PERFORM A`` (no THRU) leaves ``thru_target == ""``, so its AST is
    identical to before.

    These tests drive real COBOL source through ``CobolLexer`` into
    ``ProgramParser`` and assert on the resulting AST and diagnostics,
    exactly like ``tests/parser/test_read_at_end_parsing_fix.py``.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.parser.ast.statements import PerformStatementNode
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.program_parser import ProgramParser
from app.parser.syntax.token_stream import TokenStream

SOURCES = Path("data/sources/phase6-v2")

_HEADER = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nPROCEDURE DIVISION.\n"


def _parse(body: str, *, paragraph: str = "MAIN") -> tuple[Any, ParserState]:
    """Parse a PROCEDURE DIVISION *body* end to end."""
    source = f"{_HEADER}{paragraph}.\n{body}"
    state = ParserState(TokenStream(CobolLexer().tokenize(source, filename="t.cbl")))
    return ProgramParser()._parse_program(state), state


def _performs(program: Any) -> list[PerformStatementNode]:
    return [
        stmt
        for para in program.procedure_division.paragraphs
        for stmt in para.statements
        if isinstance(stmt, PerformStatementNode)
    ]


# ===========================================================================
# Ordinary PERFORM (no THRU) -- unaffected
# ===========================================================================


def test_ordinary_perform_has_empty_thru_target() -> None:
    program, state = _parse("    PERFORM SUB1.\n    STOP RUN.\n")
    performs = _performs(program)
    assert len(performs) == 1
    assert performs[0].target == "SUB1"
    assert performs[0].thru_target == ""
    assert not state.has_errors


def test_ordinary_perform_without_trailing_period_still_parses() -> None:
    """A bare PERFORM immediately followed by another statement, no THRU,
    no period -- the pre-existing statement-boundary behaviour must be
    completely unaffected by adding THRU support."""
    program, state = _parse("    PERFORM SUB1\n    STOP RUN.\n")
    performs = _performs(program)
    assert len(performs) == 1
    assert performs[0].target == "SUB1"
    assert performs[0].thru_target == ""


# ===========================================================================
# PERFORM A THRU C
# ===========================================================================


def test_perform_thru_captures_both_targets() -> None:
    program, state = _parse(
        "    PERFORM ALPHA THRU GAMMA.\n    STOP RUN.\n"
        'ALPHA.\n    DISPLAY "A".\n'
        'GAMMA.\n    DISPLAY "G".\n'
    )
    performs = _performs(program)
    assert len(performs) == 1
    assert performs[0].target == "ALPHA"
    assert performs[0].thru_target == "GAMMA"
    # No SYN001 "unexpected token 'THRU'" diagnostic remains.
    assert not any("THRU" in d.message for d in state.diagnostics)


def test_perform_through_spelling_is_also_recognised() -> None:
    """COBOL accepts THRU and THROUGH interchangeably."""
    program, _state = _parse(
        "    PERFORM ALPHA THROUGH GAMMA.\n    STOP RUN.\n"
        'ALPHA.\n    DISPLAY "A".\n'
        'GAMMA.\n    DISPLAY "G".\n'
    )
    performs = _performs(program)
    assert performs[0].target == "ALPHA"
    assert performs[0].thru_target == "GAMMA"


def test_perform_thru_leaves_the_statement_after_it_intact() -> None:
    """The statement immediately following a PERFORM THRU must parse
    correctly and completely -- proving no tokens belonging to it are
    consumed by the THRU clause."""
    program, state = _parse(
        "    PERFORM ALPHA THRU GAMMA.\n"
        "    ADD 1 TO WS-COUNT.\n"
        "    STOP RUN.\n"
        'ALPHA.\n    DISPLAY "A".\n'
        'GAMMA.\n    DISPLAY "G".\n'
    )
    stmt_kinds = [
        type(s).__name__
        for para in program.procedure_division.paragraphs
        for s in para.statements
    ]
    assert "AddStatementNode" in stmt_kinds
    assert not state.has_errors


def test_perform_thru_same_start_and_end_is_a_degenerate_single_paragraph_range() -> (
    None
):
    """PERFORM A THRU A is legal (if unusual) COBOL."""
    program, _state = _parse(
        '    PERFORM ALPHA THRU ALPHA.\n    STOP RUN.\nALPHA.\n    DISPLAY "A".\n'
    )
    performs = _performs(program)
    assert performs[0].target == "ALPHA"
    assert performs[0].thru_target == "ALPHA"


def test_malformed_thru_with_no_following_identifier_raises_parser_error() -> None:
    """THRU with nothing (or a non-identifier) after it is a genuine syntax
    error, not silently accepted -- it must still be diagnosed, just like
    a malformed PERFORM without a target is today."""
    _program, state = _parse("    PERFORM ALPHA THRU.\n    STOP RUN.\n")
    assert state.has_errors


# ===========================================================================
# Real corpus: t_fallthrough_flow (the one real PERFORM THRU occurrence
# among the 45 sources -- confirmed by direct corpus search, not assumed)
# ===========================================================================


def test_real_fallthrough_flow_perform_thru_is_captured() -> None:
    tokens = CobolLexer().tokenize(
        (SOURCES / "fallthrough_flow.cbl").read_text(encoding="utf-8"),
        filename="fallthrough_flow.cbl",
    )
    program = ProgramParser().parse(tokens)
    performs = _performs(program)
    assert len(performs) == 1
    assert performs[0].target == "1000-STAGE-ALPHA"
    assert performs[0].thru_target == "3000-STAGE-GAMMA"
