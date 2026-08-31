from dataclasses import dataclass, field
from typing import Dict, Any
from app.rag.models import _freeze_metadata, _to_json_compatible


@dataclass(frozen=True)
class ModernizationScore:
    """
    Immutable representation of modernization scoring metrics for a specific program/flow.
    Scores are normalized between 0.0 and 1.0.
    """

    complexity_score: float
    coupling_score: float
    overall_readiness: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "complexity_score", max(0.0, min(1.0, float(self.complexity_score)))
        )
        object.__setattr__(
            self, "coupling_score", max(0.0, min(1.0, float(self.coupling_score)))
        )
        object.__setattr__(
            self, "overall_readiness", max(0.0, min(1.0, float(self.overall_readiness)))
        )

        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def to_dict(self) -> Dict[str, Any]:
        import dataclasses

        d = dataclasses.asdict(self)
        return _to_json_compatible(d)
