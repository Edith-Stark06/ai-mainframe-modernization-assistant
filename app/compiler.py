"""
Compiler Driver — COBOL Frontend Pipeline.

Purpose:
    Provide a standalone, command-line entry point that executes the complete
    COBOL compiler frontend pipeline on a single source file and prints the
    resulting Intermediate Representation to standard output.

    The driver is independent of the FastAPI application and can be invoked
    directly::

        python -m app.compiler <source-file>

Pipeline (in order):
    1. **Read** the source file from the filesystem.
    2. **Lex** the source into a token stream via
       :class:`~app.parser.lexer.lexer.CobolLexer`.
    3. **Parse** the token stream into an AST via
       :class:`~app.parser.syntax.program_parser.ProgramParser`.
    4. **Analyse** the AST via
       :class:`~app.parser.semantic.analyzer.SemanticAnalyzer`.
    5. **Build** the Intermediate Representation via
       :class:`~app.ir.builder.IRBuilder`.
    6. **Print** the IR using :func:`~app.ir.printer.pretty_print`.

Exit codes:
    - **0** — compilation succeeded (no semantic errors).
    - **1** — source file not found or unreadable.
    - **2** — compilation completed with semantic errors.

Responsibilities:
    - Parse CLI arguments (file path).
    - Execute each pipeline stage in order.
    - Print parser diagnostics to stderr.
    - Print semantic diagnostics to stderr.
    - Print the pretty-printed IR to stdout.
    - Return an appropriate exit code.

Non-responsibilities:
    - Java / Spring Boot generation.
    - Optimisation passes.
    - COPY book expansion.
    - REST API or web serving.

Dependencies:
    - :mod:`app.parser.lexer.lexer`             — ``CobolLexer``.
    - :mod:`app.parser.syntax.program_parser`   — ``ProgramParser``.
    - :mod:`app.parser.semantic.analyzer`       — ``SemanticAnalyzer``.
    - :mod:`app.ir.builder`                     — ``IRBuilder``.
    - :mod:`app.ir.printer`                     — ``pretty_print``.
    - Python standard library (``argparse``, ``sys``, ``pathlib``).

Examples:
    Running against a COBOL file::

        python -m app.compiler examples/hello.cbl

    Running against a file with errors::

        python -m app.compiler examples/invalid.cbl
        # Prints diagnostics to stderr; exits with code 2.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from app.ir.builder import IRBuilder
from app.ir.printer import pretty_print
from app.parser.lexer.lexer import CobolLexer
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.syntax.program_parser import ProgramParser

__all__ = ["compile_file", "main"]

# ---------------------------------------------------------------------------
# Public compile function
# ---------------------------------------------------------------------------


def compile_file(source_path: Path) -> int:
    """
    Execute the full frontend pipeline on *source_path*.

    Args:
        source_path:
            Absolute or relative path to the COBOL source file.

    Returns:
        Exit code: ``0`` for success, ``1`` for I/O error, ``2`` for
        compilation errors.
    """
    # ------------------------------------------------------------------
    # Stage 0 — read source
    # ------------------------------------------------------------------
    logger.debug("Compiler: reading source file '{}'.", source_path)

    try:
        source = source_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        print(
            f"error: file not found: {source_path}",
            file=sys.stderr,
        )
        logger.error("Compiler: source file not found: {}.", source_path)
        return 1
    except OSError as exc:
        print(
            f"error: cannot read file '{source_path}': {exc}",
            file=sys.stderr,
        )
        logger.error("Compiler: cannot read '{}': {}.", source_path, exc)
        return 1

    # ------------------------------------------------------------------
    # Stage 1 — lex
    # ------------------------------------------------------------------
    logger.debug("Compiler: lexing source.")
    lexer = CobolLexer()
    from app.parser.lexer.lexer_exceptions import LexerError

    try:
        tokens = lexer.tokenize(source, filename=str(source_path))
    except LexerError as exc:
        print(f"lex error: {exc}", file=sys.stderr)
        logger.error("Compiler: lex error in '{}': {}.", source_path, exc)
        return 2
    logger.debug("Compiler: lexer produced {} token(s).", len(tokens))

    # ------------------------------------------------------------------
    # Stage 2 — parse
    # ------------------------------------------------------------------
    logger.debug("Compiler: parsing token stream.")
    parser = ProgramParser()
    program_node = parser.parse(tokens)
    logger.debug("Compiler: parsing complete.")

    # ------------------------------------------------------------------
    # Stage 3 — semantic analysis
    # ------------------------------------------------------------------
    logger.debug("Compiler: running semantic analysis.")
    analyzer = SemanticAnalyzer()
    ctx = analyzer.analyse(program_node)
    logger.debug("Compiler: semantic analysis complete. errors={}.", ctx.error_count)

    # Print semantic diagnostics
    if ctx.diagnostics:
        _print_semantic_diagnostics(ctx.diagnostics)

    # ------------------------------------------------------------------
    # Stage 4 — IR construction
    # ------------------------------------------------------------------
    logger.debug("Compiler: building IR.")
    builder = IRBuilder(context=ctx)
    ir_program = builder.build(program_node)
    logger.debug("Compiler: IR build complete.")

    # ------------------------------------------------------------------
    # Stage 5 — pretty-print IR to stdout
    # ------------------------------------------------------------------
    print(pretty_print(ir_program))

    # ------------------------------------------------------------------
    # Determine exit code
    # ------------------------------------------------------------------
    if ctx.has_errors:
        logger.info("Compiler: finished with {} semantic error(s).", ctx.error_count)
        return 2

    logger.info("Compiler: finished successfully.")
    return 0


# ---------------------------------------------------------------------------
# Diagnostic formatting helpers
# ---------------------------------------------------------------------------


def _print_semantic_diagnostics(diagnostics: list) -> None:  # type: ignore[type-arg]
    """Print *diagnostics* to stderr in a human-readable format."""
    print("\nSemantic Diagnostics:", file=sys.stderr)
    print("-" * 40, file=sys.stderr)
    for diag in diagnostics:
        pos = diag.position
        severity = (
            diag.severity.name if hasattr(diag.severity, "name") else str(diag.severity)
        )
        location = f"{pos.filename}:{pos.line}:{pos.column}" if pos else "<unknown>"
        print(
            f"  [{severity}] {location}\n  {diag.message}\n",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """
    Parse command-line arguments and invoke :func:`compile_file`.

    Args:
        argv:
            Argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Integer exit code.
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.compiler",
        description=(
            "AI Mainframe Modernization — COBOL Frontend Compiler Driver.\n"
            "Executes the complete Lexer → Parser → Semantic → IR pipeline "
            "and prints the resulting Intermediate Representation."
        ),
    )
    parser.add_argument(
        "source",
        metavar="<source-file>",
        help="Path to the COBOL source file (.cbl / .cob).",
    )

    args = parser.parse_args(argv)
    source_path = Path(args.source)
    return compile_file(source_path)


if __name__ == "__main__":
    sys.exit(main())
