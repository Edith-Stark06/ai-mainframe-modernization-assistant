"""
Unit tests for task #stage31 — COBOL DISPLAY formatting for PICTURE fields.

Scope under test (Category A only — see ``docs/MMIM_DISPLAY_FORMATTING_FIX.md``):
    - Unsigned ``PIC 9(n)``      → zero-padded to *n* digits.
    - Unsigned ``PIC 9(n)V9(m)`` → zero-padded to *n+m* digits, the assumed
      decimal point never printed.
    - ``PIC X(n)``               → space-padded (right-justified) to *n*
      characters.

Deliberately out of scope, and covered here only as regression tests proving
the old (unformatted) behavior is unchanged:
    - Signed ``PIC S9`` DISPLAY formatting.
    - Edited PICTURE clauses.
    - ``DISPLAY`` of a whole group item.
    - Numeric overflow/truncation.
    - Multi-operand ``DISPLAY``.
    - ``OCCURS``/subscripts.

Coverage
--------
_format_display_operand() / emit_display() — direct unit level
    numeric zero-padding (short/zero/full-width values, PIC 9(5) width),
    numeric-with-implied-decimal zero-padding (small/zero/full-width values,
    no decimal point ever emitted), alphanumeric space-padding (short/exact/
    SPACES), signed field left unformatted, group field left unformatted,
    literal/numeric-literal operands left unformatted, no-context regression,
    field unknown to context regression.

build_fields_from_symbols() — PICTURE metadata propagation
    NumericType -> digits/decimal_places/signed carried onto JavaField
    unchanged (not recomputed); AlphanumericType -> length carried onto
    JavaField; GroupType -> no formatting metadata attached.

generate_with_diagnostics() — end-to-end integration
    A real VariableSymbol -> JavaField -> ConditionContext -> IRDisplay
    pipeline produces the formatted System.out.println(...) call.
"""

from __future__ import annotations

from app.backend.java.condition_context import ConditionContext, build_condition_context
from app.backend.java.field_model import JavaField
from app.backend.java.generator import (
    build_fields_from_symbols,
    generate_with_diagnostics,
)
from app.backend.java.statement_emitter import _format_display_operand, emit_display
from app.ir.blocks import IRBasicBlock
from app.ir.instructions import IRDisplay
from app.ir.program import IRFunction, IRModule, IRProgram
from app.parser.lexer.position import Position
from app.parser.semantic.symbols import VariableSymbol
from app.parser.semantic.types import AlphanumericType, GroupType, NumericType

_POS = Position(line=1, column=1, offset=0, filename="test.cbl")


def _var(name: str, cobol_type=None) -> VariableSymbol:
    return VariableSymbol(name=name, declared_at=_POS, level=1, cobol_type=cobol_type)


def _make_program(*instructions) -> IRProgram:
    block = IRBasicBlock(label="entry", instructions=instructions)
    func = IRFunction(name="__entry__", blocks=(block,))
    module = IRModule(name="TEST", functions=(func,))
    return IRProgram(name="TEST", modules=(module,))


# ===========================================================================
# emit_display() — unsigned PIC 9(n) zero-padding
# ===========================================================================


class TestDisplayNumericZeroPad:
    def _ctx(self, digits: int, decimal_places: int = 0) -> ConditionContext:
        fields = [
            JavaField(
                java_name="wsCount",
                java_type="int",
                digits=digits,
                decimal_places=decimal_places,
                signed=False,
            )
        ]
        return build_condition_context(fields)

    def test_pic_9_3_short_value(self) -> None:
        ctx = self._ctx(digits=3)
        stmts = emit_display(IRDisplay(operand="WS-COUNT"), [], ctx)
        assert stmts == ['System.out.println(String.format("%03d", wsCount));']

    def test_pic_9_3_zero_value(self) -> None:
        # The formatting call is width-driven, not value-driven -- ZERO's own
        # runtime value (0) is what String.format pads, proving "000" comes
        # from the *declared width*, not a special-cased zero.
        ctx = self._ctx(digits=3)
        stmts = emit_display(IRDisplay(operand="WS-COUNT"), [], ctx)
        assert 'String.format("%03d", wsCount)' in stmts[0]

    def test_pic_9_3_full_width_value(self) -> None:
        ctx = self._ctx(digits=3)
        stmts = emit_display(IRDisplay(operand="WS-COUNT"), [], ctx)
        assert 'String.format("%03d", wsCount)' in stmts[0]

    def test_pic_9_5_width(self) -> None:
        ctx = self._ctx(digits=5)
        stmts = emit_display(IRDisplay(operand="WS-COUNT"), [], ctx)
        assert stmts == ['System.out.println(String.format("%05d", wsCount));']


