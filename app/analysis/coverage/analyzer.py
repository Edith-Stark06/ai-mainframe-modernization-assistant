"""
Analysis Coverage Analyzer (task #115 — Phase 5).

``compute_coverage(analysis_result, flow=None, business_rules=None)``
turns the Phase 1–4 outputs into a :class:`~app.analysis.coverage.models.CoverageReport`.

Everything here is deterministic and derived from concrete evidence:
token counts, parser diagnostic codes, AST node counts, IR instruction
counts, CFG node/edge counts, dependency edges, and #112 business rules.
No LLM, no parsing, no heuristic "looks fine" judgements.

Denominator choices and their limitations are documented per dimension
in :func:`compute_coverage` and echoed into each dimension's ``detail``.
"""

from __future__ import annotations

from app.analysis.coverage.models import (
    CoverageDimension,
    CoverageReport,
    CoverageStatus,
    UnsupportedSyntaxCoverage,
)
from app.analysis.models import AnalysisResult
from app.modernization.flow.models import EdgeType, Flow, NodeType
from app.parser.ast.statements import (
    IfStatementNode,
    PerformUntilStatementNode,
    StatementNode,
)

__all__ = ["compute_coverage"]

_COMPLETE = 0.999

# Statement-level unsupported / error codes: each one is a procedural
# statement (or statement region) the parser recognised but did not put
# in the AST, so it never reaches IR / CFG / dependency / rule analysis.
_STATEMENT_LOSS_CODES: frozenset[str] = frozenset({"SYN005", "SYN100", "SYN301"})

# Which dimensions each unsupported code degrades.
_CODE_AFFECTS: dict[str, tuple[str, ...]] = {
    "SYN100": (
        "statement",
        "ast",
        "ir",
        "control_flow",
        "dependency",
        "business_rule",
    ),
    "SYN101": ("ast", "ir"),
    "SYN102": ("ast",),
    "SYN200": ("ast", "ir"),
}


def _count_ast_statements(node: object) -> int:
    """Recursively count every StatementNode reachable from *node*."""
    total = 0
    if isinstance(node, StatementNode):
        total += 1
    if isinstance(node, IfStatementNode):
        for child in list(node.then_statements) + list(node.else_statements):
            total += _count_ast_statements(child)
    elif isinstance(node, PerformUntilStatementNode):
        for child in node.statements:
            total += _count_ast_statements(child)
    return total


def _ast_statement_total(analysis_result: AnalysisResult) -> int:
    ast = analysis_result.ast
    if ast is None or ast.procedure_division is None:
        return 0
    total = 0
    for para in ast.procedure_division.paragraphs:
        for stmt in para.statements:
            total += _count_ast_statements(stmt)
    return total


def _count_if_nodes(analysis_result: AnalysisResult) -> int:
    ast = analysis_result.ast
    if ast is None or ast.procedure_division is None:
        return 0

    def walk(node: object) -> int:
        n = 1 if isinstance(node, IfStatementNode) else 0
        if isinstance(node, IfStatementNode):
            for c in list(node.then_statements) + list(node.else_statements):
                n += walk(c)
        elif isinstance(node, PerformUntilStatementNode):
            for c in node.statements:
                n += walk(c)
        return n

    total = 0
    for para in ast.procedure_division.paragraphs:
        for stmt in para.statements:
            total += walk(stmt)
    return total


def _count_data_items(analysis_result: AnalysisResult) -> int:
    ast = analysis_result.ast
    if ast is None or ast.data_division is None:
        return 0
    ws = getattr(ast.data_division, "working_storage", None)
    if ws is None:
        return 0

    def walk(item: object) -> int:
        n = 1
        for child in getattr(item, "children", ()) or ():
            n += walk(child)
        return n

    return sum(walk(i) for i in getattr(ws, "items", ()) or ())


def _diag_code_counts(analysis_result: AnalysisResult) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in analysis_result.syntax_diagnostics:
        code = getattr(d, "code", "SYN?")
        counts[code] = counts.get(code, 0) + 1
    return counts


def _ratio(covered: int, total: int) -> float:
    if total <= 0:
        return 1.0
    return max(0.0, min(1.0, covered / total))


