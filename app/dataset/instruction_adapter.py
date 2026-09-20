"""Instruction format adapter for the MMIM dataset.

Converts structured `DatasetExample` records from mmim-v1 into
chat/instruction-tuning examples for Qwen2.5-Coder and similar LLMs.

Design principles:
- Explicit, auditable evidence and structured JSON targets.
- NO hidden chain-of-thought or fabricated internal reasoning fields.
- Full provenance preservation (source_id, source_sha256, task_type, ground_truth_status).
- Token and character count statistics tracked for every example.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.dataset.schema import (
    DatasetExample,
    TaskType,
)
from app.dataset.version import MMIM_DATASET_VERSION

INSTRUCTION_ADAPTER_VERSION = "mmim-inst-v1"


def estimate_tokens(text: str) -> int:
    """Estimate token count for code and natural language text.

    Uses a ~3.8 character/token heuristic standard for byte-fallback tokenizers.
    """
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 3.8))


class ChatMessage(BaseModel):
    """A single turn in a conversational training example."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class InstructionMetadata(BaseModel):
    """Provenance and token sizing metadata for an instruction example."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    source_sha256: str
    dataset_version: str
    ground_truth_status: str
    task_type: str
    generator_version: str
    license: str = "MIT"
    char_count_user: int = Field(ge=0)
    char_count_assistant: int = Field(ge=0)
    char_count_total: int = Field(ge=0)
    estimated_tokens_user: int = Field(ge=0)
    estimated_tokens_assistant: int = Field(ge=0)
    estimated_tokens_total: int = Field(ge=0)


class InstructionExample(BaseModel):
    """Complete instruction-tuning example."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    task: str
    messages: list[ChatMessage]
    metadata: InstructionMetadata

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "messages": [{"role": m.role, "content": m.content} for m in self.messages],
            "metadata": self.metadata.model_dump(),
        }


# --------------------------------------------------------------------------
# Task-specific prompt builders
# --------------------------------------------------------------------------


