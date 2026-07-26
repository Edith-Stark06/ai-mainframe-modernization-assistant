from pathlib import Path

from tests.integration.helpers import compile_cobol_pipeline

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_hello_world_pipeline() -> None:
    result = compile_cobol_pipeline(FIXTURES_DIR / "hello_world.cbl")
    assert (
        result.success
    ), f"Compilation failed: {result.error} / {result.semantic_diagnostics}"
    assert 'System.out.println("HELLO WORLD");' in result.java_source


def test_move_display_pipeline() -> None:
    result = compile_cobol_pipeline(FIXTURES_DIR / "move_display.cbl")
    assert result.success
    assert "wsCount = 5;" in result.java_source
    assert "System.out.println(wsCount);" in result.java_source


def test_arithmetic_pipeline() -> None:
    result = compile_cobol_pipeline(FIXTURES_DIR / "arithmetic.cbl")
    assert result.success
    assert "+=" in result.java_source
    assert "-=" in result.java_source
    assert "*=" in result.java_source
    assert "/=" in result.java_source


def test_if_else_pipeline() -> None:
    result = compile_cobol_pipeline(FIXTURES_DIR / "if_else.cbl")
    assert result.success
    assert "if (" in result.java_source
    assert "} else {" in result.java_source


def test_perform_until_pipeline() -> None:
    result = compile_cobol_pipeline(FIXTURES_DIR / "perform_until.cbl")
    assert result.success
    assert "while (" in result.java_source


def test_call_pipeline() -> None:
    result = compile_cobol_pipeline(FIXTURES_DIR / "call.cbl")
    assert result.success
    assert "calculateTotal();" in result.java_source
    assert "processId(wsId);" in result.java_source


def test_combined_program_pipeline() -> None:
    result = compile_cobol_pipeline(FIXTURES_DIR / "combined_program.cbl")
    assert result.success
    src = result.java_source
    assert "private int wsA;" in src
    assert "private int wsB;" in src
    assert "wsA = 30;" in src
    assert "wsA += wsB;" in src
    assert "if (" in src
    assert "overLimit();" in src
    assert "while (" in src
    assert "System.out.println(wsB);" in src


def test_invalid_syntax_pipeline() -> None:
    result = compile_cobol_pipeline(FIXTURES_DIR / "invalid_syntax.cbl")
    # This might throw a LexerError or ParserError, which the helper catches and sets in result.error
    # or it might produce a semantic diagnostic if it parses successfully but is invalid.
    # The requirement is just "diagnostics are produced, compiler fails gracefully, no unhandled exceptions"
    assert not result.success or (
        result.success and len(result.backend_diagnostics) > 0
    )
    assert (
        result.error is not None
        or len(result.semantic_diagnostics) > 0
        or len(result.backend_diagnostics) > 0
    )


def test_undefined_variable_pipeline() -> None:
    result = compile_cobol_pipeline(FIXTURES_DIR / "undefined_variable.cbl")
    assert not result.success
    assert len(result.semantic_diagnostics) > 0
    assert any(
        "UNDEFINED" in str(d).upper() or "NOT FOUND" in str(d).upper()
        for d in result.semantic_diagnostics
    )


def test_deterministic_output() -> None:
    # Running the compiler multiple times on the same COBOL fixture should always generate identical Java output.
    result1 = compile_cobol_pipeline(FIXTURES_DIR / "combined_program.cbl")
    result2 = compile_cobol_pipeline(FIXTURES_DIR / "combined_program.cbl")
    assert result1.success and result2.success
    assert result1.java_source == result2.java_source
    assert "timestamp" not in result1.java_source.lower()
    assert "uuid" not in result1.java_source.lower()
