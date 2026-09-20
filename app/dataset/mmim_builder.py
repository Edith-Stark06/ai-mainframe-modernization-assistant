"""
MMIM Dataset Builder.

Constructs training-ready DatasetExample records for the Mainframe Modernization
Intelligence Model (MMIM) across 8 core task families, backed by deterministic
Phase 1–5 analysis, target architecture derivation, and behavioral validation.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.behavioral.extraction.extractor import extract_behavioral_tests
from app.dataset.analysis_bundle import AnalysisBundle, build_analysis_bundle
from app.dataset.builder import BuildResult, SourceRecord
from app.dataset.schema import (
    DatasetExample,
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
from app.dataset.version import (
    ANALYSIS_VERSION,
    MMIM_DATASET_VERSION,
    MMIM_GENERATOR_VERSION,
)
from app.java_modernization.architecture.builder import build_architecture

__all__ = ["MMIMDatasetBuilder", "build_mmim_dataset"]


class MMIMDatasetBuilder:
    """Builder for the MMIM supervised dataset."""

    def __init__(
        self,
        work_dir: str | Path,
        secret_config: SecretScanConfig | None = None,
        created_at: str | None = None,
        dataset_version: str = MMIM_DATASET_VERSION,
        generator_version: str = MMIM_GENERATOR_VERSION,
        strict_eligibility: bool = False,
    ) -> None:
        self.work_dir = Path(work_dir)
        self.scanner = SecretScanner(secret_config)
        self._created_at = created_at or "2026-09-17T00:00:00Z"
        self._dataset_version = dataset_version
        self._generator_version = generator_version
        #: When True, a task is only emitted when its ground truth is
        #: semantically meaningful (e.g. VALIDATION_REASONING requires at
        #: least one derivable behavioral test; TRANSFORMATION_PLANNING
        #: requires at least one architecture component). Ineligible tasks
        #: are recorded in ``result.skipped`` with source_id, task_type,
        #: reason, and parser/analysis status instead of being silently
        #: emitted as an empty/meaningless target. mmim-v1 always builds
        #: with this False, preserving its original semantics exactly.
        self.strict_eligibility = strict_eligibility

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
            examples, skips = self._examples_for(rec, bundle)
            result.skipped.extend(skips)
            for ex in examples:
                if ex.example_id in seen_ids:
                    continue
                seen_ids.add(ex.example_id)
                result.examples.append(ex)

        result.examples.sort(
            key=lambda e: (e.task_type.value, e.input.source_id, e.example_id)
        )
        result.manifest = self._manifest(records, result)
        return result

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
            generator_version=self._generator_version,
            analysis_version=ANALYSIS_VERSION,
            ground_truth_status=gt,
            source_sha256=bundle.source_sha256,
            notes=notes,
            created_at=self._created_at,
        )

    def _analysis_block(self, bundle: AnalysisBundle, *fields: str) -> ExampleAnalysis:
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
            dataset_version=self._dataset_version,
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

    def _examples_for(
        self, rec: SourceRecord, bundle: AnalysisBundle
    ) -> tuple[list[DatasetExample], list[dict[str, Any]]]:
        out: list[DatasetExample] = []
        skips: list[dict[str, Any]] = []

        def skip(task: TaskType, reason: str) -> None:
            skips.append(
                {
                    "source_id": rec.source_id,
                    "task_type": task.value,
                    "reason": reason,
                    "parser_status": {
                        "parse_complete": bool(bundle.success),
                        "ast_present": bundle.ast is not None,
                        "syntax_diagnostic_count": len(bundle.syntax_diagnostics),
                        "unsupported_codes": _unsupported_codes(bundle),
                    },
                }
            )

        # 1. PROGRAM_UNDERSTANDING — always meaningful: a structural
        # summary is derivable even from a partially-parsed source.
        out.append(self._program_understanding(rec, bundle))

        # 2. BUSINESS_RULE_EXTRACTION — an empty rule set is a legitimate
        # answer when the source genuinely has none; only skip if the
        # parser produced no AST to extract rules from at all.
        if not self.strict_eligibility or bundle.ast is not None:
            out.append(self._business_rules(rec, bundle))
        else:
            skip(TaskType.BUSINESS_RULE_EXTRACTION, "parser_failed_no_ast")

        # 3. DEPENDENCY_REASONING
        if not self.strict_eligibility or bundle.ast is not None:
            out.append(self._dependencies(rec, bundle))
        else:
            skip(TaskType.DEPENDENCY_REASONING, "parser_failed_no_ast")

        # 4. RISK_CLASSIFICATION — bundle.risks is None only when
        # modernization intelligence never ran (ast missing); an empty
        # risk list from a source that *was* analyzed is a real finding.
        if not self.strict_eligibility or bundle.risks is not None:
            out.append(self._risks(rec, bundle))
        else:
            skip(TaskType.RISK_CLASSIFICATION, "parser_failed_no_risk_analysis")

        # 5. MODERNIZATION_STRATEGY
        if not self.strict_eligibility or bundle.strategy is not None:
            out.append(self._strategy(rec, bundle))
        else:
            skip(TaskType.MODERNIZATION_STRATEGY, "parser_failed_no_strategy_analysis")

        # 6. TRANSFORMATION_PLANNING — only emit when the architecture
        # builder produced at least one real component (DTO/SERVICE/…);
        # an all-empty plan would teach the model that empty architecture
        # is the normal answer.
        arch = build_architecture(bundle)
        arch_dict = arch.to_dict()
        if not self.strict_eligibility or arch_dict.get("components"):
            out.append(self._transformation_planning(rec, bundle, arch_dict))
        else:
            skip(TaskType.TRANSFORMATION_PLANNING, "architecture_builder_no_structure")

        # 7. COBOL_TO_JAVA
        if bundle.ast is not None and bundle.java_backend_output:
            out.append(self._cobol_to_java(rec, bundle))
        elif self.strict_eligibility:
            skip(TaskType.COBOL_TO_JAVA, "no_java_backend_output")

        # 8. VALIDATION_REASONING — do not teach "zero tests" as a normal
        # answer merely because the deterministic extractor could not
        # derive any; skip and record the limitation instead.
        suite = extract_behavioral_tests(bundle)
        if not self.strict_eligibility or suite.tests:
            out.append(self._validation_reasoning(rec, bundle, suite))
        else:
            skip(TaskType.VALIDATION_REASONING, "no_derivable_behavioral_tests")

        return [e for e in out if e is not None], skips

    def _program_understanding(
        self, rec: SourceRecord, bundle: AnalysisBundle
    ) -> DatasetExample:
        divisions = []
        ast = bundle.ast or {}
        if ast.get("identification_division"):
            divisions.append("IDENTIFICATION DIVISION")
        if ast.get("environment_division"):
            divisions.append("ENVIRONMENT DIVISION")
        if ast.get("data_division"):
            divisions.append("DATA DIVISION")
        if ast.get("procedure_division"):
            divisions.append("PROCEDURE DIVISION")

        variables = []
        data_div = ast.get("data_division") or {}
        ws = data_div.get("working_storage_section") or {}
        for item in ws.get("entries", []):
            if isinstance(item, dict) and item.get("name"):
                variables.append(
                    {
                        "name": item["name"],
                        "level": item.get("level", 1),
                        "picture": item.get("picture"),
                    }
                )

        expected = {
            "program_id": _program_id(bundle),
            "divisions": divisions,
            "paragraph_count": len(bundle.paragraphs),
            "paragraphs": bundle.paragraphs,
            "variables": variables,
            "external_calls": _call_targets(bundle),
            "control_flow": {
                "has_loops": _has_loop(bundle),
                "has_conditionals": _has_if(bundle),
                "cfg_nodes": (bundle.cfg_summary or {}).get("node_count", 0),
                "cfg_edges": (bundle.cfg_summary or {}).get("edge_count", 0),
            },
            "unsupported_constructs": _unsupported_codes(bundle),
            "parser_diagnostics": {
                "parse_complete": bool(bundle.success),
                "syntax_diagnostic_count": len(bundle.syntax_diagnostics),
                "diagnostic_codes": sorted(
                    {
                        d.get("code", "")
                        for d in bundle.syntax_diagnostics
                        if d.get("code")
                    }
                ),
            },
        }
        return self._example(
            rec,
            bundle,
            TaskType.PROGRAM_UNDERSTANDING,
            expected,
            analysis=self._analysis_block(
                bundle, "ast", "cfg", "dependencies", "coverage"
            ),
            provenance=Provenance.DETERMINISTIC_GENERATED,
            gt=GroundTruthStatus.DETERMINISTIC,
            source_locations=_para_locs(rec.source, bundle.paragraphs),
            notes="Deterministic structural summary derived from AST, CFG and symbol table.",
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
            notes="Deterministic business rules extracted with exact source evidence.",
        )

    def _dependencies(
        self, rec: SourceRecord, bundle: AnalysisBundle
    ) -> DatasetExample:
        deps = bundle.dependencies or []
        calls = _call_targets(bundle)
        performs = _perform_targets(bundle)
        expected = {
            "dependencies": deps,
            "dependency_count": len(deps),
            "external_calls": calls,
            "internal_performs": performs,
            "coupling": {
                "total_edges": len(deps),
                "external_calls_count": len(calls),
                "internal_performs_count": len(performs),
            },
        }
        return self._example(
            rec,
            bundle,
            TaskType.DEPENDENCY_REASONING,
            expected,
            analysis=self._analysis_block(bundle, "ast", "cfg", "dependencies"),
            provenance=Provenance.DETERMINISTIC_GENERATED,
            gt=GroundTruthStatus.DETERMINISTIC,
            notes="Deterministic dependency graph of internal PERFORM and external CALL relationships.",
        )

    def _risks(self, rec: SourceRecord, bundle: AnalysisBundle) -> DatasetExample:
        risks = bundle.risks or []
        severities = [r.get("severity", "LOW") for r in risks if isinstance(r, dict)]
        highest = "LOW"
        if "HIGH" in severities or "CRITICAL" in severities:
            highest = "HIGH"
        elif "MEDIUM" in severities:
            highest = "MEDIUM"

        return self._example(
            rec,
            bundle,
            TaskType.RISK_CLASSIFICATION,
            {"risks": risks, "risk_count": len(risks), "highest_severity": highest},
            analysis=self._analysis_block(bundle, "dependencies", "cfg", "coverage"),
            provenance=Provenance.DETERMINISTIC_GENERATED,
            gt=GroundTruthStatus.DETERMINISTIC,
            notes="Deterministic risk report classifying modernization and architectural hazards.",
        )

    def _strategy(self, rec: SourceRecord, bundle: AnalysisBundle) -> DatasetExample:
        strat = bundle.strategy or {"primary": None, "recommendations": []}
        return self._example(
            rec,
            bundle,
            TaskType.MODERNIZATION_STRATEGY,
            strat,
            analysis=self._analysis_block(
                bundle, "business_rules", "risks", "dependencies", "coverage"
            ),
            provenance=Provenance.DETERMINISTIC_GENERATED,
            gt=GroundTruthStatus.DETERMINISTIC,
            notes="Deterministic 7Rs modernization strategy recommendation and scoring rationale.",
        )

    def _transformation_planning(
        self, rec: SourceRecord, bundle: AnalysisBundle, arch_dict: dict[str, Any]
    ) -> DatasetExample:
        return self._example(
            rec,
            bundle,
            TaskType.TRANSFORMATION_PLANNING,
            arch_dict,
            analysis=self._analysis_block(
                bundle, "ast", "ir", "dependencies", "business_rules", "strategy"
            ),
            provenance=Provenance.DETERMINISTIC_GENERATED,
            gt=GroundTruthStatus.DETERMINISTIC,
            notes="Deterministic target Java architecture plan with DTOs, services, and source mappings.",
        )

    def _cobol_to_java(
        self, rec: SourceRecord, bundle: AnalysisBundle
    ) -> DatasetExample:
        compiles = False
        if rec.reviewed_java is not None:
            java_src = rec.reviewed_java
            compiles = (
                rec.java_compiles
                if rec.java_compiles is not None
                else _check_javac(java_src)
            )
            gt = (
                GroundTruthStatus.EXECUTABLE_VERIFIED
                if compiles
                else GroundTruthStatus.REVIEWED
            )
            prov = Provenance.REVIEWED_REFERENCE
            notes = "Reviewed golden Java fixture; verified with javac."
        else:
            java_src = bundle.java_backend_output
            compiles = _check_javac(java_src)
            gt = (
                GroundTruthStatus.DETERMINISTIC
                if compiles
                else GroundTruthStatus.REFERENCE
            )
            prov = Provenance.DETERMINISTIC_GENERATED
            notes = (
                "Deterministic backend Java output; compilation verified."
                if compiles
                else "Deterministic backend Java output (compilation unverified)."
            )

        expected = {
            "java": java_src,
            "compiles": compiles,
        }
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

    def _validation_reasoning(
        self, rec: SourceRecord, bundle: AnalysisBundle, suite: Any
    ) -> DatasetExample:
        test_dicts = [t.to_dict() for t in suite.tests]
        expected = {
            "suite_hash": suite.content_hash(),
            "test_count": len(suite.tests),
            "tests": test_dicts,
            "validation_status": "DETERMINISTIC",
        }
        return self._example(
            rec,
            bundle,
            TaskType.VALIDATION_REASONING,
            expected,
            analysis=self._analysis_block(bundle, "ast", "business_rules"),
            provenance=Provenance.DETERMINISTIC_GENERATED,
            gt=GroundTruthStatus.DETERMINISTIC,
            notes="Deterministic behavioral test specification derived from business rule partitions.",
        )

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
            "dataset_version": self._dataset_version,
            "generator_version": self._generator_version,
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


def build_mmim_dataset(
    output_dir: str | Path,
    records: list[SourceRecord],
    *,
    seed: int = 42,
    dataset_version: str = MMIM_DATASET_VERSION,
    generator_version: str = MMIM_GENERATOR_VERSION,
    strict_eligibility: bool = False,
    created_at: str = "2026-09-17T00:00:00Z",
) -> tuple[BuildResult, Any, Any, Any]:
    """
    Build, split, leakage-check, and validate the MMIM dataset.
    Writes all JSONL and report files into output_dir.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        builder = MMIMDatasetBuilder(
            work_dir=tmp,
            dataset_version=dataset_version,
            generator_version=generator_version,
            strict_eligibility=strict_eligibility,
            created_at=created_at,
        )
        build_result = builder.build(records)

    # 1. Write all.jsonl
    from app.dataset.io import write_jsonl
    from app.dataset.leakage import detect_leakage
    from app.dataset.splitting import SplitRatios, split_dataset
    from app.dataset.validation import validate_dataset

    all_path = out / "all.jsonl"
    write_jsonl(all_path, build_result.examples)

    # 2. Split (70/15/15) grouped by source program
    split_res = split_dataset(
        build_result.examples,
        seed=seed,
        ratios=SplitRatios(train=0.70, validation=0.15, test=0.15),
        dataset_version=dataset_version,
    )
    write_jsonl(out / "train.jsonl", split_res.train)
    write_jsonl(out / "validation.jsonl", split_res.validation)
    write_jsonl(out / "test.jsonl", split_res.test)

    # 3. Manifests
    import json

    (out / "manifest.json").write_bytes(
        f"{json.dumps(build_result.manifest, indent=2, sort_keys=True)}\n".encode()
    )
    (out / "split_manifest.json").write_bytes(
        f"{json.dumps(split_res.manifest(), indent=2, sort_keys=True)}\n".encode()
    )

    # 4. Leakage report
    leakage_rep = detect_leakage(split_res.train, split_res.validation, split_res.test)
    (out / "leakage_report.json").write_bytes(
        f"{json.dumps(leakage_rep.to_dict(), indent=2, sort_keys=True)}\n".encode()
    )

    # 5. Validation report
    val_rep = validate_dataset(all_path, expected_version=dataset_version)
    (out / "validation_report.json").write_bytes(
        f"{json.dumps(val_rep.to_dict(), indent=2, sort_keys=True)}\n".encode()
    )

    return build_result, split_res, leakage_rep, val_rep


