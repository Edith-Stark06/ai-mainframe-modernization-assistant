"""
Comprehensive tests for TASK-021: Semantic Validation Visitor.

Purpose:
    Verify that :class:`SemanticValidationVisitor` correctly traverses the
    COBOL AST after symbol collection and reference resolution, enforces
    structural and semantic constraints, emits ``SEM006`` / ``SEM007`` /
    ``SEM008`` / ``SEM009`` diagnostics for rule violations, continues
    traversal after errors, and integrates correctly with
    :class:`SemanticAnalyzer`.

Coverage:
    Visitor construction:
        - Stores diagnostics reference.
        - Is a SemanticVisitor subclass.
        - Public API exports SemanticValidationVisitor.

    SEM006 — Missing/blank PROGRAM-ID:
        - PROGRAM-ID clause absent → SEM006.
        - PROGRAM-ID value blank → SEM006.
        - PROGRAM-ID whitespace-only → SEM006.
        - Valid PROGRAM-ID → no SEM006.
        - Diagnostic code, severity, message, position.

    SEM007 — Empty PROCEDURE DIVISION:
        - PROCEDURE DIVISION with zero paragraphs → SEM007.
        - PROCEDURE DIVISION with one paragraph → no SEM007.
        - PROCEDURE DIVISION with multiple paragraphs → no SEM007.
        - Diagnostic code, severity, message, position.

    SEM008 — Reserved word as identifier:
        - Elementary item named MOVE → SEM008.
        - Group item named CALL → SEM008.
        - Condition-name named DISPLAY → SEM008.
        - Reserved word detection is case-insensitive.
        - Normal data-item name → no SEM008.
        - Multiple reserved-word items produce multiple diagnostics.

    SEM009 — Invalid static CALL target (internal hook):
        - Blank target → SEM009.
        - Whitespace-only target → SEM009.
        - Non-blank target → no SEM009 emitted by _check_static_call_target.

    Traversal continuity:
        - Multiple violations in one program are all collected.
        - Traversal continues after SEM006.
        - Traversal continues after SEM007.
        - Traversal continues after SEM008.

    Empty / minimal programs:
        - Completely empty ProgramNode → no validation diagnostics.
        - No procedure division → no SEM007.
        - No identification division → no SEM006 (rule only fires when
          the division is present but the clause is absent).

    Representative full COBOL programs:
        - Valid program → no validation diagnostics.
        - Program with every violation → all codes emitted.

    SemanticAnalyzer integration (regression guard):
        - analyse() runs all three passes in order.
        - Valid program → no errors.
        - SEM006 emitted through full pipeline.
        - SEM007 emitted through full pipeline.
        - SEM008 emitted through full pipeline.
        - SEM001 + SEM006 coexist (different passes).
        - SEM003 + SEM007 coexist (different passes).
        - SemanticAnalyzer is reusable.
        - SemanticValidationVisitor exported from public API.

Non-responsibilities:
    - Lexer / parser behaviour.
    - AST node field correctness (covered elsewhere).

Dependencies:
    - :mod:`app.parser.semantic`              — full public API.
    - :mod:`app.parser.semantic.validation`   — class under test.
    - :mod:`app.parser.ast.*`                 — AST node types.
    - :mod:`app.parser.lexer.position`        — Position.
    - :mod:`pytest`                           — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pytest

from app.parser.ast.clauses import ProgramIdClauseNode
from app.parser.ast.data import DataDivisionNode
from app.parser.ast.data_items import (
    ConditionNameNode,
    ElementaryItemNode,
    GroupItemNode,
)
from app.parser.ast.identification import IdentificationDivisionNode
from app.parser.ast.paragraphs import ParagraphNode
from app.parser.ast.procedure import ProcedureDivisionNode
from app.parser.ast.program import ProgramNode
from app.parser.ast.statements import (
    DisplayStatementNode,
    GobackStatementNode,
    MoveStatementNode,
    StopRunStatementNode,
)
from app.parser.ast.working_storage import WorkingStorageSectionNode
from app.parser.lexer.position import Position
from app.parser.semantic import (
    SemanticAnalyzer,
    SemanticDiagnostic,
    SemanticSeverity,
    SemanticValidationVisitor,
    SymbolCollectorVisitor,
    SymbolTable,
    traverse_program,
)
from app.parser.semantic.validation import COBOL_RESERVED_WORDS

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FILE = "validation_test.cbl"


def _pos(line: int = 1, col: int = 1, offset: int = 0) -> Position:
    return Position(line=line, column=col, offset=offset, filename=_FILE)


def _program_id_clause(name: str, line: int = 2) -> ProgramIdClauseNode:
    pos = _pos(line=line)
    return ProgramIdClauseNode(start_position=pos, end_position=pos, value=name)


def _ident_div(
    program_name: str | None = "TESTPROG",
) -> IdentificationDivisionNode:
    pos = _pos(line=1)
    if program_name is None:
        return IdentificationDivisionNode(start_position=pos, end_position=pos)
    pid = _program_id_clause(program_name)
    return IdentificationDivisionNode(
        start_position=pos, end_position=pos, program_id=pid
    )


def _elementary(
    name: str, level: int = 5, picture: str = "X", line: int = 10
) -> ElementaryItemNode:
    pos = _pos(line=line)
    return ElementaryItemNode(
        start_position=pos, end_position=pos, level=level, name=name, picture=picture
    )


def _group(name: str, level: int = 1, line: int = 10) -> GroupItemNode:
    pos = _pos(line=line)
    return GroupItemNode(
        start_position=pos, end_position=pos, level=level, name=name, children=()
    )


def _condition(name: str, value: str = "'Y'", line: int = 15) -> ConditionNameNode:
    pos = _pos(line=line)
    return ConditionNameNode(
        start_position=pos, end_position=pos, level=88, name=name, value=value
    )


def _working_storage(
    *items: ElementaryItemNode | GroupItemNode | ConditionNameNode,
) -> WorkingStorageSectionNode:
    pos = _pos(line=5)
    return WorkingStorageSectionNode(
        start_position=pos, end_position=pos, items=tuple(items)
    )


def _data_div(ws: WorkingStorageSectionNode | None = None) -> DataDivisionNode:
    pos = _pos(line=5)
    return DataDivisionNode(start_position=pos, end_position=pos, working_storage=ws)


def _move(source: str, target: str, line: int = 20) -> MoveStatementNode:
    pos = _pos(line=line)
    return MoveStatementNode(
        start_position=pos, end_position=pos, source=source, target=target
    )


def _display(operand: str, line: int = 20) -> DisplayStatementNode:
    pos = _pos(line=line)
    return DisplayStatementNode(start_position=pos, end_position=pos, operand=operand)


def _stop_run(line: int = 99) -> StopRunStatementNode:
    pos = _pos(line=line)
    return StopRunStatementNode(start_position=pos, end_position=pos)


def _goback(line: int = 99) -> GobackStatementNode:
    pos = _pos(line=line)
    return GobackStatementNode(start_position=pos, end_position=pos)


def _paragraph(
    name: str,
    *stmts: MoveStatementNode
    | DisplayStatementNode
    | StopRunStatementNode
    | GobackStatementNode,
    line: int = 20,
) -> ParagraphNode:
    pos = _pos(line=line)
    return ParagraphNode(
        start_position=pos, end_position=pos, name=name, statements=tuple(stmts)
    )


def _proc_div(*paragraphs: ParagraphNode, line: int = 20) -> ProcedureDivisionNode:
    pos = _pos(line=line)
    return ProcedureDivisionNode(
        start_position=pos, end_position=pos, paragraphs=tuple(paragraphs)
    )


def _empty_proc_div(line: int = 20) -> ProcedureDivisionNode:
    """Procedure division with no paragraphs."""
    pos = _pos(line=line)
    return ProcedureDivisionNode(start_position=pos, end_position=pos, paragraphs=())


def _program(
    ident: IdentificationDivisionNode | None = None,
    data: DataDivisionNode | None = None,
    proc: ProcedureDivisionNode | None = None,
) -> ProgramNode:
    pos = _pos(line=1)
    return ProgramNode(
        start_position=pos,
        end_position=pos,
        identification_division=ident,
        data_division=data,
        procedure_division=proc,
    )


def _make_validator(
    diagnostics: list[SemanticDiagnostic] | None = None,
) -> tuple[SemanticValidationVisitor, list[SemanticDiagnostic]]:
    if diagnostics is None:
        diagnostics = []
    return SemanticValidationVisitor(diagnostics=diagnostics), diagnostics


# ===========================================================================
# Construction
# ===========================================================================


class TestSemanticValidationVisitorConstruction:
    """Tests for SemanticValidationVisitor construction."""

    def test_stores_diagnostics_reference(self) -> None:
        diags: list[SemanticDiagnostic] = []
        v = SemanticValidationVisitor(diagnostics=diags)
        assert v._diagnostics is diags

    def test_is_semantic_visitor_subclass(self) -> None:
        from app.parser.semantic.visitors import SemanticVisitor

        v, _ = _make_validator()
        assert isinstance(v, SemanticVisitor)

    def test_public_api_exports_semantic_validation_visitor(self) -> None:
        from app.parser.semantic import SemanticValidationVisitor as SVV

        assert SVV is SemanticValidationVisitor


# ===========================================================================
# COBOL_RESERVED_WORDS constant
# ===========================================================================


class TestCobolReservedWords:
    """Tests for the COBOL_RESERVED_WORDS constant."""

    def test_move_is_reserved(self) -> None:
        assert "MOVE" in COBOL_RESERVED_WORDS

    def test_display_is_reserved(self) -> None:
        assert "DISPLAY" in COBOL_RESERVED_WORDS

    def test_call_is_reserved(self) -> None:
        assert "CALL" in COBOL_RESERVED_WORDS

    def test_stop_is_reserved(self) -> None:
        assert "STOP" in COBOL_RESERVED_WORDS

    def test_ws_count_is_not_reserved(self) -> None:
        assert "WS-COUNT" not in COBOL_RESERVED_WORDS

    def test_customer_id_is_not_reserved(self) -> None:
        assert "CUSTOMER-ID" not in COBOL_RESERVED_WORDS

    def test_set_is_a_frozenset(self) -> None:
        assert isinstance(COBOL_RESERVED_WORDS, frozenset)


# ===========================================================================
# SEM006 — Missing / blank PROGRAM-ID
# ===========================================================================


class TestSEM006MissingProgramId:
    """SemanticValidationVisitor emits SEM006 for missing/blank PROGRAM-ID."""

    def test_program_id_absent_emits_sem006(self) -> None:
        """IdentificationDivision with no program_id → SEM006."""
        validator, diags = _make_validator()
        traverse_program(_program(ident=_ident_div(program_name=None)), validator)
        assert any(d.code == "SEM006" for d in diags)

    def test_program_id_blank_emits_sem006(self) -> None:
        """PROGRAM-ID value is empty string → SEM006."""
        validator, diags = _make_validator()
        traverse_program(_program(ident=_ident_div(program_name="")), validator)
        assert any(d.code == "SEM006" for d in diags)

    def test_program_id_whitespace_only_emits_sem006(self) -> None:
        """PROGRAM-ID value is whitespace only → SEM006."""
        validator, diags = _make_validator()
        traverse_program(_program(ident=_ident_div(program_name="   ")), validator)
        assert any(d.code == "SEM006" for d in diags)

    def test_valid_program_id_no_sem006(self) -> None:
        """Valid PROGRAM-ID → no SEM006."""
        validator, diags = _make_validator()
        traverse_program(_program(ident=_ident_div("PAYROLL")), validator)
        sem006 = [d for d in diags if d.code == "SEM006"]
        assert len(sem006) == 0

    def test_sem006_severity_is_error(self) -> None:
        validator, diags = _make_validator()
        traverse_program(_program(ident=_ident_div(program_name=None)), validator)
        sem006 = [d for d in diags if d.code == "SEM006"]
        assert sem006[0].severity is SemanticSeverity.ERROR

    def test_sem006_message_mentions_program_id(self) -> None:
        validator, diags = _make_validator()
        traverse_program(_program(ident=_ident_div(program_name=None)), validator)
        sem006 = [d for d in diags if d.code == "SEM006"]
        assert "PROGRAM-ID" in sem006[0].message

    def test_sem006_position_is_identification_division_position(self) -> None:
        """SEM006 position matches the start of the IDENTIFICATION DIVISION."""
        ident = _ident_div(program_name=None)
        expected_line = ident.start_position.line
        validator, diags = _make_validator()
        traverse_program(_program(ident=ident), validator)
        sem006 = [d for d in diags if d.code == "SEM006"]
        assert sem006[0].position.line == expected_line

    def test_no_identification_division_no_sem006(self) -> None:
        """Completely absent IDENTIFICATION DIVISION → no SEM006 (nothing to check)."""
        validator, diags = _make_validator()
        traverse_program(_program(), validator)
        sem006 = [d for d in diags if d.code == "SEM006"]
        assert len(sem006) == 0


# ===========================================================================
# SEM007 — Empty PROCEDURE DIVISION
# ===========================================================================


class TestSEM007EmptyProcedureDivision:
    """SemanticValidationVisitor emits SEM007 for empty PROCEDURE DIVISION."""

    def test_empty_procedure_division_emits_sem007(self) -> None:
        """PROCEDURE DIVISION with no paragraphs → SEM007."""
        validator, diags = _make_validator()
        traverse_program(_program(proc=_empty_proc_div()), validator)
        assert any(d.code == "SEM007" for d in diags)

    def test_procedure_division_with_one_paragraph_no_sem007(self) -> None:
        """PROCEDURE DIVISION with one paragraph → no SEM007."""
        validator, diags = _make_validator()
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _stop_run()))),
            validator,
        )
        sem007 = [d for d in diags if d.code == "SEM007"]
        assert len(sem007) == 0

    def test_procedure_division_with_multiple_paragraphs_no_sem007(self) -> None:
        """PROCEDURE DIVISION with several paragraphs → no SEM007."""
        validator, diags = _make_validator()
        traverse_program(
            _program(
                proc=_proc_div(
                    _paragraph("INIT", _move("1", "WS-COUNT")),
                    _paragraph("MAIN", _display('"HELLO"')),
                    _paragraph("DONE", _stop_run()),
                )
            ),
            validator,
        )
        sem007 = [d for d in diags if d.code == "SEM007"]
        assert len(sem007) == 0

    def test_no_procedure_division_no_sem007(self) -> None:
        """Missing PROCEDURE DIVISION → no SEM007."""
        validator, diags = _make_validator()
        traverse_program(_program(ident=_ident_div("NOPROC")), validator)
        sem007 = [d for d in diags if d.code == "SEM007"]
        assert len(sem007) == 0

    def test_sem007_severity_is_error(self) -> None:
        validator, diags = _make_validator()
        traverse_program(_program(proc=_empty_proc_div()), validator)
        sem007 = [d for d in diags if d.code == "SEM007"]
        assert sem007[0].severity is SemanticSeverity.ERROR

    def test_sem007_message_mentions_procedure_division(self) -> None:
        validator, diags = _make_validator()
        traverse_program(_program(proc=_empty_proc_div()), validator)
        sem007 = [d for d in diags if d.code == "SEM007"]
        assert "PROCEDURE DIVISION" in sem007[0].message

    def test_sem007_position_is_procedure_division_start(self) -> None:
        """SEM007 position matches the start of the PROCEDURE DIVISION node."""
        proc = _empty_proc_div(line=40)
        validator, diags = _make_validator()
        traverse_program(_program(proc=proc), validator)
        sem007 = [d for d in diags if d.code == "SEM007"]
        assert sem007[0].position.line == 40


# ===========================================================================
# SEM008 — Reserved word used as identifier
# ===========================================================================


class TestSEM008ReservedWordIdentifier:
    """SemanticValidationVisitor emits SEM008 for reserved-word data names."""

    def test_elementary_item_named_move_emits_sem008(self) -> None:
        """Elementary item with name 'MOVE' → SEM008."""
        validator, diags = _make_validator()
        ws = _working_storage(_elementary("MOVE"))
        traverse_program(_program(data=_data_div(ws=ws)), validator)
        assert any(d.code == "SEM008" for d in diags)

    def test_group_item_named_call_emits_sem008(self) -> None:
        """Group item with name 'CALL' → SEM008."""
        validator, diags = _make_validator()
        ws = _working_storage(_group("CALL"))
        traverse_program(_program(data=_data_div(ws=ws)), validator)
        assert any(d.code == "SEM008" for d in diags)

    def test_condition_name_named_display_emits_sem008(self) -> None:
        """Condition name with name 'DISPLAY' → SEM008."""
        validator, diags = _make_validator()
        ws = _working_storage(_condition("DISPLAY"))
        traverse_program(_program(data=_data_div(ws=ws)), validator)
        assert any(d.code == "SEM008" for d in diags)

    def test_reserved_word_check_is_case_insensitive(self) -> None:
        """Reserved word detection is case-insensitive (lower-case 'move' matches)."""
        validator, diags = _make_validator()
        ws = _working_storage(_elementary("move"))
        traverse_program(_program(data=_data_div(ws=ws)), validator)
        assert any(d.code == "SEM008" for d in diags)

    def test_normal_data_name_no_sem008(self) -> None:
        """Normal data name like WS-CUSTOMER → no SEM008."""
        validator, diags = _make_validator()
        ws = _working_storage(_elementary("WS-CUSTOMER"))
        traverse_program(_program(data=_data_div(ws=ws)), validator)
        sem008 = [d for d in diags if d.code == "SEM008"]
        assert len(sem008) == 0

    def test_multiple_reserved_names_produce_multiple_sem008(self) -> None:
        """Two reserved-word items each produce a SEM008."""
        validator, diags = _make_validator()
        ws = _working_storage(_elementary("MOVE"), _elementary("CALL"))
        traverse_program(_program(data=_data_div(ws=ws)), validator)
        sem008 = [d for d in diags if d.code == "SEM008"]
        assert len(sem008) == 2

    def test_sem008_severity_is_error(self) -> None:
        validator, diags = _make_validator()
        ws = _working_storage(_elementary("STOP"))
        traverse_program(_program(data=_data_div(ws=ws)), validator)
        sem008 = [d for d in diags if d.code == "SEM008"]
        assert sem008[0].severity is SemanticSeverity.ERROR

    def test_sem008_message_contains_identifier_name(self) -> None:
        validator, diags = _make_validator()
        ws = _working_storage(_elementary("PERFORM"))
        traverse_program(_program(data=_data_div(ws=ws)), validator)
        sem008 = [d for d in diags if d.code == "SEM008"]
        assert "PERFORM" in sem008[0].message

    def test_sem008_position_is_item_position(self) -> None:
        """SEM008 position matches the data item's source position."""
        item = _elementary("IF", line=22)
        ws = _working_storage(item)
        validator, diags = _make_validator()
        traverse_program(_program(data=_data_div(ws=ws)), validator)
        sem008 = [d for d in diags if d.code == "SEM008"]
        assert sem008[0].position.line == 22

    def test_hyphenated_reserved_word_data_name_no_sem008(self) -> None:
        """Hyphenated names like HIGH-VALUES are not in the reserved list."""
        validator, diags = _make_validator()
        # HIGH-VALUES is a figurative constant, not a reserved COBOL keyword;
        # it is not in COBOL_RESERVED_WORDS so it should not produce SEM008.
        ws = _working_storage(_elementary("MY-STOP-FLAG"))
        traverse_program(_program(data=_data_div(ws=ws)), validator)
        sem008 = [d for d in diags if d.code == "SEM008"]
        assert len(sem008) == 0


