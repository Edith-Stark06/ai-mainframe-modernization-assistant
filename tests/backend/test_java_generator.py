"""
Unit tests for the Java backend generator (app/backend/java/generator.py) — TASK-032.

Coverage:
    - generate(): empty program, named program, class name derivation.
    - _to_java_class_name(): various COBOL naming conventions.
    - GenerationResult: has_errors, diagnostics.
    - generate_with_diagnostics(): missing name diagnostics.
    - Deterministic output: repeated calls produce identical output.
    - Class structure: declaration, main method, braces.
    - Instruction stubs: IR comments inside main().
"""

from __future__ import annotations

import pytest

from app.backend.java.generator import (
    BackendDiagnostic,
    BackendSeverity,
    GenerationResult,
    _to_java_class_name,
    generate,
    generate_with_diagnostics,
)
from app.ir.blocks import IRBasicBlock
from app.ir.instructions import IRCall, IRDisplay, IRMove, IRReturn
from app.ir.program import IRFunction, IRModule, IRProgram

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_program(
    prog_name: str = "TEST",
    instructions: tuple = (),
) -> IRProgram:
    """Build a minimal IRProgram with one block."""
    block = IRBasicBlock(label="entry", instructions=instructions)
    func = IRFunction(name="__entry__", blocks=(block,))
    module = IRModule(name=prog_name, functions=(func,))
    return IRProgram(name=prog_name, modules=(module,))


def _empty_program(name: str = "") -> IRProgram:
    """Build an IRProgram with no modules."""
    return IRProgram(name=name)


# ---------------------------------------------------------------------------
# _to_java_class_name
# ---------------------------------------------------------------------------


class TestToJavaClassName:
    def test_simple_upper(self) -> None:
        assert _to_java_class_name("HELLO") == "Hello"

    def test_hyphenated_cobol_name(self) -> None:
        assert _to_java_class_name("HELLO-WORLD") == "HelloWorld"

    def test_underscore_separated(self) -> None:
        assert _to_java_class_name("hello_world") == "HelloWorld"

    def test_lowercase(self) -> None:
        assert _to_java_class_name("payroll") == "Payroll"

    def test_mixed_case(self) -> None:
        assert _to_java_class_name("myProgram") == "MyProgram"

    def test_empty_string_returns_default(self) -> None:
        assert _to_java_class_name("") == "GeneratedProgram"

    def test_multi_segment(self) -> None:
        result = _to_java_class_name("CALC-PAYROLL-REPORT")
        assert result == "CalcPayrollReport"

    def test_leading_digit_prepended(self) -> None:
        result = _to_java_class_name("1BADNAME")
        assert result[0].isalpha()

    def test_special_chars_stripped(self) -> None:
        result = _to_java_class_name("HELLO@WORLD")
        # @ is stripped; result should still be usable
        assert result.isidentifier()

    def test_single_char(self) -> None:
        assert _to_java_class_name("A") == "A"

    def test_spaces_stripped(self) -> None:
        # spaces are not valid separators but should not crash
        result = _to_java_class_name("  ")
        assert result == "GeneratedProgram"


# ---------------------------------------------------------------------------
# generate() — class structure
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_returns_string(self) -> None:
        prog = _make_program("HELLO")
        assert isinstance(generate(prog), str)

    def test_non_empty(self) -> None:
        prog = _make_program("HELLO")
        assert generate(prog).strip()

    def test_class_declaration_present(self) -> None:
        prog = _make_program("HELLO")
        src = generate(prog)
        assert "public class Hello" in src

    def test_main_method_present(self) -> None:
        prog = _make_program("HELLO")
        src = generate(prog)
        assert "public static void main(String[] args)" in src

    def test_opening_brace_present(self) -> None:
        prog = _make_program("HELLO")
        src = generate(prog)
        assert "{" in src

    def test_closing_brace_present(self) -> None:
        prog = _make_program("HELLO")
        src = generate(prog)
        assert "}" in src

    def test_class_name_from_module(self) -> None:
        prog = _make_program("PAYROLL")
        src = generate(prog)
        assert "public class Payroll" in src

    def test_hyphenated_name(self) -> None:
        prog = _make_program("CALC-REPORT")
        src = generate(prog)
        assert "public class CalcReport" in src

    def test_deterministic_output(self) -> None:
        prog = _make_program("HELLO")
        assert generate(prog) == generate(prog)

    def test_deterministic_across_calls(self) -> None:
        prog1 = _make_program("SAME")
        prog2 = _make_program("SAME")
        assert generate(prog1) == generate(prog2)

    def test_empty_program_no_modules(self) -> None:
        prog = _empty_program("EMPTY")
        src = generate(prog)
        # Should still produce a class
        assert "public class Empty" in src
        assert "public static void main" in src

    def test_program_with_no_name_falls_back(self) -> None:
        prog = _empty_program("")  # no name, no modules
        src = generate(prog)
        assert "public class GeneratedProgram" in src

    def test_instruction_in_main(self) -> None:
        # DISPLAY now emits a real println, not a // IR: comment
        prog = _make_program("HELLO", instructions=(IRDisplay(operand='"HI"'),))
        src = generate(prog)
        assert 'System.out.println("HI");' in src

    def test_move_statement_present(self) -> None:
        # MOVE now emits a real Java assignment
        instr = IRMove(result="WS-B", source="WS-A")
        prog = _make_program("PROG", instructions=(instr,))
        src = generate(prog)
        assert "wsB = wsA;" in src

    def test_unsupported_return_todo_comment(self) -> None:
        # Unsupported IRReturn produces a // TODO: comment
        prog = _make_program("PROG", instructions=(IRReturn(),))
        src = generate(prog)
        assert "// TODO: translate IRReturn" in src

    def test_multiple_statements_ordered(self) -> None:
        # DISPLAY → println, MOVE → assignment, IRReturn → TODO
        instrs = (
            IRDisplay(operand='"A"'),
            IRMove(result="X", source="Y"),
            IRReturn(),
        )
        prog = _make_program("PROG", instructions=instrs)
        src = generate(prog)
        idx_display = src.index('System.out.println("A")')
        idx_move = src.index("x = y;")
        idx_todo = src.index("// TODO:")
        assert idx_display < idx_move < idx_todo

    def test_main_method_body_indented(self) -> None:
        prog = _make_program("HELLO")
        src = generate(prog)
        # main body must be inside the class body
        class_start = src.index("public class")
        main_start = src.index("public static void main")
        assert class_start < main_start

    def test_no_timestamps_in_output(self) -> None:
        import re

        prog = _make_program("HELLO")
        src = generate(prog)
        # No date-like patterns (YYYY-MM-DD / YYYY/MM/DD)
        assert not re.search(r"\d{4}[-/]\d{2}[-/]\d{2}", src)