def _build_user_prompt(example: DatasetExample) -> str:
    task = example.task_type
    cobol = example.input.source.strip()
    source_id = example.input.source_id

    if task == TaskType.PROGRAM_UNDERSTANDING:
        return (
            f"You are a mainframe modernization assistant. Analyze the following COBOL program ('{source_id}') "
            "and produce a comprehensive structural summary in JSON format.\n\n"
            "Extract:\n"
            "- Program ID and declared divisions\n"
            "- All declared paragraph names in procedural order\n"
            "- Working-Storage variable declarations (names, levels, picture clauses)\n"
            "- External program CALL targets\n"
            "- Control flow characteristics (loops, conditionals, CFG nodes/edges)\n\n"
            "COBOL SOURCE:\n"
            f"```cobol\n{cobol}\n```\n\n"
            "Respond strictly with valid, well-formed JSON conforming to the structural summary schema."
        )

    if task == TaskType.BUSINESS_RULE_EXTRACTION:
        return (
            f"You are a business logic extraction expert. Extract all deterministic business rules and decision logic "
            f"from the following COBOL program ('{source_id}').\n\n"
            "For each extracted rule, include:\n"
            "- Rule ID (e.g. 'BR-001') and business category\n"
            "- Context paragraph and exact condition expression\n"
            "- Guarded action or state transformation\n"
            "- Variables read, written, and checked\n"
            "- Exact source line locations and supporting analysis evidence\n\n"
            "COBOL SOURCE:\n"
            f"```cobol\n{cobol}\n```\n\n"
            "Respond strictly with a JSON object containing the 'rules' array and 'rule_count'."
        )

    if task == TaskType.DEPENDENCY_REASONING:
        return (
            f"You are a program analysis expert. Analyze the control flow and call dependencies for the following "
            f"COBOL program ('{source_id}').\n\n"
            "Extract:\n"
            "- Internal paragraph PERFORM targets\n"
            "- External program CALL targets\n"
            "- Direct dependency edges with source paragraph, target, and dependency type\n"
            "- Coupling metrics (total edges, internal performs count, external calls count)\n\n"
            "COBOL SOURCE:\n"
            f"```cobol\n{cobol}\n```\n\n"
            "Respond strictly with a JSON object containing the dependency graph and coupling metrics."
        )

    if task == TaskType.RISK_CLASSIFICATION:
        return (
            f"You are a mainframe modernization risk auditor. Evaluate the following COBOL program ('{source_id}') "
            "for modernization and architectural risks.\n\n"
            "Identify:\n"
            "- Highest overall risk severity ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')\n"
            "- Specific risk items categorized by hazard (e.g. coupling, dead code, complexity, missing error handling)\n"
            "- Detailed risk descriptions with supporting evidence\n\n"
            "COBOL SOURCE:\n"
            f"```cobol\n{cobol}\n```\n\n"
            "Respond strictly with a JSON object containing 'highest_severity', 'risk_count', and the 'risks' array."
        )

    if task == TaskType.MODERNIZATION_STRATEGY:
        return (
            f"You are a mainframe modernization architect. Evaluate the 7Rs modernization strategy for the following "
            f"COBOL program ('{source_id}') based on its complexity, dependencies, and business rules.\n\n"
            "Determine:\n"
            "- Primary recommended strategy (e.g. 'REFACTOR', 'REPLATFORM', 'REARCHITECT', 'REHOST', 'REPLACE', 'RETAIN', 'RETIRE')\n"
            "- Scored strategy alternatives with technical rationale\n"
            "- Governing architectural factors\n\n"
            "COBOL SOURCE:\n"
            f"```cobol\n{cobol}\n```\n\n"
            "Respond strictly with a JSON object containing the strategy recommendation and scoring rationale."
        )

    if task == TaskType.TRANSFORMATION_PLANNING:
        return (
            f"You are a Java modernization architect. Generate a target object-oriented architecture and transformation plan "
            f"for migrating the following COBOL program ('{source_id}') to Java.\n\n"
            "Specify:\n"
            "- Target Java package namespace\n"
            "- Main entry and service class structure\n"
            "- Data Transfer Objects (DTOs) mapped from COBOL Working-Storage records\n"
            "- Business service classes and methods mapped from procedure logic\n"
            "- Repository and external interface mappings\n\n"
            "COBOL SOURCE:\n"
            f"```cobol\n{cobol}\n```\n\n"
            "Respond strictly with a JSON object detailing the target architecture plan."
        )

    if task == TaskType.COBOL_TO_JAVA:
        return (
            f"You are an enterprise Java modernization engineer. Modernize the following COBOL program ('{source_id}') "
            "into clean, compilable, idiomatic Java.\n\n"
            "Requirements:\n"
            "- Generate complete, self-contained Java source code.\n"
            "- Preserve exact variable types, calculations, conditional branching, and control flow.\n"
            "- Use clean object-oriented class structure.\n\n"
            "COBOL SOURCE:\n"
            f"```cobol\n{cobol}\n```\n\n"
            "Respond strictly with a JSON object containing 'class_name', 'java_code', and 'compiles'."
        )

    if task == TaskType.VALIDATION_REASONING:
        return (
            f"You are a software test engineer. Derive a deterministic behavioral validation test suite to verify the "
            f"functional equivalence of modernizing the following COBOL program ('{source_id}').\n\n"
            "Specify:\n"
            "- Equivalence partition and boundary test cases\n"
            "- Concrete input variable assignments\n"
            "- Expected output state assertions derived from business rule logic\n\n"
            "COBOL SOURCE:\n"
            f"```cobol\n{cobol}\n```\n\n"
            "Respond strictly with a JSON object containing the validation test suite."
        )

    raise ValueError(f"Unsupported task type for instruction conversion: {task}")


