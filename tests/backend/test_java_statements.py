"""
Unit tests for TASK-034 — Java Statement Generation (MOVE and DISPLAY).

Coverage:
    - _translate_operand(): string literals, numeric literals, COBOL identifiers.
    - emit_move(): string literal, numeric literal, variable-to-variable,
      empty target, empty source.
    - emit_display(): string literal, numeric literal, variable, empty operand.
    - emit_statement(): dispatch for IRMove, IRDisplay, unsupported instructions.
    - generate() with IR instructions: MOVE, DISPLAY, mixed ordering.
    - Statement ordering preserved from IR.
    - Deterministic output.
    - BE004 / BE005 diagnostics.
"""

from __future__ import annotations


from app.backend.java.generator import (
    BackendDiagnostic,
    BackendSeverity,
    generate,
    generate_with_diagnostics,
)
from app.backend.java.statement_emitter import (
    _translate_operand,
    emit_display,
    emit_move,
    emit_statement,
)
from app.ir.blocks import IRBasicBlock
from app.ir.instructions import (
    IRAdd,
    IRCall,
    IRDisplay,
    IRMove,
    IRReturn,
)
from app.ir.program import IRFunction, IRModule, IRProgram

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_program(*instructions) -> IRProgram:
    block = IRBasicBlock(label="entry", instructions=instructions)
    func = IRFunction(name="__entry__", blocks=(block,))
    module = IRModule(name="TEST", functions=(func,))
    return IRProgram(name="TEST", modules=(module,))


# ---------------------------------------------------------------------------
# _translate_operand
# ---------------------------------------------------------------------------


class TestTranslateOperand:
    def test_quoted_string_returned_as_is(self) -> None:
        assert _translate_operand('"HELLO"') == '"HELLO"'

    def test_quoted_string_with_spaces(self) -> None:
        assert _translate_operand('"HELLO WORLD"') == '"HELLO WORLD"'

    def test_empty_quoted_string(self) -> None:
        assert _translate_operand('""') == '""'

    def test_integer_literal_returned_as_is(self) -> None:
        assert _translate_operand("42") == "42"

    def test_zero_literal(self) -> None:
        assert _translate_operand("0") == "0"

    def test_negative_integer(self) -> None:
        assert _translate_operand("-5") == "-5"

    def test_decimal_literal(self) -> None:
        assert _translate_operand("3.14") == "3.14"

    def test_cobol_identifier_converted(self) -> None:
        assert _translate_operand("WS-GREETING") == "wsGreeting"

    def test_simple_name_lowercased(self) -> None:
        assert _translate_operand("TOTAL") == "total"

    def test_multi_segment_name(self) -> None:
        assert _translate_operand("WS-TOTAL-COUNT") == "wsTotalCount"


# ---------------------------------------------------------------------------
# emit_move()
# ---------------------------------------------------------------------------


class TestEmitMove:
    def test_move_string_literal(self) -> None:
        instr = IRMove(result="WS-GREETING", source='"HELLO"')
        diags: list[BackendDiagnostic] = []
        stmts = emit_move(instr, diags)
        assert stmts == ['wsGreeting = "HELLO";']
        assert diags == []

    def test_move_numeric_literal(self) -> None:
        instr = IRMove(result="WS-COUNT", source="1")
        diags: list[BackendDiagnostic] = []
        stmts = emit_move(instr, diags)
        assert stmts == ["wsCount = 1;"]

    def test_move_variable_to_variable(self) -> None:
        instr = IRMove(result="WS-B", source="WS-A")
        diags: list[BackendDiagnostic] = []
        stmts = emit_move(instr, diags)
        assert stmts == ["wsB = wsA;"]

    def test_move_empty_target_skipped(self) -> None:
        instr = IRMove(result="", source="WS-A")
        diags: list[BackendDiagnostic] = []
        stmts = emit_move(instr, diags)
        assert stmts == []
        assert any(d.code == "BE004" for d in diags)

    def test_move_empty_source_skipped(self) -> None:
        instr = IRMove(result="WS-B", source="")
        diags: list[BackendDiagnostic] = []
        stmts = emit_move(instr, diags)
        assert stmts == []
        assert any(d.code == "BE004" for d in diags)

    def test_move_empty_source_warning_severity(self) -> None:
        instr = IRMove(result="WS-B", source="")
        diags: list[BackendDiagnostic] = []
        emit_move(instr, diags)
        assert diags[0].severity is BackendSeverity.WARNING

    def test_move_result_one_statement(self) -> None:
        instr = IRMove(result="WS-X", source="0")
        stmts = emit_move(instr, [])
        assert len(stmts) == 1

    def test_move_ends_with_semicolon(self) -> None:
        instr = IRMove(result="WS-X", source="0")
        stmts = emit_move(instr, [])
        assert stmts[0].endswith(";")

    def test_move_decimal_literal(self) -> None:
        instr = IRMove(result="WS-RATE", source="3.14")
        stmts = emit_move(instr, [])
        assert stmts == ["wsRate = 3.14;"]


# ---------------------------------------------------------------------------
# emit_display()
# ---------------------------------------------------------------------------


