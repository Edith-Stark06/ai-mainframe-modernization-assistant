"""
Tests for diagnostics serialization.

Coverage:
    - syntax diagnostic serialization
    - semantic diagnostic serialization
    - backend diagnostic serialization
    - severity/code/location preservation
    - diagnostic-specific fields
    - JSON-safe result
"""

from __future__ import annotations

from typing import Any

from app.analysis.serializers.diagnostics import serialize_diagnostics
from app.backend.java.generator import BackendDiagnostic, BackendSeverity
from app.parser.diagnostics.recovery import (
    RecoveryContext,
    SyntaxDiagnostic,
    SynchronisationPoint,
)
from app.parser.lexer.position import Position
from app.parser.semantic.diagnostics import SemanticDiagnostic, SemanticSeverity


class TestDiagnosticsSerialization:
    def test_semantic_diagnostic(self) -> None:
        pos = Position(line=10, column=4, offset=200, filename="prog.cbl")
        diag = SemanticDiagnostic(
            message="duplicate variable 'WS-COUNT'",
            position=pos,
            severity=SemanticSeverity.ERROR,
            code="SEM001",
        )
        data = serialize_diagnostics([diag])
        assert len(data) == 1
        assert data[0]["type"] == "SemanticDiagnostic"
        assert data[0]["message"] == "duplicate variable 'WS-COUNT'"
        assert data[0]["severity"] == "error"
        assert data[0]["code"] == "SEM001"
        assert data[0]["position"] == {
            "type": "Position",
            "line": 10,
            "column": 4,
            "offset": 200,
            "filename": "prog.cbl",
        }

    def test_semantic_severity_warning(self) -> None:
        pos = Position(line=5, column=1, offset=50, filename="x.cbl")
        diag = SemanticDiagnostic(
            message="unreferenced variable",
            position=pos,
            severity=SemanticSeverity.WARNING,
            code="SEM999",
        )
        data = serialize_diagnostics([diag])
        assert data[0]["severity"] == "warning"

    def test_syntax_diagnostic(self) -> None:
        diag = SyntaxDiagnostic(
            message="expected '.' after PROGRAM-ID name",
            line=3,
            column=5,
            offset=42,
            filename="prog.cbl",
            context=RecoveryContext.IDENTIFICATION_DIVISION,
            sync_point=SynchronisationPoint.PERIOD,
            tokens_skipped=2,
        )
        data = serialize_diagnostics([diag])
        assert data[0]["type"] == "SyntaxDiagnostic"
        assert data[0]["message"] == "expected '.' after PROGRAM-ID name"
        assert data[0]["line"] == 3
        assert data[0]["column"] == 5
        assert data[0]["offset"] == 42
        assert data[0]["filename"] == "prog.cbl"
        assert data[0]["context"] == "identification_division"
        assert data[0]["sync_point"] == "period"
        assert data[0]["tokens_skipped"] == 2

    def test_syntax_diagnostic_none_sync_point(self) -> None:
        diag = SyntaxDiagnostic(
            message="unexpected token",
            line=1,
            column=1,
            offset=0,
            filename="x.cbl",
            context=RecoveryContext.UNKNOWN,
            sync_point=None,
            tokens_skipped=0,
        )
        data = serialize_diagnostics([diag])
        assert data[0]["sync_point"] is None

    def test_backend_diagnostic_error(self) -> None:
        diag = BackendDiagnostic(
            severity=BackendSeverity.ERROR,
            message="unsupported type mapping",
            code="BE002",
        )
        data = serialize_diagnostics([diag])
        assert data[0]["type"] == "BackendDiagnostic"
        assert data[0]["severity"] == "ERROR"
        assert data[0]["message"] == "unsupported type mapping"
        assert data[0]["code"] == "BE002"

    def test_backend_diagnostic_warning(self) -> None:
        diag = BackendDiagnostic(
            severity=BackendSeverity.WARNING,
            message="missing name; using default",
            code="BE001",
        )
        data = serialize_diagnostics([diag])
        assert data[0]["severity"] == "WARNING"

    def test_mixed_diagnostics(self) -> None:
        pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        semantic = SemanticDiagnostic(
            message="undefined variable",
            position=pos,
            severity=SemanticSeverity.ERROR,
            code="SEM003",
        )
        syntax = SyntaxDiagnostic(
            message="expected '.'",
            line=1,
            column=1,
            offset=0,
            filename="x.cbl",
            context=RecoveryContext.STATEMENT,
            sync_point=SynchronisationPoint.PERIOD,
            tokens_skipped=1,
        )
        backend = BackendDiagnostic(
            severity=BackendSeverity.WARNING,
            message="fallback name",
            code="BE001",
        )
        data = serialize_diagnostics([semantic, syntax, backend])
        assert len(data) == 3
        assert data[0]["type"] == "SemanticDiagnostic"
        assert data[1]["type"] == "SyntaxDiagnostic"
        assert data[2]["type"] == "BackendDiagnostic"

    def test_empty_list(self) -> None:
        assert serialize_diagnostics([]) == []

    def test_deterministic_output(self) -> None:
        pos = Position(line=10, column=4, offset=200, filename="p.cbl")
        diag1 = SemanticDiagnostic(
            message="dup",
            position=pos,
            severity=SemanticSeverity.ERROR,
            code="SEM001",
        )
        diag2 = SemanticDiagnostic(
            message="dup",
            position=pos,
            severity=SemanticSeverity.ERROR,
            code="SEM001",
        )
        assert serialize_diagnostics([diag1]) == serialize_diagnostics([diag2])

    def test_json_safe_result(self) -> None:
        pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        diag = SemanticDiagnostic(
            message="test",
            position=pos,
            severity=SemanticSeverity.ERROR,
            code="SEM001",
        )
        data = serialize_diagnostics([diag])
        _assert_json_safe(data)


def _assert_json_safe(value: Any) -> None:
    """Recursively verify that *value* contains only JSON-native types."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_json_safe(item)
        return
    if isinstance(value, dict):
        for v in value.values():
            _assert_json_safe(v)
        return
    raise TypeError(f"Non-JSON-safe value: {type(value).__name__}")
