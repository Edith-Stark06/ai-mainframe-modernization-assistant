"""Tests for the MMIM v2 extractor upgrade: deterministic PERFORM UNTIL
loop/accumulator behavioral test derivation (app.behavioral.extraction.loops).

These are additive to the existing #129 IF/ELSE boundary extractor
(tests/behavioral/test_extraction.py, left untouched) — every case here
is either a new loop-derivation scenario or a regression guard proving
the original extractor's behavior did not change.
"""

from __future__ import annotations

import tempfile

from app.dataset.analysis_bundle import build_analysis_bundle
from app.behavioral.extraction.extractor import extract_behavioral_tests


def _bundle(source: str, source_id: str = "PROBE"):
    return build_analysis_bundle(source_id, source, tempfile.mkdtemp())


INTEREST_ACCRUE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. INTACCR.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-PRINCIPAL  PIC 9(7) VALUE 10000.
       01 WS-INTEREST   PIC 9(7) VALUE 0.
       01 WS-DAY        PIC 9(3) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM ACCRUE-DAILY.
           DISPLAY WS-INTEREST.
           STOP RUN.
       ACCRUE-DAILY.
           PERFORM UNTIL WS-DAY >= 30
               ADD 3 TO WS-INTEREST
               ADD 1 TO WS-DAY
           END-PERFORM.
"""

LOAN_BALANCE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOANBAL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-BALANCE     PIC 9(7) VALUE 12000.
       01 WS-PAYMENT     PIC 9(5) VALUE 500.
       01 WS-MONTHS      PIC 9(3) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM AMORTIZE.
           DISPLAY WS-MONTHS.
           STOP RUN.
       AMORTIZE.
           PERFORM UNTIL WS-BALANCE = 0
               IF WS-BALANCE < WS-PAYMENT
                   MOVE 0 TO WS-BALANCE
               ELSE
                   SUBTRACT WS-PAYMENT FROM WS-BALANCE
               END-IF
               ADD 1 TO WS-MONTHS
           END-PERFORM.
"""

#: a loop whose body PERFORMs another paragraph — not in the whitelist
LOOP_WITH_CALL = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOOPCALL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-N PIC 9(3) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM DRIVE.
           STOP RUN.
       DRIVE.
           PERFORM UNTIL WS-N >= 5
               PERFORM HELPER
               ADD 1 TO WS-N
           END-PERFORM.
       HELPER.
           DISPLAY WS-N.
"""

#: a loop whose exit boundary references a variable with no known
#: initial value (parser-incomplete-style: nothing to statically resolve)
LOOP_UNRESOLVABLE_BOUND = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOOPUNRES.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-N     PIC 9(3) VALUE 0.
       01 WS-LIMIT PIC 9(3).
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM DRIVE.
           STOP RUN.
       DRIVE.
           PERFORM UNTIL WS-N >= WS-LIMIT
               ADD 1 TO WS-N
           END-PERFORM.
"""


# --------------------------------------------------------------------------
# 1. PERFORM UNTIL with numeric accumulator
# --------------------------------------------------------------------------


def test_perform_until_numeric_accumulator_produces_tests():
    suite = extract_behavioral_tests(_bundle(INTEREST_ACCRUE))
    loop_tests = [t for t in suite.tests if t.test_type == "loop_accumulator"]
    assert len(loop_tests) == 3
    assert suite.skipped_loops == ()


# --------------------------------------------------------------------------
# 2. PERFORM UNTIL with state mutation (conditional accumulator)
# --------------------------------------------------------------------------


def test_perform_until_with_conditional_state_mutation():
    suite = extract_behavioral_tests(_bundle(LOAN_BALANCE))
    loop_tests = [t for t in suite.tests if t.test_type == "loop_accumulator"]
    assert len(loop_tests) == 2
    # one test exercises the IF-taken branch (partial final payment)
    partial_payment = [
        t
        for t in loop_tests
        if any(
            s.field == "WS-BALANCE" and s.from_value == "1"
            for s in t.expected_state_changes
        )
    ]
    assert len(partial_payment) == 1
    final_state = {
        s.field: s.to_value for s in partial_payment[0].expected_state_changes
    }
    assert final_state["WS-BALANCE"] == "0"
    assert final_state["WS-MONTHS"] == "1"


# --------------------------------------------------------------------------
# 3. Loop with zero-iteration boundary
# --------------------------------------------------------------------------


def test_zero_iteration_boundary_is_derived():
    suite = extract_behavioral_tests(_bundle(INTEREST_ACCRUE))
    zero_iter = [
        t
        for t in suite.tests
        if t.test_type == "loop_accumulator" and t.iteration_count == 0
    ]
    assert len(zero_iter) >= 1
    for t in zero_iter:
        changes = {
            s.field: (s.from_value, s.to_value) for s in t.expected_state_changes
        }
        # zero iterations => terminal state equals the (overridden) initial state
        assert changes["WS-DAY"][0] == changes["WS-DAY"][1]
        assert changes["WS-INTEREST"] == ("0", "0")


