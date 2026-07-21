"""
Comprehensive tests for TASK-020: Reference Resolution Visitor.

Purpose:
    Verify that :class:`ReferenceResolverVisitor` correctly traverses the
    COBOL AST after symbol collection, resolves identifier references against
    the populated :class:`SymbolTable`, emits ``SEM003`` / ``SEM004`` /
    ``SEM005`` diagnostics for unresolved references, continues traversal
    after errors, and integrates correctly with :class:`SemanticAnalyzer`.

Coverage:
    Visitor construction:
        - Stores table and diagnostics references.
        - Is a SemanticVisitor subclass.
        - Public API exports ReferenceResolverVisitor.

    Literal classification (_is_literal helper):
        - Quoted string literals skipped.
        - Numeric literals skipped.
        - COBOL figurative constants skipped (SPACES, ZEROS, etc.).
        - Bare identifiers NOT treated as literals.

    MOVE statement resolution:
        - Declared source variable → resolved, no diagnostic.
        - Declared target variable → resolved, no diagnostic.
        - Undeclared source variable → SEM003 emitted.
        - Undeclared target variable → SEM003 emitted.
        - Literal source value skipped.
        - Figurative constant source skipped.
        - Both operands in one MOVE resolved independently.
        - Multiple MOVE statements accumulate independent diagnostics.

    DISPLAY statement resolution:
        - Declared variable operand → resolved, no diagnostic.
        - Literal string operand skipped.
        - Undeclared variable operand → SEM003 emitted.
        - Figurative constant operand skipped.

    Traversal continuity:
        - Errors do not abort traversal.
        - Later clean references still resolved after earlier failures.
        - Multiple undefined references produce multiple diagnostics.

    Empty program:
        - No statements → no resolution diagnostics.

    Representative full COBOL program:
        - All declared variables resolved correctly in MOVE/DISPLAY.
        - Undeclared variables produce exactly the right number of diagnostics.

    _resolve_paragraph_reference:
        - Declared paragraph resolved, no diagnostic.
        - Undeclared paragraph → SEM004 emitted.

    _resolve_section_reference:
        - Undeclared section → SEM005 emitted.

    Diagnostic content:
        - Diagnostic code is correct (SEM003/SEM004/SEM005).
        - Diagnostic severity is ERROR.
        - Diagnostic message contains identifier name.
        - Diagnostic position matches statement position.

    SemanticAnalyzer integration (regression guard):
        - analyse() runs both passes in order.
        - Declared MOVE operands → no diagnostics.
        - Undeclared MOVE operand → SEM003 in result.
        - Symbol-collection diagnostics (SEM001/SEM002) still reported.
        - Pass ordering: all symbols collected before resolution.

Non-responsibilities:
    - Lexer / parser behaviour.
    - AST node field correctness (covered elsewhere).

Dependencies:
    - :mod:`app.parser.semantic`                  — full public API.
    - :mod:`app.parser.semantic.reference_resolver` — class under test.
    - :mod:`app.parser.ast.*`                     — AST node types.
    - :mod:`app.parser.lexer.position`            — Position.
    - :mod:`pytest`                               — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

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
    ParagraphSymbol,
    ReferenceResolverVisitor,
    SemanticAnalyzer,
    SemanticDiagnostic,
    SemanticSeverity,
    SymbolCollectorVisitor,
    SymbolKind,
    SymbolTable,
    VariableSymbol,
    traverse_program,
)
from app.parser.semantic.reference_resolver import _is_literal

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FILE = "resolver_test.cbl"


def _pos(line: int = 1, col: int = 1, offset: int = 0) -> Position:
    return Position(line=line, column=col, offset=offset, filename=_FILE)


def _program_id_clause(name: str, line: int = 2) -> ProgramIdClauseNode:
    pos = _pos(line=line)
    return ProgramIdClauseNode(start_position=pos, end_position=pos, value=name)


def _ident_div(program_name: str = "TESTPROG") -> IdentificationDivisionNode:
    pos = _pos(line=1)
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


def _proc_div(*paragraphs: ParagraphNode) -> ProcedureDivisionNode:
    pos = _pos(line=20)
    return ProcedureDivisionNode(
        start_position=pos, end_position=pos, paragraphs=tuple(paragraphs)
    )


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


def _populated_table(*names: str) -> SymbolTable:
    """Create a SymbolTable with the given variable names pre-registered."""
    table = SymbolTable()
    for name in names:
        pos = _pos()
        table.register(
            VariableSymbol(name=name.upper(), declared_at=pos, level=5, picture="X")
        )
    return table


def _make_resolver(
    table: SymbolTable | None = None,
    diagnostics: list[SemanticDiagnostic] | None = None,
) -> tuple[ReferenceResolverVisitor, SymbolTable, list[SemanticDiagnostic]]:
    if table is None:
        table = SymbolTable()
    if diagnostics is None:
        diagnostics = []
    return (
        ReferenceResolverVisitor(table=table, diagnostics=diagnostics),
        table,
        diagnostics,
    )


# ===========================================================================
# _is_literal helper
# ===========================================================================


class TestIsLiteral:
    """Tests for the _is_literal classification helper."""

    def test_double_quoted_string_is_literal(self) -> None:
        assert _is_literal('"HELLO"') is True

    def test_single_quoted_string_is_literal(self) -> None:
        assert _is_literal("'WORLD'") is True

    def test_integer_is_literal(self) -> None:
        assert _is_literal("1") is True

    def test_decimal_is_literal(self) -> None:
        assert _is_literal("3.14") is True

    def test_positive_numeric_is_literal(self) -> None:
        assert _is_literal("+100") is True

    def test_negative_numeric_is_literal(self) -> None:
        assert _is_literal("-99") is True

    def test_spaces_figurative_constant_is_literal(self) -> None:
        assert _is_literal("SPACES") is True

    def test_space_figurative_constant_is_literal(self) -> None:
        assert _is_literal("SPACE") is True

    def test_zeros_figurative_constant_is_literal(self) -> None:
        assert _is_literal("ZEROS") is True

    def test_zero_figurative_constant_is_literal(self) -> None:
        assert _is_literal("ZERO") is True

    def test_zeroes_figurative_constant_is_literal(self) -> None:
        assert _is_literal("ZEROES") is True

    def test_high_values_is_literal(self) -> None:
        assert _is_literal("HIGH-VALUES") is True

    def test_low_values_is_literal(self) -> None:
        assert _is_literal("LOW-VALUES") is True

    def test_null_is_literal(self) -> None:
        assert _is_literal("NULL") is True

    def test_nulls_is_literal(self) -> None:
        assert _is_literal("NULLS") is True

    def test_figurative_constant_case_insensitive(self) -> None:
        assert _is_literal("spaces") is True

    def test_plain_identifier_is_not_literal(self) -> None:
        assert _is_literal("WS-COUNT") is False

    def test_hyphenated_identifier_is_not_literal(self) -> None:
        assert _is_literal("CUST-RECORD") is False

    def test_empty_token_is_literal(self) -> None:
        assert _is_literal("") is True


# ===========================================================================
# Construction
# ===========================================================================


class TestReferenceResolverConstruction:
    """Tests for ReferenceResolverVisitor construction."""

    def test_stores_table_reference(self) -> None:
        table = SymbolTable()
        resolver = ReferenceResolverVisitor(table=table, diagnostics=[])
        assert resolver._table is table

    def test_stores_diagnostics_reference(self) -> None:
        diagnostics: list[SemanticDiagnostic] = []
        resolver = ReferenceResolverVisitor(
            table=SymbolTable(), diagnostics=diagnostics
        )
        assert resolver._diagnostics is diagnostics

    def test_is_semantic_visitor_subclass(self) -> None:
        from app.parser.semantic.visitors import SemanticVisitor

        resolver, _, _ = _make_resolver()
        assert isinstance(resolver, SemanticVisitor)

    def test_public_api_exports_reference_resolver_visitor(self) -> None:
        from app.parser.semantic import ReferenceResolverVisitor as RRV

        assert RRV is ReferenceResolverVisitor


# ===========================================================================
# MOVE statement resolution
# ===========================================================================


class TestMoveStatementResolution:
    """ReferenceResolverVisitor resolves MOVE operands correctly."""

    def test_declared_source_no_diagnostic(self) -> None:
        """Declared source variable resolves without a diagnostic."""
        table = _populated_table("WS-COUNT")
        resolver, _, diagnostics = _make_resolver(table=table)
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _move("WS-COUNT", "WS-COUNT")))),
            resolver,
        )
        assert len(diagnostics) == 0

    def test_declared_target_no_diagnostic(self) -> None:
        """Declared target variable resolves without a diagnostic."""
        table = _populated_table("WS-RESULT")
        resolver, _, diagnostics = _make_resolver(table=table)
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _move("1", "WS-RESULT")))),
            resolver,
        )
        assert len(diagnostics) == 0

    def test_undeclared_source_emits_sem003(self) -> None:
        """Undeclared source variable emits SEM003."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(
                proc=_proc_div(_paragraph("P", _move("MISSING-VAR", "WS-RESULT")))
            ),
            resolver,
        )
        assert any(d.code == "SEM003" for d in diagnostics)

    def test_undeclared_target_emits_sem003(self) -> None:
        """Undeclared target variable emits SEM003."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _move("1", "MISSING-VAR")))),
            resolver,
        )
        assert any(d.code == "SEM003" for d in diagnostics)

    def test_literal_source_skipped(self) -> None:
        """Literal source value is not resolved and produces no diagnostic."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _move("1", "MISSING-VAR")))),
            resolver,
        )
        assert len(diagnostics) == 1  # only target missing, not source

    def test_quoted_string_source_skipped(self) -> None:
        """Quoted string source is skipped."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _move('"HELLO"', "WS-OUT")))),
            resolver,
        )
        # Only WS-OUT is undefined, not "HELLO"
        assert len(diagnostics) == 1
        assert "WS-OUT" in diagnostics[0].message

    def test_figurative_constant_source_skipped(self) -> None:
        """SPACES figurative constant source is skipped."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _move("SPACES", "MISSING")))),
            resolver,
        )
        assert len(diagnostics) == 1  # only MISSING is undefined

    def test_both_undeclared_operands_produce_two_diagnostics(self) -> None:
        """Two undeclared operands each produce a SEM003 diagnostic."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _move("MISS-A", "MISS-B")))),
            resolver,
        )
        assert len(diagnostics) == 2
        assert all(d.code == "SEM003" for d in diagnostics)

    def test_multiple_moves_accumulate_diagnostics(self) -> None:
        """Multiple MOVE statements each produce their own diagnostic."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(
                proc=_proc_div(
                    _paragraph(
                        "P",
                        _move("1", "MISS-A", line=21),
                        _move("1", "MISS-B", line=22),
                        _move("1", "MISS-C", line=23),
                    )
                )
            ),
            resolver,
        )
        assert len(diagnostics) == 3

    def test_move_diagnostic_severity_is_error(self) -> None:
        """SEM003 diagnostic has ERROR severity."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _move("1", "MISSING")))),
            resolver,
        )
        assert diagnostics[0].severity is SemanticSeverity.ERROR

    def test_move_diagnostic_message_contains_identifier(self) -> None:
        """SEM003 message contains the undefined identifier name."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _move("1", "BAD-VAR")))),
            resolver,
        )
        assert "BAD-VAR" in diagnostics[0].message

    def test_move_diagnostic_position_is_statement_position(self) -> None:
        """SEM003 diagnostic position matches the MOVE statement position."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _move("1", "BAD", line=55)))),
            resolver,
        )
        assert diagnostics[0].position.line == 55


# ===========================================================================
# DISPLAY statement resolution
# ===========================================================================


class TestDisplayStatementResolution:
    """ReferenceResolverVisitor resolves DISPLAY operands correctly."""

    def test_declared_variable_operand_no_diagnostic(self) -> None:
        """Declared variable resolves without a diagnostic."""
        table = _populated_table("WS-NAME")
        resolver, _, diagnostics = _make_resolver(table=table)
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _display("WS-NAME")))),
            resolver,
        )
        assert len(diagnostics) == 0

    def test_literal_operand_skipped(self) -> None:
        """String literal operand is skipped — no diagnostic."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _display('"HELLO WORLD"')))),
            resolver,
        )
        assert len(diagnostics) == 0

    def test_undeclared_variable_operand_emits_sem003(self) -> None:
        """Undeclared variable operand emits SEM003."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _display("MISSING-VAR")))),
            resolver,
        )
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "SEM003"

    def test_figurative_constant_operand_skipped(self) -> None:
        """SPACES figurative constant is skipped."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _display("SPACES")))),
            resolver,
        )
        assert len(diagnostics) == 0

    def test_display_diagnostic_message_contains_name(self) -> None:
        """SEM003 message contains the undefined identifier name."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(proc=_proc_div(_paragraph("P", _display("UNKNOWN-FIELD")))),
            resolver,
        )
        assert "UNKNOWN-FIELD" in diagnostics[0].message


# ===========================================================================
# Traversal continuity
# ===========================================================================


class TestTraversalContinuity:
    """Traversal never aborts after a resolution error."""

    def test_traversal_continues_after_undefined_variable(self) -> None:
        """Clean references after an error are still resolved."""
        table = _populated_table("GOOD-VAR")
        resolver, _, diagnostics = _make_resolver(table=table)
        traverse_program(
            _program(
                proc=_proc_div(
                    _paragraph(
                        "P",
                        _move("1", "BAD-VAR", line=20),  # undefined → SEM003
                        _move("1", "GOOD-VAR", line=21),  # declared → OK
                    )
                )
            ),
            resolver,
        )
        assert len(diagnostics) == 1

    def test_multiple_errors_all_collected(self) -> None:
        """Multiple undefined references each produce a diagnostic."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(
                proc=_proc_div(
                    _paragraph(
                        "P",
                        _move("1", "A", line=20),
                        _move("1", "B", line=21),
                        _move("1", "C", line=22),
                    )
                )
            ),
            resolver,
        )
        assert len(diagnostics) == 3

    def test_errors_across_multiple_paragraphs(self) -> None:
        """Errors in different paragraphs are all reported."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(
                proc=_proc_div(
                    _paragraph("P1", _move("1", "MISS-A", line=20), line=20),
                    _paragraph("P2", _move("1", "MISS-B", line=30), line=30),
                )
            ),
            resolver,
        )
        assert len(diagnostics) == 2

    def test_stop_run_and_goback_produce_no_diagnostics(self) -> None:
        """STOP RUN and GOBACK statements produce no diagnostics."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(
                proc=_proc_div(
                    _paragraph("P", _stop_run(), _goback()),
                )
            ),
            resolver,
        )
        assert len(diagnostics) == 0


