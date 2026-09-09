"""
Phase 9 end-to-end (deterministic, fake provider):

    COBOL -> Phase 1-5 -> #125 architecture -> #126 Java -> #127 compile
      -> intentional compiler error -> #128 fake AI repair -> #127 compile -> SUCCESS

Proves: architecture has evidence · Java has source mappings · compiler
errors are structured · repair receives grounded context · repair is
targeted · every attempt is recorded · a successful compile ends the loop
· no semantic-equivalence claim anywhere.
"""

from __future__ import annotations

import json
import re

import pytest

from app.ai.providers.base import LLMProvider
from app.ai.providers.models import LLMRequest, LLMResponse
from app.java_modernization import run_java_modernization
from app.java_modernization.compilation import javac_available

pytestmark = pytest.mark.skipif(not javac_available(), reason="javac not on PATH")


class _WindowFixer(LLMProvider):
    """Re-adds the semicolon it sees is missing in the numbered Java window."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        target = None
        for ln in request.prompt.splitlines():
            m = re.match(r"\s*(\d+)\|\s+(\w+\(\))\s*$", ln)
            if m and not ln.rstrip().endswith(";"):
                target = (int(m.group(1)), m.group(2))
        if target is None:
            return LLMResponse(text="{}", model="fixer")
        line, call = target
        return LLMResponse(
            text=json.dumps(
                {
                    "files": [
                        {
                            "path": "src/Eligibility.java",
                            "changes": [
                                {
                                    "start_line": line,
                                    "end_line": line,
                                    "replacement": f"        {call};",
                                }
                            ],
                        }
                    ],
                    "explanation": "restore missing statement terminator",
                    "source_basis": ["E1", "E2"],
                }
            ),
            model="fixer",
        )


def test_full_pipeline_with_repair(elig_bundle, tmp_path, monkeypatch):
    # 1. force generation to emit a broken main class (intentional error)
    from app.java_modernization import generation as gen_mod

    real_generate = gen_mod.generate_project

    def broken_generate(bundle, architecture):  # noqa: ANN001
        proj = real_generate(bundle, architecture)
        main = f"src/{proj.main_class}.java"
        return proj.model_copy(
            update={
                "files": {
                    **proj.files,
                    main: proj.files[main].replace(
                        "checkEligibility();", "checkEligibility()"
                    ),
                }
            }
        )

    monkeypatch.setattr(
        "app.java_modernization.orchestrator.generate_project", broken_generate
    )

    result = run_java_modernization(
        elig_bundle,
        workspace_root=tmp_path,
        provider=_WindowFixer(),
        max_repair_attempts=3,
    )

    # architecture has evidence
    assert result.architecture.components
    assert all(c.evidence for c in result.architecture.components)

    # Java has source mappings
    mapped = [a for a in result.project.artifacts if a.mapping_status == "mapped"]
    assert mapped and any(a.business_rule_ids for a in mapped)

    # compiler errors were structured, then repaired
    assert not result.initial_compilation.success
    assert result.initial_compilation.errors
    assert result.initial_compilation.errors[0].file
    assert result.repair is not None
    assert result.repair.attempts
    assert result.repair.attempts[0].context_refs  # grounded context
    assert result.repair.attempts[0].affected_source_locations  # COBOL mapping

    # a successful compile ended the loop
    assert result.repair.stopped_reason == "compiled"
    assert result.final_compilation.success
    assert result.compiles

    # no semantic-equivalence claim anywhere
    assert result.semantic_equivalence_verified is False
    assert result.architecture.semantic_equivalence_verified is False
    assert result.project.semantic_equivalence_verified is False
    assert result.repair.semantic_equivalence_verified is False
    d = result.to_dict()
    json.dumps(d)
    assert "not" in d["disclaimer"].lower() and "phase 10" in d["disclaimer"].lower()


def test_full_pipeline_no_repair_needed(if_else_bundle, tmp_path):
    result = run_java_modernization(if_else_bundle, workspace_root=tmp_path)
    assert result.initial_compilation.success
    assert result.repair is None
    assert result.compiles
    assert result.semantic_equivalence_verified is False


def test_traceability_chain_end_to_end(elig_bundle, tmp_path):
    result = run_java_modernization(elig_bundle, workspace_root=tmp_path)
    # COBOL paragraph -> business rule -> architecture component -> java method
    comp = next(
        c for c in result.architecture.components if "BR-001" in c.business_rule_ids
    )
    assert comp.source_refs[0].paragraph == "CHECK-ELIGIBILITY"
    art = next(
        a
        for a in result.project.artifacts
        if a.architecture_component_id == comp.component_id and a.kind == "method"
    )
    assert art.method_name == "checkEligibility"
    assert "BR-001" in art.business_rule_ids
    assert art.source_locations[0].source_id == "ELIGIBILITY"
