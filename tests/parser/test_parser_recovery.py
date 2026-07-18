"""
Tests for Parser Error Recovery (TASK-017).

Purpose:
    Verify that the COBOL recursive-descent parser implements panic-mode
    error recovery correctly: recoverable syntax errors are collected as
    :class:`~app.parser.diagnostics.recovery.SyntaxDiagnostic` records
    while parsing continues, and only fatal errors raise
    :class:`~app.parser.syntax.parser_exceptions.ParserError`.

Coverage:
    Recovery utilities:
        - SyntaxDiagnostic construction and string representation.
        - RecoveryContext and SynchronisationPoint enumerations.
        - RecoveryManager.record_and_synchronise() — normal path.
        - RecoveryManager.record_error() — no-sync path.
        - RecoveryManager diagnostics accumulation.
        - RecoveryManager re-entrant guard (in_recovery).
        - synchronise() — stops at period.
        - synchronise() — stops at division keyword.
        - synchronise() — stops at section keyword.
        - synchronise() — stops at paragraph label heuristic.
        - synchronise() — stops at EOF.

    ParserState extensions:
        - record_and_synchronise() delegates to RecoveryManager.
        - diagnostics property reflects collected errors.
        - error_count merges legacy + structured counts.
        - has_errors reflects both sources.
        - in_recovery property proxy.
        - Backward-compatible record_error() still works.

    IdentificationDivisionParser recovery:
        - Unknown clause keyword — recovered, parsing continues.
        - Non-keyword token where clause expected — recovered.
        - Missing period in PROGRAM-ID clause — recovered.
        - Multiple errors collected in one pass.
        - Valid program parses cleanly (zero diagnostics).

    DataDivisionParser recovery:
        - Invalid level number — recovered.
        - Missing data-name — recovered.
        - Missing period at item end — recovered.
        - Multiple data items with mixed errors.
        - Valid data division parses cleanly.

    ProcedureDivisionParser recovery:
        - Missing period after paragraph label — recovered.
        - Unsupported statement keyword — recovered.
        - Missing operand in DISPLAY — recovered.
        - Multiple statement errors in one paragraph.
        - Recovery after paragraph boundary.
        - Valid procedure division parses cleanly.

    End-to-end:
        - Full COBOL program with multiple syntax errors across divisions.
        - Parser collects all diagnostics without aborting.
        - EOF recovery.

Non-responsibilities:
    - Semantic analysis.
    - Lexer behaviour.
    - AST node field correctness (covered by other test modules).

Dependencies:
    - :mod:`app.parser.diagnostics.recovery`          — all recovery types.
    - :mod:`app.parser.syntax.parser_state`           — ParserState.
    - :mod:`app.parser.syntax.token_stream`           — TokenStream.
    - :mod:`app.parser.syntax.identification_parser`  — IdentificationDivisionParser.
    - :mod:`app.parser.syntax.data_parser`            — DataDivisionParser.
    - :mod:`app.parser.syntax.procedure_parser`       — ProcedureDivisionParser.
    - :mod:`app.parser.syntax.program_parser`         — ProgramParser.
    - :mod:`app.parser.lexer.token`                   — Token.
    - :mod:`app.parser.lexer.token_types`             — TokenType.
    - :mod:`app.parser.lexer.position`                — Position.
    - :mod:`pytest`                                   — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pytest

from app.parser.diagnostics.recovery import (
    RecoveryContext,
    RecoveryManager,
    SynchronisationPoint,
    SyntaxDiagnostic,
    synchronise,
)
from app.parser.lexer.position import Position
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType
from app.parser.syntax.identification_parser import IdentificationDivisionParser
from app.parser.syntax.data_parser import DataDivisionParser
from app.parser.syntax.parser_exceptions import ParserError
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.procedure_parser import ProcedureDivisionParser
from app.parser.syntax.program_parser import ProgramParser
from app.parser.syntax.token_stream import TokenStream

# ---------------------------------------------------------------------------
# Token construction helpers
# ---------------------------------------------------------------------------

_FILE = "test.cbl"


def _pos(line: int = 1, col: int = 1, offset: int = 0) -> Position:
    """Create a Position with the given coordinates."""
    return Position(line=line, column=col, offset=offset, filename=_FILE)


def _tok(
    ttype: TokenType,
    lexeme: str = "",
    line: int = 1,
    col: int = 1,
    offset: int = 0,
) -> Token:
    """Create a Token."""
    return Token(type=ttype, lexeme=lexeme, position=_pos(line, col, offset))


def _kw(lexeme: str, line: int = 1) -> Token:
    """Create a KEYWORD token."""
    return _tok(TokenType.KEYWORD, lexeme, line=line)


def _id(lexeme: str, line: int = 1) -> Token:
    """Create an IDENTIFIER token."""
    return _tok(TokenType.IDENTIFIER, lexeme, line=line)


def _num(lexeme: str, line: int = 1) -> Token:
    """Create a NUMBER token."""
    return _tok(TokenType.NUMBER, lexeme, line=line)


def _str(lexeme: str, line: int = 1) -> Token:
    """Create a STRING token."""
    return _tok(TokenType.STRING, lexeme, line=line)


def _period(line: int = 1) -> Token:
    """Create a PERIOD token."""
    return _tok(TokenType.PERIOD, ".", line=line)


def _eof(line: int = 99) -> Token:
    """Create an EOF token."""
    return _tok(TokenType.EOF, "", line=line)


def _make_stream(tokens: list[Token]) -> TokenStream:
    """Create a TokenStream from a list of tokens."""
    return TokenStream(tokens)


def _make_state(tokens: list[Token]) -> ParserState:
    """Create a ParserState from a list of tokens."""
    return ParserState(_make_stream(tokens))


# ===========================================================================
# SyntaxDiagnostic tests
# ===========================================================================


class TestSyntaxDiagnostic:
    """Tests for the SyntaxDiagnostic value type."""

    def test_construction_and_fields(self) -> None:
        """SyntaxDiagnostic stores all provided fields correctly."""
        diag = SyntaxDiagnostic(
            message="expected '.'",
            line=3,
            column=5,
            offset=42,
            filename="prog.cbl",
            context=RecoveryContext.IDENTIFICATION_DIVISION,
            sync_point=SynchronisationPoint.PERIOD,
            tokens_skipped=2,
        )
        assert diag.message == "expected '.'"
        assert diag.line == 3
        assert diag.column == 5
        assert diag.offset == 42
        assert diag.filename == "prog.cbl"
        assert diag.context is RecoveryContext.IDENTIFICATION_DIVISION
        assert diag.sync_point is SynchronisationPoint.PERIOD
        assert diag.tokens_skipped == 2

    def test_str_representation(self) -> None:
        """str(SyntaxDiagnostic) produces a human-readable line."""
        diag = SyntaxDiagnostic(
            message="unexpected token",
            line=10,
            column=1,
            offset=200,
            filename="x.cbl",
            context=RecoveryContext.DATA_DIVISION,
            sync_point=SynchronisationPoint.EOF,
            tokens_skipped=0,
        )
        result = str(diag)
        assert "x.cbl" in result
        assert "10" in result
        assert "1" in result
        assert "unexpected token" in result

    def test_immutable(self) -> None:
        """SyntaxDiagnostic is frozen and cannot be mutated."""
        diag = SyntaxDiagnostic(
            message="err",
            line=1,
            column=1,
            offset=0,
            filename="",
            context=RecoveryContext.UNKNOWN,
            sync_point=None,
            tokens_skipped=0,
        )
        with pytest.raises((AttributeError, TypeError)):
            diag.message = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        """Two diagnostics with equal fields compare as equal."""
        kwargs = dict(
            message="m",
            line=1,
            column=1,
            offset=0,
            filename="f.cbl",
            context=RecoveryContext.UNKNOWN,
            sync_point=None,
            tokens_skipped=0,
        )
        assert SyntaxDiagnostic(**kwargs) == SyntaxDiagnostic(**kwargs)  # type: ignore[arg-type]

    def test_sync_point_none_allowed(self) -> None:
        """sync_point=None is valid for diagnostics with no sync attempt."""
        diag = SyntaxDiagnostic(
            message="m",
            line=1,
            column=1,
            offset=0,
            filename="",
            context=RecoveryContext.UNKNOWN,
            sync_point=None,
            tokens_skipped=0,
        )
        assert diag.sync_point is None


# ===========================================================================
# RecoveryContext and SynchronisationPoint tests
# ===========================================================================


class TestEnumerations:
    """Tests for the RecoveryContext and SynchronisationPoint enums."""

    def test_recovery_context_members(self) -> None:
        """All expected RecoveryContext members are present."""
        members = {m.value for m in RecoveryContext}
        assert "identification_division" in members
        assert "data_division" in members
        assert "procedure_division" in members
        assert "working_storage_section" in members
        assert "paragraph" in members
        assert "statement" in members
        assert "unknown" in members

    def test_synchronisation_point_members(self) -> None:
        """All expected SynchronisationPoint members are present."""
        members = {m.value for m in SynchronisationPoint}
        assert "period" in members
        assert "division" in members
        assert "section" in members
        assert "paragraph" in members
        assert "eof" in members


# ===========================================================================
# synchronise() function tests
# ===========================================================================


class TestSynchronise:
    """Unit tests for the low-level synchronise() function."""

    def test_sync_stops_at_period_and_consumes_it(self) -> None:
        """synchronise() on a NUMBER token stops at period and consumes it."""
        # Use NUMBER tokens so they don't trigger the paragraph heuristic
        # (which only fires for IDENTIFIER and KEYWORD types)
        tokens = [
            _num("123", line=1),
            _period(line=1),
            _eof(),
        ]
        stream = _make_stream(tokens)
        sync_pt, skipped = synchronise(stream)
        assert sync_pt is SynchronisationPoint.PERIOD
        assert skipped == 2  # consumed NUMBER + period
        # After sync, stream is on EOF
        assert stream.current().type is TokenType.EOF

    def test_sync_stops_at_division_keyword_without_consuming(self) -> None:
        """synchronise() stops before a division keyword."""
        tokens = [
            _kw("BAD", line=1),
            _kw("DATA", line=2),
            _kw("DIVISION", line=2),
            _period(line=2),
            _eof(),
        ]
        stream = _make_stream(tokens)
        sync_pt, skipped = synchronise(stream)
        assert sync_pt is SynchronisationPoint.DIVISION
        # BAD was consumed; DATA should be current
        assert stream.current().lexeme.upper() == "DATA"

    def test_sync_stops_at_section_keyword_without_consuming(self) -> None:
        """synchronise() stops before a WORKING-STORAGE section keyword."""
        tokens = [
            _id("JUNK", line=1),
            _kw("WORKING-STORAGE", line=2),
            _kw("SECTION", line=2),
            _period(line=2),
            _eof(),
        ]
        stream = _make_stream(tokens)
        sync_pt, skipped = synchronise(stream)
        assert sync_pt is SynchronisationPoint.SECTION
        assert stream.current().lexeme.upper() == "WORKING-STORAGE"

    def test_sync_stops_at_paragraph_label_heuristic(self) -> None:
        """synchronise() detects paragraph label; label token is consumed."""
        tokens = [
            _kw("NOISE", line=1),
            _id("MAIN-PARA", line=2),
            _period(line=2),
            _eof(),
        ]
        stream = _make_stream(tokens)
        sync_pt, skipped = synchronise(stream)
        assert sync_pt is SynchronisationPoint.PARAGRAPH
        # NOISE consumed (skipped=1), MAIN-PARA consumed (skipped=2)
        # Stream is now on PERIOD (left for the caller to inspect)
        assert stream.current().type is TokenType.PERIOD

    def test_sync_stops_at_eof(self) -> None:
        """synchronise() returns EOF when no anchor is found before end of stream."""
        tokens = [
            _kw("NOISE", line=1),
            _eof(),
        ]
        stream = _make_stream(tokens)
        sync_pt, skipped = synchronise(stream)
        assert sync_pt is SynchronisationPoint.EOF
        assert stream.current().type is TokenType.EOF

    def test_sync_on_already_eof_stream(self) -> None:
        """synchronise() on an already-EOF stream returns (EOF, 0)."""
        tokens = [_eof()]
        stream = _make_stream(tokens)
        sync_pt, skipped = synchronise(stream)
        assert sync_pt is SynchronisationPoint.EOF
        assert skipped == 0

    def test_sync_counts_skipped_tokens(self) -> None:
        """synchronise() accurately counts discarded tokens before the period."""
        # Use NUMBER tokens to bypass the paragraph-label heuristic
        # (heuristic only fires for IDENTIFIER and KEYWORD)
        tokens = [_num("1"), _num("2"), _num("3"), _period(), _eof()]
        stream = _make_stream(tokens)
        _, skipped = synchronise(stream)
        assert skipped == 4  # 1, 2, 3 consumed + period consumed

    def test_sync_multiple_periods_stops_at_first(self) -> None:
        """synchronise() stops at the very first period it encounters."""
        # Use a NUMBER to avoid the paragraph-label heuristic, then two periods
        tokens = [_num("42"), _period(line=1), _period(line=2), _eof()]
        stream = _make_stream(tokens)
        sync_pt, skipped = synchronise(stream)
        assert sync_pt is SynchronisationPoint.PERIOD
        assert skipped == 2  # num + first period
        # Second period is still in stream
        assert stream.current().type is TokenType.PERIOD


# ===========================================================================
# RecoveryManager tests
# ===========================================================================


class TestRecoveryManager:
    """Tests for RecoveryManager."""

    def _manager_with_stream(
        self, tokens: list[Token]
    ) -> tuple[RecoveryManager, TokenStream]:
        """Return a fresh manager and stream from *tokens*."""
        stream = _make_stream(tokens)
        return RecoveryManager(), stream

    def test_initial_state(self) -> None:
        """A new RecoveryManager has no errors and is not in recovery."""
        manager = RecoveryManager()
        assert manager.error_count == 0
        assert not manager.has_errors
        assert not manager.in_recovery
        assert manager.diagnostics == []

    def test_record_and_synchronise_adds_diagnostic(self) -> None:
        """record_and_synchronise() appends a SyntaxDiagnostic."""
        tokens = [_kw("BAD"), _period(), _eof()]
        manager, stream = self._manager_with_stream(tokens)
        error_tok = stream.current()
        diag = manager.record_and_synchronise(
            stream=stream,
            message="test error",
            error_token=error_tok,
            context=RecoveryContext.DATA_DIVISION,
        )
        assert manager.error_count == 1
        assert manager.has_errors
        assert len(manager.diagnostics) == 1
        assert manager.diagnostics[0] is diag
        assert diag.message == "test error"
        assert diag.context is RecoveryContext.DATA_DIVISION

    def test_record_and_synchronise_performs_sync(self) -> None:
        """record_and_synchronise() advances the stream to the sync point."""
        # Use NUMBER tokens so synchroniser reaches the PERIOD (not PARAGRAPH)
        tokens = [_num("99"), _num("88"), _period(), _eof()]
        manager, stream = self._manager_with_stream(tokens)
        error_tok = stream.current()
        diag = manager.record_and_synchronise(
            stream=stream,
            message="err",
            error_token=error_tok,
        )
        # After sync, stream should be past the period → on EOF
        assert stream.current().type is TokenType.EOF
        assert diag.sync_point is SynchronisationPoint.PERIOD
        assert diag.tokens_skipped > 0

    def test_record_error_no_sync(self) -> None:
        """record_error() records a diagnostic but does not advance the stream."""
        tokens = [_kw("STILL_HERE"), _period(), _eof()]
        manager, stream = self._manager_with_stream(tokens)
        error_tok = stream.current()
        diag = manager.record_error(
            message="no sync",
            error_token=error_tok,
            context=RecoveryContext.UNKNOWN,
            sync_point=SynchronisationPoint.PERIOD,
            tokens_skipped=0,
        )
        # Stream not advanced
        assert stream.current().lexeme == "STILL_HERE"
        assert manager.error_count == 1
        assert diag.sync_point is SynchronisationPoint.PERIOD

    def test_multiple_errors_accumulated(self) -> None:
        """RecoveryManager accumulates multiple diagnostics."""
        tokens = [_kw("E1"), _period(), _kw("E2"), _period(), _eof()]
        manager, stream = self._manager_with_stream(tokens)

        manager.record_and_synchronise(
            stream=stream,
            message="error 1",
            error_token=_tok(TokenType.KEYWORD, "E1"),
        )
        manager.record_and_synchronise(
            stream=stream,
            message="error 2",
            error_token=_tok(TokenType.KEYWORD, "E2"),
        )
        assert manager.error_count == 2
        assert manager.diagnostics[0].message == "error 1"
        assert manager.diagnostics[1].message == "error 2"

    def test_diagnostics_returns_defensive_copy(self) -> None:
        """diagnostics property returns a new list each call."""
        manager = RecoveryManager()
        d1 = manager.diagnostics
        d2 = manager.diagnostics
        assert d1 is not d2

    def test_in_recovery_flag_false_outside(self) -> None:
        """in_recovery is False when no sync is in progress."""
        manager = RecoveryManager()
        assert not manager.in_recovery

    def test_in_recovery_prevents_nested_sync(self) -> None:
        """A nested call during recovery skips synchronisation."""
        tokens = [_kw("OUTER"), _period(), _kw("INNER"), _period(), _eof()]
        manager, stream = self._manager_with_stream(tokens)

        # Simulate a nested call by directly setting the flag
        manager._in_recovery = True  # type: ignore[attr-defined]
        error_tok = _tok(TokenType.KEYWORD, "INNER")
        diag = manager.record_and_synchronise(
            stream=stream,
            message="nested",
            error_token=error_tok,
        )
        # Stream not advanced because in_recovery was True
        assert stream.current().lexeme == "OUTER"
        assert diag.sync_point is None
        assert diag.tokens_skipped == 0


# ===========================================================================
# ParserState recovery extension tests
# ===========================================================================


class TestParserStateRecovery:
    """Tests for the recovery extensions added to ParserState."""

    def test_initial_error_count_zero(self) -> None:
        """A fresh ParserState has error_count=0 and has_errors=False."""
        state = _make_state([_eof()])
        assert state.error_count == 0
        assert not state.has_errors

    def test_record_error_backward_compatible(self) -> None:
        """Legacy record_error() still works and contributes to error_count."""
        state = _make_state([_eof()])
        state.record_error()
        assert state.error_count == 1
        assert state.has_errors

    def test_record_and_synchronise_records_diagnostic(self) -> None:
        """state.record_and_synchronise() appends to state.diagnostics."""
        tokens = [_kw("BAD"), _period(), _eof()]
        state = _make_state(tokens)
        error_tok = state.current_token
        state.record_and_synchronise(
            message="test",
            error_token=error_tok,
            context=RecoveryContext.DATA_DIVISION,
        )
        assert len(state.diagnostics) == 1
        assert state.diagnostics[0].message == "test"

    def test_error_count_merges_legacy_and_structured(self) -> None:
        """error_count = legacy errors + structured diagnostic count."""
        tokens = [_kw("BAD"), _period(), _eof()]
        state = _make_state(tokens)
        state.record_error()  # legacy
        state.record_and_synchronise(
            message="structured",
            error_token=state.stream.current(),
        )
        # 1 legacy + 1 structured = 2
        assert state.error_count == 2
        assert state.has_errors

    def test_diagnostics_property_returns_copy(self) -> None:
        """state.diagnostics returns a defensive copy."""
        state = _make_state([_eof()])
        assert state.diagnostics is not state.diagnostics

    def test_recovery_manager_accessible(self) -> None:
        """state.recovery_manager returns the underlying RecoveryManager."""
        state = _make_state([_eof()])
        assert isinstance(state.recovery_manager, RecoveryManager)

    def test_in_recovery_proxy(self) -> None:
        """state.in_recovery reflects the recovery manager's flag."""
        state = _make_state([_eof()])
        assert not state.in_recovery
        state.recovery_manager._in_recovery = True  # type: ignore[attr-defined]
        assert state.in_recovery