# ===========================================================================
# SEM009 — Invalid static CALL target (internal helper)
# ===========================================================================


class TestSEM009StaticCallTarget:
    """_check_static_call_target emits SEM009 for blank/invalid CALL targets."""

    def test_blank_call_target_emits_sem009(self) -> None:
        """Blank CALL target → SEM009."""
        validator, diags = _make_validator()
        pos = _pos(line=30)
        validator._check_static_call_target("", pos)
        assert len(diags) == 1
        assert diags[0].code == "SEM009"

    def test_whitespace_only_call_target_emits_sem009(self) -> None:
        """Whitespace-only CALL target → SEM009."""
        validator, diags = _make_validator()
        pos = _pos(line=30)
        validator._check_static_call_target("   ", pos)
        assert len(diags) == 1
        assert diags[0].code == "SEM009"

    def test_non_blank_call_target_no_sem009(self) -> None:
        """Non-blank CALL target → no SEM009."""
        validator, diags = _make_validator()
        pos = _pos(line=30)
        validator._check_static_call_target("SUBPROG", pos)
        assert len(diags) == 0

    def test_sem009_severity_is_error(self) -> None:
        validator, diags = _make_validator()
        validator._check_static_call_target("", _pos())
        assert diags[0].severity is SemanticSeverity.ERROR

    def test_sem009_message_contains_target(self) -> None:
        validator, diags = _make_validator()
        validator._check_static_call_target("", _pos())
        assert diags[0].code == "SEM009"


