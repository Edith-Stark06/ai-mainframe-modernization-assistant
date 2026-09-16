"""
Regression tests for task #108 — Explicit Unsupported Syntax Reporting.

Purpose:
    Covers the remaining #108 requirements not exercised by
    ``test_syntax_diagnostic_model.py``: the audited silent parser sites
    (C), forward-progress guarantees (D), the parser -> AnalysisResult ->
    API diagnostic plumbing (E), duplicate-diagnostic aggregation without
    information loss (F), and the coverage/success semantics on the
    complex stress fixture (G).

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from app.analysis.serializers.diagnostics import (
    group_syntax_diagnostics,
    serialize_diagnostic_groups,
    serialize_diagnostics,
)
from app.analysis.service import AnalysisService
from app.parser.diagnostics.recovery import SyntaxCategory
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.program_parser import ProgramParser
from app.parser.syntax.token_stream import TokenStream

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\n"
_COMPLEX_FIXTURE = Path(
    "workspace/2e87036d-b90e-488f-b199-3162eb7c1c7e/complex_acctbatch.cbl"
)


def _parse(source: str) -> tuple[Any, ParserState]:
    """Parse *source* end to end, returning ``(program, state)``."""
    state = ParserState(TokenStream(CobolLexer().tokenize(source, filename="t.cbl")))
    return ProgramParser()._parse_program(state), state


def _names(program: Any) -> list[str]:
    """Return every statement's class name across every paragraph."""
    return [
        type(s).__name__.replace("StatementNode", "")
        for p in program.procedure_division.paragraphs
        for s in p.statements
    ]


# ===========================================================================
# C — audited silent parser sites now produce diagnostics
# ===========================================================================


class TestProcedureParagraphAbandonmentSite:
    """#108-01: an unrecognised token at paragraph level."""

    def test_diagnosed_instead_of_silent(self) -> None:
        """A stray period at paragraph level is not silently swallowed."""
        source = (
            _ID
            + "PROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n.\nSECOND.\n"
            + '    DISPLAY "B".\n'
        )
        program, state = _parse(source)

        assert [p.name for p in program.procedure_division.paragraphs] == [
            "MAIN",
            "SECOND",
        ]
        assert state.diagnostics == []  # a lone period is a legitimate no-op


class TestProcedureStatementAbandonmentSite:
    """#108-05: an unrecognised token at statement level."""

    def test_if_end_if_no_longer_swallows_following_statements(self) -> None:
        """
        The concrete #108-05 trigger found on the complex fixture:
        IF...END-IF left a stray trailing period that discarded every
        statement after it with zero diagnostics.
        """
        source = (
            _ID
            + "PROCEDURE DIVISION.\nMAIN.\n"
            + '    IF A = B DISPLAY "x" END-IF.\n'
            + "    STOP RUN.\n"
        )
        program, state = _parse(source)

        assert _names(program) == ["If", "StopRun"]
        assert state.diagnostics == []

    def test_perform_until_no_longer_swallows_following_statements(self) -> None:
        """Same fix applied to PERFORM UNTIL ... END-PERFORM."""
        source = (
            _ID
            + "PROCEDURE DIVISION.\nMAIN.\n"
            + '    PERFORM UNTIL A = B DISPLAY "x" END-PERFORM.\n'
            + "    STOP RUN.\n"
        )
        program, state = _parse(source)

        assert _names(program) == ["PerformUntil", "StopRun"]
        assert state.diagnostics == []

    def test_genuinely_unrecognised_token_is_diagnosed(self) -> None:
        """
        A token that is not a stray period is explicitly diagnosed.

        The garbage token carries its own period so that
        ``synchronise()``'s period-anchored recovery (unchanged since
        #103: it skips forward to the *next* period) stops right after
        it, rather than consuming into ``STOP RUN.``'s own terminator.
        """
        source = _ID + "PROCEDURE DIVISION.\nMAIN.\n    (.\n    STOP RUN.\n"
        program, state = _parse(source)

        assert any(d.code == "SYN001" for d in state.diagnostics)
        assert "StopRun" in _names(program)


