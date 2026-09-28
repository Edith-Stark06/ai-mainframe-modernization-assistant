"""
Java backend tests for task #stage42 — ``COMPUTE`` int/double narrowing cast.

Purpose:
    COBOL allows a ``COMPUTE`` with a decimal-valued expression to store
    into an integer-PICTURE target, implicitly truncating (unless
    ``ROUNDED`` is specified, which this backend does not model). Java has
    no implicit narrowing conversion for ``double`` -> ``int`` in an
    assignment, so ``statement_emitter.emit_compute`` translating such a
    ``COMPUTE`` produced ``int = double-expression;`` with no cast --
    valid IR, uncompilable Java. Confirmed on the real corpus:
    ``data/sources/phase6-v2/inventory_reorder.cbl``'s
    ``COMPUTE REORDER-POINT-QTY = (AVG-DAILY-DEMAND * SUPPLIER-LEAD-DAYS
    * SEASONALITY-INDEX) + SAFETY-STOCK-LEVEL`` (an integer target, two
    ``V99`` decimal operands in the expression) was the one and only
    javac failure across the full 45-source training corpus (see
    ``tests/backend/test_stage38_if_arithmetic_expression_java.py`` and
    ``tests/backend/test_stage40_read_at_end_java.py``, both of which
    used to document this as "the known unrelated issue").

    Fixed by ``emit_compute`` now accepting the same optional
    ``ConditionContext`` every other type-aware emitter already does
    (``emit_display``), and inserting an explicit ``(int)`` cast around
    the whole expression when the target's declared Java type is ``int``
    and the expression tree contains any ``double``-typed operand
    anywhere (``app.backend.java.condition_context.operand_java_type``,
    promoted from a previously-private helper of the same name, reused
    here rather than duplicated). Java's ``(int)`` cast truncates toward
    zero, matching COBOL's own un-``ROUNDED`` truncate-on-store behavior
    for this domain's non-negative quantities.

Non-responsibilities:
    - ``ROUNDED`` -- unevidenced in the 45-source corpus, out of scope.
    - Negative-value truncation direction (COBOL truncates toward zero
      the same as Java's ``(int)`` cast for this domain's non-negative
      quantities; a negative decimal's truncation semantics were not
      separately investigated).
    - Any other narrowing pair (there is no ``float``/``long`` in this
      backend's Java type vocabulary -- only ``int``/``double``/``String``,
      confirmed directly against ``app/backend/java/field_model.py``).

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.analysis.service import AnalysisService

_HEADER = (
    "IDENTIFICATION DIVISION.\n"
    "PROGRAM-ID. T.\n"
    "DATA DIVISION.\n"
    "WORKING-STORAGE SECTION.\n"
    "01 WS-INT-A PIC 9(5).\n"
    "01 WS-INT-B PIC 9(5).\n"
    "01 WS-DEC-A PIC 9(5)V99.\n"
    "01 WS-DEC-B PIC 9(5)V99.\n"
    "01 WS-RESULT-INT PIC 9(5).\n"
    "01 WS-RESULT-DEC PIC 9(5)V99.\n"
)


def _analyze(tmp_path: Path, body: str, header: str = _HEADER):
    path = tmp_path / "t.cbl"
    path.write_text(
        header + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body, encoding="utf-8"
    )
    result = AnalysisService().analyze_file(path)
    assert not result.backend_diagnostics, result.backend_diagnostics
    return result.java_source


class TestCastInsertion:
    def test_int_target_with_double_operand_gets_cast(self, tmp_path: Path) -> None:
        java = _analyze(tmp_path, "    COMPUTE WS-RESULT-INT = WS-DEC-A + WS-INT-A.\n")
        assert "wsResultInt = (int) (wsDecA + wsIntA);" in java

    def test_int_target_with_double_operand_deep_in_tree_gets_cast(
        self, tmp_path: Path
    ) -> None:
        """The double operand need not be at the top of the tree -- any
        leaf anywhere makes the whole expression double-valued, matching
        Java's own numeric-promotion rule."""
        java = _analyze(
            tmp_path,
            "    COMPUTE WS-RESULT-INT = "
            "(WS-INT-A * WS-INT-B) + (WS-DEC-A * WS-DEC-B).\n",
        )
        assert "wsResultInt = (int) (wsIntA * wsIntB + wsDecA * wsDecB);" in java

    def test_int_target_with_all_int_operands_gets_no_cast(
        self, tmp_path: Path
    ) -> None:
        java = _analyze(tmp_path, "    COMPUTE WS-RESULT-INT = WS-INT-A + WS-INT-B.\n")
        assert "wsResultInt = wsIntA + wsIntB;" in java
        assert "(int)" not in java

    def test_double_target_with_double_operand_gets_no_cast(
        self, tmp_path: Path
    ) -> None:
        """double = double needs no cast -- only the double-into-int
        direction is a Java compile error."""
        java = _analyze(tmp_path, "    COMPUTE WS-RESULT-DEC = WS-DEC-A + WS-DEC-B.\n")
        assert "wsResultDec = wsDecA + wsDecB;" in java
        assert "(int)" not in java

    def test_double_target_with_int_operands_gets_no_cast(self, tmp_path: Path) -> None:
        """int -> double is Java's own implicit widening -- no cast
        needed either way."""
        java = _analyze(tmp_path, "    COMPUTE WS-RESULT-DEC = WS-INT-A + WS-INT-B.\n")
        assert "wsResultDec = wsIntA + wsIntB;" in java
        assert "(int)" not in java

    def test_int_target_with_decimal_literal_gets_cast(self, tmp_path: Path) -> None:
        """A bare decimal literal (``1.25``), not just a ``V99`` field,
        also makes the expression double-valued."""
        java = _analyze(tmp_path, "    COMPUTE WS-RESULT-INT = WS-INT-A * 1.25.\n")
        assert "wsResultInt = (int) (wsIntA * 1.25);" in java

    def test_int_target_with_integer_literal_gets_no_cast(self, tmp_path: Path) -> None:
        java = _analyze(tmp_path, "    COMPUTE WS-RESULT-INT = WS-INT-A * 2.\n")
        assert "wsResultInt = wsIntA * 2;" in java
        assert "(int)" not in java


