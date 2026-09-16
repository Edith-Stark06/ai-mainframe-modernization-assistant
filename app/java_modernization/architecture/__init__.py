"""#125 — Java architecture generation (deterministic, evidence-based)."""

from __future__ import annotations

from app.java_modernization.architecture.builder import build_architecture
from app.java_modernization.architecture.models import (
    ArchitectureComponent,
    Assumption,
    ComponentType,
    DataModelElement,
    Evidence,
    ExternalInterface,
    JavaArchitecture,
    SourceRef,
    StrategyRef,
    UnsupportedBehavior,
)

__all__ = [
    "build_architecture",
    "JavaArchitecture",
    "ArchitectureComponent",
    "ComponentType",
    "SourceRef",
    "Evidence",
    "Assumption",
    "UnsupportedBehavior",
    "ExternalInterface",
    "DataModelElement",
    "StrategyRef",
]
