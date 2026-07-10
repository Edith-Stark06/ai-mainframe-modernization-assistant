"""
API Router.

Purpose:
    Aggregate all versioned API sub-routers into a single router that
    is registered on the FastAPI application.

Responsibilities:
    - Define the ``/api/v1`` URL prefix for all API endpoints.
    - Include every domain-specific sub-router.
    - Serve as the single integration point between the application and
      its route handlers.

Dependencies:
    - app.api.routers.health — health-check endpoints

Examples:
    The router is imported and mounted in ``app.main``::

        from app.api.router import api_router
        app.include_router(api_router)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from fastapi import APIRouter

from app.api.routers.health import router as health_router

# ---------------------------------------------------------------------------
# Versioned API router
# ---------------------------------------------------------------------------

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health_router)
