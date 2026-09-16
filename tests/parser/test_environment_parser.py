"""
Tests for the COBOL ENVIRONMENT DIVISION parser.

Purpose:
    Verify that :class:`~app.parser.syntax.environment_parser.EnvironmentDivisionParser`
    recognises the ENVIRONMENT DIVISION and, critically, that its
    presence no longer prevents
    :class:`~app.parser.syntax.program_parser.ProgramParser` from
    reaching the DATA and PROCEDURE divisions.

    Every regression test here drives the **real**
    :class:`~app.parser.lexer.lexer.CobolLexer` rather than
    hand-constructed token streams.  The bug these tests guard against
    is only observable through real lexer output: ``CONFIGURATION``,
    ``INPUT-OUTPUT`` and even ``SECTION`` are not reserved keywords, so
    they arrive as ``TokenType.IDENTIFIER``.  Hand-built ``KEYWORD``
    tokens would not reproduce production behaviour.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pathlib

import pytest

from app.parser.ast.division import DivisionNode
from app.parser.diagnostics.recovery import RecoveryContext
from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType
from app.parser.syntax.environment_parser import EnvironmentDivisionParser
from app.parser.syntax.parser_exceptions import ParserError
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.program_parser import ProgramParser
from app.parser.syntax.token_stream import TokenStream

_CORPUS = pathlib.Path(__file__).parent / "corpus"


def _tokenize(source: str) -> list[Token]:
    """Tokenise *source* with the real production lexer."""
    return CobolLexer().tokenize(source, filename="t.cbl")


def _make_state(tokens: list[Token]) -> ParserState:
    """Build a ParserState over *tokens*."""
    return ParserState(TokenStream(tokens))


# A minimal ENVIRONMENT DIVISION using the constructs that actually
# appear in the real complex_acctbatch.cbl program.
_ENV_SOURCE = (
    "ENVIRONMENT DIVISION.\n"
    "CONFIGURATION SECTION.\n"
    "SOURCE-COMPUTER. IBM-Z.\n"
    "OBJECT-COMPUTER. IBM-Z.\n"
    "INPUT-OUTPUT SECTION.\n"
    "FILE-CONTROL.\n"
    "    SELECT ACCOUNT-FILE ASSIGN TO ACCTIN\n"
    "        ORGANIZATION IS SEQUENTIAL\n"
    "        FILE STATUS IS WS-ACCT-STATUS.\n"
)


# ===========================================================================
# Lexer premise
# ===========================================================================


class TestLexerPremise:
    """The token types these tests and the parser fix depend on."""

    def test_environment_section_names_are_not_reserved_keywords(self) -> None:
        """
        Documents the real lexer classification the parser must cope
        with: only ENVIRONMENT and DIVISION are reserved keywords.  The
        section names — and ``SECTION`` itself — arrive as IDENTIFIER,
        which is why the parser matches them by uppercased lexeme (the
        same approach ``data_parser`` already uses for ``SECTION``).
        """
        by_lexeme = {t.lexeme.upper(): t.type for t in _tokenize(_ENV_SOURCE)}
        assert by_lexeme["ENVIRONMENT"] is TokenType.KEYWORD
        assert by_lexeme["DIVISION"] is TokenType.KEYWORD
        assert by_lexeme["CONFIGURATION"] is TokenType.IDENTIFIER
        assert by_lexeme["INPUT-OUTPUT"] is TokenType.IDENTIFIER
        assert by_lexeme["SECTION"] is TokenType.IDENTIFIER


# ===========================================================================
# EnvironmentDivisionParser unit behaviour
# ===========================================================================


class TestEnvironmentDivisionParser:
    """Direct tests of the ENVIRONMENT DIVISION sub-parser."""

    def test_returns_environment_division_node(self) -> None:
        """
        The division is represented by the pre-existing generic
        DivisionNode named "ENVIRONMENT" — the type ``ProgramNode``
        already declared for its ``environment_division`` field.
        """
        state = _make_state(_tokenize(_ENV_SOURCE))
        node = EnvironmentDivisionParser().parse(state)

        assert isinstance(node, DivisionNode)
        assert node.name == "ENVIRONMENT"

    def test_supported_sections_produce_no_diagnostics(self) -> None:
        """
        CONFIGURATION SECTION and INPUT-OUTPUT SECTION, including their
        paragraph bodies and SELECT clauses, are accepted cleanly.
        """
        state = _make_state(_tokenize(_ENV_SOURCE))
        EnvironmentDivisionParser().parse(state)

        assert state.diagnostics == []
        assert state.error_count == 0

    def test_children_are_empty_by_design(self) -> None:
        """
        The representation is deliberately limited: nothing downstream
        of the parser reads ENVIRONMENT metadata yet, so section
        contents are consumed but not modelled.  This test pins that
        contract so a future change to it is a conscious decision
        rather than an accident.
        """
        state = _make_state(_tokenize(_ENV_SOURCE))
        node = EnvironmentDivisionParser().parse(state)

        assert node.children == ()

    def test_stops_on_next_division_header_without_consuming_it(self) -> None:
        """
        The parser must hand the DATA DIVISION header back to
        ProgramParser untouched — this is precisely what makes the
        subsequent divisions reachable.
        """
        source = _ENV_SOURCE + "DATA DIVISION.\nWORKING-STORAGE SECTION.\n"
        state = _make_state(_tokenize(source))
        EnvironmentDivisionParser().parse(state)

        assert state.stream.current().lexeme.upper() == "DATA"
        assert state.stream.peek().lexeme.upper() == "DIVISION"

    def test_bare_environment_division_is_valid(self) -> None:
        """An ENVIRONMENT DIVISION with no sections at all is accepted."""
        state = _make_state(_tokenize("ENVIRONMENT DIVISION.\nDATA DIVISION.\n"))
        node = EnvironmentDivisionParser().parse(state)

        assert node.name == "ENVIRONMENT"
        assert state.diagnostics == []
        assert state.stream.current().lexeme.upper() == "DATA"

    def test_unsupported_section_records_exactly_one_diagnostic(self) -> None:
        """
        An unrecognised section is reported rather than silently
        swallowed — but its body must not generate a diagnostic per
        token.
        """
        source = (
            "ENVIRONMENT DIVISION.\n"
            "BOGUS SECTION.\n"
            "SOME-PARAGRAPH. FILLER TEXT HERE.\n"
            "DATA DIVISION.\n"
        )
        state = _make_state(_tokenize(source))
        EnvironmentDivisionParser().parse(state)

        assert len(state.diagnostics) == 1
        diag = state.diagnostics[0]
        assert "BOGUS" in diag.message
        assert diag.context is RecoveryContext.ENVIRONMENT_DIVISION
        # Still recovers to the next division.
        assert state.stream.current().lexeme.upper() == "DATA"

    def test_division_level_junk_is_not_silently_swallowed(self) -> None:
        """
        Content at division level that is not a section header at all
        must produce a diagnostic.  This is the guard against "fix" by
        blind token-skipping to DATA DIVISION.
        """
        source = "ENVIRONMENT DIVISION.\nTOTALLY BOGUS CONTENT\nDATA DIVISION.\n"
        state = _make_state(_tokenize(source))
        EnvironmentDivisionParser().parse(state)

        assert state.diagnostics, "malformed content was swallowed silently"
        assert all(
            d.context is RecoveryContext.ENVIRONMENT_DIVISION for d in state.diagnostics
        )
        assert state.stream.current().lexeme.upper() == "DATA"

    def test_does_not_hang_on_section_anchor_keyword(self) -> None:
        """
        ``synchronise()`` anchors on section keywords *without consuming
        them*, and WORKING-STORAGE is both a reserved lexer keyword and
        such an anchor.  Without the parser's explicit forward-progress
        guard this input loops forever, so this test is a hang
        regression, not a correctness nicety.
        """
        source = "ENVIRONMENT DIVISION.\nWORKING-STORAGE\nDATA DIVISION.\n"
        state = _make_state(_tokenize(source))

        EnvironmentDivisionParser().parse(state)

        assert state.diagnostics
        assert state.stream.current().lexeme.upper() == "DATA"

    def test_malformed_header_is_fatal(self) -> None:
        """
        A malformed division header raises, matching
        IdentificationDivisionParser's established behaviour.
        """
        state = _make_state(_tokenize("ENVIRONMENT SECTION.\n"))
        with pytest.raises(ParserError):
            EnvironmentDivisionParser().parse(state)


# ===========================================================================
# ProgramParser integration — the actual production regression
# ===========================================================================


class TestProgramParserWithEnvironmentDivision:
    """
    End-to-end: an ENVIRONMENT DIVISION must not stop the program parser
    before the DATA and PROCEDURE divisions.
    """

    @staticmethod
    def _parse_corpus(name: str) -> object:
        source = (_CORPUS / name).read_text()
        return ProgramParser().parse(CobolLexer().tokenize(source, filename=name))

    def test_full_program_reaches_all_divisions(self) -> None:
        """
        The core regression.  Before this change ProgramParser checked
        for IDENTIFICATION, then DATA, then PROCEDURE in sequence with
        no ENVIRONMENT branch, so an ENVIRONMENT DIVISION sitting
        between IDENTIFICATION and DATA left the cursor stranded and
        both later divisions came back None — with no diagnostic to
        explain why.
        """
        program = self._parse_corpus("environment_division_full.cbl")

        assert program.identification_division is not None
        assert program.environment_division is not None
        assert program.data_division is not None, "ENVIRONMENT blocked DATA DIVISION"
        assert (
            program.procedure_division is not None
        ), "ENVIRONMENT blocked PROCEDURE DIVISION"

    def test_environment_division_node_is_populated(self) -> None:
        """``ProgramNode.environment_division`` is now actually filled in."""
        program = self._parse_corpus("environment_division_full.cbl")

        assert isinstance(program.environment_division, DivisionNode)
        assert program.environment_division.name == "ENVIRONMENT"

    def test_data_division_content_is_correct(self) -> None:
        """
        The DATA DIVISION is genuinely parsed, not merely non-None, and
        the ENVIRONMENT DIVISION's SELECT/ASSIGN identifiers do not leak
        into it as spurious data items.
        """
        program = self._parse_corpus("environment_division_full.cbl")

        working_storage = program.data_division.working_storage
        assert working_storage is not None
        assert len(working_storage.items) == 1
        assert working_storage.items[0].name == "WS-ACCT-STATUS"

    def test_procedure_division_content_is_correct(self) -> None:
        """The PROCEDURE DIVISION's paragraph and statements are parsed."""
        program = self._parse_corpus("environment_division_full.cbl")

        paragraphs = program.procedure_division.paragraphs
        assert [p.name for p in paragraphs] == ["MAIN-PARA"]
        assert len(paragraphs[0].statements) == 2

    def test_environment_division_parses_without_diagnostics(self) -> None:
        """The whole fixture parses cleanly end to end."""
        source = (_CORPUS / "environment_division_full.cbl").read_text()
        state = _make_state(CobolLexer().tokenize(source, filename="env.cbl"))
        ProgramParser()._parse_program(state)

        assert state.diagnostics == []

    def test_bare_environment_division_between_divisions(self) -> None:
        """
        A section-less ENVIRONMENT DIVISION (the shape used by the
        existing mixed_program.cbl corpus file) is also transparent.
        """
        source = (
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. BARE.\n"
            "ENVIRONMENT DIVISION.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-X PIC X(01).\n"
            "PROCEDURE DIVISION.\n"
            "MAIN-PARA.\n"
            "    STOP RUN.\n"
        )
        program = ProgramParser().parse(_tokenize(source))

        assert program.environment_division is not None
        assert program.data_division is not None
        assert program.procedure_division is not None


class TestProgramsWithoutEnvironmentDivision:
    """Programs with no ENVIRONMENT DIVISION must be unaffected."""

    def test_environment_division_is_none_when_absent(self) -> None:
        """
        ``environment_division`` stays None and the other divisions are
        parsed exactly as before this change.
        """
        source = (_CORPUS / "identification_author_date_written.cbl").read_text()
        program = ProgramParser().parse(
            CobolLexer().tokenize(source, filename="ident.cbl")
        )

        assert program.environment_division is None
        assert program.identification_division is not None
        assert program.data_division is not None
        assert program.procedure_division is not None

    def test_minimal_program_still_parses(self) -> None:
        """A program with only IDENTIFICATION is still valid."""
        source = "IDENTIFICATION DIVISION.\nPROGRAM-ID. ONLYID.\n"
        program = ProgramParser().parse(_tokenize(source))

        assert program.identification_division is not None
        assert program.environment_division is None
        assert program.data_division is None
        assert program.procedure_division is None
