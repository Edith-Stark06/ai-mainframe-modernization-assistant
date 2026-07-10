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


@pytest.fixture(scope="module")
def client() -> TestClient:
    """
    Return a module-scoped synchronous test client for the application.

    Using ``scope="module"`` amortises application startup cost across
    all tests within a single module while still ensuring isolation
    between test modules.

    Returns:
        A :class:`fastapi.testclient.TestClient` wrapping the application.
    """
    with TestClient(app) as test_client:
        yield test_client