def _build_assistant_response(example: DatasetExample) -> str:
    task = example.task_type
    expected = example.expected_output

    if task == TaskType.PROGRAM_UNDERSTANDING:
        data = {
            "program_id": expected.get("program_id"),
            "divisions": expected.get("divisions", []),
            "paragraph_count": expected.get("paragraph_count", 0),
            "paragraphs": expected.get("paragraphs", []),
            "variables": expected.get("variables", []),
            "external_calls": expected.get("external_calls", []),
            "control_flow": expected.get("control_flow", {}),
            "unsupported_constructs": expected.get("unsupported_constructs", []),
        }
        return json.dumps(data, indent=2, sort_keys=True)

    if task == TaskType.BUSINESS_RULE_EXTRACTION:
        raw_rules = expected.get("business_rules", [])
        rules = []
        for r in raw_rules:
            if not isinstance(r, dict):
                continue
            src_locs = r.get("source_locations", [])
            lines: list[int] = sorted(
                {
                    int(loc["line"])
                    for loc in src_locs
                    if isinstance(loc, dict) and isinstance(loc.get("line"), int)
                }
            )
            rules.append(
                {
                    "rule_id": r.get("rule_id"),
                    "category": r.get("category"),
                    "paragraph": r.get("paragraph"),
                    "condition": r.get("condition"),
                    "action": (
                        r.get("actions", [{}])[0].get("raw")
                        if r.get("actions")
                        else None
                    ),
                    "source_lines": lines,
                    "variables": r.get("variables", {}),
                    "evidence": r.get("evidence", []),
                }
            )
        data = {
            "rules": rules,
            "rule_count": len(rules),
        }
        return json.dumps(data, indent=2, sort_keys=True)

    if task == TaskType.DEPENDENCY_REASONING:
        raw_deps = expected.get("dependencies", [])
        deps = []
        for d in raw_deps:
            if not isinstance(d, dict):
                continue
            loc = d.get("source_location") or {}
            deps.append(
                {
                    "source": d.get("source"),
                    "target": d.get("target"),
                    "type": d.get("type"),
                    "line": loc.get("line") if isinstance(loc, dict) else None,
                }
            )
        data = {
            "internal_performs": expected.get("internal_performs", []),
            "external_calls": expected.get("external_calls", []),
            "dependencies": deps,
            "coupling": expected.get("coupling", {}),
        }
        return json.dumps(data, indent=2, sort_keys=True)

    if task == TaskType.RISK_CLASSIFICATION:
        raw_risks = expected.get("risks", [])
        risks = []
        for r in raw_risks:
            if not isinstance(r, dict):
                continue
            risks.append(
                {
                    "category": r.get("category"),
                    "severity": r.get("severity"),
                    "description": r.get("description"),
                    "evidence": r.get("evidence", []),
                }
            )
        data = {
            "highest_severity": expected.get("highest_severity", "LOW"),
            "risk_count": len(risks),
            "risks": risks,
        }
        return json.dumps(data, indent=2, sort_keys=True)

    if task == TaskType.MODERNIZATION_STRATEGY:
        data = {
            "primary_strategy": expected.get("primary"),
            "recommendations": expected.get("recommendations", []),
            "factors": expected.get("factors", {}),
        }
        return json.dumps(data, indent=2, sort_keys=True)

    if task == TaskType.TRANSFORMATION_PLANNING:
        components = expected.get("components", [])

        def _components_of(component_type: str) -> list[dict[str, Any]]:
            return [
                {
                    "name": c.get("name"),
                    "responsibility": c.get("responsibility"),
                    "business_rule_ids": c.get("business_rule_ids", []),
                }
                for c in components
                if isinstance(c, dict) and c.get("type") == component_type
            ]

        data = {
            "target_package": expected.get("target_package", "com.modernization"),
            "dtos": _components_of("DTO"),
            "services": _components_of("SERVICE"),
            "repositories": _components_of("REPOSITORY"),
            "component_counts_by_type": expected.get("by_type", {}),
            "source_mappings": expected.get("source_mappings", []),
        }
        return json.dumps(data, indent=2, sort_keys=True)

    if task == TaskType.COBOL_TO_JAVA:
        java_src = expected.get("java") or expected.get("java_code") or ""
        # Determine class name from Java code or fallback
        class_name = "ModernizedProgram"
        for line in java_src.splitlines():
            if "public class " in line:
                tokens = line.split("public class ")[1].split()
                if tokens:
                    class_name = tokens[0].rstrip("{").strip()
                break
        data = {
            "class_name": class_name,
            "java_code": java_src,
            "compiles": expected.get("compiles", False),
        }
        return json.dumps(data, indent=2, sort_keys=True)

    if task == TaskType.VALIDATION_REASONING:
        data = {
            "suite_hash": expected.get("suite_hash"),
            "test_count": expected.get("test_count", 0),
            "tests": expected.get("tests", []),
            "validation_status": expected.get("validation_status", "DETERMINISTIC"),
        }
        return json.dumps(data, indent=2, sort_keys=True)

    raise ValueError(f"Unsupported task type for response formatting: {task}")


# --------------------------------------------------------------------------
# Adapter conversion functions
# --------------------------------------------------------------------------


def convert_example(example: DatasetExample) -> InstructionExample:
    """Convert a single `DatasetExample` into an `InstructionExample`."""
    user_content = _build_user_prompt(example)
    assistant_content = _build_assistant_response(example)

    char_user = len(user_content)
    char_asst = len(assistant_content)
    char_total = char_user + char_asst

    tok_user = estimate_tokens(user_content)
    tok_asst = estimate_tokens(assistant_content)
    tok_total = tok_user + tok_asst

    meta = InstructionMetadata(
        source_id=example.input.source_id,
        source_sha256=example.metadata.source_sha256,
        dataset_version=example.dataset_version or MMIM_DATASET_VERSION,
        ground_truth_status=example.metadata.ground_truth_status.value,
        task_type=example.task_type.value,
        generator_version=INSTRUCTION_ADAPTER_VERSION,
        license=example.metadata.license or "MIT",
        char_count_user=char_user,
        char_count_assistant=char_asst,
        char_count_total=char_total,
        estimated_tokens_user=tok_user,
        estimated_tokens_assistant=tok_asst,
        estimated_tokens_total=tok_total,
    )

    messages = [
        ChatMessage(role="user", content=user_content),
        ChatMessage(role="assistant", content=assistant_content),
    ]

    return InstructionExample(
        id=example.example_id,
        task=example.task_type.value,
        messages=messages,
        metadata=meta,
    )


