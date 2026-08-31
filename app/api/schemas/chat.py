from pydantic import BaseModel, Field, StringConstraints
from typing import List, Dict, Any, Optional
from typing_extensions import Annotated
import uuid


class ChatRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    workspace_id: uuid.UUID
    top_k: int = Field(default=5, ge=1, le=100)
    filename: Optional[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    ] = None
    include_modernization_context: bool = False
    ai_capabilities: List[str] = Field(default_factory=lambda: ["EXPLANATION"])


class ChatResponse(BaseModel):
    query: str
    answer: str
    context: List[Dict[str, Any]]
    error: Optional[str] = None
    modernization_data: Optional[Dict[str, Any]] = None
