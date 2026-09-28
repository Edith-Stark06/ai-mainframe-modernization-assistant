"""
``READ ... AT END`` / ``NOT AT END`` parsing.

Purpose:
    Originally (``mmim-gen-v13``/``v14``) this file pinned a defect fix in
    the *discard* path: ``READ`` had no AST node, so its ``AT END``/``NOT
    AT END`` clauses were skipped as one opaque unit, and a dedicated
    boundary-tracking skip (``_skip_read_statement``) was needed to keep
    that discard from corrupting the *next* real statement's operand
    text. See ``docs/MMIM_READ_AT_END_PARSING_FIX.md`` for that history.

    Task #stage40 gives ``READ`` a real parser and AST node
    (``ReadStatementNode``) — ``_skip_read_statement`` is now unreachable
    (removed) and every shape this file used to pin as "correctly
    discarded, no corruption" is rewritten here as "correctly
    *represented*, no corruption". The corruption risk did not
    disappear with real parsing — it reappeared in a new form: a nested
    statement's own operand reader (e.g. ``MOVE``'s target-accumulation
    loop) does not know ``END-READ``/``NOT`` end *its* operand unless
    those lexemes are in the shared operand-boundary set. This was found
    and fixed during this stage's own implementation (measured directly,
    not assumed) by adding both to ``_SCOPE_TERMINATOR_LEXEMES``.

    This backend has no file-reading runtime (task #stage40's own
    explicit scope decision — see the Stage 40 discovery report): every
    ``READ`` is modelled as always reaching end-of-file, so only
    ``at_end_statements`` is ever lowered past the AST (IR, dependency
    analysis, Java) — ``not_at_end_statements`` is captured here in full
    for AST fidelity but is provably unreachable under this model. These
    tests are parser/AST-level only; see
    ``tests/ir/test_stage40_read_at_end_ir.py`` and
    ``tests/backend/test_stage40_read_at_end_java.py`` for the
    lowering/Java coverage.

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
from app.parser.ast.statements import ReadStatementNode
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
# 1. Normal READ (no clause at all)
# ===========================================================================


class TestPlainRead:
    def test_bare_read_with_period_is_represented_no_diagnostic(self) -> None:
        program, state = _parse("    READ F1.\n    STOP RUN.\n")

        assert _names(program) == ["Read", "StopRun"]
        assert state.diagnostics == []
        read = _statements(program)[0]
        assert read.target == "F1"
        assert read.at_end_statements == ()
        assert read.not_at_end_statements == ()

    def test_bare_read_without_period_does_not_absorb_the_next_statement(
        self,
    ) -> None:
        """The exact shape ``test_statement_boundaries.py`` already pins
        for ``READ`` -- must remain unaffected."""
        program, state = _parse("    OPEN INPUT F1\n    READ F1\n    STOP RUN.\n")

        assert _names(program) == ["Read", "StopRun"]
        # Only OPEN remains unsupported; READ is no longer SYN100.
        assert len(state.diagnostics) == 1
        assert "OPEN" in state.diagnostics[0].message

    def test_bare_read_followed_by_supported_statement(self) -> None:
        program, _ = _parse("    READ F1.\n    MOVE 'X' TO WS-A.\n    STOP RUN.\n")
        stmts = _statements(program)

        assert _names(program) == ["Read", "Move", "StopRun"]
        assert stmts[1].source == "'X'"
        assert stmts[1].target == "WS-A"


# ===========================================================================
# 2. READ ... AT END
# ===========================================================================


class TestReadAtEnd:
    def test_at_end_with_end_read_is_represented(self) -> None:
        program, state = _parse(
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n    END-READ.\n    STOP RUN.\n"
        )

        assert _names(program) == ["Read", "StopRun"]
        assert state.diagnostics == []
        read = _statements(program)[0]
        assert len(read.at_end_statements) == 1
        move = read.at_end_statements[0]
        assert move.source == "'Y'"
        assert move.target == "WS-EOF"

    def test_at_end_without_end_read_closes_at_the_period(self) -> None:
        """Real COBOL: legal without ``END-READ`` when it is the only
        statement of its sentence -- the exact shape of
        ``tests/fixtures/phase5/file_processing.cbl``. The following
        ``ADD`` is a separate, ordinary statement of the paragraph, not
        part of the READ's own clause."""
        program, state = _parse(
            "    READ F1 AT END MOVE 'Y' TO WS-EOF.\n    ADD 1 TO WS-COUNT.\n    STOP RUN.\n"
        )

        assert _names(program) == ["Read", "Add", "StopRun"]
        assert state.diagnostics == []
        read = _statements(program)[0]
        assert len(read.at_end_statements) == 1
        assert read.at_end_statements[0].target == "WS-EOF"

    def test_multiple_reads_in_one_paragraph_are_each_represented_independently(
        self,
    ) -> None:
        program, state = _parse(
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n    END-READ.\n"
            "    PERFORM SUB.\n"
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n    END-READ.\n"
            "    STOP RUN.\n"
        )

        assert _names(program) == ["Read", "Perform", "Read", "StopRun"]
        assert state.diagnostics == []


