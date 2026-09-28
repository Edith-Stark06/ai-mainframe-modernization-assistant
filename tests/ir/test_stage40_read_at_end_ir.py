"""
IR tests for task #stage40 — ``ReadStatementNode`` lowering.

Purpose:
    ``IRBuilder.build_read_statement`` lowers only ``at_end_statements``,
    each via the ordinary ``_translate_statement`` dispatch in sequence
    -- no new IR instruction type, and no ``IRIf``/branch marker either:
    this backend models every ``READ`` as always reaching end-of-file (no
    file-reading runtime exists -- task #stage40's own explicit scope
    decision), so the ``AT END`` statements are the only ones ever
    reachable, unconditionally. ``not_at_end_statements`` is never
    lowered -- confirmed directly here, not just documented.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.service import AnalysisService
from app.ir.instructions import IRAdd, IRMove

_HEADER = (
    "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nDATA DIVISION.\n"
    "WORKING-STORAGE SECTION.\n"
    "01 WS-EOF PIC X(1) VALUE 'N'.\n"
    "01 WS-COUNT PIC 9(3) VALUE 0.\n"
)


def _analyze(tmp_path: Path, body: str, header: str = _HEADER):
    path = tmp_path / "t.cbl"
    path.write_text(
        header + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body, encoding="utf-8"
    )
    return AnalysisService().analyze_file(path)


def _instructions(result):
    return result.ir.modules[0].functions[0].blocks[0].instructions


class TestAtEndIsLoweredUnconditionally:
    def test_at_end_move_becomes_a_real_irmove(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n    END-READ.\n    STOP RUN.\n",
        )
        moves = [i for i in _instructions(result) if isinstance(i, IRMove)]
        assert len(moves) == 1
        assert moves[0].result == "WS-EOF"
        assert moves[0].source == "'Y'"

    def test_no_irif_or_branch_marker_wraps_it(self, tmp_path: Path) -> None:
        """This backend has no condition to branch on -- READ always
        reaches end-of-file, so the AT END statements are emitted flat,
        never inside an IRIf/IREndIf pair."""
        from app.ir.instructions import IRIf

        result = _analyze(
            tmp_path,
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n    END-READ.\n    STOP RUN.\n",
        )
        assert not any(isinstance(i, IRIf) for i in _instructions(result))

    def test_multiple_at_end_statements_all_lower_in_order(
        self, tmp_path: Path
    ) -> None:
        result = _analyze(
            tmp_path,
            "    READ F1\n"
            "        AT END MOVE 'Y' TO WS-EOF\n"
            "                ADD 1 TO WS-COUNT\n"
            "    END-READ.\n    STOP RUN.\n",
        )
        instrs = [i for i in _instructions(result) if isinstance(i, (IRMove, IRAdd))]
        assert len(instrs) == 2
        assert isinstance(instrs[0], IRMove)
        assert isinstance(instrs[1], IRAdd)


class TestNotAtEndIsNeverLowered:
    def test_not_at_end_statement_produces_no_ir(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    READ F1 NOT AT END ADD 1 TO WS-COUNT\n    END-READ.\n    STOP RUN.\n",
        )
        assert not any(isinstance(i, IRAdd) for i in _instructions(result))

    def test_at_end_and_not_at_end_together_only_at_end_lowers(
        self, tmp_path: Path
    ) -> None:
        """The real corpus shape (t_batch_acct_update): AT END's MOVE
        becomes real IR; NOT AT END's ADD does not."""
        result = _analyze(
            tmp_path,
            "    READ F1 INTO R\n"
            "        AT END MOVE 'Y' TO WS-EOF\n"
            "        NOT AT END ADD 1 TO WS-COUNT\n"
            "    END-READ.\n    STOP RUN.\n",
        )
        instrs = _instructions(result)
        moves = [i for i in instrs if isinstance(i, IRMove)]
        adds = [i for i in instrs if isinstance(i, IRAdd)]
        assert len(moves) == 1
        assert moves[0].result == "WS-EOF"
        assert adds == []


class TestReadItselfProducesNoInstruction:
    def test_bare_read_no_clause_produces_no_instruction(self, tmp_path: Path) -> None:
        result = _analyze(tmp_path, "    READ F1.\n    STOP RUN.\n")
        instrs = _instructions(result)
        # Only the STOP RUN (IRReturn) should be present.
        from app.ir.instructions import IRReturn

        assert [type(i).__name__ for i in instrs] == [IRReturn.__name__]

    def test_into_target_not_represented_in_ir(self, tmp_path: Path) -> None:
        """No file-content source exists to assign it from -- leaving it
        unmentioned, not fabricating a value."""
        result = _analyze(tmp_path, "    READ F1 INTO WS-COUNT.\n    STOP RUN.\n")
        assert not any(isinstance(i, IRMove) for i in _instructions(result))


class TestRealCorpusIntegration:
    """The confirmed, previously infinite-looping sources: the loop's own
    exit-flag assignment must now be real IR."""

    def test_daily_trans_report_loop_flag_write_exists(self, tmp_path: Path) -> None:
        result = AnalysisService().analyze_file(
            Path("data/sources/phase6-v2/daily_trans_report.cbl")
        )
        instrs = result.ir.modules[0].functions[0].blocks[0].instructions
        moves = [i for i in instrs if isinstance(i, IRMove) and i.result == "WS-EOF"]
        assert len(moves) >= 1

    def test_batch_acct_update_loop_flag_write_exists_and_not_at_end_absent(
        self, tmp_path: Path
    ) -> None:
        result = AnalysisService().analyze_file(
            Path("data/sources/phase6-v2/batch_acct_update.cbl")
        )
        instrs = result.ir.modules[0].functions[0].blocks[0].instructions
        eof_moves = [
            i for i in instrs if isinstance(i, IRMove) and i.result == "WS-EOF-FLAG"
        ]
        assert len(eof_moves) >= 1
        records_read_adds = [
            i for i in instrs if isinstance(i, IRAdd) and i.right == "WS-RECORDS-READ"
        ]
        assert records_read_adds == []


class TestScalarRegression:
    def test_if_statement_ir_unaffected(self, tmp_path: Path) -> None:
        from app.ir.instructions import IRIf

        result = _analyze(
            tmp_path,
            "    IF WS-COUNT > 0\n        MOVE 'Y' TO WS-EOF\n    END-IF.\n    STOP RUN.\n",
        )
        assert any(isinstance(i, IRIf) for i in _instructions(result))
