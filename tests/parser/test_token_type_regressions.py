"""
Regression tests for the #104 token-type audit fixes (task #105).

Purpose:
    Lock in the parser corrections for the grammar words that the lexer
    emits as ``TokenType.IDENTIFIER`` rather than ``TokenType.KEYWORD``.

    Every test drives the real pipeline — COBOL source text through
    :class:`~app.parser.lexer.lexer.CobolLexer` into
    :class:`~app.parser.syntax.program_parser.ProgramParser` — because
    the defects are only observable through real lexer output.
    Hand-built ``KEYWORD`` tokens would not reproduce them.

    Each area is covered by a positive case, an AST-content assertion, a
    diagnostics assertion, and a *negative* case proving that an
    arbitrary user-defined name is still not treated as grammar.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pathlib
import threading
from typing import Any

from app.parser.diagnostics.recovery import (
    RecoveryContext,
    SynchronisationPoint,
    synchronise,
)
from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.token import Token
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.program_parser import ProgramParser
from app.parser.syntax.token_stream import TokenStream

_CORPUS = pathlib.Path(__file__).parent / "corpus"

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\n"
_WS_HEADER = "DATA DIVISION.\nWORKING-STORAGE SECTION.\n"
_PROC = "PROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n"


def _tokenize(source: str) -> list[Token]:
    """Tokenise *source* with the real production lexer."""
    return CobolLexer().tokenize(source, filename="t.cbl")


def _parse(source: str) -> tuple[Any, ParserState]:
    """Parse *source* end to end, returning ``(program, state)``."""
    state = ParserState(TokenStream(_tokenize(source)))
    program = ProgramParser()._parse_program(state)
    return program, state


def _items(program: Any) -> tuple[Any, ...]:
    """Return the WORKING-STORAGE items of *program*, or ``()``."""
    if program.data_division is None:
        return ()
    storage = program.data_division.working_storage
    return storage.items if storage is not None else ()


def _one_item(source_line: str) -> tuple[Any, ParserState]:
    """Parse a single WORKING-STORAGE entry and return it with the state."""
    program, state = _parse(_ID + _WS_HEADER + source_line + _PROC)
    items = _items(program)
    assert len(items) == 1, f"expected exactly one data item, got {len(items)}"
    return items[0], state


# ===========================================================================
# Part 1 — section boundaries
# ===========================================================================


class TestUnsupportedSectionHandling:
    """
    An unsupported DATA DIVISION section must be skipped, not treated as
    the end of the division.

    Before #105 the ``_UNSUPPORTED_SECTION_KEYWORDS`` check sat behind
    ``if tok.type is TokenType.KEYWORD``.  None of those six names is a
    reserved lexer word, so the branch was unreachable; the parser fell
    into its "unexpected token" path and stopped inside the section,
    losing every later section and the PROCEDURE DIVISION with it.
    """

    def test_file_section_does_not_hide_working_storage(self) -> None:
        """WORKING-STORAGE after FILE SECTION is still parsed."""
        source = (
            _ID
            + "DATA DIVISION.\n"
            + "FILE SECTION.\nFD INPUT-FILE.\n01 INPUT-REC PIC X(100).\n"
            + "WORKING-STORAGE SECTION.\n01 WS-COUNT PIC 9(4).\n"
            + _PROC
        )
        program, _ = _parse(source)

        assert [i.name for i in _items(program)] == ["WS-COUNT"]

    def test_file_section_does_not_hide_procedure_division(self) -> None:
        """The PROCEDURE DIVISION is still reached, with its statements."""
        source = (
            _ID
            + "DATA DIVISION.\nFILE SECTION.\nFD F.\n01 R PIC X(1).\n"
            + "WORKING-STORAGE SECTION.\n01 WS-COUNT PIC 9(4).\n"
            + "PROCEDURE DIVISION.\nMAIN.\n    DISPLAY WS-COUNT.\n    STOP RUN.\n"
        )
        program, _ = _parse(source)

        assert program.procedure_division is not None
        paragraphs = program.procedure_division.paragraphs
        assert [p.name for p in paragraphs] == ["MAIN"]
        assert len(paragraphs[0].statements) == 2

    def test_unsupported_section_is_reported_explicitly(self) -> None:
        """Exactly one meaningful diagnostic, not one per skipped token."""
        source = (
            _ID
            + "DATA DIVISION.\nFILE SECTION.\nFD F.\n01 R PIC X(1).\n"
            + "WORKING-STORAGE SECTION.\n01 WS-COUNT PIC 9(4).\n"
            + _PROC
        )
        _, state = _parse(source)

        assert len(state.diagnostics) == 1
        diagnostic = state.diagnostics[0]
        assert "FILE" in diagnostic.message
        assert "skipped" in diagnostic.message
        assert diagnostic.context is RecoveryContext.DATA_DIVISION

    def test_linkage_section_is_also_skipped(self) -> None:
        """The fix covers every name in the unsupported-section set."""
        source = (
            _ID
            + "DATA DIVISION.\nLINKAGE SECTION.\n01 L1 PIC X(1).\n"
            + "WORKING-STORAGE SECTION.\n01 WS-COUNT PIC 9(4).\n"
            + _PROC
        )
        program, state = _parse(source)

        assert [i.name for i in _items(program)] == ["WS-COUNT"]
        assert any("LINKAGE" in d.message for d in state.diagnostics)

    def test_data_item_named_file_is_not_a_section_boundary(self) -> None:
        """
        Negative case.  ``FILE`` is only a section header when followed
        by ``SECTION``; a data item that happens to be *named* FILE must
        still parse as a data item.  This is what stops the fix from
        degenerating into "any IDENTIFIER may be grammar".
        """
        source = _ID + _WS_HEADER + "01 FILE PIC X(4).\n01 WS-COUNT PIC 9(4).\n" + _PROC
        program, state = _parse(source)

        assert [i.name for i in _items(program)] == ["FILE", "WS-COUNT"]
        assert state.diagnostics == []

    def test_working_storage_only_program_is_unchanged(self) -> None:
        """Programs with no unsupported section behave exactly as before."""
        program, state = _parse(_ID + _WS_HEADER + "01 WS-COUNT PIC 9(4).\n" + _PROC)

        assert [i.name for i in _items(program)] == ["WS-COUNT"]
        assert state.diagnostics == []


class TestMandatorySectionFixture:
    """End-to-end coverage of the #105 fixture."""

    @staticmethod
    def _parse_fixture() -> tuple[Any, ParserState]:
        source = (_CORPUS / "data_sections_and_clauses.cbl").read_text()
        state = ParserState(
            TokenStream(CobolLexer().tokenize(source, filename="fixture.cbl"))
        )
        return ProgramParser()._parse_program(state), state

    def test_all_divisions_present(self) -> None:
        """Nothing in the DATA DIVISION blocks the divisions after it."""
        program, _ = self._parse_fixture()

        assert program.identification_division is not None
        assert program.environment_division is not None
        assert program.data_division is not None
        assert program.procedure_division is not None

    def test_working_storage_items_and_pictures(self) -> None:
        """
        All three WORKING-STORAGE items survive the FILE SECTION, and
        none of their picture strings absorbed a following clause.
        """
        program, _ = self._parse_fixture()
        items = _items(program)

        assert [i.name for i in items] == ["WS-COUNT", "WS-AMOUNT", "WS-ALT"]
        assert [i.picture for i in items] == ["9(4)", "S9(7)V99", "X(5)"]

    def test_procedure_statements_survive(self) -> None:
        """DISPLAY and STOP RUN remain available to downstream stages."""
        program, _ = self._parse_fixture()
        paragraphs = program.procedure_division.paragraphs

        assert [p.name for p in paragraphs] == ["MAIN"]
        assert len(paragraphs[0].statements) == 2