# --------------------------------------------------------------------------
# 4. Loop with one-iteration case
# --------------------------------------------------------------------------


def test_one_iteration_case_is_derived():
    suite = extract_behavioral_tests(_bundle(INTEREST_ACCRUE))
    one_iter = [
        t
        for t in suite.tests
        if t.test_type == "loop_accumulator" and t.iteration_count == 1
    ]
    assert len(one_iter) == 1
    t = one_iter[0]
    changes = {s.field: s.to_value for s in t.expected_state_changes}
    assert changes["WS-DAY"] == "30"
    assert changes["WS-INTEREST"] == "3"


# --------------------------------------------------------------------------
# 5. Accumulator expected-value derivation is numerically correct
# --------------------------------------------------------------------------


def test_accumulator_expected_value_is_correct_not_fabricated():
    suite = extract_behavioral_tests(_bundle(INTEREST_ACCRUE))
    for t in suite.tests:
        if t.test_type != "loop_accumulator":
            continue
        by_field = {s.field: s for s in t.expected_state_changes}
        day_change = by_field["WS-DAY"]
        interest_change = by_field["WS-INTEREST"]
        # WS-INTEREST accrues +3 per day, from a starting value of 0
        expected_interest = 3 * t.iteration_count
        assert int(interest_change.to_value) == expected_interest
        assert (
            int(day_change.to_value) == int(day_change.from_value) + t.iteration_count
        )
        # outputs mirror the state changes
        out_by_name = {o.name: o.expected_value for o in t.expected_outputs}
        assert out_by_name["WS-INTEREST"] == interest_change.to_value


# --------------------------------------------------------------------------
# 6. Existing IF/ELSE behavior remains unchanged
# --------------------------------------------------------------------------


def test_existing_if_else_boundary_extraction_unchanged(
    if_else_bundle, combined_bundle
):
    for bundle in (if_else_bundle, combined_bundle):
        suite = extract_behavioral_tests(bundle)
        boundary_tests = [t for t in suite.tests if t.test_type == "boundary_partition"]
        assert (
            boundary_tests
        ), "the original #129 extractor must still produce its tests"
        for t in boundary_tests:
            assert t.iteration_count is None


def test_no_loops_means_no_loop_skips_recorded(if_else_bundle):
    suite = extract_behavioral_tests(if_else_bundle)
    assert suite.skipped_loops == ()


# --------------------------------------------------------------------------
# 7. Unsupported loop construct remains explicitly unsupported
# --------------------------------------------------------------------------


def test_loop_body_with_call_is_skipped_not_guessed():
    suite = extract_behavioral_tests(_bundle(LOOP_WITH_CALL))
    loop_tests = [t for t in suite.tests if t.test_type == "loop_accumulator"]
    assert loop_tests == []
    assert len(suite.skipped_loops) == 1
    assert "IRCall" in suite.skipped_loops[0].reason


# --------------------------------------------------------------------------
# 8. Parser-incomplete / unresolvable source does not become falsely verified
# --------------------------------------------------------------------------


def test_unresolvable_loop_bound_is_skipped_not_fabricated():
    suite = extract_behavioral_tests(_bundle(LOOP_UNRESOLVABLE_BOUND))
    loop_tests = [t for t in suite.tests if t.test_type == "loop_accumulator"]
    assert loop_tests == []
    assert len(suite.skipped_loops) == 1
    assert "WS-LIMIT" in suite.skipped_loops[0].reason


def test_parser_incomplete_source_never_marked_executable():
    """A source with real, pre-existing parser limitations (FILE SECTION /
    OPEN / READ) must never have any of its tests silently marked
    executable=True by the loop extractor."""
    from app.dataset.corpus import load_training_corpus

    records = {r.source_id: r for r in load_training_corpus()}
    bundle = _bundle(records["t_batch_acct_update"].source, "t_batch_acct_update")
    suite = extract_behavioral_tests(bundle)
    loop_tests = [t for t in suite.tests if t.test_type == "loop_accumulator"]
    assert loop_tests == []
    for t in suite.tests:
        assert t.executable is False or t.inconclusive_reason is None


# --------------------------------------------------------------------------
# Determinism (mirrors the existing #129 determinism guard)
# --------------------------------------------------------------------------


def test_loop_extraction_is_deterministic():
    a = extract_behavioral_tests(_bundle(LOAN_BALANCE, "DET"))
    b = extract_behavioral_tests(_bundle(LOAN_BALANCE, "DET"))
    assert [t.to_dict() for t in a.tests] == [t.to_dict() for t in b.tests]
    assert a.skipped_loops == b.skipped_loops
