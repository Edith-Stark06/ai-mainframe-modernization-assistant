from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class ChatRequest(BaseModel):
    query: str
    workspace_id: str
    top_k: int = 5
    include_modernization_context: bool = False
    ai_capabilities: List[str] = Field(default_factory=lambda: ["EXPLANATION"])


class ChatResponse(BaseModel):
    query: str
    answer: str
    context: List[Dict[str, Any]]
    error: Optional[str] = None
    modernization_data: Optional[Dict[str, Any]] = None
