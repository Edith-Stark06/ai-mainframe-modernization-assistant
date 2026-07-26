"""
Unit tests for TASK-035 — Java Arithmetic Generation (ADD, SUBTRACT, MULTIPLY, DIVIDE).

This file extends the TASK-034 test suite (MOVE and DISPLAY) with full coverage
of arithmetic IR instruction translation.

Coverage
--------
_translate_operand()
    string literals, integer literals, decimal literals, negative numbers,
    COBOL identifiers, multi-segment identifiers.

emit_add()
    integer literal operand, decimal literal operand, variable operand,
    mixed (literal result / variable operand), empty result, empty left operand,
    non-empty right operand warning (BE006).

emit_subtract()
    integer literal, decimal literal, variable operand, empty result,
    empty left operand.

emit_multiply()
    integer literal, decimal literal, variable operand, empty result,
    empty left operand.

emit_divide()
    integer literal, decimal literal, variable operand, empty result,
    empty left operand.

emit_statement() dispatcher
    dispatches IRAdd, IRSubtract, IRMultiply, IRDivide correctly;
    unsupported instructions still produce TODO + BE005.

generate() integration — arithmetic statements inside main()
    ADD literal in main, SUBTRACT literal in main, MULTIPLY literal in main,
    DIVIDE literal in main, variable operands in main, mixed arithmetic sequence,
    mixed arithmetic + MOVE + DISPLAY sequence, statement ordering preserved,
    deterministic output, indentation (8 spaces).

Diagnostics
    BE006 for empty result, empty left, and non-empty right fields.
    BE005 for genuinely unsupported instructions.

TASK-034 regression
    All TASK-034 tests (MOVE, DISPLAY, operand translation, ordering,
    determinism, indentation) continue to pass.
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
    emit_add,
    emit_display,
    emit_divide,
    emit_move,
    emit_multiply,
    emit_statement,
    emit_subtract,
)
from app.ir.blocks import IRBasicBlock
from app.ir.instructions import (
    IRAdd,
    IRCall,
    IRDisplay,
    IRDivide,
    IRMove,
    IRMultiply,
    IRReturn,
    IRSubtract,
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


# ===========================================================================
# _translate_operand — TASK-034 regression
# ===========================================================================


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

    def test_negative_decimal(self) -> None:
        assert _translate_operand("-1.5") == "-1.5"

    def test_cobol_identifier_converted(self) -> None:
        assert _translate_operand("WS-GREETING") == "wsGreeting"

    def test_simple_name_lowercased(self) -> None:
        assert _translate_operand("TOTAL") == "total"

    def test_multi_segment_name(self) -> None:
        assert _translate_operand("WS-TOTAL-COUNT") == "wsTotalCount"


# ===========================================================================
# emit_move — TASK-034 regression
# ===========================================================================


class TestEmitMove:
    def test_move_string_literal(self) -> None:
        instr = IRMove(result="WS-GREETING", source='"HELLO"')
        diags: list[BackendDiagnostic] = []
        stmts = emit_move(instr, diags)
        assert stmts == ['wsGreeting = "HELLO";']
        assert diags == []

    def test_move_numeric_literal(self) -> None:
        instr = IRMove(result="WS-COUNT", source="1")
        stmts = emit_move(instr, [])
        assert stmts == ["wsCount = 1;"]

    def test_move_variable_to_variable(self) -> None:
        instr = IRMove(result="WS-B", source="WS-A")
        stmts = emit_move(instr, [])
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
        assert len(emit_move(instr, [])) == 1

    def test_move_ends_with_semicolon(self) -> None:
        instr = IRMove(result="WS-X", source="0")
        assert emit_move(instr, [])[0].endswith(";")

    def test_move_decimal_literal(self) -> None:
        instr = IRMove(result="WS-RATE", source="3.14")
        assert emit_move(instr, []) == ["wsRate = 3.14;"]


# ===========================================================================
# emit_display — TASK-034 regression
# ===========================================================================


class TestEmitDisplay:
    def test_display_string_literal(self) -> None:
        instr = IRDisplay(operand='"HELLO WORLD"')
        diags: list[BackendDiagnostic] = []
        stmts = emit_display(instr, diags)
        assert stmts == ['System.out.println("HELLO WORLD");']
        assert diags == []

    def test_display_variable(self) -> None:
        instr = IRDisplay(operand="WS-GREETING")
        assert emit_display(instr, []) == ["System.out.println(wsGreeting);"]

    def test_display_numeric(self) -> None:
        instr = IRDisplay(operand="42")
        assert emit_display(instr, []) == ["System.out.println(42);"]

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


# ===========================================================================
# emit_add
# ===========================================================================


class TestEmitAdd:
    def test_add_integer_literal(self) -> None:
        instr = IRAdd(result="WS-COUNT", left="5")
        diags: list[BackendDiagnostic] = []
        stmts = emit_add(instr, diags)
        assert stmts == ["wsCount += 5;"]
        assert diags == []

    def test_add_decimal_literal(self) -> None:
        instr = IRAdd(result="WS-RATE", left="1.5")
        assert emit_add(instr, []) == ["wsRate += 1.5;"]

    def test_add_zero_literal(self) -> None:
        instr = IRAdd(result="WS-COUNT", left="0")
        assert emit_add(instr, []) == ["wsCount += 0;"]

    def test_add_negative_literal(self) -> None:
        instr = IRAdd(result="WS-COUNT", left="-3")
        assert emit_add(instr, []) == ["wsCount += -3;"]

    def test_add_variable_operand(self) -> None:
        instr = IRAdd(result="WS-TOTAL", left="WS-VALUE")
        assert emit_add(instr, []) == ["wsTotal += wsValue;"]

    def test_add_multi_segment_variable(self) -> None:
        instr = IRAdd(result="WS-GRAND-TOTAL", left="WS-LINE-ITEM")
        assert emit_add(instr, []) == ["wsGrandTotal += wsLineItem;"]

    def test_add_ends_with_semicolon(self) -> None:
        stmts = emit_add(IRAdd(result="WS-X", left="1"), [])
        assert stmts[0].endswith(";")

    def test_add_uses_plus_equals(self) -> None:
        stmts = emit_add(IRAdd(result="WS-X", left="1"), [])
        assert "+=" in stmts[0]

    def test_add_exactly_one_statement(self) -> None:
        assert len(emit_add(IRAdd(result="WS-X", left="1"), [])) == 1

    def test_add_empty_result_skipped(self) -> None:
        instr = IRAdd(result="", left="5")
        diags: list[BackendDiagnostic] = []
        stmts = emit_add(instr, diags)
        assert stmts == []
        assert any(d.code == "BE006" for d in diags)

    def test_add_empty_result_warning_severity(self) -> None:
        instr = IRAdd(result="", left="5")
        diags: list[BackendDiagnostic] = []
        emit_add(instr, diags)
        assert diags[0].severity is BackendSeverity.WARNING

    def test_add_empty_left_skipped(self) -> None:
        instr = IRAdd(result="WS-COUNT", left="")
        diags: list[BackendDiagnostic] = []
        stmts = emit_add(instr, diags)
        assert stmts == []
        assert any(d.code == "BE006" for d in diags)

    def test_add_empty_left_warning_severity(self) -> None:
        instr = IRAdd(result="WS-COUNT", left="")
        diags: list[BackendDiagnostic] = []
        emit_add(instr, diags)
        assert diags[0].severity is BackendSeverity.WARNING

    def test_add_non_empty_right_emits_be006(self) -> None:
        """right != "" and right != result triggers a BE006 warning."""
        instr = IRAdd(result="WS-TOTAL", left="WS-A", right="WS-B")
        diags: list[BackendDiagnostic] = []
        stmts = emit_add(instr, diags)
        # Statement is still generated (graceful degradation)
        assert stmts == ["wsTotal += wsA;"]
        assert any(d.code == "BE006" for d in diags)

    def test_add_right_equals_result_no_warning(self) -> None:
        """right == result is the self-add form; no warning expected."""
        instr = IRAdd(result="WS-TOTAL", left="WS-A", right="WS-TOTAL")
        diags: list[BackendDiagnostic] = []
        stmts = emit_add(instr, diags)
        assert stmts == ["wsTotal += wsA;"]
        assert not any(d.code == "BE006" for d in diags)


# ===========================================================================
# emit_subtract
# ===========================================================================


class TestEmitSubtract:
    def test_subtract_integer_literal(self) -> None:
        instr = IRSubtract(result="WS-COUNT", left="2")
        diags: list[BackendDiagnostic] = []
        stmts = emit_subtract(instr, diags)
        assert stmts == ["wsCount -= 2;"]
        assert diags == []

    def test_subtract_decimal_literal(self) -> None:
        instr = IRSubtract(result="WS-BALANCE", left="0.5")
        assert emit_subtract(instr, []) == ["wsBalance -= 0.5;"]

    def test_subtract_zero(self) -> None:
        instr = IRSubtract(result="WS-X", left="0")
        assert emit_subtract(instr, []) == ["wsX -= 0;"]

    def test_subtract_variable_operand(self) -> None:
        instr = IRSubtract(result="WS-TOTAL", left="WS-LOSS")
        assert emit_subtract(instr, []) == ["wsTotal -= wsLoss;"]

    def test_subtract_uses_minus_equals(self) -> None:
        stmts = emit_subtract(IRSubtract(result="WS-X", left="1"), [])
        assert "-=" in stmts[0]

    def test_subtract_ends_with_semicolon(self) -> None:
        stmts = emit_subtract(IRSubtract(result="WS-X", left="1"), [])
        assert stmts[0].endswith(";")

    def test_subtract_exactly_one_statement(self) -> None:
        assert len(emit_subtract(IRSubtract(result="WS-X", left="1"), [])) == 1

    def test_subtract_empty_result_skipped(self) -> None:
        instr = IRSubtract(result="", left="2")
        diags: list[BackendDiagnostic] = []
        assert emit_subtract(instr, diags) == []
        assert any(d.code == "BE006" for d in diags)

    def test_subtract_empty_left_skipped(self) -> None:
        instr = IRSubtract(result="WS-COUNT", left="")
        diags: list[BackendDiagnostic] = []
        assert emit_subtract(instr, diags) == []
        assert any(d.code == "BE006" for d in diags)

    def test_subtract_multi_segment_variable(self) -> None:
        instr = IRSubtract(result="WS-NET-TOTAL", left="WS-TAX-AMOUNT")
        assert emit_subtract(instr, []) == ["wsNetTotal -= wsTaxAmount;"]


# ===========================================================================
# emit_multiply
# ===========================================================================


class TestEmitMultiply:
    def test_multiply_integer_literal(self) -> None:
        instr = IRMultiply(result="WS-COUNT", left="2")
        diags: list[BackendDiagnostic] = []
        stmts = emit_multiply(instr, diags)
        assert stmts == ["wsCount *= 2;"]
        assert diags == []

    def test_multiply_decimal_literal(self) -> None:
        instr = IRMultiply(result="WS-AMOUNT", left="1.1")
        assert emit_multiply(instr, []) == ["wsAmount *= 1.1;"]

    def test_multiply_variable_operand(self) -> None:
        instr = IRMultiply(result="WS-TOTAL", left="WS-RATE")
        assert emit_multiply(instr, []) == ["wsTotal *= wsRate;"]

    def test_multiply_uses_star_equals(self) -> None:
        stmts = emit_multiply(IRMultiply(result="WS-X", left="3"), [])
        assert "*=" in stmts[0]

    def test_multiply_ends_with_semicolon(self) -> None:
        stmts = emit_multiply(IRMultiply(result="WS-X", left="3"), [])
        assert stmts[0].endswith(";")

    def test_multiply_exactly_one_statement(self) -> None:
        assert len(emit_multiply(IRMultiply(result="WS-X", left="3"), [])) == 1

    def test_multiply_empty_result_skipped(self) -> None:
        instr = IRMultiply(result="", left="2")
        diags: list[BackendDiagnostic] = []
        assert emit_multiply(instr, diags) == []
        assert any(d.code == "BE006" for d in diags)

    def test_multiply_empty_left_skipped(self) -> None:
        instr = IRMultiply(result="WS-COUNT", left="")
        diags: list[BackendDiagnostic] = []
        assert emit_multiply(instr, diags) == []
        assert any(d.code == "BE006" for d in diags)

    def test_multiply_multi_segment_variable(self) -> None:
        instr = IRMultiply(result="WS-GROSS-PAY", left="WS-HOURS-WORKED")
        assert emit_multiply(instr, []) == ["wsGrossPay *= wsHoursWorked;"]


# ===========================================================================
# emit_divide
# ===========================================================================


class TestEmitDivide:
    def test_divide_integer_literal(self) -> None:
        instr = IRDivide(result="WS-TOTAL", left="2")
        diags: list[BackendDiagnostic] = []
        stmts = emit_divide(instr, diags)
        assert stmts == ["wsTotal /= 2;"]
        assert diags == []

    def test_divide_decimal_literal(self) -> None:
        instr = IRDivide(result="WS-AMOUNT", left="3.14")
        assert emit_divide(instr, []) == ["wsAmount /= 3.14;"]

    def test_divide_variable_operand(self) -> None:
        instr = IRDivide(result="WS-QUOTIENT", left="WS-DIVISOR")
        assert emit_divide(instr, []) == ["wsQuotient /= wsDivisor;"]

    def test_divide_uses_slash_equals(self) -> None:
        stmts = emit_divide(IRDivide(result="WS-X", left="4"), [])
        assert "/=" in stmts[0]

    def test_divide_ends_with_semicolon(self) -> None:
        stmts = emit_divide(IRDivide(result="WS-X", left="4"), [])
        assert stmts[0].endswith(";")

    def test_divide_exactly_one_statement(self) -> None:
        assert len(emit_divide(IRDivide(result="WS-X", left="4"), [])) == 1

    def test_divide_empty_result_skipped(self) -> None:
        instr = IRDivide(result="", left="2")
        diags: list[BackendDiagnostic] = []
        assert emit_divide(instr, diags) == []
        assert any(d.code == "BE006" for d in diags)

    def test_divide_empty_left_skipped(self) -> None:
        instr = IRDivide(result="WS-TOTAL", left="")
        diags: list[BackendDiagnostic] = []
        assert emit_divide(instr, diags) == []
        assert any(d.code == "BE006" for d in diags)

    def test_divide_multi_segment_variable(self) -> None:
        instr = IRDivide(result="WS-AVG-SCORE", left="WS-NUM-ITEMS")
        assert emit_divide(instr, []) == ["wsAvgScore /= wsNumItems;"]


# ===========================================================================
# emit_statement() dispatcher
# ===========================================================================


class TestEmitStatement:
    # TASK-034 regression: MOVE / DISPLAY
    def test_dispatches_move(self) -> None:
        instr = IRMove(result="WS-X", source='"VAL"')
        assert 'wsX = "VAL";' in emit_statement(instr, [])

    def test_dispatches_display(self) -> None:
        instr = IRDisplay(operand='"HELLO"')
        assert 'System.out.println("HELLO");' in emit_statement(instr, [])

    # Arithmetic dispatchers
    def test_dispatches_add(self) -> None:
        instr = IRAdd(result="WS-COUNT", left="5")
        stmts = emit_statement(instr, [])
        assert stmts == ["wsCount += 5;"]

    def test_dispatches_subtract(self) -> None:
        instr = IRSubtract(result="WS-COUNT", left="2")
        stmts = emit_statement(instr, [])
        assert stmts == ["wsCount -= 2;"]

    def test_dispatches_multiply(self) -> None:
        instr = IRMultiply(result="WS-COUNT", left="3")
        stmts = emit_statement(instr, [])
        assert stmts == ["wsCount *= 3;"]

    def test_dispatches_divide(self) -> None:
        instr = IRDivide(result="WS-TOTAL", left="4")
        stmts = emit_statement(instr, [])
        assert stmts == ["wsTotal /= 4;"]

    # Unsupported instructions still produce TODO + BE005
    def test_unsupported_produces_todo_comment(self) -> None:
        instr = IRCall(target="PROC")
        stmts = emit_statement(instr, [])
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


# ===========================================================================
# generate() integration — arithmetic statements inside main()
# ===========================================================================


class TestGenerateArithmetic:
    def test_add_literal_in_main(self) -> None:
        prog = _make_program(IRAdd(result="WS-COUNT", left="5"))
        src = generate(prog)
        assert "wsCount += 5;" in src

    def test_add_variable_in_main(self) -> None:
        prog = _make_program(IRAdd(result="WS-TOTAL", left="WS-VALUE"))
        src = generate(prog)
        assert "wsTotal += wsValue;" in src

    def test_subtract_literal_in_main(self) -> None:
        prog = _make_program(IRSubtract(result="WS-COUNT", left="2"))
        src = generate(prog)
        assert "wsCount -= 2;" in src

    def test_subtract_variable_in_main(self) -> None:
        prog = _make_program(IRSubtract(result="WS-TOTAL", left="WS-LOSS"))
        src = generate(prog)
        assert "wsTotal -= wsLoss;" in src

    def test_multiply_literal_in_main(self) -> None:
        prog = _make_program(IRMultiply(result="WS-COUNT", left="2"))
        src = generate(prog)
        assert "wsCount *= 2;" in src

    def test_multiply_variable_in_main(self) -> None:
        prog = _make_program(IRMultiply(result="WS-TOTAL", left="WS-RATE"))
        src = generate(prog)
        assert "wsTotal *= wsRate;" in src

    def test_divide_literal_in_main(self) -> None:
        prog = _make_program(IRDivide(result="WS-TOTAL", left="2"))
        src = generate(prog)
        assert "wsTotal /= 2;" in src

    def test_divide_variable_in_main(self) -> None:
        prog = _make_program(IRDivide(result="WS-QUOTIENT", left="WS-DIVISOR"))
        src = generate(prog)
        assert "wsQuotient /= wsDivisor;" in src

    def test_decimal_add_in_main(self) -> None:
        prog = _make_program(IRAdd(result="WS-RATE", left="0.5"))
        src = generate(prog)
        assert "wsRate += 0.5;" in src

    def test_arithmetic_inside_main_braces(self) -> None:
        prog = _make_program(IRAdd(result="WS-COUNT", left="1"))
        src = generate(prog)
        main_start = src.index("public static void main")
        stmt_pos = src.index("wsCount += 1")
        assert stmt_pos > main_start

    def test_arithmetic_indented_8_spaces(self) -> None:
        prog = _make_program(IRAdd(result="WS-COUNT", left="1"))
        src = generate(prog)
        for line in src.splitlines():
            if "wsCount +=" in line:
                assert line.startswith("        ")
                break

    def test_mixed_arithmetic_sequence(self) -> None:
        prog = _make_program(
            IRAdd(result="WS-X", left="10"),
            IRSubtract(result="WS-X", left="3"),
            IRMultiply(result="WS-X", left="2"),
            IRDivide(result="WS-X", left="4"),
        )
        src = generate(prog)
        assert "wsX += 10;" in src
        assert "wsX -= 3;" in src
        assert "wsX *= 2;" in src
        assert "wsX /= 4;" in src

    def test_mixed_arithmetic_ordering(self) -> None:
        prog = _make_program(
            IRAdd(result="WS-X", left="10"),
            IRSubtract(result="WS-X", left="3"),
            IRMultiply(result="WS-X", left="2"),
            IRDivide(result="WS-X", left="4"),
        )
        src = generate(prog)
        idx_add = src.index("wsX += 10")
        idx_sub = src.index("wsX -= 3")
        idx_mul = src.index("wsX *= 2")
        idx_div = src.index("wsX /= 4")
        assert idx_add < idx_sub < idx_mul < idx_div

    def test_mixed_move_add_display_subtract_display_ordering(self) -> None:
        """TASK-035 spec: MOVE, ADD, DISPLAY, SUBTRACT, DISPLAY must preserve order."""
        prog = _make_program(
            IRMove(result="WS-A", source="0"),
            IRAdd(result="WS-A", left="5"),
            IRDisplay(operand="WS-A"),
            IRSubtract(result="WS-A", left="2"),
            IRDisplay(operand="WS-A"),
        )
        src = generate(prog)
        idx_move = src.index("wsA = 0")
        idx_add = src.index("wsA += 5")
        idx_disp1 = src.index("System.out.println(wsA)")
        # After first println there will be another -= then another println
        idx_sub = src.index("wsA -= 2")
        idx_disp2 = src.rindex("System.out.println(wsA)")
        assert idx_move < idx_add < idx_disp1 < idx_sub < idx_disp2

    def test_deterministic_arithmetic_output(self) -> None:
        prog = _make_program(
            IRAdd(result="WS-TOTAL", left="WS-VALUE"),
            IRSubtract(result="WS-TOTAL", left="3"),
            IRMultiply(result="WS-TOTAL", left="WS-RATE"),
            IRDivide(result="WS-TOTAL", left="4"),
        )
        assert generate(prog) == generate(prog)

    def test_deterministic_no_timestamps(self) -> None:
        prog = _make_program(IRAdd(result="WS-COUNT", left="1"))
        src = generate(prog)
        # Determinism checks: no known non-deterministic markers
        assert "timestamp" not in src.lower()
        assert "uuid" not in src.lower()

    def test_arithmetic_with_display_no_ir_comments(self) -> None:
        prog = _make_program(
            IRAdd(result="WS-COUNT", left="1"),
            IRDisplay(operand="WS-COUNT"),
        )
        src = generate(prog)
        assert "// IR:" not in src

    def test_all_four_operations_have_correct_operators(self) -> None:
        prog = _make_program(
            IRAdd(result="WS-X", left="1"),
            IRSubtract(result="WS-X", left="1"),
            IRMultiply(result="WS-X", left="1"),
            IRDivide(result="WS-X", left="1"),
        )
        src = generate(prog)
        assert "+=" in src
        assert "-=" in src
        assert "*=" in src
        assert "/=" in src


# ===========================================================================
# Diagnostic coverage
# ===========================================================================


class TestArithmeticDiagnostics:
    def test_add_empty_result_produces_be006(self) -> None:
        prog = _make_program(IRAdd(result="", left="5"))
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE006" for d in result.diagnostics)

    def test_add_empty_left_produces_be006(self) -> None:
        prog = _make_program(IRAdd(result="WS-COUNT", left=""))
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE006" for d in result.diagnostics)

    def test_subtract_empty_result_produces_be006(self) -> None:
        prog = _make_program(IRSubtract(result="", left="2"))
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE006" for d in result.diagnostics)

    def test_subtract_empty_left_produces_be006(self) -> None:
        prog = _make_program(IRSubtract(result="WS-COUNT", left=""))
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE006" for d in result.diagnostics)

    def test_multiply_empty_result_produces_be006(self) -> None:
        prog = _make_program(IRMultiply(result="", left="2"))
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE006" for d in result.diagnostics)

    def test_multiply_empty_left_produces_be006(self) -> None:
        prog = _make_program(IRMultiply(result="WS-COUNT", left=""))
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE006" for d in result.diagnostics)

    def test_divide_empty_result_produces_be006(self) -> None:
        prog = _make_program(IRDivide(result="", left="2"))
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE006" for d in result.diagnostics)

    def test_divide_empty_left_produces_be006(self) -> None:
        prog = _make_program(IRDivide(result="WS-TOTAL", left=""))
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE006" for d in result.diagnostics)

    def test_add_right_differs_from_result_produces_be006(self) -> None:
        prog = _make_program(IRAdd(result="WS-TOTAL", left="WS-A", right="WS-B"))
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE006" for d in result.diagnostics)

    def test_all_be006_severity_warning(self) -> None:
        prog = _make_program(
            IRAdd(result="", left="1"),
            IRSubtract(result="", left="1"),
            IRMultiply(result="", left="1"),
            IRDivide(result="", left="1"),
        )
        result = generate_with_diagnostics(prog)
        be006 = [d for d in result.diagnostics if d.code == "BE006"]
        assert len(be006) == 4
        for d in be006:
            assert d.severity is BackendSeverity.WARNING

    def test_generation_continues_after_be006(self) -> None:
        """Malformed instructions must not prevent subsequent statements from being emitted."""
        prog = _make_program(
            IRAdd(result="", left="5"),  # bad — no result
            IRAdd(result="WS-COUNT", left="10"),  # good
        )
        src = generate(prog)
        assert "wsCount += 10;" in src

    def test_generate_with_diagnostics_be005_still_works(self) -> None:
        prog = _make_program(IRReturn())
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE005" for d in result.diagnostics)


# ===========================================================================
# generate() integration — TASK-034 regression
# ===========================================================================


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
        prog = _make_program(IRCall(target="PROC"))
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
