from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class ModernizationRequest(BaseModel):
    filename: str = Field(..., description="The source filename to analyze and modernize")

class FlowNodeResponse(BaseModel):
    id: str
    node_type: str
    name: str
    metadata: Dict[str, Any]

class FlowEdgeResponse(BaseModel):
    id: str
    source_id: str
    target_id: str
    edge_type: str
    metadata: Dict[str, Any]

class FlowResponse(BaseModel):
    id: str
    name: str
    nodes: List[FlowNodeResponse]
    edges: List[FlowEdgeResponse]
    metadata: Dict[str, Any]

class ModernizationScoreResponse(BaseModel):
    complexity_score: float
    coupling_score: float
    overall_readiness: float
    metadata: Dict[str, Any]

class RecommendationResponse(BaseModel):
    id: str
    title: str
    description: str
    priority: str

class ModernizationPipelineResponse(BaseModel):
    flow: Optional[FlowResponse] = None
    score: Optional[ModernizationScoreResponse] = None
    recommendations: Optional[List[RecommendationResponse]] = None