class TestEmitDisplay:
    def test_display_string_literal(self) -> None:
        instr = IRDisplay(operand='"HELLO WORLD"')
        diags: list[BackendDiagnostic] = []
        stmts = emit_display(instr, diags)
        assert stmts == ['System.out.println("HELLO WORLD");']
        assert diags == []

    def test_display_variable(self) -> None:
        instr = IRDisplay(operand="WS-GREETING")
        stmts = emit_display(instr, [])
        assert stmts == ["System.out.println(wsGreeting);"]

    def test_display_numeric(self) -> None:
        instr = IRDisplay(operand="42")
        stmts = emit_display(instr, [])
        assert stmts == ["System.out.println(42);"]

    def test_display_empty_operand_skipped(self) -> None:
        instr = IRDisplay(operand="")
        diags: list[BackendDiagnostic] = []
        stmts = emit_display(instr, diags)
        assert stmts == []
        assert any(d.code == "BE004" for d in diags)

    def test_display_result_one_statement(self) -> None:
        instr = IRDisplay(operand='"HI"')
        assert len(emit_display(instr, [])) == 1

    def test_display_ends_with_semicolon(self) -> None:
        instr = IRDisplay(operand='"X"')
        assert emit_display(instr, [])[0].endswith(";")

    def test_display_contains_println(self) -> None:
        instr = IRDisplay(operand='"MSG"')
        assert "System.out.println" in emit_display(instr, [])[0]


# ---------------------------------------------------------------------------
# emit_statement() dispatcher
# ---------------------------------------------------------------------------


class TestEmitStatement:
    def test_dispatches_move(self) -> None:
        instr = IRMove(result="WS-X", source='"VAL"')
        stmts = emit_statement(instr, [])
        assert 'wsX = "VAL";' in stmts

    def test_dispatches_display(self) -> None:
        instr = IRDisplay(operand='"HELLO"')
        stmts = emit_statement(instr, [])
        assert 'System.out.println("HELLO");' in stmts

    def test_unsupported_produces_todo_comment(self) -> None:
        instr = IRAdd(result="WS-X", left="WS-A", right="WS-B")
        diags: list[BackendDiagnostic] = []
        stmts = emit_statement(instr, diags)
        assert any("TODO" in s for s in stmts)

    def test_unsupported_produces_be005(self) -> None:
        instr = IRCall(target="PROC")
        diags: list[BackendDiagnostic] = []
        emit_statement(instr, diags)
        assert any(d.code == "BE005" for d in diags)

    def test_unsupported_be005_warning(self) -> None:
        instr = IRReturn()
        diags: list[BackendDiagnostic] = []
        emit_statement(instr, diags)
        assert diags[0].severity is BackendSeverity.WARNING


# ---------------------------------------------------------------------------
# generate() integration — statements inside main()
# ---------------------------------------------------------------------------


class TestGenerateStatements:
    def test_display_string_in_main(self) -> None:
        prog = _make_program(IRDisplay(operand='"HELLO"'))
        src = generate(prog)
        assert 'System.out.println("HELLO");' in src

    def test_display_variable_in_main(self) -> None:
        prog = _make_program(IRDisplay(operand="WS-GREETING"))
        src = generate(prog)
        assert "System.out.println(wsGreeting);" in src

    def test_move_string_in_main(self) -> None:
        prog = _make_program(IRMove(result="WS-GREETING", source='"WELCOME"'))
        src = generate(prog)
        assert 'wsGreeting = "WELCOME";' in src

    def test_move_numeric_in_main(self) -> None:
        prog = _make_program(IRMove(result="WS-COUNT", source="1"))
        src = generate(prog)
        assert "wsCount = 1;" in src

    def test_move_var_to_var_in_main(self) -> None:
        prog = _make_program(IRMove(result="WS-B", source="WS-A"))
        src = generate(prog)
        assert "wsB = wsA;" in src

    def test_statements_inside_main_braces(self) -> None:
        prog = _make_program(IRDisplay(operand='"HI"'))
        src = generate(prog)
        main_start = src.index("public static void main")
        stmt_pos = src.index("System.out.println")
        assert stmt_pos > main_start

    def test_statement_ordering_preserved(self) -> None:
        prog = _make_program(
            IRMove(result="WS-A", source='"FIRST"'),
            IRDisplay(operand="WS-A"),
            IRMove(result="WS-B", source="2"),
            IRDisplay(operand="WS-B"),
        )
        src = generate(prog)
        idx_assign1 = src.index('wsA = "FIRST"')
        idx_print1 = src.index("System.out.println(wsA)")
        idx_assign2 = src.index("wsB = 2")
        idx_print2 = src.index("System.out.println(wsB)")
        assert idx_assign1 < idx_print1 < idx_assign2 < idx_print2

    def test_multiple_display_ordered(self) -> None:
        prog = _make_program(
            IRDisplay(operand='"A"'),
            IRDisplay(operand='"B"'),
            IRDisplay(operand='"C"'),
        )
        src = generate(prog)
        assert src.index('"A"') < src.index('"B"') < src.index('"C"')

    def test_deterministic_with_statements(self) -> None:
        prog = _make_program(
            IRMove(result="WS-X", source='"VAL"'),
            IRDisplay(operand="WS-X"),
        )
        assert generate(prog) == generate(prog)

    def test_no_ir_comments_in_statements(self) -> None:
        prog = _make_program(IRDisplay(operand='"HI"'))
        src = generate(prog)
        assert "// IR:" not in src

    def test_unsupported_ir_produces_todo(self) -> None:
        prog = _make_program(IRAdd(result="X", left="A", right="B"))
        src = generate(prog)
        assert "// TODO:" in src

    def test_generate_with_diagnostics_be005(self) -> None:
        prog = _make_program(IRReturn())
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE005" for d in result.diagnostics)

    def test_empty_program_no_statements(self) -> None:
        prog = IRProgram(name="EMPTY")
        src = generate(prog)
        assert "System.out.println" not in src
        assert "= " not in src

    def test_statements_indented_8_spaces(self) -> None:
        prog = _make_program(IRDisplay(operand='"X"'))
        src = generate(prog)
        for line in src.splitlines():
            if "System.out.println" in line:
                assert line.startswith("        ")
                break
