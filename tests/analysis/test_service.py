"""
Focused tests for the AnalysisService.

Coverage:
    1. Successful analysis of a valid COBOL program.
    2. Analysis of a COBOL program with semantic errors.
    3. Graceful handling of unexpected exceptions (e.g. reading a directory).
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.models import AnalysisResult
from app.analysis.service import AnalysisService

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestAnalysisService:
    def test_successful_analysis(self) -> None:
        """A valid COBOL program should produce Java source with no errors."""
        result: AnalysisResult = AnalysisService().analyze_file(
            FIXTURES_DIR / "hello_world.cbl"
        )
        assert result.success is True
        assert result.error is None
        assert result.ast is not None
        assert result.ir is not None
        assert 'System.out.println("HELLO WORLD");' in result.java_source
        assert len(result.semantic_diagnostics) == 0
        assert isinstance(result.dependencies, list)

    def test_semantic_error_analysis(self) -> None:
        """A program with undefined variables should fail semantic analysis."""
        result: AnalysisResult = AnalysisService().analyze_file(
            FIXTURES_DIR / "undefined_variable.cbl"
        )
        assert result.success is False
        assert result.error is None
        assert result.ast is not None
        assert len(result.semantic_diagnostics) > 0
        assert isinstance(result.dependencies, list)
        assert any(
            "UNDEFINED" in str(d).upper() or "NOT FOUND" in str(d).upper()
            for d in result.semantic_diagnostics
        )

    def test_unexpected_exception_handling(self, tmp_path: Path) -> None:
        """Passing a directory path should be handled gracefully."""
        result: AnalysisResult = AnalysisService().analyze_file(tmp_path)
        assert result.success is False
        assert result.error is not None
