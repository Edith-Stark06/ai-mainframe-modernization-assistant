"""
Tests for :class:`~app.modernization.cloud.analyzer.CloudReadinessAnalyzer`
(task #stage48) — every tier assertion checks its cited evidence too.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import textwrap

from app.modernization.cloud.analyzer import CloudReadinessAnalyzer
from app.modernization.cloud.models import CloudReadinessTier
from app.modernization.flow.generator import generate_flow
from app.modernization.risk.analyzer import RiskAnalyzer

_HEADER = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 0.
       PROCEDURE DIVISION.
"""


def _assess(analyze, body: str):
    src = _HEADER + textwrap.dedent(body)
    ar = analyze(src)
    flow = generate_flow(ar)
    risks = RiskAnalyzer().analyze(ar, flow, [])
    return src, CloudReadinessAnalyzer().analyze(src, ar, risks)


class TestCloudReady:
    def test_trivial_program_is_cloud_ready(self, analyze) -> None:
        _, assessment = _assess(
            analyze, "MAIN-PARA.\n    MOVE 1 TO WS-A.\n    STOP RUN.\n"
        )
        assert assessment.tier is CloudReadinessTier.CLOUD_READY
        assert assessment.evidence

    def test_cloud_ready_has_no_cics_sql_dli_vsam_evidence(self, analyze) -> None:
        _, assessment = _assess(
            analyze, "MAIN-PARA.\n    MOVE 1 TO WS-A.\n    STOP RUN.\n"
        )
        joined = " ".join(assessment.evidence).upper()
        assert "EXEC" not in joined or "NO EXEC" in joined

    def test_one_or_two_external_calls_still_cloud_ready(self, analyze) -> None:
        """External CALL alone only escalates at 3+ (see
        ``_rule_needs_refactoring``) -- 1-2 calls are an ordinary,
        portable integration surface."""
        _, assessment = _assess(
            analyze,
            "MAIN-PARA.\n" "    CALL 'SUB1'.\n" "    CALL 'SUB2'.\n" "    STOP RUN.\n",
        )
        assert assessment.tier is CloudReadinessTier.CLOUD_READY


class TestNeedsRefactoring:
    def test_exec_sql_triggers_needs_refactoring(self, analyze) -> None:
        _, assessment = _assess(
            analyze,
            "MAIN-PARA.\n"
            "    EXEC SQL\n"
            "        SELECT COL INTO :WS-A FROM TBL\n"
            "    END-EXEC.\n"
            "    STOP RUN.\n",
        )
        assert assessment.tier is CloudReadinessTier.NEEDS_REFACTORING
        assert any("EXEC SQL" in e for e in assessment.evidence)

    def test_three_external_calls_triggers_needs_refactoring(self, analyze) -> None:
        _, assessment = _assess(
            analyze,
            "MAIN-PARA.\n"
            "    CALL 'SUB1'.\n"
            "    CALL 'SUB2'.\n"
            "    CALL 'SUB3'.\n"
            "    STOP RUN.\n",
        )
        assert assessment.tier is CloudReadinessTier.NEEDS_REFACTORING
        assert any("external CALL" in e for e in assessment.evidence)

    def test_single_vsam_indicator_triggers_needs_refactoring(self, analyze) -> None:
        src = (
            "       IDENTIFICATION DIVISION.\n"
            "       PROGRAM-ID. T.\n"
            "       ENVIRONMENT DIVISION.\n"
            "       INPUT-OUTPUT SECTION.\n"
            "       FILE-CONTROL.\n"
            "           SELECT F1 ASSIGN TO DISK\n"
            "               ORGANIZATION IS INDEXED.\n"
            "       DATA DIVISION.\n"
            "       WORKING-STORAGE SECTION.\n"
            "       01 WS-A PIC 9(5) VALUE 0.\n"
            "       PROCEDURE DIVISION.\n"
            "       MAIN-PARA.\n"
            "           STOP RUN.\n"
        )
        ar = analyze(src)
        flow = generate_flow(ar)
        risks = RiskAnalyzer().analyze(ar, flow, [])
        assessment = CloudReadinessAnalyzer().analyze(src, ar, risks)
        assert assessment.tier is CloudReadinessTier.NEEDS_REFACTORING
        assert any("VSAM" in e for e in assessment.evidence)

    def test_exec_sql_evidence_cites_line_number(self, analyze) -> None:
        src, assessment = _assess(
            analyze,
            "MAIN-PARA.\n"
            "    EXEC SQL\n"
            "        SELECT COL INTO :WS-A FROM TBL\n"
            "    END-EXEC.\n"
            "    STOP RUN.\n",
        )
        exec_sql_line = next(
            i for i, ln in enumerate(src.splitlines(), start=1) if "EXEC SQL" in ln
        )
        assert any(str(exec_sql_line) in e for e in assessment.evidence)


