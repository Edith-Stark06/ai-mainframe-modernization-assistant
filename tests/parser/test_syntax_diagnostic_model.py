"""
Tests for the structured syntax diagnostic model (task #108-03).

Purpose:
    Lock in the classification vocabulary added on top of
    :class:`~app.parser.diagnostics.recovery.SyntaxDiagnostic`: a
    registered ``code``, a ``severity``, and a derived ``category``.
    These fields are authoritative -- consumers must never need to parse
    ``message`` text to tell a syntax error from an unsupported
    construct.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.parser.diagnostics.recovery import (
    SYNTAX_DIAGNOSTIC_CODES,
    RecoveryContext,
    SyntaxCategory,
    SyntaxDiagnostic,
    SyntaxSeverity,
)
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.program_parser import ProgramParser
from app.parser.syntax.token_stream import TokenStream

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nPROCEDURE DIVISION.\nMAIN.\n"


def _diagnostics_for(source: str) -> list[SyntaxDiagnostic]:
    """Parse *source* and return the syntax diagnostics recorded."""
    state = ParserState(TokenStream(CobolLexer().tokenize(source, filename="t.cbl")))
    ProgramParser()._parse_program(state)
    return state.diagnostics


# ===========================================================================
# A — diagnostic model
# ===========================================================================


class TestSyntaxDiagnosticModel:
    """Structural properties of the diagnostic value type and registry."""

    def test_has_severity_field(self) -> None:
        """SyntaxDiagnostic carries a structured severity."""
        diag = SyntaxDiagnostic(
            message="x",
            line=1,
            column=1,
            offset=0,
            filename="t.cbl",
            context=RecoveryContext.UNKNOWN,
            sync_point=None,
            tokens_skipped=0,
            severity=SyntaxSeverity.WARNING,
            code="SYN100",
        )
        assert diag.severity is SyntaxSeverity.WARNING

    def test_has_code_field(self) -> None:
        """SyntaxDiagnostic carries a structured code."""
        diag = SyntaxDiagnostic(
            message="x",
            line=1,
            column=1,
            offset=0,
            filename="t.cbl",
            context=RecoveryContext.UNKNOWN,
            sync_point=None,
            tokens_skipped=0,
            code="SYN200",
        )
        assert diag.code == "SYN200"

    def test_category_is_derived_from_registered_code(self) -> None:
        """`category` looks up the registry rather than being stored twice."""
        diag = SyntaxDiagnostic(
            message="x",
            line=1,
            column=1,
            offset=0,
            filename="t.cbl",
            context=RecoveryContext.UNKNOWN,
            sync_point=None,
            tokens_skipped=0,
            code="SYN100",
        )
        assert diag.category is SyntaxCategory.UNSUPPORTED

    def test_every_registered_code_has_a_category_and_severity(self) -> None:
        """The registry itself is well-formed."""
        assert len(SYNTAX_DIAGNOSTIC_CODES) > 0
        for code, spec in SYNTAX_DIAGNOSTIC_CODES.items():
            assert isinstance(spec.category, SyntaxCategory), code
            assert isinstance(spec.severity, SyntaxSeverity), code
            assert spec.description, code

    def test_registry_covers_all_four_required_distinctions(self) -> None:
        """
        The registry must be able to express: syntax errors, unsupported
        syntax, unmodelled-but-valid syntax, and a recoverable/warning
        condition.
        """
        categories = {spec.category for spec in SYNTAX_DIAGNOSTIC_CODES.values()}
        assert categories == {
            SyntaxCategory.SYNTAX_ERROR,
            SyntaxCategory.UNSUPPORTED,
            SyntaxCategory.UNMODELLED,
            SyntaxCategory.ABANDONED,
        }
        severities = {spec.severity for spec in SYNTAX_DIAGNOSTIC_CODES.values()}
        assert SyntaxSeverity.WARNING in severities

    def test_str_matches_semantic_diagnostic_convention(self) -> None:
        """
        __str__ follows the same
        "<file>:<line>:<col> [<SEVERITY> <code>] <message>" shape as
        SemanticDiagnostic, not the old plain "<file>:<line>:<col>: <msg>".
        """
        diag = SyntaxDiagnostic(
            message="unexpected token",
            line=10,
            column=1,
            offset=200,
            filename="x.cbl",
            context=RecoveryContext.DATA_DIVISION,
            sync_point=None,
            tokens_skipped=0,
            severity=SyntaxSeverity.ERROR,
            code="SYN001",
        )
        text = str(diag)
        assert text == "x.cbl:10:1 [ERROR SYN001] unexpected token"

    def test_original_fields_are_preserved(self) -> None:
        """message/line/column/offset/filename/context/sync_point/tokens_skipped."""
        diag = SyntaxDiagnostic(
            message="expected '.'",
            line=3,
            column=5,
            offset=42,
            filename="prog.cbl",
            context=RecoveryContext.IDENTIFICATION_DIVISION,
            sync_point=None,
            tokens_skipped=2,
        )
        assert diag.message == "expected '.'"
        assert diag.line == 3
        assert diag.column == 5
        assert diag.offset == 42
        assert diag.filename == "prog.cbl"
        assert diag.context is RecoveryContext.IDENTIFICATION_DIVISION
        assert diag.tokens_skipped == 2


# ===========================================================================
# B — classification (structured fields, never message text)
# ===========================================================================


class TestDiagnosticClassification:
    """
    Each case below is chosen from the audit's own examples.  Every
    assertion reads ``.severity``/``.code``/``.category`` -- never
    ``.message`` -- proving classification does not require parsing
    English text.
    """

    def test_open_is_classified_unsupported(self) -> None:
        """OPEN: valid COBOL, not implemented -> UNSUPPORTED / WARNING."""
        diags = _diagnostics_for(_ID + "    OPEN INPUT F1.\n    STOP RUN.\n")
        target = next(d for d in diags if "OPEN" in d.message)

        assert target.category is SyntaxCategory.UNSUPPORTED
        assert target.severity is SyntaxSeverity.WARNING
        assert target.code == "SYN100"

    def test_if_not_equals_is_classified_syntax_error(self) -> None:
        """IF A NOT = B: malformed grammar -> SYNTAX_ERROR / ERROR."""
        diags = _diagnostics_for(_ID + '    IF A NOT = B DISPLAY "x" END-IF.\n')
        assert len(diags) == 1
        target = diags[0]

        assert target.category is SyntaxCategory.SYNTAX_ERROR
        assert target.severity is SyntaxSeverity.ERROR

    def test_comp_3_is_classified_unmodelled(self) -> None:
        """COMP-3: parsed and understood, but the AST has no field for it."""
        source = (
            _ID.replace("PROCEDURE DIVISION.\nMAIN.\n", "")
            + "DATA DIVISION.\nWORKING-STORAGE SECTION.\n"
            "01 WS-AMOUNT PIC S9(7)V99 COMP-3.\n"
            "PROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n"
        )
        diags = _diagnostics_for(source)
        target = next(d for d in diags if "COMP-3" in d.message)

        assert target.category is SyntaxCategory.UNMODELLED
        assert target.severity is SyntaxSeverity.WARNING
        assert target.code == "SYN200"

    def test_categories_are_distinguishable_without_reading_message(self) -> None:
        """The three cases above must land in three different categories."""
        open_diags = _diagnostics_for(_ID + "    OPEN INPUT F1.\n    STOP RUN.\n")
        if_diags = _diagnostics_for(_ID + '    IF A NOT = B DISPLAY "x" END-IF.\n')

        open_cat = next(d for d in open_diags if "OPEN" in d.message).category
        if_cat = if_diags[0].category

        assert open_cat is not if_cat
        assert {open_cat, if_cat} == {
            SyntaxCategory.UNSUPPORTED,
            SyntaxCategory.SYNTAX_ERROR,
        }
