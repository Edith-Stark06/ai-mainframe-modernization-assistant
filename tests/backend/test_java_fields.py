"""
Unit tests for TASK-033 — Java Variable & Data Division Generation.

Coverage:
    - JavaField.render(): with and without initial value.
    - to_java_field_name(): various COBOL naming conventions.
    - map_cobol_type(): all supported CobolType subtypes.
    - build_fields_from_symbols(): full symbol-to-field pipeline.
    - generate() with fields: field presence, ordering, determinism.
    - Diagnostics: BE002 for unsupported type, BE003 for missing type.
    - GenerationResult integration.
"""

from __future__ import annotations

import pytest

from app.backend.java.field_model import JavaField
from app.backend.java.generator import (
    BackendDiagnostic,
    BackendSeverity,
    GenerationResult,
    build_fields_from_symbols,
    generate,
    generate_with_diagnostics,
)
from app.backend.java.naming import to_java_field_name
from app.backend.java.type_mapper import map_cobol_type
from app.ir.blocks import IRBasicBlock
from app.ir.program import IRFunction, IRModule, IRProgram
from app.parser.lexer.position import Position
from app.parser.semantic.symbols import VariableSymbol
from app.parser.semantic.types import AlphanumericType, GroupType, NumericType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_POS = Position(line=1, column=1, offset=0, filename="test.cbl")


def _make_program(prog_name: str = "TEST") -> IRProgram:
    block = IRBasicBlock(label="entry")
    func = IRFunction(name="__entry__", blocks=(block,))
    module = IRModule(name=prog_name, functions=(func,))
    return IRProgram(name=prog_name, modules=(module,))


def _var(name: str, cobol_type=None) -> VariableSymbol:
    return VariableSymbol(name=name, declared_at=_POS, level=1, cobol_type=cobol_type)


# ---------------------------------------------------------------------------
# JavaField.render()
# ---------------------------------------------------------------------------


class TestJavaFieldRender:
    def test_string_field_with_value(self) -> None:
        f = JavaField(
            java_name="wsGreeting", java_type="String", initial_value='"WELCOME"'
        )
        assert f.render() == '    private String wsGreeting = "WELCOME";'

    def test_int_field_with_value(self) -> None:
        f = JavaField(java_name="wsCount", java_type="int", initial_value="0")
        assert f.render() == "    private int wsCount = 0;"

    def test_double_field_with_value(self) -> None:
        f = JavaField(java_name="wsRate", java_type="double", initial_value="0.0")
        assert f.render() == "    private double wsRate = 0.0;"

    def test_boolean_field_with_value(self) -> None:
        f = JavaField(java_name="wsFlag", java_type="boolean", initial_value="false")
        assert f.render() == "    private boolean wsFlag = false;"

    def test_field_without_initial_value(self) -> None:
        f = JavaField(java_name="customerName", java_type="String")
        assert f.render() == "    private String customerName;"

    def test_none_initial_value_no_equals(self) -> None:
        f = JavaField(java_name="x", java_type="int", initial_value=None)
        rendered = f.render()
        assert "=" not in rendered

    def test_custom_indent(self) -> None:
        f = JavaField(java_name="x", java_type="int")
        assert f.render(indent="  ") == "  private int x;"

    def test_immutable_frozen(self) -> None:
        f = JavaField(java_name="x", java_type="int")
        with pytest.raises((AttributeError, TypeError)):
            f.java_name = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# to_java_field_name()
# ---------------------------------------------------------------------------