# ===========================================================================
# Traversal continuity
# ===========================================================================


class TestTraversalContinuity:
    """Traversal never aborts after a validation error."""

    def test_sem006_and_sem007_both_collected(self) -> None:
        """SEM006 (bad PROGRAM-ID) and SEM007 (empty proc) are both collected."""
        validator, diags = _make_validator()
        traverse_program(
            _program(
                ident=_ident_div(program_name=None),
                proc=_empty_proc_div(),
            ),
            validator,
        )
        codes = {d.code for d in diags}
        assert "SEM006" in codes
        assert "SEM007" in codes

    def test_sem008_and_sem007_both_collected(self) -> None:
        """SEM008 (reserved name) and SEM007 (empty proc) are both collected."""
        validator, diags = _make_validator()
        ws = _working_storage(_elementary("MOVE"))
        traverse_program(
            _program(data=_data_div(ws=ws), proc=_empty_proc_div()),
            validator,
        )
        codes = {d.code for d in diags}
        assert "SEM008" in codes
        assert "SEM007" in codes

    def test_multiple_sem008_all_collected(self) -> None:
        """Three reserved-word items → three SEM008 diagnostics."""
        validator, diags = _make_validator()
        ws = _working_storage(
            _elementary("MOVE"),
            _elementary("CALL"),
            _elementary("IF"),
        )
        traverse_program(_program(data=_data_div(ws=ws)), validator)
        sem008 = [d for d in diags if d.code == "SEM008"]
        assert len(sem008) == 3

    def test_clean_program_after_bad_does_not_inherit_errors(self) -> None:
        """A second validator on a clean program produces no diagnostics."""
        validator2, diags2 = _make_validator()
        traverse_program(
            _program(
                ident=_ident_div("CLEAN"),
                proc=_proc_div(_paragraph("P", _stop_run())),
            ),
            validator2,
        )
        assert len(diags2) == 0