# ===========================================================================
# 3. READ ... NOT AT END (and AT END + NOT AT END together)
# ===========================================================================


class TestReadNotAtEnd:
    def test_not_at_end_alone(self) -> None:
        program, state = _parse(
            "    READ F1 NOT AT END ADD 1 TO WS-COUNT\n    END-READ.\n    STOP RUN.\n"
        )

        assert _names(program) == ["Read", "StopRun"]
        assert state.diagnostics == []
        read = _statements(program)[0]
        assert read.at_end_statements == ()
        assert len(read.not_at_end_statements) == 1
        assert read.not_at_end_statements[0].right == "WS-COUNT"

    def test_at_end_and_not_at_end_together(self) -> None:
        """The real corpus shape (``t_batch_acct_update``) -- no
        corruption between the two clauses (the exact defect this
        stage's own implementation found and fixed: without ``NOT``/
        ``END-READ`` in the operand-boundary set, the AT END clause's
        MOVE absorbed "NOT AT END" as target text)."""
        program, state = _parse(
            "    READ F1 INTO R\n"
            "        AT END MOVE 'Y' TO WS-EOF-FLAG\n"
            "        NOT AT END ADD 1 TO WS-RECORDS-READ\n"
            "    END-READ.\n"
            "    STOP RUN.\n"
        )

        assert _names(program) == ["Read", "StopRun"]
        assert state.diagnostics == []
        read = _statements(program)[0]
        assert read.into_target == "R"
        assert len(read.at_end_statements) == 1
        assert read.at_end_statements[0].target == "WS-EOF-FLAG"
        assert len(read.not_at_end_statements) == 1
        assert read.not_at_end_statements[0].right == "WS-RECORDS-READ"


# ===========================================================================
# 4. The exact real-corpus forms
# ===========================================================================


