"""
Application Entry Point.

Purpose:
    Bootstrap and configure the FastAPI application for the
    AI-Powered Mainframe Modernization Assistant.

Responsibilities:
    - Instantiate the FastAPI application with metadata.
    - Register global middleware (CORS, request logging).
    - Register the versioned API router.
    - Expose the root (/) and /docs endpoints.
    - Handle application lifespan (startup / shutdown hooks).

Dependencies:
    - app.api.router         — versioned API router
    - app.core.config        — application settings
    - app.core.logging       — Loguru logger
    - app.core.handlers      — global exception handlers
    - app.core.middleware     — request ID middleware

Examples:
    Start the development server::

        uvicorn app.main:app --reload

    Run via the project script::

        python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.handlers import register_exception_handlers
from app.core.logging import logger
from app.core.middleware import RequestIDMiddleware

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """
    Manage application startup and shutdown lifecycle.

    Logs a startup banner and a clean shutdown message so that
    operators can confirm the service is running correctly in
    both development and production environments.

    Args:
        application: The FastAPI application instance.

    Yields:
        Control to the running application.
    """
    logger.info(
        "Starting {} v{}",
        settings.app_name,
        settings.app_version,
    )
    logger.info("API docs available at /docs")
    yield
    logger.info("Shutting down {}.", settings.app_name)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_application() -> FastAPI:
    """
    Construct and configure the FastAPI application.

    Returns:
        A fully-configured :class:`fastapi.FastAPI` instance.
    """
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Enterprise AI platform for understanding and modernizing "
            "IBM Z mainframe applications. Combines deterministic static "
            "analysis with Large Language Models."
        ),
        contact={
            "name": "Edith Stark",
        },
        license_info={
            "name": "MIT",
        },
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # Exception handlers
    # ------------------------------------------------------------------

    register_exception_handlers(application)

    # ------------------------------------------------------------------
    # Middleware
    # ------------------------------------------------------------------

    # Note: Starlette processes middleware in reverse-registration order.
    # RequestIDMiddleware must be the innermost middleware so the request
    # ID is available to exception handlers during error processing.
    application.add_middleware(RequestIDMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------

    application.include_router(api_router)

    # ------------------------------------------------------------------
    # Root endpoint
    # ------------------------------------------------------------------

    @application.get(
        "/",
        tags=["Root"],
        summary="Service root",
        response_class=JSONResponse,
    )
    async def root() -> dict[str, str]:
        """
        Return structured service information and links to key endpoints.

        Returns:
            A mapping containing the application name, version, running
            status, and URLs for the documentation and health endpoints.
        """
        logger.debug("Root endpoint accessed.")
        return {
            "application": settings.app_name,
            "version": settings.app_version,
            "status": "running",
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    return application


# ---------------------------------------------------------------------------
# Application instance (used by uvicorn / pytest)
# ---------------------------------------------------------------------------

app: FastAPI = create_application()