# ===========================================================================
# Part 2 — recovery forward progress
# ===========================================================================


class TestRecoveryForwardProgress:
    """
    Recovery must always terminate.  ``synchronise()`` anchors on a
    section header *without consuming it*, so a loop that recovers at
    such a token and then re-inspects it would spin forever.  Making the
    six IDENTIFIER-typed section names reachable (Part 1) newly exposed
    that path, so every recovery loop now guards forward progress.
    """

    @staticmethod
    def _parse_with_deadline(source: str, seconds: float = 10.0) -> ParserState:
        """Parse in a worker thread, failing the test if it does not finish."""
        state = ParserState(TokenStream(_tokenize(source)))
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
            "parser did not terminate within "
            f"{seconds}s — recovery lost forward progress"
        )
        if error:
            raise error[0]
        return state

    def test_section_anchor_without_section_word_terminates(self) -> None:
        """
        ``WORKING-STORAGE`` with no following ``SECTION`` is the exact
        zero-progress case: it is both a reserved word and a recovery
        section anchor.
        """
        source = _ID + "DATA DIVISION.\nWORKING-STORAGE\n" + _PROC
        state = self._parse_with_deadline(source)

        assert state.diagnostics

    def test_unknown_section_name_terminates(self) -> None:
        """An unrecognised section is skipped rather than looping."""
        source = (
            _ID
            + "DATA DIVISION.\nBOGUS SECTION.\n01 X PIC X(1).\n"
            + "WORKING-STORAGE SECTION.\n01 WS-COUNT PIC 9(4).\n"
            + _PROC
        )
        state = self._parse_with_deadline(source)

        assert any("BOGUS" in d.message for d in state.diagnostics)

    def test_synchronise_anchors_on_identifier_typed_section(self) -> None:
        """
        Unit-level proof of F-06: recovery can now stop at ``FILE
        SECTION``.  Previously the anchor was behind a KEYWORD gate and
        recovery ran past it into the next division.
        """
        tokens = _tokenize("JUNK\nFILE SECTION.\n01 A PIC X(1).\n")
        stream = TokenStream(tokens)

        sync_point, _ = synchronise(stream)

        assert sync_point is SynchronisationPoint.SECTION
        assert stream.current().lexeme.upper() == "FILE"

    def test_synchronise_does_not_anchor_on_bare_section_name(self) -> None:
        """
        Negative case: ``FILE`` not followed by ``SECTION`` is not a
        boundary, so recovery must not stop there.
        """
        tokens = _tokenize("JUNK FILE STATUS IS WS-S.\n")
        stream = TokenStream(tokens)

        sync_point, _ = synchronise(stream)

        assert sync_point is not SynchronisationPoint.SECTION