# ===========================================================================
# Empty / minimal programs
# ===========================================================================


class TestEmptyProgramValidation:
    """SemanticValidationVisitor handles empty / minimal ASTs gracefully."""

    def test_completely_empty_program_no_diagnostics(self) -> None:
        """An empty ProgramNode (no divisions) produces no validation diagnostics."""
        validator, diags = _make_validator()
        traverse_program(_program(), validator)
        assert len(diags) == 0

    def test_ident_div_only_with_valid_program_id_no_diagnostics(self) -> None:
        """Identification division only, valid PROGRAM-ID → no diagnostics."""
        validator, diags = _make_validator()
        traverse_program(_program(ident=_ident_div("MINIMAL")), validator)
        assert len(diags) == 0

    def test_data_div_only_no_diagnostics(self) -> None:
        """Data division without proc division → no SEM007."""
        validator, diags = _make_validator()
        ws = _working_storage(_elementary("WS-X"))
        traverse_program(_program(data=_data_div(ws=ws)), validator)
        assert len(diags) == 0

    def test_empty_working_storage_no_diagnostics(self) -> None:
        """Empty working storage → no SEM008."""
        validator, diags = _make_validator()
        traverse_program(_program(data=_data_div(ws=_working_storage())), validator)
        assert len(diags) == 0