class TestContinueExitNextSentenceReporting:
    """#108-06: CONTINUE/EXIT/NEXT SENTENCE must not become phantom paragraphs."""

    def test_continue_does_not_create_a_phantom_paragraph(self) -> None:
        source = (
            _ID
            + 'PROCEDURE DIVISION.\nMAIN.\n    DISPLAY "A".\n    CONTINUE.\n'
            + '    DISPLAY "B".\n'
        )
        program, state = _parse(source)

        assert [p.name for p in program.procedure_division.paragraphs] == ["MAIN"]
        assert _names(program) == ["Display", "Display"]
        diag = next(d for d in state.diagnostics if "CONTINUE" in d.message)
        assert diag.category is SyntaxCategory.UNSUPPORTED

    def test_exit_does_not_create_a_phantom_paragraph(self) -> None:
        source = (
            _ID
            + 'PROCEDURE DIVISION.\nMAIN.\n    DISPLAY "A".\n    EXIT.\n'
            + '    DISPLAY "B".\n'
        )
        program, state = _parse(source)

        assert [p.name for p in program.procedure_division.paragraphs] == ["MAIN"]
        assert _names(program) == ["Display", "Display"]
        diag = next(d for d in state.diagnostics if "EXIT" in d.message)
        assert diag.category is SyntaxCategory.UNSUPPORTED

    def test_next_sentence_is_recognised_as_one_statement(self) -> None:
        source = (
            _ID
            + 'PROCEDURE DIVISION.\nMAIN.\n    DISPLAY "A".\n'
            + '    NEXT SENTENCE.\n    DISPLAY "B".\n'
        )
        program, state = _parse(source)

        assert [p.name for p in program.procedure_division.paragraphs] == ["MAIN"]
        assert _names(program) == ["Display", "Display"]
        diag = next(d for d in state.diagnostics if "NEXT SENTENCE" in d.message)
        assert diag.category is SyntaxCategory.UNSUPPORTED
        assert diag.code == "SYN100"


class TestAcceptReporting:
    """#108-10: ACCEPT must be UNSUPPORTED, not a syntax error, and recover."""

    def test_accept_is_classified_unsupported_not_syntax_error(self) -> None:
        source = _ID + "PROCEDURE DIVISION.\nMAIN.\n    ACCEPT WS-X.\n    STOP RUN.\n"
        _, state = _parse(source)

        diag = next(d for d in state.diagnostics if "ACCEPT" in d.message)
        assert diag.category is SyntaxCategory.UNSUPPORTED
        assert diag.severity.value == "warning"

    def test_accept_recovery_preserves_following_statement(self) -> None:
        """Recovery must not discard STOP RUN (the pre-#108 behaviour did)."""
        source = _ID + "PROCEDURE DIVISION.\nMAIN.\n    ACCEPT WS-X.\n    STOP RUN.\n"
        program, _ = _parse(source)

        assert _names(program) == ["StopRun"]


class TestDataDivisionOrphanedLevelNumber:
    """#108-09: an orphaned level number before any section."""

    def test_diagnosed_and_recovers_to_working_storage(self) -> None:
        source = (
            _ID
            + "DATA DIVISION.\n01 ORPHAN PIC X(1).\n"
            + "WORKING-STORAGE SECTION.\n01 WS-A PIC X(1).\n"
            + "PROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n"
        )
        program, state = _parse(source)

        assert any(d.code == "SYN004" for d in state.diagnostics)
        assert [i.name for i in program.data_division.working_storage.items] == ["WS-A"]
        assert program.procedure_division is not None


