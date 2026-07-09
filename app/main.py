"""
Application entry point.

Author:
Edith Stark

Project:
AI-Powered Mainframe Modernization Assistant
"""

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import logger

logger.info("Starting application...")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Enterprise AI platform for understanding and "
        "modernizing IBM Z mainframe applications."
    ),
)

app.include_router(api_router)


@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    """
    Root endpoint.
    """

    logger.info("Root endpoint accessed.")

    return {
        "message": "Welcome to AI-Powered Mainframe Modernization Assistant",
        "docs": "/docs",
    }