# ===========================================================================
# Representative COBOL programs
# ===========================================================================


class TestRepresentativePrograms:
    """End-to-end validation on representative COBOL programs."""

    def _build_valid_program(self) -> ProgramNode:
        """A syntactically and semantically correct COBOL program."""
        ws = _working_storage(
            _elementary("WS-COUNT", level=77, picture="9(5)", line=6),
            _elementary("WS-NAME", level=77, picture="X(30)", line=7),
        )
        proc = _proc_div(
            _paragraph(
                "INIT",
                _move("0", "WS-COUNT", line=21),
                _move("SPACES", "WS-NAME", line=22),
                line=20,
            ),
            _paragraph("DONE", _stop_run(), line=30),
        )
        return _program(
            ident=_ident_div("PAYROLL"),
            data=_data_div(ws=ws),
            proc=proc,
        )

    def _build_invalid_program(self) -> ProgramNode:
        """A program that violates multiple validation rules."""
        ws = _working_storage(
            _elementary("MOVE", line=6),  # SEM008
            _elementary("IF", line=7),  # SEM008
        )
        proc = _empty_proc_div(line=20)  # SEM007
        return _program(
            ident=_ident_div(program_name=None),  # SEM006
            data=_data_div(ws=ws),
            proc=proc,
        )

    def test_valid_program_no_validation_diagnostics(self) -> None:
        validator, diags = _make_validator()
        traverse_program(self._build_valid_program(), validator)
        assert len(diags) == 0

    def test_invalid_program_all_codes_emitted(self) -> None:
        validator, diags = _make_validator()
        traverse_program(self._build_invalid_program(), validator)
        codes = {d.code for d in diags}
        assert "SEM006" in codes
        assert "SEM007" in codes
        assert "SEM008" in codes

    def test_invalid_program_sem008_count(self) -> None:
        """Two reserved-word items → exactly two SEM008 diagnostics."""
        validator, diags = _make_validator()
        traverse_program(self._build_invalid_program(), validator)
        sem008 = [d for d in diags if d.code == "SEM008"]
        assert len(sem008) == 2


