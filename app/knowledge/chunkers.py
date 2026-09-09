"""
Deterministic, modernization-aware chunking (#122 Step 2).

Each function turns one artifact into semantic chunks (never fixed-size
character slices) and attaches full :class:`~app.knowledge.provenance.Provenance`.
For identical ``(source, analysis, CHUNKING_VERSION)`` the chunks — ids
included — are identical.
"""

from __future__ import annotations

import re
from typing import Any

from app.knowledge.chunk import ChunkType, KnowledgeChunk
from app.knowledge.provenance import Provenance, SourceType
from app.knowledge.version import CHUNKING_VERSION

__all__ = [
    "chunk_cobol_source",
    "chunk_business_rules",
    "chunk_risks",
    "chunk_dependencies",
    "chunk_strategy",
    "chunk_cfg",
    "chunk_ir",
    "chunk_generated_java",
]

_DIVISION_RE = re.compile(r"^\s{0,15}([A-Z0-9-]+)\s+DIVISION\b", re.IGNORECASE)


def _artifact_version() -> str:
    return CHUNKING_VERSION


def _lines_of(loc_list: list[dict[str, Any]] | None) -> tuple[int | None, int | None]:
    lines = sorted(
        int(loc["line"])
        for loc in (loc_list or [])
        if isinstance(loc, dict) and isinstance(loc.get("line"), int)
    )
    if not lines:
        return None, None
    return lines[0], lines[-1]


# ---------------------------------------------------------------------------
# COBOL source
# ---------------------------------------------------------------------------


def _paragraph_spans(
    source: str, paragraph_names: list[str]
) -> list[tuple[str, int, int]]:
    lines = source.splitlines()
    names = {n.upper() for n in paragraph_names}
    headers: list[tuple[str, int]] = []
    for i, raw in enumerate(lines, start=1):
        token = raw.strip().rstrip(".").upper()
        if token in names:
            headers.append((token, i))
    spans: list[tuple[str, int, int]] = []
    for idx, (name, start) in enumerate(headers):
        end = headers[idx + 1][1] - 1 if idx + 1 < len(headers) else len(lines)
        spans.append((name, start, end))
    return spans


