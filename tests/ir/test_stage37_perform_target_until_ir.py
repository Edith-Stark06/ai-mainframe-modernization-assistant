"""
IR tests for task #stage37 — ``PerformTargetUntilStatementNode`` ->
``IRPerformUntil``/``IRCall``/``IREndPerform`` lowering.

Purpose:
    ``IRBuilder.build_perform_target_until_statement`` lowers an
    out-of-line ``PERFORM paragraph-name UNTIL condition`` into the
    identical ``IRPerformUntil``/``IREndPerform`` loop-marker pair
    :meth:`~app.ir.builder.IRBuilder.build_perform_until_statement`
    already emits for the *inline* form, with a single
    ``IRCall(comment="PERFORM")`` in between standing in for the loop
    body — the exact same ``IRCall`` shape
    :meth:`~app.ir.builder.IRBuilder.build_perform_statement` already
    produces for a plain ``PERFORM``, so Stage 36's paragraph-outlining
    scan (keyed on that ``comment="PERFORM"`` tag) recognises the target
    identically whether it is performed at the top level or inside this
    loop. The target paragraph's own instructions are never duplicated
    into the loop body — only a reference to it.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.service import AnalysisService
from app.ir.instructions import IRCall, IRDisplay, IREndPerform, IRPerformUntil

_HEADER = (
    "IDENTIFICATION DIVISION.\n"
    "PROGRAM-ID. T.\n"
    "DATA DIVISION.\n"
    "WORKING-STORAGE SECTION.\n"
    "01 WS-EOF PIC X(1) VALUE SPACE.\n"
)


def _analyze(tmp_path: Path, body: str, header: str = _HEADER):
    path = tmp_path / "t.cbl"
    path.write_text(
        header + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + body, encoding="utf-8"
    )
    return AnalysisService().analyze_file(path)


def _instructions(result):
    return result.ir.modules[0].functions[0].blocks[0].instructions


_BODY = (
    "    PERFORM 2000-PROCESS-RECORDS UNTIL WS-EOF = 'Y'.\n"
    "    GOBACK.\n"
    "2000-PROCESS-RECORDS.\n"
    "    DISPLAY 'X'.\n"
)


class TestLoopMarkerPair:
    def test_irperformuntil_is_produced(self, tmp_path: Path) -> None:
        result = _analyze(tmp_path, _BODY)
        loops = [i for i in _instructions(result) if isinstance(i, IRPerformUntil)]
        assert len(loops) == 1

    def test_closed_by_irendperform(self, tmp_path: Path) -> None:
        result = _analyze(tmp_path, _BODY)
        ends = [i for i in _instructions(result) if isinstance(i, IREndPerform)]
        assert len(ends) == 1

    def test_condition_fields(self, tmp_path: Path) -> None:
        result = _analyze(tmp_path, _BODY)
        (loop,) = [i for i in _instructions(result) if isinstance(i, IRPerformUntil)]
        assert loop.left == "WS-EOF"
        assert loop.operator == "="
        assert loop.right == "'Y'"


class TestLoopBodyIsACallNotADuplicate:
    def test_body_is_a_single_ircall_tagged_perform(self, tmp_path: Path) -> None:
        instrs = _instructions(_analyze(tmp_path, _BODY))
        open_idx = next(
            i for i, x in enumerate(instrs) if isinstance(x, IRPerformUntil)
        )
        close_idx = next(i for i, x in enumerate(instrs) if isinstance(x, IREndPerform))
        body = instrs[open_idx + 1 : close_idx]
        assert len(body) == 1
        assert isinstance(body[0], IRCall)
        assert body[0].comment == "PERFORM"
        assert body[0].target == "2000-PROCESS-RECORDS"

    def test_target_paragraphs_own_instructions_are_not_inside_the_loop(
        self, tmp_path: Path
    ) -> None:
        """The target's own DISPLAY must appear exactly once in the flat
        block -- as part of its own paragraph range -- never copied
        again between IRPerformUntil and IREndPerform."""
        instrs = _instructions(_analyze(tmp_path, _BODY))
        displays = [i for i in instrs if isinstance(i, IRDisplay)]
        assert len(displays) == 1
        open_idx = next(
            i for i, x in enumerate(instrs) if isinstance(x, IRPerformUntil)
        )
        close_idx = next(i for i, x in enumerate(instrs) if isinstance(x, IREndPerform))
        assert not any(
            isinstance(x, IRDisplay) for x in instrs[open_idx + 1 : close_idx]
        )

    def test_target_paragraph_tag_is_the_entry_paragraph_not_the_target(
        self, tmp_path: Path
    ) -> None:
        """The loop-marker instructions belong to the performing
        paragraph (MAIN-PARA), not the target -- task #109's
        ``.paragraph`` tagging is unaffected by this new lowering."""
        instrs = _instructions(_analyze(tmp_path, _BODY))
        (loop,) = [i for i in instrs if isinstance(i, IRPerformUntil)]
        assert (loop.paragraph or "").upper() == "MAIN-PARA"


class TestNoIRPerformVaryingConfusion:
    def test_lowering_uses_irperformuntil_not_irperformvarying(
        self, tmp_path: Path
    ) -> None:
        from app.ir.instructions import IRPerformVarying

        instrs = _instructions(_analyze(tmp_path, _BODY))
        assert not any(isinstance(i, IRPerformVarying) for i in instrs)


class TestScalarRegression:
    def test_inline_perform_until_ir_unaffected(self, tmp_path: Path) -> None:
        """The pre-existing inline PERFORM UNTIL...END-PERFORM lowering
        (Stage 34's own sibling path) must stay untouched: its body is
        still the literal recursively-lowered statement list, not an
        IRCall."""
        result = _analyze(
            tmp_path,
            "    PERFORM UNTIL WS-EOF = 'Y'\n"
            "        DISPLAY 'X'\n"
            "    END-PERFORM.\n    GOBACK.\n",
        )
        instrs = _instructions(result)
        open_idx = next(
            i for i, x in enumerate(instrs) if isinstance(x, IRPerformUntil)
        )
        close_idx = next(i for i, x in enumerate(instrs) if isinstance(x, IREndPerform))
        body = instrs[open_idx + 1 : close_idx]
        assert len(body) == 1
        assert isinstance(body[0], IRDisplay)

    def test_plain_perform_ir_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "    PERFORM SUB-PARA.\n    GOBACK.\nSUB-PARA.\n    DISPLAY 'X'.\n",
        )
        instrs = _instructions(result)
        calls = [i for i in instrs if isinstance(i, IRCall)]
        assert len(calls) == 1
        assert calls[0].comment == "PERFORM"
        assert not any(isinstance(i, IRPerformUntil) for i in instrs)