# ===========================================================================
# Parts 3-5 — PICTURE clause integrity
# ===========================================================================


class TestPictureClauseIntegrity:
    """
    Optional and following grammar words must not end up inside the
    picture string.  Every corrupted value below was produced by the
    pre-#105 parser with **no diagnostic at all**.
    """

    def test_pic_short_form(self) -> None:
        """The already-working baseline still works."""
        item, state = _one_item("01 A PIC X(10).\n")

        assert item.picture == "X(10)"
        assert state.diagnostics == []

    def test_picture_long_form(self) -> None:
        """``PICTURE`` is IDENTIFIER-typed and was previously rejected."""
        item, state = _one_item("01 A PICTURE X(10).\n")

        assert item.picture == "X(10)"
        assert state.diagnostics == []

    def test_optional_is_after_pic(self) -> None:
        """``PIC IS X(10)`` previously produced picture ``'ISX(10)'``."""
        item, state = _one_item("01 A PIC IS X(10).\n")

        assert item.picture == "X(10)"
        assert state.diagnostics == []

    def test_optional_is_after_picture_long_form(self) -> None:
        """Both optional words combined."""
        item, state = _one_item("01 A PICTURE IS X(10).\n")

        assert item.picture == "X(10)"
        assert state.diagnostics == []

    def test_value_clause_still_parsed(self) -> None:
        """VALUE is unaffected by the picture-terminator change."""
        item, _ = _one_item("01 A PIC 9(2) VALUE 5.\n")

        assert item.picture == "9(2)"
        assert item.value == "5"

    def test_optional_is_after_value(self) -> None:
        """``VALUE IS 5`` previously dropped the whole data item."""
        item, state = _one_item("01 A PIC 9(2) VALUE IS 5.\n")

        assert item.picture == "9(2)"
        assert item.value == "5"
        assert state.diagnostics == []

    def test_editing_characters_are_not_treated_as_clause_words(self) -> None:
        """
        Negative case: a picture string is only terminated by a real
        clause word, so editing characters survive intact.
        """
        item, state = _one_item("01 A PIC ZZZ,ZZ9.\n")

        assert item.picture == "ZZZ,ZZ9"
        assert state.diagnostics == []

    def test_clause_word_inside_a_literal_is_not_a_clause(self) -> None:
        """
        Negative case: a clause word appearing inside a VALUE literal is
        data, not grammar, and must not trigger clause handling.
        """
        item, state = _one_item('01 A PIC X(9) VALUE "REDEFINES".\n')

        assert item.picture == "X(9)"
        assert item.value == '"REDEFINES"'
        assert state.diagnostics == []