class TestRealCorpusForms:
    """Each of the 4 real sources with a READ, reproduced verbatim (the
    exact structure, condensed to just the READ paragraph)."""

    def test_batch_acct_update_shape(self) -> None:
        program, state = _parse(
            "    READ ACCT-IN-FILE INTO FD-ACCT-RECORD\n"
            "        AT END MOVE 'Y' TO WS-EOF-FLAG\n"
            "        NOT AT END ADD 1 TO WS-RECORDS-READ\n"
            "    END-READ.\n"
        )
        (read,) = _statements(program)
        assert read.target == "ACCT-IN-FILE"
        assert read.at_end_statements[0].target == "WS-EOF-FLAG"
        assert read.not_at_end_statements[0].right == "WS-RECORDS-READ"
        assert state.diagnostics == []

    def test_daily_trans_report_shape(self) -> None:
        program, state = _parse(
            "    READ TX-IN-FILE INTO FD-TX-IN-RECORD\n"
            "        AT END MOVE 'Y' TO WS-EOF\n"
            "    END-READ.\n"
        )
        (read,) = _statements(program)
        assert read.at_end_statements[0].target == "WS-EOF"
        assert state.diagnostics == []

    def test_inventory_extract_shape(self) -> None:
        program, state = _parse(
            "    READ INV-MASTER-FILE INTO FD-INV-RECORD\n"
            "        AT END MOVE 'Y' TO WS-INV-EOF\n"
            "    END-READ.\n"
        )
        (read,) = _statements(program)
        assert read.at_end_statements[0].target == "WS-INV-EOF"
        assert state.diagnostics == []

    def test_payroll_file_post_shape(self) -> None:
        program, state = _parse(
            "    READ EMP-IN-FILE INTO FD-EMP-RECORD\n"
            "        AT END MOVE 'Y' TO WS-PAY-EOF\n"
            "    END-READ.\n"
        )
        (read,) = _statements(program)
        assert read.at_end_statements[0].target == "WS-PAY-EOF"
        assert state.diagnostics == []

    def test_file_processing_fixture_shape(self) -> None:
        """``tests/fixtures/phase5/file_processing.cbl`` -- bare-period
        form, no ``INTO``."""
        program, state = _parse("    READ CUST-FILE AT END MOVE 'Y' TO WS-EOF.\n")
        (read,) = _statements(program)
        assert read.into_target == ""
        assert read.at_end_statements[0].target == "WS-EOF"
        assert state.diagnostics == []


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
def test_real_corpus_no_corrupted_identifier(real_results, filename):
    """No mangled identifier -- the corruption class this stage's own
    implementation found and fixed (not the original discard-path
    defect, which is structurally impossible to reintroduce now that
    READ is a real AST node)."""
    result = real_results(filename)
    for para in result.ast.procedure_division.paragraphs:
        for stmt in para.statements:
            if not isinstance(stmt, ReadStatementNode):
                continue
            for clause in (stmt.at_end_statements, stmt.not_at_end_statements):
                for nested in clause:
                    for attr in ("source", "target", "left", "right"):
                        value = getattr(nested, attr, "") or ""
                        assert "AT END" not in value.upper(), (filename, attr, value)
                        assert "END-READ" not in value.upper(), (filename, attr, value)
                        assert " NOT " not in f" {value.upper()} ", (filename, value)


@pytest.mark.parametrize("filename", REAL_SOURCES)
def test_real_corpus_read_is_no_longer_syn100(real_results, filename):
    """task #stage40: READ is fully parsed now, not SYN100."""
    read_diags = [
        d
        for d in real_results(filename).syntax_diagnostics
        if "READ" in d.message.upper() and d.code == "SYN100"
    ]
    assert read_diags == [], filename


# ===========================================================================
# 5. Ordinary identifiers are not mistakenly consumed by the grammar
# ===========================================================================


class TestOrdinaryIdentifiersUnaffected:
    def test_a_data_name_beginning_with_at_is_not_mistaken_for_the_at_clause(
        self,
    ) -> None:
        """A data name like ``AT-RISK-FLAG`` is one IDENTIFIER token
        (hyphen included) -- never the bare word ``AT`` the grammar
        looks for."""
        program, state = _parse("    READ F1 INTO AT-RISK-FLAG.\n    STOP RUN.\n")
        assert _names(program) == ["Read", "StopRun"]
        assert state.diagnostics == []
        read = _statements(program)[0]
        assert read.into_target == "AT-RISK-FLAG"
        assert read.at_end_statements == ()

    def test_move_after_a_fully_closed_read_is_ordinary(self) -> None:
        program, _ = _parse(
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n"
            "    END-READ.\n"
            "    MOVE 'Z' TO WS-B.\n"
            "    STOP RUN.\n"
        )
        stmts = _statements(program)

        assert _names(program) == ["Read", "Move", "StopRun"]
        assert stmts[1].source == "'Z'"
        assert stmts[1].target == "WS-B"

    def test_if_statement_after_read_is_still_parsed(self) -> None:
        program, _ = _parse(
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n"
            "    END-READ.\n"
            "    IF WS-A = WS-B\n"
            "        DISPLAY 'X'\n"
            "    END-IF.\n"
            "    STOP RUN.\n"
        )
        assert _names(program) == ["Read", "If", "StopRun"]

    def test_at_end_of_paragraph_read_without_end_read_or_period_reports_missing_period(
        self,
    ) -> None:
        """Defensive: malformed input (last sentence has no period) is
        still reported (``SYN002``), never hangs, never consumes past
        the procedure division. READ itself is no longer SYN100 (it is
        a real statement now)."""
        program, state = _parse(
            "    READ F1 AT END MOVE 'Y' TO WS-EOF\n", paragraph="ONLY-PARA"
        )
        (read,) = _statements(program)
        assert len(read.at_end_statements) == 1
        assert [d.code for d in state.diagnostics] == ["SYN002"]