# ===========================================================================
# Empty / minimal programs
# ===========================================================================


class TestEmptyProgramResolution:
    """ReferenceResolverVisitor handles empty / minimal ASTs gracefully."""

    def test_empty_program_no_diagnostics(self) -> None:
        """Completely empty ProgramNode produces no resolution diagnostics."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(_program(), resolver)
        assert len(diagnostics) == 0

    def test_program_with_no_statements_no_diagnostics(self) -> None:
        """Program with paragraphs but no statements produces no diagnostics."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(proc=_proc_div(_paragraph("INIT"), _paragraph("MAIN"))),
            resolver,
        )
        assert len(diagnostics) == 0

    def test_program_with_no_procedure_division(self) -> None:
        """No PROCEDURE DIVISION → no resolution diagnostics."""
        resolver, _, diagnostics = _make_resolver()
        traverse_program(
            _program(
                ident=_ident_div("NOPROC"),
                data=_data_div(ws=_working_storage(_elementary("WS-X"))),
            ),
            resolver,
        )
        assert len(diagnostics) == 0


# ===========================================================================
# Paragraph and section reference resolution helpers
# ===========================================================================


class TestParagraphAndSectionResolution:
    """Internal helpers _resolve_paragraph_reference and _resolve_section_reference."""

    def test_declared_paragraph_reference_no_diagnostic(self) -> None:
        """Declared paragraph resolved silently."""
        table = SymbolTable()
        pos = _pos()
        table.register(ParagraphSymbol(name="MAIN-PARA", declared_at=pos))
        resolver, _, diagnostics = _make_resolver(table=table)
        resolver._resolve_paragraph_reference("MAIN-PARA", pos)
        assert len(diagnostics) == 0

    def test_undeclared_paragraph_reference_emits_sem004(self) -> None:
        """Undeclared paragraph emits SEM004."""
        resolver, _, diagnostics = _make_resolver()
        resolver._resolve_paragraph_reference("MISSING-PARA", _pos(line=42))
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "SEM004"
        assert diagnostics[0].severity is SemanticSeverity.ERROR
        assert "MISSING-PARA" in diagnostics[0].message
        assert diagnostics[0].position.line == 42

    def test_section_reference_emits_sem005(self) -> None:
        """Undeclared section emits SEM005."""
        resolver, _, diagnostics = _make_resolver()
        resolver._resolve_section_reference("MISSING-SECTION", _pos(line=10))
        assert len(diagnostics) == 1
        assert diagnostics[0].code == "SEM005"
        assert diagnostics[0].severity is SemanticSeverity.ERROR
        assert "MISSING-SECTION" in diagnostics[0].message