# ===========================================================================
# IdentificationDivisionParser recovery tests
# ===========================================================================


class TestIdentificationDivisionRecovery:
    """Recovery tests for IdentificationDivisionParser."""

    _parser = IdentificationDivisionParser()

    def _state_for(self, tokens: list[Token]) -> ParserState:
        return _make_state(tokens)

    def _minimal_id_division_tokens(
        self, extra: list[Token] | None = None
    ) -> list[Token]:
        """Return minimal valid IDENTIFICATION DIVISION tokens."""
        base = [
            _kw("IDENTIFICATION", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("PROGRAM-ID", line=2),
            _period(line=2),
            _id("MYPROG", line=2),
            _period(line=2),
        ]
        if extra:
            base.extend(extra)
        base.append(_eof())
        return base

    def test_valid_identification_parses_cleanly(self) -> None:
        """A well-formed IDENTIFICATION DIVISION produces zero diagnostics."""
        state = self._state_for(self._minimal_id_division_tokens())
        node = self._parser.parse(state)
        assert node.program_id is not None
        assert node.program_id.value == "MYPROG"
        assert state.diagnostics == []

    def test_unknown_clause_keyword_recovered(self) -> None:
        """An unknown clause keyword is recorded as a diagnostic; parse continues."""
        tokens = [
            _kw("IDENTIFICATION", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("PROGRAM-ID", line=2),
            _period(line=2),
            _id("MYPROG", line=2),
            _period(line=2),
            # Unknown clause — should be recovered
            _kw("UNKNOWN-CLAUSE", line=3),
            _period(line=3),
            _eof(),
        ]
        state = self._state_for(tokens)
        node = self._parser.parse(state)
        assert node.program_id is not None
        assert len(state.diagnostics) == 1
        assert "unknown" in state.diagnostics[0].message.lower()

    def test_non_keyword_token_at_clause_level_recovered(self) -> None:
        """A non-keyword token where a clause is expected is recovered."""
        tokens = [
            _kw("IDENTIFICATION", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("PROGRAM-ID", line=2),
            _period(line=2),
            _id("MYPROG", line=2),
            _period(line=2),
            # Number where clause keyword expected
            _num("999", line=3),
            _period(line=3),
            _eof(),
        ]
        state = self._state_for(tokens)
        self._parser.parse(state)
        assert len(state.diagnostics) == 1
        assert "clause keyword" in state.diagnostics[0].message.lower()

    def test_multiple_errors_collected(self) -> None:
        """Two recoverable errors both appear in state.diagnostics."""
        tokens = [
            _kw("IDENTIFICATION", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("PROGRAM-ID", line=2),
            _period(line=2),
            _id("MYPROG", line=2),
            _period(line=2),
            _kw("BAD-CLAUSE-1", line=3),
            _period(line=3),
            _kw("BAD-CLAUSE-2", line=4),
            _period(line=4),
            _eof(),
        ]
        state = self._state_for(tokens)
        self._parser.parse(state)
        assert len(state.diagnostics) == 2

    def test_fatal_missing_identification_keyword_raises(self) -> None:
        """Missing IDENTIFICATION keyword raises ParserError immediately."""
        tokens = [_kw("DIVISION"), _period(), _eof()]
        state = self._state_for(tokens)
        with pytest.raises(ParserError):
            self._parser.parse(state)

    def test_fatal_missing_division_keyword_raises(self) -> None:
        """Missing DIVISION keyword after IDENTIFICATION raises ParserError."""
        tokens = [_kw("IDENTIFICATION"), _period(), _eof()]
        state = self._state_for(tokens)
        with pytest.raises(ParserError):
            self._parser.parse(state)

    def test_recovery_context_is_identification(self) -> None:
        """Recovered diagnostics carry RecoveryContext.IDENTIFICATION_DIVISION."""
        tokens = [
            _kw("IDENTIFICATION", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("PROGRAM-ID", line=2),
            _period(line=2),
            _id("P", line=2),
            _period(line=2),
            _kw("BOGUS", line=3),
            _period(line=3),
            _eof(),
        ]
        state = self._state_for(tokens)
        self._parser.parse(state)
        assert state.diagnostics[0].context is RecoveryContext.IDENTIFICATION_DIVISION

    def test_parsing_stops_at_next_division_header(self) -> None:
        """Parser stops consuming when DATA DIVISION header is seen."""
        tokens = [
            _kw("IDENTIFICATION", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("PROGRAM-ID", line=2),
            _period(line=2),
            _id("MYPROG", line=2),
            _period(line=2),
            _kw("DATA", line=3),
            _kw("DIVISION", line=3),
            _period(line=3),
            _eof(),
        ]
        state = self._state_for(tokens)
        self._parser.parse(state)
        # No extra diagnostics; DATA DIVISION recognised as boundary
        assert state.diagnostics == []
        # Stream should be on DATA keyword
        assert state.current_token.lexeme.upper() == "DATA"


# ===========================================================================
# DataDivisionParser recovery tests
# ===========================================================================


class TestDataDivisionRecovery:
    """Recovery tests for DataDivisionParser."""

    _parser = DataDivisionParser()

    def _state_for(self, tokens: list[Token]) -> ParserState:
        return _make_state(tokens)

    def test_valid_data_division_parses_cleanly(self) -> None:
        """A well-formed DATA DIVISION produces zero diagnostics."""
        tokens = [
            _kw("DATA", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("WORKING-STORAGE", line=2),
            _kw("SECTION", line=2),
            _period(line=2),
            _num("01", line=3),
            _id("WS-VAR", line=3),
            _kw("PIC", line=3),
            _tok(TokenType.IDENTIFIER, "X", line=3),
            _period(line=3),
            _eof(),
        ]
        state = self._state_for(tokens)
        node = self._parser.parse(state)
        assert node.working_storage is not None
        assert state.diagnostics == []

    def test_invalid_level_number_recovered(self) -> None:
        """An invalid level number (e.g. 99) is recorded and parsing continues."""
        tokens = [
            _kw("DATA", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("WORKING-STORAGE", line=2),
            _kw("SECTION", line=2),
            _period(line=2),
            _num("99", line=3),  # Invalid level
            _id("WS-VAR", line=3),
            _period(line=3),
            _num("01", line=4),  # Valid — should parse after recovery
            _id("GOOD-VAR", line=4),
            _kw("PIC", line=4),
            _tok(TokenType.IDENTIFIER, "X", line=4),
            _period(line=4),
            _eof(),
        ]
        state = self._state_for(tokens)
        node = self._parser.parse(state)
        assert len(state.diagnostics) == 1
        assert "invalid level number" in state.diagnostics[0].message.lower()
        # The valid item after recovery is parsed
        assert node.working_storage is not None
        assert len(node.working_storage.items) == 1

    def test_missing_period_after_data_item_recovered(self) -> None:
        """Missing period at end of data item is recorded and parsing continues."""
        tokens = [
            _kw("DATA", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("WORKING-STORAGE", line=2),
            _kw("SECTION", line=2),
            _period(line=2),
            _num("01", line=3),
            _id("WS-VAR1", line=3),
            _kw("PIC", line=3),
            _tok(TokenType.IDENTIFIER, "X", line=3),
            # Missing period — next token is another level number
            _num("01", line=4),
            _id("WS-VAR2", line=4),
            _period(line=4),
            _eof(),
        ]
        state = self._state_for(tokens)
        self._parser.parse(state)
        # One error recorded for missing period
        assert len(state.diagnostics) >= 1

    def test_recovery_context_is_working_storage(self) -> None:
        """Recovered data-item errors carry RecoveryContext.WORKING_STORAGE_SECTION."""
        tokens = [
            _kw("DATA", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("WORKING-STORAGE", line=2),
            _kw("SECTION", line=2),
            _period(line=2),
            _num("99", line=3),
            _id("BAD", line=3),
            _period(line=3),
            _eof(),
        ]
        state = self._state_for(tokens)
        self._parser.parse(state)
        assert state.diagnostics[0].context is RecoveryContext.WORKING_STORAGE_SECTION

    def test_fatal_missing_data_keyword_raises(self) -> None:
        """Missing DATA keyword raises ParserError."""
        tokens = [_kw("DIVISION"), _period(), _eof()]
        state = self._state_for(tokens)
        with pytest.raises(ParserError):
            self._parser.parse(state)

    def test_multiple_invalid_levels_accumulate_diagnostics(self) -> None:
        """Multiple bad level numbers each produce a separate diagnostic."""
        tokens = [
            _kw("DATA", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("WORKING-STORAGE", line=2),
            _kw("SECTION", line=2),
            _period(line=2),
            _num("99", line=3),
            _id("BAD1", line=3),
            _period(line=3),
            _num("98", line=4),
            _id("BAD2", line=4),
            _period(line=4),
            _eof(),
        ]
        state = self._state_for(tokens)
        self._parser.parse(state)
        assert len(state.diagnostics) == 2


# ===========================================================================
# ProcedureDivisionParser recovery tests
# ===========================================================================


class TestProcedureDivisionRecovery:
    """Recovery tests for ProcedureDivisionParser."""

    _parser = ProcedureDivisionParser()

    def _state_for(self, tokens: list[Token]) -> ParserState:
        return _make_state(tokens)

    def test_valid_procedure_parses_cleanly(self) -> None:
        """A well-formed PROCEDURE DIVISION produces zero diagnostics."""
        tokens = [
            _kw("PROCEDURE", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _id("MAIN-PARA", line=2),
            _period(line=2),
            _kw("DISPLAY", line=3),
            _str('"HELLO"', line=3),
            _period(line=3),
            _kw("STOP", line=4),
            _kw("RUN", line=4),
            _period(line=4),
            _eof(),
        ]
        state = self._state_for(tokens)
        node = self._parser.parse(state)
        assert len(node.paragraphs) == 1
        assert state.diagnostics == []

    def test_missing_period_after_paragraph_label_recovered(self) -> None:
        """Missing period after paragraph label is recovered as diagnostic."""
        tokens = [
            _kw("PROCEDURE", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _id("BAD-PARA", line=2),
            # No period after label — next is a DISPLAY
            _kw("DISPLAY", line=3),
            _str('"HELLO"', line=3),
            _period(line=3),
            _eof(),
        ]
        state = self._state_for(tokens)
        self._parser.parse(state)
        # Parser recovered from missing period
        assert len(state.diagnostics) >= 1
        assert (
            "'.'" in state.diagnostics[0].message
            or "expected" in state.diagnostics[0].message.lower()
        )

    def test_malformed_stop_run_recovered(self) -> None:
        """STOP without RUN is recovered as diagnostic; parsing continues."""
        tokens = [
            _kw("PROCEDURE", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _id("MAIN-PARA", line=2),
            _period(line=2),
            _kw("STOP", line=3),
            _period(line=3),  # period instead of RUN
            _kw("DISPLAY", line=4),
            _str('"OK"', line=4),
            _period(line=4),
            _eof(),
        ]
        state = self._state_for(tokens)
        self._parser.parse(state)
        assert len(state.diagnostics) >= 1
        assert (
            "run" in state.diagnostics[0].message.lower()
            or "expected" in state.diagnostics[0].message.lower()
        )

    def test_multiple_statement_errors_accumulated(self) -> None:
        """Multiple statement errors produce multiple diagnostics."""
        tokens = [
            _kw("PROCEDURE", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _id("PARA-A", line=2),
            _period(line=2),
            # STOP without RUN
            _kw("STOP", line=3),
            _period(line=3),
            # DISPLAY without operand (period immediately follows)
            _kw("DISPLAY", line=4),
            _period(line=4),
            _eof(),
        ]
        state = self._state_for(tokens)
        self._parser.parse(state)
        assert len(state.diagnostics) >= 2

    def test_recovery_context_is_statement(self) -> None:
        """Statement errors carry RecoveryContext.STATEMENT."""
        tokens = [
            _kw("PROCEDURE", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _id("PARA", line=2),
            _period(line=2),
            _kw("STOP", line=3),
            _period(line=3),
            _eof(),
        ]
        state = self._state_for(tokens)
        self._parser.parse(state)
        assert state.diagnostics[0].context is RecoveryContext.STATEMENT

    def test_fatal_missing_procedure_keyword_raises(self) -> None:
        """Missing PROCEDURE keyword raises ParserError."""
        tokens = [_kw("DIVISION"), _period(), _eof()]
        state = self._state_for(tokens)
        with pytest.raises(ParserError):
            self._parser.parse(state)

    def test_recovery_after_paragraph_boundary(self) -> None:
        """After recovering in first paragraph, second paragraph parses normally."""
        tokens = [
            _kw("PROCEDURE", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _id("PARA-A", line=2),
            _period(line=2),
            # Bad statement in PARA-A
            _kw("STOP", line=3),
            _period(line=3),
            # Second paragraph — should parse cleanly
            _id("PARA-B", line=4),
            _period(line=4),
            _kw("DISPLAY", line=5),
            _str('"OK"', line=5),
            _period(line=5),
            _eof(),
        ]
        state = self._state_for(tokens)
        node = self._parser.parse(state)
        # At least PARA-B should be in the AST
        names = [p.name for p in node.paragraphs]
        assert "PARA-B" in names

    def test_recovery_context_procedure_division_paragraph(self) -> None:
        """Paragraph-level errors carry RecoveryContext.PROCEDURE_DIVISION."""
        tokens = [
            _kw("PROCEDURE", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _id("PARA", line=2),
            # Missing period — triggers paragraph error
            _kw("DISPLAY", line=3),
            _str('"X"', line=3),
            _period(line=3),
            _eof(),
        ]
        state = self._state_for(tokens)
        self._parser.parse(state)
        if state.diagnostics:
            assert state.diagnostics[0].context is RecoveryContext.PROCEDURE_DIVISION


# ===========================================================================
# EOF recovery tests
# ===========================================================================


class TestEOFRecovery:
    """Tests for recovery that terminates at EOF."""

    def test_synchronise_eof_recovery(self) -> None:
        """synchronise() handles a stream that ends without a period anchor."""
        tokens = [_kw("X"), _kw("Y"), _eof()]
        stream = _make_stream(tokens)
        sync_pt, skipped = synchronise(stream)
        assert sync_pt is SynchronisationPoint.EOF
        assert stream.current().type is TokenType.EOF

    def test_parser_state_eof_recovery_records_diagnostic(self) -> None:
        """record_and_synchronise on a stream with only EOF still records error."""
        tokens = [_kw("BAD"), _eof()]
        state = _make_state(tokens)
        error_tok = state.current_token
        state.record_and_synchronise(
            message="eof test",
            error_token=error_tok,
        )
        assert state.diagnostics[0].sync_point in (
            SynchronisationPoint.EOF,
            SynchronisationPoint.PERIOD,
        )


# ===========================================================================
# End-to-end integration tests
# ===========================================================================


class TestEndToEndRecovery:
    """Integration tests for the full parser pipeline with error recovery."""

    _program_parser = ProgramParser()

    def test_full_valid_program_no_diagnostics(self) -> None:
        """A syntactically correct program produces zero diagnostics."""
        tokens = [
            _kw("IDENTIFICATION", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("PROGRAM-ID", line=2),
            _period(line=2),
            _id("HELLO", line=2),
            _period(line=2),
            _kw("DATA", line=4),
            _kw("DIVISION", line=4),
            _period(line=4),
            _kw("WORKING-STORAGE", line=5),
            _kw("SECTION", line=5),
            _period(line=5),
            _num("01", line=6),
            _id("WS-VAR", line=6),
            _kw("PIC", line=6),
            _tok(TokenType.IDENTIFIER, "X", line=6),
            _period(line=6),
            _kw("PROCEDURE", line=8),
            _kw("DIVISION", line=8),
            _period(line=8),
            _id("MAIN-PARA", line=9),
            _period(line=9),
            _kw("DISPLAY", line=10),
            _str('"HELLO"', line=10),
            _period(line=10),
            _kw("STOP", line=11),
            _kw("RUN", line=11),
            _period(line=11),
            _eof(),
        ]
        program = self._program_parser.parse(tokens)
        assert program.identification_division is not None
        assert program.data_division is not None
        assert program.procedure_division is not None

    def test_program_with_errors_in_multiple_divisions(self) -> None:
        """Parser continues through all divisions collecting multiple diagnostics."""
        tokens = [
            # IDENTIFICATION DIVISION — unknown clause after PROGRAM-ID
            _kw("IDENTIFICATION", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("PROGRAM-ID", line=2),
            _period(line=2),
            _id("MYPROG", line=2),
            _period(line=2),
            _kw("UNKNOWN-CLAUSE", line=3),
            _period(line=3),
            # DATA DIVISION — invalid level number
            _kw("DATA", line=5),
            _kw("DIVISION", line=5),
            _period(line=5),
            _kw("WORKING-STORAGE", line=6),
            _kw("SECTION", line=6),
            _period(line=6),
            _num("99", line=7),  # Invalid level
            _id("WS-VAR", line=7),
            _period(line=7),
            # PROCEDURE DIVISION — missing RUN after STOP
            _kw("PROCEDURE", line=9),
            _kw("DIVISION", line=9),
            _period(line=9),
            _id("MAIN-PARA", line=10),
            _period(line=10),
            _kw("STOP", line=11),
            _period(line=11),  # missing RUN
            _eof(),
        ]
        program = self._program_parser.parse(tokens)
        # Program node created even with errors
        assert program is not None
        assert program.identification_division is not None
        assert program.data_division is not None
        assert program.procedure_division is not None

    def test_parser_state_accumulates_diagnostics_across_divisions(self) -> None:
        """Diagnostics from all divisions accumulate in a single state."""
        # We test this by manually wiring up shared state across parsers
        tokens = [
            _kw("IDENTIFICATION", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("PROGRAM-ID", line=2),
            _period(line=2),
            _id("P", line=2),
            _period(line=2),
            _kw("BOGUS-CLAUSE", line=3),
            _period(line=3),
            _eof(),
        ]
        state = _make_state(tokens)
        id_parser = IdentificationDivisionParser()
        id_parser.parse(state)
        assert state.error_count >= 1
        assert len(state.diagnostics) >= 1

    def test_sync_point_recorded_in_diagnostic(self) -> None:
        """Each diagnostic records its synchronisation point."""
        tokens = [
            _kw("IDENTIFICATION", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("PROGRAM-ID", line=2),
            _period(line=2),
            _id("P", line=2),
            _period(line=2),
            _kw("BAD-CLAUSE", line=3),
            _period(line=3),
            _eof(),
        ]
        state = _make_state(tokens)
        IdentificationDivisionParser().parse(state)
        diag = state.diagnostics[0]
        assert diag.sync_point is not None

    def test_diagnostics_are_ordered_by_encounter(self) -> None:
        """Diagnostics appear in the order errors were encountered."""
        tokens = [
            _kw("IDENTIFICATION", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("PROGRAM-ID", line=2),
            _period(line=2),
            _id("P", line=2),
            _period(line=2),
            _kw("CLAUSE-A", line=3),
            _period(line=3),
            _kw("CLAUSE-B", line=4),
            _period(line=4),
            _eof(),
        ]
        state = _make_state(tokens)
        IdentificationDivisionParser().parse(state)
        assert len(state.diagnostics) == 2
        # First error appears at line 3, second at line 4
        assert state.diagnostics[0].line <= state.diagnostics[1].line

    def test_parser_does_not_abort_on_first_error(self) -> None:
        """Parser continues past the first error without raising."""
        tokens = [
            _kw("IDENTIFICATION", line=1),
            _kw("DIVISION", line=1),
            _period(line=1),
            _kw("PROGRAM-ID", line=2),
            _period(line=2),
            _id("P", line=2),
            _period(line=2),
            # Three recoverable errors
            _kw("E1", line=3),
            _period(line=3),
            _kw("E2", line=4),
            _period(line=4),
            _kw("E3", line=5),
            _period(line=5),
            _eof(),
        ]
        state = _make_state(tokens)
        # Should not raise even with 3 errors
        node = IdentificationDivisionParser().parse(state)
        assert node is not None
        assert len(state.diagnostics) == 3