class TestArrayOperands:
    """``JavaField.java_type`` for an ``OCCURS`` array is the array's own
    type (``"int[]"``/``"double[]"``, task #stage32/33), not the bare
    element type -- found and fixed during this stage's own review, not
    evidenced by the real corpus source (which has no array COMPUTE
    target/operand). Both directions of the same class of bug as the
    scalar case above: a subscripted array assignment target, and a
    subscripted array operand feeding a different scalar target."""

    _ARRAY_HEADER = (
        "IDENTIFICATION DIVISION.\n"
        "PROGRAM-ID. T.\n"
        "DATA DIVISION.\n"
        "WORKING-STORAGE SECTION.\n"
        "01 WS-IDX PIC 9(2).\n"
        "01 WS-INT-ARR PIC 9(5) OCCURS 5.\n"
        "01 WS-DEC-ARR PIC 9(5)V99 OCCURS 5.\n"
        "01 WS-DEC-A PIC 9(5)V99.\n"
        "01 WS-RESULT-INT PIC 9(5).\n"
    )

    def test_subscripted_int_array_target_gets_cast(self, tmp_path: Path) -> None:
        """A subscripted ``int[]`` element target needs the same cast a
        scalar ``int`` field does -- one element is always assigned,
        never the whole array."""
        java = _analyze(
            tmp_path,
            "    COMPUTE WS-INT-ARR(WS-IDX) = WS-DEC-A * 2.\n",
            header=self._ARRAY_HEADER,
        )
        assert "wsIntArr[wsIdx - 1] = (int) (wsDecA * 2);" in java

    def test_subscripted_double_array_operand_triggers_cast(
        self, tmp_path: Path
    ) -> None:
        """A subscripted ``double[]`` element used as an *operand* also
        makes the whole expression double-valued, exactly like a plain
        scalar ``double`` field would."""
        java = _analyze(
            tmp_path,
            "    COMPUTE WS-RESULT-INT = WS-DEC-ARR(WS-IDX) * 2.\n",
            header=self._ARRAY_HEADER,
        )
        assert "wsResultInt = (int) (wsDecArr[wsIdx - 1] * 2);" in java

    def test_subscripted_int_array_operand_gets_no_cast(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path,
            "    COMPUTE WS-RESULT-INT = WS-INT-ARR(WS-IDX) * 2.\n",
            header=self._ARRAY_HEADER,
        )
        assert "wsResultInt = wsIntArr[wsIdx - 1] * 2;" in java
        assert "(int)" not in java

    def test_array_compute_compiles(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path,
            "    COMPUTE WS-INT-ARR(WS-IDX) = WS-DEC-A * 2.\n"
            "    COMPUTE WS-RESULT-INT = WS-DEC-ARR(WS-IDX) * 2.\n",
            header=self._ARRAY_HEADER,
        )
        java_file = tmp_path / "T.java"
        java_file.write_text(java, encoding="utf-8")
        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert javac.returncode == 0, javac.stderr


