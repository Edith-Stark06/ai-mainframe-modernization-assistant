"""Exceptions for the Phase 9 Java-modernization pipeline (#125–#128)."""

from __future__ import annotations


class JavaModernizationError(Exception):
    """Base class for every Phase 9 error."""


class ArchitectureError(JavaModernizationError):
    """The target architecture could not be derived from the analysis."""


class GenerationError(JavaModernizationError):
    """Java project generation failed."""


class CompilationSetupError(JavaModernizationError):
    """The compilation workspace / command could not be prepared safely.

    Raised for path traversal, out-of-project files, a missing JDK, etc.
    A *compile failure* (bad Java) is NOT this — that is a normal
    :class:`~app.java_modernization.compilation.models.CompilationResult`
    with ``success = False``.
    """


class UnsafePatchError(JavaModernizationError):
    """An AI-proposed repair patch failed validation and was rejected."""


class RepairError(JavaModernizationError):
    """The self-repair loop could not run (not the same as 'still failing')."""


__all__ = [
    "JavaModernizationError",
    "ArchitectureError",
    "GenerationError",
    "CompilationSetupError",
    "UnsafePatchError",
    "RepairError",
]
