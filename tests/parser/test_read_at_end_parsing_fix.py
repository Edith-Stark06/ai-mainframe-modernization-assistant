"""
Regression tests for the ``READ ... AT END`` / ``NOT AT END`` parsing defect
identified in the ``mmim-gen-v13`` audit.

Purpose:
    ``READ`` has no AST node or parser of its own -- it is one of the
    verbs in ``_UNSUPPORTED_STATEMENT_LEXEMES``, skipped as a single
    ``SYN100`` diagnostic like ``OPEN``/``CLOSE``/``WRITE``/etc. Its
    ``AT END``/``NOT AT END`` clauses legitimately contain full imperative
    statements (``MOVE``, ``ADD``, ...), the same way ``EVALUATE``'s
    ``WHEN`` clauses do -- but unlike ``EVALUATE``, ``READ`` was not given
    the scope-matching skip (``_skip_to_matching_close_word``) that
    protects a nested statement from being mistaken for the *next real
    statement*.

    Before the fix, the generic "scan to next period, but stop at the
    first statement-verb token" skip stopped the moment it reached the
    nested ``MOVE``/``ADD`` inside the ``AT END``/``NOT AT END`` clause,
    leaving the clause's remaining words (``NOT AT END``, ``END-READ``, a
    second clause's verb, ...) to be consumed by the *ordinary* statement
    parser as if they were real operand text -- producing corrupted
    identifiers like ``MoveStatementNode(target="WS-EOF-FLAG NOT AT
    END")``, which the Java backend then turned into undeclared,
    unparseable identifiers (``wsEofFlagnotatend``).

    ``ProcedureDivisionParser._skip_read_statement`` fixes this: before
    the first ``AT`` token, it behaves exactly like the generic skip
    (preserving every existing period-less-READ test); from the first
    ``AT`` onward, a statement-verb token no longer ends the skip early --
    only ``END-READ`` or a bare period does, matching real COBOL grammar
    for both of ``READ``'s two legal forms.

    These tests drive real COBOL source through ``CobolLexer`` into
    ``ProgramParser`` and assert on the resulting AST and diagnostics,
    exactly like ``tests/parser/test_statement_boundaries.py``.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.analysis.service import AnalysisService
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.program_parser import ProgramParser
from app.parser.syntax.token_stream import TokenStream

SOURCES = Path("data/sources/phase6-v2")

_HEADER = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nPROCEDURE DIVISION.\n"


def _parse(body: str, *, paragraph: str = "MAIN") -> tuple[Any, ParserState]:
    """Parse a PROCEDURE DIVISION *body* end to end."""
    source = f"{_HEADER}{paragraph}.\n{body}"
    state = ParserState(TokenStream(CobolLexer().tokenize(source, filename="t.cbl")))
    return ProgramParser()._parse_program(state), state


def _statements(program: Any) -> list[Any]:
    return [
        stmt
        for para in program.procedure_division.paragraphs
        for stmt in para.statements
    ]


def _names(program: Any) -> list[str]:
    return [type(s).__name__.replace("StatementNode", "") for s in _statements(program)]


# ===========================================================================
# 1. Normal READ (no clause at all) -- unchanged
# ===========================================================================


class TestPlainReadUnchanged:
    def test_bare_read_with_period_is_one_diagnosed_skip(self) -> None:
        program, state = _parse("    READ F1.\n    STOP RUN.\n")

        assert _names(program) == ["StopRun"]
        assert len(state.diagnostics) == 1
        assert "READ" in state.diagnostics[0].message

    def test_bare_read_without_period_does_not_absorb_the_next_statement(
        self,
    ) -> None:
        """The exact shape ``test_statement_boundaries.py`` already pins for
        ``READ`` -- must remain unaffected by this fix."""
        program, state = _parse("    OPEN INPUT F1\n    READ F1\n    STOP RUN.\n")

        assert _names(program) == ["StopRun"]
        assert len(state.diagnostics) == 2

    def test_bare_read_followed_by_supported_statement(self) -> None:
        program, _ = _parse("    READ F1.\n    MOVE 'X' TO WS-A.\n    STOP RUN.\n")
        move = _statements(program)[0]

        assert _names(program) == ["Move", "StopRun"]
        assert move.source == "'X'"
        assert move.target == "WS-A"


# ===========================================================================
# 2. READ ... AT END
# ===========================================================================


class TestReadAtEnd:
    def test_at_end_with_end_read_is_skipped_whole(self) -> None:
        program, state = _parse(
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n    END-READ.\n    STOP RUN.\n"
        )

        assert _names(program) == ["StopRun"]
        assert len(state.diagnostics) == 1
        assert not [d for d in state.diagnostics if "undefined variable" in d.message]

    def test_at_end_without_end_read_closes_at_the_period(self) -> None:
        """Real COBOL: legal without ``END-READ`` when it is the only
        statement of its sentence -- the exact shape of
        ``tests/fixtures/phase5/file_processing.cbl``."""
        program, state = _parse(
            "    READ F1 AT END MOVE 'Y' TO WS-EOF.\n    ADD 1 TO WS-COUNT.\n    STOP RUN.\n"
        )

        assert _names(program) == ["Add", "StopRun"]
        assert len(state.diagnostics) == 1

    def test_multiple_reads_in_one_paragraph_are_each_skipped_independently(
        self,
    ) -> None:
        program, state = _parse(
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n    END-READ.\n"
            "    PERFORM SUB.\n"
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n    END-READ.\n"
            "    STOP RUN.\n"
        )

        assert _names(program) == ["Perform", "StopRun"]
        assert len([d for d in state.diagnostics if "READ" in d.message]) == 2


# ===========================================================================
# 3. READ ... NOT AT END (and AT END + NOT AT END together)
# ===========================================================================


class TestReadNotAtEnd:
    def test_not_at_end_alone(self) -> None:
        program, state = _parse(
            "    READ F1 NOT AT END ADD 1 TO WS-COUNT\n    END-READ.\n    STOP RUN.\n"
        )

        assert _names(program) == ["StopRun"]
        assert len(state.diagnostics) == 1

    def test_at_end_and_not_at_end_together(self) -> None:
        """The real corpus shape (``t_batch_acct_update``)."""
        program, state = _parse(
            "    READ F1 INTO R\n"
            "        AT END MOVE 'Y' TO WS-EOF-FLAG\n"
            "        NOT AT END ADD 1 TO WS-RECORDS-READ\n"
            "    END-READ.\n"
            "    STOP RUN.\n"
        )

        assert _names(program) == ["StopRun"]
        assert len(state.diagnostics) == 1
        assert not [d for d in state.diagnostics if "undefined variable" in d.message]


# ===========================================================================
# 4. The exact real-corpus forms that produced mangled identifiers
# ===========================================================================


class TestRealCorpusForms:
    """Each of the 5 real sources with a READ, reproduced verbatim (the
    exact structure, condensed to just the READ paragraph)."""

    def test_batch_acct_update_shape(self) -> None:
        program, state = _parse(
            "    READ ACCT-IN-FILE INTO FD-ACCT-RECORD\n"
            "        AT END MOVE 'Y' TO WS-EOF-FLAG\n"
            "        NOT AT END ADD 1 TO WS-RECORDS-READ\n"
            "    END-READ.\n"
        )
        assert _statements(program) == []
        assert not [d for d in state.diagnostics if "undefined variable" in d.message]

    def test_daily_trans_report_shape(self) -> None:
        program, state = _parse(
            "    READ TX-IN-FILE INTO FD-TX-IN-RECORD\n"
            "        AT END MOVE 'Y' TO WS-EOF\n"
            "    END-READ.\n"
        )
        assert _statements(program) == []
        assert not [d for d in state.diagnostics if "undefined variable" in d.message]

    def test_inventory_extract_shape(self) -> None:
        program, state = _parse(
            "    READ INV-MASTER-FILE INTO FD-INV-RECORD\n"
            "        AT END MOVE 'Y' TO WS-INV-EOF\n"
            "    END-READ.\n"
        )
        assert _statements(program) == []
        assert not [d for d in state.diagnostics if "undefined variable" in d.message]

    def test_payroll_file_post_shape(self) -> None:
        program, state = _parse(
            "    READ EMP-IN-FILE INTO FD-EMP-RECORD\n"
            "        AT END MOVE 'Y' TO WS-PAY-EOF\n"
            "    END-READ.\n"
        )
        assert _statements(program) == []
        assert not [d for d in state.diagnostics if "undefined variable" in d.message]

    def test_file_processing_fixture_shape(self) -> None:
        """``tests/fixtures/phase5/file_processing.cbl`` -- bare-period form."""
        program, state = _parse("    READ CUST-FILE AT END MOVE 'Y' TO WS-EOF.\n")
        assert _statements(program) == []
        assert not [d for d in state.diagnostics if "undefined variable" in d.message]


@pytest.fixture(scope="module")
def real_results():
    cache: dict[str, Any] = {}

    def load(filename: str):
        if filename not in cache:
            cache[filename] = AnalysisService().analyze_file(SOURCES / filename)
        return cache[filename]

    return load


REAL_SOURCES = [
    "batch_acct_update.cbl",
    "daily_trans_report.cbl",
    "inventory_extract.cbl",
    "payroll_file_post.cbl",
]


@pytest.mark.parametrize("filename", REAL_SOURCES)
def test_real_corpus_no_mangled_identifier_remains(real_results, filename):
    """Some sources (payroll_file_post.cbl) legitimately have unrelated
    'undefined variable' diagnostics for undeclared FILE SECTION fields
    (a separate, already-documented, out-of-scope gap) -- this checks
    specifically for the READ-mangling pattern (clause words leaking into
    an identifier), not for the mere presence of any such diagnostic."""
    result = real_results(filename)
    assert not [
        d
        for d in result.semantic_diagnostics
        if "undefined variable" in d.message
        and any(w in d.message.upper() for w in ("AT END", "NOT AT", "END-READ"))
    ]
    for stmt_type in ("MoveStatementNode", "AddStatementNode"):
        for para in result.ast.procedure_division.paragraphs:
            for stmt in para.statements:
                if type(stmt).__name__ == stmt_type:
                    for attr in ("source", "target"):
                        value = getattr(stmt, attr, "") or ""
                        assert "AT END" not in value.upper(), (filename, attr, value)
                        assert "END-READ" not in value.upper(), (filename, attr, value)
                        assert " NOT " not in f" {value.upper()} ", (filename, value)


@pytest.mark.parametrize(
    ("filename", "bad_identifier"),
    [
        ("batch_acct_update.cbl", "wsEofFlagnotatend"),
        ("batch_acct_update.cbl", "wsRecordsReadendRead"),
        ("daily_trans_report.cbl", "wsEofendRead"),
        ("inventory_extract.cbl", "wsInvEofendRead"),
        ("payroll_file_post.cbl", "wsPayEofendRead"),
    ],
)
def test_real_corpus_mangled_java_identifier_no_longer_appears(
    real_results, filename, bad_identifier
):
    java = real_results(filename).java_source
    assert bad_identifier not in java, (filename, bad_identifier)


def test_real_corpus_read_is_still_recorded_as_unsupported(real_results):
    """The fix does not implement READ -- it must still be SYN100, not
    silently accepted."""
    for filename in REAL_SOURCES:
        codes = {d.code for d in real_results(filename).syntax_diagnostics}
        assert "SYN100" in codes, filename


# ===========================================================================
# 5. Ordinary identifiers are not mistakenly consumed by the new grammar
# ===========================================================================


class TestOrdinaryIdentifiersUnaffected:
    def test_a_data_name_beginning_with_at_is_not_mistaken_for_the_at_clause(
        self,
    ) -> None:
        """A data name like ``AT-RISK-FLAG`` is one IDENTIFIER token
        (``AT-RISK-FLAG``, hyphen included) -- never the bare word ``AT``
        the new grammar looks for."""
        program, state = _parse("    READ F1 INTO AT-RISK-FLAG.\n    STOP RUN.\n")
        assert _names(program) == ["StopRun"]
        assert len(state.diagnostics) == 1

    def test_move_after_a_fully_closed_read_is_ordinary(self) -> None:
        program, _ = _parse(
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n"
            "    END-READ.\n"
            "    MOVE 'Z' TO WS-B.\n"
            "    STOP RUN.\n"
        )
        move = _statements(program)[0]

        assert _names(program) == ["Move", "StopRun"]
        assert move.source == "'Z'"
        assert move.target == "WS-B"

    def test_if_statement_after_read_is_still_parsed(self) -> None:
        """The scope-close mechanism for ``READ`` must not swallow a real
        ``IF`` that follows it, the same guarantee already proven for
        ``EVALUATE`` in ``test_token_type_regressions.py``."""
        program, _ = _parse(
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n"
            "    END-READ.\n"
            "    IF WS-A = WS-B\n"
            "        DISPLAY 'X'\n"
            "    END-IF.\n"
            "    STOP RUN.\n"
        )
        assert _names(program) == ["If", "StopRun"]

    def test_at_end_of_paragraph_read_without_end_read_or_period_stops_at_boundary(
        self,
    ) -> None:
        """Defensive: if a READ's clause runs to the very end of a
        paragraph with no period and no END-READ (malformed input), the
        skip must still stop at EOF/division boundary, never hang or
        consume past the procedure division.

        The input really is malformed (its last sentence has no period), so
        besides the unsupported-``READ`` diagnostic the parser also reports
        the missing terminating period (``SYN002``, at end of input only)."""
        program, state = _parse(
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n", paragraph="ONLY-PARA"
        )
        assert _statements(program) == []
        assert [d.code for d in state.diagnostics] == ["SYN100", "SYN002"]
