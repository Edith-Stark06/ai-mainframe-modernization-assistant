"""
Health API Router.

Purpose:
    Expose a health-check endpoint that allows load balancers, monitoring
    systems, and CI pipelines to verify that the service is alive and
    correctly configured.

Responsibilities:
    - Handle ``GET /api/v1/health`` requests.
    - Return application name, version, status, and current UTC timestamp.
    - Log every health-check invocation at DEBUG level.

Dependencies:
    - app.api.schemas.health — :class:`HealthResponse` response model
    - app.core.config        — application settings
    - app.core.logging       — Loguru logger

Examples:
    Example response::

        {
            "status": "healthy",
            "application": "AI Mainframe Modernization Assistant",
            "version": "0.1.0",
            "timestamp": "2026-07-10T12:00:00.000000Z"
        }

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.schemas.health import HealthResponse
from app.core.config import settings
from app.core.logging import logger

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=HealthResponse,
    summary="Application health check",
    description=(
        "Returns the application status, version, and the current UTC "
        "timestamp. Intended for use by load balancers and monitoring systems."
    ),
)
async def health_check() -> HealthResponse:
    """
    Return application health information.

    Performs a lightweight liveness check confirming that the API process
    is running and its configuration has been loaded successfully.

    Returns:
        :class:`~app.api.schemas.health.HealthResponse` containing the
        current health status, application name, version, and UTC timestamp.
    """
    logger.debug("Health check requested.")

    return HealthResponse(
        status="healthy",
        application=settings.app_name,
        version=settings.app_version,
        timestamp=datetime.now(UTC),
    )
