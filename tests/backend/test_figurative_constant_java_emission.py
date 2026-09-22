"""
Java translation of figurative-constant condition operands (Stage 31).

Purpose:
    ``docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md`` (Stage 26) fixed the
    *parser* so ``SPACES``/``ZEROS`` could stand as an ``IF``-condition
    operand, and documented (its own §6, not fixed there) that the Java
    backend then translated every figurative-constant spelling -- old and
    new alike -- as a bare, undeclared Java identifier reference
    (``ZERO`` -> ``zero``, ``SPACES`` -> ``spaces``): a guaranteed ``javac``
    "cannot find symbol" failure, for any COBOL program that used one. A
    manual end-to-end conversion test (``IF WS-BALANCE < ZEROS``) hit
    exactly this, confirming it experimentally rather than only in a unit
    test.

    This stage fixes that translation, narrowly: a
    ``ZERO``/``ZEROS``/``ZEROES`` or ``SPACE``/``SPACES`` operand of an
    ``IF``/``PERFORM UNTIL`` comparison is translated to a type-compatible
    Java literal (``0``, ``0.0``, ``""``) using the *other* operand's
    already-known Java type, reusing
    :func:`~app.backend.java.value_initializer.translate_value_literal` --
    the exact function already used, unmodified, for ``VALUE`` clauses and
    level-88 values. See
    ``app.backend.java.condition_context.translate_figurative_operand`` for
    the full rationale, including why ``HIGH-VALUE(S)``/``LOW-VALUE(S)`` are
    deliberately left untranslated (no existing Java representation to
    reuse, anywhere in the codebase, for either).

    Only comparison-condition translation changes here. ``MOVE ZEROS TO X``
    and every other statement kind still go through the generic, unmodified
    ``_translate_operand`` -- out of scope (the objective, and every example
    given, is about ``IF``/``PERFORM UNTIL`` conditions).

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from app.analysis.service import AnalysisService
from app.backend.java.condition_context import (
    ConditionContext,
    translate_figurative_operand,
)
from app.backend.java.control_flow_emitter import emit_if, emit_perform_until
from app.dataset.corpus import load_training_corpus
from app.ir.instructions import IRIf, IRPerformUntil

needs_java = pytest.mark.skipif(
    shutil.which("javac") is None or shutil.which("java") is None,
    reason="javac/java not available",
)


def _ctx(**types: str) -> ConditionContext:
    return ConditionContext(field_types=dict(types))


# ===========================================================================
# 1. translate_figurative_operand: unit-level, every required case
# ===========================================================================

_NUMERIC_CTX = _ctx(wsN="int", wsAmt="double", wsCode="String")


@pytest.mark.parametrize("word", ["ZERO", "ZEROS", "ZEROES"])
def test_zero_family_against_an_int_field_is_0(word: str) -> None:
    assert translate_figurative_operand(word, "WS-N", "==", _NUMERIC_CTX) == "0"
    assert translate_figurative_operand(word, "WS-N", "<", _NUMERIC_CTX) == "0"


@pytest.mark.parametrize("word", ["ZERO", "ZEROS", "ZEROES"])
def test_zero_family_against_a_double_field_is_0_point_0(word: str) -> None:
    assert translate_figurative_operand(word, "WS-AMT", "<", _NUMERIC_CTX) == "0.0"
    assert translate_figurative_operand(word, "WS-AMT", ">=", _NUMERIC_CTX) == "0.0"


@pytest.mark.parametrize("word", ["SPACE", "SPACES"])
def test_space_family_against_a_string_field_is_empty_string(word: str) -> None:
    assert translate_figurative_operand(word, "WS-CODE", "==", _NUMERIC_CTX) == '""'
    assert translate_figurative_operand(word, "WS-CODE", "!=", _NUMERIC_CTX) == '""'


def test_space_family_ordering_is_not_translated() -> None:
    """``_cobolEquals`` -- and this translation -- is equality-only; COBOL
    text ordering is collating-sequence semantics this backend does not
    model (matching ``translate_comparison``'s own restriction)."""
    assert translate_figurative_operand("SPACES", "WS-CODE", "<", _NUMERIC_CTX) is None
    assert translate_figurative_operand("SPACES", "WS-CODE", ">=", _NUMERIC_CTX) is None


def test_left_hand_figurative_operand() -> None:
    """The figurative constant may be on either side of the comparison."""
    assert translate_figurative_operand("ZEROS", "WS-N", "==", _NUMERIC_CTX) == "0"
    assert translate_figurative_operand("SPACES", "WS-CODE", "==", _NUMERIC_CTX) == '""'


def test_type_mismatch_is_not_translated() -> None:
    """ZERO-family against text, SPACE-family against a number: no proof
    either is what the COBOL author meant, so nothing is guessed."""
    assert translate_figurative_operand("ZERO", "WS-CODE", "==", _NUMERIC_CTX) is None
    assert translate_figurative_operand("SPACES", "WS-N", "==", _NUMERIC_CTX) is None
    assert translate_figurative_operand("ZEROS", "WS-AMT", "==", _NUMERIC_CTX) == "0.0"


def test_unknown_other_type_is_not_translated() -> None:
    """The other operand is a field this context does not know (e.g. a FILE
    SECTION field the backend never declared) -- decline, do not guess."""
    assert (
        translate_figurative_operand("ZEROS", "FD-UNKNOWN", "==", _NUMERIC_CTX) is None
    )
    assert (
        translate_figurative_operand("SPACES", "FD-UNKNOWN", "==", _NUMERIC_CTX) is None
    )


def test_other_operand_may_be_a_bare_literal() -> None:
    """The other side need not be a field -- a quoted or numeric literal's
    own shape is enough to prove a type."""
    assert translate_figurative_operand("ZEROS", "5", "<", _ctx()) == "0"
    assert translate_figurative_operand("ZEROS", "2.5", "<", _ctx()) == "0.0"
    assert translate_figurative_operand("SPACES", "'AUTO'", "==", _ctx()) == '""'


def test_high_values_and_low_values_are_never_translated() -> None:
    """Deliberately out of scope: no existing Java representation for
    either spelling anywhere in the codebase (not even for ``VALUE``
    clauses) to safely reuse -- see this module's docstring."""
    for word in ("HIGH-VALUE", "HIGH-VALUES", "LOW-VALUE", "LOW-VALUES"):
        assert translate_figurative_operand(word, "WS-N", "==", _NUMERIC_CTX) is None
        assert translate_figurative_operand(word, "WS-CODE", "==", _NUMERIC_CTX) is None


def test_no_context_means_no_change() -> None:
    assert translate_figurative_operand("ZEROS", "WS-N", "==", None) is None
    assert translate_figurative_operand("SPACES", "WS-CODE", "==", None) is None


def test_an_ordinary_identifier_is_never_mistaken_for_a_figurative_constant() -> None:
    """Regression guard: only the two canonical families are recognised --
    an ordinary COBOL name is untouched, however it compares."""
    assert (
        translate_figurative_operand("WS-BALANCE", "WS-N", "==", _NUMERIC_CTX) is None
    )
    assert (
        translate_figurative_operand("WS-CODE", "WS-CODE", "==", _NUMERIC_CTX) is None
    )


# ===========================================================================
# 2. emit_if / emit_perform_until: the full condition-triple path
# ===========================================================================


def test_emit_if_ordering_right_hand_zeros() -> None:
    """The motivating example: ``IF WS-BALANCE < ZEROS``."""
    ctx = _ctx(wsBalance="double")
    instr = IRIf(left="WS-BALANCE", operator="<", right="ZEROS")
    assert emit_if(instr, 0, [], ctx) == ["if (wsBalance < 0.0) {"]


def test_emit_if_equality_right_hand_zero_on_int_field() -> None:
    ctx = _ctx(wsCount="int")
    instr = IRIf(left="WS-COUNT", operator="=", right="ZERO")
    assert emit_if(instr, 0, [], ctx) == ["if (wsCount == 0) {"]


def test_emit_if_left_hand_zeros() -> None:
    ctx = _ctx(wsBalance="double")
    instr = IRIf(left="ZEROS", operator="=", right="WS-BALANCE")
    assert emit_if(instr, 0, [], ctx) == ["if (0.0 == wsBalance) {"]


def test_emit_if_equality_and_not_equal_spaces_on_string_field() -> None:
    ctx = _ctx(wsName="String")
    eq = IRIf(left="WS-NAME", operator="=", right="SPACES")
    assert emit_if(eq, 0, [], ctx) == ['if (_cobolEquals(wsName, "")) {']
    ne = IRIf(left="WS-NAME", operator="<>", right="SPACES")  # COBOL NOT = spelling
    assert emit_if(ne, 0, [], ctx) == ['if (!_cobolEquals(wsName, "")) {']


def test_emit_if_without_context_is_unchanged() -> None:
    """No context: every condition translates exactly as before this stage
    (and before Stage 24) -- same contract as ``translate_comparison``."""
    instr = IRIf(left="WS-BALANCE", operator="<", right="ZEROS")
    assert emit_if(instr, 0, []) == ["if (wsBalance < zeros) {"]


def test_emit_perform_until_zeros() -> None:
    """The same ``_build_condition`` path serves ``PERFORM UNTIL``."""
    ctx = _ctx(wsBalance="double")
    instr = IRPerformUntil(left="WS-BALANCE", operator="<", right="ZEROS")
    assert emit_perform_until(instr, 0, [], ctx) == ["while (!(wsBalance < 0.0)) {"]


def test_emit_if_high_values_still_undeclared() -> None:
    """Documents, does not fix: HIGH-VALUES stays exactly as broken as it
    was before this stage."""
    ctx = _ctx(wsCount="int")
    instr = IRIf(left="WS-COUNT", operator="=", right="HIGH-VALUES")
    assert emit_if(instr, 0, [], ctx) == ["if (wsCount == highValues) {"]


# ===========================================================================
# 3. Regression: ordinary reserved words still rejected at parse time
# ===========================================================================


def test_ordinary_reserved_word_operand_still_rejected_at_parse_time() -> None:
    """``IF X = MOVE`` must not become a valid comparison merely because
    ``MOVE`` is a ``TokenType.KEYWORD`` -- unchanged parser behavior from
    Stage 26 (``_FIGURATIVE_CONSTANT_KEYWORDS`` names only ``ZEROS``/
    ``SPACES``); this stage touches only the Java backend, so this must
    still hold."""
    source = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-CODE PIC X(5) VALUE 'AUTO'.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           IF WS-CODE = MOVE\n"
        "               DISPLAY 'Y'\n"
        "           END-IF\n"
        "           STOP RUN.\n"
    )
    from app.parser.lexer.lexer import CobolLexer
    from app.parser.syntax.program_parser import ProgramParser

    result = ProgramParser().parse_with_diagnostics(
        CobolLexer().tokenize(source, filename="t.cbl")
    )
    assert "SYN005" in [str(d.code) for d in result.diagnostics]