class TestToJavaFieldName:
    def test_ws_count(self) -> None:
        assert to_java_field_name("WS-COUNT") == "wsCount"

    def test_customer_name(self) -> None:
        assert to_java_field_name("CUSTOMER-NAME") == "customerName"

    def test_employee_id(self) -> None:
        assert to_java_field_name("EMPLOYEE-ID") == "employeeId"

    def test_single_word(self) -> None:
        assert to_java_field_name("TOTAL") == "total"

    def test_underscore_separator(self) -> None:
        assert to_java_field_name("WS_COUNT") == "wsCount"

    def test_already_lower(self) -> None:
        assert to_java_field_name("total") == "total"

    def test_empty_returns_field(self) -> None:
        assert to_java_field_name("") == "field"

    def test_whitespace_only_returns_field(self) -> None:
        assert to_java_field_name("   ") == "field"

    def test_leading_digit_prepended(self) -> None:
        result = to_java_field_name("1BAD")
        assert result[0].isalpha()
        assert result.startswith("f")

    def test_three_segment_name(self) -> None:
        assert to_java_field_name("WS-TOTAL-COUNT") == "wsTotalCount"

    def test_valid_java_identifier(self) -> None:
        result = to_java_field_name("WS-GREETING")
        assert result.isidentifier()

    def test_first_letter_lowercase(self) -> None:
        result = to_java_field_name("HELLO")
        assert result[0].islower()


# ---------------------------------------------------------------------------
# map_cobol_type()
# ---------------------------------------------------------------------------


class TestMapCobolType:
    def test_alphanumeric_maps_to_string(self) -> None:
        t = AlphanumericType(length=20)
        java_type, err = map_cobol_type(t)
        assert java_type == "String"
        assert err is None

    def test_numeric_integer_maps_to_int(self) -> None:
        t = NumericType(digits=5)
        java_type, err = map_cobol_type(t)
        assert java_type == "int"
        assert err is None

    def test_numeric_decimal_maps_to_double(self) -> None:
        t = NumericType(digits=7, decimal_places=2)
        java_type, err = map_cobol_type(t)
        assert java_type == "double"
        assert err is None

    def test_group_type_maps_to_string(self) -> None:
        t = GroupType()
        java_type, err = map_cobol_type(t)
        assert java_type == "String"
        assert err is None

    def test_numeric_signed_integer_maps_to_int(self) -> None:
        t = NumericType(digits=9, signed=True)
        java_type, err = map_cobol_type(t)
        assert java_type == "int"
        assert err is None

    def test_returns_tuple(self) -> None:
        t = AlphanumericType(length=1)
        result = map_cobol_type(t)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_no_error_for_alphanumeric(self) -> None:
        t = AlphanumericType(length=5)
        _, err = map_cobol_type(t)
        assert err is None


# ---------------------------------------------------------------------------
# build_fields_from_symbols()
# ---------------------------------------------------------------------------


class TestBuildFieldsFromSymbols:
    def test_alphanumeric_symbol(self) -> None:
        sym = _var("WS-GREETING", AlphanumericType(length=20))
        fields = build_fields_from_symbols([sym])
        assert len(fields) == 1
        assert fields[0].java_type == "String"
        assert fields[0].java_name == "wsGreeting"

    def test_integer_symbol(self) -> None:
        sym = _var("WS-COUNT", NumericType(digits=3))
        fields = build_fields_from_symbols([sym])
        assert fields[0].java_type == "int"
        assert fields[0].java_name == "wsCount"

    def test_decimal_symbol(self) -> None:
        sym = _var("WS-RATE", NumericType(digits=5, decimal_places=2))
        fields = build_fields_from_symbols([sym])
        assert fields[0].java_type == "double"
        assert fields[0].java_name == "wsRate"

    def test_group_symbol(self) -> None:
        sym = _var("WS-GROUP", GroupType())
        fields = build_fields_from_symbols([sym])
        assert fields[0].java_type == "String"

    def test_symbol_without_type_skipped_with_diagnostic(self) -> None:
        sym = _var("WS-UNKNOWN", cobol_type=None)
        diags: list[BackendDiagnostic] = []
        fields = build_fields_from_symbols([sym], diagnostics=diags)
        assert len(fields) == 0
        assert any(d.code == "BE003" for d in diags)

    def test_be003_warning_severity(self) -> None:
        sym = _var("WS-NONE", cobol_type=None)
        diags: list[BackendDiagnostic] = []
        build_fields_from_symbols([sym], diagnostics=diags)
        be003 = [d for d in diags if d.code == "BE003"]
        assert be003[0].severity is BackendSeverity.WARNING

    def test_multiple_symbols_ordered(self) -> None:
        syms = [
            _var("WS-A", AlphanumericType(length=10)),
            _var("WS-B", NumericType(digits=5)),
            _var("WS-C", NumericType(digits=7, decimal_places=2)),
        ]
        fields = build_fields_from_symbols(syms)
        assert [f.java_name for f in fields] == ["wsA", "wsB", "wsC"]

    def test_empty_input_returns_empty_list(self) -> None:
        assert build_fields_from_symbols([]) == []

    def test_cobol_name_preserved(self) -> None:
        sym = _var("WS-GREETING", AlphanumericType(length=10))
        fields = build_fields_from_symbols([sym])
        assert fields[0].cobol_name == "WS-GREETING"

    def test_no_initial_value_by_default(self) -> None:
        sym = _var("WS-X", NumericType(digits=3))
        fields = build_fields_from_symbols([sym])
        assert fields[0].initial_value is None