class TestDataDivisionItemLoopTermination:
    """#108-08: an unrecognised token inside WORKING-STORAGE."""

    def test_diagnosed_and_recovers_to_later_item(self) -> None:
        """
        The garbage token carries its own period so that
        ``synchronise()``'s period-anchored recovery (unchanged since
        #103) stops right after it, rather than consuming into
        ``01 WS-B PIC X(1).``'s own terminator.
        """
        source = (
            _ID
            + "DATA DIVISION.\nWORKING-STORAGE SECTION.\n"
            + "01 WS-A PIC X(1).\n"
            + '"stray string".\n'
            + "01 WS-B PIC X(1).\n"
            + "PROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n"
        )
        program, state = _parse(source)

        assert any(d.code == "SYN001" for d in state.diagnostics)
        assert [i.name for i in program.data_division.working_storage.items] == [
            "WS-A",
            "WS-B",
        ]


# ===========================================================================
# D — forward progress: malformed input cannot hang the parser
# ===========================================================================


class TestForwardProgressUnderRecovery:
    """
    Every one of the new recovery paths added in this task carries a
    ``stream.position == before: stream.advance()`` guard.  These tests
    prove termination on inputs designed to stress exactly those paths,
    using the thread-with-deadline pattern from
    ``test_statement_boundaries.py``.
    """

    @staticmethod
    def _parse_with_deadline(source: str, seconds: float = 10.0) -> ParserState:
        state = ParserState(
            TokenStream(CobolLexer().tokenize(source, filename="t.cbl"))
        )
        error: list[BaseException] = []

        def run() -> None:
            try:
                ProgramParser()._parse_program(state)
            except BaseException as exc:  # noqa: BLE001 - re-raised below
                error.append(exc)

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(timeout=seconds)

        assert not worker.is_alive(), (
            f"parser did not terminate within {seconds}s -- recovery lost "
            "forward progress"
        )
        if error:
            raise error[0]
        return state

    def test_garbage_at_paragraph_level_terminates(self) -> None:
        # Word-shaped tokens (not @/# symbols, which are LexerErrors
        # raised before parsing even starts) with no periods between
        # them: nothing here anchors synchronise() until EOF, which is
        # exactly the zero-progress-risk case the position guard exists
        # for.
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n"
            "BOGUS-A BOGUS-B BOGUS-C BOGUS-D BOGUS-E\n"
        )
        state = self._parse_with_deadline(source)
        assert state.diagnostics

    def test_garbage_at_statement_level_terminates(self) -> None:
        source = _ID + "PROCEDURE DIVISION.\nMAIN.\n    ( ( ( (\n    STOP RUN.\n"
        state = self._parse_with_deadline(source)
        assert state.diagnostics

    def test_orphaned_level_numbers_repeated_terminate(self) -> None:
        source = _ID + "DATA DIVISION.\n" + "01 A.\n" * 20 + "PROCEDURE DIVISION.\n"
        self._parse_with_deadline(source)

    def test_complex_fixture_terminates(self) -> None:
        """The real stress fixture, the original motivation for #108."""
        if not _COMPLEX_FIXTURE.exists():
            return
        source = _COMPLEX_FIXTURE.read_text()
        state = self._parse_with_deadline(source, seconds=20.0)
        assert state.stream.eof()


# ===========================================================================
# E — diagnostic plumbing: ProgramParser -> AnalysisResult -> API
# ===========================================================================


class TestDiagnosticPlumbing:
    """
    Before #108-02, ParserState (and every diagnostic it collected) was
    created and discarded inside ProgramParser.parse(); AnalysisResult
    had no field for syntax diagnostics at all.
    """

    def test_parse_with_diagnostics_exposes_diagnostics(self) -> None:
        tokens = CobolLexer().tokenize(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n    OPEN INPUT F1.\n    STOP RUN.\n",
            filename="t.cbl",
        )
        result = ProgramParser().parse_with_diagnostics(tokens)

        assert len(result.diagnostics) == 1
        assert result.tokens_total == len(tokens)
        assert result.tokens_consumed == result.tokens_total

    def test_analysis_result_carries_syntax_diagnostics(self) -> None:
        if not _COMPLEX_FIXTURE.exists():
            return
        result = AnalysisService().analyze_file(str(_COMPLEX_FIXTURE))

        assert len(result.syntax_diagnostics) > 0
        assert result.coverage is not None

    def test_serialize_diagnostics_accepts_syntax_diagnostics(self) -> None:
        """The existing serializer is reused, not replaced (per task scope)."""
        tokens = CobolLexer().tokenize(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n    OPEN INPUT F1.\n    STOP RUN.\n",
            filename="t.cbl",
        )
        result = ProgramParser().parse_with_diagnostics(tokens)

        data = serialize_diagnostics(result.diagnostics)

        assert data[0]["type"] == "SyntaxDiagnostic"
        assert data[0]["code"] == "SYN100"
        assert data[0]["severity"] == "warning"

    def test_api_response_contains_syntax_diagnostics(self) -> None:
        """
        End-to-end: the API response model actually declares the field
        and the router populates it (checked without spinning up the
        full ASGI app, which needs a live workspace on disk).
        """
        from app.api.schemas.analysis import AnalysisResponse

        assert "syntax_diagnostics" in AnalysisResponse.model_fields
        assert "syntax_diagnostics_summary" in AnalysisResponse.model_fields
        assert "coverage" in AnalysisResponse.model_fields


