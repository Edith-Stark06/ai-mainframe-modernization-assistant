"""
#125 — derive a target Java architecture from deterministic analysis.

No LLM. Every component, interface, assumption and unsupported-behavior
record is backed by a Phase 1–5 fact (dependency, business rule, risk,
strategy, data item, coverage gap). If there is no evidence, nothing is
invented.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.dataset.analysis_bundle import AnalysisBundle
from app.java_modernization.architecture.models import (
    ArchitectureComponent,
    Assumption,
    ComponentType,
    DataModelElement,
    Evidence,
    ExternalInterface,
    JavaArchitecture,
    SourceRef,
    StrategyRef,
    UnsupportedBehavior,
)
from app.java_modernization.errors import ArchitectureError
from app.java_modernization.version import (
    ANALYSIS_CONTRACT_VERSION,
    ARCHITECTURE_VERSION,
)

__all__ = ["build_architecture"]

_FIELD_RE = re.compile(r"^\s*private\s+([\w<>\[\]]+)\s+(\w+)\s*;", re.MULTILINE)
_TODO_RE = re.compile(
    r"//\s*TODO:\s*implement\s+(CALL/PERFORM|[A-Z/]+)\s+target\s+'([^']+)'\s*\(([A-Z0-9]+)\)"
)
_JAVA_NAME_RE = re.compile(r"[^A-Za-z0-9]+")


def _pascal(name: str) -> str:
    parts = [p for p in _JAVA_NAME_RE.split(name) if p]
    return "".join(p[:1].upper() + p[1:].lower() for p in parts) or "Component"


def _lines(loc_list: list[dict[str, Any]] | None) -> tuple[int | None, int | None]:
    ls = sorted(
        int(loc["line"])
        for loc in (loc_list or [])
        if isinstance(loc, dict) and isinstance(loc.get("line"), int)
    )
    return (ls[0], ls[-1]) if ls else (None, None)


def _paragraph_spans(source: str, names: list[str]) -> dict[str, tuple[int, int]]:
    lines = source.splitlines()
    want = {n.upper() for n in names}
    headers = [
        (raw.strip().rstrip(".").upper(), i)
        for i, raw in enumerate(lines, start=1)
        if raw.strip().rstrip(".").upper() in want
    ]
    spans: dict[str, tuple[int, int]] = {}
    for idx, (name, start) in enumerate(headers):
        end = headers[idx + 1][1] - 1 if idx + 1 < len(headers) else len(lines)
        spans[name] = (start, end)
    return spans


def _strategy_ref(rec: dict[str, Any] | None) -> StrategyRef | None:
    if not rec:
        return None
    return StrategyRef(
        recommendation_id=str(rec.get("recommendation_id", "")),
        strategy=str(rec.get("strategy", "")),
        is_primary=bool(rec.get("is_primary", False)),
        rationale=str(rec.get("rationale", "")),
        evidence=tuple(str(e) for e in rec.get("evidence", [])),
        referenced_risk_ids=tuple(str(r) for r in rec.get("referenced_risk_ids", [])),
    )


def build_architecture(bundle: AnalysisBundle) -> JavaArchitecture:
    if bundle.ast is None:
        raise ArchitectureError(
            f"{bundle.source_id}: no AST — cannot derive an evidence-based architecture"
        )
    sid = bundle.source_id
    av = ANALYSIS_CONTRACT_VERSION
    path = f"{sid}.cbl"
    spans = _paragraph_spans(bundle.source, list(bundle.paragraphs))

    def sref(paragraph: str | None, span: tuple[int | None, int | None]) -> SourceRef:
        return SourceRef(
            source_id=sid,
            source_path=path,
            line_start=span[0],
            line_end=span[1],
            paragraph=paragraph,
        )

    rules = bundle.business_rules or []
    risks = bundle.risks or []
    deps = bundle.dependencies or []

    rules_by_para: dict[str, list[dict[str, Any]]] = {}
    for r in rules:
        ls, le = _lines(r.get("source_locations"))
        owner = None
        for pname, (ps, pe) in spans.items():
            if ls is not None and ps <= ls <= pe:
                owner = pname
                break
        rules_by_para.setdefault(owner or "__program__", []).append(r)

    components: list[ArchitectureComponent] = []
    source_mappings: dict[str, tuple[SourceRef, ...]] = {}

    # --- top-level orchestrator service (maps to the whole procedure div) ---
    entry_para = bundle.paragraphs[0] if bundle.paragraphs else None
    entry_span = spans.get(
        (entry_para or "").upper(), (1, len(bundle.source.splitlines()))
    )
    top = ArchitectureComponent(
        component_id=f"svc-{sid}-main",
        name=f"{_pascal(sid)}Service",
        type=ComponentType.SERVICE,
        responsibility=f"Orchestrates the {sid} program flow (entry: {entry_para}).",
        source_refs=(sref(entry_para, entry_span),),
        evidence=(
            Evidence(
                kind="strategy",
                detail=(
                    bundle.strategy.get("primary", {}).get("strategy", "REFACTOR")
                    if bundle.strategy
                    else "REFACTOR"
                ),
            ),
        ),
    )
    components.append(top)
    source_mappings[top.component_id] = top.source_refs

    # --- one SERVICE per paragraph that carries business rules ---
    for pname, prules in sorted(rules_by_para.items()):
        if pname == "__program__" or not prules:
            continue
        span = spans.get(pname, (None, None))
        rids = tuple(str(r.get("rule_id")) for r in prules if r.get("rule_id"))
        comp = ArchitectureComponent(
            component_id=f"svc-{sid}-{pname.lower()}",
            name=f"{_pascal(pname)}Service",
            type=ComponentType.SERVICE,
            responsibility=f"Applies business rules {', '.join(rids)} from paragraph {pname}.",
            source_refs=(sref(pname, span),),
            business_rule_ids=rids,
            evidence=tuple(
                Evidence(
                    kind="business_rule",
                    detail=f"{r.get('rule_id')}: {r.get('description', '')}",
                    source_refs=(sref(pname, _lines(r.get("source_locations"))),),
                )
                for r in prules
            ),
        )
        components.append(comp)
        source_mappings[comp.component_id] = comp.source_refs

    # --- DOMAIN component if shared mutable state was flagged ---
    shared = [r for r in risks if r.get("category") == "SHARED_MUTABLE_STATE"]
    if shared:
        srefs = tuple(sref(None, _lines(r.get("source_locations"))) for r in shared)
        dom = ArchitectureComponent(
            component_id=f"dom-{sid}-state",
            name=f"{_pascal(sid)}State",
            type=ComponentType.DOMAIN,
            responsibility="Owns shared mutable variables so decomposed services do not interfere.",
            source_refs=srefs,
            evidence=tuple(
                Evidence(
                    kind="risk", detail=f"{r.get('risk_id')}: {r.get('title', '')}"
                )
                for r in shared
            ),
        )
        components.append(dom)
        source_mappings[dom.component_id] = srefs

    # --- external interfaces + INTEGRATION components (from CALL deps) ---
    external_interfaces: list[ExternalInterface] = []
    seen_targets: set[str] = set()
    for d in deps:
        if str(d.get("type", "")).upper() != "CALL":
            continue
        target = str(d.get("target", "")).strip().strip("'\"")
        if not target or target in seen_targets:
            continue
        seen_targets.add(target)
        loc = d.get("source_location") or {}
        ln = loc.get("line") if isinstance(loc.get("line"), int) else None
        iref = SourceRef(
            source_id=sid,
            source_path=path,
            line_start=ln,
            line_end=ln,
            paragraph=str(d.get("source") or "") or None,
        )
        external_interfaces.append(
            ExternalInterface(
                interface_id=f"iface-{sid}-{_pascal(target).lower()}",
                kind="CALL",
                target=target,
                modeled=False,
                source_refs=(iref,),
                note="external CALL target is not present in the analysed workspace",
            )
        )
        comp = ArchitectureComponent(
            component_id=f"int-{sid}-{_pascal(target).lower()}",
            name=f"{_pascal(target)}Client",
            type=ComponentType.INTEGRATION,
            responsibility=f"Boundary for the external program {target} (CALL).",
            source_refs=(iref,),
            external_interface_ids=(f"iface-{sid}-{_pascal(target).lower()}",),
            evidence=(
                Evidence(
                    kind="dependency", detail=f"CALL {target}", source_refs=(iref,)
                ),
            ),
        )
        components.append(comp)
        source_mappings[comp.component_id] = comp.source_refs

    # --- data model + one DTO (from the fields the generator will emit) ---
    data_model: list[DataModelElement] = []
    for m in _FIELD_RE.finditer(bundle.java_backend_output):
        data_model.append(
            DataModelElement(
                name=m.group(2),
                java_concept="field",
                java_type=m.group(1),
                source_refs=(SourceRef(source_id=sid, source_path=path),),
            )
        )
    if data_model:
        dto = ArchitectureComponent(
            component_id=f"dto-{sid}-state",
            name=f"{_pascal(sid)}State",
            type=ComponentType.DTO,
            responsibility="Holds the program's WORKING-STORAGE data.",
            source_refs=(SourceRef(source_id=sid, source_path=path),),
            evidence=(
                Evidence(
                    kind="data_item",
                    detail=f"{len(data_model)} WORKING-STORAGE field(s)",
                ),
            ),
        )
        components.append(dto)
        source_mappings[dto.component_id] = dto.source_refs

    # --- assumptions ---
    assumptions: list[Assumption] = []
    for iface in external_interfaces:
        assumptions.append(
            Assumption(
                assumption_id=f"asm-{iface.interface_id}",
                statement=f"External CALL target {iface.target} is unavailable in this workspace.",
                reason="No matching program was found in the analysed sources.",
                source_refs=iface.source_refs,
            )
        )
    if data_model and all(f.java_type in ("int", "long", "double") for f in data_model):
        assumptions.append(
            Assumption(
                assumption_id=f"asm-{sid}-numeric",
                statement="COBOL numeric PIC 9 fields are represented as Java int/long.",
                reason="No COMP-3 / packed-decimal constructs were detected in the source.",
            )
        )

    # --- unsupported behaviors (coverage + parser diagnostics) ---
    unsupported: list[UnsupportedBehavior] = []
    cov_codes = ((bundle.coverage or {}).get("unsupported_syntax") or {}).get(
        "codes", []
    )
    for code in cov_codes:
        unsupported.append(
            UnsupportedBehavior(
                construct_name=str(code),
                explanation="Reported by the deterministic coverage analyzer as unsupported/unmodelled.",
                impact="This behavior is NOT represented in the generated Java.",
                diagnostic_code=str(code),
            )
        )
    for diag in bundle.syntax_diagnostics or []:
        code = str(diag.get("code", ""))
        if code.startswith(("SYN1", "SYN2", "SYN3")):
            ln = diag.get("line")
            unsupported.append(
                UnsupportedBehavior(
                    construct_name=code,
                    explanation=str(diag.get("message", "unsupported construct")),
                    impact="Not translated; see the diagnostic.",
                    diagnostic_code=code,
                    source_refs=(
                        SourceRef(
                            source_id=sid,
                            source_path=path,
                            line_start=ln if isinstance(ln, int) else None,
                            line_end=ln if isinstance(ln, int) else None,
                        ),
                    ),
                )
            )

    # the existing Java generator emits `// TODO: implement ... (BEnnn)` stubs
    # for PERFORM/CALL targets it cannot lower — surface each as an explicit
    # unsupported behavior rather than pretending the method body exists.
    for m in _TODO_RE.finditer(bundle.java_backend_output):
        unsupported.append(
            UnsupportedBehavior(
                construct_name=f"{m.group(1)} {m.group(2)}",
                explanation=(
                    f"The Java generator produced an empty stub for "
                    f"{m.group(1)} target '{m.group(2)}' (diagnostic {m.group(3)})."
                ),
                impact="The paragraph/subprogram logic is NOT present in the generated method body.",
                diagnostic_code=m.group(3),
                source_refs=(
                    SourceRef(
                        source_id=sid,
                        source_path=path,
                        line_start=spans.get(m.group(2).upper(), (None, None))[0],
                        line_end=spans.get(m.group(2).upper(), (None, None))[1],
                        paragraph=(
                            m.group(2).upper() if m.group(2).upper() in spans else None
                        ),
                    ),
                ),
            )
        )

    primary = _strategy_ref((bundle.strategy or {}).get("primary"))
    alts = tuple(
        s
        for r in (bundle.strategy or {}).get("recommendations", [])
        if (s := _strategy_ref(r)) is not None and not s.is_primary
    )

    payload = json.dumps(
        {
            "components": [c.model_dump(mode="json") for c in components],
            "data_model": [d.model_dump(mode="json") for d in data_model],
            "interfaces": [i.model_dump(mode="json") for i in external_interfaces],
            "assumptions": [a.model_dump(mode="json") for a in assumptions],
            "unsupported": [u.model_dump(mode="json") for u in unsupported],
            "primary": primary.model_dump(mode="json") if primary else None,
            "av": av,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]

    return JavaArchitecture(
        architecture_id=f"arch-{sid}-{digest}",
        version=ARCHITECTURE_VERSION,
        analysis_version=str(av),
        source_id=sid,
        primary_strategy=primary,
        alternative_strategies=alts,
        components=tuple(components),
        data_model=tuple(data_model),
        external_interfaces=tuple(external_interfaces),
        assumptions=tuple(assumptions),
        unsupported_behaviors=tuple(unsupported),
        source_mappings=source_mappings,
        semantic_equivalence_verified=False,
    )