# ===========================================================================
# emit_display() — unsigned PIC 9(n)V9(m): zero-pad, never print '.'
# ===========================================================================


class TestDisplayNumericDecimalZeroPad:
    def _ctx(self, digits: int, decimal_places: int) -> ConditionContext:
        fields = [
            JavaField(
                java_name="wsAmount",
                java_type="double",
                digits=digits,
                decimal_places=decimal_places,
                signed=False,
            )
        ]
        return build_condition_context(fields)

    def test_pic_9_7_v99_full_width_value(self) -> None:
        # PIC 9(7)V99 -> NumericType(digits=9, decimal_places=2); value 500.00
        ctx = self._ctx(digits=9, decimal_places=2)
        stmts = emit_display(IRDisplay(operand="WS-AMOUNT"), [], ctx)
        assert stmts == [
            'System.out.println(String.format("%09d", ' "Math.round(wsAmount * 100)));"
        ]

    def test_pic_9_7_v99_small_value(self) -> None:
        ctx = self._ctx(digits=9, decimal_places=2)
        stmts = emit_display(IRDisplay(operand="WS-AMOUNT"), [], ctx)
        # Same generated expression regardless of the runtime value -- the
        # width/scale are compile-time (declared), the value is Java's own.
        assert 'String.format("%09d", Math.round(wsAmount * 100))' in stmts[0]

    def test_pic_9_7_v99_zero_value(self) -> None:
        ctx = self._ctx(digits=9, decimal_places=2)
        stmts = emit_display(IRDisplay(operand="WS-AMOUNT"), [], ctx)
        assert 'String.format("%09d", Math.round(wsAmount * 100))' in stmts[0]

    def test_no_decimal_point_ever_emitted(self) -> None:
        # An integer ("%0Nd") format specifier, not a floating-point one
        # ("%f"), is what guarantees the *runtime-printed value* never
        # contains COBOL's assumed decimal point -- Java's %d never emits a
        # '.', regardless of the argument's runtime value.
        ctx = self._ctx(digits=9, decimal_places=2)
        stmts = emit_display(IRDisplay(operand="WS-AMOUNT"), [], ctx)
        assert '"%09d"' in stmts[0]
        assert "%f" not in stmts[0]

    def test_pic_9v99_single_digit(self) -> None:
        # PIC 9V99 -> NumericType(digits=3, decimal_places=2)
        ctx = self._ctx(digits=3, decimal_places=2)
        stmts = emit_display(IRDisplay(operand="WS-AMOUNT"), [], ctx)
        assert stmts == [
            'System.out.println(String.format("%03d", ' "Math.round(wsAmount * 100)));"
        ]
        assert "%f" not in stmts[0]


# ===========================================================================
# emit_display() — PIC X(n) space-padding
# ===========================================================================


class TestDisplayAlphanumericSpacePad:
    def _ctx(self, length: int) -> ConditionContext:
        fields = [JavaField(java_name="wsText", java_type="String", length=length)]
        return build_condition_context(fields)

    def test_pic_x_4_shorter_value(self) -> None:
        ctx = self._ctx(length=4)
        stmts = emit_display(IRDisplay(operand="WS-TEXT"), [], ctx)
        assert stmts == ['System.out.println(String.format("%-4s", wsText));']

    def test_pic_x_4_exact_width_value(self) -> None:
        # Same generated expression regardless of the runtime value's own
        # width -- Java's "%-4s" leaves an already-4-character value alone.
        ctx = self._ctx(length=4)
        stmts = emit_display(IRDisplay(operand="WS-TEXT"), [], ctx)
        assert stmts == ['System.out.println(String.format("%-4s", wsText));']

    def test_pic_x_6_spaces(self) -> None:
        ctx = self._ctx(length=6)
        stmts = emit_display(IRDisplay(operand="WS-TEXT"), [], ctx)
        assert stmts == ['System.out.println(String.format("%-6s", wsText));']