def chunk_cobol_source(
    source_id: str,
    source: str,
    *,
    source_path: str | None = None,
    paragraph_names: list[str] | None = None,
    source_type: SourceType = SourceType.COBOL,
) -> list[KnowledgeChunk]:
    lines = source.splitlines()
    chunks: list[KnowledgeChunk] = []
    path = source_path or f"{source_id}.cbl"

    # one chunk per DIVISION header region
    div_headers = [
        (m.group(1).upper(), i)
        for i, raw in enumerate(lines, start=1)
        if (m := _DIVISION_RE.match(raw))
    ]
    for idx, (name, start) in enumerate(div_headers):
        end = div_headers[idx + 1][1] - 1 if idx + 1 < len(div_headers) else len(lines)
        content = "\n".join(lines[start - 1 : end]).strip()
        if not content:
            continue
        prov = Provenance(
            source_id=source_id,
            source_type=source_type,
            source_path=path,
            program_source_id=source_id,
            line_start=start,
            line_end=end,
            section=f"{name} DIVISION",
            artifact_version=_artifact_version(),
        )
        chunks.append(
            KnowledgeChunk.create(
                chunk_type=ChunkType.COBOL_DIVISION,
                content=content,
                provenance=prov,
                location_key=f"div:{name}:{start}-{end}",
            )
        )

    # one chunk per paragraph
    for name, start, end in _paragraph_spans(source, paragraph_names or []):
        content = "\n".join(lines[start - 1 : end]).strip()
        if not content:
            continue
        prov = Provenance(
            source_id=source_id,
            source_type=source_type,
            source_path=path,
            program_source_id=source_id,
            line_start=start,
            line_end=end,
            paragraph=name,
            artifact_version=_artifact_version(),
        )
        chunks.append(
            KnowledgeChunk.create(
                chunk_type=ChunkType.COBOL_PARAGRAPH,
                content=content,
                provenance=prov,
                location_key=f"para:{name}:{start}-{end}",
            )
        )

    if not chunks:  # unstructured / tiny source — keep it whole, still attributed
        prov = Provenance(
            source_id=source_id,
            source_type=source_type,
            source_path=path,
            program_source_id=source_id,
            line_start=1,
            line_end=max(1, len(lines)),
            artifact_version=_artifact_version(),
        )
        chunks.append(
            KnowledgeChunk.create(
                chunk_type=ChunkType.COBOL_SOURCE,
                content=source.strip(),
                provenance=prov,
                location_key="whole",
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# business rules
# ---------------------------------------------------------------------------


def chunk_business_rules(
    rules: list[dict[str, Any]] | None,
    *,
    program_source_id: str,
    analysis_version: str,
    source_path: str | None = None,
) -> list[KnowledgeChunk]:
    out: list[KnowledgeChunk] = []
    for rule in rules or []:
        rid = str(rule.get("rule_id") or "")
        if not rid:
            continue
        ls, le = _lines_of(rule.get("source_locations"))
        actions = "; ".join(
            str(a.get("raw", "")).strip()
            for a in rule.get("actions", [])
            if a.get("raw")
        )
        content = (
            f"Business rule {rid} ({rule.get('category', 'RULE')}): "
            f"{rule.get('description', '').strip()}\n"
            f"Condition: {rule.get('condition', '').strip()}\n"
            f"Actions: {actions}\n"
            f"Reads: {', '.join(rule.get('variables', {}).get('reads', []))}; "
            f"Writes: {', '.join(rule.get('variables', {}).get('writes', []))}"
        ).strip()
        prov = Provenance(
            source_id=program_source_id,
            source_type=SourceType.BUSINESS_RULE,
            source_path=source_path,
            program_source_id=program_source_id,
            rule_id=rid,
            line_start=ls,
            line_end=le,
            artifact_version=CHUNKING_VERSION,
            analysis_version=analysis_version,
        )
        out.append(
            KnowledgeChunk.create(
                chunk_type=ChunkType.BUSINESS_RULE,
                content=content,
                provenance=prov,
                location_key=f"rule:{rid}",
                metadata={"category": str(rule.get("category", ""))},
            )
        )
    return out


# ---------------------------------------------------------------------------
# risks
# ---------------------------------------------------------------------------


def chunk_risks(
    risks: list[dict[str, Any]] | None,
    *,
    program_source_id: str,
    analysis_version: str,
    source_path: str | None = None,
) -> list[KnowledgeChunk]:
    out: list[KnowledgeChunk] = []
    for risk in risks or []:
        rid = str(risk.get("risk_id") or "")
        if not rid:
            continue
        ls, le = _lines_of(risk.get("source_locations"))
        content = (
            f"Modernization risk {rid} [{risk.get('severity', '')}] "
            f"{risk.get('category', '')}: {risk.get('title', '').strip()}\n"
            f"{risk.get('explanation', '').strip()}\n"
            f"Evidence: {' | '.join(risk.get('evidence', []))}"
        ).strip()
        prov = Provenance(
            source_id=program_source_id,
            source_type=SourceType.MODERNIZATION_RISK,
            source_path=source_path,
            program_source_id=program_source_id,
            risk_id=rid,
            line_start=ls,
            line_end=le,
            artifact_version=CHUNKING_VERSION,
            analysis_version=analysis_version,
        )
        out.append(
            KnowledgeChunk.create(
                chunk_type=ChunkType.RISK,
                content=content,
                provenance=prov,
                location_key=f"risk:{rid}",
                metadata={"severity": str(risk.get("severity", ""))},
            )
        )
    return out


# ---------------------------------------------------------------------------
# dependencies
# ---------------------------------------------------------------------------


def chunk_dependencies(
    deps: list[dict[str, Any]] | None,
    *,
    program_source_id: str,
    analysis_version: str,
    source_path: str | None = None,
) -> list[KnowledgeChunk]:
    out: list[KnowledgeChunk] = []
    for i, dep in enumerate(deps or []):
        dtype = str(dep.get("type", "")).upper()
        target = str(dep.get("target", "")).strip()
        if not dtype or not target:
            continue
        loc = dep.get("source_location") or {}
        line = loc.get("line") if isinstance(loc.get("line"), int) else None
        src_para = str(dep.get("source", "")).strip() or None
        content = (
            f"Dependency: {dep.get('source', '?')} --{dtype}--> {target} "
            f"(confidence {dep.get('confidence', 'n/a')})"
        )
        prov = Provenance(
            source_id=program_source_id,
            source_type=SourceType.DEPENDENCY,
            source_path=source_path,
            program_source_id=program_source_id,
            dependency=f"{dtype}:{target}",
            paragraph=src_para,
            line_start=line,
            line_end=line,
            artifact_version=CHUNKING_VERSION,
            analysis_version=analysis_version,
        )
        out.append(
            KnowledgeChunk.create(
                chunk_type=ChunkType.DEPENDENCY,
                content=content,
                provenance=prov,
                location_key=f"dep:{dtype}:{target}:{src_para}:{i}",
                metadata={"dependency_type": dtype},
            )
        )
    return out


# ---------------------------------------------------------------------------
# strategy + patterns
# ---------------------------------------------------------------------------


def chunk_strategy(
    strategy: dict[str, Any] | None,
    *,
    program_source_id: str,
    analysis_version: str,
) -> list[KnowledgeChunk]:
    if not strategy:
        return []
    out: list[KnowledgeChunk] = []
    entries: list[tuple[dict[str, Any], bool]] = []
    if strategy.get("primary"):
        entries.append((strategy["primary"], True))
    for rec in strategy.get("recommendations", []):
        if rec is not strategy.get("primary"):
            entries.append((rec, False))
    for rec, is_primary in entries:
        sid = str(rec.get("recommendation_id") or rec.get("strategy") or "")
        if not sid:
            continue
        content = (
            f"Modernization strategy {sid} "
            f"({'primary' if is_primary else 'alternative'}): "
            f"{rec.get('strategy', '')}\n{rec.get('rationale', '').strip()}\n"
            f"Evidence: {' | '.join(rec.get('evidence', []))}"
        ).strip()
        prov = Provenance(
            source_id=program_source_id,
            source_type=SourceType.MODERNIZATION_STRATEGY,
            program_source_id=program_source_id,
            strategy_id=sid,
            artifact_version=CHUNKING_VERSION,
            analysis_version=analysis_version,
        )
        out.append(
            KnowledgeChunk.create(
                chunk_type=ChunkType.MODERNIZATION_STRATEGY,
                content=content,
                provenance=prov,
                location_key=f"strategy:{sid}:{is_primary}",
                metadata={"strategy": str(rec.get("strategy", ""))},
            )
        )
    return out


# ---------------------------------------------------------------------------
# CFG / IR
# ---------------------------------------------------------------------------

_CFG_ID_RE = re.compile(r"^(?:stmt|fn)_[^_]+_(?P<para>.+?)_\d+$|^fn_[^_]+_(?P<p2>.+?)$")


def chunk_cfg(
    cfg: dict[str, Any] | None,
    *,
    program_source_id: str,
    analysis_version: str,
) -> list[KnowledgeChunk]:
    if not cfg or not cfg.get("nodes"):
        return []
    by_para: dict[str, list[str]] = {}
    for node in cfg["nodes"]:
        nid = str(node.get("id", ""))
        m = _CFG_ID_RE.match(nid)
        para = (m.group("para") or m.group("p2")) if m else "__flow__"
        if para in ("__entry__", "__exit__"):
            para = "__flow__"
        by_para.setdefault(para, []).append(
            f"[{node.get('node_type', '?')}] {node.get('name', '')}".strip()
        )
    out: list[KnowledgeChunk] = []
    for para, entries in by_para.items():
        content = f"Control-flow region for paragraph {para}:\n" + "\n".join(entries)
        prov = Provenance(
            source_id=program_source_id,
            source_type=SourceType.CFG,
            program_source_id=program_source_id,
            paragraph=None if para == "__flow__" else para,
            artifact_version=CHUNKING_VERSION,
            analysis_version=analysis_version,
        )
        out.append(
            KnowledgeChunk.create(
                chunk_type=ChunkType.CFG_REGION,
                content=content,
                provenance=prov,
                location_key=f"cfg:{para}",
            )
        )
    return out


def chunk_ir(
    ir: dict[str, Any] | None,
    *,
    program_source_id: str,
    analysis_version: str,
) -> list[KnowledgeChunk]:
    if not ir or not ir.get("modules"):
        return []
    out: list[KnowledgeChunk] = []
    for module in ir["modules"]:
        mname = str(module.get("name", "module"))
        for fn in module.get("functions", []):
            fname = str(fn.get("name", "fn"))
            block_lines = []
            for blk in fn.get("blocks", []):
                for ins in blk.get("instructions", []):
                    txt = ins.get("comment") or ins.get("type", "")
                    if ins.get("name"):
                        txt += f" {ins['name']}"
                    block_lines.append(f"  {txt}".rstrip())
            content = f"IR function {mname}.{fname}:\n" + "\n".join(block_lines)
            prov = Provenance(
                source_id=program_source_id,
                source_type=SourceType.IR,
                program_source_id=program_source_id,
                paragraph=None if fname == "__entry__" else fname,
                symbol=f"{mname}.{fname}",
                artifact_version=CHUNKING_VERSION,
                analysis_version=analysis_version,
            )
            out.append(
                KnowledgeChunk.create(
                    chunk_type=ChunkType.IR_MODULE,
                    content=content,
                    provenance=prov,
                    location_key=f"ir:{mname}.{fname}",
                )
            )
    return out


# ---------------------------------------------------------------------------
# generated Java
# ---------------------------------------------------------------------------

_JAVA_CLASS_RE = re.compile(r"^\s*(?:public\s+|final\s+|abstract\s+)*class\s+(\w+)")
_JAVA_METHOD_RE = re.compile(
    r"^\s{2,}(?:public|private|protected)\s+"
    r"(?:static\s+)?[\w<>\[\], ]+\s+(\w+)\s*\([^;]*\)\s*\{"
)


def chunk_generated_java(
    java_source: str,
    *,
    program_source_id: str,
) -> list[KnowledgeChunk]:
    if not java_source or not java_source.strip():
        return []
    lines = java_source.splitlines()
    out: list[KnowledgeChunk] = []
    class_name = None
    for i, raw in enumerate(lines, start=1):
        cm = _JAVA_CLASS_RE.match(raw)
        if cm:
            class_name = cm.group(1)
            prov = Provenance(
                source_id=program_source_id,
                source_type=SourceType.GENERATED_JAVA,
                program_source_id=program_source_id,
                java_class=class_name,
                line_start=i,
                line_end=i,
                artifact_version=CHUNKING_VERSION,
            )
            out.append(
                KnowledgeChunk.create(
                    chunk_type=ChunkType.JAVA_CLASS,
                    content="\n".join(lines[i - 1 : i + 2]).strip() or raw.strip(),
                    provenance=prov,
                    location_key=f"java:class:{class_name}",
                )
            )
        mm = _JAVA_METHOD_RE.match(raw)
        if mm and class_name:
            start = i
            depth = raw.count("{") - raw.count("}")
            j = i
            while j < len(lines) and depth > 0:
                j += 1
                depth += lines[j - 1].count("{") - lines[j - 1].count("}")
            content = "\n".join(lines[start - 1 : j]).strip()
            prov = Provenance(
                source_id=program_source_id,
                source_type=SourceType.GENERATED_JAVA,
                program_source_id=program_source_id,
                java_class=class_name,
                java_method=mm.group(1),
                line_start=start,
                line_end=j,
                artifact_version=CHUNKING_VERSION,
            )
            out.append(
                KnowledgeChunk.create(
                    chunk_type=ChunkType.JAVA_METHOD,
                    content=content,
                    provenance=prov,
                    location_key=f"java:method:{class_name}.{mm.group(1)}:{start}",
                )
            )
    return out
