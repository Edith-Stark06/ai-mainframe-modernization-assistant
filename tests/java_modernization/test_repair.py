"""#128 — bounded, grounded self-repair: patch safety, loop protection, provenance."""

from __future__ import annotations

import json
import re

import pytest

from app.ai.providers.base import LLMProvider
from app.ai.providers.errors import LLMProviderUnavailableError
from app.ai.providers.models import LLMRequest, LLMResponse
from app.java_modernization.architecture import build_architecture
from app.java_modernization.compilation import JavaCompiler, javac_available
from app.java_modernization.errors import UnsafePatchError
from app.java_modernization.generation import generate_project
from app.java_modernization.repair import (
    SelfRepairLoop,
    build_repair_context,
    parse_patch,
    validate_patch,
)

pytestmark = pytest.mark.skipif(not javac_available(), reason="javac not on PATH")


def _project(bundle):
    return generate_project(bundle, build_architecture(bundle))


def _break(project, old, new):
    main = f"src/{project.main_class}.java"
    return project.model_copy(
        update={"files": {**project.files, main: project.files[main].replace(old, new)}}
    )


class _SemicolonFixer(LLMProvider):
    """Reads the numbered Java window and re-adds a missing semicolon."""

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        line = None
        for ln in request.prompt.splitlines():
            m = re.match(r"\s*(\d+)\|\s+(checkEligibility\(\))\s*$", ln)
            if m:
                line = int(m.group(1))
        if line is None:
            return LLMResponse(text="{}", model="fixer")
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
                                    "replacement": "        checkEligibility();",
                                }
                            ],
                        }
                    ],
                    "explanation": "restore missing semicolon",
                    "source_basis": ["E1"],
                }
            ),
            model="fixer",
        )


def test_one_error_is_repaired_and_the_loop_ends(elig_bundle, tmp_path):
    broken = _break(_project(elig_bundle), "checkEligibility();", "checkEligibility()")
    prov = _SemicolonFixer()
    res = SelfRepairLoop(prov, JavaCompiler(tmp_path), max_attempts=3).run(
        broken, elig_bundle
    )
    assert res.success
    assert res.stopped_reason == "compiled"
    assert len(res.attempts) == 1
    assert res.initial_error_count == 1 and res.final_error_count == 0
    assert res.attempts[0].patch_applied
    assert res.attempts[0].context_refs  # grounded context was built
    assert res.attempts[0].affected_source_locations  # COBOL mapping retained
    assert res.semantic_equivalence_verified is False
    assert prov.calls == 1  # did not keep hammering the model


def test_stops_exactly_at_max_attempts(elig_bundle, tmp_path):
    broken = _break(_project(elig_bundle), "checkEligibility();", "checkEligibility()")

    class WrongFixer(LLMProvider):
        def __init__(self):
            self.n = 0

        def generate(self, request):  # noqa: ANN001
            self.n += 1
            # a syntactically valid but non-fixing edit on an allowed file:
            # replace the erroring line with a different broken statement each time
            line = None
            for ln in request.prompt.splitlines():
                m = re.match(r"\s*(\d+)\|\s+checkEligibility\(\)\s*$", ln)
                if m:
                    line = int(m.group(1))
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
                                        "replacement": f"        checkEligibility() {'/' * self.n}",
                                    }
                                ],
                            }
                        ],
                        "explanation": f"attempt {self.n}",
                    }
                ),
                model="wrong",
            )

    wf = WrongFixer()
    res = SelfRepairLoop(wf, JavaCompiler(tmp_path), max_attempts=2).run(
        broken, elig_bundle
    )
    assert not res.success
    assert res.stopped_reason in ("max_attempts", "no_progress")
    assert len(res.attempts) <= 2


def test_duplicate_patch_stops_the_loop(elig_bundle, tmp_path):
    broken = _break(_project(elig_bundle), "checkEligibility();", "checkEligibility()")

    class SamePatch(LLMProvider):
        def generate(self, request):  # noqa: ANN001
            line = None
            for ln in request.prompt.splitlines():
                m = re.match(r"\s*(\d+)\|\s+checkEligibility\(\)\s*$", ln)
                if m:
                    line = int(m.group(1))
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
                                        "replacement": "        checkEligibility() // still broken",
                                    }
                                ],
                            }
                        ],
                        "explanation": "same every time",
                    }
                ),
                model="same",
            )

    res = SelfRepairLoop(SamePatch(), JavaCompiler(tmp_path), max_attempts=4).run(
        broken, elig_bundle
    )
    assert not res.success
    assert res.stopped_reason in ("duplicate_patch", "no_progress")
    assert len(res.attempts) <= 2


def test_provider_failure_is_a_structured_repair_failure(elig_bundle, tmp_path):
    broken = _break(_project(elig_bundle), "checkEligibility();", "checkEligibility()")

    class Down(LLMProvider):
        def generate(self, request):  # noqa: ANN001
            raise LLMProviderUnavailableError("outage")

    res = SelfRepairLoop(Down(), JavaCompiler(tmp_path), max_attempts=3).run(
        broken, elig_bundle
    )
    assert not res.success
    assert res.stopped_reason == "provider_failure"
    assert any("provider_failure" in a.note for a in res.attempts)


def test_path_traversal_patch_is_rejected(elig_bundle):
    p = _project(elig_bundle)
    patch = parse_patch(
        json.dumps(
            {
                "files": [
                    {
                        "path": "../evil.java",
                        "changes": [
                            {"start_line": 1, "end_line": 1, "replacement": "x"}
                        ],
                    }
                ]
            }
        )
    )
    with pytest.raises(UnsafePatchError):
        validate_patch(patch, p, allowed_files=set())


def test_patch_to_a_file_without_an_error_is_rejected(elig_bundle):
    p = _project(elig_bundle)
    patch = parse_patch(
        json.dumps(
            {
                "files": [
                    {
                        "path": f"src/{p.main_class}State.java",
                        "changes": [
                            {"start_line": 1, "end_line": 1, "replacement": "//"}
                        ],
                    }
                ]
            }
        )
    )
    with pytest.raises(UnsafePatchError, match="no compiler error"):
        validate_patch(patch, p, allowed_files={f"src/{p.main_class}.java"})


def test_patch_removing_the_class_declaration_is_rejected(elig_bundle):
    p = _project(elig_bundle)
    main = f"src/{p.main_class}.java"
    patch = parse_patch(
        json.dumps(
            {
                "files": [
                    {
                        "path": main,
                        "changes": [
                            {
                                "start_line": 1,
                                "end_line": 1,
                                "replacement": "// removed",
                            }
                        ],
                    }
                ]
            }
        )
    )
    with pytest.raises(UnsafePatchError, match="declaration"):
        validate_patch(patch, p, allowed_files={main})


def test_repair_context_has_provenance_on_every_item(elig_bundle, tmp_path):
    broken = _break(
        _project(elig_bundle),
        "private void checkEligibility() {",
        "private void checkEligibility() {\n        int x = ;",
    )
    comp = JavaCompiler(tmp_path).compile(broken)
    assert not comp.success
    ctx = build_repair_context(comp, broken, elig_bundle)
    ctx.validate()  # raises if any item lacks provenance
    assert ctx.all_items()
    for it in ctx.all_items():
        it.provenance.validate_complete()
        assert it.provenance.source_id == "ELIGIBILITY"
    # targeted: it does not dump the whole project
    assert len(ctx.all_items()) < 15
