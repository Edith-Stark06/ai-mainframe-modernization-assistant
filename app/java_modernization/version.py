"""
Phase 9 versioning (#125–#128).

Every artifact records the versions that produced it so an architecture,
a generated file, a compiler run and a repair attempt are all traceable
to a concrete pipeline state.
"""

from __future__ import annotations

from app.dataset.version import ANALYSIS_VERSION

ARCHITECTURE_VERSION: str = "p9-arch-v1"
GENERATION_VERSION: str = "p9-gen-v1"
COMPILATION_VERSION: str = "p9-compile-v1"
REPAIR_VERSION: str = "p9-repair-v1"
ANALYSIS_CONTRACT_VERSION: str = ANALYSIS_VERSION

__all__ = [
    "ARCHITECTURE_VERSION",
    "GENERATION_VERSION",
    "COMPILATION_VERSION",
    "REPAIR_VERSION",
    "ANALYSIS_CONTRACT_VERSION",
]
