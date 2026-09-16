"""
Business Rules API Schemas.

Purpose:
    Define Pydantic v2 response models for business rule data
    exposed by the analysis API endpoint.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.dependencies import PositionResponse

__all__ = ["BusinessRuleResponse"]


class BusinessRuleResponse(BaseModel):
    """
    Typed representation of a serialized BusinessRule.

    Attributes:
        condition:
            The normalized text representation of the business rule condition.
        actions:
            A list of normalized text representations of the business rule actions.
        source_location:
            The location within the source file where this rule is defined, if known.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    condition: str = Field(
        ...,
        description="The normalized text representation of the business rule condition.",
    )
    actions: list[str] = Field(
        ...,
        description="A list of normalized text representations of the business rule actions.",
    )
    source_location: PositionResponse | None = Field(
        None,
        description="The location within the source file where this rule is defined, if known.",
    )
