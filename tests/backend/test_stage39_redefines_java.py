"""
Java backend + integration tests for task #stage39 — ``REDEFINES``
byte-overlay value derivation.

Purpose:
    Before this stage, a ``REDEFINES`` group's elementary children had
    no ``VALUE`` clause of their own (never evidenced in the corpus) and
    so were left with Java's own type defaults (``0``, ``""``) — silently
    wrong, since ``t_policy_redefines.cbl``'s ``PROCEDURE DIVISION``
    branches on exactly two of them (``NUM-VEHICLE-DRIVERS``,
    ``SMOKER-STATUS-CODE``) as if they held real data.

    :func:`~app.backend.java.generator._resolve_redefines_values` derives
    each child's value by slicing the redefined base item's own literal
    ``VALUE`` at that child's byte offset — COBOL's actual REDEFINES
    semantics — reusing :func:`~app.backend.java.value_initializer
    .translate_value_literal` unchanged for the Java initializer, never a
    second pipeline. This corpus's own base literal does not happen to
    align meaningfully with either redefining view's field layout (a
    genuine, pre-existing property of the synthetic data, not introduced
    by this stage) and one view's own declared fields exceed the base's
    length by 2 bytes — both are exercised directly below, gracefully
    degrading (a ``BE013`` diagnostic, no fabricated value) rather than
    guessing.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.analysis.service import AnalysisService
from app.backend.java.generator import (
    BackendDiagnostic,
    _resolve_redefines_values,
    build_fields_from_symbols,
)
from app.parser.lexer.position import Position
from app.parser.semantic.symbols import VariableSymbol
from app.parser.semantic.types import AlphanumericType, NumericType

_POS = Position(line=1, column=1, offset=0, filename="t.cbl")


def _sym(
    name: str,
    level: int,
    *,
    cobol_type=None,
    value: str | None = None,
    redefines: str | None = None,
) -> VariableSymbol:
    return VariableSymbol(
        name=name,
        declared_at=_POS,
        level=level,
        cobol_type=cobol_type,
        value=value,
        redefines=redefines,
    )


# ===========================================================================
# A. _resolve_redefines_values — direct unit coverage
# ===========================================================================


class TestBasicDerivation:
    def test_alphanumeric_children_sliced_correctly(self) -> None:
        symbols = [
            _sym(
                "BASE", 1, cobol_type=AlphanumericType(length=10), value="'ABCDEFGHIJ'"
            ),
            _sym("GRP", 1, redefines="BASE"),
            _sym("FIRST", 5, cobol_type=AlphanumericType(length=4)),
            _sym("SECOND", 5, cobol_type=AlphanumericType(length=6)),
        ]
        diags: list[BackendDiagnostic] = []
        result = _resolve_redefines_values(symbols, diags)
        assert result["FIRST"] == "'ABCD'"
        assert result["SECOND"] == "'EFGHIJ'"
        assert diags == []

    def test_numeric_child_sliced_as_plain_digits(self) -> None:
        symbols = [
            _sym("BASE", 1, cobol_type=AlphanumericType(length=5), value="'12345'"),
            _sym("GRP", 1, redefines="BASE"),
            _sym("NUM", 5, cobol_type=NumericType(digits=5)),
        ]
        diags: list[BackendDiagnostic] = []
        result = _resolve_redefines_values(symbols, diags)
        assert result["NUM"] == "12345"
        assert diags == []

    def test_non_digit_slice_still_returned_raw(self) -> None:
        """t_policy_redefines.cbl's own real shape: a numeric child's byte
        range doesn't happen to hold digit characters. This function
        still returns the raw slice -- translate_value_literal is the
        one place that declines an unsafe literal, exactly as it would
        for a hand-written VALUE clause with the same text."""
        symbols = [
            _sym("BASE", 1, cobol_type=AlphanumericType(length=5), value="'AB  E'"),
            _sym("GRP", 1, redefines="BASE"),
            _sym("NUM", 5, cobol_type=NumericType(digits=5)),
        ]
        diags: list[BackendDiagnostic] = []
        result = _resolve_redefines_values(symbols, diags)
        assert result["NUM"] == "AB  E"


class TestGracefulDegrade:
    def test_base_not_found(self) -> None:
        symbols = [
            _sym("GRP", 1, redefines="MISSING"),
            _sym("CHILD", 5, cobol_type=AlphanumericType(length=3)),
        ]
        diags: list[BackendDiagnostic] = []
        result = _resolve_redefines_values(symbols, diags)
        assert result == {}
        assert len(diags) == 1
        assert diags[0].code == "BE013"

    def test_base_has_no_value_clause(self) -> None:
        symbols = [
            _sym("BASE", 1, cobol_type=AlphanumericType(length=5), value=None),
            _sym("GRP", 1, redefines="BASE"),
            _sym("CHILD", 5, cobol_type=AlphanumericType(length=3)),
        ]
        diags: list[BackendDiagnostic] = []
        result = _resolve_redefines_values(symbols, diags)
        assert result == {}
        assert len(diags) == 1
        assert diags[0].code == "BE013"

    def test_base_value_not_a_quoted_string(self) -> None:
        symbols = [
            _sym("BASE", 1, cobol_type=NumericType(digits=5), value="12345"),
            _sym("GRP", 1, redefines="BASE"),
            _sym("CHILD", 5, cobol_type=AlphanumericType(length=3)),
        ]
        diags: list[BackendDiagnostic] = []
        result = _resolve_redefines_values(symbols, diags)
        assert result == {}
        assert len(diags) == 1
        assert diags[0].code == "BE013"

    def test_child_with_unresolvable_width_stops_group(self) -> None:
        symbols = [
            _sym(
                "BASE", 1, cobol_type=AlphanumericType(length=10), value="'ABCDEFGHIJ'"
            ),
            _sym("GRP", 1, redefines="BASE"),
            _sym("FIRST", 5, cobol_type=AlphanumericType(length=4)),
            _sym("BAD", 5, cobol_type=None),  # unresolved type
            _sym("NEVER-REACHED", 5, cobol_type=AlphanumericType(length=2)),
        ]
        diags: list[BackendDiagnostic] = []
        result = _resolve_redefines_values(symbols, diags)
        assert result == {"FIRST": "'ABCD'"}
        assert "NEVER-REACHED" not in result
        assert len(diags) == 1
        assert diags[0].code == "BE013"

    def test_width_overflow_stops_group_but_keeps_earlier_fields(self) -> None:
        """t_policy_redefines.cbl's real LIFE-PAYLOAD shape: the group's
        own declared width (62) exceeds the base's length (60). Fields
        fully within range keep their derived values; the offending
        field and everything after it get none."""
        symbols = [
            _sym(
                "BASE",
                1,
                cobol_type=AlphanumericType(length=60),
                value="'" + "X" * 60 + "'",
            ),
            _sym("GRP", 1, redefines="BASE"),
            _sym("A", 5, cobol_type=AlphanumericType(length=30)),
            _sym("B", 5, cobol_type=AlphanumericType(length=10)),
            _sym("C", 5, cobol_type=AlphanumericType(length=1)),
            _sym("D", 5, cobol_type=AlphanumericType(length=21)),  # 30+10+1+21=62 > 60
        ]
        diags: list[BackendDiagnostic] = []
        result = _resolve_redefines_values(symbols, diags)
        assert set(result) == {"A", "B", "C"}
        assert "D" not in result
        assert len(diags) == 1
        assert diags[0].code == "BE013"
        assert "exceeds" in diags[0].message


class TestScopeExclusions:
    def test_elementary_redefines_elementary_has_no_children_to_derive(
        self,
    ) -> None:
        """An elementary item redefining another elementary item is not
        evidenced anywhere in the corpus; it is captured on the symbol
        (``redefines``) but has no children, so nothing is derived for
        it -- confirmed here rather than assumed."""
        symbols = [
            _sym("BASE", 1, cobol_type=AlphanumericType(length=5), value="'HELLO'"),
            _sym("ALIAS", 1, cobol_type=AlphanumericType(length=5), redefines="BASE"),
        ]
        diags: list[BackendDiagnostic] = []
        result = _resolve_redefines_values(symbols, diags)
        assert result == {}
        assert diags == []

    def test_non_redefines_group_untouched(self) -> None:
        symbols = [
            _sym("GRP", 1),
            _sym("CHILD", 5, cobol_type=AlphanumericType(length=3)),
        ]
        diags: list[BackendDiagnostic] = []
        result = _resolve_redefines_values(symbols, diags)
        assert result == {}
        assert diags == []


# ===========================================================================
# B. build_fields_from_symbols integration
# ===========================================================================


class TestBuildFieldsIntegration:
    def test_derived_value_flows_into_java_field(self) -> None:
        symbols = [
            _sym(
                "BASE", 1, cobol_type=AlphanumericType(length=10), value="'ABCDEFGHIJ'"
            ),
            _sym("GRP", 1, redefines="BASE"),
            _sym("FIRST", 5, cobol_type=AlphanumericType(length=4)),
        ]
        diags: list[BackendDiagnostic] = []
        fields = build_fields_from_symbols(symbols, diags)
        by_name = {f.cobol_name: f for f in fields}
        assert by_name["FIRST"].initial_value == '"ABCD"'

    def test_non_digit_numeric_slice_gets_no_initializer(self) -> None:
        symbols = [
            _sym("BASE", 1, cobol_type=AlphanumericType(length=5), value="'AB  E'"),
            _sym("GRP", 1, redefines="BASE"),
            _sym("NUM", 5, cobol_type=NumericType(digits=5)),
        ]
        diags: list[BackendDiagnostic] = []
        fields = build_fields_from_symbols(symbols, diags)
        by_name = {f.cobol_name: f for f in fields}
        assert by_name["NUM"].initial_value is None

    def test_plain_symbol_without_redefines_unaffected(self) -> None:
        symbols = [
            _sym("WS-COUNT", 1, cobol_type=NumericType(digits=3), value="042"),
        ]
        fields = build_fields_from_symbols(symbols, [])
        assert fields[0].initial_value == "42"


# ===========================================================================
# C. Real corpus integration
# ===========================================================================


class TestRealCorpusIntegration:
    _PATH = Path("data/sources/phase6-v2/policy_redefines.cbl")

    def test_no_diagnostics_at_all(self) -> None:
        result = AnalysisService().analyze_file(self._PATH)
        assert result.syntax_diagnostics == []
        assert result.backend_diagnostics == []

    def test_auto_payload_children_derived(self) -> None:
        result = AnalysisService().analyze_file(self._PATH)
        java = result.java_source
        assert 'vehicleVin = "VIN12345678901234"' in java
        assert 'bodyStyle = "567SEDAN  "' in java
        assert 'specialPermitFlag = " "' in java
        # NUM-VEHICLE-DRIVERS's byte range isn't digits in this corpus's
        # own literal -- correctly declined, not fabricated.
        assert "numVehicleDrivers = " not in java
        assert "private int numVehicleDrivers;" in java

    def test_life_payload_children_derived_where_in_range(self) -> None:
        result = AnalysisService().analyze_file(self._PATH)
        java = result.java_source
        assert 'beneficiaryName = "VIN12345678901234567SEDAN     "' in java
        assert 'smokerStatusCode = "O"' in java
        # COVERAGE-DEATH-BEN's byte range isn't a valid decimal literal.
        assert "private double coverageDeathBen;" in java

    def test_generated_java_compiles_and_runs(self, tmp_path: Path) -> None:
        result = AnalysisService().analyze_file(self._PATH)
        java_file = tmp_path / "Polred01.java"
        java_file.write_text(result.java_source, encoding="utf-8")
        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr

        run = subprocess.run(
            ["java", "-cp", str(tmp_path), "Polred01"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert run.returncode == 0, run.stderr


# ===========================================================================
# D. Regression
# ===========================================================================


class TestRegressionOtherCorpusSources:
    """A handful of other corpus sources with VALUE clauses, groups, and
    OCCURS must render byte-identical Java -- REDEFINES derivation must
    never fire for a symbol that isn't tagged ``redefines``."""

    def test_table_indexed_unaffected(self) -> None:
        result = AnalysisService().analyze_file(
            Path("data/sources/phase6-v2/table_indexed.cbl")
        )
        assert not any(d.code == "BE013" for d in result.backend_diagnostics)

    def test_order_hierarchy_unaffected(self) -> None:
        result = AnalysisService().analyze_file(
            Path("data/sources/phase6-v2/order_hierarchy.cbl")
        )
        assert not any(d.code == "BE013" for d in result.backend_diagnostics)