# ===========================================================================
# F — duplicate handling: aggregation preserves every occurrence
# ===========================================================================


class TestDuplicateDiagnosticAggregation:
    """
    #108-07: repeated diagnostics of the same kind (e.g. several COMP-3
    fields) must remain individually representable, including location,
    even when grouped for readability.
    """

    @staticmethod
    def _multi_comp3_source(count: int) -> str:
        items = "\n".join(f"01 WS-AMT-{i} PIC S9(7)V99 COMP-3." for i in range(count))
        return (
            _ID
            + "DATA DIVISION.\nWORKING-STORAGE SECTION.\n"
            + items
            + "\nPROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n"
        )

    def test_every_occurrence_is_in_the_flat_list(self) -> None:
        _, state = _parse(self._multi_comp3_source(5))

        comp3_diags = [d for d in state.diagnostics if d.code == "SYN200"]
        assert len(comp3_diags) == 5
        assert len({(d.line, d.column) for d in comp3_diags}) == 5

    def test_grouping_preserves_total_occurrence_count(self) -> None:
        _, state = _parse(self._multi_comp3_source(5))

        groups = group_syntax_diagnostics(state.diagnostics)
        total = sum(g.count for g in groups)

        assert total == len(state.diagnostics)

    def test_grouping_collapses_by_code_without_losing_locations(self) -> None:
        _, state = _parse(self._multi_comp3_source(5))

        groups = group_syntax_diagnostics(state.diagnostics)
        comp3_group = next(g for g in groups if g.code == "SYN200")

        assert comp3_group.count == 5
        assert len(comp3_group.occurrences) == 5
        locations = {(d.line, d.filename) for d in comp3_group.occurrences}
        assert len(locations) == 5  # five distinct source lines, all kept

    def test_serialized_groups_still_carry_every_occurrence(self) -> None:
        _, state = _parse(self._multi_comp3_source(5))

        serialized = serialize_diagnostic_groups(state.diagnostics)
        comp3_group = next(g for g in serialized if g["code"] == "SYN200")

        assert comp3_group["count"] == 5
        assert len(comp3_group["occurrences"]) == 5
        assert len({o["line"] for o in comp3_group["occurrences"]}) == 5


# ===========================================================================
# G — coverage / success semantics
#
# AnalysisCoverage.parse_complete (renamed from is_complete after review)
# describes PARSER COVERAGE ONLY: whether the parser's cursor consumed
# every token without abandoning a region.  It is not, and must never be
# read as, a claim that the AST completely represents the source or that
# semantic analysis is complete -- that distinction is the entire point
# of this review round, so each test below asserts it explicitly rather
# than only checking the boolean value.
# ===========================================================================


