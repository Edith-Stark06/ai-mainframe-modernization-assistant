"""
Health API schemas.
"""

from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """
    Health response model.
    """

    status: str
    application: str
    version: str
    timestamp: datetime