class TestRuntimeExecution:
    def test_cast_expression_compiles_and_truncates(self, tmp_path: Path) -> None:
        """25.50 * 10 = 255.0, truncated (not rounded) to 255 -- proving
        the cast is a real, correct truncation, not just a compile-fix."""
        path = tmp_path / "t.cbl"
        path.write_text(
            _HEADER
            + "PROCEDURE DIVISION.\nMAIN-PARA.\n"
            + "    MOVE 25.50 TO WS-DEC-A.\n"
            + "    MOVE 10 TO WS-INT-A.\n"
            + "    COMPUTE WS-RESULT-INT = WS-DEC-A * WS-INT-A.\n"
            + "    DISPLAY WS-RESULT-INT.\n"
            + "    STOP RUN.\n",
            encoding="utf-8",
        )
        result = AnalysisService().analyze_file(path)
        java_file = tmp_path / "T.java"
        java_file.write_text(result.java_source, encoding="utf-8")
        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert javac.returncode == 0, javac.stderr
        run = subprocess.run(
            ["java", "-cp", str(tmp_path), "T"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert run.returncode == 0, run.stderr
        # WS-RESULT-INT is PIC 9(5): DISPLAY zero-pads to 5 digits.
        assert run.stdout.strip() == "00255"


class TestRealCorpusIntegration:
    """``inventory_reorder.cbl`` -- the exact real corpus source this
    fix was found on -- the only javac failure across all 45 training
    corpus sources before this fix."""

    _PATH = Path("data/sources/phase6-v2/inventory_reorder.cbl")

    def test_reorder_point_qty_cast_is_present(self) -> None:
        result = AnalysisService().analyze_file(self._PATH)
        assert (
            "reorderPointQty = (int) (avgDailyDemand * supplierLeadDays "
            "* seasonalityIndex + safetyStockLevel);" in result.java_source
        )

    def test_compiles_and_runs(self, tmp_path: Path) -> None:
        result = AnalysisService().analyze_file(self._PATH)
        java_file = tmp_path / "Invro01.java"
        java_file.write_text(result.java_source, encoding="utf-8")
        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr
        run = subprocess.run(
            ["java", "-cp", str(tmp_path), "Invro01"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert run.returncode == 0, run.stderr

    def test_computed_reorder_point_qty_is_correctly_truncated(
        self, tmp_path: Path
    ) -> None:
        """(25.50 * 10 * 1.25) + 150 = 468.75, truncated (not rounded,
        since this source has no ROUNDED clause) to 468 -- verified via
        reflection on the real, unmodified corpus source's own class,
        not a synthetic stand-in."""
        result = AnalysisService().analyze_file(self._PATH)
        java_file = tmp_path / "Invro01.java"
        java_file.write_text(result.java_source, encoding="utf-8")
        reader = tmp_path / "Reader.java"
        reader.write_text(
            "import java.lang.reflect.Field;\n"
            "public class Reader {\n"
            "    public static void main(String[] args) throws Exception {\n"
            '        Class<?> c = Class.forName("Invro01");\n'
            "        Object o = c.getDeclaredConstructor().newInstance();\n"
            '        c.getMethod("run").invoke(o);\n'
            '        Field f = c.getDeclaredField("reorderPointQty");\n'
            "        f.setAccessible(true);\n"
            "        System.out.println(f.get(o));\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file), str(reader)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr
        run = subprocess.run(
            ["java", "-cp", str(tmp_path), "Reader"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert run.returncode == 0, run.stderr
        assert run.stdout.strip() == "468"
