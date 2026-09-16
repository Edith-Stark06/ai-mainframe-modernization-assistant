"""#128 — bounded, grounded AI self-repair."""

from __future__ import annotations

from app.java_modernization.repair.context import build_repair_context
from app.java_modernization.repair.loop import (
    REPAIR_PROMPT_VERSION,
    SelfRepairLoop,
    build_repair_prompt,
)
from app.java_modernization.repair.models import (
    FileChange,
    FilePatch,
    RepairAttempt,
    RepairPatch,
    RepairResult,
)
from app.java_modernization.repair.patch import apply_patch, parse_patch, validate_patch

__all__ = [
    "SelfRepairLoop",
    "build_repair_context",
    "build_repair_prompt",
    "REPAIR_PROMPT_VERSION",
    "parse_patch",
    "validate_patch",
    "apply_patch",
    "RepairPatch",
    "FilePatch",
    "FileChange",
    "RepairAttempt",
    "RepairResult",
]