class TestUnmodelledClauseTermination:
    """
    Clauses the AST cannot represent must terminate the picture string
    and be reported, never absorbed into it.
    """

    def test_comp_3_does_not_enter_picture(self) -> None:
        """Previously ``'S9(7)V99COMP-3'`` with no diagnostic."""
        item, state = _one_item("01 A PIC S9(7)V99 COMP-3.\n")

        assert item.picture == "S9(7)V99"
        assert len(state.diagnostics) == 1
        assert "COMP-3" in state.diagnostics[0].message

    def test_redefines_does_not_enter_picture(self) -> None:
        """Previously ``'X(5)REDEFINESWS-B'`` with no diagnostic."""
        item, state = _one_item("01 A PIC X(5) REDEFINES WS-B.\n")

        assert item.picture == "X(5)"
        assert any("REDEFINES" in d.message for d in state.diagnostics)

    def test_occurs_keeps_the_item(self) -> None:
        """Previously the whole data item was dropped."""
        item, state = _one_item("01 A PIC X(5) OCCURS 3 TIMES.\n")

        assert item.picture == "X(5)"
        assert any("OCCURS" in d.message for d in state.diagnostics)

    def test_justified_does_not_enter_picture(self) -> None:
        """Previously ``'X(5)JUSTIFIEDRIGHT'``."""
        item, _ = _one_item("01 A PIC X(5) JUSTIFIED RIGHT.\n")

        assert item.picture == "X(5)"

    def test_usage_is_comp_3_is_one_clause(self) -> None:
        """``USAGE [IS] COMP-3`` is reported once, not twice."""
        item, state = _one_item("01 A PIC S9(4) USAGE IS COMP-3.\n")

        assert item.picture == "S9(4)"
        assert len(state.diagnostics) == 1

    def test_clause_before_value_keeps_both(self) -> None:
        """A skipped clause must not consume a following VALUE clause."""
        item, _ = _one_item("01 A PIC S9(4) COMP-3 VALUE 0.\n")

        assert item.picture == "S9(4)"
        assert item.value == "0"

    def test_group_item_unaffected(self) -> None:
        """Items with no PIC clause are still group items."""
        program, state = _parse(_ID + _WS_HEADER + "01 A.\n  05 B PIC X(2).\n" + _PROC)
        items = _items(program)

        assert [i.name for i in items] == ["A", "B"]
        assert state.diagnostics == []


# ===========================================================================
# Part 6 — unsupported procedure statements
# ===========================================================================


