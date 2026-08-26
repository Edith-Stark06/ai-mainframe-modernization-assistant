"""
Tests for AI Analysis Orchestrator.
"""

import pytest
from unittest.mock import MagicMock
from typing import Any

from app.ai.documentation.service import DocumentationGenerationService
from app.ai.explanation.models import CodeExplanation
from app.ai.explanation.service import CodeExplanationService
from app.ai.orchestration.models import AIAnalysisResult, AICapability
from app.ai.orchestration.service import AIAnalysisOrchestrator
from app.ai.providers.errors import LLMProviderUnavailableError
from app.ai.providers.fake import FakeLLMProvider
from app.ai.documentation.models import Documentation


def _get_services(
    fail_explanation: bool = False, fail_documentation: bool = False
) -> tuple[CodeExplanationService, DocumentationGenerationService]:
    """Helper to create independent services with fake providers."""
    # Setup explanation provider
    exp_response = "Summary:\nTest sum\n\nExplanation:\nTest exp"
    exp_provider = FakeLLMProvider(
        response_text=exp_response, simulate_failure=fail_explanation
    )
    exp_service = CodeExplanationService(exp_provider)

    # Setup documentation provider
    doc_response = "Title:\nTest doc\n\nOverview:\nTest over\n\nSection:\nS1\nC1"
    doc_provider = FakeLLMProvider(
        response_text=doc_response, simulate_failure=fail_documentation
    )
    doc_service = DocumentationGenerationService(doc_provider)

    return exp_service, doc_service


def test_orchestration_both_capabilities() -> None:
    exp_svc, doc_svc = _get_services()
    orchestrator = AIAnalysisOrchestrator(exp_svc, doc_svc)

    source = "       IDENTIFICATION DIVISION."
    capabilities = {AICapability.EXPLANATION, AICapability.DOCUMENTATION}

    result = orchestrator.analyze(source, capabilities)

    assert result.explanation is not None
    assert result.explanation.summary == "Test sum"

    assert result.documentation is not None
    assert result.documentation.title == "Test doc"


def test_orchestration_explanation_only() -> None:
    exp_svc, doc_svc = _get_services(fail_documentation=True)
    orchestrator = AIAnalysisOrchestrator(exp_svc, doc_svc)

    source = "       IDENTIFICATION DIVISION."
    capabilities = {AICapability.EXPLANATION}

    # Should succeed because documentation is not requested, despite doc provider being set to fail
    result = orchestrator.analyze(source, capabilities)

    assert result.explanation is not None
    assert result.documentation is None


def test_orchestration_documentation_only() -> None:
    exp_svc, doc_svc = _get_services(fail_explanation=True)
    orchestrator = AIAnalysisOrchestrator(exp_svc, doc_svc)

    source = "       IDENTIFICATION DIVISION."
    capabilities = {AICapability.DOCUMENTATION}

    # Should succeed because explanation is not requested
    result = orchestrator.analyze(source, capabilities)

    assert result.explanation is None
    assert result.documentation is not None


def test_orchestration_phase1_context_propagation() -> None:
    exp_svc, doc_svc = _get_services()
    orchestrator = AIAnalysisOrchestrator(exp_svc, doc_svc)

    source = "       IDENTIFICATION DIVISION."
    capabilities = {AICapability.EXPLANATION, AICapability.DOCUMENTATION}
    context = {
        "correlation_id": "c-123",
        "dependencies": ["A", "B"],
        "diagnostics": ["Diag1"],
    }

    result = orchestrator.analyze(source, capabilities, context)

    # Context should be preserved
    assert result.context["correlation_id"] == "c-123"
    assert result.context["dependencies"] == ["A", "B"]


def test_orchestration_provider_failure() -> None:
    # Both fail
    exp_svc, doc_svc = _get_services(fail_explanation=True, fail_documentation=True)
    orchestrator = AIAnalysisOrchestrator(exp_svc, doc_svc)

    source = "       IDENTIFICATION DIVISION."
    capabilities = {AICapability.EXPLANATION, AICapability.DOCUMENTATION}

    with pytest.raises(LLMProviderUnavailableError):
        orchestrator.analyze(source, capabilities)