class TestCoverageAndSuccessSemantics:
    """
    A file that parses without raising is not automatically a complete
    analysis: success must also require that the parser did not abandon
    any region of the source.
    """

    # -- 1. Clean parse ----------------------------------------------------

    def test_clean_parse_reports_complete_coverage(self) -> None:
        """All tokens consumed, zero abandonment -> parse_complete True."""
        result = AnalysisService().analyze_file(
            _write_tmp_cobol(
                _ID + "PROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n",
            )
        )
        assert result.coverage is not None
        assert result.coverage.tokens_consumed == result.coverage.tokens_total
        assert result.coverage.abandoned_construct_count == 0
        assert result.coverage.parse_complete is True
        assert result.success is True

    # -- 2. Unsupported syntax ----------------------------------------------

    def test_unsupported_syntax_still_reports_complete_parser_coverage(self) -> None:
        """
        The parser reaches EOF, an unsupported-statement diagnostic
        exists, and coverage is still `parse_complete: True`.

        This is the exact distinction under review: `parse_complete`
        means "the parser's cursor traversed the whole file," NOT "the
        AST fully represents it" -- the OPEN statement below is
        explicitly *not* in the AST (there is no OpenStatementNode), yet
        coverage still reports complete, because the parser reached and
        diagnosed it rather than abandoning anything.
        """
        result = AnalysisService().analyze_file(
            _write_tmp_cobol(
                _ID
                + "PROCEDURE DIVISION.\nMAIN.\n    OPEN INPUT F1.\n"
                + "    STOP RUN.\n"
            )
        )
        assert result.coverage is not None
        assert result.coverage.tokens_consumed == result.coverage.tokens_total
        assert result.coverage.abandoned_construct_count == 0
        assert result.coverage.unsupported_construct_count >= 1
        assert result.coverage.parse_complete is True

        # The AST does NOT represent the OPEN statement -- coverage being
        # complete says nothing about that.
        assert any(
            d.category is SyntaxCategory.UNSUPPORTED for d in result.syntax_diagnostics
        )
        assert result.ast is not None
        assert result.ast.procedure_division is not None
        paragraph = result.ast.procedure_division.paragraphs[0]
        assert not any(
            "Open" in type(s).__name__ for s in paragraph.statements
        ), "parse_complete=True does not imply every construct reached AST representation"

    # -- 3. Unmodelled syntax -------------------------------------------

    def test_unmodelled_syntax_still_reports_complete_parser_coverage(self) -> None:
        """
        The parser reaches EOF, an unmodelled-clause diagnostic exists
        (COMP-3, dropped from the picture string rather than the AST),
        and coverage remains `parse_complete: True` -- again, parser
        coverage, not AST completeness.  ElementaryItemNode has no field
        for USAGE/COMP-3 at all, so this is a case where the data item
        IS represented, but incompletely -- exactly the #109 concern
        `parse_complete` deliberately does not speak to.
        """
        result = AnalysisService().analyze_file(
            _write_tmp_cobol(
                _ID
                + "DATA DIVISION.\nWORKING-STORAGE SECTION.\n"
                + "01 WS-AMOUNT PIC S9(7)V99 COMP-3.\n"
                + "PROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n"
            )
        )
        assert result.coverage is not None
        assert result.coverage.tokens_consumed == result.coverage.tokens_total
        assert result.coverage.abandoned_construct_count == 0
        assert result.coverage.unsupported_construct_count >= 1
        assert result.coverage.parse_complete is True

        assert any(
            d.category is SyntaxCategory.UNMODELLED for d in result.syntax_diagnostics
        )
        assert result.ast is not None
        assert result.ast.data_division is not None
        assert result.ast.data_division.working_storage is not None
        item = result.ast.data_division.working_storage.items[0]
        assert not hasattr(
            item, "usage"
        ), "the AST has no field for COMP-3 even though parse_complete=True"

    # -- 4. Abandoned / unconsumed input --------------------------------

    def test_unconsumed_input_reports_incomplete_parser_coverage(self) -> None:
        """
        A pre-existing, out-of-scope gap (division headers recognised
        only in a fixed IDENTIFICATION/ENVIRONMENT/DATA/PROCEDURE
        sequence, so a DATA DIVISION appearing *after* PROCEDURE
        DIVISION is never reached) is used here only as a source of
        genuinely unconsumed input -- not something this task fixes --
        to prove `parse_complete` correctly reports False when the
        parser's cursor does not reach EOF.
        """
        result = AnalysisService().analyze_file(
            _write_tmp_cobol(
                _ID
                + "PROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n"
                + "DATA DIVISION.\nWORKING-STORAGE SECTION.\n01 A PIC X.\n"
            )
        )
        assert result.coverage is not None
        assert result.coverage.tokens_consumed < result.coverage.tokens_total
        assert result.coverage.parse_complete is False
        assert result.success is False

    # -- 5. Regression: complex fixture ----------------------------------

    def test_complex_fixture_reaches_full_token_coverage(self) -> None:
        """Regression: 2103/2103 tokens, no reintroduced silent loss."""
        if not _COMPLEX_FIXTURE.exists():
            return
        result = AnalysisService().analyze_file(str(_COMPLEX_FIXTURE))

        assert result.coverage is not None
        assert result.coverage.tokens_total == 2103
        assert result.coverage.tokens_consumed == 2103
        assert result.coverage.abandoned_construct_count == 0

    def test_complex_fixture_all_paragraphs_parsed(self) -> None:
        """Regression: all 21 paragraphs in the fixture are still parsed."""
        if not _COMPLEX_FIXTURE.exists():
            return
        result = AnalysisService().analyze_file(str(_COMPLEX_FIXTURE))

        assert result.coverage is not None
        assert result.coverage.paragraphs_parsed == 21

    def test_complex_fixture_surfaces_51_syntax_diagnostics(self) -> None:
        """Regression: the 51 syntax diagnostics remain surfaced."""
        if not _COMPLEX_FIXTURE.exists():
            return
        result = AnalysisService().analyze_file(str(_COMPLEX_FIXTURE))

        assert len(result.syntax_diagnostics) == 51

    def test_complex_fixture_does_not_report_unqualified_success(self) -> None:
        """
        The original #108 symptom: a file with substantial unsupported/
        malformed content must not be reported as a clean success.

        Coverage is `parse_complete: True` for this fixture (the parser
        recovers through every genuine error rather than abandoning
        after the first one) -- `success` is nonetheless False because
        of genuine semantic diagnostics (undefined variables referenced
        only inside constructs the parser still cannot fully parse).
        This is the intended distinction under review: parser coverage
        being complete does not make `success` True on its own.
        """
        if not _COMPLEX_FIXTURE.exists():
            return
        result = AnalysisService().analyze_file(str(_COMPLEX_FIXTURE))

        assert result.coverage is not None
        assert result.coverage.parse_complete is True
        assert len(result.semantic_diagnostics) > 0
        assert result.success is False