class TestUnsupportedStatementHandling:
    """
    An unimplemented verb must cost one diagnostic and one statement —
    not the rest of the paragraph.  Previously the statement loop broke
    with no diagnostic at all, silently discarding everything after it.
    """

    def test_statements_after_unsupported_verb_survive(self) -> None:
        """The motivating case from the #104 audit."""
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            '    OPEN INPUT F1.\n    DISPLAY "HELLO".\n    STOP RUN.\n'
        )
        program, state = _parse(source)
        paragraph = program.procedure_division.paragraphs[0]

        assert len(paragraph.statements) == 2
        assert len(state.diagnostics) == 1
        assert "OPEN" in state.diagnostics[0].message

    def test_each_unsupported_verb_reported_once(self) -> None:
        """Several unsupported verbs interleaved with supported ones."""
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            '    OPEN INPUT F1.\n    READ F1.\n    DISPLAY "X".\n'
            "    CLOSE F1.\n    STOP RUN.\n"
        )
        program, state = _parse(source)
        paragraph = program.procedure_division.paragraphs[0]

        assert len(paragraph.statements) == 2
        assert len(state.diagnostics) == 3

    def test_scope_delimited_construct_skipped_whole(self) -> None:
        """EVALUATE ... END-EVALUATE. is skipped as a single statement."""
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            '    EVALUATE X\n    WHEN 1 DISPLAY "A"\n    END-EVALUATE.\n'
            "    STOP RUN.\n"
        )
        program, state = _parse(source)
        paragraph = program.procedure_division.paragraphs[0]

        assert len(paragraph.statements) == 1
        assert len(state.diagnostics) == 1

    def test_following_paragraph_still_parsed(self) -> None:
        """Recovery does not swallow the next paragraph."""
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    OPEN INPUT F1.\n    STOP RUN.\n"
            'SECOND-PARA.\n    DISPLAY "B".\n'
        )
        program, _ = _parse(source)
        paragraphs = program.procedure_division.paragraphs

        assert [p.name for p in paragraphs] == ["MAIN", "SECOND-PARA"]

    def test_supported_statements_unchanged(self) -> None:
        """Programs with no unsupported verb behave exactly as before."""
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            '    DISPLAY "A".\n    MOVE 1 TO X.\n    STOP RUN.\n'
        )
        program, state = _parse(source)

        assert len(program.procedure_division.paragraphs[0].statements) == 3
        assert state.diagnostics == []

    def test_unlisted_identifier_is_not_treated_as_a_statement(self) -> None:
        """
        Negative case.  Only the explicitly listed verbs are recognised;
        an arbitrary name still ends the statement list rather than being
        reported as an unsupported statement.
        """
        source = _ID + "PROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\nWIDGET-PARA.\n"
        _, state = _parse(source)

        assert not any("unsupported statement" in d.message for d in state.diagnostics)


# ===========================================================================
# Part 7 — identification clause missing period
# ===========================================================================


class TestIdentificationMissingPeriod:
    """
    #104 finding F-07: the missing-period guard was gated on
    ``TokenType.KEYWORD``, but only PROGRAM-ID is a reserved word, so an
    unterminated AUTHOR value silently absorbed the next clause name and
    that clause was lost.
    """

    def test_missing_period_is_detected_and_next_clause_survives(self) -> None:
        """
        ``AUTHOR. ME`` (no period) previously yielded
        ``author='ME DATE-WRITTEN'`` and ``date_written=None``.
        """
        source = (
            "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\n"
            "AUTHOR. ME\nDATE-WRITTEN. TODAY.\n"
        )
        program, state = _parse(source)
        identification = program.identification_division

        # The AUTHOR value is kept and no longer absorbs the next name.
        assert identification.author is not None
        assert identification.author.value == "ME"
        # ...and the clause that follows is no longer lost.
        assert identification.date_written is not None
        assert identification.date_written.value == "TODAY"
        assert any("missing period" in d.message for d in state.diagnostics)

    def test_well_formed_clauses_record_no_diagnostics(self) -> None:
        """The guard must not fire on correct input."""
        source = (
            "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\n"
            "AUTHOR. ME.\nDATE-WRITTEN. TODAY.\n"
        )
        program, state = _parse(source)
        identification = program.identification_division

        assert identification.author.value == "ME"
        assert identification.date_written.value == "TODAY"
        assert state.diagnostics == []

    def test_clause_value_may_contain_ordinary_words(self) -> None:
        """
        Negative case: only real clause names terminate a comment entry,
        so an ordinary multi-word value is preserved intact.
        """
        source = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nAUTHOR. JANE DOE TEAM.\n"
        program, state = _parse(source)

        assert program.identification_division.author.value == "JANE DOE TEAM"
        assert state.diagnostics == []