# ===========================================================================
# Regression — deliberately unformatted cases
# ===========================================================================


class TestDisplayFormattingRegressions:
    def test_signed_field_unchanged(self) -> None:
        fields = [
            JavaField(
                java_name="wsSigned",
                java_type="int",
                digits=5,
                decimal_places=0,
                signed=True,
            )
        ]
        ctx = build_condition_context(fields)
        stmts = emit_display(IRDisplay(operand="WS-SIGNED"), [], ctx)
        assert stmts == ["System.out.println(wsSigned);"]

    def test_group_display_out_of_scope(self) -> None:
        # A group item maps to Java String (type_mapper) but carries no
        # `length` (only an elementary AlphanumericType does) -- DISPLAY of
        # the group stays exactly as it was before #stage31.
        fields = [JavaField(java_name="wsGroup", java_type="String")]
        ctx = build_condition_context(fields)
        stmts = emit_display(IRDisplay(operand="WS-GROUP"), [], ctx)
        assert stmts == ["System.out.println(wsGroup);"]

    def test_string_literal_unchanged(self) -> None:
        ctx = build_condition_context(
            [JavaField(java_name="wsGreeting", java_type="String", length=20)]
        )
        stmts = emit_display(IRDisplay(operand='"HELLO"'), [], ctx)
        assert stmts == ['System.out.println("HELLO");']

    def test_cobol_single_quoted_literal_unchanged(self) -> None:
        ctx = build_condition_context(
            [JavaField(java_name="wsGreeting", java_type="String", length=20)]
        )
        stmts = emit_display(IRDisplay(operand="'HELLO'"), [], ctx)
        assert stmts == ['System.out.println("HELLO");']

    def test_numeric_literal_unchanged(self) -> None:
        ctx = build_condition_context(
            [JavaField(java_name="wsCount", java_type="int", digits=3)]
        )
        stmts = emit_display(IRDisplay(operand="42"), [], ctx)
        assert stmts == ["System.out.println(42);"]

    def test_no_context_preserves_old_behavior(self) -> None:
        stmts = emit_display(IRDisplay(operand="WS-COUNT"), [])
        assert stmts == ["System.out.println(wsCount);"]

    def test_context_without_matching_field_unchanged(self) -> None:
        ctx = build_condition_context(
            [JavaField(java_name="wsOther", java_type="int", digits=3)]
        )
        stmts = emit_display(IRDisplay(operand="WS-UNKNOWN"), [], ctx)
        assert stmts == ["System.out.println(wsUnknown);"]

    def test_unresolved_type_field_unchanged(self) -> None:
        # A field with no resolved cobol_type carries neither digits nor
        # length (both None): nothing to format with.
        ctx = build_condition_context(
            [JavaField(java_name="wsMystery", java_type="String")]
        )
        stmts = emit_display(IRDisplay(operand="WS-MYSTERY"), [], ctx)
        assert stmts == ["System.out.println(wsMystery);"]


# ===========================================================================
# _format_display_operand() — direct unit tests
# ===========================================================================


class TestFormatDisplayOperandDirect:
    def test_returns_unchanged_when_context_is_none(self) -> None:
        assert _format_display_operand("WS-COUNT", "wsCount", None) == "wsCount"

    def test_formats_known_numeric_field(self) -> None:
        ctx = build_condition_context(
            [JavaField(java_name="wsCount", java_type="int", digits=3)]
        )
        assert (
            _format_display_operand("WS-COUNT", "wsCount", ctx)
            == 'String.format("%03d", wsCount)'
        )


# ===========================================================================
# build_fields_from_symbols() — PICTURE metadata propagation (task #stage31)
# ===========================================================================