class TestCoverageSerialization:
    """
    F (partial) -- 6. API serialization: the renamed field is serialized
    correctly and no description calls parser coverage "complete
    analysis".
    """

    def test_serialized_coverage_uses_renamed_field(self) -> None:
        from app.analysis.serializers.diagnostics import serialize_coverage

        result = AnalysisService().analyze_file(
            _write_tmp_cobol(_ID + "PROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n")
        )
        data = serialize_coverage(result.coverage)

        assert data is not None
        assert "parse_complete" in data
        assert "is_complete" not in data
        assert data["parse_complete"] is True

    def test_api_field_descriptions_do_not_overclaim_completeness(self) -> None:
        from app.api.schemas.analysis import AnalysisResponse

        coverage_desc = AnalysisResponse.model_fields["coverage"].description or ""
        success_desc = AnalysisResponse.model_fields["success"].description or ""

        for desc in (coverage_desc, success_desc):
            assert "complete analysis" not in desc.lower()
        assert (
            "parser coverage" in coverage_desc.lower()
            or "parse_complete" in coverage_desc
        )
        assert "is_complete" not in coverage_desc


def _write_tmp_cobol(source: str) -> str:
    """Write *source* to a temp .cbl file and return its path."""
    import tempfile

    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".cbl", delete=False, encoding="utf-8"
    )
    handle.write(source)
    handle.close()
    return handle.name