# ===========================================================================
# 4. Existing level-88 and VALUE-clause figurative-constant behavior is
#    unchanged (this stage touches only comparison-condition translation)
# ===========================================================================


def _analyse(source: str, tmp_path: Path) -> Any:
    path = tmp_path / "t.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def test_value_clause_figurative_constants_are_unchanged(tmp_path: Path) -> None:
    source = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TVAL.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-BAL PIC S9(5)V99 VALUE ZEROS.\n"
        "       01 WS-CNT PIC 9(3) VALUE ZEROS.\n"
        "       01 WS-NM  PIC X(10) VALUE SPACES.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
    )
    java = _analyse(source, tmp_path).java_source
    assert "private double wsBal = 0.0;" in java
    assert "private int wsCnt = 0;" in java
    assert 'private String wsNm = "";' in java


def test_level88_condition_behavior_is_unchanged(tmp_path: Path) -> None:
    """Level-88 translation goes through ``translate_condition_name``, a
    completely separate code path from the comparison-operand translation
    this stage adds; confirms it directly, end to end."""
    source = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T88.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-STATUS PIC X VALUE 'A'.\n"
        "           88 ACCOUNT-ACTIVE VALUE 'A'.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           IF ACCOUNT-ACTIVE\n"
        "               DISPLAY 'ACTIVE'\n"
        "           END-IF\n"
        "           STOP RUN.\n"
    )
    result = _analyse(source, tmp_path)
    assert result.success
    assert not [d for d in result.backend_diagnostics if d.code == "BE007"]
    assert '_cobolEquals(wsStatus, "A")' in result.java_source


