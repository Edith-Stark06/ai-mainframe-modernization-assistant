"""
Production Analysis Service.

Purpose:
    Provide :class:`AnalysisService` — the production entry point for executing
    the complete COBOL analysis pipeline.  The service orchestrates:

    1. Source reading
    2. Lexical analysis (``CobolLexer``)
    3. Parsing (``ProgramParser``)
    4. Semantic analysis (``SemanticAnalyzer``)
    5. IR construction (``IRBuilder``)
    6. Java field construction (``build_fields_from_symbols``)
    7. Java code generation (``generate_with_diagnostics``)

    The service returns an :class:`~app.analysis.models.AnalysisResult` that
    bundles the generated Java source with all collected diagnostics.

Responsibilities:
    - Accept a COBOL source file path.
    - Execute every compiler stage in the exact order listed above.
    - Collect semantic and backend diagnostics.
    - Return a structured :class:`~app.analysis.models.AnalysisResult`.
    - Catch unexpected exceptions and report them in the result.

Non-responsibilities:
    - FastAPI endpoints or REST exposure.
    - AST / IR / Java source serialization to JSON.
    - Database persistence or artifact storage.
    - Parser, lexer, semantic analyser, IR builder, or Java generator
      implementation changes.

Dependencies:
    - :mod:`app.analysis.models`               — ``AnalysisResult``.
    - :mod:`app.backend.java.generator`        — ``build_fields_from_symbols``,
                                                 ``generate_with_diagnostics``.
    - :mod:`app.ir.builder`                    — ``IRBuilder``.
    - :mod:`app.parser.lexer.lexer`            — ``CobolLexer``.
    - :mod:`app.parser.semantic.analyzer`       — ``SemanticAnalyzer``.
    - :mod:`app.parser.semantic.symbols`        — ``VariableSymbol``.
    - :mod:`app.parser.syntax.program_parser`   — ``ProgramParser``.
    - Loguru for structured logging.
    - Python standard library (``pathlib``).

Examples:
    Analyzing a COBOL source file::

        from app.analysis.service import AnalysisService

        service = AnalysisService()
        result = service.analyze_file("examples/hello.cbl")
        result.success        # True
        result.java_source    # "public class Hello { ... }"
        result.semantic_diagnostics  # []

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from app.analysis.models import AnalysisResult
from app.backend.java.generator import (
    build_fields_from_symbols,
    generate_with_diagnostics,
)
from app.ir.builder import IRBuilder
from app.parser.lexer.lexer import CobolLexer
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.semantic.symbols import VariableSymbol
from app.parser.syntax.program_parser import ProgramParser

__all__ = ["AnalysisService"]


class AnalysisService:
    """
    Production service that orchestrates the COBOL analysis pipeline.

    The service is stateless and may be instantiated once and reused for
    multiple analyses, or instantiated per analysis call.
    """

    def analyze_file(self, source_path: str | Path) -> AnalysisResult:
        """
        Execute the full COBOL analysis pipeline on *source_path*.

        Args:
            source_path:
                Absolute or relative path to the COBOL source file.

        Returns:
            An :class:`~app.analysis.models.AnalysisResult` carrying the
            generated Java source, diagnostics, and success status.
        """
        path = Path(source_path)

        # ------------------------------------------------------------------
        # Stage 0 — read source
        # ------------------------------------------------------------------
        logger.debug("AnalysisService: reading source file '{}'.", path)

        try:
            source = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error("AnalysisService: source file not found: {}.", path)
            return AnalysisResult(
                java_source="",
                backend_diagnostics=[],
                semantic_diagnostics=[],
                success=False,
                error=FileNotFoundError(f"file not found: {path}"),
                ast=None,
                ir=None,
            )
        except OSError as exc:
            logger.error("AnalysisService: cannot read '{}': {}.", path, exc)
            return AnalysisResult(
                java_source="",
                backend_diagnostics=[],
                semantic_diagnostics=[],
                success=False,
                error=exc,
                ast=None,
                ir=None,
            )

        # ------------------------------------------------------------------
        # Stage 1 — lex
        # ------------------------------------------------------------------
        logger.debug("AnalysisService: lexing source.")
        lexer = CobolLexer()

        try:
            tokens = lexer.tokenize(source, filename=str(path))
        except Exception as exc:
            logger.error("AnalysisService: lex error in '{}': {}.", path, exc)
            return AnalysisResult(
                java_source="",
                backend_diagnostics=[],
                semantic_diagnostics=[],
                success=False,
                error=exc,
                ast=None,
                ir=None,
            )
        logger.debug("AnalysisService: lexer produced {} token(s).", len(tokens))

        # ------------------------------------------------------------------
        # Stage 2 — parse
        # ------------------------------------------------------------------
        logger.debug("AnalysisService: parsing token stream.")
        parser = ProgramParser()

        try:
            ast = parser.parse(tokens)
        except Exception as exc:
            logger.error("AnalysisService: parse error in '{}': {}.", path, exc)
            return AnalysisResult(
                java_source="",
                backend_diagnostics=[],
                semantic_diagnostics=[],
                success=False,
                error=exc,
                ast=None,
                ir=None,
            )
        logger.debug("AnalysisService: parsing complete.")

        # ------------------------------------------------------------------
        # Stage 3 — semantic analysis
        # ------------------------------------------------------------------
        logger.debug("AnalysisService: running semantic analysis.")
        analyzer = SemanticAnalyzer()

        try:
            semantic_ctx = analyzer.analyse(ast)
        except Exception as exc:
            logger.error("AnalysisService: semantic error in '{}': {}.", path, exc)
            return AnalysisResult(
                java_source="",
                backend_diagnostics=[],
                semantic_diagnostics=[],
                success=False,
                error=exc,
                ast=ast,
                ir=None,
            )
        logger.debug(
            "AnalysisService: semantic analysis complete. errors={}.",
            semantic_ctx.error_count,
        )

        # ------------------------------------------------------------------
        # Stage 4 — IR construction
        # ------------------------------------------------------------------
        logger.debug("AnalysisService: building IR.")
        builder = IRBuilder(context=semantic_ctx)

        try:
            ir_program = builder.build(ast)
        except Exception as exc:
            logger.error("AnalysisService: IR error in '{}': {}.", path, exc)
            return AnalysisResult(
                java_source="",
                backend_diagnostics=[],
                semantic_diagnostics=semantic_ctx.diagnostics,
                success=False,
                error=exc,
                ast=ast,
                ir=None,
            )
        logger.debug("AnalysisService: IR build complete.")

        # ------------------------------------------------------------------
        # Stage 5 — Java field construction
        # ------------------------------------------------------------------
        logger.debug("AnalysisService: building Java fields.")
        vars = [
            s
            for s in semantic_ctx.symbol_table.all_symbols()
            if isinstance(s, VariableSymbol)
        ]
        diags: list[Any] = []

        try:
            fields = build_fields_from_symbols(vars, diags)
        except Exception as exc:
            logger.error(
                "AnalysisService: field construction error in '{}': {}.",
                path,
                exc,
            )
            return AnalysisResult(
                java_source="",
                backend_diagnostics=diags,
                semantic_diagnostics=semantic_ctx.diagnostics,
                success=False,
                error=exc,
                ast=ast,
                ir=ir_program,
            )
        logger.debug("AnalysisService: built {} Java field(s).", len(fields))

        # ------------------------------------------------------------------
        # Stage 6 — Java code generation
        # ------------------------------------------------------------------
        logger.debug("AnalysisService: generating Java source.")
        try:
            gen_result = generate_with_diagnostics(ir_program, fields)
        except Exception as exc:
            logger.error("AnalysisService: generation error in '{}': {}.", path, exc)
            return AnalysisResult(
                java_source="",
                backend_diagnostics=diags,
                semantic_diagnostics=semantic_ctx.diagnostics,
                success=False,
                error=exc,
                ast=ast,
                ir=ir_program,
            )
        logger.debug(
            "AnalysisService: Java generation complete ({} diagnostics).",
            len(gen_result.diagnostics),
        )

        return AnalysisResult(
            java_source=gen_result.source,
            backend_diagnostics=gen_result.diagnostics + diags,
            semantic_diagnostics=semantic_ctx.diagnostics,
            success=not semantic_ctx.has_errors,
            error=None,
            ast=ast,
            ir=ir_program,
        )
