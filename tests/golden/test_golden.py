"""
Golden File Test Runner.

Verifies the complete generated Java output against expected 'golden' files.
"""

import difflib
import os
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
    """Discover all .cbl fixtures in the golden directory."""
    base_dir = Path(__file__).parent
    fixtures = []
    for cbl_file in base_dir.glob("*.cbl"):
        fixtures.append(cbl_file)
    return sorted(fixtures)


def normalize_output(text: str) -> str:
    """Normalize line endings and trailing whitespace for comparison."""
    lines = text.replace("\r\n", "\n").split("\n")
    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in lines]
    # Rejoin and ensure a single trailing newline if not empty
    result = "\n".join(lines).strip()
    return result + "\n" if result else ""


@pytest.mark.parametrize("cbl_path", discover_fixtures(), ids=lambda p: p.name)
def test_golden_file(cbl_path: Path) -> None:
    """Run the compiler pipeline and compare against the golden Java file."""
    java_path = cbl_path.with_suffix(".java")
    source = cbl_path.read_text(encoding="utf-8")

    # Pipeline
    lexer = CobolLexer()
    tokens = lexer.tokenize(source, filename=str(cbl_path))

    parser = ProgramParser()
    program_node = parser.parse(tokens)

    analyzer = SemanticAnalyzer()
    ctx = analyzer.analyse(program_node)

    if ctx.has_errors:
        pytest.fail(f"Compiler encountered semantic errors on {cbl_path.name}")

    builder = IRBuilder(context=ctx)
    ir_program = builder.build(program_node)

    var_symbols = ctx.symbol_table.symbols_of_kind(SymbolKind.VARIABLE)
    fields = build_fields_from_symbols(var_symbols)

    result = generate_with_diagnostics(ir_program, fields)
    generated_java = result.source

    normalized_generated = normalize_output(generated_java)

    update_golden = os.environ.get("UPDATE_GOLDEN") == "1"

    if update_golden:
        java_path.write_text(normalized_generated, encoding="utf-8")
        # Automatically pass when updating
        return

    if not java_path.exists():
        pytest.fail(
            f"Golden file {java_path.name} not found. Run with UPDATE_GOLDEN=1 to generate it."
        )

    golden_java = java_path.read_text(encoding="utf-8")
    normalized_golden = normalize_output(golden_java)

    if normalized_generated != normalized_golden:
        diff = difflib.unified_diff(
            normalized_golden.splitlines(keepends=True),
            normalized_generated.splitlines(keepends=True),
            fromfile=f"a/{java_path.name}",
            tofile=f"b/{java_path.name}",
        )
        diff_text = "".join(diff)
        pytest.fail(f"Golden file mismatch for {cbl_path.name}:\n\n{diff_text}")
