"""
Run the full deterministic Phase 1–5 pipeline for one source and collect
every serialized artifact Phase 6 needs. Nothing here recomputes or
reimplements analysis — it only calls the existing services and
serializers.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.analysis.serializers.ast import serialize_ast
from app.analysis.serializers.dependencies import serialize_dependencies
from app.analysis.serializers.ir import serialize_ir
from app.analysis.service import AnalysisService
from app.modernization.flow.generator import generate_flow
from app.modernization.intelligence import analyze_modernization_intelligence
from app.modernization.scoring.confidence_aware import score_with_confidence

__all__ = ["AnalysisBundle", "build_analysis_bundle"]


@dataclass(frozen=True)
class AnalysisBundle:
    """Every deterministic analysis artifact for one COBOL source."""

    source_id: str
    source: str
    source_sha256: str
    success: bool

    ast: dict[str, Any] | None
    ir: dict[str, Any] | None
    cfg: dict[str, Any] | None
    cfg_summary: dict[str, Any] | None
    dependencies: list[dict[str, Any]] | None
    business_rules: list[dict[str, Any]] | None
    risks: list[dict[str, Any]] | None
    strategy: dict[str, Any] | None
    coverage: dict[str, Any] | None
    confidence: dict[str, Any] | None
    java_backend_output: str

    syntax_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)


def _cfg_summary(flow: Any) -> dict[str, Any]:
    from app.modernization.flow.generator import compute_reachability, count_cycles

    entry = flow.nodes[0].id if flow.nodes else None
    reachable = compute_reachability(flow, entry) if entry else set()
    by_node_type: dict[str, int] = {}
    for n in flow.nodes:
        by_node_type[n.node_type.name] = by_node_type.get(n.node_type.name, 0) + 1
    by_edge_type: dict[str, int] = {}
    for e in flow.edges:
        by_edge_type[e.edge_type.name] = by_edge_type.get(e.edge_type.name, 0) + 1
    return {
        "node_count": len(flow.nodes),
        "edge_count": len(flow.edges),
        "node_types": dict(sorted(by_node_type.items())),
        "edge_types": dict(sorted(by_edge_type.items())),
        "reachable_node_count": len(reachable),
        "cycle_count": count_cycles(flow),
    }


def _paragraph_names(ast: Any) -> list[str]:
    if ast is None or ast.procedure_division is None:
        return []
    return [p.name for p in ast.procedure_division.paragraphs]


def _normalize_paths(obj: Any, real_path: str, canonical: str) -> Any:
    """
    Replace the on-disk analysis path with a canonical ``<source_id>.cbl``
    everywhere it appears (position ``filename`` fields, diagnostic
    messages, …), so a build is byte-reproducible regardless of the temp
    dir it ran in.
    """
    if isinstance(obj, str):
        out = obj.replace(real_path, canonical)
        # also handle the basename form the parser sometimes stores
        return out
    if isinstance(obj, dict):
        return {k: _normalize_paths(v, real_path, canonical) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_paths(v, real_path, canonical) for v in obj]
    return obj


def _serialize_syntax_diags(diags: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in diags:
        out.append(
            {
                "code": getattr(d, "code", ""),
                "category": getattr(getattr(d, "category", None), "value", ""),
                "severity": getattr(getattr(d, "severity", None), "value", ""),
                "line": getattr(d, "line", None),
                "column": getattr(d, "column", None),
                "message": getattr(d, "message", ""),
            }
        )
    return out


def build_analysis_bundle(
    source_id: str, source: str, work_dir: str | Path
) -> AnalysisBundle:
    """
    Analyse *source* deterministically and return an :class:`AnalysisBundle`.

    *work_dir* is a caller-owned directory; a stable ``<source_id>.cbl``
    file is written into it so the run is reproducible.
    """
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    path = work / f"{source_id}.cbl"
    path.write_text(source, encoding="utf-8")

    result = AnalysisService().analyze_file(path)

    flow = generate_flow(result) if result.ir is not None else None
    intel = analyze_modernization_intelligence(result, flow) if result.ast else None
    aware = score_with_confidence(result, flow) if result.ast else None

    canonical = f"{source_id}.cbl"
    real = str(path)

    def norm(obj: Any) -> Any:
        return _normalize_paths(obj, real, canonical)

    ast_json = norm(serialize_ast(result.ast)) if result.ast is not None else None
    ir_json = norm(serialize_ir(result.ir)) if result.ir is not None else None
    cfg_json = norm(flow.to_dict()) if flow is not None and flow.nodes else None
    cfg_sum = _cfg_summary(flow) if flow is not None and flow.nodes else None

    deps_json = (
        norm(serialize_dependencies(result.dependencies) if result.dependencies else [])
        if result.ast is not None
        else None
    )

    return AnalysisBundle(
        source_id=source_id,
        source=source,
        source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        success=bool(result.success),
        ast=ast_json,
        ir=ir_json,
        cfg=cfg_json,
        cfg_summary=cfg_sum,
        dependencies=deps_json,
        business_rules=(
            [norm(r.to_dict()) for r in intel.business_rules] if intel else None
        ),
        risks=[norm(r.to_dict()) for r in intel.risks] if intel else None,
        strategy=(
            norm(
                {
                    "primary": (
                        intel.primary_strategy.to_dict()
                        if intel.primary_strategy
                        else None
                    ),
                    "recommendations": [s.to_dict() for s in intel.strategies],
                }
            )
            if intel
            else None
        ),
        coverage=norm(aware.coverage_report.to_dict()) if aware else None,
        confidence=norm(aware.confidence.to_dict()) if aware else None,
        java_backend_output=result.java_source or "",
        syntax_diagnostics=norm(_serialize_syntax_diags(result.syntax_diagnostics)),
        paragraphs=_paragraph_names(result.ast),
    )
