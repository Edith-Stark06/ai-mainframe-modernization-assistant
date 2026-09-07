"""
Phase 6 training-dataset builder (#118).

Turns a *controlled source corpus* into versioned :class:`DatasetExample`
records, one per (source, task type[, variant]). Every ``expected_output``
is either produced verbatim by the deterministic Phase 1–5 analyzers
(``ground_truth_status = deterministic``) or is a clearly-marked
reference / reviewed answer — never an uncontrolled LLM generation.

The builder does not fabricate: if a stage produced no output for a
source (e.g. no business rules), the example records exactly that
("business_rules": []) rather than inventing one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.dataset.analysis_bundle import AnalysisBundle, build_analysis_bundle
from app.dataset.schema import (
    DatasetExample,
    Difficulty,
    ExampleAnalysis,
    ExampleInput,
    ExampleMetadata,
    GroundTruthStatus,
    Provenance,
    SourceLocation,
    TaskType,
    derive_example_id,
)
from app.dataset.security import SecretScanConfig, SecretScanner
from app.dataset.version import ANALYSIS_VERSION, DATASET_VERSION, GENERATOR_VERSION

__all__ = ["SourceRecord", "BuildResult", "DatasetBuilder"]


@dataclass(frozen=True)
class SourceRecord:
    """One controlled corpus entry."""

    source_id: str
    source: str
    provenance: Provenance
    license: str
    difficulty: Difficulty = Difficulty.MEDIUM
    #: which task types to emit for this source; empty = all applicable
    tasks: tuple[TaskType, ...] = ()
    #: gold Java for the cobol_to_java task, if a reviewed one exists
    reviewed_java: str | None = None
    java_compiles: bool | None = None
    notes: str | None = None


@dataclass
class BuildResult:
    examples: list[DatasetExample] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)


class DatasetBuilder:
    def __init__(
        self,
        work_dir: str | Path,
        secret_config: SecretScanConfig | None = None,
        created_at: str | None = None,
    ) -> None:
        self.work_dir = Path(work_dir)
        self.scanner = SecretScanner(secret_config)
        # A fixed timestamp keeps the build byte-reproducible; callers that
        # want a real wall-clock time pass it explicitly.
        self._created_at = created_at

    # ------------------------------------------------------------------

    def build(self, records: list[SourceRecord]) -> BuildResult:
        result = BuildResult()
        seen_ids: set[str] = set()

        for rec in sorted(records, key=lambda r: r.source_id):
            blocking = [
                f for f in self.scanner.scan(rec.source) if f.severity.value == "high"
            ]
            if blocking:
                result.skipped.append(
                    {
                        "source_id": rec.source_id,
                        "reason": "secret_scan_blocking",
                        "detail": "; ".join(f"{f.pattern}@L{f.line}" for f in blocking),
                    }
                )
                continue

            bundle = build_analysis_bundle(rec.source_id, rec.source, self.work_dir)
            for ex in self._examples_for(rec, bundle):
                if ex.example_id in seen_ids:
                    continue
                seen_ids.add(ex.example_id)
                result.examples.append(ex)

        result.examples.sort(
            key=lambda e: (e.task_type.value, e.input.source_id, e.example_id)
        )
        result.manifest = self._manifest(records, result)
        return result

    # ------------------------------------------------------------------

    def _created(self) -> str | None:
        return self._created_at

    def _meta(
        self,
        rec: SourceRecord,
        bundle: AnalysisBundle,
        provenance: Provenance,
        gt: GroundTruthStatus,
        notes: str | None = None,
    ) -> ExampleMetadata:
        return ExampleMetadata(
            source_id=rec.source_id,
            source_provenance=rec.provenance,
            provenance=provenance,
            license=rec.license,
            generator_version=GENERATOR_VERSION,
            analysis_version=ANALYSIS_VERSION,
            ground_truth_status=gt,
            source_sha256=bundle.source_sha256,
            notes=notes,
            created_at=self._created(),
        )

    def _analysis_block(self, bundle: AnalysisBundle, *fields: str) -> ExampleAnalysis:
        """Attach only the named analysis fields; others stay None."""
        data: dict[str, Any] = {}
        for f in fields:
            data[f] = getattr(bundle, f)
        return ExampleAnalysis(**data)

    def _example(
        self,
        rec: SourceRecord,
        bundle: AnalysisBundle,
        task: TaskType,
        expected: dict[str, Any],
        *,
        analysis: ExampleAnalysis,
        provenance: Provenance,
        gt: GroundTruthStatus,
        context: dict[str, Any] | None = None,
        source_locations: list[SourceLocation] | None = None,
        variant: str = "",
        notes: str | None = None,
    ) -> DatasetExample:
        return DatasetExample(
            example_id=derive_example_id(task, rec.source_id, variant),
            dataset_version=DATASET_VERSION,
            task_type=task,
            difficulty=rec.difficulty,
            input=ExampleInput(
                source=rec.source,
                source_id=rec.source_id,
                context=context or {},
            ),
            analysis=analysis,
            expected_output=expected,
            source_locations=source_locations or [],
            metadata=self._meta(rec, bundle, provenance, gt, notes),
        )

    # ------------------------------------------------------------------
    # per-task emitters
    # ------------------------------------------------------------------

    def _examples_for(
        self, rec: SourceRecord, bundle: AnalysisBundle
    ) -> list[DatasetExample]:
        want = set(rec.tasks) if rec.tasks else set(TaskType)
        out: list[DatasetExample] = []

        if TaskType.COBOL_EXPLANATION in want:
            out.append(self._explanation(rec, bundle))
        if TaskType.BUSINESS_RULE_EXTRACTION in want:
            out.append(self._business_rules(rec, bundle))
        if TaskType.RISK_IDENTIFICATION in want:
            out.append(self._risks(rec, bundle))
        if TaskType.MODERNIZATION_RECOMMENDATION in want:
            out.append(self._recommendation(rec, bundle))
        if TaskType.COBOL_TO_STRUCTURED in want:
            out.append(self._structured(rec, bundle))
        if TaskType.COBOL_TO_JAVA in want and bundle.ast is not None:
            out.append(self._cobol_to_java(rec, bundle))
        if TaskType.MODERNIZATION_QA in want:
            out.extend(self._modernization_qa(rec, bundle))
        if TaskType.SOURCE_GROUNDED_QA in want:
            out.extend(self._grounded_qa(rec, bundle))
        return [e for e in out if e is not None]

    def _explanation(self, rec: SourceRecord, bundle: AnalysisBundle) -> DatasetExample:
        # Deterministic STRUCTURAL summary — facts from the AST/IR only, no
        # invented prose. The label is the structure a correct explanation
        # must cover, not a golden paragraph of English.
        expected = {
            "program_id": _program_id(bundle),
            "paragraph_count": len(bundle.paragraphs),
            "paragraphs": bundle.paragraphs,
            "external_calls": _call_targets(bundle),
            "has_conditional_logic": _has_if(bundle),
            "has_loops": _has_loop(bundle),
            "required_concepts": _required_concepts(bundle),
            "unsupported_constructs": _unsupported_codes(bundle),
        }
        return self._example(
            rec,
            bundle,
            TaskType.COBOL_EXPLANATION,
            expected,
            analysis=self._analysis_block(bundle, "ast", "cfg", "dependencies"),
            provenance=Provenance.DETERMINISTIC_GENERATED,
            gt=GroundTruthStatus.DETERMINISTIC,
            notes=(
                "expected_output is the set of structural facts a correct "
                "explanation must cover, derived from the AST/CFG — not a "
                "reference prose answer."
            ),
        )

    def _business_rules(
        self, rec: SourceRecord, bundle: AnalysisBundle
    ) -> DatasetExample:
        rules = bundle.business_rules or []
        return self._example(
            rec,
            bundle,
            TaskType.BUSINESS_RULE_EXTRACTION,
            {"business_rules": rules, "rule_count": len(rules)},
            analysis=self._analysis_block(bundle, "ast", "dependencies"),
            provenance=Provenance.DETERMINISTIC_GENERATED,
            gt=GroundTruthStatus.DETERMINISTIC,
            source_locations=_locs_from_rules(rules),
        )

    def _risks(self, rec: SourceRecord, bundle: AnalysisBundle) -> DatasetExample:
        risks = bundle.risks or []
        return self._example(
            rec,
            bundle,
            TaskType.RISK_IDENTIFICATION,
            {"risks": risks, "risk_count": len(risks)},
            analysis=self._analysis_block(bundle, "dependencies", "cfg", "coverage"),
            provenance=Provenance.DETERMINISTIC_GENERATED,
            gt=GroundTruthStatus.DETERMINISTIC,
        )

    def _recommendation(
        self, rec: SourceRecord, bundle: AnalysisBundle
    ) -> DatasetExample:
        strat = bundle.strategy or {"primary": None, "recommendations": []}
        return self._example(
            rec,
            bundle,
            TaskType.MODERNIZATION_RECOMMENDATION,
            strat,
            analysis=self._analysis_block(
                bundle, "business_rules", "risks", "dependencies", "coverage"
            ),
            provenance=Provenance.DETERMINISTIC_GENERATED,
            gt=GroundTruthStatus.DETERMINISTIC,
        )

    def _structured(self, rec: SourceRecord, bundle: AnalysisBundle) -> DatasetExample:
        expected = {
            "ast": bundle.ast,
            "ir": bundle.ir,
            "cfg_summary": bundle.cfg_summary,
            "dependencies": bundle.dependencies or [],
        }
        return self._example(
            rec,
            bundle,
            TaskType.COBOL_TO_STRUCTURED,
            expected,
            analysis=ExampleAnalysis(),  # the answer IS the analysis
            provenance=Provenance.DETERMINISTIC_GENERATED,
            gt=GroundTruthStatus.DETERMINISTIC,
        )

    def _cobol_to_java(
        self, rec: SourceRecord, bundle: AnalysisBundle
    ) -> DatasetExample:
        if rec.reviewed_java is not None:
            expected = {
                "java": rec.reviewed_java,
                "compiles": rec.java_compiles,
            }
            gt = (
                GroundTruthStatus.EXECUTABLE_VERIFIED
                if rec.java_compiles
                else GroundTruthStatus.REVIEWED
            )
            prov = Provenance.REVIEWED_REFERENCE
            notes = "reviewed golden Java" + (
                "; compiles with javac" if rec.java_compiles else ""
            )
        else:
            expected = {"java": bundle.java_backend_output}
            gt = GroundTruthStatus.REFERENCE
            prov = Provenance.DETERMINISTIC_GENERATED
            notes = (
                "Java backend output, NOT a human-reviewed gold answer — "
                "reference only, must not be treated as ground truth."
            )
        return self._example(
            rec,
            bundle,
            TaskType.COBOL_TO_JAVA,
            expected,
            analysis=self._analysis_block(bundle, "ast", "ir", "dependencies"),
            provenance=prov,
            gt=gt,
            notes=notes,
        )

    def _modernization_qa(
        self, rec: SourceRecord, bundle: AnalysisBundle
    ) -> list[DatasetExample]:
        out: list[DatasetExample] = []
        primary = (bundle.strategy or {}).get("primary")
        qa: list[tuple[str, dict[str, Any], str]] = [
            (
                "What modernization strategy is appropriate for this program, "
                "and why?",
                {
                    "strategy": (primary or {}).get("strategy"),
                    "rationale": (primary or {}).get("rationale"),
                    "referenced_risk_ids": (primary or {}).get(
                        "referenced_risk_ids", []
                    ),
                },
                "strategy",
            ),
            (
                "What are the major business rules in this program?",
                {
                    "business_rules": [
                        {"rule_id": r["rule_id"], "condition": r["condition"]}
                        for r in (bundle.business_rules or [])
                    ]
                },
                "rules",
            ),
            (
                "What external dependencies does this program have?",
                {"external_calls": _call_targets(bundle)},
                "calls",
            ),
        ]
        for question, answer, variant in qa:
            out.append(
                self._example(
                    rec,
                    bundle,
                    TaskType.MODERNIZATION_QA,
                    {"answer": answer},
                    analysis=self._analysis_block(
                        bundle,
                        "business_rules",
                        "risks",
                        "strategy",
                        "dependencies",
                    ),
                    provenance=Provenance.DETERMINISTIC_GENERATED,
                    gt=GroundTruthStatus.DETERMINISTIC,
                    context={"question": question},
                    variant=variant,
                )
            )
        return out

    def _grounded_qa(
        self, rec: SourceRecord, bundle: AnalysisBundle
    ) -> list[DatasetExample]:
        out: list[DatasetExample] = []

        # Q1 — paragraph inventory (answerable purely from source structure)
        out.append(
            self._example(
                rec,
                bundle,
                TaskType.SOURCE_GROUNDED_QA,
                {
                    "answer": {
                        "paragraph_count": len(bundle.paragraphs),
                        "paragraphs": bundle.paragraphs,
                    },
                    "evidence": "PROCEDURE DIVISION paragraph labels",
                },
                analysis=self._analysis_block(bundle, "ast"),
                provenance=Provenance.DETERMINISTIC_GENERATED,
                gt=GroundTruthStatus.DETERMINISTIC,
                context={
                    "question": "How many paragraphs does this program have, "
                    "and what are their names?"
                },
                source_locations=_para_locs(rec.source, bundle.paragraphs),
                variant="paragraphs",
            )
        )

        # Q2 — unsupported syntax (a hallucination trap: the honest answer
        # may be "none")
        codes = _unsupported_codes(bundle)
        out.append(
            self._example(
                rec,
                bundle,
                TaskType.SOURCE_GROUNDED_QA,
                {
                    "answer": {
                        "has_unsupported_syntax": bool(codes),
                        "codes": codes,
                    },
                    "evidence": "parser syntax diagnostics",
                },
                analysis=self._analysis_block(bundle, "coverage"),
                provenance=Provenance.DETERMINISTIC_GENERATED,
                gt=GroundTruthStatus.DETERMINISTIC,
                context={
                    "question": "Does this program use any COBOL construct the "
                    "analyzer does not support? If so, which?"
                },
                variant="unsupported",
            )
        )
        return out

    # ------------------------------------------------------------------

    def _manifest(
        self, records: list[SourceRecord], result: BuildResult
    ) -> dict[str, Any]:
        per_task: dict[str, int] = {}
        per_prov: dict[str, int] = {}
        per_src_prov: dict[str, int] = {}
        per_gt: dict[str, int] = {}
        per_diff: dict[str, int] = {}
        for e in result.examples:
            per_task[e.task_type.value] = per_task.get(e.task_type.value, 0) + 1
            per_prov[e.metadata.provenance.value] = (
                per_prov.get(e.metadata.provenance.value, 0) + 1
            )
            per_src_prov[e.metadata.source_provenance.value] = (
                per_src_prov.get(e.metadata.source_provenance.value, 0) + 1
            )
            per_gt[e.metadata.ground_truth_status.value] = (
                per_gt.get(e.metadata.ground_truth_status.value, 0) + 1
            )
            per_diff[e.difficulty.value] = per_diff.get(e.difficulty.value, 0) + 1
        return {
            "dataset_version": DATASET_VERSION,
            "generator_version": GENERATOR_VERSION,
            "analysis_version": ANALYSIS_VERSION,
            "created_at": self._created_at,
            "source_count": len(records),
            "example_count": len(result.examples),
            "skipped_count": len(result.skipped),
            "skipped": result.skipped,
            "source_ids": sorted(r.source_id for r in records),
            "per_task": dict(sorted(per_task.items())),
            "per_provenance": dict(sorted(per_prov.items())),
            "per_source_provenance": dict(sorted(per_src_prov.items())),
            "per_ground_truth_status": dict(sorted(per_gt.items())),
            "per_difficulty": dict(sorted(per_diff.items())),
        }


# ---------------------------------------------------------------------------
# small deterministic helpers over an AnalysisBundle
# ---------------------------------------------------------------------------


def _program_id(bundle: AnalysisBundle) -> str | None:
    ast = bundle.ast
    if not ast:
        return None
    ident = (ast or {}).get("identification_division") or {}
    pid = ident.get("program_id")
    if isinstance(pid, dict):
        return pid.get("value") or pid.get("name")
    return pid


def _iter_ir_instructions(bundle: AnalysisBundle) -> list[dict[str, Any]]:
    ir = bundle.ir or {}
    out: list[dict[str, Any]] = []
    for mod in ir.get("modules", []):
        for fn in mod.get("functions", []):
            for blk in fn.get("blocks", []):
                out.extend(blk.get("instructions", []))
    return out


def _call_targets(bundle: AnalysisBundle) -> list[str]:
    targets = sorted(
        {
            _strip_quotes(str(d.get("target", "")))
            for d in (bundle.dependencies or [])
            if str(d.get("type", "")).upper() == "CALL" and d.get("target")
        }
    )
    return targets


def _has_if(bundle: AnalysisBundle) -> bool:
    return any(
        i.get("type") in ("IRIf", "IRConditionalBranch")
        for i in _iter_ir_instructions(bundle)
    )


def _has_loop(bundle: AnalysisBundle) -> bool:
    if any(i.get("type") == "IRPerformUntil" for i in _iter_ir_instructions(bundle)):
        return True
    cfg = bundle.cfg_summary or {}
    return "LOOP_BACK" in (cfg.get("edge_types") or {})


def _unsupported_codes(bundle: AnalysisBundle) -> list[str]:
    cov = bundle.coverage or {}
    us = cov.get("unsupported_syntax") or {}
    return sorted(us.get("codes", []))


def _required_concepts(bundle: AnalysisBundle) -> list[str]:
    """Concepts a correct explanation must mention (identifiers/verbs)."""
    concepts: set[str] = set()
    for name in bundle.paragraphs:
        concepts.add(name)
    for t in _call_targets(bundle):
        concepts.add(t)
    for i in _iter_ir_instructions(bundle):
        for key in ("result", "target", "left", "operand", "source"):
            v = i.get(key)
            if isinstance(v, str) and v and not _is_literal(v):
                concepts.add(v)
    return sorted(c for c in concepts if c)


def _locs_from_rules(rules: list[dict[str, Any]]) -> list[SourceLocation]:
    out: list[SourceLocation] = []
    for r in rules:
        for loc in r.get("source_locations", []) or []:
            if isinstance(loc, dict) and loc.get("line"):
                out.append(
                    SourceLocation(
                        line=int(loc["line"]),
                        column=int(loc.get("column", 1) or 1),
                        offset=int(loc.get("offset", 0) or 0),
                        filename=str(loc.get("filename", "") or ""),
                    )
                )
    return out


def _para_locs(source: str, paragraphs: list[str]) -> list[SourceLocation]:
    out: list[SourceLocation] = []
    lines = source.splitlines()
    for name in paragraphs:
        for idx, line in enumerate(lines, start=1):
            if line.strip().rstrip(".").upper() == name.upper():
                out.append(SourceLocation(line=idx, snippet=line.strip()))
                break
    return out


def _strip_quotes(text: str) -> str:
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in {"'", '"'}:
        return t[1:-1]
    return t


def _is_literal(text: str) -> bool:
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in {"'", '"'}:
        return True
    cand = t.lstrip("+-")
    return bool(cand) and all(p.isdigit() for p in cand.split(".") if p)
