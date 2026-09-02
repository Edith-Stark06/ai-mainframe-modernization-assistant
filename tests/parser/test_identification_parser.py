"""
Tests for the Identification Division Parser.

Purpose:
    Verify that the ProgramParser, IdentificationDivisionParser, and all
    related AST nodes (IdentificationDivisionNode + clause nodes) behave
    correctly in isolation and in combination.

Coverage:
    - Empty program (EOF-only) → ProgramNode with no identification division.
    - Minimal IDENTIFICATION DIVISION with PROGRAM-ID only.
    - Full IDENTIFICATION DIVISION with all six clauses.
    - Each optional clause in isolation.
    - Malformed division header (missing DIVISION keyword).
    - Missing period after IDENTIFICATION DIVISION header.
    - Missing period after PROGRAM-ID name.
    - Unknown clause keyword raises ParserError.
    - AST node immutability (frozen dataclasses).
    - AST node inheritance from ASTNode.
    - ProgramParser satisfies ParserProtocol.

Non-responsibilities:
    - Data Division or Procedure Division parsing.
    - Semantic analysis.

Dependencies:
    - :mod:`app.parser.syntax.program_parser`       — ProgramParser.
    - :mod:`app.parser.syntax.identification_parser` — IdentificationDivisionParser.
    - :mod:`app.parser.ast.identification`           — IdentificationDivisionNode.
    - :mod:`app.parser.ast.clauses`                  — clause nodes.
    - :mod:`app.parser.ast.node`                     — ASTNode.
    - :mod:`app.parser.ast.program`                  — ProgramNode.
    - :mod:`app.parser.syntax.parser_exceptions`     — ParserError.
    - :mod:`app.parser.syntax.parser_state`          — ParserState.
    - :mod:`app.parser.syntax.token_stream`          — TokenStream.
    - :mod:`app.parser.lexer.token`                  — Token.
    - :mod:`app.parser.lexer.token_types`            — TokenType.
    - :mod:`app.parser.lexer.position`               — Position.
    - :mod:`pytest`                                  — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import dataclasses
import pathlib

import pytest

from app.parser.ast.clauses import (
    AuthorClauseNode,
    DateCompiledClauseNode,
    DateWrittenClauseNode,
    InstallationClauseNode,
    ProgramIdClauseNode,
    SecurityClauseNode,
)
from app.parser.ast.identification import IdentificationDivisionNode
from app.parser.ast.node import ASTNode
from app.parser.ast.program import ProgramNode
from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.position import Position
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType
from app.parser.syntax.identification_parser import IdentificationDivisionParser
from app.parser.syntax.parser_exceptions import ParserError
from app.parser.syntax.parser_interfaces import ParserProtocol
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.program_parser import ProgramParser
from app.parser.syntax.token_stream import TokenStream

# ---------------------------------------------------------------------------
# Token-building helpers
# ---------------------------------------------------------------------------

_FILE = "test.cbl"


def _pos(line: int = 1, col: int = 1, offset: int = 0) -> Position:
    return Position(line=line, column=col, offset=offset, filename=_FILE)


def _kw(lexeme: str, line: int = 1, col: int = 1, offset: int = 0) -> Token:
    return Token(
        type=TokenType.KEYWORD, lexeme=lexeme, position=_pos(line, col, offset)
    )


def _id(lexeme: str, line: int = 1, col: int = 1, offset: int = 0) -> Token:
    return Token(
        type=TokenType.IDENTIFIER, lexeme=lexeme, position=_pos(line, col, offset)
    )


def _period(line: int = 1, col: int = 1, offset: int = 0) -> Token:
    return Token(type=TokenType.PERIOD, lexeme=".", position=_pos(line, col, offset))


def _eof(line: int = 99, col: int = 1, offset: int = 999) -> Token:
    return Token(type=TokenType.EOF, lexeme="", position=_pos(line, col, offset))


def _str_tok(lexeme: str, line: int = 1, col: int = 1, offset: int = 0) -> Token:
    return Token(type=TokenType.STRING, lexeme=lexeme, position=_pos(line, col, offset))


def _make_state(tokens: list[Token]) -> ParserState:
    return ParserState(TokenStream(tokens))


# ---------------------------------------------------------------------------
# Minimal token sequences
# ---------------------------------------------------------------------------


def _ident_header() -> list[Token]:
    """IDENTIFICATION DIVISION ."""
    return [_kw("IDENTIFICATION"), _kw("DIVISION"), _period()]


def _program_id_clause(name: str = "MYPROG") -> list[Token]:
    """PROGRAM-ID . <name> ."""
    return [_kw("PROGRAM-ID"), _period(), _id(name), _period()]


def _full_ident_tokens(name: str = "PAYROLL") -> list[Token]:
    """Full IDENTIFICATION DIVISION with PROGRAM-ID only."""
    return _ident_header() + _program_id_clause(name) + [_eof()]


# ---------------------------------------------------------------------------
# ProgramParser — empty program
# ---------------------------------------------------------------------------


class TestProgramParserEmpty:
    """ProgramParser on an EOF-only stream returns an empty ProgramNode."""

    def test_empty_stream_returns_program_node(self) -> None:
        parser = ProgramParser()
        program = parser.parse([_eof()])
        assert isinstance(program, ProgramNode)

    def test_empty_stream_has_no_identification_division(self) -> None:
        parser = ProgramParser()
        program = parser.parse([_eof()])
        assert program.identification_division is None

    def test_empty_stream_has_no_other_divisions(self) -> None:
        parser = ProgramParser()
        program = parser.parse([_eof()])
        assert program.environment_division is None
        assert program.data_division is None
        assert program.procedure_division is None

    def test_program_parser_satisfies_protocol(self) -> None:
        assert isinstance(ProgramParser(), ParserProtocol)

    def test_empty_token_list_raises(self) -> None:
        with pytest.raises(ValueError):
            ProgramParser().parse([])


# ---------------------------------------------------------------------------
# ProgramParser — IDENTIFICATION DIVISION detection
# ---------------------------------------------------------------------------


class TestProgramParserIdentification:
    """ProgramParser correctly detects and delegates identification division."""

    def test_parses_identification_division(self) -> None:
        parser = ProgramParser()
        program = parser.parse(_full_ident_tokens())
        assert program.identification_division is not None

    def test_identification_division_has_program_id(self) -> None:
        parser = ProgramParser()
        program = parser.parse(_full_ident_tokens("PAYROLL"))
        ident = program.identification_division
        assert ident is not None
        assert ident.program_id is not None
        assert ident.program_id.value == "PAYROLL"

    def test_program_node_is_astnode(self) -> None:
        parser = ProgramParser()
        program = parser.parse(_full_ident_tokens())
        assert isinstance(program, ASTNode)


# ---------------------------------------------------------------------------
# IdentificationDivisionParser — valid inputs
# ---------------------------------------------------------------------------


class TestIdentificationDivisionParserValid:
    """Correct identification division inputs produce correct AST nodes."""

    def _parse(self, tokens: list[Token]) -> IdentificationDivisionNode:
        state = _make_state(tokens)
        parser = IdentificationDivisionParser()
        return parser.parse(state)

    def test_minimal_division_with_program_id(self) -> None:
        tokens = _ident_header() + _program_id_clause("MYPROG") + [_eof()]
        node = self._parse(tokens)
        assert isinstance(node, IdentificationDivisionNode)
        assert node.program_id is not None
        assert node.program_id.value == "MYPROG"

    def test_program_id_value_stored(self) -> None:
        tokens = _ident_header() + _program_id_clause("HELLO-WORLD") + [_eof()]
        node = self._parse(tokens)
        assert node.program_id is not None
        assert node.program_id.value == "HELLO-WORLD"

    def test_author_clause_parsed(self) -> None:
        tokens = (
            _ident_header()
            + _program_id_clause()
            + [_kw("AUTHOR"), _period(), _id("EDITH"), _id("STARK"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.author is not None
        assert "EDITH" in node.author.value
        assert "STARK" in node.author.value

    def test_installation_clause_parsed(self) -> None:
        tokens = (
            _ident_header()
            + _program_id_clause()
            + [_kw("INSTALLATION"), _period(), _id("HQ"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.installation is not None
        assert node.installation.value == "HQ"

    def test_date_written_clause_parsed(self) -> None:
        tokens = (
            _ident_header()
            + _program_id_clause()
            + [_kw("DATE-WRITTEN"), _period(), _id("2024-01-01"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.date_written is not None
        assert node.date_written.value == "2024-01-01"

    def test_date_compiled_clause_parsed(self) -> None:
        tokens = (
            _ident_header()
            + _program_id_clause()
            + [_kw("DATE-COMPILED"), _period(), _id("2024-02-01"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.date_compiled is not None
        assert node.date_compiled.value == "2024-02-01"

    def test_security_clause_parsed(self) -> None:
        tokens = (
            _ident_header()
            + _program_id_clause()
            + [_kw("SECURITY"), _period(), _id("CONFIDENTIAL"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.security is not None
        assert node.security.value == "CONFIDENTIAL"

    def test_all_six_clauses(self) -> None:
        tokens = (
            _ident_header()
            + _program_id_clause("FULLPROG")
            + [_kw("AUTHOR"), _period(), _id("EDITH"), _period()]
            + [_kw("INSTALLATION"), _period(), _id("LAB"), _period()]
            + [_kw("DATE-WRITTEN"), _period(), _id("2024-01-01"), _period()]
            + [_kw("DATE-COMPILED"), _period(), _id("2024-02-01"), _period()]
            + [_kw("SECURITY"), _period(), _id("SECRET"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.program_id is not None
        assert node.author is not None
        assert node.installation is not None
        assert node.date_written is not None
        assert node.date_compiled is not None
        assert node.security is not None

    def test_no_optional_clauses(self) -> None:
        tokens = _ident_header() + _program_id_clause() + [_eof()]
        node = self._parse(tokens)
        assert node.author is None
        assert node.installation is None
        assert node.date_written is None
        assert node.date_compiled is None
        assert node.security is None

    def test_identification_node_is_astnode(self) -> None:
        tokens = _ident_header() + _program_id_clause() + [_eof()]
        node = self._parse(tokens)
        assert isinstance(node, ASTNode)

    def test_start_position_is_identification_keyword(self) -> None:
        tokens = _ident_header() + _program_id_clause() + [_eof()]
        node = self._parse(tokens)
        assert node.start_position.line == 1

    def test_stops_before_next_division(self) -> None:
        """Parser stops when it sees DATA DIVISION."""
        tokens = (
            _ident_header()
            + _program_id_clause("PROG")
            + [_kw("DATA"), _kw("DIVISION"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.program_id is not None
        # DATA DIVISION not consumed — no error


# ---------------------------------------------------------------------------
# IdentificationDivisionParser — real production lexer (not hand-built
# KEYWORD tokens)
#
# Regression coverage for a real production bug: AUTHOR, INSTALLATION,
# DATE-WRITTEN, DATE-COMPILED, and SECURITY are not in CobolLexer's
# reserved-keyword set (only PROGRAM-ID is), so the real lexer emits them
# as IDENTIFIER tokens, not KEYWORD tokens. Every test above constructs
# AUTHOR/DATE-WRITTEN as hand-built KEYWORD tokens via _kw(...), which
# does not match what the real lexer actually produces -- those tests
# passed identically whether or not the parser accepted IDENTIFIER-typed
# clause names, and so never exercised (or could have caught) this bug.
# These tests drive the real CobolLexer end to end instead.
# ---------------------------------------------------------------------------


class TestIdentificationDivisionParserRealLexer:
    """
    AUTHOR/DATE-WRITTEN clauses must be accepted as the real lexer
    actually tokenises them, not as tests assume they are tokenised.
    """

    def test_real_lexer_emits_author_and_date_written_as_identifier(self) -> None:
        """
        Documents the actual lexer behaviour that caused the production
        bug: AUTHOR and DATE-WRITTEN come back as IDENTIFIER, not
        KEYWORD (unlike PROGRAM-ID, which is a real reserved keyword).
        If this ever changes, the parser-side fix below is still safe
        (it accepts either token type), but this test protects the
        premise of the other tests in this class.
        """
        tokens = CobolLexer().tokenize(
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. X.\n"
            "AUTHOR. Y.\n"
            "DATE-WRITTEN. Z.\n",
            filename="t.cbl",
        )
        by_lexeme = {t.lexeme: t.type for t in tokens}
        assert by_lexeme["PROGRAM-ID"] is TokenType.KEYWORD
        assert by_lexeme["AUTHOR"] is TokenType.IDENTIFIER
        assert by_lexeme["DATE-WRITTEN"] is TokenType.IDENTIFIER

    def test_author_and_date_written_accepted_via_real_lexer(self) -> None:
        """
        Regression test: CobolLexer.tokenize() + ProgramParser.parse()
        together previously recorded 4 diagnostics for exactly this input
        ("expected a clause keyword, got 'AUTHOR'", "...'AI-MODERNIZATION-
        TEST'", "...'DATE-WRITTEN'", "...'2026'") and left both clauses
        unparsed, because the dispatch loop required TokenType.KEYWORD.
        Must now parse with zero diagnostics and correct clause values.
        """
        tokens = CobolLexer().tokenize(
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. ACCTBATCH.\n"
            "AUTHOR. AI-MODERNIZATION-TEST.\n"
            "DATE-WRITTEN. 2026-09-02.\n",
            filename="t.cbl",
        )
        state = _make_state(tokens)
        node = IdentificationDivisionParser().parse(state)

        assert state.error_count == 0
        assert node.program_id is not None
        assert node.program_id.value == "ACCTBATCH"
        assert node.author is not None
        assert node.author.value == "AI-MODERNIZATION-TEST"
        assert node.date_written is not None
        assert "2026" in node.date_written.value

    def test_full_program_with_author_date_written_reaches_procedure_division(
        self,
    ) -> None:
        """
        Regression test proving the parser proceeds far enough to produce
        the expected subsequent divisions, AND that AUTHOR/DATE-WRITTEN
        are themselves actually parsed rather than silently dropped.

        For this specific fixture, the pre-fix parser's error recovery
        already happened to synchronise past the unparsed AUTHOR/
        DATE-WRITTEN clauses and still reach data_division and
        procedure_division -- so reachability alone would not have
        caught this bug. What recovery could not do was recover the
        clause *values*: pre-fix, this asserts author is not None and
        fails, because AUTHOR was recorded as a diagnostic and dropped,
        not parsed.

        (For the real-world file that exposed this bug,
        complex_acctbatch.cbl, reachability *is* additionally broken --
        but for a separate reason: an ENVIRONMENT DIVISION sits between
        IDENTIFICATION and DATA DIVISION, and ENVIRONMENT DIVISION
        parsing is unimplemented -- a distinct, pre-existing,
        out-of-scope limitation; see program_parser.py's own docstring.
        This fixture deliberately omits an ENVIRONMENT DIVISION so it
        isolates the identification-division fix from that unrelated
        gap.)
        """
        corpus = (
            pathlib.Path(__file__).parent
            / "corpus"
            / "identification_author_date_written.cbl"
        )
        source = corpus.read_text(encoding="utf-8")

        tokens = CobolLexer().tokenize(source, filename=str(corpus))
        program = ProgramParser().parse(tokens)

        assert program.identification_division is not None
        assert program.identification_division.author is not None
        assert program.identification_division.author.value == "AI-MODERNIZATION-TEST"
        assert program.identification_division.date_written is not None
        assert program.data_division is not None
        assert program.procedure_division is not None
        assert len(program.procedure_division.paragraphs) == 1
        assert program.procedure_division.paragraphs[0].name == "MAIN-PARA"

    def test_unrecognised_identifier_still_rejected(self) -> None:
        """
        The fix must not overly loosen validation: an IDENTIFIER-typed
        token whose lexeme is genuinely not a known clause name must
        still be rejected, exactly as an unrecognised KEYWORD already is
        (test_unknown_clause_recovers_diagnostic, above).
        """
        tokens = CobolLexer().tokenize(
            "IDENTIFICATION DIVISION.\nPROGRAM-ID. X.\nBOGUS-CLAUSE. Y.\n",
            filename="t.cbl",
        )
        state = _make_state(tokens)
        node = IdentificationDivisionParser().parse(state)

        assert state.has_errors
        assert any(
            "BOGUS-CLAUSE" in d.message or "expected a clause keyword" in d.message
            for d in state.diagnostics
        )
        assert node.program_id is not None
        assert node.program_id.value == "X"


# ---------------------------------------------------------------------------
# IdentificationDivisionParser — malformed inputs
# ---------------------------------------------------------------------------


class TestIdentificationDivisionParserMalformed:
    """Fatal errors raise ParserError; recoverable errors record diagnostics.

    After TASK-017, clause-level errors (unknown keyword, non-keyword token,
    missing period in clause body) are recovered via SyntaxDiagnostic.
    Only division-header errors remain fatal.
    """

    def _parse_expect_error(self, tokens: list[Token]) -> ParserError:
        state = _make_state(tokens)
        parser = IdentificationDivisionParser()
        with pytest.raises(ParserError) as exc_info:
            parser.parse(state)
        return exc_info.value

    def test_missing_division_keyword(self) -> None:
        """IDENTIFICATION <period> → missing DIVISION keyword."""
        tokens = [_kw("IDENTIFICATION"), _period(), _eof()]
        self._parse_expect_error(tokens)

    def test_wrong_keyword_instead_of_division(self) -> None:
        """IDENTIFICATION DATA . → wrong second keyword."""
        tokens = [_kw("IDENTIFICATION"), _kw("DATA"), _period(), _eof()]
        self._parse_expect_error(tokens)

    def test_missing_period_after_header(self) -> None:
        """IDENTIFICATION DIVISION <eof> → missing period."""
        tokens = [_kw("IDENTIFICATION"), _kw("DIVISION"), _eof()]
        self._parse_expect_error(tokens)

    def test_missing_period_after_program_id_name(self) -> None:
        """PROGRAM-ID . PROG <eof> → missing closing period → recovered.

        After TASK-017 the parser records a diagnostic and continues
        rather than raising ParserError.
        """
        tokens = (
            _ident_header() + [_kw("PROGRAM-ID"), _period(), _id("PROG")] + [_eof()]
        )
        state = _make_state(tokens)
        parser = IdentificationDivisionParser()
        # Should not raise; missing period is a recovered diagnostic
        parser.parse(state)
        assert state.has_errors

    def test_unknown_clause_recovers_diagnostic(self) -> None:
        """An unknown KEYWORD in clause position records a diagnostic.

        After TASK-017 the parser records a SyntaxDiagnostic and continues
        rather than raising ParserError.
        """
        tokens = (
            _ident_header()
            + _program_id_clause()
            + [_kw("UNKNOWN-CLAUSE"), _period(), _id("VALUE"), _period()]
            + [_eof()]
        )
        state = _make_state(tokens)
        parser = IdentificationDivisionParser()
        parser.parse(state)
        assert state.has_errors
        diag_messages = " ".join(d.message for d in state.diagnostics)
        assert "unknown" in diag_messages.lower() or "UNKNOWN-CLAUSE" in diag_messages

    def test_non_keyword_in_clause_position_recovers(self) -> None:
        """A non-KEYWORD token in clause position records a diagnostic.

        After TASK-017 the parser records a SyntaxDiagnostic and continues.
        """
        tokens = (
            _ident_header()
            + _program_id_clause()
            + [_id("NOT-A-KEYWORD"), _period(), _eof()]
        )
        state = _make_state(tokens)
        parser = IdentificationDivisionParser()
        parser.parse(state)
        assert state.has_errors

    def test_eof_after_header_no_program_id(self) -> None:
        """IDENTIFICATION DIVISION . <eof> → program_id is None (no crash)."""
        tokens = _ident_header() + [_eof()]
        state = _make_state(tokens)
        parser = IdentificationDivisionParser()
        node = parser.parse(state)
        assert node.program_id is None

    def test_program_id_missing_name_recovers(self) -> None:
        """PROGRAM-ID . . → no name token → diagnostic recorded.

        After TASK-017 the parser records a SyntaxDiagnostic and continues.
        program_id will be None since it could not be parsed.
        """
        tokens = _ident_header() + [_kw("PROGRAM-ID"), _period(), _period(), _eof()]
        state = _make_state(tokens)
        parser = IdentificationDivisionParser()
        node = parser.parse(state)
        assert state.has_errors
        assert node.program_id is None


# ---------------------------------------------------------------------------
# AST Node — immutability
# ---------------------------------------------------------------------------


class TestASTImmutability:
    """All new AST nodes are frozen dataclasses."""

    _POS = _pos()

    def test_program_id_clause_is_frozen(self) -> None:
        node = ProgramIdClauseNode(
            start_position=self._POS, end_position=self._POS, value="X"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.value = "Y"  # type: ignore[misc]

    def test_author_clause_is_frozen(self) -> None:
        node = AuthorClauseNode(
            start_position=self._POS, end_position=self._POS, value="A"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.value = "B"  # type: ignore[misc]

    def test_installation_clause_is_frozen(self) -> None:
        node = InstallationClauseNode(
            start_position=self._POS, end_position=self._POS, value="I"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.value = "J"  # type: ignore[misc]

    def test_date_written_clause_is_frozen(self) -> None:
        node = DateWrittenClauseNode(
            start_position=self._POS, end_position=self._POS, value="D"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.value = "E"  # type: ignore[misc]

    def test_date_compiled_clause_is_frozen(self) -> None:
        node = DateCompiledClauseNode(
            start_position=self._POS, end_position=self._POS, value="D"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.value = "E"  # type: ignore[misc]

    def test_security_clause_is_frozen(self) -> None:
        node = SecurityClauseNode(
            start_position=self._POS, end_position=self._POS, value="S"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.value = "T"  # type: ignore[misc]

    def test_identification_division_node_is_frozen(self) -> None:
        node = IdentificationDivisionNode(
            start_position=self._POS, end_position=self._POS
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.program_id = None  # type: ignore[misc]

    def test_all_clause_nodes_are_astnodes(self) -> None:
        for cls in (
            ProgramIdClauseNode,
            AuthorClauseNode,
            InstallationClauseNode,
            DateWrittenClauseNode,
            DateCompiledClauseNode,
            SecurityClauseNode,
        ):
            node = cls(start_position=self._POS, end_position=self._POS, value="v")
            assert isinstance(node, ASTNode), f"{cls.__name__} not an ASTNode"

    def test_identification_division_node_is_astnode(self) -> None:
        node = IdentificationDivisionNode(
            start_position=self._POS, end_position=self._POS
        )
        assert isinstance(node, ASTNode)


# ---------------------------------------------------------------------------
# AST Node — field defaults
# ---------------------------------------------------------------------------


class TestIdentificationDivisionNodeDefaults:
    """IdentificationDivisionNode defaults all clause fields to None."""

    _POS = _pos()

    def test_all_clauses_none_by_default(self) -> None:
        node = IdentificationDivisionNode(
            start_position=self._POS, end_position=self._POS
        )
        assert node.program_id is None
        assert node.author is None
        assert node.installation is None
        assert node.date_written is None
        assert node.date_compiled is None
        assert node.security is None

    def test_program_id_set(self) -> None:
        pid = ProgramIdClauseNode(
            start_position=self._POS, end_position=self._POS, value="PROG"
        )
        node = IdentificationDivisionNode(
            start_position=self._POS, end_position=self._POS, program_id=pid
        )
        assert node.program_id is pid


# ---------------------------------------------------------------------------
# Visitor dispatch via accept()
# ---------------------------------------------------------------------------


class TestVisitorDispatch:
    """accept() on new nodes dispatches to the correct visitor method."""

    _POS = _pos()

    def test_program_id_accept_dispatches(self) -> None:
        visited: list[ProgramIdClauseNode] = []

        class V:
            def visit_program_id_clause(self, n: ProgramIdClauseNode) -> None:
                visited.append(n)

        node = ProgramIdClauseNode(
            start_position=self._POS, end_position=self._POS, value="X"
        )
        node.accept(V())
        assert len(visited) == 1
        assert visited[0] is node

    def test_identification_division_accept_dispatches(self) -> None:
        visited: list[IdentificationDivisionNode] = []

        class V:
            def visit_identification_division(
                self, n: IdentificationDivisionNode
            ) -> None:
                visited.append(n)

        node = IdentificationDivisionNode(
            start_position=self._POS, end_position=self._POS
        )
        node.accept(V())
        assert len(visited) == 1

    def test_accept_returns_none_for_unknown_visitor(self) -> None:
        node = ProgramIdClauseNode(
            start_position=self._POS, end_position=self._POS, value="Y"
        )
        result = node.accept(object())
        assert result is None
