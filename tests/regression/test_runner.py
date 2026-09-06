"""
Regression test runner.

Automatically discovers `.cbl` fixtures in `tests/regression/fixtures/` and
validates them against expectations in their corresponding `.json` sidecar files.
"""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from app.backend.java.generator import (
    build_fields_from_symbols,
    generate_with_diagnostics,
)
from app.ir.builder import IRBuilder
from app.parser.lexer.lexer import CobolLexer
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.syntax.program_parser import ProgramParser
from app.parser.lexer.lexer_exceptions import LexerError
from app.parser.syntax.parser_exceptions import ParserError


class FixtureExpectations(BaseModel):
    success: bool
    expected_java_constructs: list[str] = Field(default_factory=list)
    expected_diagnostics: list[str] = Field(default_factory=list)


def discover_fixtures() -> list[tuple[Path, Path]]:
    """Discover all .cbl fixtures and their .json sidecars."""
    base_dir = Path(__file__).parent / "fixtures"
    fixtures = []
    for cbl_file in base_dir.rglob("*.cbl"):
        json_file = cbl_file.with_suffix(".json")
        if json_file.exists():
            fixtures.append((cbl_file, json_file))
    return sorted(fixtures)


@pytest.mark.parametrize(
    "cbl_path, json_path",
    discover_fixtures(),
    ids=lambda x: str(x.name) if isinstance(x, Path) else x,
)
def test_regression_fixture(cbl_path: Path, json_path: Path) -> None:
    """Execute the full compiler pipeline on a regression fixture and validate."""
    # 1. Load Expectations
    with open(json_path, encoding="utf-8") as f:
        expectations_data = json.load(f)
    expectations = FixtureExpectations(**expectations_data)

    # 2. Read Source
    source = cbl_path.read_text(encoding="utf-8")

    all_diagnostics = []
    java_source = ""
    pipeline_success = True

    try:
        # 3. Lex
        lexer = CobolLexer()
        tokens = lexer.tokenize(source, filename=str(cbl_path))

        # 4. Parse
        parser = ProgramParser()
        program_node = parser.parse(tokens)

        # 5. Semantic Analysis
        analyzer = SemanticAnalyzer()
        ctx = analyzer.analyse(program_node)
        for diag in ctx.diagnostics:
            all_diagnostics.append(diag.message)

        if ctx.has_errors:
            pipeline_success = False
        else:
            # 6. IR Builder
            builder = IRBuilder(context=ctx)
            ir_program = builder.build(program_node)

            from app.parser.semantic.symbols import SymbolKind

            # 7. Java Generation
            var_symbols = ctx.symbol_table.symbols_of_kind(SymbolKind.VARIABLE)
            fields = build_fields_from_symbols(var_symbols)
            result = generate_with_diagnostics(ir_program, fields)
            java_source = result.source
            for diag in result.diagnostics:
                all_diagnostics.append(diag.message)
                # Assume any backend diagnostic is a failure for now
                pipeline_success = False

    except (LexerError, ParserError) as e:
        pipeline_success = False
        all_diagnostics.append(str(e))
    except Exception as e:
        pytest.fail(f"Compiler crashed unexpectedly on {cbl_path.name}: {e}")

    # 8. Assertions

    # A) Check Success State
    assert pipeline_success == expectations.success, (
        f"Fixture {cbl_path.name} success state mismatch.\n"
        f"Expected success: {expectations.success}\n"
        f"Actual success: {pipeline_success}\n"
        f"Diagnostics: {all_diagnostics}"
    )

    # B) Check Expected Java Constructs (if successful)
    if expectations.success:
        for construct in expectations.expected_java_constructs:
            assert construct in java_source, (
                f"Fixture {cbl_path.name} missing expected Java construct.\n"
                f"Expected: '{construct}'\n"
                f"Generated Source:\n{java_source}"
            )

    # C) Check Expected Diagnostics (if unsuccessful)
    if not expectations.success:
        for expected_diag in expectations.expected_diagnostics:
            found = any(expected_diag in actual for actual in all_diagnostics)
            assert found, (
                f"Fixture {cbl_path.name} missing expected diagnostic.\n"
                f"Expected to find substring: '{expected_diag}'\n"
                f"Actual diagnostics: {all_diagnostics}"
            )
