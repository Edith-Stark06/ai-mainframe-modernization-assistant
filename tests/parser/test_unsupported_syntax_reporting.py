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
_COMPLEX_FIXTURE = Path("tests/fixtures/complex_acctbatch.cbl")


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
    #108-07: repeated diagnostics of the same kind (e.g. several SIGN
    clauses) must remain individually representable, including location,
    even when grouped for readability.

    Uses ``SIGN`` rather than the originally-written ``COMP-3``: task
    #stage41 gave ``USAGE``/``COMP*`` a real parser/AST field, so it no
    longer produces a repeatable ``SYN200``. ``SIGN`` still does, and
    preserves this class's original shape and purpose.
    """

    @staticmethod
    def _multi_sign_source(count: int) -> str:
        items = "\n".join(
            f"01 WS-AMT-{i} PIC S9(7)V99 SIGN IS TRAILING." for i in range(count)
        )
        return (
            _ID
            + "DATA DIVISION.\nWORKING-STORAGE SECTION.\n"
            + items
            + "\nPROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n"
        )

    def test_every_occurrence_is_in_the_flat_list(self) -> None:
        _, state = _parse(self._multi_sign_source(5))

        sign_diags = [d for d in state.diagnostics if d.code == "SYN200"]
        assert len(sign_diags) == 5
        assert len({(d.line, d.column) for d in sign_diags}) == 5

    def test_grouping_preserves_total_occurrence_count(self) -> None:
        _, state = _parse(self._multi_sign_source(5))

        groups = group_syntax_diagnostics(state.diagnostics)
        total = sum(g.count for g in groups)

        assert total == len(state.diagnostics)

    def test_grouping_collapses_by_code_without_losing_locations(self) -> None:
        _, state = _parse(self._multi_sign_source(5))

        groups = group_syntax_diagnostics(state.diagnostics)
        sign_group = next(g for g in groups if g.code == "SYN200")

        assert sign_group.count == 5
        assert len(sign_group.occurrences) == 5
        locations = {(d.line, d.filename) for d in sign_group.occurrences}
        assert len(locations) == 5  # five distinct source lines, all kept

    def test_serialized_groups_still_carry_every_occurrence(self) -> None:
        _, state = _parse(self._multi_sign_source(5))

        serialized = serialize_diagnostic_groups(state.diagnostics)
        sign_group = next(g for g in serialized if g["code"] == "SYN200")

        assert sign_group["count"] == 5
        assert len(sign_group["occurrences"]) == 5
        assert len({o["line"] for o in sign_group["occurrences"]}) == 5


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
        (``SIGN``, dropped from the picture string rather than the AST),
        and coverage remains `parse_complete: True` -- again, parser
        coverage, not AST completeness.  ElementaryItemNode has no field
        for SIGN at all, so this is a case where the data item IS
        represented, but incompletely -- exactly the #109 concern
        `parse_complete` deliberately does not speak to.

        Uses ``SIGN`` rather than the originally-written ``COMP-3``: task
        #stage41 gave ``USAGE``/``COMP*`` a real parser/AST field
        (:attr:`~app.parser.ast.data_items.ElementaryItemNode.usage`), so
        it is no longer an example of an unmodelled clause. ``SIGN``
        still is, and preserves this test's original shape and purpose.
        """
        result = AnalysisService().analyze_file(
            _write_tmp_cobol(
                _ID
                + "DATA DIVISION.\nWORKING-STORAGE SECTION.\n"
                + "01 WS-AMOUNT PIC S9(7)V99 SIGN IS TRAILING.\n"
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
            item, "sign"
        ), "the AST has no field for SIGN even though parse_complete=True"

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
        """Regression: 2093/2093 tokens, no reintroduced silent loss.

        Was 2103/2103 before the decimal-literal lexer fix
        (docs/MMIM_PARSER_VALIDATION_FIX.md): 5 decimal literals in this
        fixture (``9.99`` in a PICTURE clause, ``0.0025``/``0.0035``/
        ``0.0050``/``0.0075`` in MOVE statements) were previously
        mis-tokenized as 3 tokens each (``NUMBER``, spurious ``PERIOD``,
        ``NUMBER``) instead of 1 correct ``NUMBER`` token — accounting for
        exactly the -10 token delta (5 × 2). Verified token-for-token
        against the pre-fix lexer: every other token in this 2093-token
        stream is byte-identical to before; nothing else changed and
        nothing was silently lost.
        """
        if not _COMPLEX_FIXTURE.exists():
            return
        result = AnalysisService().analyze_file(str(_COMPLEX_FIXTURE))

        assert result.coverage is not None
        assert result.coverage.tokens_total == 2093
        assert result.coverage.tokens_consumed == 2093
        assert result.coverage.abandoned_construct_count == 0

    def test_complex_fixture_all_paragraphs_parsed(self) -> None:
        """Regression: all 21 paragraphs in the fixture are still parsed."""
        if not _COMPLEX_FIXTURE.exists():
            return
        result = AnalysisService().analyze_file(str(_COMPLEX_FIXTURE))

        assert result.coverage is not None
        assert result.coverage.paragraphs_parsed == 21

    def test_complex_fixture_surfaces_49_syntax_diagnostics(self) -> None:
        """Regression: the (now 49, was 51) syntax diagnostics remain surfaced.

        51 -> 44 came from the decimal-literal lexer fix (7 fewer cascading
        SYN001/SYN005 "unexpected token"/resync errors -- see
        test_complex_fixture_reaches_full_token_coverage and
        docs/MMIM_PARSER_VALIDATION_FIX.md).

        44 -> 45 comes from the COMPUTE/EVALUATE-inside-IF-block parser
        recovery fix and is a *strengthening* of diagnostic accuracy, not
        a regression: the vague `SYN005 "expected statement in IF block"`
        previously reported at line 339 is replaced by the precise
        `SYN100 "unsupported statement 'COMPUTE'"` (same line, matching
        every other COMPUTE occurrence in this file), and a COMPUTE at
        line 412 that was previously silently swallowed by the old
        scan-to-next-period recovery cascade -- with *zero* diagnostic at
        all -- is now correctly surfaced. `statements_parsed` for this
        fixture rose 46 -> 52 in the same change: more of the source is
        actually represented, not less. See docs/MMIM_PARSER_VALIDATION_FIX.md.

        45 -> 47 (task #stage25) is the same kind of strengthening again, from
        a different corner: this fixture has 9 `NOT =`/`<>` comparisons
        (`docs/MMIM_NEGATED_COMPARISON_FIX.md`), 7 of which the parser can now
        represent (`IF WS-CUST-STATUS NOT = '00'` and 3 siblings, plus a
        3-term `AND` chain on `TR-CURRENCY`) -- each used to be its own
        `SYN005 "expected comparison operator"`, now gone. But fixing them
        lets the parser walk *past* line 317 for the first time, which
        reveals a genuinely different, pre-existing, unrelated gap this
        fixture already had: `IF WA-STATUS(WS-IDX) = 'C'` at line 323 uses a
        *subscripted* operand, which this grammar's operand check has never
        supported -- its own `SYN005 "expected comparison operator"` was
        always latent here, just hidden behind the recovery cascade of the
        (now-fixed) earlier failure. `statements_parsed` rose 52 -> 60 in the
        same change. `success` and `semantic_diags` (10) are unchanged.

        47 -> 49 (task #stage27) is the FILE SECTION fix: this fixture's own
        FILE SECTION (3 `FD` records, unrelated to the 45-source training
        corpus) previously produced exactly one `SYN101 "unsupported DATA
        DIVISION section 'FILE'"` and was otherwise skipped whole. It now
        parses in full, which removes that one diagnostic but reveals 3
        genuinely different, pre-existing, unrelated `SYN200 "'COMP-3' clause
        ... not represented"` warnings on 3 of its fields (`AR-BALANCE`,
        `AR-CREDIT-LIMIT`, `TR-AMOUNT`) that were always latent inside the
        skipped section -- the same "more honest, not less" pattern as
        45 -> 47 above (net -1 + 3 = +2). `statements_parsed` is unchanged
        (FILE SECTION adds no PROCEDURE DIVISION statements).
        `semantic_diagnostics` drops 10 -> 2: 8 of the 10 were
        `SEM003 "undefined variable"` on FILE SECTION fields the semantic
        analyser could not previously see declared anywhere (`AR-BALANCE`
        and 7 siblings); they are real variables now, so the diagnostic --
        which was correct given the information available, not a bug -- no
        longer fires. The remaining 2 (`ALL '-'`/`ALL '='`, a `STRING`
        figurative-constant-repetition construct) are unrelated and
        unchanged. `success` stays `False`.

        49 -> 48 (task #stage32) is the OCCURS/subscripted-operand
        representation fix: `IF WA-ACCOUNT-ID(WS-IDX) = TR-ACCOUNT-ID` at
        line 323 (already named above as the concrete example that first
        surfaced this fixture's subscripted-condition gap) and several
        sibling `IF`s in `4300-VALIDATE-TRANSACTION` and its callees on
        subscripted table elements -- previously each its own latent
        `SYN005 "expected comparison operator"`, this grammar's comparison
        operand check having never accepted a subscripted reference -- now
        parse as a single structured operand instead
        (`app.parser.ast.statements.Subscript`), net -1 diagnostic.
        `statements_parsed` rises 60 -> 68 (confirmed directly, not
        assumed) as the previously-dropped `IF`/`END-IF` bodies these
        `SYN005`s used to discard whole are now reachable -- the same
        "fixing one gate reveals previously-unreachable code" pattern this
        fixture's own history above already shows for the `NOT =` fix.
        `success` stays `False` (2 semantic diagnostics, `ZZZ,ZZZ,ZZ9`
        edited-PICTURE and the `STRING`/figurative-constant-repetition gap,
        are both untouched -- neither is a subscript). See
        `tests/parser/test_perform_until_unsupported_statement_fix.py
        ::test_fixture_diagnostic_total_and_statements_parsed_move_by_the_read_fix`
        for the full per-paragraph accounting.

        48 -> 47 (task #stage34) is the `PERFORM VARYING` implementation:
        this fixture's four occurrences (`4100-FIND-ACCOUNT`,
        `4200-FIND-CUSTOMER`, `5000-CALCULATE-EXPOSURE`,
        `5100-RISK-AGGREGATION`) previously mis-parsed into a bare
        `PerformStatementNode(target="VARYING")`, stranding the loop
        variable (`WS-IDX`/`WS-IDX2`) on the stream as an unexpected
        token -- 4 latent `SYN001 "unexpected token"` diagnostics (2 per
        variable name, one per loop). Task #stage34's real
        `PerformVaryingStatementNode`/parser removes all 4; it also newly
        reaches two `EXIT PERFORM` statements nested inside two of those
        loops' `IF` bodies (`4100-FIND-ACCOUNT`/`4200-FIND-CUSTOMER`) and
        correctly reports each as its own
        `SYN100 "unsupported statement 'EXIT PERFORM'"` instead of
        letting a mis-skipped bare `EXIT` leave a stray `PERFORM` token
        to corrupt the surrounding parse -- see
        `tests/parser/test_stage34_perform_varying.py` for the
        parser-level tests and `docs`-free inline documentation in
        `app.parser.syntax.procedure_parser
        .ProcedureDivisionParser._skip_unsupported_statement_auto`.
        `statements_parsed` moves 68 -> 67 (confirmed directly, not
        assumed) -- the four loops' headers and genuinely-supported body
        statements are now real, counted statements, net of what the
        previous `SYN001` misparse recovery had, by accident, still
        managed to count nearby. `success` stays `False`; the 2 semantic
        diagnostics (unrelated to subscripts or loops) are untouched.

        47 -> 44 (task #stage35) is the COMPUTE implementation. This
        fixture has 6 real COMPUTE statements (`4310-CHECK-LIMIT` x2,
        `4330-CHECK-DATE` x1, `4410-CALCULATE-FEE` x1,
        `4420-UPDATE-ACCOUNT-TABLE` x1, `5000-CALCULATE-EXPOSURE` x1). 4
        are plain `+ - * /` expressions (optionally subscripted, one
        inside a `PERFORM VARYING` body) -- squarely Stage 35's supported
        grammar -- and now parse into a real `ComputeStatementNode`
        instead of a `SYN100` skip: net -4 diagnostics. The other 2 use
        syntax Stage 35 deliberately does not implement (neither is
        anywhere in the 45-source training corpus) and are still
        correctly reported as `SYN100 "unsupported statement 'COMPUTE'"`:
        `4330-CHECK-DATE`'s `COMPUTE WS-MONTH = FUNCTION MOD(...)` (an
        intrinsic-function operand) and `4410-CALCULATE-FEE`'s
        `COMPUTE WS-CURRENT-FEE ROUNDED = ...` (the `ROUNDED` clause).
        Verified directly: with
        `ProcedureDivisionParser._compute_has_supported_syntax` forced to
        always return `False` (reproducing the pre-#stage35 behavior
        exactly, since that predicate is the only thing #stage35 added
        to the skip decision -- the skip mechanism itself is unchanged),
        this fixture reproduces the documented pre-#stage35 baseline
        byte-for-byte: 47 diagnostics, 6 of them COMPUTE, 67
        `statements_parsed`. `statements_parsed` rises 67 -> 69 here (not
        67 -> 71): it counts each paragraph's own top-level statement
        list, and 2 of the 4 newly-parsed COMPUTEs are nested inside an
        `IF` (`4310-CHECK-LIMIT`'s second, `5000-CALCULATE-EXPOSURE`'s
        one) rather than being a top-level paragraph statement
        themselves -- the same counting rule already visible above for
        nested `IF`/`PERFORM` bodies. `success` stays `False`; the 2
        semantic diagnostics are untouched.

        44 -> 41 (task #stage40) is the `READ` implementation. This
        fixture has 3 real `READ ... AT END ... NOT AT END ...
        END-READ` occurrences (`2000-LOAD-CUSTOMERS`, `3000-LOAD-
        ACCOUNTS`, `4000-PROCESS-TRANSACTIONS`, lines 191/229/256),
        each previously its own `SYN100 "unsupported statement
        'READ'"`; all three now parse into a real `ReadStatementNode`
        with zero diagnostics (net -3). See
        `tests/parser/test_perform_until_unsupported_statement_fix.py
        ::test_fixture_diagnostic_total_and_statements_parsed_move_by_the_read_fix`
        for the full per-paragraph accounting. `statements_parsed`
        stays at 69 (each `PERFORM UNTIL` body already counted as one
        statement before this fix -- now real content instead of a
        fully-discarded unsupported statement, not an additional one).
        `success` stays `False`; the 2 semantic diagnostics are
        untouched.

        41 -> 24 (task #stage41) is the `USAGE`/`COMP*` implementation:
        this fixture has 17 real `COMP-3` occurrences (an accumulator
        pattern spread across `1000`-series working-storage fields, the
        `WS-ACCOUNT-TABLE` subtable's `WA-BALANCE`/`WA-LIMIT`, and
        `AUDIT-AMOUNT`), each previously its own `SYN200 "'COMP-3'
        clause ... not represented"`; all 17 now attach a real
        `UsageType.COMP_3` via `ElementaryItemNode.usage` with zero
        diagnostics (net -17, confirmed directly: 17 is exactly this
        fixture's own COMP-3 occurrence count, not a coincidence).
        `statements_parsed` is unchanged (USAGE adds no PROCEDURE
        DIVISION statements). `success` stays `False`; the 2 semantic
        diagnostics are untouched.
        """
        if not _COMPLEX_FIXTURE.exists():
            return
        result = AnalysisService().analyze_file(str(_COMPLEX_FIXTURE))

        assert len(result.syntax_diagnostics) == 24

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