def _status_for(ratio: float, *, had_input: bool) -> CoverageStatus:
    if not had_input:
        return CoverageStatus.NOT_MEASURABLE
    if ratio >= _COMPLETE:
        return CoverageStatus.COMPLETE
    if ratio <= 0.0:
        return CoverageStatus.FAILED
    return CoverageStatus.PARTIAL


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def compute_coverage(
    analysis_result: AnalysisResult,
    flow: Flow | None = None,
    business_rules: list | None = None,
) -> CoverageReport:
    """
    Build the :class:`CoverageReport` for *analysis_result*.

    Args:
        analysis_result: Phase 1–4 pipeline output.
        flow: The CFG; if ``None`` the ``control_flow`` dimension is
            derived without it (FAILED when IR exists, NOT_MEASURABLE
            otherwise).
        business_rules: #112 output; only used to annotate the
            ``business_rule`` dimension's detail.
    """
    cov = analysis_result.coverage
    ast = analysis_result.ast
    ir = analysis_result.ir
    codes = _diag_code_counts(analysis_result)
    notes: list[str] = []

    # -- pipeline totally failed before coverage could be measured -------
    pipeline_failed = cov is None and ast is None

    # =====================================================================
    # 1. lexical
    # =====================================================================
    if cov is None:
        lexical = CoverageDimension(
            name="lexical",
            ratio=0.0,
            covered=0,
            total=0,
            status=CoverageStatus.FAILED,
            detail=(
                "Lexing/parsing did not complete far enough to measure "
                "lexical coverage (a LexerError or top-level parser failure)."
            ),
        )
    else:
        # tokens_total includes the trailing EOF sentinel; exclude it.
        lex_total = max(0, cov.tokens_total - 1)
        lex_covered = max(0, lex_total - cov.unknown_token_count)
        lex_ratio = _ratio(lex_covered, lex_total)
        lexical = CoverageDimension(
            name="lexical",
            ratio=lex_ratio,
            covered=lex_covered,
            total=lex_total,
            status=_status_for(lex_ratio, had_input=lex_total > 0),
            detail=(
                f"{cov.unknown_token_count} of {lex_total} source token(s) "
                "could not be classified by the lexer (UNKNOWN)."
                if lex_total > 0
                else "No source tokens."
            ),
        )

    # =====================================================================
    # 2. parser  (reuse #108 AnalysisCoverage directly)
    # =====================================================================
    if cov is None:
        parser = CoverageDimension(
            name="parser",
            ratio=0.0,
            covered=0,
            total=0,
            status=CoverageStatus.FAILED,
            detail="The parser did not produce a coverage snapshot.",
        )
    else:
        p_ratio = _ratio(cov.tokens_consumed, cov.tokens_total)
        if cov.parse_complete:
            p_status = CoverageStatus.COMPLETE
        elif cov.tokens_consumed <= 0:
            p_status = CoverageStatus.FAILED
        else:
            p_status = CoverageStatus.PARTIAL
        detail = (
            f"parser consumed {cov.tokens_consumed}/{cov.tokens_total} tokens; "
            f"{cov.abandoned_construct_count} abandoned region(s)."
        )
        if cov.abandoned_construct_count > 0 and p_status is CoverageStatus.COMPLETE:
            p_status = CoverageStatus.PARTIAL  # never COMPLETE with abandonment
        parser = CoverageDimension(
            name="parser",
            ratio=p_ratio if p_status is not CoverageStatus.COMPLETE else 1.0,
            covered=cov.tokens_consumed,
            total=cov.tokens_total,
            status=p_status,
            detail=detail,
        )

    # =====================================================================
    # 3. statement
    # =====================================================================
    stmts_parsed = cov.statements_parsed if cov is not None else 0
    stmt_loss = sum(codes.get(c, 0) for c in _STATEMENT_LOSS_CODES)
    has_proc = bool(
        ast is not None
        and ast.procedure_division is not None
        and (ast.procedure_division.paragraphs or stmt_loss)
    )
    if not has_proc and stmts_parsed == 0 and stmt_loss == 0:
        statement = CoverageDimension(
            name="statement",
            ratio=1.0,
            covered=0,
            total=0,
            status=CoverageStatus.NOT_MEASURABLE,
            detail="No PROCEDURE DIVISION statements to analyze.",
        )
    else:
        s_total = stmts_parsed + stmt_loss
        s_ratio = _ratio(stmts_parsed, s_total)
        statement = CoverageDimension(
            name="statement",
            ratio=s_ratio,
            covered=stmts_parsed,
            total=s_total,
            status=_status_for(s_ratio, had_input=s_total > 0),
            detail=(
                f"{stmts_parsed} statement(s) parsed; {stmt_loss} statement-level "
                "failure(s) (SYN005/SYN100/SYN301). Denominator is parsed + "
                "failed statements — statements inside an abandoned region are "
                "counted by the 'parser' dimension, not here."
            ),
        )

    # =====================================================================
    # 4. ast
    # =====================================================================
    if ast is None:
        ast_dim = CoverageDimension(
            name="ast",
            ratio=0.0,
            covered=0,
            total=0,
            status=CoverageStatus.FAILED,
            detail="No AST was produced.",
        )
    else:
        data_items = _count_data_items(analysis_result)
        represented = stmts_parsed + data_items
        not_represented = sum(
            codes.get(c, 0) for c in ("SYN100", "SYN101", "SYN102", "SYN200")
        )
        a_total = represented + not_represented
        if a_total == 0:
            ast_dim = CoverageDimension(
                name="ast",
                ratio=1.0,
                covered=0,
                total=0,
                status=CoverageStatus.NOT_MEASURABLE,
                detail="AST exists; no procedural or data constructs to represent.",
            )
        else:
            a_ratio = _ratio(represented, a_total)
            ast_dim = CoverageDimension(
                name="ast",
                ratio=a_ratio,
                covered=represented,
                total=a_total,
                status=_status_for(a_ratio, had_input=True),
                detail=(
                    f"{represented} recognised construct(s) represented as AST "
                    f"nodes; {not_represented} recognised construct(s) diagnosed "
                    "but not represented (SYN100/101/102/200)."
                ),
            )

    # =====================================================================
    # 5. ir
    # =====================================================================
    ast_stmt_total = _ast_statement_total(analysis_result)
    if ir is None:
        if ast is None:
            ir_dim = CoverageDimension(
                name="ir",
                ratio=1.0,
                covered=0,
                total=0,
                status=CoverageStatus.NOT_MEASURABLE,
                detail="IR not built because there is no AST (upstream failure).",
            )
        else:
            ir_dim = CoverageDimension(
                name="ir",
                ratio=0.0,
                covered=0,
                total=1,
                status=CoverageStatus.FAILED,
                detail="An AST exists but IR construction produced nothing.",
            )
    else:
        ir_instr = 0
        for mod in ir.modules:
            for fn in mod.functions:
                for blk in fn.blocks:
                    ir_instr += len(blk.instructions)
        if ast_stmt_total == 0:
            ir_dim = CoverageDimension(
                name="ir",
                ratio=1.0,
                covered=ir_instr,
                total=0,
                status=CoverageStatus.NOT_MEASURABLE,
                detail="IR exists; no AST statements to lower.",
            )
        else:
            # Every AST statement lowers to >= 1 IR instruction (an IF
            # lowers to IRIf+IREndIf, so IR count >= AST statement count
            # for well-formed input). A shortfall means the IR builder
            # dropped statements.
            covered = min(ast_stmt_total, ir_instr)
            i_ratio = _ratio(covered, ast_stmt_total)
            status = _status_for(i_ratio, had_input=True)
            detail = (
                f"{ir_instr} IR instruction(s) from {ast_stmt_total} AST "
                "statement(s)."
            )
            if analysis_result.semantic_diagnostics:
                detail += (
                    f" {len(analysis_result.semantic_diagnostics)} semantic "
                    "error(s) — IR values may be incomplete (reflected in "
                    "confidence, not this ratio)."
                )
            ir_dim = CoverageDimension(
                name="ir",
                ratio=i_ratio,
                covered=covered,
                total=ast_stmt_total,
                status=status,
                detail=detail,
            )

    # =====================================================================
    # 6. control_flow
    # =====================================================================
    if ir is None:
        cfg_dim = CoverageDimension(
            name="control_flow",
            ratio=1.0,
            covered=0,
            total=0,
            status=CoverageStatus.NOT_MEASURABLE,
            detail="No IR, so no control-flow graph could be built.",
        )
    elif flow is None or not flow.nodes:
        cfg_dim = CoverageDimension(
            name="control_flow",
            ratio=0.0,
            covered=0,
            total=1,
            status=CoverageStatus.FAILED,
            detail="IR exists but no control-flow graph was produced.",
        )
    else:
        stmt_nodes = [
            n
            for n in flow.nodes
            if n.node_type in (NodeType.PROCESS, NodeType.DECISION)
        ]
        external_nodes = [n for n in flow.nodes if n.node_type is NodeType.EXTERNAL]
        unresolved = sum(
            1
            for e in flow.edges
            if e.edge_type in (EdgeType.PERFORMS, EdgeType.GOES_TO)
            and e.target_id in {n.id for n in external_nodes}
        )
        if ast_stmt_total == 0:
            cfg_dim = CoverageDimension(
                name="control_flow",
                ratio=1.0,
                covered=len(stmt_nodes),
                total=0,
                status=CoverageStatus.NOT_MEASURABLE,
                detail="No statements to represent in the CFG.",
            )
        else:
            covered = min(ast_stmt_total, len(stmt_nodes))
            # An unresolved PERFORM/GO TO target is a real control-flow gap:
            # the graph does not know where control goes. Fold it into the
            # denominator so ratio and status agree.
            cfg_total = ast_stmt_total + unresolved
            c_ratio = _ratio(covered, cfg_total)
            status = _status_for(c_ratio, had_input=True)
            cfg_dim = CoverageDimension(
                name="control_flow",
                ratio=c_ratio,
                covered=covered,
                total=cfg_total,
                status=status,
                detail=(
                    f"{len(stmt_nodes)} statement/decision node(s) for "
                    f"{ast_stmt_total} AST statement(s); {unresolved} unresolved "
                    "PERFORM/GO TO target(s) — the CFG is statement-level "
                    "(task #110)."
                ),
            )

    # =====================================================================
    # 7. dependency
    # =====================================================================
    deps = analysis_result.dependencies
    dep_targets = [
        d for d in deps if getattr(d.type, "value", "") in ("CALL", "PERFORM")
    ]
    known_paragraphs = set()
    if ast is not None and ast.procedure_division is not None:
        known_paragraphs = {p.name.upper() for p in ast.procedure_division.paragraphs}
    unresolved_dep = sum(
        1
        for d in dep_targets
        if _strip_quotes(d.target).upper() not in known_paragraphs
        and getattr(d.type, "value", "") == "PERFORM"
    )
    stmt_loss_hides_deps = codes.get("SYN100", 0) + sum(
        codes.get(c, 0) for c in ("SYN301", "SYN300")
    )
    has_proc_body = bool(
        ast is not None
        and ast.procedure_division is not None
        and ast.procedure_division.paragraphs
    )
    if cov is None:
        dep_dim = CoverageDimension(
            name="dependency",
            ratio=0.0,
            covered=0,
            total=0,
            status=CoverageStatus.FAILED,
            detail="Dependency analysis had no AST to inspect.",
        )
    elif not has_proc_body and not deps and stmt_loss_hides_deps == 0:
        dep_dim = CoverageDimension(
            name="dependency",
            ratio=1.0,
            covered=0,
            total=0,
            status=CoverageStatus.NOT_MEASURABLE,
            detail="No PROCEDURE DIVISION body — no dependency-bearing logic.",
        )
    else:
        # Base: dependency analysis can only see what parsed and became AST.
        base = min(parser.ratio, statement.ratio if statement.measurable else 1.0)
        resolved_frac = 1.0
        if dep_targets:
            resolved_frac = (len(dep_targets) - unresolved_dep) / len(dep_targets)
        d_ratio = max(0.0, min(1.0, base * resolved_frac))
        fully_clean = (
            cov.parse_complete and stmt_loss_hides_deps == 0 and unresolved_dep == 0
        )
        if fully_clean:
            status = CoverageStatus.COMPLETE
            d_ratio = 1.0
        elif d_ratio <= 0.0:
            status = CoverageStatus.FAILED
        else:
            status = CoverageStatus.PARTIAL
        no_call_perform = not dep_targets
        incomplete_here = (
            not cov.parse_complete or stmt_loss_hides_deps > 0 or unresolved_dep > 0
        )
        if no_call_perform and not incomplete_here:
            detail = (
                f"{len(deps)} dependency edge(s); no CALL/PERFORM dependencies, "
                "and the whole program was analyzed — absence of coupling is "
                "confirmed."
            )
        elif no_call_perform:
            detail = (
                f"{len(deps)} dependency edge(s); no CALL/PERFORM dependencies "
                f"found, but {stmt_loss_hides_deps} statement region(s) were not "
                "analyzed and/or the parser did not finish — absence of coupling "
                "is NOT confirmed."
            )
        else:
            detail = (
                f"{len(deps)} dependency edge(s), {len(dep_targets)} CALL/PERFORM; "
                f"{unresolved_dep} unresolved PERFORM target(s); "
                f"{stmt_loss_hides_deps} unanalyzed statement region(s) that "
                "could hide a CALL/PERFORM."
                + (
                    ""
                    if not incomplete_here
                    else " Coupling picture is NOT confirmed complete."
                )
            )
        dep_dim = CoverageDimension(
            name="dependency",
            ratio=d_ratio,
            covered=len(dep_targets) - unresolved_dep,
            total=max(len(dep_targets), len(dep_targets) - unresolved_dep),
            status=status,
            detail=detail,
        )

    # =====================================================================
    # 8. business_rule
    # =====================================================================
    if_nodes = _count_if_nodes(analysis_result)
    syn005 = codes.get("SYN005", 0)
    rule_count = len(business_rules) if business_rules is not None else None
    if cov is None:
        br_dim = CoverageDimension(
            name="business_rule",
            ratio=0.0,
            covered=0,
            total=0,
            status=CoverageStatus.FAILED,
            detail="Business-rule analysis had no AST to inspect.",
        )
    elif if_nodes == 0 and syn005 == 0:
        br_dim = CoverageDimension(
            name="business_rule",
            ratio=1.0,
            covered=0,
            total=0,
            status=CoverageStatus.NOT_MEASURABLE,
            detail=(
                "No conditional logic in the analyzed source — nothing for "
                "business-rule extraction to inspect."
                + (
                    f" ({rule_count} rule(s) extracted.)"
                    if rule_count is not None
                    else ""
                )
            ),
        )
    else:
        br_total = if_nodes + syn005
        br_ratio = _ratio(if_nodes, br_total)
        status = _status_for(br_ratio, had_input=True)
        if not cov.parse_complete and status is CoverageStatus.COMPLETE:
            status = CoverageStatus.PARTIAL
        br_dim = CoverageDimension(
            name="business_rule",
            ratio=br_ratio,
            covered=if_nodes,
            total=br_total,
            status=status,
            detail=(
                f"{if_nodes} IF region(s) reached AST; {syn005} malformed-"
                "statement error(s) (SYN005) — each is a conditional whose "
                "body or compound condition was dropped, so a rule may be "
                "missing."
                + (
                    f" {rule_count} rule(s) extracted."
                    if rule_count is not None
                    else ""
                )
            ),
        )

    # =====================================================================
    # unsupported syntax summary
    # =====================================================================
    unsup_codes = sorted(
        c for c in codes if c.startswith("SYN1") or c.startswith("SYN2")
    )
    affected: set[str] = set()
    for c in unsup_codes:
        affected.update(_CODE_AFFECTS.get(c, ()))
    unsupported = UnsupportedSyntaxCoverage(
        distinct_codes=len(unsup_codes),
        total_occurrences=sum(codes[c] for c in unsup_codes),
        codes=tuple(unsup_codes),
        affected_dimensions=tuple(sorted(affected)),
        detail=(
            f"{len(unsup_codes)} distinct unsupported/unmodelled construct "
            f"type(s), {sum(codes[c] for c in unsup_codes)} occurrence(s)."
            if unsup_codes
            else "No unsupported or unmodelled syntax."
        ),
    )

    # =====================================================================
    # overall = weakest measurable link
    # =====================================================================
    dims = (
        lexical,
        parser,
        statement,
        ast_dim,
        ir_dim,
        cfg_dim,
        dep_dim,
        br_dim,
    )
    measurable = [d for d in dims if d.measurable]
    if pipeline_failed or not measurable:
        overall = 0.0
        overall_status = CoverageStatus.FAILED
    else:
        overall = min(d.ratio for d in measurable)
        if any(d.status is CoverageStatus.FAILED for d in measurable):
            overall_status = CoverageStatus.FAILED
        elif all(d.status is CoverageStatus.COMPLETE for d in measurable):
            overall_status = CoverageStatus.COMPLETE
        else:
            overall_status = CoverageStatus.PARTIAL

    if pipeline_failed:
        notes.append("Analysis did not complete: no coverage snapshot and no AST.")
    if (
        ast is not None
        and not pipeline_failed
        and (ast.procedure_division is None or not ast.procedure_division.paragraphs)
    ):
        notes.append(
            "No PROCEDURE DIVISION body — there is no procedural logic to "
            "analyze; coverage reflects only the parsed identification/data "
            "structure, and downstream dimensions are NOT_MEASURABLE."
        )
    if cov is not None and cov.abandoned_construct_count > 0:
        notes.append(
            f"{cov.abandoned_construct_count} region(s) of source were "
            "abandoned by the parser and are invisible to every later stage."
        )
    if unsup_codes:
        notes.append(
            "Unsupported syntax present — see 'unsupported_syntax'. Absence "
            "of a construct in the analyzed representation is not evidence "
            "the construct is absent from the program."
        )

    return CoverageReport(
        lexical=lexical,
        parser=parser,
        statement=statement,
        ast=ast_dim,
        ir=ir_dim,
        control_flow=cfg_dim,
        dependency=dep_dim,
        business_rule=br_dim,
        unsupported_syntax=unsupported,
        overall=overall,
        overall_status=overall_status,
        notes=tuple(notes),
    )


def _strip_quotes(text: str) -> str:
    t = (text or "").strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in {"'", '"'}:
        return t[1:-1]
    return t