# ===========================================================================
# Representative COBOL program (end-to-end)
# ===========================================================================


class TestRepresentativeProgram:
    """End-to-end reference resolution on a representative COBOL program."""

    def _build_clean_program(self) -> ProgramNode:
        """All MOVE/DISPLAY operands are declared variables."""
        ws = _working_storage(
            _elementary("WS-COUNT", level=77, picture="9(5)", line=6),
            _elementary("WS-NAME", level=77, picture="X(30)", line=7),
            _elementary("WS-TOTAL", level=77, picture="S9(9)V99", line=8),
        )
        proc = _proc_div(
            _paragraph(
                "INIT",
                _move("0", "WS-COUNT", line=21),
                _move("SPACES", "WS-NAME", line=22),
                line=20,
            ),
            _paragraph(
                "PROCESS",
                _display("WS-NAME", line=31),
                _move("WS-COUNT", "WS-TOTAL", line=32),
                line=30,
            ),
            _paragraph("DONE", _stop_run(), line=40),
        )
        return _program(ident=_ident_div("PAYROLL"), data=_data_div(ws=ws), proc=proc)

    def _build_dirty_program(self) -> ProgramNode:
        """Some MOVE operands are undeclared variables."""
        ws = _working_storage(
            _elementary("WS-COUNT", level=77, picture="9(5)", line=6),
        )
        proc = _proc_div(
            _paragraph(
                "MAIN",
                _move("0", "WS-COUNT", line=21),  # OK
                _move("MISSING-A", "WS-COUNT", line=22),  # SEM003
                _move("0", "MISSING-B", line=23),  # SEM003
                line=20,
            )
        )
        return _program(ident=_ident_div("DIRTY"), data=_data_div(ws=ws), proc=proc)

    def _run_two_pass(self, program: ProgramNode) -> list[SemanticDiagnostic]:
        table: SymbolTable = SymbolTable()
        diagnostics: list[SemanticDiagnostic] = []
        SymbolCollectorVisitor(table=table, diagnostics=diagnostics)
        traverse_program(
            program, SymbolCollectorVisitor(table=table, diagnostics=diagnostics)
        )
        traverse_program(
            program, ReferenceResolverVisitor(table=table, diagnostics=diagnostics)
        )
        return diagnostics

    def test_clean_program_no_resolution_diagnostics(self) -> None:
        diagnostics = self._run_two_pass(self._build_clean_program())
        assert len(diagnostics) == 0

    def test_dirty_program_correct_sem003_count(self) -> None:
        diagnostics = self._run_two_pass(self._build_dirty_program())
        sem003 = [d for d in diagnostics if d.code == "SEM003"]
        assert len(sem003) == 2

    def test_dirty_program_correct_identifiers_in_messages(self) -> None:
        diagnostics = self._run_two_pass(self._build_dirty_program())
        messages = [d.message for d in diagnostics if d.code == "SEM003"]
        names_mentioned = " ".join(messages)
        assert "MISSING-A" in names_mentioned
        assert "MISSING-B" in names_mentioned