# ---------------------------------------------------------------------------
# generate_with_diagnostics()
# ---------------------------------------------------------------------------


class TestGenerateWithDiagnostics:
    def test_returns_generation_result(self) -> None:
        prog = _make_program("HELLO")
        result = generate_with_diagnostics(prog)
        assert isinstance(result, GenerationResult)

    def test_no_diagnostics_for_valid_program(self) -> None:
        prog = _make_program("HELLO")
        result = generate_with_diagnostics(prog)
        assert result.diagnostics == []

    def test_warning_for_missing_name(self) -> None:
        prog = _empty_program("")  # no name, no modules
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE001" for d in result.diagnostics)

    def test_warning_severity_for_missing_name(self) -> None:
        prog = _empty_program("")
        result = generate_with_diagnostics(prog)
        diags = [d for d in result.diagnostics if d.code == "BE001"]
        assert diags[0].severity is BackendSeverity.WARNING

    def test_has_errors_false_for_warnings(self) -> None:
        prog = _empty_program("")
        result = generate_with_diagnostics(prog)
        assert not result.has_errors

    def test_source_non_empty_even_with_diagnostics(self) -> None:
        prog = _empty_program("")
        result = generate_with_diagnostics(prog)
        assert result.source.strip()

    def test_backend_diagnostic_immutable(self) -> None:
        diag = BackendDiagnostic(
            severity=BackendSeverity.ERROR,
            message="test",
            code="BE999",
        )
        with pytest.raises((AttributeError, TypeError)):
            diag.message = "changed"  # type: ignore[misc]

    def test_generation_result_has_errors_with_error_diag(self) -> None:
        result = GenerationResult(
            source="public class X {}",
            diagnostics=[
                BackendDiagnostic(
                    severity=BackendSeverity.ERROR,
                    message="forced error",
                    code="BE999",
                )
            ],
        )
        assert result.has_errors

    def test_generation_result_has_errors_false_when_empty(self) -> None:
        result = GenerationResult(source="public class X {}")
        assert not result.has_errors

    def test_be009_warning_for_unresolved_call_target(self) -> None:
        # An IRCall whose target has no generated method body must surface a
        # BE009 diagnostic rather than silently emitting an undefined call.
        prog = _make_program(
            "CALLER",
            instructions=(IRCall(target="SUBPROG"),),
        )
        result = generate_with_diagnostics(prog)
        assert any(d.code == "BE009" for d in result.diagnostics)

    def test_be009_severity_is_warning(self) -> None:
        prog = _make_program("CALLER", instructions=(IRCall(target="SUBPROG"),))
        result = generate_with_diagnostics(prog)
        diags = [d for d in result.diagnostics if d.code == "BE009"]
        assert diags and diags[0].severity is BackendSeverity.WARNING

    def test_be009_does_not_mark_errors(self) -> None:
        # A missing method body is a warning, not a hard error.
        prog = _make_program("CALLER", instructions=(IRCall(target="SUBPROG"),))
        result = generate_with_diagnostics(prog)
        assert not result.has_errors

    def test_be009_emits_stub_method_with_todo(self) -> None:
        # The generated source must contain an explicit stub method and a TODO
        # marker so the missing translation is visible, not hidden.
        prog = _make_program("CALLER", instructions=(IRCall(target="SUBPROG"),))
        result = generate_with_diagnostics(prog)
        assert "private void subprog()" in result.source
        assert (
            "// TODO: implement CALL/PERFORM target 'SUBPROG' (BE009)." in result.source
        )

    def test_be009_deduplicates_repeated_targets(self) -> None:
        # Two calls to the same target must produce exactly one stub and one
        # diagnostic, keeping generation deterministic.
        prog = _make_program(
            "CALLER",
            instructions=(IRCall(target="SUBPROG"), IRCall(target="SUBPROG")),
        )
        result = generate_with_diagnostics(prog)
        be009 = [d for d in result.diagnostics if d.code == "BE009"]
        assert len(be009) == 1
        assert result.source.count("private void subprog()") == 1