def _program_id(bundle: AnalysisBundle) -> str | None:
    ast = bundle.ast
    if not ast:
        return None
    ident = (ast or {}).get("identification_division") or {}
    pid = ident.get("program_id")
    if isinstance(pid, dict):
        return pid.get("value") or pid.get("name")
    return pid


def _call_targets(bundle: AnalysisBundle) -> list[str]:
    return sorted(
        {
            _strip_quotes(str(d.get("target", "")))
            for d in (bundle.dependencies or [])
            if str(d.get("type", "")).upper() == "CALL" and d.get("target")
        }
    )


def _perform_targets(bundle: AnalysisBundle) -> list[str]:
    return sorted(
        {
            _strip_quotes(str(d.get("target", "")))
            for d in (bundle.dependencies or [])
            if str(d.get("type", "")).upper() == "PERFORM" and d.get("target")
        }
    )


def _coupling_metrics(bundle: AnalysisBundle) -> dict[str, int]:
    deps = bundle.dependencies or []
    calls = _call_targets(bundle)
    performs = _perform_targets(bundle)
    return {
        "total_dependencies": len(deps),
        "external_calls_count": len(calls),
        "internal_performs_count": len(performs),
    }


def _highest_risk_severity(risks: list[dict[str, Any]]) -> str:
    severities = [r.get("severity", "LOW") for r in risks if isinstance(r, dict)]
    if "HIGH" in severities or "CRITICAL" in severities:
        return "HIGH"
    if "MEDIUM" in severities:
        return "MEDIUM"
    return "LOW" if severities else "NONE"


