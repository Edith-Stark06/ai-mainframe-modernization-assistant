"""
Regression tests for real COBOL ``GO TO`` parsing (Stage 17).

Purpose:
    ``GO`` was in ``_UNSUPPORTED_STATEMENT_LEXEMES`` since inception --
    a real ``GO TO paragraph-name`` statement produced no AST node at
    all (a single ``SYN100`` diagnostic and nothing else), even though
    ``GoToStatementNode`` and ``IRBuilder.build_go_to_statement`` (->
    ``IRJump``) already existed and were already fully wired --
    confirmed unreachable only at the parser boundary
    (``tests/ir/test_ir_ast_node_coverage.py``).

    The fix moves ``"GO"`` from ``_UNSUPPORTED_STATEMENT_LEXEMES`` to
    ``_STATEMENT_LEXEMES`` and adds a dispatch case
    (``_parse_go_to_statement``) that parses the single-target
    ``GO TO paragraph-name`` form -- the only form found anywhere in the
    45-source corpus (confirmed by direct search: no ``DEPENDING ON``,
    no multi-target list). Neither ``GO`` nor ``TO`` is a reserved word
    in this lexer, so ``TO`` is recognised by lexeme, the same way
    ``PERFORM``'s ``THRU``/``THROUGH`` markers already are.

    These tests drive real COBOL source through ``CobolLexer`` into
    ``ProgramParser`` and assert on the resulting AST and diagnostics,
    exactly like ``tests/parser/test_perform_thru_parsing_fix.py``.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.parser.ast.statements import GoToStatementNode, IfStatementNode
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


def _statements(program: Any) -> list[Any]:
    return [
        stmt
        for para in program.procedure_division.paragraphs
        for stmt in para.statements
    ]


def _all_statements_recursive(statements: Any) -> list[Any]:
    """Every statement, including those nested inside an IF's THEN/ELSE
    branches -- a GO TO very commonly lives there, not only at a
    paragraph's top level."""
    out: list[Any] = []
    for stmt in statements:
        out.append(stmt)
        if isinstance(stmt, IfStatementNode):
            out.extend(_all_statements_recursive(stmt.then_statements))
            out.extend(_all_statements_recursive(stmt.else_statements))
    return out


def _go_tos(program: Any) -> list[GoToStatementNode]:
    return [
        s
        for para in program.procedure_division.paragraphs
        for s in _all_statements_recursive(para.statements)
        if isinstance(s, GoToStatementNode)
    ]


# ===========================================================================
# Simple GO TO
# ===========================================================================


def test_simple_go_to_is_parsed() -> None:
    program, state = _parse("    GO TO OTHER-PARA.\nOTHER-PARA.\n    STOP RUN.\n")
    gotos = _go_tos(program)
    assert len(gotos) == 1
    assert gotos[0].target == "OTHER-PARA"
    assert not state.has_errors
    assert not any(d.code == "SYN100" for d in state.diagnostics)


def test_go_to_without_trailing_period_still_parses() -> None:
    """A bare GO TO immediately followed by another statement, no period
    -- the same period-less-statement pattern PERFORM/DISPLAY already
    support."""
    program, state = _parse("    GO TO OTHER-PARA\nOTHER-PARA.\n    STOP RUN\n")
    gotos = _go_tos(program)
    assert len(gotos) == 1
    assert gotos[0].target == "OTHER-PARA"


def test_malformed_go_missing_to_is_diagnosed() -> None:
    """``GO`` not followed by ``TO`` is a genuine syntax error, not
    silently accepted."""
    _program, state = _parse("    GO SOMEWHERE.\n    STOP RUN.\n")
    assert state.has_errors


def test_malformed_go_to_missing_target_is_diagnosed() -> None:
    _program, state = _parse("    GO TO.\n    STOP RUN.\n")
    assert state.has_errors


# ===========================================================================
# Nested inside IF/ELSE (the real corpus's actual shape)
# ===========================================================================