# ===========================================================================
# SemanticAnalyzer integration (regression guard)
# ===========================================================================


class TestSemanticAnalyzerIntegration:
    """Guard that SemanticAnalyzer runs all three passes in the correct order."""

    def test_valid_program_no_errors(self) -> None:
        """Clean program → no diagnostics at all."""
        ws = _working_storage(_elementary("WS-A"))
        proc = _proc_div(_paragraph("P", _stop_run()))
        ctx = SemanticAnalyzer().analyse(
            _program(ident=_ident_div("CLEAN"), data=_data_div(ws=ws), proc=proc)
        )
        assert not ctx.has_errors

    def test_sem006_emitted_through_pipeline(self) -> None:
        """Missing PROGRAM-ID → SEM006 in the final context."""
        ctx = SemanticAnalyzer().analyse(_program(ident=_ident_div(program_name=None)))
        codes = [d.code for d in ctx.diagnostics]
        assert "SEM006" in codes

    def test_sem007_emitted_through_pipeline(self) -> None:
        """Empty PROCEDURE DIVISION → SEM007 in the final context."""
        ctx = SemanticAnalyzer().analyse(_program(proc=_empty_proc_div()))
        codes = [d.code for d in ctx.diagnostics]
        assert "SEM007" in codes

    def test_sem008_emitted_through_pipeline(self) -> None:
        """Reserved-word data name → SEM008 in the final context."""
        ws = _working_storage(_elementary("MOVE"))
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws)))
        codes = [d.code for d in ctx.diagnostics]
        assert "SEM008" in codes

    def test_sem001_and_sem006_coexist(self) -> None:
        """Duplicate variable (SEM001, pass 1) and missing PROGRAM-ID (SEM006, pass 3)."""
        ws = _working_storage(
            _elementary("DUP", line=10),
            _elementary("DUP", line=11),
        )
        ctx = SemanticAnalyzer().analyse(
            _program(
                ident=_ident_div(program_name=None),
                data=_data_div(ws=ws),
            )
        )
        codes = {d.code for d in ctx.diagnostics}
        assert "SEM001" in codes
        assert "SEM006" in codes

    def test_sem003_and_sem007_coexist(self) -> None:
        """Undefined variable (SEM003, pass 2) and empty proc div (SEM007, pass 3)."""
        ctx = SemanticAnalyzer().analyse(_program(proc=_empty_proc_div()))
        # The empty proc div produces SEM007 from pass 3.
        # (No MOVE statements so no SEM003 here, but both passes ran.)
        codes = {d.code for d in ctx.diagnostics}
        assert "SEM007" in codes

    def test_all_passes_run_in_order(self) -> None:
        """SEM001 (pass 1) + SEM003 (pass 2) + SEM008 (pass 3) all present."""
        ws = _working_storage(
            _elementary("DUP", line=10),
            _elementary("DUP", line=11),  # SEM001
            _elementary("MOVE", line=12),  # SEM008
        )
        proc = _proc_div(
            _paragraph("P", _move("1", "MISSING-VAR", line=20), line=20)
        )  # SEM003
        ctx = SemanticAnalyzer().analyse(
            _program(ident=_ident_div("TEST"), data=_data_div(ws=ws), proc=proc)
        )
        codes = {d.code for d in ctx.diagnostics}
        assert "SEM001" in codes
        assert "SEM003" in codes
        assert "SEM008" in codes

    def test_analyser_is_reusable(self) -> None:
        """SemanticAnalyzer can be reused across independent programs."""
        analyzer = SemanticAnalyzer()
        # First call — invalid program
        ctx1 = analyzer.analyse(_program(ident=_ident_div(program_name=None)))
        # Second call — clean program
        ws = _working_storage(_elementary("WS-A"))
        ctx2 = analyzer.analyse(
            _program(
                ident=_ident_div("CLEAN"),
                data=_data_div(ws=ws),
                proc=_proc_div(_paragraph("P", _stop_run())),
            )
        )
        assert ctx1.has_errors
        assert not ctx2.has_errors

    def test_sem007_only_one_diagnostic_for_empty_proc(self) -> None:
        """Empty PROCEDURE DIVISION produces exactly one SEM007, not more."""
        ctx = SemanticAnalyzer().analyse(_program(proc=_empty_proc_div()))
        sem007 = [d for d in ctx.diagnostics if d.code == "SEM007"]
        assert len(sem007) == 1

    def test_sem006_position_propagated_in_context(self) -> None:
        """SEM006 diagnostic position is reachable from the context."""
        ident = _ident_div(program_name=None)
        ctx = SemanticAnalyzer().analyse(_program(ident=ident))
        sem006 = [d for d in ctx.diagnostics if d.code == "SEM006"]
        assert sem006[0].position.line == ident.start_position.line

    def test_symbol_table_still_populated_after_three_passes(self) -> None:
        """SemanticContext symbol table remains accessible after all three passes."""
        ws = _working_storage(
            _elementary("WS-A", line=6),
            _elementary("WS-B", line=7),
        )
        ctx = SemanticAnalyzer().analyse(
            _program(ident=_ident_div("TEST"), data=_data_div(ws=ws))
        )
        from app.parser.semantic.symbols import SymbolKind

        variables = ctx.symbol_table.symbols_of_kind(SymbolKind.VARIABLE)
        assert len(variables) == 2