def convert_dataset(examples: list[DatasetExample]) -> list[InstructionExample]:
    """Convert a list of DatasetExamples into InstructionExamples."""
    return [convert_example(e) for e in examples]


def build_instruction_dataset(
    input_dir: Path | str = Path("data/dataset/mmim-v1"),
    output_dir: Path | str = Path("data/dataset/mmim-v1/instruction"),
) -> dict[str, Any]:
    """Build instruction-tuning splits and manifest from mmim-v1 dataset.

    Reads `train.jsonl`, `validation.jsonl`, `test.jsonl` from input_dir and
    writes converted instruction format to output_dir with strict LF line endings.
    """
    inp = Path(input_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    from app.dataset.io import read_examples

    train_raw = read_examples(inp / "train.jsonl")
    val_raw = read_examples(inp / "validation.jsonl")
    test_raw = read_examples(inp / "test.jsonl")

    train_inst = convert_dataset(train_raw)
    val_inst = convert_dataset(val_raw)
    test_inst = convert_dataset(test_raw)
    all_inst = train_inst + val_inst + test_inst

    # Write JSONL files with LF bytes
    def _write_inst_jsonl(path: Path, items: list[InstructionExample]) -> None:
        content = (
            "\n".join(json.dumps(item.to_dict(), sort_keys=True) for item in items)
            + "\n"
        )
        path.write_bytes(content.encode("utf-8"))

    _write_inst_jsonl(out / "train.jsonl", train_inst)
    _write_inst_jsonl(out / "validation.jsonl", val_inst)
    _write_inst_jsonl(out / "test.jsonl", test_inst)

    # Statistics & manifest calculation
    all_tok_users = [ex.metadata.estimated_tokens_user for ex in all_inst]
    all_tok_assts = [ex.metadata.estimated_tokens_assistant for ex in all_inst]
    all_tok_totals = [ex.metadata.estimated_tokens_total for ex in all_inst]
    all_char_totals = [ex.metadata.char_count_total for ex in all_inst]

    per_task: dict[str, int] = {}
    per_gt: dict[str, int] = {}
    for ex in all_inst:
        per_task[ex.task] = per_task.get(ex.task, 0) + 1
        gt = ex.metadata.ground_truth_status
        per_gt[gt] = per_gt.get(gt, 0) + 1

    source_ids = sorted({ex.metadata.source_id for ex in all_inst})

    # Benchmark leakage verification
    from app.dataset.corpus import BENCHMARK_SOURCE_IDS

    bench_overlap = set(source_ids) & BENCHMARK_SOURCE_IDS

    dataset_versions = sorted({ex.metadata.dataset_version for ex in all_inst})
    if len(dataset_versions) > 1:
        raise ValueError(
            f"instruction examples span multiple dataset versions: {dataset_versions}"
        )
    resolved_dataset_version = (
        dataset_versions[0] if dataset_versions else MMIM_DATASET_VERSION
    )

    manifest = {
        "dataset_version": resolved_dataset_version,
        "adapter_version": INSTRUCTION_ADAPTER_VERSION,
        "source_count": len(source_ids),
        "example_count": len(all_inst),
        "split_counts": {
            "train": len(train_inst),
            "validation": len(val_inst),
            "test": len(test_inst),
        },
        "per_task": dict(sorted(per_task.items())),
        "per_ground_truth_status": dict(sorted(per_gt.items())),
        "token_statistics": {
            "user_tokens": {
                "min": min(all_tok_users),
                "max": max(all_tok_users),
                "avg": round(sum(all_tok_users) / len(all_tok_users), 2),
            },
            "assistant_tokens": {
                "min": min(all_tok_assts),
                "max": max(all_tok_assts),
                "avg": round(sum(all_tok_assts) / len(all_tok_assts), 2),
            },
            "total_tokens": {
                "min": min(all_tok_totals),
                "max": max(all_tok_totals),
                "avg": round(sum(all_tok_totals) / len(all_tok_totals), 2),
            },
        },
        "character_statistics": {
            "total_chars": {
                "min": min(all_char_totals),
                "max": max(all_char_totals),
                "avg": round(sum(all_char_totals) / len(all_char_totals), 2),
            }
        },
        "benchmark_leakage": {
            "overlap_count": len(bench_overlap),
            "overlap_sources": sorted(bench_overlap),
            "clean": len(bench_overlap) == 0,
        },
        "source_ids": source_ids,
    }

    manifest_bytes = f"{json.dumps(manifest, indent=2, sort_keys=True)}\n".encode()
    (out / "manifest.json").write_bytes(manifest_bytes)

    return manifest
