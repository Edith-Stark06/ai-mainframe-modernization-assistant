from dataclasses import dataclass
from typing import Any
import math


@dataclass(frozen=True)
class Embedding:
    """
    An immutable representation of a vector embedding for a chunk.
    """

    chunk_id: str
    vector: tuple[float, ...]
    dimension: int
    model: str | None = None

    def __post_init__(self) -> None:
        if not self.chunk_id or not self.chunk_id.strip():
            raise ValueError("chunk_id cannot be empty")

        if not self.vector:
            raise ValueError("vector cannot be empty")

        if len(self.vector) != self.dimension:
            raise ValueError(
                f"vector length {len(self.vector)} does not match dimension {self.dimension}"
            )

        for val in self.vector:
            if not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ValueError("vector must contain only finite numbers")

    def to_dict(self) -> dict[str, Any]:
        """
        Deterministic, JSON-compatible serialization.
        """
        return {
            "chunk_id": self.chunk_id,
            "vector": list(self.vector),
            "dimension": self.dimension,
            "model": self.model,
        }
