from pydantic import BaseModel, Field, StringConstraints
from typing import List, Dict, Any
from typing_extensions import Annotated


class ModernizationRequest(BaseModel):
    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = (
        Field(..., description="The source filename to analyze and modernize")
    )


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
    flow: FlowResponse
    score: ModernizationScoreResponse
    recommendations: List[RecommendationResponse]


# ---------------------------------------------------------------------------
# Phase 4 — Modernization Intelligence (#112 / #113 / #114)
# ---------------------------------------------------------------------------


class BusinessRuleActionResponse(BaseModel):
    kind: str
    target: str
    sources: List[str]
    literals: List[str]
    raw: str
    source_location: Dict[str, Any] | None = None


class BusinessRuleVariablesResponse(BaseModel):
    reads: List[str]
    writes: List[str]
    conditions: List[str]


class Phase4BusinessRuleResponse(BaseModel):
    rule_id: str
    category: str
    description: str
    condition: str
    actions: List[BusinessRuleActionResponse]
    variables: BusinessRuleVariablesResponse
    dependencies: List[str]
    source_locations: List[Dict[str, Any]]
    paragraph: str
    section: str | None = None
    confidence: float
    evidence: List[str]


class ModernizationRiskResponse(BaseModel):
    risk_id: str
    category: str
    severity: str
    title: str
    explanation: str
    evidence: List[str]
    source_locations: List[Dict[str, Any]]
    affected_components: List[str]
    confidence: float
    recommended_mitigation: str
    occurrence_count: int


class StrategyRecommendationResponse(BaseModel):
    recommendation_id: str
    strategy: str
    is_primary: bool
    rationale: str
    evidence: List[str]
    referenced_risk_ids: List[str]
    prerequisites: List[str]
    confidence: float


class ModernizationIntelligenceResponse(BaseModel):
    business_rules: List[Phase4BusinessRuleResponse]
    risks: List[ModernizationRiskResponse]
    strategies: List[StrategyRecommendationResponse]
