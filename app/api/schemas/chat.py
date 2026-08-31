from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uuid


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    workspace_id: uuid.UUID
    top_k: int = Field(default=5, ge=1, le=100)
    filename: Optional[str] = Field(default=None)
    include_modernization_context: bool = False
    ai_capabilities: List[str] = Field(default_factory=lambda: ["EXPLANATION"])


class ChatResponse(BaseModel):
    query: str
    answer: str
    context: List[Dict[str, Any]]
    error: Optional[str] = None
    modernization_data: Optional[Dict[str, Any]] = None
