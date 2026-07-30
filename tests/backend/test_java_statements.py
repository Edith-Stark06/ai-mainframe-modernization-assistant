"""
Unit tests for TASK-034/035/036 — Java Statement Generation.

TASK-034: MOVE, DISPLAY, operand translation.
TASK-035: ADD, SUBTRACT, MULTIPLY, DIVIDE arithmetic.
TASK-036: IF, ELSE, END-IF control flow with nesting and diagnostics.

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

from app.backend.java.control_flow_emitter import (
    SUPPORTED_OPERATORS,
    emit_else,
    emit_end_if,
    emit_end_perform,
    emit_if,
    emit_perform_until,
)
from app.backend.java.generator import (
    BackendDiagnostic,
    BackendSeverity,
    generate,
    generate_with_diagnostics,
)
from app.backend.java.statement_emitter import (
    _translate_operand,
    emit_add,
    emit_call,
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
    IRElse,
    IREndIf,
    IREndPerform,
    IRIf,
    IRJump,
    IRMove,
    IRMultiply,
    IRPerformUntil,
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
        instr = IRJump(target="PROC")
        stmts = emit_statement(instr, [])
        assert any("TODO" in s for s in stmts)

    def test_unsupported_produces_be005(self) -> None:
        instr = IRJump(target="PROC")
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
        prog = _make_program(IRJump(target="PROC"))
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


# ===========================================================================
# TASK-036 — Control Flow: emit_if / emit_else / emit_end_if
# ===========================================================================


class TestSupportedOperators:
    def test_all_six_operators_present(self) -> None:
        assert SUPPORTED_OPERATORS == {"==", "!=", ">", ">=", "<", "<="}

    def test_operators_is_frozenset(self) -> None:
        assert isinstance(SUPPORTED_OPERATORS, frozenset)


class TestEmitIf:
    # --- valid conditions at depth 0 ---
    def test_if_greater_than_literal(self) -> None:
        instr = IRIf(left="WS-COUNT", operator=">", right="0")
        assert emit_if(instr, 0, []) == ["if (wsCount > 0) {"]

    def test_if_less_than_literal(self) -> None:
        instr = IRIf(left="WS-X", operator="<", right="10")
        assert emit_if(instr, 0, []) == ["if (wsX < 10) {"]

    def test_if_equals_literal(self) -> None:
        instr = IRIf(left="WS-STATUS", operator="==", right="1")
        assert emit_if(instr, 0, []) == ["if (wsStatus == 1) {"]

    def test_if_not_equals_literal(self) -> None:
        instr = IRIf(left="WS-FLAG", operator="!=", right="0")
        assert emit_if(instr, 0, []) == ["if (wsFlag != 0) {"]

    def test_if_greater_equal_literal(self) -> None:
        instr = IRIf(left="WS-AGE", operator=">=", right="18")
        assert emit_if(instr, 0, []) == ["if (wsAge >= 18) {"]

    def test_if_less_equal_literal(self) -> None:
        instr = IRIf(left="WS-SCORE", operator="<=", right="100")
        assert emit_if(instr, 0, []) == ["if (wsScore <= 100) {"]

    def test_if_variable_vs_variable(self) -> None:
        instr = IRIf(left="WS-A", operator="==", right="WS-B")
        assert emit_if(instr, 0, []) == ["if (wsA == wsB) {"]

    def test_if_decimal_literal(self) -> None:
        instr = IRIf(left="WS-RATE", operator=">", right="0.5")
        assert emit_if(instr, 0, []) == ["if (wsRate > 0.5) {"]

    def test_if_negative_literal(self) -> None:
        instr = IRIf(left="WS-TEMP", operator="<", right="-1")
        assert emit_if(instr, 0, []) == ["if (wsTemp < -1) {"]

    def test_if_quoted_string(self) -> None:
        instr = IRIf(left="WS-CODE", operator="==", right='"Y"')
        assert emit_if(instr, 0, []) == ['if (wsCode == "Y") {']

    def test_if_multi_segment_variable(self) -> None:
        instr = IRIf(left="WS-GRAND-TOTAL", operator=">", right="0")
        assert emit_if(instr, 0, []) == ["if (wsGrandTotal > 0) {"]

    # --- depth-based indentation ---
    def test_if_depth_0_no_prefix(self) -> None:
        instr = IRIf(left="WS-X", operator=">", right="0")
        stmts = emit_if(instr, 0, [])
        assert not stmts[0].startswith(" ")

    def test_if_depth_1_four_space_prefix(self) -> None:
        instr = IRIf(left="WS-X", operator=">", right="0")
        stmts = emit_if(instr, 1, [])
        assert stmts[0].startswith("    ")
        assert not stmts[0].startswith("        ")

    def test_if_depth_2_eight_space_prefix(self) -> None:
        instr = IRIf(left="WS-X", operator=">", right="0")
        stmts = emit_if(instr, 2, [])
        assert stmts[0].startswith("        ")

    def test_if_exactly_one_statement(self) -> None:
        instr = IRIf(left="WS-X", operator=">", right="0")
        assert len(emit_if(instr, 0, [])) == 1

    def test_if_ends_with_open_brace(self) -> None:
        instr = IRIf(left="WS-X", operator=">", right="0")
        assert emit_if(instr, 0, [])[0].endswith("{")

    def test_if_contains_if_keyword(self) -> None:
        instr = IRIf(left="WS-X", operator=">", right="0")
        assert emit_if(instr, 0, [])[0].startswith("if ")

    # --- diagnostics ---
    def test_if_empty_left_skipped(self) -> None:
        instr = IRIf(left="", operator=">", right="0")
        diags: list[BackendDiagnostic] = []
        assert emit_if(instr, 0, diags) == []
        assert any(d.code == "BE007" for d in diags)

    def test_if_empty_right_skipped(self) -> None:
        instr = IRIf(left="WS-X", operator=">", right="")
        diags: list[BackendDiagnostic] = []
        assert emit_if(instr, 0, diags) == []
        assert any(d.code == "BE007" for d in diags)

    def test_if_unsupported_operator_skipped(self) -> None:
        instr = IRIf(left="WS-X", operator="GREATER", right="0")
        diags: list[BackendDiagnostic] = []
        assert emit_if(instr, 0, diags) == []
        assert any(d.code == "BE007" for d in diags)

    def test_if_empty_operator_skipped(self) -> None:
        instr = IRIf(left="WS-X", operator="", right="0")
        diags: list[BackendDiagnostic] = []
        assert emit_if(instr, 0, diags) == []
        assert any(d.code == "BE007" for d in diags)

    def test_if_be007_severity_warning(self) -> None:
        instr = IRIf(left="", operator=">", right="0")
        diags: list[BackendDiagnostic] = []
        emit_if(instr, 0, diags)
        assert diags[0].severity is BackendSeverity.WARNING


class TestEmitElse:
    def test_else_depth_0_format(self) -> None:
        assert emit_else(0, []) == ["}  else {"[0:0] + "} else {"]

    def test_else_depth_0_exact(self) -> None:
        assert emit_else(0, []) == [") else {"[0:0] + "} else {"]

    def test_else_exact_string_depth0(self) -> None:
        stmts = emit_else(0, [])
        assert stmts == ["}  else {"[0:0] + "} else {"]

    def test_else_depth_0_simple(self) -> None:
        assert emit_else(0, []) == ["}  else {"[:0] + "} else {"]

    # Use a direct string comparison to avoid confusion:
    def test_else_depth0_value(self) -> None:
        result = emit_else(0, [])
        assert len(result) == 1
        assert result[0] == "} else {"

    def test_else_depth1_value(self) -> None:
        result = emit_else(1, [])
        assert len(result) == 1
        assert result[0] == "    } else {"

    def test_else_depth2_value(self) -> None:
        assert emit_else(2, []) == ["        } else {"]

    def test_else_contains_else_keyword(self) -> None:
        assert "else" in emit_else(0, [])[0]

    def test_else_ends_with_open_brace(self) -> None:
        assert emit_else(0, [])[0].endswith("{")

    def test_else_starts_with_close_brace(self) -> None:
        assert emit_else(0, [])[0].startswith("}")

    def test_else_exactly_one_statement(self) -> None:
        assert len(emit_else(0, [])) == 1


class TestEmitEndIf:
    def test_end_if_depth0_value(self) -> None:
        assert emit_end_if(0, []) == ["}"]

    def test_end_if_depth1_value(self) -> None:
        assert emit_end_if(1, []) == ["    }"]

    def test_end_if_depth2_value(self) -> None:
        assert emit_end_if(2, []) == ["        }"]

    def test_end_if_is_just_brace_at_depth0(self) -> None:
        assert emit_end_if(0, [])[0] == "}"

    def test_end_if_exactly_one_statement(self) -> None:
        assert len(emit_end_if(0, [])) == 1


class TestEmitStatementControlFlow:
    """emit_statement dispatcher routes control-flow instructions at depth=0."""

    def test_dispatches_ir_if(self) -> None:
        instr = IRIf(left="WS-COUNT", operator=">", right="0")
        stmts = emit_statement(instr, [])
        assert stmts == ["if (wsCount > 0) {"]

    def test_dispatches_ir_if_with_depth(self) -> None:
        instr = IRIf(left="WS-COUNT", operator=">", right="0")
        stmts = emit_statement(instr, [], depth=1)
        assert stmts == ["    if (wsCount > 0) {"]

    def test_dispatches_ir_else_depth0(self) -> None:
        stmts = emit_statement(IRElse(), [])
        assert stmts == ["}  else {"[:0] + "} else {"]

    def test_dispatches_ir_else_exact(self) -> None:
        stmts = emit_statement(IRElse(), [])
        assert len(stmts) == 1
        assert stmts[0] == "} else {"

    def test_dispatches_ir_end_if(self) -> None:
        stmts = emit_statement(IREndIf(), [])
        assert stmts == ["}"]

    def test_dispatches_ir_end_if_with_depth(self) -> None:
        stmts = emit_statement(IREndIf(), [], depth=2)
        assert stmts == ["        }"]

    def test_ir_if_bad_operator_produces_be007(self) -> None:
        instr = IRIf(left="WS-X", operator="GREATER", right="0")
        diags: list[BackendDiagnostic] = []
        stmts = emit_statement(instr, diags)
        assert stmts == []
        assert any(d.code == "BE007" for d in diags)

    def test_non_cf_instructions_still_produce_be005(self) -> None:
        diags: list[BackendDiagnostic] = []
        emit_statement(IRJump(target="PROC"), diags)
        assert any(d.code == "BE005" for d in diags)


class TestGenerateControlFlow:
    """Integration tests: generate() produces correct Java for control-flow IR."""

    # --- simple IF ---
    def test_simple_if_in_main(self) -> None:
        prog = _make_program(
            IRIf(left="WS-COUNT", operator=">", right="0"),
            IRDisplay(operand='"POSITIVE"'),
            IREndIf(),
        )
        src = generate(prog)
        assert "if (wsCount > 0) {" in src
        assert 'System.out.println("POSITIVE");' in src
        assert "}" in src

    def test_simple_if_header_position_before_body(self) -> None:
        prog = _make_program(
            IRIf(left="WS-COUNT", operator=">", right="0"),
            IRDisplay(operand='"POS"'),
            IREndIf(),
        )
        src = generate(prog)
        assert src.index("if (") < src.index("println")

    def test_simple_if_body_before_close_brace(self) -> None:
        prog = _make_program(
            IRIf(left="WS-COUNT", operator=">", right="0"),
            IRDisplay(operand='"POS"'),
            IREndIf(),
        )
        src = generate(prog)
        assert src.index("println") < src.rindex("}")

    # --- all six comparison operators ---
    def test_operator_equals(self) -> None:
        prog = _make_program(IRIf(left="WS-X", operator="==", right="1"), IREndIf())
        assert "if (wsX == 1) {" in generate(prog)

    def test_operator_not_equals(self) -> None:
        prog = _make_program(IRIf(left="WS-X", operator="!=", right="0"), IREndIf())
        assert "if (wsX != 0) {" in generate(prog)

    def test_operator_greater_than(self) -> None:
        prog = _make_program(IRIf(left="WS-X", operator=">", right="5"), IREndIf())
        assert "if (wsX > 5) {" in generate(prog)

    def test_operator_greater_equal(self) -> None:
        prog = _make_program(IRIf(left="WS-X", operator=">=", right="0"), IREndIf())
        assert "if (wsX >= 0) {" in generate(prog)

    def test_operator_less_than(self) -> None:
        prog = _make_program(IRIf(left="WS-X", operator="<", right="100"), IREndIf())
        assert "if (wsX < 100) {" in generate(prog)

    def test_operator_less_equal(self) -> None:
        prog = _make_program(IRIf(left="WS-X", operator="<=", right="99"), IREndIf())
        assert "if (wsX <= 99) {" in generate(prog)

    # --- IF-ELSE ---
    def test_if_else_contains_both_branches(self) -> None:
        prog = _make_program(
            IRIf(left="WS-COUNT", operator=">", right="0"),
            IRDisplay(operand='"POSITIVE"'),
            IRElse(),
            IRDisplay(operand='"NON-POSITIVE"'),
            IREndIf(),
        )
        src = generate(prog)
        assert "if (wsCount > 0) {" in src
        assert "} else {" in src
        assert 'System.out.println("POSITIVE");' in src
        assert 'System.out.println("NON-POSITIVE");' in src

    def test_if_else_ordering(self) -> None:
        prog = _make_program(
            IRIf(left="WS-COUNT", operator=">", right="0"),
            IRDisplay(operand='"POSITIVE"'),
            IRElse(),
            IRDisplay(operand='"NON-POSITIVE"'),
            IREndIf(),
        )
        src = generate(prog)
        idx_if = src.index("if (wsCount")
        idx_pos = src.index('"POSITIVE"')
        idx_else = src.index("} else {")
        idx_neg = src.index('"NON-POSITIVE"')
        idx_end = src.rindex("}")
        assert idx_if < idx_pos < idx_else < idx_neg < idx_end

    # --- nested IF ---
    def test_nested_if_headers_present(self) -> None:
        prog = _make_program(
            IRIf(left="WS-A", operator=">", right="0"),
            IRIf(left="WS-B", operator="<", right="100"),
            IRDisplay(operand='"BOTH"'),
            IREndIf(),
            IREndIf(),
        )
        src = generate(prog)
        assert "if (wsA > 0) {" in src
        assert "if (wsB < 100) {" in src
        assert 'System.out.println("BOTH");' in src

    def test_nested_if_outer_header_before_inner(self) -> None:
        prog = _make_program(
            IRIf(left="WS-A", operator=">", right="0"),
            IRIf(left="WS-B", operator="<", right="100"),
            IRDisplay(operand='"BOTH"'),
            IREndIf(),
            IREndIf(),
        )
        src = generate(prog)
        assert src.index("if (wsA") < src.index("if (wsB")

    def test_nested_if_inner_indented_more(self) -> None:
        prog = _make_program(
            IRIf(left="WS-A", operator=">", right="0"),
            IRIf(left="WS-B", operator="<", right="100"),
            IREndIf(),
            IREndIf(),
        )
        src = generate(prog)
        outer_line = next(ln for ln in src.splitlines() if "if (wsA" in ln)
        inner_line = next(ln for ln in src.splitlines() if "if (wsB" in ln)
        # Inner line should have more leading spaces than outer
        outer_indent = len(outer_line) - len(outer_line.lstrip())
        inner_indent = len(inner_line) - len(inner_line.lstrip())
        assert inner_indent > outer_indent

    def test_nested_if_body_indented_more_than_inner_header(self) -> None:
        prog = _make_program(
            IRIf(left="WS-A", operator=">", right="0"),
            IRIf(left="WS-B", operator="<", right="100"),
            IRDisplay(operand='"BOTH"'),
            IREndIf(),
            IREndIf(),
        )
        src = generate(prog)
        inner_header = next(ln for ln in src.splitlines() if "if (wsB" in ln)
        body_line = next(ln for ln in src.splitlines() if '"BOTH"' in ln)
        inner_indent = len(inner_header) - len(inner_header.lstrip())
        body_indent = len(body_line) - len(body_line.lstrip())
        assert body_indent > inner_indent

    # --- body indentation within if ---
    def test_if_body_indented_more_than_header(self) -> None:
        prog = _make_program(
            IRIf(left="WS-X", operator=">", right="0"),
            IRDisplay(operand='"HI"'),
            IREndIf(),
        )
        src = generate(prog)
        header_line = next(ln for ln in src.splitlines() if "if (wsX" in ln)
        body_line = next(ln for ln in src.splitlines() if '"HI"' in ln)
        header_indent = len(header_line) - len(header_line.lstrip())
        body_indent = len(body_line) - len(body_line.lstrip())
        assert body_indent > header_indent

    def test_if_close_brace_same_indent_as_header(self) -> None:
        prog = _make_program(
            IRIf(left="WS-X", operator=">", right="0"),
            IRDisplay(operand='"HI"'),
            IREndIf(),
        )
        src = generate(prog)
        src_lines = src.splitlines()
        header_idx = next(i for i, ln in enumerate(src_lines) if "if (wsX" in ln)
        header_line = src_lines[header_idx]
        # The IF's closing brace is the first bare "}" after the header (not
        # main()'s or the class's brace, which sit at shallower indents).
        close_line = next(ln for ln in src_lines[header_idx + 1 :] if ln.strip() == "}")
        header_indent = len(header_line) - len(header_line.lstrip())
        close_indent = len(close_line) - len(close_line.lstrip())
        assert close_indent == header_indent

    # --- variable operands in conditions ---
    def test_variable_left_operand_translated(self) -> None:
        prog = _make_program(
            IRIf(left="WS-GRAND-TOTAL", operator=">=", right="0"),
            IREndIf(),
        )
        src = generate(prog)
        assert "wsGrandTotal" in src

    def test_variable_right_operand_translated(self) -> None:
        prog = _make_program(
            IRIf(left="WS-A", operator="==", right="WS-B"),
            IREndIf(),
        )
        src = generate(prog)
        assert "wsA == wsB" in src

    # --- mixed with MOVE, DISPLAY, arithmetic ---
    def test_mixed_move_if_display_end_if(self) -> None:
        prog = _make_program(
            IRMove(result="WS-COUNT", source="5"),
            IRIf(left="WS-COUNT", operator=">", right="0"),
            IRDisplay(operand='"POSITIVE"'),
            IREndIf(),
        )
        src = generate(prog)
        assert "wsCount = 5;" in src
        assert "if (wsCount > 0) {" in src
        assert 'System.out.println("POSITIVE");' in src
        assert "}" in src

    def test_mixed_ordering_move_if_display(self) -> None:
        prog = _make_program(
            IRMove(result="WS-COUNT", source="5"),
            IRIf(left="WS-COUNT", operator=">", right="0"),
            IRDisplay(operand='"POSITIVE"'),
            IREndIf(),
        )
        src = generate(prog)
        assert src.index("wsCount = 5") < src.index("if (wsCount")
        assert src.index("if (wsCount") < src.index("println")

    def test_arithmetic_inside_if_body(self) -> None:
        prog = _make_program(
            IRIf(left="WS-X", operator=">", right="0"),
            IRAdd(result="WS-TOTAL", left="WS-X"),
            IREndIf(),
        )
        src = generate(prog)
        assert "wsTotal += wsX;" in src

    # --- statement order preserved ---
    def test_statement_order_preserved_across_if(self) -> None:
        prog = _make_program(
            IRMove(result="WS-A", source="1"),
            IRIf(left="WS-A", operator=">", right="0"),
            IRMove(result="WS-B", source="2"),
            IREndIf(),
            IRMove(result="WS-C", source="3"),
        )
        src = generate(prog)
        assert (
            src.index("wsA = 1")
            < src.index("if (")
            < src.index("wsB = 2")
            < src.index("wsC = 3")
        )

    # --- deterministic output ---
    def test_deterministic_if_output(self) -> None:
        prog = _make_program(
            IRIf(left="WS-COUNT", operator=">", right="0"),
            IRDisplay(operand='"POSITIVE"'),
            IRElse(),
            IRDisplay(operand='"NEGATIVE"'),
            IREndIf(),
        )
        assert generate(prog) == generate(prog)

    def test_deterministic_nested_if(self) -> None:
        prog = _make_program(
            IRIf(left="WS-A", operator=">", right="0"),
            IRIf(left="WS-B", operator="<", right="100"),
            IRDisplay(operand='"BOTH"'),
            IREndIf(),
            IREndIf(),
        )
        assert generate(prog) == generate(prog)

    def test_no_timestamps_in_cf_output(self) -> None:
        prog = _make_program(
            IRIf(left="WS-X", operator=">", right="0"),
            IREndIf(),
        )
        src = generate(prog)
        assert "timestamp" not in src.lower()


class TestControlFlowDiagnostics:
    """BE007 diagnostics for malformed control-flow instructions."""

    def test_if_empty_left_produces_be007(self) -> None:
        prog = _make_program(IRIf(left="", operator=">", right="0"))
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE007" for d in result.diagnostics)

    def test_if_empty_right_produces_be007(self) -> None:
        prog = _make_program(IRIf(left="WS-X", operator=">", right=""))
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE007" for d in result.diagnostics)

    def test_if_unsupported_operator_produces_be007(self) -> None:
        prog = _make_program(IRIf(left="WS-X", operator="GREATER", right="0"))
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE007" for d in result.diagnostics)

    def test_if_empty_operator_produces_be007(self) -> None:
        prog = _make_program(IRIf(left="WS-X", operator="", right="0"))
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE007" for d in result.diagnostics)

    def test_unmatched_end_if_produces_be007(self) -> None:
        prog = _make_program(IREndIf())
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE007" for d in result.diagnostics)

    def test_unmatched_else_produces_be007(self) -> None:
        prog = _make_program(IRElse())
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE007" for d in result.diagnostics)

    def test_all_be007_severity_warning(self) -> None:
        prog = _make_program(
            IRIf(left="", operator=">", right="0"),
            IRElse(),
            IREndIf(),
        )
        result = generate_with_diagnostics(prog)
        be007 = [d for d in result.diagnostics if d.code == "BE007"]
        assert len(be007) >= 1
        for d in be007:
            assert d.severity is BackendSeverity.WARNING

    def test_generation_continues_after_bad_if(self) -> None:
        """A malformed IRIf must not prevent subsequent instructions from being emitted."""
        prog = _make_program(
            IRIf(left="", operator=">", right="0"),  # bad
            IRDisplay(operand='"AFTER"'),  # should still be emitted
        )
        src = generate(prog)
        assert 'System.out.println("AFTER");' in src

    def test_unmatched_end_if_does_not_emit_brace(self) -> None:
        prog = _make_program(IREndIf())
        result = generate_with_diagnostics(prog)
        brace_count = result.source.count("}")
        # The orphaned } must be skipped: the class has exactly the same closing
        # braces as an empty program (main + run + class), with no extra brace
        # from the unmatched END-IF.
        empty = generate_with_diagnostics(_make_program())
        assert brace_count == empty.source.count("}")

    def test_generation_continues_after_unmatched_end_if(self) -> None:
        prog = _make_program(
            IREndIf(),  # bad
            IRDisplay(operand='"OK"'),
        )
        src = generate(prog)
        assert 'System.out.println("OK");' in src

    def test_be007_does_not_suppress_be005(self) -> None:
        """BE007 and BE005 can coexist in the same diagnostic list."""
        prog = _make_program(
            IRIf(left="", operator=">", right="0"),  # BE007
            IRReturn(),  # BE005
        )
        result = generate_with_diagnostics(prog)
        codes = {d.code for d in result.diagnostics}
        assert "BE007" in codes
        assert "BE005" in codes


# ===========================================================================
# TASK-037 — Control Flow: emit_perform_until / emit_end_perform
# ===========================================================================


class TestEmitPerformUntil:
    def test_perform_greater_than_literal(self) -> None:
        instr = IRPerformUntil(left="WS-COUNT", operator=">", right="0")
        assert emit_perform_until(instr, 0, []) == ["while (!(wsCount > 0)) {"]

    def test_perform_depth_1_prefix(self) -> None:
        instr = IRPerformUntil(left="WS-X", operator="<", right="10")
        assert emit_perform_until(instr, 1, []) == ["    while (!(wsX < 10)) {"]

    def test_perform_empty_left_produces_be007(self) -> None:
        instr = IRPerformUntil(left="", operator=">", right="0")
        diags: list[BackendDiagnostic] = []
        assert emit_perform_until(instr, 0, diags) == []
        assert any(d.code == "BE007" for d in diags)

    def test_perform_unsupported_operator_produces_be007(self) -> None:
        instr = IRPerformUntil(left="WS-X", operator="GREATER", right="0")
        diags: list[BackendDiagnostic] = []
        assert emit_perform_until(instr, 0, diags) == []
        assert any(d.code == "BE007" for d in diags)


class TestEmitEndPerform:
    def test_end_perform_depth0_value(self) -> None:
        assert emit_end_perform(0, []) == ["}"]

    def test_end_perform_depth1_value(self) -> None:
        assert emit_end_perform(1, []) == ["    }"]


class TestGeneratePerform:
    """Integration tests: generate() produces correct Java for PERFORM IR."""

    def test_simple_perform_until(self) -> None:
        prog = _make_program(
            IRPerformUntil(left="WS-COUNT", operator=">=", right="10"),
            IRAdd(result="WS-COUNT", left="1"),
            IREndPerform(),
        )
        src = generate(prog)
        assert "while (!(wsCount >= 10)) {" in src
        assert "    wsCount += 1;" in src
        assert "}" in src

    def test_nested_perform(self) -> None:
        prog = _make_program(
            IRPerformUntil(left="WS-A", operator=">", right="0"),
            IRPerformUntil(left="WS-B", operator="<", right="100"),
            IRDisplay(operand='"X"'),
            IREndPerform(),
            IREndPerform(),
        )
        src = generate(prog)
        assert "while (!(wsA > 0)) {" in src
        assert "while (!(wsB < 100)) {" in src
        assert src.index("while (!(wsA") < src.index("while (!(wsB")

        outer_line = next(ln for ln in src.splitlines() if "while (!(wsA" in ln)
        inner_line = next(ln for ln in src.splitlines() if "while (!(wsB" in ln)
        outer_indent = len(outer_line) - len(outer_line.lstrip())
        inner_indent = len(inner_line) - len(inner_line.lstrip())
        assert inner_indent > outer_indent

    def test_mixed_if_and_perform(self) -> None:
        prog = _make_program(
            IRPerformUntil(left="WS-COUNT", operator=">", right="0"),
            IRIf(left="WS-X", operator="==", right="1"),
            IRDisplay(operand='"YES"'),
            IREndIf(),
            IREndPerform(),
        )
        src = generate(prog)
        assert "while (!(wsCount > 0)) {" in src
        assert "if (wsX == 1) {" in src

        while_line = next(ln for ln in src.splitlines() if "while" in ln)
        if_line = next(ln for ln in src.splitlines() if "if (" in ln)
        while_indent = len(while_line) - len(while_line.lstrip())
        if_indent = len(if_line) - len(if_line.lstrip())
        assert if_indent > while_indent

    def test_statement_order_preserved(self) -> None:
        prog = _make_program(
            IRMove(result="WS-A", source="1"),
            IRPerformUntil(left="WS-A", operator=">", right="0"),
            IRMove(result="WS-B", source="2"),
            IREndPerform(),
            IRMove(result="WS-C", source="3"),
        )
        src = generate(prog)
        assert (
            src.index("wsA = 1")
            < src.index("while")
            < src.index("wsB = 2")
            < src.index("wsC = 3")
        )

    def test_deterministic_perform_output(self) -> None:
        prog = _make_program(
            IRPerformUntil(left="WS-COUNT", operator=">", right="0"),
            IRDisplay(operand='"LOOP"'),
            IREndPerform(),
        )
        assert generate(prog) == generate(prog)

    def test_no_timestamps_in_perform_output(self) -> None:
        prog = _make_program(
            IRPerformUntil(left="WS-X", operator=">", right="0"),
            IREndPerform(),
        )
        src = generate(prog)
        assert "timestamp" not in src.lower()

    def test_unmatched_end_perform_produces_be007(self) -> None:
        prog = _make_program(IREndPerform())
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE007" for d in result.diagnostics)
        assert "IREndPerform encountered without a matching IRPerformUntil" in str(
            result.diagnostics
        )

    def test_generation_continues_after_bad_perform(self) -> None:
        prog = _make_program(
            IRPerformUntil(left="", operator=">", right="0"),  # bad
            IRDisplay(operand='"AFTER"'),  # should still be emitted
        )
        src = generate(prog)
        assert 'System.out.println("AFTER");' in src


# ===========================================================================
# TASK-038 — Procedure Invocation: emit_call
# ===========================================================================


class TestEmitCall:
    def test_call_no_args_unquoted(self) -> None:
        instr = IRCall(target="CALCULATE-TOTAL")
        assert emit_call(instr, []) == ["calculateTotal();"]

    def test_call_no_args_quoted(self) -> None:
        instr = IRCall(target='"CALCULATE-TOTAL"')
        assert emit_call(instr, []) == ["calculateTotal();"]

    def test_call_with_args(self) -> None:
        instr = IRCall(target='"UPDATE-ACCOUNT"', args=("WS-ID", "WS-BALANCE"))
        assert emit_call(instr, []) == ["updateAccount(wsId, wsBalance);"]

    def test_call_with_literals(self) -> None:
        instr = IRCall(target="COMPUTE", args=("100", '"TEST"'))
        assert emit_call(instr, []) == ['compute(100, "TEST");']

    def test_call_with_result(self) -> None:
        instr = IRCall(target="GET-STATUS", result="WS-STATUS")
        assert emit_call(instr, []) == ["wsStatus = getStatus();"]

    def test_call_empty_target_produces_be008(self) -> None:
        instr = IRCall(target="", args=("WS-A",))
        diags: list[BackendDiagnostic] = []
        assert emit_call(instr, diags) == []
        assert any(d.code == "BE008" for d in diags)
        assert "empty target" in str(diags[0].message)

    def test_call_empty_arg_produces_be008(self) -> None:
        instr = IRCall(target="FUNC", args=("WS-A", "", "WS-B"))
        diags: list[BackendDiagnostic] = []
        assert emit_call(instr, diags) == []
        assert any(d.code == "BE008" for d in diags)
        assert "empty argument" in str(diags[0].message)


class TestGenerateCall:
    """Integration tests: generate() produces correct Java for CALL IR."""

    def test_simple_call(self) -> None:
        prog = _make_program(IRCall(target='"PROCESS-RECORD"'))
        src = generate(prog)
        assert "processRecord();" in src

    def test_call_with_args(self) -> None:
        prog = _make_program(
            IRCall(target="UPDATE", args=("WS-ID", "WS-AMT")),
        )
        src = generate(prog)
        assert "update(wsId, wsAmt);" in src

    def test_mixed_call_and_arithmetic(self) -> None:
        prog = _make_program(
            IRAdd(result="WS-COUNT", left="1"),
            IRCall(target="LOG-COUNT", args=("WS-COUNT",)),
        )
        src = generate(prog)
        assert src.index("wsCount += 1;") < src.index("logCount(wsCount);")

    def test_call_inside_if(self) -> None:
        prog = _make_program(
            IRIf(left="WS-VALID", operator="==", right='"Y"'),
            IRCall(target="PROCESS"),
            IREndIf(),
        )
        src = generate(prog)
        assert 'if (wsValid == "Y") {' in src
        assert "    process();" in src
        assert "}" in src

    def test_call_inside_perform(self) -> None:
        prog = _make_program(
            IRPerformUntil(left="WS-DONE", operator="==", right='"Y"'),
            IRCall(target="PROCESS"),
            IREndPerform(),
        )
        src = generate(prog)
        assert 'while (!(wsDone == "Y")) {' in src
        assert "    process();" in src
        assert "}" in src

    def test_deterministic_call_output(self) -> None:
        prog = _make_program(
            IRCall(target="DO-WORK", args=("A", "B")),
        )
        assert generate(prog) == generate(prog)
