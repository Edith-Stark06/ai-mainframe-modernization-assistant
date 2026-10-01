"""
Chat answers questions about the Validation Center's results.

Purpose:
    "analyze the validation of the java code compilation" is about the
    compile/test/validation stages, which are not part of the searchable code
    chunks -- the model had nothing to answer from and deflected. The chat now
    attaches the validation results as numbered evidence when the question is
    about them (and only then), and carries on without them if they cannot be
    computed.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.ai.explanation.models import CodeExplanation
from app.ai.orchestration.models import AIAnalysisResult
from app.api.routers import chat as chat_router
from app.api.routers.chat import get_rag_orchestrator
from app.api.schemas.validation import StageResult, StageStatus
from app.api.services import validation_context as vc
from app.api.services.validation_context import (
    VALIDATION_CHUNK_TYPE,
    _detail_text,
    build_validation_chunk,
)
from app.main import app
from app.rag.intent import wants_validation_context
from app.rag.orchestration.models import RAGRequest, RAGResult, RetrievedContext
from app.rag.retrieval.models import RetrievalResult

# ------------------------------------------------------------ the question test


@pytest.mark.parametrize(
    "question",
    [
        "analyze the validation of the java code compilation",
        "did the java compile?",
        "does it compile",
        "Did the tests pass?",
        "what is the test coverage",
        "is the java behaviorally equivalent to the cobol",
        "is it ready for production?",
        "any compiler errors?",
        "show me the validation results",
        "what failed in the build",
        "was the self-repair run",
        "is the conversion verified",
        "did it pass?",
    ],
)
def test_validation_questions_are_recognised(question: str) -> None:
    assert wants_validation_context(question)


@pytest.mark.parametrize(
    "question",
    [
        "What is the tax rate?",
        "At what order total does the status become HIGH VALUE?",
        "what discount does type R get?",
        "Explain what this program does",
        "list the business rules",
        "walk me through an order",
        "hi",
    ],
)
def test_ordinary_questions_are_not(question: str) -> None:
    assert not wants_validation_context(question)


# --------------------------------------------------------------- the chunk text


def _stage(name: str, status: StageStatus, summary: str, **details) -> StageResult:
    return StageResult(stage=name, status=status, summary=summary, details=details)


@pytest.fixture
def stages(monkeypatch: pytest.MonkeyPatch) -> list[StageResult]:
    chosen = [
        _stage(
            "Compilation",
            StageStatus.FAIL,
            "2 compiler error(s).",
            errors=["cannot find symbol wsX", "missing return"],
        ),
        _stage("Tests", StageStatus.PASS, "All 5 test(s) passed."),
        _stage(
            "Coverage",
            StageStatus.INCONCLUSIVE,
            "Overall coverage 92% (PARTIAL).",
            overall=0.92,
            notes="",
        ),
    ]
    monkeypatch.setattr(vc, "compute_validation_stages", lambda b, m: chosen)
    return chosen


class _Mb:
    compilation = None


def test_the_chunk_lists_every_stage_with_its_status_and_summary(stages) -> None:
    chunk = build_validation_chunk(object(), _Mb(), "sales.cbl")  # type: ignore[arg-type]
    text = chunk.content
    assert "Validation Center results for sales.cbl" in text
    assert "overall status: FAIL" in text  # a failed core stage fails the rollup
    assert "- Compilation: FAIL - 2 compiler error(s)." in text
    assert "- Tests: PASS - All 5 test(s) passed." in text
    assert "- Coverage: INCONCLUSIVE - Overall coverage 92% (PARTIAL)." in text


def test_stage_details_are_included_and_empty_ones_are_not(stages) -> None:
    text = build_validation_chunk(object(), _Mb(), "sales.cbl").content  # type: ignore[arg-type]
    assert "errors: cannot find symbol wsX, missing return" in text
    assert "overall: 0.92" in text
    assert "notes" not in text


def test_the_chunk_is_marked_and_has_a_stable_content_derived_id(stages) -> None:
    a = build_validation_chunk(object(), _Mb(), "sales.cbl")  # type: ignore[arg-type]
    b = build_validation_chunk(object(), _Mb(), "sales.cbl")  # type: ignore[arg-type]
    assert a.chunk_id == b.chunk_id
    assert a.chunk_id.startswith(f"{VALIDATION_CHUNK_TYPE}-")
    assert a.metadata["chunk_type"] == VALIDATION_CHUNK_TYPE
    assert a.document_id == "sales.cbl"


def test_a_changed_result_changes_the_id(stages, monkeypatch) -> None:
    before = build_validation_chunk(object(), _Mb(), "sales.cbl").chunk_id  # type: ignore[arg-type]
    monkeypatch.setattr(
        vc,
        "compute_validation_stages",
        lambda b, m: [
            _stage("Compilation", StageStatus.PASS, "Compilation succeeded.")
        ],
    )
    assert build_validation_chunk(object(), _Mb(), "sales.cbl").chunk_id != before  # type: ignore[arg-type]


def test_compilation_details_are_added_when_it_ran(stages) -> None:
    class Diagnostic:
        message = "cannot find symbol wsX"

    class Compilation:
        success = False
        jdk_version = "javac 25.0.3"
        errors = (Diagnostic(),)
        warnings = ()
        file_records = ("A.java", "B.java")
        duration_s = 1.26
        timed_out = False

    mb = _Mb()
    mb.compilation = Compilation()  # type: ignore[assignment]
    text = build_validation_chunk(object(), mb, "sales.cbl").content  # type: ignore[arg-type]
    assert (
        "Java compilation details: failed with JDK javac 25.0.3; 1 error(s), "
        "0 warning(s); 2 file(s) compiled in 1.3s." in text
    )
    assert "Compiler error: cannot find symbol wsX" in text


def test_detail_text_skips_structures_and_truncates_long_lists() -> None:
    text = _detail_text(
        {
            "files": [f"F{i}.java" for i in range(13)],
            "factors": [{"name": "coverage"}],
            "nested": {"a": 1},
            "empty": [],
            "none": None,
            "count": 3,
        }
    )
    assert "F9.java (+3 more)" in text
    assert "F10.java" not in text
    assert "count: 3" in text
    assert "factors" not in text and "nested" not in text and "empty" not in text


# ------------------------------------------------------------- router behaviour


class SpyOrchestrator:
    def __init__(self) -> None:
        self.requests: list[RAGRequest] = []

    def orchestrate(self, request: RAGRequest) -> RAGResult:
        self.requests.append(request)
        return RAGResult(
            request=request,
            context=RetrievedContext(results=request.extra_chunks),
            ai_result=AIAnalysisResult(
                explanation=CodeExplanation(
                    summary="The answer.", explanation="Detail."
                ),
                documentation=None,
                context={},
            ),
        )


CHUNK = RetrievalResult(
    chunk_id="validation-0123456789abcdef",
    document_id="sales.cbl",
    content="Validation Center results for sales.cbl (overall status: PASS).",
    chunk_index=0,
    metadata={"chunk_type": "validation"},
    score=0.0,
)


@pytest.fixture
def spy():
    orchestrator = SpyOrchestrator()
    app.dependency_overrides[get_rag_orchestrator] = lambda: orchestrator
    yield orchestrator
    app.dependency_overrides.pop(get_rag_orchestrator, None)


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch):
    """Replace the heavy pipeline + chunk builder; record how they are used."""
    calls: list[tuple] = []

    def fake_run(workspace_id, filename, workspace_manager, cache):
        calls.append((workspace_id, filename))
        return object(), object()

    monkeypatch.setattr(chat_router, "run_pipeline_for_source", fake_run)
    monkeypatch.setattr(chat_router, "build_validation_chunk", lambda b, m, f: CHUNK)
    return calls


def _post(query: str, **extra):
    body = {"query": query, "workspace_id": str(uuid.uuid4()), **extra}
    return TestClient(app).post("/api/v1/chat/", json=body)


def test_a_validation_question_gets_the_validation_results_as_evidence(
    spy: SpyOrchestrator, pipeline: list
) -> None:
    data = _post(
        "analyze the validation of the java code compilation", filename="sales.cbl"
    ).json()
    assert spy.requests[0].extra_chunks == (CHUNK,)
    assert pipeline and pipeline[0][1] == "sales.cbl"
    # ... and it shows up numbered in the evidence list the UI displays
    assert [c["id"] for c in data["context"]] == [CHUNK.chunk_id]
    assert data["context"][0]["ref"] == 1


def test_an_ordinary_question_does_not_run_the_pipeline(
    spy: SpyOrchestrator, pipeline: list
) -> None:
    _post("What is the tax rate?", filename="sales.cbl")
    assert spy.requests[0].extra_chunks == ()
    assert pipeline == []


def test_without_a_file_there_is_nothing_to_validate(
    spy: SpyOrchestrator, pipeline: list
) -> None:
    _post("did the java compile?")
    assert spy.requests[0].extra_chunks == ()
    assert pipeline == []


@pytest.mark.parametrize(
    "error", [RuntimeError("javac exploded"), HTTPException(status_code=404)]
)
def test_if_the_results_cannot_be_computed_the_chat_still_answers(
    spy: SpyOrchestrator, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def failing(*args, **kwargs):
        raise error

    monkeypatch.setattr(chat_router, "run_pipeline_for_source", failing)
    resp = _post("did the java compile?", filename="sales.cbl")
    assert resp.status_code == 200
    assert spy.requests[0].extra_chunks == ()


def test_a_greeting_never_triggers_the_pipeline(
    spy: SpyOrchestrator, pipeline: list
) -> None:
    _post("hi", filename="sales.cbl")
    assert pipeline == []
    assert spy.requests == []


def test_the_real_chunk_is_built_from_the_real_pipeline_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spy: SpyOrchestrator
) -> None:
    """No fakes for the chunk: run the real pipeline on a tiny program."""
    from app.dataset.analysis_bundle import build_analysis_bundle
    from app.dataset.modernization_bundle import build_modernization_bundle

    source = Path("tests/fixtures/hello_world.cbl").read_text(encoding="utf-8")
    bundle = build_analysis_bundle("HELLO", source, tmp_path / "a")
    mb = build_modernization_bundle(bundle, workspace_root=tmp_path / "m")
    monkeypatch.setattr(
        chat_router, "run_pipeline_for_source", lambda *a, **k: (bundle, mb)
    )

    _post("did the java compile?", filename="hello_world.cbl")
    text = spy.requests[0].extra_chunks[0].content
    for stage in ("Parser", "Java Generation", "Compilation", "Tests", "Self Repair"):
        assert f"- {stage}:" in text
    assert "overall status:" in text
