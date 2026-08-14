from pathlib import Path
from dataclasses import dataclass
from typing import Any

from app.analysis.models import AnalysisResult
from app.analysis.service import AnalysisService


@dataclass
class CompilationResult:
    java_source: str
    backend_diagnostics: list[Any]
    semantic_diagnostics: list[Any]
    success: bool
    error: Exception | None = None


def compile_cobol_pipeline(source_path: str | Path) -> CompilationResult:
    """
    Executes the full compiler pipeline by delegating to AnalysisService.

    This helper preserves the original public behavior while routing the
    actual orchestration through the production AnalysisService.
    """
    result: AnalysisResult = AnalysisService().analyze(source_path)
    return CompilationResult(
        java_source=result.java_source,
        backend_diagnostics=result.backend_diagnostics,
        semantic_diagnostics=result.semantic_diagnostics,
        success=result.success,
        error=result.error,
    )
