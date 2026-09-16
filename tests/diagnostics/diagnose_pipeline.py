"""
End-to-end pipeline diagnostic: source -> lexer -> parser -> AST -> IR ->
flow extraction -> modernization scoring.

Purpose:
    Investigate, without modifying, why a given COBOL source file produces
    "insufficient data" (zero flow nodes/edges, all scores 0%) from the real
    modernization pipeline. Every stage is driven through the exact
    production classes/functions the application uses -- nothing here is a
    reimplementation or a parallel/mocked pipeline:

        app.analysis.service.AnalysisService.analyze_file
            -> app.parser.lexer.lexer.CobolLexer.tokenize
            -> app.parser.syntax.program_parser.ProgramParser.parse
            -> app.parser.semantic.analyzer.SemanticAnalyzer.analyse
            -> app.ir.builder.IRBuilder.build
        app.modernization.flow.generator.generate_flow
        app.modernization.scoring.service.calculate_scores

    The only deviation from calling AnalysisService.analyze_file() directly
    is that this script also re-runs the lexer and the parser's internal
    ParserState on the same token stream (via ProgramParser's own division
    parsers) purely to *read* the SyntaxDiagnostic list that parsing
    produces internally -- ProgramParser.parse()'s public return value is
    just the AST; it does not surface parser diagnostics to callers, which
    is itself one of this diagnostic's findings (see the report). No parsing
    or recovery logic is reimplemented; the same ProgramParser instance
    method that AnalysisService relies on is called directly, once.

Usage (from the repository root):

    python tests/diagnostics/diagnose_pipeline.py <path-to-cobol-file>

Or, to run both the comparison fixture and a target file in one go:

    python tests/diagnostics/diagnose_pipeline.py <path-to-cobol-file> --compare

This script intentionally has no pytest assertions -- it is a read-only
diagnostic, not a pass/fail gate. It exits 0 unless the file cannot be read
at all.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.analysis.service import AnalysisService  # noqa: E402
from app.parser.lexer.lexer import CobolLexer  # noqa: E402
from app.parser.lexer.token_types import TokenType  # noqa: E402
from app.parser.syntax.parser_state import ParserState  # noqa: E402
from app.parser.syntax.program_parser import ProgramParser  # noqa: E402
from app.parser.syntax.token_stream import TokenStream  # noqa: E402
from app.modernization.flow.generator import generate_flow  # noqa: E402
from app.modernization.scoring.service import calculate_scores  # noqa: E402

DEFAULT_KNOWN_GOOD_FIXTURE = (
    PROJECT_ROOT / "tests" / "fixtures" / "combined_program.cbl"
)

_STATEMENT_TYPE_ORDER = [
    "DisplayStatementNode",
    "AcceptStatementNode",
    "MoveStatementNode",
    "AddStatementNode",
    "SubtractStatementNode",
    "MultiplyStatementNode",
    "DivideStatementNode",
    "StopRunStatementNode",
    "GobackStatementNode",
    "IfStatementNode",
    "PerformStatementNode",
    "PerformUntilStatementNode",
    "GoToStatementNode",
    "CallStatementNode",
]


def _hr(title: str) -> None:
    print(f"\n{'=' * 10} {title} {'=' * 10}")


def _walk_statements(paragraphs) -> list:
    """Flatten every statement across every paragraph, in source order."""
    statements = []
    for para in paragraphs:
        statements.extend(para.statements)
    return statements


def diagnose(path: Path) -> dict:
    """Run the real production pipeline against *path* and print a full report."""
    result: dict = {"path": str(path)}

    # ------------------------------------------------------------------
    # SOURCE
    # ------------------------------------------------------------------
    _hr("SOURCE")
    print(f"filename: {path.name}")
    if not path.exists():
        print(f"FATAL: file does not exist: {path}")
        result["fatal"] = "file not found"
        return result

    source = path.read_text(encoding="utf-8")
    line_count = source.count("\n") + (1 if source and not source.endswith("\n") else 0)
    print(f"line count: {line_count}")
    print(f"character count: {len(source)}")
    print(f"byte count (utf-8): {len(source.encode('utf-8'))}")
    result["line_count"] = line_count
    result["char_count"] = len(source)

    # ------------------------------------------------------------------
    # LEXER (app.parser.lexer.lexer.CobolLexer)
    # ------------------------------------------------------------------
    _hr("LEXER")
    lexer = CobolLexer()
    tokens = None
    try:
        tokens = lexer.tokenize(source, filename=str(path))
    except Exception as exc:  # noqa: BLE001 - diagnostic must not crash on any input
        print(f"LEXER RAISED: {type(exc).__name__}: {exc}")
        line_no = getattr(exc, "line", None)
        col_no = getattr(exc, "column", None)
        if line_no:
            source_lines = source.splitlines()
            print(f"source line {line_no}, column {col_no}:")
            for ln in range(
                max(1, line_no - 2), min(len(source_lines), line_no + 2) + 1
            ):
                marker = ">>" if ln == line_no else "  "
                print(f"  {marker} {ln:5}: {source_lines[ln - 1]}")
                if ln == line_no and col_no:
                    print("        " + " " * (col_no - 1) + "^")
        print(
            "Lexing failed as a single hard raise (not a recoverable "
            "per-token error) -- CobolLexer.tokenize() does not return a "
            "partial token list on failure, and AnalysisService.analyze_file() "
            "catches this exception and returns immediately with ast=None, "
            "ir=None, success=False. The parser is never invoked."
        )
        print("AST nodes produced: 0 (parsing did not run)")
        print("IR produced: 0 (IR construction did not run)")
        result["fatal"] = f"lexer raised: {exc}"
        result["lexer_error_line"] = line_no
        result["lexer_error_column"] = col_no

    if tokens is not None:
        unknown_tokens = [t for t in tokens if t.type is TokenType.UNKNOWN]
        print(f"token count (incl. EOF): {len(tokens)}")
        print(f"UNKNOWN token count: {len(unknown_tokens)}")
        if unknown_tokens:
            print("first 10 UNKNOWN tokens (line, lexeme):")
            for t in unknown_tokens[:10]:
                print(f"  line {t.position.line}: {t.lexeme!r}")
        print("first 20 token types:")
        print("  " + ", ".join(t.type.name for t in tokens[:20]))
        result["token_count"] = len(tokens)
        result["unknown_token_count"] = len(unknown_tokens)

    # ------------------------------------------------------------------
    # AST (app.parser.syntax.program_parser.ProgramParser)
    # ------------------------------------------------------------------
    _hr("AST")
    ast = None
    if tokens is None:
        print("skipped: lexing did not produce a token stream.")
    else:
        parser = ProgramParser()
        try:
            ast = parser.parse(tokens)
        except Exception as exc:  # noqa: BLE001
            print(f"PARSER RAISED: {type(exc).__name__}: {exc}")
            result["fatal"] = f"parser raised: {exc}"
        else:
            print("parse() completed without raising: True")

    paragraphs: list = []
    statements: list = []

    if ast is None:
        print("skipped: no AST was produced.")
        result["parser_diagnostic_count"] = 0
        result["divisions_present"] = 0
        result["paragraph_count"] = 0
        result["statement_count"] = 0
        result["statement_type_counts"] = {}
    else:
        # ast is only ever set (above) inside the branch where tokens was
        # already proven non-None.
        assert tokens is not None
        # ProgramParser.parse() does not return parser-level SyntaxDiagnostics
        # to the caller (AnalysisService does not see them either). To surface
        # them here we call the same production ParserState/ProgramParser
        # machinery directly -- no new parsing logic, just reading the
        # diagnostics list that a second, identical parse run collects.
        diag_state = ParserState(TokenStream(tokens))
        try:
            parser._parse_program(
                diag_state
            )  # same production method AnalysisService's parser.parse() calls internally
        except Exception as exc:  # noqa: BLE001
            print(
                f"(diagnostic re-parse for diagnostics raised: {type(exc).__name__}: {exc})"
            )
        print(f"parser diagnostic count: {diag_state.error_count}")
        if diag_state.diagnostics:
            print("first 10 parser diagnostics:")
            for d in diag_state.diagnostics[:10]:
                print(f"  line {d.line}: [{d.context}] {d.message}")
        result["parser_diagnostic_count"] = diag_state.error_count

        divisions_present = sum(
            1
            for d in (
                ast.identification_division,
                ast.environment_division,
                ast.data_division,
                ast.procedure_division,
            )
            if d is not None
        )
        print(f"divisions present: {divisions_present} / 4")
        print(f"  identification_division: {ast.identification_division is not None}")
        print(f"  environment_division:    {ast.environment_division is not None}")
        print(f"  data_division:           {ast.data_division is not None}")
        print(f"  procedure_division:      {ast.procedure_division is not None}")
        result["divisions_present"] = divisions_present

        if ast.procedure_division is None:
            print(
                "procedure_division is None -- no paragraphs, no statements possible."
            )
            result["paragraph_count"] = 0
            result["statement_count"] = 0
        else:
            paragraphs = list(ast.procedure_division.paragraphs)
            statements = _walk_statements(paragraphs)
            result["paragraph_count"] = len(paragraphs)
            result["statement_count"] = len(statements)

        print(f"paragraph count: {len(paragraphs)}")
        if paragraphs:
            print("paragraphs (name: statement count):")
            for p in paragraphs:
                print(f"  {p.name}: {len(p.statements)}")
        print(f"total statement count: {len(statements)}")

        type_counts: Counter = Counter(type(s).__name__ for s in statements)
        print("statement counts by type:")
        seen_types = set(type_counts)
        for stype in _STATEMENT_TYPE_ORDER:
            if stype in type_counts:
                print(f"  {stype}: {type_counts[stype]}")
        extra_types = seen_types - set(_STATEMENT_TYPE_ORDER)
        for stype in sorted(extra_types):
            print(f"  {stype}: {type_counts[stype]}  (not in expected list)")
        result["statement_type_counts"] = dict(type_counts)

        print(f"IF statements: {type_counts.get('IfStatementNode', 0)}")
        print(
            "PERFORM statements (simple + UNTIL): "
            f"{type_counts.get('PerformStatementNode', 0) + type_counts.get('PerformUntilStatementNode', 0)}"
        )
        print(f"GO TO statements: {type_counts.get('GoToStatementNode', 0)}")
        print(f"CALL statements: {type_counts.get('CallStatementNode', 0)}")
        arithmetic = sum(
            type_counts.get(t, 0)
            for t in (
                "AddStatementNode",
                "SubtractStatementNode",
                "MultiplyStatementNode",
                "DivideStatementNode",
            )
        )
        print(f"arithmetic statements (ADD/SUBTRACT/MULTIPLY/DIVIDE): {arithmetic}")

    # ------------------------------------------------------------------
    # Statement-loss check: compare recognized statements against verbs
    # actually present in the source text, to catch verbs the parser has
    # no AST node for at all (this does not reimplement parsing -- it is
    # a plain text scan used only to explain a *count* discrepancy).
    # ------------------------------------------------------------------
    _hr("SOURCE-VS-AST VERB CHECK (diagnostic only, not part of the parser)")
    unsupported_verb_lines: list[tuple[int, str]] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        first_word = stripped.split()[0].rstrip(".") if stripped.split() else ""
        if first_word in {
            "OPEN",
            "CLOSE",
            "READ",
            "WRITE",
            "REWRITE",
            "DELETE",
            "EVALUATE",
            "COMPUTE",
            "STRING",
            "UNSTRING",
            "INITIALIZE",
            "SEARCH",
            "SORT",
            "SET",
            "INSPECT",
        }:
            unsupported_verb_lines.append((lineno, first_word))
    if unsupported_verb_lines:
        print(
            f"source lines starting with a verb that has NO dedicated AST "
            f"statement node ({len(unsupported_verb_lines)} occurrence(s)):"
        )
        counts = Counter(v for _, v in unsupported_verb_lines)
        for verb, count in counts.most_common():
            print(f"  {verb}: {count}")
        print(
            f"first occurrence: line {unsupported_verb_lines[0][0]}: {unsupported_verb_lines[0][1]}"
        )
    else:
        print("no unsupported verbs detected in source text.")
    result["unsupported_verb_occurrences"] = len(unsupported_verb_lines)
    result["unsupported_verb_first_line"] = (
        unsupported_verb_lines[0][0] if unsupported_verb_lines else None
    )

    # ------------------------------------------------------------------
    # Run the real AnalysisService end to end (this is what the
    # application actually calls) for IR/flow/scoring.
    # ------------------------------------------------------------------
    service = AnalysisService()
    analysis = service.analyze_file(path)

    # ------------------------------------------------------------------
    # IR (app.ir.builder.IRBuilder, via AnalysisService)
    # ------------------------------------------------------------------
    _hr("IR")
    print(f"AnalysisService.analyze_file success: {analysis.success}")
    if analysis.error is not None:
        print(
            f"AnalysisService error: {type(analysis.error).__name__}: {analysis.error}"
        )
    result["analysis_success"] = analysis.success

    if analysis.ir is None:
        print("ir is None -- IR construction did not complete (see error above).")
        result["ir_built"] = False
        result["ir_module_count"] = 0
        result["ir_function_count"] = 0
        result["ir_block_count"] = 0
        result["ir_instruction_count"] = 0
    else:
        result["ir_built"] = True
        modules = list(analysis.ir.modules)
        functions = [fn for mod in modules for fn in mod.functions]
        blocks = [b for fn in functions for b in fn.blocks]
        instructions = [i for b in blocks for i in b.instructions]
        print("ir construction succeeded: True")
        print(f"module count: {len(modules)}")
        print(f"function count: {len(functions)}")
        for fn in functions:
            print(f"  function {fn.name}: {len(fn.blocks)} block(s)")
        print(f"basic block count: {len(blocks)}")
        print(f"instruction count: {len(instructions)}")
        # Known, separately-documented limitation: IRBuilder does not
        # lower control flow into a multi-block CFG (IRConditionalBranch
        # is defined but never constructed) -- every function is exactly
        # one flat block, so there is never more than 0 inter-block edges
        # at the IR level. This is not something this diagnostic
        # investigates further; it is unrelated to flow/scoring, which
        # operate on FlowGenerationVisitor's own IRCall traversal, not on
        # IR-level basic-block edges.
        print(
            "control-flow edge count (inter-block, IR level): 0 (IRBuilder does not build a CFG; documented, separate, pre-existing limitation)"
        )
        instr_type_counts = Counter(type(i).__name__ for i in instructions)
        print("instruction counts by type:")
        for itype, count in instr_type_counts.most_common():
            print(f"  {itype}: {count}")
        result["ir_module_count"] = len(modules)
        result["ir_function_count"] = len(functions)
        result["ir_block_count"] = len(blocks)
        result["ir_instruction_count"] = len(instructions)

    if analysis.semantic_diagnostics:
        print(f"semantic diagnostic count: {len(analysis.semantic_diagnostics)}")
        for d in analysis.semantic_diagnostics[:10]:
            print(f"  {d}")
    else:
        print("semantic diagnostic count: 0")

    # ------------------------------------------------------------------
    # FLOW (app.modernization.flow.generator.generate_flow)
    # ------------------------------------------------------------------
    _hr("FLOW")
    flow = generate_flow(analysis)
    print(f"flow.id: {flow.id}")
    print(f"node count: {len(flow.nodes)}")
    print(f"edge count: {len(flow.edges)}")
    if flow.nodes:
        print("nodes:")
        for n in flow.nodes:
            print(f"  {n.id}  [{n.node_type.name}]  name={n.name!r}")
    else:
        print(
            "0 nodes. generate_flow() returns an empty Flow whenever "
            "`not analysis.ir` is true (analysis.ir is None, OR analysis.ir "
            "is falsy because IRProgram has zero modules -- IRProgram "
            "supports __len__ returning the module count). It also produces "
            "0 nodes if IR was built but contains functions with no "
            "IRFunction nodes for FlowGenerationVisitor.visit_function to "
            "visit (e.g. a paragraph with a body but with the outer IR "
            "function/module wrapping empty or absent)."
        )
    result["flow_node_count"] = len(flow.nodes)
    result["flow_edge_count"] = len(flow.edges)

    # A paragraph in the AST is the closest source-level analogue to a
    # flow node's "PROCESS" identity for this codebase's IR shape (see
    # generator.py: one IRFunction is expected to correspond to the
    # program's entry, not one per paragraph -- confirm/refute this
    # empirically per file rather than assuming).
    print(f"paragraph count (from AST, for comparison): {len(paragraphs)}")

    # ------------------------------------------------------------------
    # MODERNIZATION (app.modernization.scoring.service.calculate_scores)
    # ------------------------------------------------------------------
    _hr("MODERNIZATION")
    score = calculate_scores(analysis, flow)
    print(f"complexity_score: {score.complexity_score}")
    print(f"coupling_score: {score.coupling_score}")
    print(f"overall_readiness: {score.overall_readiness}")
    print(f"metadata: {dict(score.metadata)}")
    insufficient = bool(score.metadata.get("insufficient_data"))
    print(f"insufficient_data: {insufficient}")
    if insufficient:
        print(
            "WHY: calculate_scores() sets insufficient_data=True whenever "
            f"len(flow.nodes) == 0 (observed node count: {len(flow.nodes)}). "
            "This is a downstream consequence of the FLOW section above, "
            "which is itself a downstream consequence of the IR/AST sections."
        )
    result["complexity_score"] = score.complexity_score
    result["coupling_score"] = score.coupling_score
    result["overall_readiness"] = score.overall_readiness
    result["insufficient_data"] = insufficient

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path", type=Path, help="Path to a COBOL source file to diagnose."
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help=f"Also run the known-good fixture ({DEFAULT_KNOWN_GOOD_FIXTURE.relative_to(PROJECT_ROOT)}) first, for comparison.",
    )
    args = parser.parse_args()

    results = {}
    if args.compare:
        print("#" * 70)
        print(f"# KNOWN-GOOD FIXTURE: {DEFAULT_KNOWN_GOOD_FIXTURE}")
        print("#" * 70)
        results["known_good"] = diagnose(DEFAULT_KNOWN_GOOD_FIXTURE)

    print("\n" + "#" * 70)
    print(f"# TARGET FILE: {args.path}")
    print("#" * 70)
    results["target"] = diagnose(args.path)

    if args.compare:
        _hr("SUMMARY COMPARISON")
        kg = results["known_good"]
        tg = results["target"]
        fields = [
            "line_count",
            "token_count",
            "unknown_token_count",
            "paragraph_count",
            "statement_count",
            "unsupported_verb_occurrences",
            "ir_built",
            "ir_function_count",
            "ir_block_count",
            "ir_instruction_count",
            "flow_node_count",
            "flow_edge_count",
            "insufficient_data",
        ]
        header = f"{'field':32} {'known_good':>15} {'target':>15}"
        print(header)
        print("-" * len(header))
        for f in fields:
            print(f"{f:32} {str(kg.get(f)):>15} {str(tg.get(f)):>15}")


if __name__ == "__main__":
    main()