class TestRequiresRearchitecture:
    def test_exec_cics_triggers_requires_rearchitecture(self, analyze) -> None:
        _, assessment = _assess(
            analyze,
            "MAIN-PARA.\n"
            "    EXEC CICS\n"
            "        SEND MAP('MYMAP')\n"
            "    END-EXEC.\n"
            "    STOP RUN.\n",
        )
        assert assessment.tier is CloudReadinessTier.REQUIRES_REARCHITECTURE
        assert any("EXEC CICS" in e for e in assessment.evidence)

    def test_single_exec_dli_triggers_requires_rearchitecture(self, analyze) -> None:
        _, assessment = _assess(
            analyze,
            "MAIN-PARA.\n"
            "    EXEC DLI\n"
            "        GET UNIQUE SEGMENT\n"
            "    END-EXEC.\n"
            "    STOP RUN.\n",
        )
        assert assessment.tier is CloudReadinessTier.REQUIRES_REARCHITECTURE
        assert any("EXEC DLI" in e for e in assessment.evidence)

    def test_single_call_cbltdli_triggers_requires_rearchitecture(
        self, analyze
    ) -> None:
        """``CALL 'CBLTDLI'`` is COBOL's standard DL/I call interface --
        as unambiguous an IMS signal as ``EXEC DLI...END-EXEC``."""
        _, assessment = _assess(
            analyze,
            "MAIN-PARA.\n" "    CALL 'CBLTDLI' USING WS-A.\n" "    STOP RUN.\n",
        )
        assert assessment.tier is CloudReadinessTier.REQUIRES_REARCHITECTURE
        assert any("CBLTDLI" in e for e in assessment.evidence)

    def test_two_vsam_indicators_triggers_requires_rearchitecture(
        self, analyze
    ) -> None:
        src = (
            "       IDENTIFICATION DIVISION.\n"
            "       PROGRAM-ID. T.\n"
            "       ENVIRONMENT DIVISION.\n"
            "       INPUT-OUTPUT SECTION.\n"
            "       FILE-CONTROL.\n"
            "           SELECT F1 ASSIGN TO DISK\n"
            "               ORGANIZATION IS INDEXED\n"
            "               ACCESS MODE IS DYNAMIC.\n"
            "       DATA DIVISION.\n"
            "       WORKING-STORAGE SECTION.\n"
            "       01 WS-A PIC 9(5) VALUE 0.\n"
            "       PROCEDURE DIVISION.\n"
            "       MAIN-PARA.\n"
            "           STOP RUN.\n"
        )
        ar = analyze(src)
        flow = generate_flow(ar)
        risks = RiskAnalyzer().analyze(ar, flow, [])
        assessment = CloudReadinessAnalyzer().analyze(src, ar, risks)
        assert assessment.tier is CloudReadinessTier.REQUIRES_REARCHITECTURE