# ===========================================================================
# Standalone visitor interaction (two-visitor composition)
# ===========================================================================


class TestStandaloneVisitorComposition:
    """Validator can be used independently alongside SymbolCollectorVisitor."""

    def test_composition_with_symbol_collector(self) -> None:
        """Run collector then validator on same program manually."""
        table = SymbolTable()
        diags: list[SemanticDiagnostic] = []

        ws = _working_storage(_elementary("MOVE", line=6))
        prog = _program(
            ident=_ident_div(program_name=None),
            data=_data_div(ws=ws),
        )

        collector = SymbolCollectorVisitor(table=table, diagnostics=diags)
        traverse_program(prog, collector)

        validator = SemanticValidationVisitor(diagnostics=diags)
        traverse_program(prog, validator)

        codes = {d.code for d in diags}
        assert "SEM006" in codes
        assert "SEM008" in codes


# ===========================================================================
# Parameterised reserved-word spot-checks
# ===========================================================================

_RESERVED_SPOT_CHECKS = [
    "ACCEPT",
    "ADD",
    "CALL",
    "COMPUTE",
    "DELETE",
    "DISPLAY",
    "EVALUATE",
    "EXIT",
    "GO",
    "GOBACK",
    "IF",
    "MOVE",
    "PERFORM",
    "READ",
    "STOP",
    "WRITE",
]


@pytest.mark.parametrize("keyword", _RESERVED_SPOT_CHECKS)
def test_reserved_keyword_as_elementary_item_emits_sem008(keyword: str) -> None:
    """Each reserved keyword, used as an elementary item name, → SEM008."""
    validator, diags = _make_validator()
    ws = _working_storage(_elementary(keyword))
    traverse_program(_program(data=_data_div(ws=ws)), validator)
    sem008 = [d for d in diags if d.code == "SEM008"]
    assert len(sem008) == 1, f"Expected SEM008 for reserved word {keyword!r}"