def _has_if(bundle: AnalysisBundle) -> bool:
    ir = bundle.ir or {}
    for mod in ir.get("modules", []):
        for fn in mod.get("functions", []):
            for blk in fn.get("blocks", []):
                for i in blk.get("instructions", []):
                    if i.get("type") in ("IRIf", "IRConditionalBranch"):
                        return True
    return False


def _has_loop(bundle: AnalysisBundle) -> bool:
    ir = bundle.ir or {}
    for mod in ir.get("modules", []):
        for fn in mod.get("functions", []):
            for blk in fn.get("blocks", []):
                for i in blk.get("instructions", []):
                    if i.get("type") == "IRPerformUntil":
                        return True
    cfg = bundle.cfg_summary or {}
    return "LOOP_BACK" in (cfg.get("edge_types") or {})


def _unsupported_codes(bundle: AnalysisBundle) -> list[str]:
    cov = bundle.coverage or {}
    us = cov.get("unsupported_syntax") or {}
    return sorted(us.get("codes", []))


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


def _check_javac(java_source: str) -> bool:
    if not shutil.which("javac") or not java_source.strip():
        return False
    match = re.search(r"public class ([A-Za-z0-9_]+)", java_source)
    class_name = match.group(1) if match else "TempProgram"
    with tempfile.TemporaryDirectory() as tmp:
        fpath = Path(tmp) / f"{class_name}.java"
        fpath.write_text(java_source, encoding="utf-8")
        try:
            res = subprocess.run(
                ["javac", str(fpath)],
                capture_output=True,
                check=False,
            )
            return res.returncode == 0
        except Exception:
            return False
