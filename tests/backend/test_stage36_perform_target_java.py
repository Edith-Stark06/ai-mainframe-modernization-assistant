"""
Java backend tests for task #stage36 — ``PERFORM paragraph-name`` (and
``PERFORM ... THRU``) target-body outlining.

Purpose:
    Before this stage, every paragraph's instructions lived in one flat
    ``IRBasicBlock`` (task #109), and a ``PERFORM``-lowered ``IRCall``
    unconditionally got an *empty* stub method (``BE009``) plus, when the
    performing paragraph ended in ``STOP RUN``/``GOBACK`` before the
    target paragraph physically appeared in that flat list, the target's
    own instructions were separately marked unreachable and dropped
    (``BE011``) — so a real ``PERFORM`` target's body never reached
    generated Java at all, even though it was correctly represented in
    AST/IR/dependencies/CFG/risk (Stage 35's own finding).

    ``_paragraph_ranges``/``_local_perform_targets``/
    ``_collect_outlined_statements`` partition the same flat instruction
    list into contiguous per-paragraph index ranges (using the existing
    ``.paragraph`` tag, task #109, unchanged) and lower each target's own
    range — or, for ``PERFORM ... THRU``, the contiguous range spanning
    from the target paragraph's first instruction to the THRU paragraph's
    last — into a genuine ``private void`` method, reusing
    ``_emit_instruction_list`` (:func:`_collect_statements`'s own
    per-instruction dispatch loop, extracted, never duplicated) on that
    slice instead of the whole block.

    This path is mutually exclusive with the pre-existing ``GO TO``
    dispatcher (task #stage19): inert whenever a ``GO TO`` dispatch plan
    exists, since no real corpus source combines the two (confirmed
    during this stage's investigation — the corpus's one ``GO TO`` source,
    ``t_goto_spaghetti.cbl``, has zero ``PERFORM`` statements).

    Investigating this stage's own corpus regressions also found two
    pre-existing, independent bugs in ``CALL ... USING`` handling
    (comma-separated arguments corrupted into phantom operands; stub
    methods always declared with zero parameters regardless of the real
    call site's argument count) — both fixed here too, since real
    multi-argument external ``CALL``s had never previously reached
    compiled Java (always inside an always-stub paragraph) and would
    otherwise make this stage a net ``javac`` regression. See
    ``tests/parser/test_stage36_call_using_comma_fix.py`` for the parser
    half of the first fix.

Explicitly NOT covered here (out of this stage's scope):
    - ``PERFORM ... TIMES``, inline/recursive ``PERFORM``, or any other
      unevidenced ``PERFORM`` form (zero occurrences in the 45-source
      corpus).
    - Stage 34's ``PERFORM VARYING`` (self-contained inline body,
      unaffected by construction — see ``TestStage34Regression`` below).
    - A ``PERFORM`` target whose own body is entirely unsupported
      statements (e.g. ``READ``) — genuinely absent from the IR, so it
      correctly keeps the pre-existing ``BE009`` stub path (nothing to
      outline).

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
    "01 WS-A PIC 9(5).\n"
    "01 WS-B PIC 9(5).\n"
    "01 WS-CNT PIC 9(3).\n"
)


def _analyze(tmp_path: Path, body: str, header: str = _HEADER):
    path = tmp_path / "t.cbl"
    path.write_text(header + "PROCEDURE DIVISION.\n" + body, encoding="utf-8")
    return AnalysisService().analyze_file(path)


class TestPlainPerformOutlining:
    """tests/golden/perform_until.cbl's real shape, the dominant corpus
    form (97 of 98 real PERFORM-target occurrences)."""

    def test_target_body_is_emitted_not_stubbed(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    PERFORM SUB-PARA.\n"
            "    STOP RUN.\n"
            "SUB-PARA.\n"
            "    DISPLAY WS-CNT.\n",
        )
        assert not result.backend_diagnostics
        assert "private void subPara()" in result.java_source
        assert "System.out.println" in result.java_source
        assert "TODO" not in result.java_source

    def test_call_site_invokes_the_real_method(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    PERFORM SUB-PARA.\n"
            "    STOP RUN.\n"
            "SUB-PARA.\n"
            "    DISPLAY WS-CNT.\n",
        )
        run_method = result.java_source.split("public void run()")[1].split(
            "private void"
        )[0]
        assert "subPara();" in run_method

    def test_three_paragraphs_each_get_a_real_method(self, tmp_path: Path) -> None:
        """order_hierarchy.cbl's real shape: an entry paragraph performing
        three subordinate paragraphs in sequence, each with real logic."""
        result = _analyze(
            tmp_path,
            "0000-MAIN.\n"
            "    PERFORM 1000-FIRST\n"
            "    PERFORM 2000-SECOND\n"
            "    PERFORM 3000-THIRD\n"
            "    GOBACK.\n"
            "1000-FIRST.\n"
            "    MOVE 1 TO WS-A.\n"
            "2000-SECOND.\n"
            "    MOVE 2 TO WS-B.\n"
            "3000-THIRD.\n"
            "    COMPUTE WS-A = WS-A + WS-B.\n",
        )
        assert not result.backend_diagnostics
        java = result.java_source
        assert "private void f1000First()" in java
        assert "private void f2000Second()" in java
        assert "private void f3000Third()" in java
        assert "wsA = 1;" in java
        assert "wsB = 2;" in java
        assert "wsA = wsA + wsB;" in java  # task #stage35's COMPUTE, unaffected

    def test_nested_if_inside_outlined_paragraph_still_works(
        self, tmp_path: Path
    ) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    PERFORM SUB-PARA.\n"
            "    STOP RUN.\n"
            "SUB-PARA.\n"
            "    IF WS-A > 0\n"
            "        MOVE 1 TO WS-B\n"
            "    ELSE\n"
            "        MOVE 2 TO WS-B\n"
            "    END-IF.\n",
        )
        assert not result.backend_diagnostics
        java = result.java_source
        assert "private void subPara()" in java
        method = java.split("private void subPara()")[1]
        assert "if (wsA > 0)" in method
        assert "} else {" in method

    def test_paragraph_never_performed_is_not_outlined(self, tmp_path: Path) -> None:
        """A paragraph nobody PERFORMs is genuinely dead COBOL code -- it
        must stay absent (not fabricated), exactly like the pre-existing
        "never PERFORMed" handling elsewhere in the pipeline
        (app/behavioral/extraction/extractor.py, unchanged)."""
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n" "    STOP RUN.\n" "NEVER-CALLED.\n" "    MOVE 1 TO WS-A.\n",
        )
        assert "neverCalled" not in result.java_source


class TestPerformThruOutlining:
    """fallthrough_flow.cbl's real shape: the one evidenced ``PERFORM ...
    THRU`` occurrence in the 45-source corpus."""

    def test_thru_range_concatenates_into_one_method(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "0000-MAIN.\n"
            "    PERFORM 1000-ALPHA THRU 3000-GAMMA\n"
            "    MOVE 99 TO WS-A\n"
            "    GOBACK.\n"
            "1000-ALPHA.\n"
            "    MOVE 1 TO WS-A.\n"
            "2000-BETA.\n"
            "    MOVE 2 TO WS-B.\n"
            "3000-GAMMA.\n"
            "    ADD 1 TO WS-CNT.\n",
        )
        assert not result.backend_diagnostics
        java = result.java_source
        assert "private void f1000Alpha()" in java
        # 2000-BETA/3000-GAMMA are folded into 1000-ALPHA's own method, not
        # separately named -- COBOL's own THRU semantics (call 1000-ALPHA,
        # fall through the range, return once 3000-GAMMA completes).
        assert "private void f2000Beta()" not in java
        assert "private void f3000Gamma()" not in java
        method = java.split("private void f1000Alpha()")[1].split(
            "public static void main"
        )[0]
        assert "wsA = 1;" in method
        assert "wsB = 2;" in method
        assert "wsCnt += 1;" in method
        # after the THRU call returns, the caller's own next statement runs
        run_method = java.split("public void run()")[1].split("private void")[0]
        assert "f1000Alpha();" in run_method
        assert "wsA = 99;" in run_method


class TestStubbingStillAppliesWhenNothingToOutline:
    def test_external_call_still_stubbed(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n    CALL 'SUBPROG'.\n    STOP RUN.\n",
        )
        assert any(
            getattr(d, "code", "") == "BE009" for d in result.backend_diagnostics
        )
        assert "private void subprog()" in result.java_source
        assert "TODO" in result.java_source

    def test_perform_to_paragraph_with_only_unsupported_statements_still_stubbed(
        self, tmp_path: Path
    ) -> None:
        """A paragraph whose entire body is an unsupported statement (e.g.
        INITIALIZE) has zero IR instructions -- genuinely nothing to
        outline, so the pre-existing BE009 stub path still applies,
        correctly."""
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    PERFORM SUB-PARA.\n"
            "    STOP RUN.\n"
            "SUB-PARA.\n"
            "    INITIALIZE WS-A.\n",
        )
        assert any(
            getattr(d, "code", "") == "BE009" for d in result.backend_diagnostics
        )
        assert "private void subPara()" in result.java_source
        assert "TODO: implement CALL/PERFORM target 'SUB-PARA'" in result.java_source


class TestCallArityStubFix:
    """The second pre-existing bug this stage's own investigation found:
    a stub always had zero parameters regardless of the real call site's
    argument count."""

    def test_stub_gets_matching_parameter_count(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    CALL 'EXTSVC' USING WS-A, WS-B, WS-CNT.\n"
            "    STOP RUN.\n",
        )
        java = result.java_source
        assert "private void extsvc(Object arg0, Object arg1, Object arg2)" in java
        assert "extsvc(wsA, wsB, wsCnt);" in java

    def test_zero_argument_stub_unchanged(self, tmp_path: Path) -> None:
        """The pre-existing zero-argument case (tests/golden/call.java)
        must render exactly as before -- no empty parens regression."""
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n    CALL 'SUBPROG'.\n    STOP RUN.\n",
        )
        assert "private void subprog()" in result.java_source
        assert "private void subprog(" not in result.java_source.replace(
            "private void subprog()", ""
        )


class TestStage34Regression:
    """PERFORM VARYING's self-contained inline body (task #stage34) must
    be completely unaffected -- its body is never "elsewhere" in the flat
    list, so outlining never applies to it."""

    def test_perform_varying_still_inline_even_alongside_outlined_paragraphs(
        self, tmp_path: Path
    ) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    PERFORM SUB-PARA.\n"
            "    PERFORM VARYING WS-CNT FROM 1 BY 1 UNTIL WS-CNT > 3\n"
            "        ADD 1 TO WS-A\n"
            "    END-PERFORM\n"
            "    STOP RUN.\n"
            "SUB-PARA.\n"
            "    MOVE 1 TO WS-B.\n",
        )
        assert not result.backend_diagnostics
        run_method = result.java_source.split("public void run()")[1].split(
            "private void"
        )[0]
        assert "for (wsCnt = 1; wsCnt <= 3; wsCnt += 1) {" in run_method
        assert "subPara();" in run_method


class TestStage35Regression:
    """COMPUTE (task #stage35) inside an outlined paragraph must lower
    exactly as it does at the top level -- already exercised in
    TestPlainPerformOutlining above; this locks in the specific
    subscripted/PERFORM-VARYING-body interaction table_indexed.cbl's real
    shape needs."""

    def test_compute_inside_perform_varying_inside_outlined_paragraph(
        self, tmp_path: Path
    ) -> None:
        header = (
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. T.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-I PIC 9(2).\n"
            "01 WS-ITEM PIC 9(3) OCCURS 3.\n"
            "01 WS-TOTAL PIC 9(5).\n"
        )
        result = _analyze(
            tmp_path,
            "0000-MAIN.\n"
            "    PERFORM 1000-SUM\n"
            "    GOBACK.\n"
            "1000-SUM.\n"
            "    PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > 3\n"
            "        COMPUTE WS-TOTAL = WS-TOTAL + WS-ITEM(WS-I)\n"
            "    END-PERFORM.\n",
            header,
        )
        assert not result.backend_diagnostics
        method = result.java_source.split("private void f1000Sum()")[1]
        assert "wsTotal = wsTotal + wsItem[wsI - 1];" in method


class TestMalformedPerformStillFailsCleanly:
    def test_perform_to_undefined_paragraph_still_stubbed_with_be009(
        self, tmp_path: Path
    ) -> None:
        """A PERFORM to a name that resolves to no local paragraph and no
        external sub-program is left exactly as before -- BE009, empty
        stub, never fabricated."""
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n    PERFORM NONEXISTENT-PARA.\n    STOP RUN.\n",
        )
        assert any(
            getattr(d, "code", "") == "BE009" for d in result.backend_diagnostics
        )
        assert "TODO: implement CALL/PERFORM target 'NONEXISTENT-PARA'" in (
            result.java_source
        )


class TestRuntimeExecution:
    """javac success alone does not prove the outlined body actually
    executes -- these actually run the generated program."""

    def test_outlined_target_body_actually_executes(self, tmp_path: Path) -> None:
        header = (
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. TEXE.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-TOTAL PIC 9(5) VALUE 0.\n"
        )
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    PERFORM ADD-TEN\n"
            "    PERFORM ADD-TEN\n"
            "    DISPLAY WS-TOTAL\n"
            "    STOP RUN.\n"
            "ADD-TEN.\n"
            "    ADD 10 TO WS-TOTAL.\n",
            header,
        )
        assert not result.backend_diagnostics
        java_file = tmp_path / "Texe.java"
        java_file.write_text(result.java_source, encoding="utf-8")

        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr

        run = subprocess.run(
            ["java", "-cp", str(tmp_path), "Texe"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert run.returncode == 0, run.stderr
        # ADD-TEN performed twice: 10 + 10 = 20, zero-padded to PIC 9(5).
        assert run.stdout.strip() == "00020"

    def test_thru_range_actually_executes_in_order(self, tmp_path: Path) -> None:
        header = (
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. TEXE2.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-RESULT PIC 9(5) VALUE 0.\n"
        )
        result = _analyze(
            tmp_path,
            "0000-MAIN.\n"
            "    PERFORM 1000-SET THRU 3000-MULTIPLY\n"
            "    DISPLAY WS-RESULT\n"
            "    GOBACK.\n"
            "1000-SET.\n"
            "    MOVE 5 TO WS-RESULT.\n"
            "2000-ADD.\n"
            "    ADD 3 TO WS-RESULT.\n"
            "3000-MULTIPLY.\n"
            "    MULTIPLY 2 BY WS-RESULT.\n",
            header,
        )
        assert not result.backend_diagnostics
        java_file = tmp_path / "Texe2.java"
        java_file.write_text(result.java_source, encoding="utf-8")

        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr

        run = subprocess.run(
            ["java", "-cp", str(tmp_path), "Texe2"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert run.returncode == 0, run.stderr
        # (5 + 3) * 2 = 16, zero-padded to PIC 9(5) -- proves 1000/2000/3000
        # ran in order, in one PERFORM, not just that *something* compiled.
        assert run.stdout.strip() == "00016"