def test_orchestration_partial_failure_explanation() -> None:
    # Explanation fails, documentation would succeed
    exp_svc, doc_svc = _get_services(fail_explanation=True)
    orchestrator = AIAnalysisOrchestrator(exp_svc, doc_svc)

    source = "       IDENTIFICATION DIVISION."
    capabilities = {AICapability.EXPLANATION, AICapability.DOCUMENTATION}

    with pytest.raises(LLMProviderUnavailableError):
        orchestrator.analyze(source, capabilities)


def test_orchestration_partial_failure_documentation() -> None:
    # Documentation fails, explanation would succeed
    exp_svc, doc_svc = _get_services(fail_documentation=True)
    orchestrator = AIAnalysisOrchestrator(exp_svc, doc_svc)

    source = "       IDENTIFICATION DIVISION."
    capabilities = {AICapability.EXPLANATION, AICapability.DOCUMENTATION}

    with pytest.raises(LLMProviderUnavailableError):
        orchestrator.analyze(source, capabilities)


def test_orchestration_empty_source() -> None:
    exp_svc, doc_svc = _get_services()
    orchestrator = AIAnalysisOrchestrator(exp_svc, doc_svc)

    with pytest.raises(ValueError, match="cannot be empty"):
        orchestrator.analyze("   ", {AICapability.EXPLANATION})


def test_orchestration_invalid_capabilities() -> None:
    exp_svc, doc_svc = _get_services()
    orchestrator = AIAnalysisOrchestrator(exp_svc, doc_svc)

    with pytest.raises(ValueError, match="At least one capability must be requested"):
        orchestrator.analyze("       IDENTIFICATION DIVISION.", set())


def test_orchestration_determinism() -> None:
    exp_svc, doc_svc = _get_services()
    orchestrator = AIAnalysisOrchestrator(exp_svc, doc_svc)

    source = "       IDENTIFICATION DIVISION."
    capabilities = {AICapability.EXPLANATION, AICapability.DOCUMENTATION}
    context = {"id": "1"}

    result1 = orchestrator.analyze(source, capabilities, context)
    result2 = orchestrator.analyze(source, capabilities, context)

    assert result1.explanation == result2.explanation
    assert result1.documentation == result2.documentation
    assert result1.context == result2.context


def test_orchestration_context_immutability() -> None:
    exp_svc, doc_svc = _get_services()
    orchestrator = AIAnalysisOrchestrator(exp_svc, doc_svc)

    source = "       IDENTIFICATION DIVISION."
    capabilities = {AICapability.EXPLANATION}
    context: dict[str, Any] = {"nested": {"key": "value"}}

    result = orchestrator.analyze(source, capabilities, context)

    # 1. caller_context != result.context by identity
    assert result.context is not context
    # 2. Mutating the caller after orchestration does not alter the result
    context["nested"]["key"] = "mutated"
    assert result.context["nested"]["key"] == "value"

    # Also prove result context itself is an immutable mapping proxy
    with pytest.raises(TypeError):
        result.context["new"] = "k"  # type: ignore


def test_orchestration_result_immutability() -> None:
    result = AIAnalysisResult(
        explanation=CodeExplanation("S", "E"),
        documentation=None,
        context={"k": "v"},
    )
    with pytest.raises(Exception):
        result.context = {"new": "k"}  # type: ignore


def test_orchestration_execution_order() -> None:
    """Equivalent capability sets must always execute in EXPLANATION -> DOCUMENTATION order."""
    exp_svc, doc_svc = _get_services()

    # We will wrap the underlying methods with mocks to track call order
    exp_svc.explain_code = MagicMock(return_value=CodeExplanation("S", "E"))  # type: ignore
    doc_svc.generate_documentation = MagicMock(return_value=Documentation("T", "O"))  # type: ignore

    orchestrator = AIAnalysisOrchestrator(exp_svc, doc_svc)
    source = "       IDENTIFICATION DIVISION."

    # Python sets do not guarantee order.
    # Whether we build {A, B} or {B, A}, it is the same set.
    # The orchestrator MUST enforce a stable execution order internally.
    capabilities = {AICapability.DOCUMENTATION, AICapability.EXPLANATION}

    # Verify execution order: explanation, then documentation
    # We can attach a common parent mock to track order
    parent = MagicMock()
    parent.attach_mock(exp_svc.explain_code, "explain")
    parent.attach_mock(doc_svc.generate_documentation, "document")

    # Run to capture in parent
    orchestrator.analyze(source, capabilities)

    calls = parent.mock_calls
    # Should see explain followed by document
    assert len(calls) == 2
    assert calls[0][0] == "explain"
    assert calls[1][0] == "document"