def test_go_to_inside_if_then_branch_is_parsed() -> None:
    program, state = _parse(
        "    IF WS-FLAG = 1\n"
        "        GO TO PARA-B\n"
        "    END-IF.\n"
        "    STOP RUN.\n"
        "PARA-B.\n    STOP RUN.\n"
    )
    assert not state.has_errors
    if_stmt = next(s for s in _statements(program) if isinstance(s, IfStatementNode))
    assert len(if_stmt.then_statements) == 1
    assert isinstance(if_stmt.then_statements[0], GoToStatementNode)
    assert if_stmt.then_statements[0].target == "PARA-B"


def test_go_to_inside_if_then_and_else_branches_is_parsed() -> None:
    """The real corpus shape (t_goto_spaghetti.cbl's 1000-ENTRY-POINT):
    both branches of an IF end in an unconditional GO TO."""
    program, state = _parse(
        "    IF WS-FLAG = 1\n"
        "        GO TO PARA-B\n"
        "    ELSE\n"
        "        GO TO PARA-C\n"
        "    END-IF.\n"
        "PARA-B.\n    STOP RUN.\n"
        "PARA-C.\n    STOP RUN.\n"
    )
    assert not state.has_errors
    if_stmt = next(s for s in _statements(program) if isinstance(s, IfStatementNode))
    assert isinstance(if_stmt.then_statements[0], GoToStatementNode)
    assert if_stmt.then_statements[0].target == "PARA-B"
    assert isinstance(if_stmt.else_statements[0], GoToStatementNode)
    assert if_stmt.else_statements[0].target == "PARA-C"


def test_statement_after_a_nested_go_to_still_parses() -> None:
    """A statement following the IF/END-IF that contains a GO TO must
    still parse intact -- proving no tokens leak past the nested
    statement's boundary."""
    program, state = _parse(
        "    IF WS-FLAG = 1\n"
        "        GO TO PARA-B\n"
        "    END-IF\n"
        "    ADD 1 TO WS-COUNT.\n"
        "    STOP RUN.\n"
        "PARA-B.\n    STOP RUN.\n"
    )
    assert not state.has_errors
    kinds = [type(s).__name__ for s in _statements(program)]
    assert "AddStatementNode" in kinds


# ===========================================================================
# Multi-target / DEPENDING ON -- not implemented (not in the corpus);
# proven safe rather than assumed.
# ===========================================================================


def test_go_to_depending_on_is_not_silently_narrowed_to_the_first_target() -> None:
    """``GO TO A B DEPENDING ON X`` is not implemented (no such usage
    anywhere in the real corpus). This must not be silently misread as
    a plain ``GO TO A`` (which would fabricate deterministic behavior
    for what is actually a runtime-computed jump); the leftover tokens
    must instead be diagnosed, exactly like any other not-yet-supported
    clause extension in this parser."""
    program, state = _parse(
        "    GO TO PARA-A PARA-B DEPENDING ON WS-CHOICE.\n"
        "    STOP RUN.\n"
        "PARA-A.\n    STOP RUN.\n"
        "PARA-B.\n    STOP RUN.\n"
    )
    assert state.has_errors
    # exactly one GO TO node is still produced, capturing only the first
    # name -- not silently treated as the complete, correct statement.
    gotos = _go_tos(program)
    assert len(gotos) == 1
    assert gotos[0].target == "PARA-A"


# ===========================================================================
# Real corpus: t_goto_spaghetti (the only real GO TO usage among the 45
# sources -- confirmed by direct corpus search, not assumed)
# ===========================================================================


def test_real_goto_spaghetti_every_go_to_is_captured() -> None:
    tokens = CobolLexer().tokenize(
        (SOURCES / "goto_spaghetti.cbl").read_text(encoding="utf-8"),
        filename="goto_spaghetti.cbl",
    )
    program = ProgramParser().parse(tokens)
    gotos = _go_tos(program)
    assert len(gotos) == 7
    assert sorted(g.target for g in gotos) == [
        "2000-STAGE-ALPHA",
        "2000-STAGE-ALPHA",
        "3000-STAGE-BETA",
        "4000-LOOP-BACK",
        "5000-FINAL-STAGE",
        "5000-FINAL-STAGE",
        "5000-FINAL-STAGE",
    ]
