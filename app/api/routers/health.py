"""
Health API.

Author:
Edith Stark

Project:
AI-Powered Mainframe Modernization Assistant
"""

from datetime import datetime, UTC

from fastapi import APIRouter

from app.api.schemas.health import HealthResponse
from app.core.config import settings
from app.core.logging import logger

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get(
    "",
    response_model=HealthResponse,
    summary="Application Health Check",
)
async def health_check() -> HealthResponse:
    """
    Returns application health information.
    """

    logger.info("Health endpoint called.")

    return HealthResponse(
        status="healthy",
        application=settings.app_name,
        version=settings.app_version,
        timestamp=datetime.now(UTC),
    )
