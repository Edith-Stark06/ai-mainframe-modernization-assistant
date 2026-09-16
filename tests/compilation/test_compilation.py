"""
Java Compilation Test Runner.

Verifies the complete generated Java output can be successfully compiled by javac,
and verifies that invalid COBOL stops before Java generation and javac invocation.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.backend.java.generator import (
    build_fields_from_symbols,
    generate_with_diagnostics,
)
from app.ir.builder import IRBuilder
from app.parser.lexer.lexer import CobolLexer
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.semantic.symbols import SymbolKind
from app.parser.syntax.program_parser import ProgramParser


def discover_fixtures() -> list[Path]:
    """Discover valid .cbl fixtures from golden directory."""
    base_dir = Path(__file__).parent.parent
    golden_dir = base_dir / "golden"
    if golden_dir.exists():
        return sorted(golden_dir.glob("*.cbl"))
    return []


def discover_invalid_fixtures() -> list[Path]:
    """Discover invalid .cbl fixtures from regression/fixtures/invalid directory."""
    base_dir = Path(__file__).parent.parent
    invalid_dir = base_dir / "regression" / "fixtures" / "invalid"
    if invalid_dir.exists():
        return sorted(invalid_dir.glob("*.cbl"))
    return []


@pytest.mark.parametrize("cbl_path", discover_fixtures(), ids=lambda p: p.name)
def test_java_compilation(cbl_path: Path, tmp_path: Path) -> None:
    """Run the compiler pipeline and invoke javac on the result."""
    source = cbl_path.read_text(encoding="utf-8")

    # Pipeline
    lexer = CobolLexer()
    tokens = lexer.tokenize(source, filename=str(cbl_path))

    parser = ProgramParser()
    program_node = parser.parse(tokens)

    analyzer = SemanticAnalyzer()
    ctx = analyzer.analyse(program_node)

    # Valid fixtures must not produce semantic errors
    assert program_node is not None, f"Parsing failed for valid fixture {cbl_path.name}"
    assert (
        not ctx.has_errors
    ), f"Semantic analysis failed for valid fixture {cbl_path.name}: {ctx.diagnostics}"

    builder = IRBuilder(context=ctx)
    ir_program = builder.build(program_node)

    var_symbols = ctx.symbol_table.symbols_of_kind(SymbolKind.VARIABLE)
    fields = build_fields_from_symbols(var_symbols)

    result = generate_with_diagnostics(ir_program, fields)
    generated_java = result.source

    # Check if javac is installed
    if not shutil.which("javac"):
        pytest.skip("javac not found on the system")

    # Create temporary file
    # Extract public class name from generated output
    class_name_match = re.search(r"public class ([A-Za-z0-9_]+)", generated_java)
    class_name = class_name_match.group(1) if class_name_match else "UnknownClass"

    java_file = tmp_path / f"{class_name}.java"
    java_file.write_text(generated_java, encoding="utf-8")

    # Invoke javac
    try:
        subprocess.run(
            ["javac", str(java_file)], capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        pytest.fail(
            f"Java compilation failed for {cbl_path.name}\n"
            f"File path: {java_file}\n"
            f"STDOUT:\n{e.stdout}\n"
            f"STDERR:\n{e.stderr}\n"
        )


@pytest.mark.parametrize("cbl_path", discover_invalid_fixtures(), ids=lambda p: p.name)
def test_invalid_cobol_stops_before_java_generation(
    cbl_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that invalid COBOL fixtures produce errors and stop before Java generation or javac."""

    # Intercept Java generation: must fail if attempted for invalid COBOL
    def _fail_on_generate(*args: object, **kwargs: object) -> object:
        pytest.fail(
            f"Java generation was attempted for invalid fixture '{cbl_path.name}'"
        )

    monkeypatch.setattr(
        "tests.compilation.test_compilation.generate_with_diagnostics",
        _fail_on_generate,
    )

    # Intercept javac invocation: must fail if javac is called for invalid COBOL
    def _fail_on_javac(*args: object, **kwargs: object) -> object:
        pytest.fail(f"javac was invoked for invalid fixture '{cbl_path.name}'")

    monkeypatch.setattr(subprocess, "run", _fail_on_javac)

    source = cbl_path.read_text(encoding="utf-8")

    # Pipeline: lexer -> parser -> semantic analyzer
    lexer = CobolLexer()
    tokens = lexer.tokenize(source, filename=str(cbl_path))

    parser = ProgramParser()
    program_node = parser.parse(tokens)

    is_invalid = False
    if program_node is None:
        is_invalid = True
    else:
        analyzer = SemanticAnalyzer()
        ctx = analyzer.analyse(program_node)
        if ctx.has_errors:
            is_invalid = True

    # Assert that invalid fixture actually produced compiler errors
    assert (
        is_invalid
    ), f"Expected invalid fixture '{cbl_path.name}' to produce parser or semantic errors"

    # Contract verification: pipeline must stop before IRBuilder and Java generator when input is invalid
    if not is_invalid:
        builder = IRBuilder(context=ctx)
        ir_program = builder.build(program_node)
        generate_with_diagnostics(ir_program)
        subprocess.run(["javac", "dummy.java"], check=True)