# ===========================================================================
# 5. End-to-end regression: the manual test's exact scenario, real javac
# ===========================================================================

_E2E_SOURCE = (
    "       IDENTIFICATION DIVISION.\n"
    "       PROGRAM-ID. NEGCHK.\n"
    "       DATA DIVISION.\n"
    "       WORKING-STORAGE SECTION.\n"
    "       01 WS-BALANCE PIC S9(7)V99 VALUE -5.00.\n"
    "       PROCEDURE DIVISION.\n"
    "       MAIN-PARA.\n"
    "           IF WS-BALANCE < ZEROS\n"
    "               DISPLAY 'NEGATIVE'\n"
    "           ELSE\n"
    "               DISPLAY 'NON-NEGATIVE'\n"
    "           END-IF\n"
    "           STOP RUN.\n"
)


def test_end_to_end_no_undeclared_identifier(tmp_path: Path) -> None:
    result = _analyse(_E2E_SOURCE, tmp_path)
    assert result.success
    assert result.syntax_diagnostics == []
    assert result.backend_diagnostics == []
    assert "if (wsBalance < 0.0) {" in result.java_source
    assert re.search(r"\bzeros\b", result.java_source) is None


@needs_java
def test_end_to_end_compiles_and_runs(tmp_path: Path) -> None:
    result = _analyse(_E2E_SOURCE, tmp_path)
    cls = re.search(r"public class (\w+)", result.java_source).group(1)  # type: ignore[union-attr]
    (tmp_path / f"{cls}.java").write_text(result.java_source, encoding="utf-8")
    compiled = subprocess.run(
        ["javac", "-d", str(tmp_path), str(tmp_path / f"{cls}.java")],
        capture_output=True,
        text=True,
    )
    assert compiled.returncode == 0, compiled.stderr
    ran = subprocess.run(
        ["java", "-cp", str(tmp_path), cls], capture_output=True, text=True, timeout=20
    )
    assert ran.returncode == 0
    assert ran.stdout.strip() == "NEGATIVE"  # WS-BALANCE = -5.00 < 0


# ===========================================================================
# 6. Corpus safety: zero occurrences means zero corpus/dataset impact
# ===========================================================================

_FIGURATIVE_IN_COMPARISON = re.compile(
    r"(?:=|<>|<=|>=|<|>)\s*(SPACES?|ZEROS?|ZEROES|HIGH-VALUES?|LOW-VALUES?)\b",
    re.IGNORECASE,
)


def test_no_corpus_source_has_a_figurative_constant_comparison_operand() -> None:
    """Re-verified for this stage, not assumed from Stage 26: this backend
    fix has zero corpus impact, so the MMIM generator version is not
    bumped and the dataset is not regenerated for it."""
    hits: dict[str, int] = {}
    for rec in load_training_corpus():
        n = 0
        for line in rec.source.splitlines():
            if len(line) > 6 and line[6] in "*/":
                continue
            code = line[7:] if len(line) > 7 else ""
            n += len(_FIGURATIVE_IN_COMPARISON.findall(code))
        if n:
            hits[rec.source_id] = n
    assert hits == {}