# ===========================================================================
# SemanticAnalyzer integration (regression guard)
# ===========================================================================


class TestSemanticAnalyzerIntegration:
    """Guard that SemanticAnalyzer uses both passes in the correct order."""

    def test_empty_program_clean(self) -> None:
        ctx = SemanticAnalyzer().analyse(_program())
        assert not ctx.has_errors

    def test_declared_move_operands_no_diagnostics(self) -> None:
        """Declared MOVE operands produce no diagnostics."""
        ws = _working_storage(
            _elementary("WS-A", line=6),
            _elementary("WS-B", line=7),
        )
        proc = _proc_div(_paragraph("P", _move("WS-A", "WS-B", line=20), line=20))
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws), proc=proc))
        assert not ctx.has_errors

    def test_undeclared_move_target_emits_sem003(self) -> None:
        """Undeclared target in MOVE emits SEM003 through both passes."""
        proc = _proc_div(_paragraph("P", _move("1", "MISSING-VAR", line=20), line=20))
        ctx = SemanticAnalyzer().analyse(_program(proc=proc))
        assert ctx.has_errors
        assert ctx.diagnostics[0].code == "SEM003"

    def test_undeclared_display_operand_emits_sem003(self) -> None:
        """Undeclared DISPLAY operand emits SEM003."""
        proc = _proc_div(_paragraph("P", _display("MISSING-FIELD", line=20), line=20))
        ctx = SemanticAnalyzer().analyse(_program(proc=proc))
        assert ctx.has_errors
        codes = [d.code for d in ctx.diagnostics]
        assert "SEM003" in codes

    def test_sem001_and_sem003_coexist(self) -> None:
        """Duplicate variable (SEM001) and undefined reference (SEM003) both reported."""
        ws = _working_storage(
            _elementary("DUP", line=10),
            _elementary("DUP", line=11),  # duplicate → SEM001
        )
        proc = _proc_div(
            _paragraph("P", _move("1", "MISSING", line=20), line=20)  # → SEM003
        )
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws), proc=proc))
        codes = {d.code for d in ctx.diagnostics}
        assert "SEM001" in codes
        assert "SEM003" in codes

    def test_pass_ordering_symbols_available_before_resolution(self) -> None:
        """Symbols declared in pass 1 are available to the resolver in pass 2."""
        # WS-FLAG declared in data division, referenced in MOVE —
        # only works if pass 1 runs before pass 2.
        ws = _working_storage(_elementary("WS-FLAG", line=6))
        proc = _proc_div(_paragraph("P", _move("1", "WS-FLAG", line=20), line=20))
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws), proc=proc))
        assert not ctx.has_errors

    def test_analyser_is_reusable(self) -> None:
        """SemanticAnalyzer can be reused for independent programs."""
        analyzer = SemanticAnalyzer()
        proc = _proc_div(_paragraph("P", _move("1", "MISSING", line=20), line=20))
        ctx1 = analyzer.analyse(_program(proc=proc))
        ctx2 = analyzer.analyse(_program())  # clean program
        assert ctx1.has_errors
        assert not ctx2.has_errors

    def test_literal_move_source_not_resolved(self) -> None:
        """Literal source in MOVE is not resolved — no false SEM003."""
        proc = _proc_div(_paragraph("P", _move('"INIT"', "MISSING", line=20), line=20))
        ctx = SemanticAnalyzer().analyse(_program(proc=proc))
        # Only MISSING produces a diagnostic, not "INIT"
        assert ctx.error_count == 1
        assert "MISSING" in ctx.diagnostics[0].message

    def test_symbol_table_still_populated_in_context(self) -> None:
        """SemanticContext symbol table remains accessible after both passes."""
        ws = _working_storage(
            _elementary("WS-A", line=6),
            _elementary("WS-B", line=7),
        )
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws)))
        assert len(ctx.symbol_table.symbols_of_kind(SymbolKind.VARIABLE)) == 2
