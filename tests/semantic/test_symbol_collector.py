"""
Comprehensive tests for TASK-019: AST Symbol Collection Visitor.

Purpose:
    Verify that :class:`SymbolCollectorVisitor` correctly traverses the COBOL
    AST and populates the symbol table — registering program, variable, and
    paragraph symbols, detecting duplicate declarations, emitting structured
    diagnostics, and continuing traversal after errors.

Coverage:
    SymbolCollectorVisitor construction:
        - Stores table and diagnostics references.
        - Works with any SymbolTable and diagnostics list.

    Program symbol registration:
        - PROGRAM-ID present → ProgramSymbol registered.
        - PROGRAM-ID absent → no symbol, no crash.
        - Program name uppercased.

    Variable symbol registration:
        - Single ElementaryItemNode → VariableSymbol.
        - Single GroupItemNode → VariableSymbol with picture=None.
        - Single ConditionNameNode (level 88) → VariableSymbol.
        - Multiple items → all registered in insertion order.
        - Empty WORKING-STORAGE → no variables.
        - No data division → no variables.

    Paragraph symbol registration:
        - Single ParagraphNode → ParagraphSymbol.
        - Multiple paragraphs → all registered.
        - Paragraph names uppercased.
        - No procedure division → no paragraphs.

    Duplicate detection:
        - Duplicate variable → SEM001 emitted, first survives.
        - Duplicate paragraph → SEM002 emitted, first survives.
        - Multiple duplicates → each produces its own diagnostic.
        - Traversal continues after duplicate — later clean symbols registered.
        - Diagnostic severity is ERROR.
        - Diagnostic message contains symbol name.
        - Diagnostic message contains previous declaration location.

    Empty AST:
        - Empty ProgramNode → empty table, no diagnostics.

    Representative full COBOL program:
        - All three divisions → all symbol kinds registered.
        - Correct total symbol count.
        - No spurious diagnostics.

    SemanticAnalyzer integration:
        - SemanticAnalyzer.analyse() uses SymbolCollectorVisitor internally.
        - Result SemanticContext is fully populated (regression guard).

Non-responsibilities:
    - Parser behaviour (covered in test_*_parser.py).
    - Lexer behaviour.
    - AST node field correctness (covered in other test modules).

Dependencies:
    - :mod:`app.parser.semantic`             — full public API.
    - :mod:`app.parser.semantic.symbol_collector` — the class under test.
    - :mod:`app.parser.ast.*`                — AST node types.
    - :mod:`app.parser.lexer.position`       — Position.
    - :mod:`pytest`                          — test framework.

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
from app.parser.ast.working_storage import WorkingStorageSectionNode
from app.parser.lexer.position import Position
from app.parser.semantic import (
    ParagraphSymbol,
    ProgramSymbol,
    SemanticAnalyzer,
    SemanticDiagnostic,
    SemanticSeverity,
    SymbolCollectorVisitor,
    SymbolKind,
    SymbolTable,
    VariableSymbol,
    traverse_program,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_FILE = "collector_test.cbl"


def _pos(line: int = 1, col: int = 1, offset: int = 0) -> Position:
    """Create a Position with the given coordinates."""
    return Position(line=line, column=col, offset=offset, filename=_FILE)


def _program_id_clause(name: str, line: int = 2) -> ProgramIdClauseNode:
    """Create a ProgramIdClauseNode."""
    pos = _pos(line=line)
    return ProgramIdClauseNode(start_position=pos, end_position=pos, value=name)


def _ident_div(
    program_name: str | None = "TESTPROG",
) -> IdentificationDivisionNode:
    """Create an IdentificationDivisionNode with optional PROGRAM-ID."""
    pos = _pos(line=1)
    pid = _program_id_clause(program_name) if program_name else None
    return IdentificationDivisionNode(
        start_position=pos, end_position=pos, program_id=pid
    )


def _elementary(
    name: str, level: int = 5, picture: str = "X", line: int = 10
) -> ElementaryItemNode:
    """Create an ElementaryItemNode."""
    pos = _pos(line=line)
    return ElementaryItemNode(
        start_position=pos, end_position=pos, level=level, name=name, picture=picture
    )


def _group(name: str, level: int = 1, line: int = 10) -> GroupItemNode:
    """Create a GroupItemNode."""
    pos = _pos(line=line)
    return GroupItemNode(
        start_position=pos, end_position=pos, level=level, name=name, children=()
    )


def _condition(name: str, value: str = "'Y'", line: int = 15) -> ConditionNameNode:
    """Create a ConditionNameNode."""
    pos = _pos(line=line)
    return ConditionNameNode(
        start_position=pos, end_position=pos, level=88, name=name, value=value
    )


def _paragraph(name: str, line: int = 20) -> ParagraphNode:
    """Create a ParagraphNode."""
    pos = _pos(line=line)
    return ParagraphNode(start_position=pos, end_position=pos, name=name, statements=())


def _working_storage(
    *items: ElementaryItemNode | GroupItemNode | ConditionNameNode,
) -> WorkingStorageSectionNode:
    """Create a WorkingStorageSectionNode."""
    pos = _pos(line=5)
    return WorkingStorageSectionNode(
        start_position=pos, end_position=pos, items=tuple(items)
    )


def _data_div(ws: WorkingStorageSectionNode | None = None) -> DataDivisionNode:
    """Create a DataDivisionNode."""
    pos = _pos(line=5)
    return DataDivisionNode(start_position=pos, end_position=pos, working_storage=ws)


def _proc_div(*paragraphs: ParagraphNode) -> ProcedureDivisionNode:
    """Create a ProcedureDivisionNode."""
    pos = _pos(line=20)
    return ProcedureDivisionNode(
        start_position=pos, end_position=pos, paragraphs=tuple(paragraphs)
    )


def _program(
    ident: IdentificationDivisionNode | None = None,
    data: DataDivisionNode | None = None,
    proc: ProcedureDivisionNode | None = None,
) -> ProgramNode:
    """Create a ProgramNode with optional divisions."""
    pos = _pos(line=1)
    return ProgramNode(
        start_position=pos,
        end_position=pos,
        identification_division=ident,
        data_division=data,
        procedure_division=proc,
    )


def _make_collector(
    table: SymbolTable | None = None,
    diagnostics: list[SemanticDiagnostic] | None = None,
) -> tuple[SymbolCollectorVisitor, SymbolTable, list[SemanticDiagnostic]]:
    """Create a SymbolCollectorVisitor with fresh state and return all three objects."""
    if table is None:
        table = SymbolTable()
    if diagnostics is None:
        diagnostics = []
    return (
        SymbolCollectorVisitor(table=table, diagnostics=diagnostics),
        table,
        diagnostics,
    )


# ===========================================================================
# Construction
# ===========================================================================


class TestSymbolCollectorVisitorConstruction:
    """Tests for SymbolCollectorVisitor construction."""

    def test_stores_table_reference(self) -> None:
        """SymbolCollectorVisitor stores the provided SymbolTable."""
        table = SymbolTable()
        collector = SymbolCollectorVisitor(table=table, diagnostics=[])
        assert collector._table is table

    def test_stores_diagnostics_reference(self) -> None:
        """SymbolCollectorVisitor stores the provided diagnostics list."""
        diagnostics: list[SemanticDiagnostic] = []
        collector = SymbolCollectorVisitor(table=SymbolTable(), diagnostics=diagnostics)
        assert collector._diagnostics is diagnostics

    def test_accepts_fresh_empty_table(self) -> None:
        """SymbolCollectorVisitor accepts a fresh SymbolTable without error."""
        collector, table, _ = _make_collector()
        assert len(table) == 0

    def test_accepts_pre_populated_table(self) -> None:
        """SymbolCollectorVisitor can be given a pre-populated table."""
        table = SymbolTable()
        pos = _pos()
        table.register(ProgramSymbol(name="EXISTING", declared_at=pos))
        collector = SymbolCollectorVisitor(table=table, diagnostics=[])
        assert len(collector._table) == 1

    def test_is_semantic_visitor_subclass(self) -> None:
        """SymbolCollectorVisitor is a SemanticVisitor."""
        from app.parser.semantic.visitors import SemanticVisitor

        collector, _, _ = _make_collector()
        assert isinstance(collector, SemanticVisitor)


# ===========================================================================
# Program symbol registration
# ===========================================================================


class TestSymbolCollectorProgramSymbol:
    """SymbolCollectorVisitor correctly registers the program symbol."""

    def test_program_id_present_registers_symbol(self) -> None:
        """PROGRAM-ID clause → ProgramSymbol registered in table."""
        collector, table, diagnostics = _make_collector()
        traverse_program(_program(ident=_ident_div("PAYROLL")), collector)
        sym = table.lookup("PAYROLL")
        assert sym is not None
        assert isinstance(sym, ProgramSymbol)
        assert sym.kind is SymbolKind.PROGRAM
        assert len(diagnostics) == 0

    def test_program_name_uppercased(self) -> None:
        """Program symbol name is stored in uppercase regardless of source case."""
        collector, table, _ = _make_collector()
        traverse_program(_program(ident=_ident_div("payroll")), collector)
        assert table.lookup("PAYROLL") is not None

    def test_program_id_absent_no_symbol_no_crash(self) -> None:
        """Absent PROGRAM-ID produces no symbol and no diagnostic."""
        collector, table, diagnostics = _make_collector()
        traverse_program(_program(ident=_ident_div(program_name=None)), collector)
        assert len(table) == 0
        assert len(diagnostics) == 0

    def test_no_identification_division_no_symbol(self) -> None:
        """No identification division produces no symbol."""
        collector, table, _ = _make_collector()
        traverse_program(_program(), collector)
        assert len(table.symbols_of_kind(SymbolKind.PROGRAM)) == 0

    def test_program_symbol_position_preserved(self) -> None:
        """ProgramSymbol.declared_at records the source position."""
        collector, table, _ = _make_collector()
        traverse_program(_program(ident=_ident_div("MYPROG")), collector)
        sym = table.lookup("MYPROG")
        assert sym is not None
        assert sym.declared_at.filename == _FILE


# ===========================================================================
# Variable symbol registration
# ===========================================================================


class TestSymbolCollectorVariableSymbols:
    """SymbolCollectorVisitor correctly registers Working-Storage variables."""

    def test_single_elementary_item(self) -> None:
        """ElementaryItemNode → VariableSymbol with correct level and picture."""
        ws = _working_storage(_elementary("WS-COUNT", level=77, picture="9(4)"))
        collector, table, _ = _make_collector()
        traverse_program(_program(data=_data_div(ws=ws)), collector)
        sym = table.lookup("WS-COUNT")
        assert sym is not None
        assert isinstance(sym, VariableSymbol)
        assert sym.kind is SymbolKind.VARIABLE
        assert sym.level == 77
        assert sym.picture == "9(4)"

    def test_group_item_registered_no_picture(self) -> None:
        """GroupItemNode → VariableSymbol with picture=None."""
        ws = _working_storage(_group("CUST-REC", level=1))
        collector, table, _ = _make_collector()
        traverse_program(_program(data=_data_div(ws=ws)), collector)
        sym = table.lookup("CUST-REC")
        assert sym is not None
        assert isinstance(sym, VariableSymbol)
        assert sym.picture is None

    def test_condition_name_registered_level_88(self) -> None:
        """ConditionNameNode → VariableSymbol at level 88."""
        ws = _working_storage(_condition("END-OF-FILE"))
        collector, table, _ = _make_collector()
        traverse_program(_program(data=_data_div(ws=ws)), collector)
        sym = table.lookup("END-OF-FILE")
        assert sym is not None
        assert isinstance(sym, VariableSymbol)
        assert sym.level == 88
        assert sym.picture is None

    def test_multiple_items_all_registered(self) -> None:
        """Multiple items in WORKING-STORAGE all produce VariableSymbol records."""
        ws = _working_storage(
            _group("CUST-REC", level=1, line=6),
            _elementary("CUST-ID", level=5, picture="9(5)", line=7),
            _elementary("CUST-NAME", level=5, picture="X(30)", line=8),
            _condition("END-OF-FILE", line=9),
        )
        collector, table, diagnostics = _make_collector()
        traverse_program(_program(data=_data_div(ws=ws)), collector)
        variables = table.symbols_of_kind(SymbolKind.VARIABLE)
        names = {s.name for s in variables}
        assert names == {"CUST-REC", "CUST-ID", "CUST-NAME", "END-OF-FILE"}
        assert len(diagnostics) == 0

    def test_empty_working_storage_no_variables(self) -> None:
        """Empty WORKING-STORAGE SECTION produces no VariableSymbols."""
        collector, table, _ = _make_collector()
        traverse_program(_program(data=_data_div(ws=_working_storage())), collector)
        assert len(table.symbols_of_kind(SymbolKind.VARIABLE)) == 0

    def test_no_data_division_no_variables(self) -> None:
        """Absent DATA DIVISION produces no VariableSymbols."""
        collector, table, _ = _make_collector()
        traverse_program(_program(), collector)
        assert len(table.symbols_of_kind(SymbolKind.VARIABLE)) == 0

    def test_variable_name_uppercased(self) -> None:
        """Variable names are stored in uppercase."""
        ws = _working_storage(_elementary("ws-amount", level=5, picture="9(9)"))
        collector, table, _ = _make_collector()
        traverse_program(_program(data=_data_div(ws=ws)), collector)
        assert table.lookup("WS-AMOUNT") is not None

    def test_insertion_order_preserved(self) -> None:
        """Variables are inserted in source order."""
        ws = _working_storage(
            _elementary("ALPHA", line=10),
            _elementary("BETA", line=11),
            _elementary("GAMMA", line=12),
        )
        collector, table, _ = _make_collector()
        traverse_program(_program(data=_data_div(ws=ws)), collector)
        variables = table.symbols_of_kind(SymbolKind.VARIABLE)
        assert [s.name for s in variables] == ["ALPHA", "BETA", "GAMMA"]

    def test_variable_position_preserved(self) -> None:
        """VariableSymbol.declared_at records the source line."""
        ws = _working_storage(_elementary("WS-FLAG", line=42))
        collector, table, _ = _make_collector()
        traverse_program(_program(data=_data_div(ws=ws)), collector)
        sym = table.lookup("WS-FLAG")
        assert sym is not None
        assert sym.declared_at.line == 42


# ===========================================================================
# Paragraph symbol registration
# ===========================================================================


class TestSymbolCollectorParagraphSymbols:
    """SymbolCollectorVisitor correctly registers paragraphs."""

    def test_single_paragraph_registered(self) -> None:
        """ParagraphNode → ParagraphSymbol in the table."""
        collector, table, diagnostics = _make_collector()
        traverse_program(_program(proc=_proc_div(_paragraph("MAIN-PARA"))), collector)
        sym = table.lookup("MAIN-PARA")
        assert sym is not None
        assert isinstance(sym, ParagraphSymbol)
        assert sym.kind is SymbolKind.PARAGRAPH
        assert len(diagnostics) == 0

    def test_multiple_paragraphs_all_registered(self) -> None:
        """Multiple paragraphs all produce ParagraphSymbol records."""
        collector, table, _ = _make_collector()
        traverse_program(
            _program(
                proc=_proc_div(
                    _paragraph("INIT-PARA"),
                    _paragraph("PROCESS-PARA"),
                    _paragraph("CLEANUP-PARA"),
                )
            ),
            collector,
        )
        paragraphs = table.symbols_of_kind(SymbolKind.PARAGRAPH)
        names = {s.name for s in paragraphs}
        assert names == {"INIT-PARA", "PROCESS-PARA", "CLEANUP-PARA"}

    def test_paragraph_name_uppercased(self) -> None:
        """Paragraph names are stored in uppercase."""
        collector, table, _ = _make_collector()
        traverse_program(_program(proc=_proc_div(_paragraph("main-para"))), collector)
        assert table.lookup("MAIN-PARA") is not None

    def test_no_procedure_division_no_paragraphs(self) -> None:
        """Absent PROCEDURE DIVISION produces no ParagraphSymbols."""
        collector, table, _ = _make_collector()
        traverse_program(_program(), collector)
        assert len(table.symbols_of_kind(SymbolKind.PARAGRAPH)) == 0

    def test_paragraph_position_preserved(self) -> None:
        """ParagraphSymbol.declared_at records the source line."""
        collector, table, _ = _make_collector()
        traverse_program(
            _program(proc=_proc_div(_paragraph("CALC-PARA", line=55))), collector
        )
        sym = table.lookup("CALC-PARA")
        assert sym is not None
        assert sym.declared_at.line == 55


# ===========================================================================
# Duplicate detection
# ===========================================================================


class TestSymbolCollectorDuplicateDetection:
    """SymbolCollectorVisitor emits diagnostics for duplicate declarations."""

    def test_duplicate_variable_emits_sem001(self) -> None:
        """Two variables with the same name emit one SEM001 diagnostic."""
        ws = _working_storage(
            _elementary("WS-COUNT", level=77, picture="9", line=10),
            _elementary("WS-COUNT", level=77, picture="9", line=15),
        )
        collector, table, diagnostics = _make_collector()
        traverse_program(_program(data=_data_div(ws=ws)), collector)
        assert len(diagnostics) == 1
        diag = diagnostics[0]
        assert diag.code == "SEM001"
        assert diag.severity is SemanticSeverity.ERROR

    def test_duplicate_variable_message_contains_name(self) -> None:
        """SEM001 message includes the variable name."""
        ws = _working_storage(
            _elementary("DUP-VAR", line=10),
            _elementary("DUP-VAR", line=15),
        )
        collector, _, diagnostics = _make_collector()
        traverse_program(_program(data=_data_div(ws=ws)), collector)
        assert "DUP-VAR" in diagnostics[0].message

    def test_duplicate_variable_message_contains_first_location(self) -> None:
        """SEM001 message includes the first declaration location."""
        ws = _working_storage(
            _elementary("DUP-VAR", line=10),
            _elementary("DUP-VAR", line=15),
        )
        collector, _, diagnostics = _make_collector()
        traverse_program(_program(data=_data_div(ws=ws)), collector)
        assert "10" in diagnostics[0].message

    def test_duplicate_variable_first_registration_survives(self) -> None:
        """The first variable registration is kept when a duplicate is detected."""
        ws = _working_storage(
            _elementary("VAR", level=5, picture="X", line=10),
            _elementary("VAR", level=5, picture="9", line=15),
        )
        collector, table, _ = _make_collector()
        traverse_program(_program(data=_data_div(ws=ws)), collector)
        sym = table.lookup("VAR")
        assert sym is not None
        assert isinstance(sym, VariableSymbol)
        assert sym.picture == "X"  # first registration survives

    def test_duplicate_paragraph_emits_sem002(self) -> None:
        """Two paragraphs with the same name emit one SEM002 diagnostic."""
        collector, table, diagnostics = _make_collector()
        traverse_program(
            _program(
                proc=_proc_div(
                    _paragraph("MAIN-PARA", line=20),
                    _paragraph("MAIN-PARA", line=30),
                )
            ),
            collector,
        )
        assert len(diagnostics) == 1
        diag = diagnostics[0]
        assert diag.code == "SEM002"
        assert diag.severity is SemanticSeverity.ERROR

    def test_duplicate_paragraph_message_contains_name(self) -> None:
        """SEM002 message includes the paragraph name."""
        collector, _, diagnostics = _make_collector()
        traverse_program(
            _program(proc=_proc_div(_paragraph("DUP"), _paragraph("DUP"))), collector
        )
        assert "DUP" in diagnostics[0].message

    def test_duplicate_paragraph_message_contains_first_location(self) -> None:
        """SEM002 message includes the first declaration location."""
        collector, _, diagnostics = _make_collector()
        traverse_program(
            _program(
                proc=_proc_div(
                    _paragraph("DUP-PARA", line=20),
                    _paragraph("DUP-PARA", line=30),
                )
            ),
            collector,
        )
        assert "20" in diagnostics[0].message

    def test_duplicate_paragraph_first_registration_survives(self) -> None:
        """The first paragraph registration is kept when a duplicate is detected."""
        collector, table, _ = _make_collector()
        traverse_program(
            _program(
                proc=_proc_div(
                    _paragraph("PARA", line=20),
                    _paragraph("PARA", line=30),
                )
            ),
            collector,
        )
        sym = table.lookup("PARA")
        assert sym is not None
        assert sym.declared_at.line == 20

    def test_multiple_duplicate_variables_each_produce_diagnostic(self) -> None:
        """Each duplicate variable produces its own diagnostic."""
        ws = _working_storage(
            _elementary("A", line=10),
            _elementary("A", line=11),
            _elementary("B", line=12),
            _elementary("B", line=13),
        )
        collector, _, diagnostics = _make_collector()
        traverse_program(_program(data=_data_div(ws=ws)), collector)
        assert len(diagnostics) == 2
        codes = [d.code for d in diagnostics]
        assert codes == ["SEM001", "SEM001"]

    def test_traversal_continues_after_duplicate(self) -> None:
        """Clean symbols after a duplicate are still registered."""
        ws = _working_storage(
            _elementary("DUP", line=10),
            _elementary("DUP", line=11),  # duplicate → diagnostic
            _elementary("CLEAN", line=12),  # still registered
        )
        collector, table, diagnostics = _make_collector()
        traverse_program(_program(data=_data_div(ws=ws)), collector)
        assert len(diagnostics) == 1
        assert table.lookup("CLEAN") is not None

    def test_diagnostics_position_is_duplicate_location(self) -> None:
        """The diagnostic position points to the *duplicate* declaration, not the first."""
        ws = _working_storage(
            _elementary("DUP", line=10),
            _elementary("DUP", line=20),
        )
        collector, _, diagnostics = _make_collector()
        traverse_program(_program(data=_data_div(ws=ws)), collector)
        assert diagnostics[0].position.line == 20

    def test_mixed_variable_and_paragraph_duplicates(self) -> None:
        """Variable and paragraph duplicates are both detected in one pass."""
        ws = _working_storage(
            _elementary("VAR", line=10),
            _elementary("VAR", line=11),
        )
        collector, table, diagnostics = _make_collector()
        traverse_program(
            _program(
                data=_data_div(ws=ws),
                proc=_proc_div(
                    _paragraph("PARA", line=20),
                    _paragraph("PARA", line=30),
                ),
            ),
            collector,
        )
        assert len(diagnostics) == 2
        sem001 = [d for d in diagnostics if d.code == "SEM001"]
        sem002 = [d for d in diagnostics if d.code == "SEM002"]
        assert len(sem001) == 1
        assert len(sem002) == 1


# ===========================================================================
# Empty AST
# ===========================================================================


class TestSymbolCollectorEmptyAST:
    """SymbolCollectorVisitor handles empty / minimal ASTs gracefully."""

    def test_empty_program_no_symbols_no_diagnostics(self) -> None:
        """Completely empty ProgramNode produces no symbols and no diagnostics."""
        collector, table, diagnostics = _make_collector()
        traverse_program(_program(), collector)
        assert len(table) == 0
        assert len(diagnostics) == 0

    def test_identification_only_no_variables_no_paragraphs(self) -> None:
        """Program with only IDENTIFICATION DIVISION produces one program symbol."""
        collector, table, diagnostics = _make_collector()
        traverse_program(_program(ident=_ident_div("IDONLY")), collector)
        assert len(table) == 1
        assert len(table.symbols_of_kind(SymbolKind.VARIABLE)) == 0
        assert len(table.symbols_of_kind(SymbolKind.PARAGRAPH)) == 0
        assert len(diagnostics) == 0

    def test_data_division_without_working_storage(self) -> None:
        """DATA DIVISION without a WORKING-STORAGE SECTION produces no variables."""
        collector, table, diagnostics = _make_collector()
        traverse_program(_program(data=_data_div(ws=None)), collector)
        assert len(table.symbols_of_kind(SymbolKind.VARIABLE)) == 0
        assert len(diagnostics) == 0

    def test_procedure_division_without_paragraphs(self) -> None:
        """PROCEDURE DIVISION without paragraphs produces no paragraph symbols."""
        collector, table, diagnostics = _make_collector()
        traverse_program(_program(proc=_proc_div()), collector)
        assert len(table.symbols_of_kind(SymbolKind.PARAGRAPH)) == 0
        assert len(diagnostics) == 0


# ===========================================================================
# Representative COBOL program (end-to-end)
# ===========================================================================


class TestSymbolCollectorRepresentativeProgram:
    """End-to-end symbol collection on a representative COBOL program structure."""

    def _build_program(self) -> ProgramNode:
        """Build a realistic COBOL program AST."""
        ident = _ident_div("CUSTMGR")
        ws = _working_storage(
            _group("CUSTOMER-RECORD", level=1, line=6),
            _elementary("CUSTOMER-ID", level=5, picture="9(5)", line=7),
            _elementary("CUSTOMER-NAME", level=5, picture="X(30)", line=8),
            _elementary("CUSTOMER-BALANCE", level=5, picture="S9(9)V99", line=9),
            _condition("CUSTOMER-ACTIVE", value="'Y'", line=10),
            _elementary("WS-EOF-FLAG", level=77, picture="9", line=11),
        )
        proc = _proc_div(
            _paragraph("0000-MAIN-LOGIC", line=20),
            _paragraph("1000-INITIALISE", line=30),
            _paragraph("2000-PROCESS-RECORD", line=40),
            _paragraph("3000-WRITE-OUTPUT", line=50),
            _paragraph("9999-CLEANUP", line=60),
        )
        return _program(ident=ident, data=_data_div(ws=ws), proc=proc)

    def test_all_symbol_kinds_registered(self) -> None:
        """All three symbol kinds are present in the table."""
        collector, table, _ = _make_collector()
        traverse_program(self._build_program(), collector)
        assert len(table.symbols_of_kind(SymbolKind.PROGRAM)) == 1
        assert len(table.symbols_of_kind(SymbolKind.VARIABLE)) == 6
        assert len(table.symbols_of_kind(SymbolKind.PARAGRAPH)) == 5

    def test_total_symbol_count(self) -> None:
        """Total symbol count matches sum of all kinds."""
        collector, table, _ = _make_collector()
        traverse_program(self._build_program(), collector)
        assert len(table) == 1 + 6 + 5

    def test_no_diagnostics_on_clean_program(self) -> None:
        """A well-formed program produces no diagnostics."""
        collector, _, diagnostics = _make_collector()
        traverse_program(self._build_program(), collector)
        assert len(diagnostics) == 0

    def test_program_symbol_name(self) -> None:
        """Program symbol holds the uppercased PROGRAM-ID name."""
        collector, table, _ = _make_collector()
        traverse_program(self._build_program(), collector)
        sym = table.lookup("CUSTMGR")
        assert sym is not None
        assert isinstance(sym, ProgramSymbol)

    def test_specific_variable_accessible(self) -> None:
        """Individual variable symbols can be retrieved by name."""
        collector, table, _ = _make_collector()
        traverse_program(self._build_program(), collector)
        sym = table.lookup("CUSTOMER-BALANCE")
        assert sym is not None
        assert isinstance(sym, VariableSymbol)
        assert sym.picture == "S9(9)V99"

    def test_specific_paragraph_accessible(self) -> None:
        """Individual paragraph symbols can be retrieved by name."""
        collector, table, _ = _make_collector()
        traverse_program(self._build_program(), collector)
        sym = table.lookup("2000-PROCESS-RECORD")
        assert sym is not None
        assert isinstance(sym, ParagraphSymbol)


# ===========================================================================
# Visitor reusability
# ===========================================================================


class TestSymbolCollectorReusability:
    """SymbolCollectorVisitor can be composed and reused correctly."""

    def test_visitor_populates_pre_existing_table(self) -> None:
        """Visitor appends to an already-populated table without clearing it."""
        table = SymbolTable()
        pos = _pos()
        table.register(ProgramSymbol(name="EXISTING", declared_at=pos))

        diagnostics: list[SemanticDiagnostic] = []
        collector = SymbolCollectorVisitor(table=table, diagnostics=diagnostics)
        ws = _working_storage(_elementary("NEW-VAR"))
        traverse_program(_program(data=_data_div(ws=ws)), collector)

        assert table.lookup("EXISTING") is not None
        assert table.lookup("NEW-VAR") is not None
        assert len(table) == 2

    def test_two_independent_collectors_independent_tables(self) -> None:
        """Two collectors with separate tables produce independent results."""
        table1: SymbolTable = SymbolTable()
        table2: SymbolTable = SymbolTable()
        diag1: list[SemanticDiagnostic] = []
        diag2: list[SemanticDiagnostic] = []

        c1 = SymbolCollectorVisitor(table=table1, diagnostics=diag1)
        c2 = SymbolCollectorVisitor(table=table2, diagnostics=diag2)

        p1 = _program(ident=_ident_div("PROG1"))
        p2 = _program(ident=_ident_div("PROG2"))

        traverse_program(p1, c1)
        traverse_program(p2, c2)

        assert table1.lookup("PROG1") is not None
        assert table1.lookup("PROG2") is None
        assert table2.lookup("PROG2") is not None
        assert table2.lookup("PROG1") is None

    def test_public_api_exports_symbol_collector_visitor(self) -> None:
        """SymbolCollectorVisitor is importable from the semantic package."""
        from app.parser.semantic import SymbolCollectorVisitor as SCV

        assert SCV is SymbolCollectorVisitor


# ===========================================================================
# SemanticAnalyzer integration (regression guard)
# ===========================================================================


class TestSemanticAnalyzerIntegration:
    """Guard that SemanticAnalyzer.analyse() still works via SymbolCollectorVisitor."""

    def test_analyse_empty_program_clean(self) -> None:
        """SemanticAnalyzer on empty program returns clean SemanticContext."""
        ctx = SemanticAnalyzer().analyse(_program())
        assert not ctx.has_errors
        assert len(ctx.symbol_table) == 0

    def test_analyse_full_program_populates_context(self) -> None:
        """SemanticAnalyzer returns a fully populated SemanticContext."""
        ident = _ident_div("FULLPROG")
        ws = _working_storage(
            _group("REC", level=1, line=6),
            _elementary("FIELD-A", level=5, picture="X(10)", line=7),
        )
        proc = _proc_div(
            _paragraph("INIT", line=20),
            _paragraph("PROCESS", line=25),
        )
        ctx = SemanticAnalyzer().analyse(
            _program(ident=ident, data=_data_div(ws=ws), proc=proc)
        )
        assert not ctx.has_errors
        assert len(ctx.symbol_table.symbols_of_kind(SymbolKind.PROGRAM)) == 1
        assert len(ctx.symbol_table.symbols_of_kind(SymbolKind.VARIABLE)) == 2
        assert len(ctx.symbol_table.symbols_of_kind(SymbolKind.PARAGRAPH)) == 2

    def test_analyse_duplicate_variable_emits_sem001(self) -> None:
        """SemanticAnalyzer still emits SEM001 via SymbolCollectorVisitor."""
        ws = _working_storage(
            _elementary("DUP", line=10),
            _elementary("DUP", line=15),
        )
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws)))
        assert ctx.has_errors
        assert ctx.diagnostics[0].code == "SEM001"

    def test_analyse_duplicate_paragraph_emits_sem002(self) -> None:
        """SemanticAnalyzer still emits SEM002 via SymbolCollectorVisitor."""
        ctx = SemanticAnalyzer().analyse(
            _program(proc=_proc_div(_paragraph("DUP"), _paragraph("DUP")))
        )
        assert ctx.has_errors
        assert ctx.diagnostics[0].code == "SEM002"