class TestBuildFieldsFromSymbolsCarriesPictureMetadata:
    def test_pic_9_n_carries_digits_unsigned(self) -> None:
        sym = _var("WS-COUNT", NumericType(digits=3))
        fields = build_fields_from_symbols([sym])
        assert fields[0].digits == 3
        assert fields[0].decimal_places == 0
        assert fields[0].signed is False
        assert fields[0].length is None

    def test_pic_s9_n_carries_signed_true(self) -> None:
        sym = _var("WS-SIGNED", NumericType(digits=5, signed=True))
        fields = build_fields_from_symbols([sym])
        assert fields[0].signed is True
        assert fields[0].digits == 5

    def test_pic_9_n_v_9_m_carries_total_digits_and_decimal_places(self) -> None:
        # PIC 9(7)V99 -> NumericType(digits=9, decimal_places=2) (n+m total,
        # per TypeBuilder's own convention -- never recomputed here).
        sym = _var("WS-AMOUNT", NumericType(digits=9, decimal_places=2))
        fields = build_fields_from_symbols([sym])
        assert fields[0].digits == 9
        assert fields[0].decimal_places == 2
        assert fields[0].signed is False

    def test_pic_x_n_carries_length(self) -> None:
        sym = _var("WS-TEXT", AlphanumericType(length=12))
        fields = build_fields_from_symbols([sym])
        assert fields[0].length == 12
        assert fields[0].digits is None

    def test_group_type_carries_no_formatting_metadata(self) -> None:
        sym = _var("WS-GROUP", GroupType())
        fields = build_fields_from_symbols([sym])
        assert fields[0].digits is None
        assert fields[0].length is None
        assert fields[0].decimal_places == 0
        assert fields[0].signed is False

    def test_unresolved_type_skipped_no_field_at_all(self) -> None:
        sym = _var("WS-UNKNOWN", None)
        fields = build_fields_from_symbols([sym])
        assert fields == []


# ===========================================================================
# generate_with_diagnostics() — end-to-end integration
# ===========================================================================


class TestGenerateWithDiagnosticsDisplayFormatting:
    def test_pic_9_field_formatted_in_generated_source(self) -> None:
        sym = _var("WS-COUNT", NumericType(digits=3))
        fields = build_fields_from_symbols([sym])
        prog = _make_program(IRDisplay(operand="WS-COUNT"))
        result = generate_with_diagnostics(prog, fields=fields)
        assert 'System.out.println(String.format("%03d", wsCount));' in result.source

    def test_pic_9_v_9_field_formatted_in_generated_source(self) -> None:
        sym = _var("WS-AMOUNT", NumericType(digits=9, decimal_places=2))
        fields = build_fields_from_symbols([sym])
        prog = _make_program(IRDisplay(operand="WS-AMOUNT"))
        result = generate_with_diagnostics(prog, fields=fields)
        assert 'String.format("%09d", Math.round(wsAmount * 100))' in result.source
        assert "System.out.println" in result.source

    def test_pic_x_field_formatted_in_generated_source(self) -> None:
        sym = _var("WS-TEXT", AlphanumericType(length=10))
        fields = build_fields_from_symbols([sym])
        prog = _make_program(IRDisplay(operand="WS-TEXT"))
        result = generate_with_diagnostics(prog, fields=fields)
        assert 'System.out.println(String.format("%-10s", wsText));' in result.source

    def test_signed_field_unformatted_in_generated_source(self) -> None:
        sym = _var("WS-SIGNED", NumericType(digits=5, signed=True))
        fields = build_fields_from_symbols([sym])
        prog = _make_program(IRDisplay(operand="WS-SIGNED"))
        result = generate_with_diagnostics(prog, fields=fields)
        assert "System.out.println(wsSigned);" in result.source
        assert "String.format" not in result.source

    def test_literal_display_unaffected_by_unrelated_fields(self) -> None:
        sym = _var("WS-COUNT", NumericType(digits=3))
        fields = build_fields_from_symbols([sym])
        prog = _make_program(IRDisplay(operand='"HELLO"'))
        result = generate_with_diagnostics(prog, fields=fields)
        assert 'System.out.println("HELLO");' in result.source
        assert "String.format" not in result.source

    def test_no_fields_generation_unchanged(self) -> None:
        prog = _make_program(IRDisplay(operand="WS-GREETING"))
        result = generate_with_diagnostics(prog)
        assert "System.out.println(wsGreeting);" in result.source
        assert "String.format" not in result.source
