"""
Base API response schemas.

Author:
Edith Stark

Project:
AI-Powered Mainframe Modernization Assistant
"""

from datetime import datetime, UTC

from pydantic import BaseModel, Field


class APIResponse(BaseModel):
    """
    Base response model for API responses.
    """

    success: bool = True
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
