"""
Comprehensive tests for TASK-018: Semantic Analyser Foundation.

Purpose:
    Verify that the COBOL semantic analyser correctly builds symbol tables,
    registers program/variable/paragraph symbols, detects duplicate
    declarations, and returns a populated SemanticContext — all without
    raising unhandled exceptions.

Coverage:
    Symbol types:
        - SymbolKind enumeration members.
        - ProgramSymbol construction and kind.
        - VariableSymbol construction, kind, level, picture.
        - ParagraphSymbol construction and kind.
        - Symbol immutability (frozen dataclass).

    SymbolTable:
        - Empty table has length zero.
        - register() returns True on first registration.
        - register() returns False for duplicate name.
        - lookup() finds registered symbol (case-insensitive).
        - lookup() returns None for unknown name.
        - all_symbols() returns defensive copy in insertion order.
        - symbols_of_kind() filters correctly.
        - __contains__ works with str name.
        - __len__ reflects registration count.

    SemanticDiagnostic:
        - Construction and field access.
        - __str__ format.
        - Frozen (immutable).
        - Equality.

    SemanticContext:
        - has_errors False when diagnostics empty.
        - has_errors True when ERROR diagnostic present.
        - error_count correct.
        - diagnostics property returns defensive copy.
        - symbol_table property returns the table.

    SemanticVisitor:
        - All default visit_* methods return None.
        - Subclass can selectively override hooks.

    traverse_program:
        - Visits program node.
        - Visits identification division.
        - Visits data division and working-storage items.
        - Visits procedure division and paragraphs.
        - Handles None divisions gracefully.

    SemanticAnalyzer:
        - Empty program (no divisions) → clean context.
        - Program with PROGRAM-ID → ProgramSymbol registered.
        - Working-storage items → VariableSymbol records registered.
        - Paragraphs → ParagraphSymbol records registered.
        - Duplicate variable → SEM001 diagnostic emitted.
        - Duplicate paragraph → SEM002 diagnostic emitted.
        - Full program → all symbol kinds registered.
        - Multiple errors accumulated in one pass.
        - Reusable analyser produces independent contexts.
        - Missing PROGRAM-ID → no crash.

Non-responsibilities:
    - Parser behaviour (covered in test_*_parser.py).
    - Lexer behaviour.
    - AST node field correctness (covered in other test modules).

Dependencies:
    - :mod:`app.parser.semantic`             — full public API.
    - :mod:`app.parser.ast.*`                — AST node types.
    - :mod:`app.parser.lexer.position`       — Position.
    - :mod:`pytest`                          — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pytest

from app.parser.ast.clauses import ProgramIdClauseNode
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
    SemanticContext,
    SemanticDiagnostic,
    SemanticSeverity,
    SemanticVisitor,
    Symbol,
    SymbolKind,
    SymbolTable,
    VariableSymbol,
    traverse_program,
)
from app.parser.ast.data import DataDivisionNode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FILE = "test.cbl"


def _pos(line: int = 1, col: int = 1, offset: int = 0) -> Position:
    """Create a Position with the given coordinates."""
    return Position(line=line, column=col, offset=offset, filename=_FILE)


def _program_id_clause(name: str, line: int = 2) -> ProgramIdClauseNode:
    """Create a ProgramIdClauseNode."""
    pos = _pos(line=line)
    return ProgramIdClauseNode(start_position=pos, end_position=pos, value=name)


def _ident_div(program_name: str | None = "TESTPROG") -> IdentificationDivisionNode:
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


# ===========================================================================
# SymbolKind tests
# ===========================================================================


class TestSymbolKind:
    """Tests for the SymbolKind enumeration."""

    def test_program_member(self) -> None:
        """PROGRAM member has value 'program'."""
        assert SymbolKind.PROGRAM.value == "program"

    def test_variable_member(self) -> None:
        """VARIABLE member has value 'variable'."""
        assert SymbolKind.VARIABLE.value == "variable"

    def test_paragraph_member(self) -> None:
        """PARAGRAPH member has value 'paragraph'."""
        assert SymbolKind.PARAGRAPH.value == "paragraph"

    def test_all_members_present(self) -> None:
        """All three expected members exist."""
        values = {m.value for m in SymbolKind}
        assert values == {"program", "variable", "paragraph"}


# ===========================================================================
# Symbol subclass tests
# ===========================================================================


class TestProgramSymbol:
    """Tests for ProgramSymbol."""

    def test_construction(self) -> None:
        """ProgramSymbol stores name and position."""
        pos = _pos()
        sym = ProgramSymbol(name="PAYROLL", declared_at=pos)
        assert sym.name == "PAYROLL"
        assert sym.declared_at is pos

    def test_kind(self) -> None:
        """ProgramSymbol.kind is SymbolKind.PROGRAM."""
        pos = _pos()
        sym = ProgramSymbol(name="X", declared_at=pos)
        assert sym.kind is SymbolKind.PROGRAM

    def test_immutable(self) -> None:
        """ProgramSymbol is frozen and cannot be mutated."""
        pos = _pos()
        sym = ProgramSymbol(name="X", declared_at=pos)
        with pytest.raises((AttributeError, TypeError)):
            sym.name = "Y"  # type: ignore[misc]

    def test_is_symbol_subclass(self) -> None:
        """ProgramSymbol is a subclass of Symbol."""
        pos = _pos()
        sym = ProgramSymbol(name="X", declared_at=pos)
        assert isinstance(sym, Symbol)


class TestVariableSymbol:
    """Tests for VariableSymbol."""

    def test_construction_with_picture(self) -> None:
        """VariableSymbol stores name, position, level, and picture."""
        pos = _pos()
        sym = VariableSymbol(name="WS-COUNT", declared_at=pos, level=77, picture="9(4)")
        assert sym.name == "WS-COUNT"
        assert sym.level == 77
        assert sym.picture == "9(4)"

    def test_construction_without_picture(self) -> None:
        """VariableSymbol picture defaults to None for group items."""
        pos = _pos()
        sym = VariableSymbol(name="CUST-REC", declared_at=pos, level=1)
        assert sym.picture is None

    def test_kind(self) -> None:
        """VariableSymbol.kind is SymbolKind.VARIABLE."""
        pos = _pos()
        sym = VariableSymbol(name="X", declared_at=pos, level=5, picture="X")
        assert sym.kind is SymbolKind.VARIABLE

    def test_immutable(self) -> None:
        """VariableSymbol is frozen and cannot be mutated."""
        pos = _pos()
        sym = VariableSymbol(name="X", declared_at=pos, level=5, picture="X")
        with pytest.raises((AttributeError, TypeError)):
            sym.level = 99  # type: ignore[misc]


class TestParagraphSymbol:
    """Tests for ParagraphSymbol."""

    def test_construction(self) -> None:
        """ParagraphSymbol stores name and position."""
        pos = _pos()
        sym = ParagraphSymbol(name="MAIN-PARA", declared_at=pos)
        assert sym.name == "MAIN-PARA"
        assert sym.declared_at is pos

    def test_kind(self) -> None:
        """ParagraphSymbol.kind is SymbolKind.PARAGRAPH."""
        pos = _pos()
        sym = ParagraphSymbol(name="MAIN-PARA", declared_at=pos)
        assert sym.kind is SymbolKind.PARAGRAPH

    def test_immutable(self) -> None:
        """ParagraphSymbol is frozen and cannot be mutated."""
        pos = _pos()
        sym = ParagraphSymbol(name="MAIN-PARA", declared_at=pos)
        with pytest.raises((AttributeError, TypeError)):
            sym.name = "OTHER"  # type: ignore[misc]


# ===========================================================================
# SymbolTable tests
# ===========================================================================


class TestSymbolTable:
    """Tests for SymbolTable."""

    def test_empty_table_has_zero_length(self) -> None:
        """A new table has no symbols."""
        table = SymbolTable()
        assert len(table) == 0

    def test_register_returns_true_on_first_registration(self) -> None:
        """First registration of a name returns True."""
        pos = _pos()
        sym = ProgramSymbol(name="PAYROLL", declared_at=pos)
        table = SymbolTable()
        assert table.register(sym) is True

    def test_register_returns_false_for_duplicate(self) -> None:
        """Second registration with same name returns False."""
        pos = _pos()
        sym = ProgramSymbol(name="PAYROLL", declared_at=pos)
        table = SymbolTable()
        table.register(sym)
        assert table.register(sym) is False

    def test_register_increases_length(self) -> None:
        """Length increases after each successful registration."""
        table = SymbolTable()
        for i in range(3):
            pos = _pos(line=i + 1)
            sym = ParagraphSymbol(name=f"PARA-{i}", declared_at=pos)
            table.register(sym)
        assert len(table) == 3

    def test_duplicate_does_not_increase_length(self) -> None:
        """Failed (duplicate) registration does not increase length."""
        pos = _pos()
        sym = ProgramSymbol(name="X", declared_at=pos)
        table = SymbolTable()
        table.register(sym)
        table.register(sym)
        assert len(table) == 1

    def test_lookup_finds_registered_symbol(self) -> None:
        """lookup() returns the registered symbol."""
        pos = _pos()
        sym = ProgramSymbol(name="PAYROLL", declared_at=pos)
        table = SymbolTable()
        table.register(sym)
        assert table.lookup("PAYROLL") is sym

    def test_lookup_case_insensitive(self) -> None:
        """lookup() is case-insensitive."""
        pos = _pos()
        sym = VariableSymbol(name="WS-COUNT", declared_at=pos, level=77, picture="9")
        table = SymbolTable()
        table.register(sym)
        assert table.lookup("ws-count") is sym
        assert table.lookup("WS-COUNT") is sym
        assert table.lookup("Ws-Count") is sym

    def test_lookup_returns_none_for_missing(self) -> None:
        """lookup() returns None when the name is not registered."""
        table = SymbolTable()
        assert table.lookup("MISSING") is None

    def test_all_symbols_returns_defensive_copy(self) -> None:
        """all_symbols() returns a new list each time."""
        pos = _pos()
        sym = ProgramSymbol(name="P", declared_at=pos)
        table = SymbolTable()
        table.register(sym)
        lst1 = table.all_symbols()
        lst2 = table.all_symbols()
        assert lst1 is not lst2
        assert lst1 == lst2

    def test_all_symbols_preserves_insertion_order(self) -> None:
        """all_symbols() returns symbols in insertion order."""
        table = SymbolTable()
        names = ["ALPHA", "BETA", "GAMMA"]
        for name in names:
            pos = _pos()
            table.register(
                VariableSymbol(name=name, declared_at=pos, level=5, picture="X")
            )
        assert [s.name for s in table.all_symbols()] == names

    def test_symbols_of_kind_filters_correctly(self) -> None:
        """symbols_of_kind() returns only symbols of the requested kind."""
        table = SymbolTable()
        pos = _pos()
        table.register(ProgramSymbol(name="PROG", declared_at=pos))
        table.register(
            VariableSymbol(name="VAR1", declared_at=pos, level=5, picture="X")
        )
        table.register(
            VariableSymbol(name="VAR2", declared_at=pos, level=77, picture="9")
        )
        table.register(ParagraphSymbol(name="PARA1", declared_at=pos))

        variables = table.symbols_of_kind(SymbolKind.VARIABLE)
        assert len(variables) == 2
        assert all(s.kind is SymbolKind.VARIABLE for s in variables)

        programs = table.symbols_of_kind(SymbolKind.PROGRAM)
        assert len(programs) == 1

        paragraphs = table.symbols_of_kind(SymbolKind.PARAGRAPH)
        assert len(paragraphs) == 1

    def test_contains_name_present(self) -> None:
        """__contains__ returns True for a registered name."""
        pos = _pos()
        sym = ProgramSymbol(name="PAYROLL", declared_at=pos)
        table = SymbolTable()
        table.register(sym)
        assert "PAYROLL" in table
        assert "payroll" in table  # case-insensitive

    def test_contains_name_absent(self) -> None:
        """__contains__ returns False for an unregistered name."""
        table = SymbolTable()
        assert "MISSING" not in table


# ===========================================================================
# SemanticDiagnostic tests
# ===========================================================================


class TestSemanticDiagnostic:
    """Tests for SemanticDiagnostic."""

    def _make(
        self, msg: str = "test error", code: str = "SEM001"
    ) -> SemanticDiagnostic:
        return SemanticDiagnostic(
            message=msg,
            position=_pos(line=5, col=4),
            severity=SemanticSeverity.ERROR,
            code=code,
        )

    def test_construction_and_fields(self) -> None:
        """SemanticDiagnostic stores all fields correctly."""
        diag = self._make()
        assert diag.message == "test error"
        assert diag.severity is SemanticSeverity.ERROR
        assert diag.code == "SEM001"
        assert diag.position.line == 5

    def test_str_format(self) -> None:
        """str(SemanticDiagnostic) includes filename, line, severity, code, message."""
        diag = self._make(msg="dup var 'X'", code="SEM001")
        result = str(diag)
        assert _FILE in result
        assert "5" in result
        assert "ERROR" in result
        assert "SEM001" in result
        assert "dup var" in result

    def test_frozen(self) -> None:
        """SemanticDiagnostic is frozen and cannot be mutated."""
        diag = self._make()
        with pytest.raises((AttributeError, TypeError)):
            diag.message = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        """Two diagnostics with equal fields are equal."""
        d1 = self._make()
        d2 = self._make()
        assert d1 == d2

    def test_severity_members(self) -> None:
        """SemanticSeverity has ERROR and WARNING members."""
        assert SemanticSeverity.ERROR.value == "error"
        assert SemanticSeverity.WARNING.value == "warning"


# ===========================================================================
# SemanticContext tests
# ===========================================================================


class TestSemanticContext:
    """Tests for SemanticContext."""

    def test_empty_context_no_errors(self) -> None:
        """A context with no diagnostics has no errors."""
        ctx = SemanticContext(symbol_table=SymbolTable(), diagnostics=[])
        assert ctx.has_errors is False
        assert ctx.error_count == 0

    def test_context_with_error_diagnostic(self) -> None:
        """A context with an ERROR diagnostic has errors."""
        diag = SemanticDiagnostic(
            message="dup",
            position=_pos(),
            severity=SemanticSeverity.ERROR,
            code="SEM001",
        )
        ctx = SemanticContext(symbol_table=SymbolTable(), diagnostics=[diag])
        assert ctx.has_errors is True
        assert ctx.error_count == 1

    def test_error_count_ignores_warnings(self) -> None:
        """error_count counts only ERROR-level diagnostics."""
        warning = SemanticDiagnostic(
            message="warn",
            position=_pos(),
            severity=SemanticSeverity.WARNING,
            code="SEM099",
        )
        ctx = SemanticContext(symbol_table=SymbolTable(), diagnostics=[warning])
        assert ctx.has_errors is False
        assert ctx.error_count == 0

    def test_diagnostics_returns_defensive_copy(self) -> None:
        """diagnostics property returns a new list each time."""
        ctx = SemanticContext(symbol_table=SymbolTable(), diagnostics=[])
        lst1 = ctx.diagnostics
        lst2 = ctx.diagnostics
        assert lst1 is not lst2

    def test_symbol_table_accessible(self) -> None:
        """symbol_table property returns the SymbolTable."""
        table = SymbolTable()
        ctx = SemanticContext(symbol_table=table, diagnostics=[])
        assert ctx.symbol_table is table


# ===========================================================================
# SemanticVisitor tests
# ===========================================================================


class TestSemanticVisitor:
    """Tests for SemanticVisitor default implementations."""

    def test_all_default_methods_return_none(self) -> None:
        """Every visit_* method on SemanticVisitor returns None by default."""

        class Noop(SemanticVisitor):
            pass

        visitor = Noop()
        assert visitor.visit_program(None) is None  # type: ignore[arg-type]
        assert visitor.visit_identification_division(None) is None  # type: ignore[arg-type]
        assert visitor.visit_data_division(None) is None  # type: ignore[arg-type]
        assert visitor.visit_working_storage_section(None) is None  # type: ignore[arg-type]
        assert visitor.visit_data_item(None) is None  # type: ignore[arg-type]
        assert visitor.visit_elementary_item(None) is None  # type: ignore[arg-type]
        assert visitor.visit_group_item(None) is None  # type: ignore[arg-type]
        assert visitor.visit_condition_name(None) is None  # type: ignore[arg-type]
        assert visitor.visit_procedure_division(None) is None  # type: ignore[arg-type]
        assert visitor.visit_paragraph(None) is None  # type: ignore[arg-type]

    def test_subclass_overrides_single_hook(self) -> None:
        """A subclass can override just one visit_* hook."""

        class ParaCollector(SemanticVisitor):
            def __init__(self) -> None:
                self.names: list[str] = []

            def visit_paragraph(self, node: ParagraphNode) -> None:
                self.names.append(node.name)

        collector = ParaCollector()
        para = _paragraph("MAIN-PARA")
        collector.visit_paragraph(para)
        assert collector.names == ["MAIN-PARA"]


# ===========================================================================
# traverse_program tests
# ===========================================================================


class TestTraverseProgram:
    """Tests for the traverse_program traversal driver."""

    def test_visits_program_node(self) -> None:
        """traverse_program calls visit_program on the root node."""
        visited: list[str] = []

        class V(SemanticVisitor):
            def visit_program(self, node: ProgramNode) -> None:
                visited.append("program")

        program = _program()
        traverse_program(program, V())
        assert "program" in visited

    def test_visits_identification_division(self) -> None:
        """traverse_program visits the identification division when present."""
        visited: list[str] = []

        class V(SemanticVisitor):
            def visit_identification_division(
                self, node: IdentificationDivisionNode
            ) -> None:
                visited.append("identification")

        program = _program(ident=_ident_div())
        traverse_program(program, V())
        assert "identification" in visited

    def test_skips_missing_identification_division(self) -> None:
        """traverse_program does not crash when identification division is None."""

        class V(SemanticVisitor):
            def visit_identification_division(
                self, node: IdentificationDivisionNode
            ) -> None:
                raise AssertionError("Should not be called")

        traverse_program(_program(), V())  # no crash

    def test_visits_working_storage_items(self) -> None:
        """traverse_program visits each data item in the working-storage section."""
        visited: list[str] = []

        class V(SemanticVisitor):
            def visit_elementary_item(self, node: ElementaryItemNode) -> None:
                visited.append(node.name)

        ws = _working_storage(
            _elementary("VAR-A"),
            _elementary("VAR-B"),
        )
        program = _program(data=_data_div(ws=ws))
        traverse_program(program, V())
        assert visited == ["VAR-A", "VAR-B"]

    def test_visits_paragraphs(self) -> None:
        """traverse_program visits each paragraph in the procedure division."""
        visited: list[str] = []

        class V(SemanticVisitor):
            def visit_paragraph(self, node: ParagraphNode) -> None:
                visited.append(node.name)

        program = _program(proc=_proc_div(_paragraph("PARA-A"), _paragraph("PARA-B")))
        traverse_program(program, V())
        assert visited == ["PARA-A", "PARA-B"]

    def test_handles_program_with_no_divisions(self) -> None:
        """traverse_program does not crash on a minimal program."""
        traverse_program(_program(), SemanticVisitor())  # no crash


# ===========================================================================
# SemanticAnalyzer tests
# ===========================================================================


class TestSemanticAnalyzerEmpty:
    """SemanticAnalyzer on minimal / empty programs."""

    def test_empty_program_returns_clean_context(self) -> None:
        """An empty ProgramNode produces a context with no errors and no symbols."""
        ctx = SemanticAnalyzer().analyse(_program())
        assert not ctx.has_errors
        assert ctx.error_count == 0
        assert len(ctx.symbol_table) == 0

    def test_missing_program_id_emits_sem006(self) -> None:
        """A program with an identification division but no PROGRAM-ID emits SEM006.

        Previously this test asserted ``not ctx.has_errors`` because pass 3
        (SemanticValidationVisitor) did not yet exist.  With TASK-021 pass 3
        correctly flags missing PROGRAM-ID as SEM006.
        """
        program = _program(ident=_ident_div(program_name=None))
        ctx = SemanticAnalyzer().analyse(program)
        # Pass 3 emits SEM006 for the missing PROGRAM-ID.
        codes = {d.code for d in ctx.diagnostics}
        assert "SEM006" in codes
        # Symbol table still has no program symbol (pass 1 couldn't register one).
        assert len(ctx.symbol_table.symbols_of_kind(SymbolKind.PROGRAM)) == 0


class TestSemanticAnalyzerProgramSymbol:
    """SemanticAnalyzer correctly registers the program symbol."""

    def test_program_id_registered(self) -> None:
        """PROGRAM-ID clause produces a ProgramSymbol in the symbol table."""
        program = _program(ident=_ident_div("PAYROLL"))
        ctx = SemanticAnalyzer().analyse(program)
        sym = ctx.symbol_table.lookup("PAYROLL")
        assert sym is not None
        assert isinstance(sym, ProgramSymbol)
        assert sym.kind is SymbolKind.PROGRAM

    def test_program_symbol_name_uppercased(self) -> None:
        """Program symbol name is stored in uppercase."""
        program = _program(ident=_ident_div("payroll"))
        ctx = SemanticAnalyzer().analyse(program)
        assert ctx.symbol_table.lookup("PAYROLL") is not None

    def test_program_symbol_count_is_one(self) -> None:
        """Exactly one ProgramSymbol is registered per program."""
        program = _program(ident=_ident_div("MYPROG"))
        ctx = SemanticAnalyzer().analyse(program)
        assert len(ctx.symbol_table.symbols_of_kind(SymbolKind.PROGRAM)) == 1


class TestSemanticAnalyzerVariableRegistration:
    """SemanticAnalyzer correctly registers Working-Storage variables."""

    def test_elementary_item_registered(self) -> None:
        """An ElementaryItemNode produces a VariableSymbol."""
        ws = _working_storage(_elementary("WS-COUNT", level=77, picture="9(4)"))
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws)))
        sym = ctx.symbol_table.lookup("WS-COUNT")
        assert sym is not None
        assert isinstance(sym, VariableSymbol)
        assert sym.kind is SymbolKind.VARIABLE
        assert sym.level == 77
        assert sym.picture == "9(4)"

    def test_group_item_registered_without_picture(self) -> None:
        """A GroupItemNode produces a VariableSymbol with picture=None."""
        ws = _working_storage(_group("CUST-REC", level=1))
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws)))
        sym = ctx.symbol_table.lookup("CUST-REC")
        assert sym is not None
        assert isinstance(sym, VariableSymbol)
        assert sym.picture is None

    def test_condition_name_registered(self) -> None:
        """A ConditionNameNode produces a VariableSymbol at level 88."""
        ws = _working_storage(_condition("END-OF-FILE"))
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws)))
        sym = ctx.symbol_table.lookup("END-OF-FILE")
        assert sym is not None
        assert isinstance(sym, VariableSymbol)
        assert sym.level == 88

    def test_multiple_variables_registered(self) -> None:
        """Multiple data items all produce VariableSymbol records."""
        ws = _working_storage(
            _group("CUST-REC", level=1),
            _elementary("CUST-ID", level=5, picture="9(5)"),
            _elementary("CUST-NAME", level=5, picture="X(30)"),
        )
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws)))
        variables = ctx.symbol_table.symbols_of_kind(SymbolKind.VARIABLE)
        names = {s.name for s in variables}
        assert names == {"CUST-REC", "CUST-ID", "CUST-NAME"}

    def test_empty_working_storage_no_variables(self) -> None:
        """An empty WORKING-STORAGE SECTION produces no VariableSymbols."""
        ctx = SemanticAnalyzer().analyse(
            _program(data=_data_div(ws=_working_storage()))
        )
        assert len(ctx.symbol_table.symbols_of_kind(SymbolKind.VARIABLE)) == 0

    def test_no_data_division_no_variables(self) -> None:
        """Absence of a DATA DIVISION produces no VariableSymbols."""
        ctx = SemanticAnalyzer().analyse(_program())
        assert len(ctx.symbol_table.symbols_of_kind(SymbolKind.VARIABLE)) == 0


class TestSemanticAnalyzerParagraphRegistration:
    """SemanticAnalyzer correctly registers paragraphs."""

    def test_paragraph_registered(self) -> None:
        """A ParagraphNode produces a ParagraphSymbol."""
        ctx = SemanticAnalyzer().analyse(
            _program(proc=_proc_div(_paragraph("MAIN-PARA")))
        )
        sym = ctx.symbol_table.lookup("MAIN-PARA")
        assert sym is not None
        assert isinstance(sym, ParagraphSymbol)
        assert sym.kind is SymbolKind.PARAGRAPH

    def test_multiple_paragraphs_registered(self) -> None:
        """Multiple paragraphs all produce ParagraphSymbol records."""
        ctx = SemanticAnalyzer().analyse(
            _program(
                proc=_proc_div(
                    _paragraph("INIT-PARA"),
                    _paragraph("PROCESS-PARA"),
                    _paragraph("CLEANUP-PARA"),
                )
            )
        )
        paragraphs = ctx.symbol_table.symbols_of_kind(SymbolKind.PARAGRAPH)
        assert len(paragraphs) == 3
        names = {s.name for s in paragraphs}
        assert names == {"INIT-PARA", "PROCESS-PARA", "CLEANUP-PARA"}

    def test_no_procedure_division_no_paragraphs(self) -> None:
        """Absence of a PROCEDURE DIVISION produces no ParagraphSymbols."""
        ctx = SemanticAnalyzer().analyse(_program())
        assert len(ctx.symbol_table.symbols_of_kind(SymbolKind.PARAGRAPH)) == 0


class TestSemanticAnalyzerDuplicateDetection:
    """SemanticAnalyzer correctly detects and reports duplicates."""

    def test_duplicate_variable_emits_sem001(self) -> None:
        """Two variables with the same name emit a SEM001 diagnostic."""
        ws = _working_storage(
            _elementary("WS-COUNT", level=77, picture="9", line=10),
            _elementary("WS-COUNT", level=77, picture="9", line=15),
        )
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws)))
        assert ctx.has_errors
        assert ctx.error_count == 1
        diag = ctx.diagnostics[0]
        assert diag.code == "SEM001"
        assert "WS-COUNT" in diag.message

    def test_duplicate_paragraph_emits_sem002(self) -> None:
        """Two paragraphs with the same name emit a SEM002 diagnostic."""
        ctx = SemanticAnalyzer().analyse(
            _program(
                proc=_proc_div(
                    _paragraph("MAIN-PARA", line=20),
                    _paragraph("MAIN-PARA", line=30),
                )
            )
        )
        assert ctx.has_errors
        assert ctx.error_count == 1
        diag = ctx.diagnostics[0]
        assert diag.code == "SEM002"
        assert "MAIN-PARA" in diag.message

    def test_duplicate_variable_first_registration_survives(self) -> None:
        """The first variable registration is kept; the duplicate is rejected."""
        ws = _working_storage(
            _elementary("VAR", level=5, picture="X", line=10),
            _elementary("VAR", level=5, picture="9", line=15),
        )
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws)))
        sym = ctx.symbol_table.lookup("VAR")
        assert sym is not None
        assert isinstance(sym, VariableSymbol)
        assert sym.picture == "X"  # first registration survives

    def test_duplicate_paragraph_first_registration_survives(self) -> None:
        """The first paragraph registration is kept; the duplicate is rejected."""
        ctx = SemanticAnalyzer().analyse(
            _program(
                proc=_proc_div(
                    _paragraph("PARA", line=20),
                    _paragraph("PARA", line=30),
                )
            )
        )
        sym = ctx.symbol_table.lookup("PARA")
        assert sym is not None
        assert sym.declared_at.line == 20

    def test_multiple_duplicate_variables_accumulate(self) -> None:
        """Multiple duplicate variables all produce individual diagnostics."""
        ws = _working_storage(
            _elementary("A", level=5, picture="X", line=10),
            _elementary("A", level=5, picture="X", line=11),
            _elementary("B", level=5, picture="X", line=12),
            _elementary("B", level=5, picture="X", line=13),
        )
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws)))
        assert ctx.error_count == 2

    def test_duplicate_variable_diagnostic_severity(self) -> None:
        """Duplicate variable diagnostic has ERROR severity."""
        ws = _working_storage(
            _elementary("DUP", level=5, picture="X"),
            _elementary("DUP", level=5, picture="X"),
        )
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws)))
        assert ctx.diagnostics[0].severity is SemanticSeverity.ERROR

    def test_duplicate_paragraph_diagnostic_severity(self) -> None:
        """Duplicate paragraph diagnostic has ERROR severity."""
        ctx = SemanticAnalyzer().analyse(
            _program(proc=_proc_div(_paragraph("DUP"), _paragraph("DUP")))
        )
        assert ctx.diagnostics[0].severity is SemanticSeverity.ERROR


class TestSemanticAnalyzerFullProgram:
    """End-to-end tests with all three divisions present."""

    def _full_program(self) -> ProgramNode:
        """Build a complete ProgramNode for integration testing."""
        ident = _ident_div("FULLPROG")
        ws = _working_storage(
            _group("CUST-REC", level=1, line=6),
            _elementary("CUST-ID", level=5, picture="9(5)", line=7),
            _elementary("CUST-NAME", level=5, picture="X(30)", line=8),
            _condition("END-OF-FILE", line=9),
        )
        proc = _proc_div(
            _paragraph("INIT-PARA", line=20),
            _paragraph("PROCESS-PARA", line=25),
            _paragraph("CLEANUP-PARA", line=30),
        )
        return _program(ident=ident, data=_data_div(ws=ws), proc=proc)

    def test_full_program_no_errors(self) -> None:
        """A well-formed program with all divisions produces no errors."""
        ctx = SemanticAnalyzer().analyse(self._full_program())
        assert not ctx.has_errors

    def test_full_program_symbol_counts(self) -> None:
        """All symbol kinds are correctly registered."""
        ctx = SemanticAnalyzer().analyse(self._full_program())
        table = ctx.symbol_table
        assert len(table.symbols_of_kind(SymbolKind.PROGRAM)) == 1
        assert len(table.symbols_of_kind(SymbolKind.VARIABLE)) == 4
        assert len(table.symbols_of_kind(SymbolKind.PARAGRAPH)) == 3

    def test_full_program_total_symbols(self) -> None:
        """Total symbol count equals sum across all kinds."""
        ctx = SemanticAnalyzer().analyse(self._full_program())
        total = len(ctx.symbol_table)
        assert total == 1 + 4 + 3  # program + variables + paragraphs

    def test_analyser_is_reusable(self) -> None:
        """A single SemanticAnalyzer instance produces independent contexts."""
        analyzer = SemanticAnalyzer()
        ctx1 = analyzer.analyse(_program(ident=_ident_div("PROG1")))
        ctx2 = analyzer.analyse(_program(ident=_ident_div("PROG2")))
        assert ctx1.symbol_table.lookup("PROG1") is not None
        assert ctx2.symbol_table.lookup("PROG2") is not None
        assert ctx1.symbol_table.lookup("PROG2") is None
        assert ctx2.symbol_table.lookup("PROG1") is None

    def test_mixed_errors_and_clean_symbols(self) -> None:
        """A program with one duplicate variable still registers the valid ones."""
        ws = _working_storage(
            _elementary("OK-VAR", level=5, picture="X", line=10),
            _elementary("DUP-VAR", level=5, picture="X", line=11),
            _elementary("DUP-VAR", level=5, picture="X", line=12),
        )
        ctx = SemanticAnalyzer().analyse(_program(data=_data_div(ws=ws)))
        assert ctx.error_count == 1
        assert ctx.symbol_table.lookup("OK-VAR") is not None
        assert ctx.symbol_table.lookup("DUP-VAR") is not None
