"""
Regression tests: a missing period at the end of the program (``SYN002``).

Purpose:
    Statement parsers treat their trailing period as optional
    (``ProcedureDivisionParser._consume_optional_period``), because a
    statement nested in ``IF``/``PERFORM UNTIL`` legitimately has none and a
    bare statement parser cannot know its context. That leniency also
    silently accepted the one place a period is always required -- the last
    sentence of the program -- so ``MOVE 1 TO WS-A`` ending the source
    produced no diagnostic, although the diagnostic taxonomy registers
    ``SYN002 "Missing period"`` for exactly this and
    ``ProcedureDivisionParser.parse``'s own contract lists it. Four unit
    tests written for TASK-017 (``TestProcedureDivisionParserErrors``)
    encode that contract and had been failing since TASK-039 made periods
    optional.

    ``ProcedureDivisionParser._diagnose_unterminated_final_sentence`` closes
    the gap at end of input only. These tests pin both halves of the
    contract: the diagnostic fires where a period is genuinely required, and
    the deliberately-accepted period-less style elsewhere is untouched.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any

from app.analysis.service import AnalysisService
from app.dataset.corpus import load_training_corpus
from app.parser.diagnostics.recovery import SyntaxCategory, SyntaxSeverity
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.program_parser import ProgramParser
from app.parser.syntax.token_stream import TokenStream

_HEADER = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nPROCEDURE DIVISION.\n"


def _parse(body: str) -> tuple[Any, ParserState]:
    source = f"{_HEADER}MAIN.\n{body}"
    state = ParserState(TokenStream(CobolLexer().tokenize(source, filename="t.cbl")))
    return ProgramParser()._parse_program(state), state


def _codes(state: ParserState) -> list[str]:
    return [d.code for d in state.diagnostics]


def _statement_names(program: Any) -> list[str]:
    return [
        type(s).__name__.replace("StatementNode", "")
        for para in program.procedure_division.paragraphs
        for s in para.statements
    ]


def test_final_statement_without_period_is_reported() -> None:
    program, state = _parse("    MOVE 1 TO WS-A\n")
    assert _codes(state) == ["SYN002"]
    (diag,) = state.diagnostics
    assert diag.severity is SyntaxSeverity.ERROR
    assert diag.category is SyntaxCategory.SYNTAX_ERROR
    assert "'.'" in diag.message
    # reporting the gap loses nothing: the statement is still in the AST
    assert _statement_names(program) == ["Move"]


def test_final_statement_with_period_is_clean() -> None:
    program, state = _parse("    MOVE 1 TO WS-A.\n")
    assert state.diagnostics == []
    assert _statement_names(program) == ["Move"]


def test_period_less_statements_before_the_final_sentence_stay_legal() -> None:
    """Idiomatic COBOL: periods only at the end of the paragraph. Must never
    be reported -- only the *end of input* is checked."""
    program, state = _parse("    MOVE 1 TO WS-A\n    MOVE 2 TO WS-B\n    STOP RUN.\n")
    assert state.diagnostics == []
    assert _statement_names(program) == ["Move", "Move", "StopRun"]


def test_structured_block_ending_the_program_needs_its_period_too() -> None:
    _, state = _parse("    IF WS-A = 1\n        MOVE 2 TO WS-B\n    END-IF\n")
    assert _codes(state) == ["SYN002"]


def test_structured_block_with_final_period_is_clean() -> None:
    _, state = _parse("    IF WS-A = 1\n        MOVE 2 TO WS-B\n    END-IF.\n")
    assert state.diagnostics == []


def test_empty_procedure_division_has_no_sentence_to_terminate() -> None:
    state = ParserState(
        TokenStream(
            CobolLexer().tokenize(
                "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nPROCEDURE DIVISION.\n",
                filename="t.cbl",
            )
        )
    )
    ProgramParser()._parse_program(state)
    assert state.diagnostics == []


def test_reported_through_the_full_analysis_pipeline(tmp_path) -> None:
    path = tmp_path / "noperiod.cbl"
    path.write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. NOPER.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01  WS-A PIC 9(3) VALUE 0.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           MOVE 1 TO WS-A\n"
        "           STOP RUN\n",
        encoding="utf-8",
    )
    result = AnalysisService().analyze_file(path)
    assert [str(d.code) for d in result.syntax_diagnostics] == ["SYN002"]
    stmts = result.ast.procedure_division.paragraphs[0].statements
    assert [type(s).__name__ for s in stmts] == [
        "MoveStatementNode",
        "StopRunStatementNode",
    ]


def test_no_corpus_source_is_affected() -> None:
    """Every one of the 45 corpus sources ends with a period, so this check
    cannot change any dataset content (no version bump, no regeneration)."""
    flagged = []
    for rec in load_training_corpus():
        state = ParserState(
            TokenStream(CobolLexer().tokenize(rec.source, filename=rec.source_id))
        )
        ProgramParser()._parse_program(state)
        if any(d.code == "SYN002" for d in state.diagnostics):
            flagged.append(rec.source_id)
    assert flagged == []
