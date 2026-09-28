"""
Java backend + integration tests for task #stage40 — ``READ ... AT END``
control flow.

Purpose:
    No changes were needed in ``app/backend/java/*.py`` for this stage:
    ``at_end_statements`` lower to ordinary IR instructions
    (``IRMove``/``IRAdd``/...) via the existing ``_translate_statement``
    dispatch, and the existing Java emitters already know how to render
    those. These tests exist to prove that composition holds and, most
    importantly, that the confirmed infinite-loop bug (Stage 40's own
    discovery finding) is actually fixed at runtime for all four real
    corpus sources -- not just that the generated Java *looks* right.

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
    "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nDATA DIVISION.\n"
    "WORKING-STORAGE SECTION.\n"
    "01 WS-EOF PIC X(1) VALUE 'N'.\n"
    "01 WS-COUNT PIC 9(3) VALUE 0.\n"
)


def _analyze(tmp_path: Path, body: str, header: str = _HEADER):
    path = tmp_path / "t.cbl"
    path.write_text(header + "PROCEDURE DIVISION.\n" + body, encoding="utf-8")
    return AnalysisService().analyze_file(path)


class TestJavaGeneration:
    def test_no_diagnostics(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n    END-READ.\n    STOP RUN.\n",
        )
        assert not result.backend_diagnostics

    def test_generated_java_contains_the_at_end_assignment(
        self, tmp_path: Path
    ) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n    END-READ.\n    STOP RUN.\n",
        )
        assert 'wsEof = "Y";' in result.java_source

    def test_not_at_end_statement_absent_from_java(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    READ F1 NOT AT END ADD 1 TO WS-COUNT\n    END-READ.\n    STOP RUN.\n",
        )
        assert "wsCount += 1" not in result.java_source

    def test_generated_java_compiles(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n    END-READ.\n    STOP RUN.\n",
        )
        java_file = tmp_path / "T.java"
        java_file.write_text(result.java_source, encoding="utf-8")
        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr


class TestRegressionOtherStatements:
    def test_plain_if_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    IF WS-COUNT > 0\n        MOVE 'Y' TO WS-EOF\n    END-IF.\n    STOP RUN.\n",
        )
        assert not result.backend_diagnostics
        assert "if (wsCount > 0) {" in result.java_source

    def test_perform_target_until_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "MAIN-PARA.\n"
            "    PERFORM SUB-PARA UNTIL WS-EOF = 'Y'.\n"
            "    GOBACK.\n"
            "SUB-PARA.\n"
            "    ADD 1 TO WS-COUNT.\n",
        )
        assert not result.backend_diagnostics
        assert 'while (!(_cobolEquals(wsEof, "Y"))) {' in result.java_source


class TestRuntimeExecution:
    """javac success alone does not prove the loop actually terminates --
    these actually run the generated program."""

    def test_read_at_end_loop_terminates(self, tmp_path: Path) -> None:
        header = (
            "IDENTIFICATION DIVISION.\nPROGRAM-ID. TEXE7.\nDATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-EOF PIC X(1) VALUE 'N'.\n"
            "01 WS-COUNT PIC 9(3) VALUE 0.\n"
        )
        source = (
            header + "PROCEDURE DIVISION.\n"
            "MAIN-PARA.\n"
            "    PERFORM READ-PARA UNTIL WS-EOF = 'Y'.\n"
            "    DISPLAY WS-COUNT.\n"
            "    STOP RUN.\n"
            "READ-PARA.\n"
            "    READ F1 AT END MOVE 'Y' TO WS-EOF.\n"
            "    ADD 1 TO WS-COUNT.\n"
        )
        path = tmp_path / "t.cbl"
        path.write_text(source, encoding="utf-8")
        result = AnalysisService().analyze_file(path)
        assert not result.backend_diagnostics

        java_file = tmp_path / "Texe7.java"
        java_file.write_text(result.java_source, encoding="utf-8")
        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr

        run = subprocess.run(
            ["java", "-cp", str(tmp_path), "Texe7"],
            capture_output=True,
            text=True,
            timeout=15,  # a hang here would previously have been infinite
        )
        assert run.returncode == 0, run.stderr
        # READ-PARA runs exactly once: WS-EOF becomes 'Y' unconditionally
        # on the first call, so the loop exits after incrementing WS-COUNT
        # exactly once.
        assert run.stdout.strip() == "001"


class TestRealCorpusIntegration:
    """Direct integration against the four real, unmodified corpus
    sources this stage exists to fix."""

    _SOURCES = [
        ("batch_acct_update.cbl", "Btacup01"),
        ("daily_trans_report.cbl", "Dlytrp01"),
        ("inventory_extract.cbl", "Invext01"),
        ("payroll_file_post.cbl", "Paypst01"),
    ]

    def test_no_syn100_for_read_in_any_source(self) -> None:
        for filename, _ in self._SOURCES:
            result = AnalysisService().analyze_file(
                Path(f"data/sources/phase6-v2/{filename}")
            )
            read_syn100 = [
                d
                for d in result.syntax_diagnostics
                if d.code == "SYN100" and "READ" in d.message.upper()
            ]
            assert read_syn100 == [], filename

    def test_all_four_sources_compile_and_terminate(self, tmp_path: Path) -> None:
        for filename, class_name in self._SOURCES:
            result = AnalysisService().analyze_file(
                Path(f"data/sources/phase6-v2/{filename}")
            )
            assert not [
                d for d in result.backend_diagnostics if d.code != "BE009"
            ], filename

            java_file = tmp_path / f"{class_name}.java"
            java_file.write_text(result.java_source, encoding="utf-8")
            javac = subprocess.run(
                ["javac", "-d", str(tmp_path), str(java_file)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert javac.returncode == 0, (filename, javac.stderr)

            run = subprocess.run(
                ["java", "-cp", str(tmp_path), class_name],
                capture_output=True,
                text=True,
                timeout=15,  # a hang here is exactly the bug this stage fixes
            )
            assert run.returncode == 0, (filename, run.stderr)

    def test_javac_now_succeeds_for_the_formerly_known_unrelated_issue(
        self, tmp_path: Path
    ) -> None:
        """task #stage42: this source's own, pre-existing, unrelated
        ``COMPUTE`` narrowing bug (a ``double``-valued expression assigned
        to an ``int`` field) is now fixed with an explicit ``(int)`` cast
        -- see ``tests/backend/test_stage42_compute_narrowing_cast.py``
        for the dedicated tests. Unaffected by Stage 40's own READ fix
        either way; kept here, updated, as a regression anchor since this
        exact source/test pairing predates the fix."""
        result = AnalysisService().analyze_file(
            Path("data/sources/phase6-v2/inventory_reorder.cbl")
        )
        java_file = tmp_path / "Invro01.java"
        java_file.write_text(result.java_source, encoding="utf-8")
        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert javac.returncode == 0, javac.stderr
