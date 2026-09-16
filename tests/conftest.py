"""
Pytest configuration and shared fixtures.

Purpose:
    Provide a configured :class:`fastapi.testclient.TestClient` fixture
    that is shared across all test modules, and set up any application-
    level state required before the test suite runs.

Responsibilities:
    - Create and expose a ``client`` fixture backed by the FastAPI
      application instance.
    - Ensure the test environment is isolated from production settings.

Dependencies:
    - fastapi.testclient — synchronous HTTPX-backed test client
    - app.main           — application factory

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """
    Return a synchronous test client for the application.

    Returns:
        A :class:`fastapi.testclient.TestClient` wrapping the application.
    """
    from app.api.dependencies.ai import get_ai_orchestrator
    from app.ai.providers.fake import FakeLLMProvider
    from app.ai.orchestration.service import AIAnalysisOrchestrator
    from app.ai.explanation.service import CodeExplanationService
    from app.ai.documentation.service import DocumentationGenerationService

    def override_orchestrator():
        exp_provider = FakeLLMProvider(
            response_text="Summary:\nFake summary\n\nExplanation:\nFake explanation"
        )
        doc_provider = FakeLLMProvider(
            response_text="Title:\nFake doc\n\nOverview:\nFake overview\n\nSection:\nFake heading\nFake content"
        )
        return AIAnalysisOrchestrator(
            explanation_service=CodeExplanationService(exp_provider),
            documentation_service=DocumentationGenerationService(doc_provider),
        )

    app.dependency_overrides[get_ai_orchestrator] = override_orchestrator
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_ai_orchestrator, None)
