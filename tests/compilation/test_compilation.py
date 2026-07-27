"""
Java Compilation Test Runner.

Verifies the complete generated Java output can be successfully compiled by javac.
"""

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
from app.parser.syntax.program_parser import ProgramParser
from app.parser.semantic.symbols import SymbolKind


def discover_fixtures() -> list[Path]:
    """Discover .cbl fixtures from golden and regression/invalid directories."""
    base_dir = Path(__file__).parent.parent

    fixtures = []

    golden_dir = base_dir / "golden"
    if golden_dir.exists():
        fixtures.extend(golden_dir.glob("*.cbl"))

    invalid_dir = base_dir / "regression" / "fixtures" / "invalid"
    if invalid_dir.exists():
        fixtures.extend(invalid_dir.glob("*.cbl"))

    return sorted(fixtures)


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

    # If the COBOL is invalid, we shouldn't attempt to generate or compile Java.
    if ctx.has_errors or program_node is None:
        # We verified that the invalid fixture did not reach javac.
        return

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
    # We must determine the class name from the generated Java or IR program to name the file correctly,
    # as Java requires the public class name to match the file name.
    # IRProgram.name has the program ID. The Java generator capitalizes it and converts hyphens,
    # but let's extract the actual public class name from the generated output.
    import re

    class_name_match = re.search(r"public class ([A-Za-z0-9_]+)", generated_java)
    class_name = class_name_match.group(1) if class_name_match else "UnknownClass"

    java_file = tmp_path / f"{class_name}.java"
    java_file.write_text(generated_java, encoding="utf-8")

    # Invoke javac
    try:
        process = subprocess.run(
            ["javac", str(java_file)], capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        pytest.fail(
            f"Java compilation failed for {cbl_path.name}\n"
            f"File path: {java_file}\n"
            f"STDOUT:\n{e.stdout}\n"
            f"STDERR:\n{e.stderr}\n"
        )
