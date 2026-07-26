from pathlib import Path
from dataclasses import dataclass
from typing import Any

from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.program_parser import ProgramParser
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.ir.builder import IRBuilder
from app.backend.java.generator import (
    generate_with_diagnostics,
    build_fields_from_symbols,
)


@dataclass
class CompilationResult:
    java_source: str
    backend_diagnostics: list[Any]
    semantic_diagnostics: list[Any]
    success: bool
    error: Exception | None = None


def compile_cobol_pipeline(source_path: str | Path) -> CompilationResult:
    """
    Executes the full compiler pipeline:
    Lexer -> Parser -> Semantic Analysis -> IR -> Java Backend
    """
    path = Path(source_path)
    source = path.read_text(encoding="utf-8")

    try:
        # Lexer
        lexer = CobolLexer()
        tokens = lexer.tokenize(source, filename=str(path))

        # Parser
        parser = ProgramParser()
        ast = parser.parse(tokens)

        # Semantic Analysis
        analyzer = SemanticAnalyzer()
        semantic_ctx = analyzer.analyse(ast)

        # IR Generation
        builder = IRBuilder(context=semantic_ctx)
        ir_program = builder.build(ast)

        # Java Backend
        from app.parser.semantic.symbols import VariableSymbol

        vars = [
            s
            for s in semantic_ctx.symbol_table.all_symbols()
            if isinstance(s, VariableSymbol)
        ]
        diags: list[Any] = []
        fields = build_fields_from_symbols(vars, diags)
        gen_result = generate_with_diagnostics(ir_program, fields)

        return CompilationResult(
            java_source=gen_result.source,
            backend_diagnostics=gen_result.diagnostics + diags,
            semantic_diagnostics=semantic_ctx.diagnostics,
            success=not semantic_ctx.has_errors,
            error=None,
        )
    except Exception as e:
        return CompilationResult(
            java_source="",
            backend_diagnostics=[],
            semantic_diagnostics=[],
            success=False,
            error=e,
        )
