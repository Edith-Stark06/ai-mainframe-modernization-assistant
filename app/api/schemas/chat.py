from enum import Enum

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


class ChatErrorCode(str, Enum):
    """
    Machine-readable classification of why a chat request produced no
    answer. Exactly one of these -- never a generic catch-all string --
    is set on ``ChatResponse.error_code`` whenever ``error`` is set.

    SOURCE_NOT_FOUND / WORKSPACE_NOT_FOUND / INVALID_REQUEST correspond
    to the existing 404/404/400 HTTPException paths in
    ``app.api.routers.chat`` (unchanged) -- those terminate the request
    before a ChatResponse body is built at all, so they are expressed
    via HTTP status + a safe message rather than this field. The
    remaining six values are the ones that actually appear in
    ``error_code``.

    GROUNDED_CONTEXT_UNAVAILABLE is defined for completeness with the
    reviewed error taxonomy but is currently unreachable: distinguishing
    "retrieval infrastructure failed" from any other unexpected
    orchestration-level exception would require changing
    ``RAGOrchestrator.orchestrate()``'s retrieval-failure behavior, which
    an existing test
    (``tests/rag/test_orchestration.py::test_orchestrator_retrieval_failure_propagates``)
    explicitly locks in as "propagates uncaught" -- out of scope per
    "do not modify RAG semantics". Such a failure is reported as
    INTERNAL_ERROR instead, exactly as it always has been.
    """

    LLM_PROVIDER_NOT_CONFIGURED = "LLM_PROVIDER_NOT_CONFIGURED"
    LLM_PROVIDER_UNAVAILABLE = "LLM_PROVIDER_UNAVAILABLE"
    LLM_GENERATION_FAILED = "LLM_GENERATION_FAILED"
    GROUNDED_CONTEXT_UNAVAILABLE = "GROUNDED_CONTEXT_UNAVAILABLE"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    INVALID_REQUEST = "INVALID_REQUEST"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ChatResponse(BaseModel):
    query: str
    answer: str
    context: List[Dict[str, Any]]
    error: Optional[str] = None
    error_code: Optional[ChatErrorCode] = None
    modernization_data: Optional[Dict[str, Any]] = None