class TestNotRecommended:
    def test_cics_and_dli_together_triggers_not_recommended(self, analyze) -> None:
        _, assessment = _assess(
            analyze,
            "MAIN-PARA.\n"
            "    EXEC CICS\n"
            "        SEND MAP('MYMAP')\n"
            "    END-EXEC.\n"
            "    EXEC DLI\n"
            "        GET UNIQUE SEGMENT\n"
            "    END-EXEC.\n"
            "    STOP RUN.\n",
        )
        assert assessment.tier is CloudReadinessTier.NOT_RECOMMENDED
        joined = " ".join(assessment.evidence)
        assert "EXEC CICS" in joined and "EXEC DLI" in joined

    def test_three_or_more_exec_dli_triggers_not_recommended_alone(
        self, analyze
    ) -> None:
        _, assessment = _assess(
            analyze,
            "MAIN-PARA.\n"
            "    EXEC DLI\n        GET UNIQUE A\n    END-EXEC.\n"
            "    EXEC DLI\n        GET UNIQUE B\n    END-EXEC.\n"
            "    EXEC DLI\n        GET UNIQUE C\n    END-EXEC.\n"
            "    STOP RUN.\n",
        )
        assert assessment.tier is CloudReadinessTier.NOT_RECOMMENDED

    def test_cics_and_call_cbltdli_together_triggers_not_recommended(
        self, analyze
    ) -> None:
        """The two DL/I forms (``EXEC DLI`` and ``CALL 'CBLTDLI'``) are
        equivalent evidence -- CICS plus either one must combine the
        same way."""
        _, assessment = _assess(
            analyze,
            "MAIN-PARA.\n"
            "    EXEC CICS\n"
            "        SEND MAP('MYMAP')\n"
            "    END-EXEC.\n"
            "    CALL 'CBLTDLI' USING WS-A.\n"
            "    STOP RUN.\n",
        )
        assert assessment.tier is CloudReadinessTier.NOT_RECOMMENDED
        joined = " ".join(assessment.evidence)
        assert "EXEC CICS" in joined and "CBLTDLI" in joined

    def test_mixed_dli_forms_combine_toward_not_recommended(self, analyze) -> None:
        """Two ``EXEC DLI`` occurrences plus one ``CALL 'CBLTDLI'`` is
        three total IMS/DL-I signals -- the same threshold three
        ``EXEC DLI``-only occurrences trigger, since the two forms are
        counted together."""
        _, assessment = _assess(
            analyze,
            "MAIN-PARA.\n"
            "    EXEC DLI\n        GET UNIQUE A\n    END-EXEC.\n"
            "    EXEC DLI\n        GET UNIQUE B\n    END-EXEC.\n"
            "    CALL 'CBLTDLI' USING WS-A.\n"
            "    STOP RUN.\n",
        )
        assert assessment.tier is CloudReadinessTier.NOT_RECOMMENDED

    def test_not_recommended_takes_precedence_over_needs_refactoring(
        self, analyze
    ) -> None:
        """A program with EXEC SQL *and* both CICS+DLI must land on the
        most severe applicable tier, not the mildest."""
        _, assessment = _assess(
            analyze,
            "MAIN-PARA.\n"
            "    EXEC SQL\n        SELECT COL INTO :WS-A FROM TBL\n    END-EXEC.\n"
            "    EXEC CICS\n        SEND MAP('MYMAP')\n    END-EXEC.\n"
            "    EXEC DLI\n        GET UNIQUE SEGMENT\n    END-EXEC.\n"
            "    STOP RUN.\n",
        )
        assert assessment.tier is CloudReadinessTier.NOT_RECOMMENDED


class TestNeverCrashesOrFabricates:
    def test_none_risks_is_treated_as_no_critical_risk(self, analyze) -> None:
        src = _HEADER + "MAIN-PARA.\n    MOVE 1 TO WS-A.\n    STOP RUN.\n"
        ar = analyze(src)
        assessment = CloudReadinessAnalyzer().analyze(src, ar, None)
        assert assessment.tier is CloudReadinessTier.CLOUD_READY

    def test_assessment_always_has_rationale_and_evidence(self, analyze) -> None:
        for body in (
            "MAIN-PARA.\n    STOP RUN.\n",
            "MAIN-PARA.\n    EXEC SQL\n        X\n    END-EXEC.\n    STOP RUN.\n",
        ):
            _, assessment = _assess(analyze, body)
            assert assessment.rationale.strip()
            assert assessment.evidence
            assert 0.0 <= assessment.confidence <= 1.0

    def test_to_dict_is_json_safe(self, analyze) -> None:
        _, assessment = _assess(analyze, "MAIN-PARA.\n    STOP RUN.\n")
        d = assessment.to_dict()
        assert d["tier"] == "CLOUD_READY"
        assert isinstance(d["evidence"], list)