# ---------------------------------------------------------------------------
# generate() with fields
# ---------------------------------------------------------------------------


class TestGenerateWithFields:
    def test_field_declaration_in_output(self) -> None:
        prog = _make_program("HELLO")
        fields = [JavaField(java_name="wsGreeting", java_type="String")]
        src = generate(prog, fields=fields)
        assert "private String wsGreeting;" in src

    def test_field_appears_before_main(self) -> None:
        prog = _make_program("HELLO")
        fields = [JavaField(java_name="wsCount", java_type="int")]
        src = generate(prog, fields=fields)
        field_pos = src.index("private int wsCount")
        main_pos = src.index("public static void main")
        assert field_pos < main_pos

    def test_multiple_fields_ordered(self) -> None:
        prog = _make_program("HELLO")
        fields = [
            JavaField(java_name="wsA", java_type="String"),
            JavaField(java_name="wsB", java_type="int"),
        ]
        src = generate(prog, fields=fields)
        assert src.index("wsA") < src.index("wsB")

    def test_field_with_initial_value(self) -> None:
        prog = _make_program("HELLO")
        fields = [JavaField(java_name="wsCount", java_type="int", initial_value="0")]
        src = generate(prog, fields=fields)
        assert "private int wsCount = 0;" in src

    def test_string_field_with_initial_value(self) -> None:
        prog = _make_program("HELLO")
        fields = [
            JavaField(java_name="wsName", java_type="String", initial_value='"WELCOME"')
        ]
        src = generate(prog, fields=fields)
        assert 'private String wsName = "WELCOME";' in src

    def test_no_fields_no_private_keyword(self) -> None:
        prog = _make_program("HELLO")
        src = generate(prog, fields=None)
        assert "private" not in src

    def test_empty_fields_no_private_keyword(self) -> None:
        prog = _make_program("HELLO")
        src = generate(prog, fields=[])
        assert "private" not in src

    def test_deterministic_with_fields(self) -> None:
        prog = _make_program("HELLO")
        fields = [
            JavaField(java_name="wsA", java_type="String"),
            JavaField(java_name="wsB", java_type="int"),
        ]
        assert generate(prog, fields=fields) == generate(prog, fields=fields)

    def test_generate_with_diagnostics_fields(self) -> None:
        prog = _make_program("HELLO")
        fields = [JavaField(java_name="wsX", java_type="double")]
        result = generate_with_diagnostics(prog, fields=fields)
        assert isinstance(result, GenerationResult)
        assert "private double wsX;" in result.source

    def test_full_pipeline_string_field(self) -> None:
        """End-to-end: symbol → JavaField → Java source."""
        sym = _var("WS-GREETING", AlphanumericType(length=20))
        fields = build_fields_from_symbols([sym])
        prog = _make_program("HELLO")
        src = generate(prog, fields=fields)
        assert "private String wsGreeting;" in src

    def test_full_pipeline_int_field(self) -> None:
        sym = _var("WS-COUNT", NumericType(digits=3))
        fields = build_fields_from_symbols([sym])
        prog = _make_program("HELLO")
        src = generate(prog, fields=fields)
        assert "private int wsCount;" in src

    def test_full_pipeline_double_field(self) -> None:
        sym = _var("WS-RATE", NumericType(digits=5, decimal_places=2))
        fields = build_fields_from_symbols([sym])
        prog = _make_program("HELLO")
        src = generate(prog, fields=fields)
        assert "private double wsRate;" in src
