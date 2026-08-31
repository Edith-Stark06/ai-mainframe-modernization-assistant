from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any
from app.rag.models import _to_json_compatible


class Priority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class Recommendation:
    """
    Immutable representation of a modernization recommendation.
    """

    id: str
    title: str
    description: str
    priority: Priority

    def to_dict(self) -> Dict[str, Any]:
        import dataclasses

        d = dataclasses.asdict(self)
        return _to_json_compatible(d)
