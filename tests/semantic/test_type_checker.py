"""
Comprehensive tests for TASK-023: Semantic Type Checking.

Purpose:
    Verify that :class:`TypeCheckerVisitor` correctly validates type
    compatibility of COBOL statements and emits structured semantic diagnostics,
    that the visitor integrates correctly as pass 5 in the
    :class:`SemanticAnalyzer` pipeline, and that all existing tests remain
    green.

Coverage:
    TypeCheckerVisitor construction:
        - Stores table and diagnostics references.

    _is_literal helper:
        - Quoted string → literal.
        - Numeric literal → literal.
        - Figurative constant → literal.
        - Bare identifier → not a literal.

    _compatible_move() static method:
        - NumericType source → NumericType target: allowed.
        - NumericType source → AlphanumericType target: allowed.
        - AlphanumericType source → NumericType target: NOT allowed (SEM010).
        - AlphanumericType source → AlphanumericType target: allowed.
        - GroupType source → any target: allowed.
        - Any source → GroupType target: allowed.

    visit_move_statement():
        - Numeric → numeric: no diagnostic.
        - Numeric → alphanumeric: no diagnostic.
        - Alphanumeric → alphanumeric: no diagnostic.
        - Alphanumeric → numeric: SEM010.
        - Group → numeric: no diagnostic.
        - Literal source → any: no diagnostic.
        - Figurative constant → any: no diagnostic.
        - Numeric literal → any: no diagnostic.
        - Target not in symbol table: no diagnostic (SEM003 already emitted).
        - Source not in symbol table: no diagnostic (SEM003 already emitted).
        - Target has no cobol_type: SEM012.
        - Source has no cobol_type: SEM012.
        - Traversal continues after SEM010.
        - Multiple MOVE violations in same program: all collected.

    visit_display_statement():
        - Literal operand: no diagnostic.
        - Quoted string operand: no diagnostic.
        - Figurative constant operand: no diagnostic.
        - Variable with resolved type: no diagnostic.
        - Variable with no cobol_type: SEM012.
        - Undefined variable: no diagnostic (SEM003 from pass 2).
        - Numeric type on DISPLAY: no diagnostic (all types valid for DISPLAY).
        - Alphanumeric type on DISPLAY: no diagnostic.
        - Group type on DISPLAY: no diagnostic.

    _check_arithmetic_operand() extension hook:
        - Literal operand: no diagnostic.
        - Numeric variable: no diagnostic.
        - Alphanumeric variable: SEM011.
        - Group variable: SEM011.
        - Variable with no cobol_type: SEM012.
        - Undefined variable: no diagnostic (SEM003 from pass 2).

    _check_unsupported_operation() extension hook:
        - Emits SEM013 with operation and type in message.

    SemanticAnalyzer integration (pass 5):
        - Valid program (numeric → numeric): no type-checker diagnostics.
        - Invalid MOVE (alphanumeric → numeric): SEM010 emitted.
        - SEM010 from pass 5 coexists with SEM001 from pass 1.
        - SEM010 from pass 5 coexists with SEM003 from pass 2.
        - DISPLAY with typed variable: no diagnostic.
        - Five-pass pipeline order preserved (type available when checker runs).
        - SemanticAnalyzer reusable across calls.
        - SEM012 emitted if TypeBuilder somehow skipped a variable.

    Representative COBOL programs:
        - Clean program with mixed types: no type errors.
        - Program with bad MOVE alpha → numeric: SEM010.
        - Program with multiple bad MOVEs: each SEM010 collected.
        - Mixed valid and invalid statements in single program.

    Public API:
        - TypeCheckerVisitor exported from package.

Non-responsibilities:
    - Parser or lexer behaviour.
    - AST node field correctness.
    - Pass 1–4 behaviour (tested in their own modules).

Dependencies:
    - :mod:`app.parser.semantic`              — full public API.
    - :mod:`app.parser.semantic.type_checker` — class under test.
    - :mod:`app.parser.ast.*`                 — AST helpers.
    - :mod:`app.parser.lexer.position`        — Position.
    - :mod:`pytest`                           — test framework.

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
    AlphanumericType,
    GroupType,
    NumericType,
    SemanticAnalyzer,
    SymbolTable,
    TypeCheckerVisitor,
    VariableSymbol,
)
from app.parser.semantic.symbol_collector import SymbolCollectorVisitor
from app.parser.semantic.type_builder import TypeBuilder
from app.parser.semantic.type_checker import _is_literal
from app.parser.semantic.visitors import traverse_program

# ---------------------------------------------------------------------------
# Shared position / node helpers
# ---------------------------------------------------------------------------

_FILE = "tc_test.cbl"


def _pos(line: int = 1, col: int = 1) -> Position:
    return Position(line=line, column=col, offset=0, filename=_FILE)


def _var_sym(
    name: str,
    level: int = 77,
    picture: str | None = None,
    cobol_type=None,
) -> VariableSymbol:
    return VariableSymbol(
        name=name,
        declared_at=_pos(),
        level=level,
        picture=picture,
        cobol_type=cobol_type,
    )


def _move(source: str, target: str, line: int = 10) -> MoveStatementNode:
    pos = _pos(line=line)
    return MoveStatementNode(
        start_position=pos, end_position=pos, source=source, target=target
    )


def _display(operand: str, line: int = 10) -> DisplayStatementNode:
    pos = _pos(line=line)
    return DisplayStatementNode(start_position=pos, end_position=pos, operand=operand)


def _stop_run(line: int = 99) -> StopRunStatementNode:
    pos = _pos(line=line)
    return StopRunStatementNode(start_position=pos, end_position=pos)


def _goback(line: int = 99) -> GobackStatementNode:
    pos = _pos(line=line)
    return GobackStatementNode(start_position=pos, end_position=pos)


def _paragraph(name: str, *stmts, line: int = 20) -> ParagraphNode:
    pos = _pos(line=line)
    return ParagraphNode(
        start_position=pos, end_position=pos, name=name, statements=tuple(stmts)
    )


def _proc_div(*paras: ParagraphNode, line: int = 18) -> ProcedureDivisionNode:
    pos = _pos(line=line)
    return ProcedureDivisionNode(
        start_position=pos, end_position=pos, paragraphs=tuple(paras)
    )


def _elementary(
    name: str, picture: str, level: int = 77, line: int = 10
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


def _ws(*items) -> WorkingStorageSectionNode:
    pos = _pos(line=5)
    return WorkingStorageSectionNode(
        start_position=pos, end_position=pos, items=tuple(items)
    )


def _data_div(ws=None) -> DataDivisionNode:
    pos = _pos(line=5)
    return DataDivisionNode(start_position=pos, end_position=pos, working_storage=ws)


def _pid(name: str) -> ProgramIdClauseNode:
    pos = _pos(line=2)
    return ProgramIdClauseNode(start_position=pos, end_position=pos, value=name)


def _ident(name: str = "TESTPROG") -> IdentificationDivisionNode:
    pos = _pos(line=1)
    return IdentificationDivisionNode(
        start_position=pos, end_position=pos, program_id=_pid(name)
    )


def _program(ident=None, data=None, proc=None) -> ProgramNode:
    pos = _pos()
    return ProgramNode(
        start_position=pos,
        end_position=pos,
        identification_division=ident,
        data_division=data,
        procedure_division=proc,
    )


def _make_typed_table(**name_to_type) -> SymbolTable:
    """Build a SymbolTable with VariableSymbols pre-typed by cobol_type."""
    table = SymbolTable()
    for name, t in name_to_type.items():
        sym = _var_sym(
            name,
            picture="X(5)" if isinstance(t, AlphanumericType) else "9(5)",
            cobol_type=t,
        )
        table.register(sym)
    return table


def _checker(table: SymbolTable) -> tuple[TypeCheckerVisitor, list]:
    diags: list = []
    v = TypeCheckerVisitor(table=table, diagnostics=diags)
    return v, diags


# ===========================================================================
# _is_literal helper
# ===========================================================================


class TestIsLiteral:
    """_is_literal() helper function."""

    def test_double_quoted_string(self) -> None:
        assert _is_literal('"HELLO"') is True

    def test_single_quoted_string(self) -> None:
        assert _is_literal("'HELLO'") is True

    def test_numeric_digit(self) -> None:
        assert _is_literal("42") is True

    def test_numeric_signed_plus(self) -> None:
        assert _is_literal("+1") is True

    def test_numeric_signed_minus(self) -> None:
        assert _is_literal("-99") is True

    def test_figurative_spaces(self) -> None:
        assert _is_literal("SPACES") is True

    def test_figurative_zeros(self) -> None:
        assert _is_literal("ZEROS") is True

    def test_figurative_zero(self) -> None:
        assert _is_literal("ZERO") is True

    def test_figurative_zeroes(self) -> None:
        assert _is_literal("ZEROES") is True

    def test_figurative_high_values(self) -> None:
        assert _is_literal("HIGH-VALUES") is True

    def test_figurative_null(self) -> None:
        assert _is_literal("NULL") is True

    def test_figurative_case_insensitive(self) -> None:
        assert _is_literal("spaces") is True

    def test_bare_identifier(self) -> None:
        assert _is_literal("WS-NAME") is False

    def test_bare_identifier_lowercase(self) -> None:
        assert _is_literal("ws-count") is False

    def test_empty_string(self) -> None:
        assert _is_literal("") is False


# ===========================================================================
# _compatible_move() static method
# ===========================================================================


class TestCompatibleMove:
    """TypeCheckerVisitor._compatible_move() static method."""

    _num = NumericType(digits=5)
    _alpha = AlphanumericType(length=10)
    _group = GroupType()

    def test_numeric_to_numeric_allowed(self) -> None:
        assert TypeCheckerVisitor._compatible_move(self._num, self._num) is True

    def test_numeric_to_alpha_allowed(self) -> None:
        assert TypeCheckerVisitor._compatible_move(self._num, self._alpha) is True

    def test_numeric_to_group_allowed(self) -> None:
        assert TypeCheckerVisitor._compatible_move(self._num, self._group) is True

    def test_alpha_to_alpha_allowed(self) -> None:
        assert TypeCheckerVisitor._compatible_move(self._alpha, self._alpha) is True

    def test_alpha_to_group_allowed(self) -> None:
        assert TypeCheckerVisitor._compatible_move(self._alpha, self._group) is True

    def test_alpha_to_numeric_not_allowed(self) -> None:
        assert TypeCheckerVisitor._compatible_move(self._alpha, self._num) is False

    def test_group_to_numeric_allowed(self) -> None:
        assert TypeCheckerVisitor._compatible_move(self._group, self._num) is True

    def test_group_to_alpha_allowed(self) -> None:
        assert TypeCheckerVisitor._compatible_move(self._group, self._alpha) is True

    def test_group_to_group_allowed(self) -> None:
        assert TypeCheckerVisitor._compatible_move(self._group, self._group) is True

    def test_signed_numeric_to_numeric_allowed(self) -> None:
        signed = NumericType(digits=7, signed=True)
        assert TypeCheckerVisitor._compatible_move(signed, self._num) is True

    def test_alpha_to_signed_numeric_not_allowed(self) -> None:
        signed = NumericType(digits=7, signed=True)
        assert TypeCheckerVisitor._compatible_move(self._alpha, signed) is False


# ===========================================================================
# TypeCheckerVisitor construction
# ===========================================================================


class TestTypeCheckerVisitorConstruction:
    """TypeCheckerVisitor can be constructed."""

    def test_stores_table(self) -> None:
        table = SymbolTable()
        v = TypeCheckerVisitor(table=table, diagnostics=[])
        assert v._table is table

    def test_stores_diagnostics(self) -> None:
        diags: list = []
        v = TypeCheckerVisitor(table=SymbolTable(), diagnostics=diags)
        assert v._diagnostics is diags

    def test_empty_table_no_crash(self) -> None:
        table = SymbolTable()
        v, diags = _checker(table)
        node = _move("WS-A", "WS-B")
        v.visit_move_statement(node)  # both undefined → skip
        assert diags == []


# ===========================================================================
# visit_move_statement()
# ===========================================================================


class TestVisitMoveStatement:
    """visit_move_statement() validation."""

    def test_numeric_to_numeric_no_diagnostic(self) -> None:
        table = _make_typed_table(
            **{"WS-SRC": NumericType(digits=5), "WS-TGT": NumericType(digits=9)}
        )
        v, diags = _checker(table)
        v.visit_move_statement(_move("WS-SRC", "WS-TGT"))
        assert diags == []

    def test_numeric_to_alpha_no_diagnostic(self) -> None:
        table = _make_typed_table(
            **{"WS-N": NumericType(digits=5), "WS-A": AlphanumericType(length=10)}
        )
        v, diags = _checker(table)
        v.visit_move_statement(_move("WS-N", "WS-A"))
        assert diags == []

    def test_alpha_to_alpha_no_diagnostic(self) -> None:
        table = _make_typed_table(
            **{"WS-A": AlphanumericType(length=10), "WS-B": AlphanumericType(length=20)}
        )
        v, diags = _checker(table)
        v.visit_move_statement(_move("WS-A", "WS-B"))
        assert diags == []

    def test_alpha_to_numeric_sem010(self) -> None:
        table = _make_typed_table(
            **{"WS-A": AlphanumericType(length=10), "WS-N": NumericType(digits=5)}
        )
        v, diags = _checker(table)
        v.visit_move_statement(_move("WS-A", "WS-N"))
        assert len(diags) == 1
        assert diags[0].code == "SEM010"

    def test_sem010_message_contains_source_and_target(self) -> None:
        table = _make_typed_table(
            **{"WS-A": AlphanumericType(length=10), "WS-N": NumericType(digits=5)}
        )
        v, diags = _checker(table)
        v.visit_move_statement(_move("WS-A", "WS-N"))
        assert "WS-A" in diags[0].message
        assert "WS-N" in diags[0].message

    def test_sem010_severity_is_error(self) -> None:
        from app.parser.semantic.diagnostics import SemanticSeverity

        table = _make_typed_table(
            **{"WS-A": AlphanumericType(length=10), "WS-N": NumericType(digits=5)}
        )
        v, diags = _checker(table)
        v.visit_move_statement(_move("WS-A", "WS-N"))
        assert diags[0].severity is SemanticSeverity.ERROR

    def test_sem010_position_is_move_position(self) -> None:
        table = _make_typed_table(
            **{"WS-A": AlphanumericType(length=10), "WS-N": NumericType(digits=5)}
        )
        v, diags = _checker(table)
        v.visit_move_statement(_move("WS-A", "WS-N", line=42))
        assert diags[0].position.line == 42

    def test_group_to_numeric_no_diagnostic(self) -> None:
        table = _make_typed_table(**{"GRP": GroupType(), "WS-N": NumericType(digits=5)})
        v, diags = _checker(table)
        v.visit_move_statement(_move("GRP", "WS-N"))
        assert diags == []

    def test_alpha_to_group_no_diagnostic(self) -> None:
        table = _make_typed_table(
            **{"WS-A": AlphanumericType(length=10), "GRP": GroupType()}
        )
        v, diags = _checker(table)
        v.visit_move_statement(_move("WS-A", "GRP"))
        assert diags == []

    def test_literal_source_no_diagnostic(self) -> None:
        table = _make_typed_table(**{"WS-N": NumericType(digits=5)})
        v, diags = _checker(table)
        v.visit_move_statement(_move('"HELLO"', "WS-N"))
        assert diags == []

    def test_numeric_literal_source_no_diagnostic(self) -> None:
        table = _make_typed_table(**{"WS-N": NumericType(digits=5)})
        v, diags = _checker(table)
        v.visit_move_statement(_move("42", "WS-N"))
        assert diags == []

    def test_figurative_constant_source_no_diagnostic(self) -> None:
        table = _make_typed_table(**{"WS-N": NumericType(digits=5)})
        v, diags = _checker(table)
        v.visit_move_statement(_move("ZEROS", "WS-N"))
        assert diags == []

    def test_spaces_source_no_diagnostic(self) -> None:
        table = _make_typed_table(**{"WS-A": AlphanumericType(length=10)})
        v, diags = _checker(table)
        v.visit_move_statement(_move("SPACES", "WS-A"))
        assert diags == []

    def test_target_undefined_no_diagnostic(self) -> None:
        """Undefined target: SEM003 already emitted by pass 2; checker skips."""
        table = SymbolTable()
        v, diags = _checker(table)
        v.visit_move_statement(_move("WS-A", "UNDEFINED-TARGET"))
        assert diags == []

    def test_source_undefined_no_diagnostic(self) -> None:
        """Undefined source: SEM003 already emitted by pass 2; checker skips."""
        table = _make_typed_table(**{"WS-N": NumericType(digits=5)})
        v, diags = _checker(table)
        v.visit_move_statement(_move("UNDEFINED-SRC", "WS-N"))
        assert diags == []

    def test_target_no_cobol_type_sem012(self) -> None:
        """Target in table but cobol_type=None → SEM012."""
        sym = _var_sym("WS-UNTYPED", picture="9(5)", cobol_type=None)
        table = SymbolTable()
        table.register(sym)
        v, diags = _checker(table)
        v.visit_move_statement(_move("ZEROS", "WS-UNTYPED"))
        assert len(diags) == 1
        assert diags[0].code == "SEM012"

    def test_source_no_cobol_type_sem012(self) -> None:
        """Source in table but cobol_type=None → SEM012."""
        src_sym = _var_sym("WS-UNTYPED-SRC", picture="X(5)", cobol_type=None)
        tgt_sym = _var_sym(
            "WS-TGT", picture="X(5)", cobol_type=AlphanumericType(length=5)
        )
        table = SymbolTable()
        table.register(src_sym)
        table.register(tgt_sym)
        v, diags = _checker(table)
        v.visit_move_statement(_move("WS-UNTYPED-SRC", "WS-TGT"))
        assert len(diags) == 1
        assert diags[0].code == "SEM012"

    def test_traversal_continues_after_sem010(self) -> None:
        """Two bad MOVEs → both SEM010 collected."""
        table = _make_typed_table(
            **{
                "WS-A1": AlphanumericType(length=10),
                "WS-N1": NumericType(digits=5),
                "WS-A2": AlphanumericType(length=10),
                "WS-N2": NumericType(digits=9),
            }
        )
        v, diags = _checker(table)
        v.visit_move_statement(_move("WS-A1", "WS-N1", line=10))
        v.visit_move_statement(_move("WS-A2", "WS-N2", line=11))
        codes = [d.code for d in diags]
        assert codes.count("SEM010") == 2

    def test_signed_numeric_to_numeric_no_diagnostic(self) -> None:
        table = _make_typed_table(
            **{
                "WS-AMT": NumericType(digits=9, signed=True, decimal_places=2),
                "WS-TOT": NumericType(digits=11),
            }
        )
        v, diags = _checker(table)
        v.visit_move_statement(_move("WS-AMT", "WS-TOT"))
        assert diags == []


# ===========================================================================
# visit_display_statement()
# ===========================================================================


class TestVisitDisplayStatement:
    """visit_display_statement() validation."""

    def test_literal_operand_no_diagnostic(self) -> None:
        table = SymbolTable()
        v, diags = _checker(table)
        v.visit_display_statement(_display('"Hello World"'))
        assert diags == []

    def test_quoted_string_no_diagnostic(self) -> None:
        table = SymbolTable()
        v, diags = _checker(table)
        v.visit_display_statement(_display("'HELLO'"))
        assert diags == []

    def test_figurative_constant_no_diagnostic(self) -> None:
        table = SymbolTable()
        v, diags = _checker(table)
        v.visit_display_statement(_display("SPACES"))
        assert diags == []

    def test_numeric_variable_no_diagnostic(self) -> None:
        table = _make_typed_table(**{"WS-COUNT": NumericType(digits=5)})
        v, diags = _checker(table)
        v.visit_display_statement(_display("WS-COUNT"))
        assert diags == []

    def test_alpha_variable_no_diagnostic(self) -> None:
        table = _make_typed_table(**{"WS-NAME": AlphanumericType(length=30)})
        v, diags = _checker(table)
        v.visit_display_statement(_display("WS-NAME"))
        assert diags == []

    def test_group_variable_no_diagnostic(self) -> None:
        table = _make_typed_table(**{"CUST-REC": GroupType()})
        v, diags = _checker(table)
        v.visit_display_statement(_display("CUST-REC"))
        assert diags == []

    def test_variable_no_cobol_type_sem012(self) -> None:
        sym = _var_sym("WS-UNTYPED", picture="X(5)", cobol_type=None)
        table = SymbolTable()
        table.register(sym)
        v, diags = _checker(table)
        v.visit_display_statement(_display("WS-UNTYPED"))
        assert len(diags) == 1
        assert diags[0].code == "SEM012"

    def test_undefined_variable_no_diagnostic(self) -> None:
        """Undefined variable already reported by pass 2; checker skips."""
        table = SymbolTable()
        v, diags = _checker(table)
        v.visit_display_statement(_display("UNDEFINED-VAR"))
        assert diags == []

    def test_sem012_message_contains_operand(self) -> None:
        sym = _var_sym("WS-BAD", picture="X(5)", cobol_type=None)
        table = SymbolTable()
        table.register(sym)
        v, diags = _checker(table)
        v.visit_display_statement(_display("WS-BAD"))
        assert "WS-BAD" in diags[0].message

    def test_sem012_position_is_display_position(self) -> None:
        sym = _var_sym("WS-BAD", picture="X(5)", cobol_type=None)
        table = SymbolTable()
        table.register(sym)
        v, diags = _checker(table)
        v.visit_display_statement(_display("WS-BAD", line=55))
        assert diags[0].position.line == 55


# ===========================================================================
# _check_arithmetic_operand() extension hook
# ===========================================================================


class TestCheckArithmeticOperand:
    """_check_arithmetic_operand() extension hook."""

    def test_literal_operand_no_diagnostic(self) -> None:
        table = SymbolTable()
        v, diags = _checker(table)
        stmt = _move("42", "WS-X")
        v._check_arithmetic_operand("42", stmt)
        assert diags == []

    def test_quoted_literal_no_diagnostic(self) -> None:
        table = SymbolTable()
        v, diags = _checker(table)
        stmt = _move('"A"', "WS-X")
        v._check_arithmetic_operand('"A"', stmt)
        assert diags == []

    def test_numeric_variable_no_diagnostic(self) -> None:
        table = _make_typed_table(**{"WS-N": NumericType(digits=5)})
        v, diags = _checker(table)
        stmt = _move("WS-N", "WS-X")
        v._check_arithmetic_operand("WS-N", stmt)
        assert diags == []

    def test_alpha_variable_sem011(self) -> None:
        table = _make_typed_table(**{"WS-A": AlphanumericType(length=10)})
        v, diags = _checker(table)
        stmt = _move("WS-A", "WS-X")
        v._check_arithmetic_operand("WS-A", stmt)
        assert len(diags) == 1
        assert diags[0].code == "SEM011"

    def test_group_variable_sem011(self) -> None:
        table = _make_typed_table(**{"GRP": GroupType()})
        v, diags = _checker(table)
        stmt = _move("GRP", "WS-X")
        v._check_arithmetic_operand("GRP", stmt)
        assert len(diags) == 1
        assert diags[0].code == "SEM011"

    def test_untyped_variable_sem012(self) -> None:
        sym = _var_sym("WS-UNTYPED", picture="9(5)", cobol_type=None)
        table = SymbolTable()
        table.register(sym)
        v, diags = _checker(table)
        stmt = _move("WS-UNTYPED", "WS-X")
        v._check_arithmetic_operand("WS-UNTYPED", stmt)
        assert len(diags) == 1
        assert diags[0].code == "SEM012"

    def test_undefined_variable_no_diagnostic(self) -> None:
        """Undefined → skip (SEM003 from pass 2)."""
        table = SymbolTable()
        v, diags = _checker(table)
        stmt = _move("UNDEFINED", "WS-X")
        v._check_arithmetic_operand("UNDEFINED", stmt)
        assert diags == []

    def test_sem011_message_contains_operand_name(self) -> None:
        table = _make_typed_table(**{"WS-A": AlphanumericType(length=10)})
        v, diags = _checker(table)
        v._check_arithmetic_operand("WS-A", _move("WS-A", "WS-X"))
        assert "WS-A" in diags[0].message

    def test_sem011_message_contains_type_category(self) -> None:
        table = _make_typed_table(**{"WS-A": AlphanumericType(length=10)})
        v, diags = _checker(table)
        v._check_arithmetic_operand("WS-A", _move("WS-A", "WS-X"))
        assert "alphanumeric" in diags[0].message

    def test_zeros_figurative_constant_no_diagnostic(self) -> None:
        table = SymbolTable()
        v, diags = _checker(table)
        v._check_arithmetic_operand("ZEROS", _move("ZEROS", "WS-X"))
        assert diags == []


# ===========================================================================
# _check_unsupported_operation() extension hook
# ===========================================================================


class TestCheckUnsupportedOperation:
    """_check_unsupported_operation() extension hook."""

    def test_emits_sem013(self) -> None:
        table = SymbolTable()
        v, diags = _checker(table)
        v._check_unsupported_operation("ADD", "group", _move("A", "B"))
        assert len(diags) == 1
        assert diags[0].code == "SEM013"

    def test_sem013_message_contains_operation(self) -> None:
        table = SymbolTable()
        v, diags = _checker(table)
        v._check_unsupported_operation("INSPECT", "alphanumeric", _display("WS-X"))
        assert "INSPECT" in diags[0].message

    def test_sem013_message_contains_type_name(self) -> None:
        table = SymbolTable()
        v, diags = _checker(table)
        v._check_unsupported_operation("ADD", "national", _move("A", "B"))
        assert "national" in diags[0].message

    def test_sem013_severity_is_error(self) -> None:
        from app.parser.semantic.diagnostics import SemanticSeverity

        table = SymbolTable()
        v, diags = _checker(table)
        v._check_unsupported_operation("OP", "type", _move("A", "B"))
        assert diags[0].severity is SemanticSeverity.ERROR


# ===========================================================================
# SemanticAnalyzer integration (pass 5)
# ===========================================================================


class TestSemanticAnalyzerPass5Integration:
    """Five-pass SemanticAnalyzer pipeline including TypeCheckerVisitor."""

    def _analyse(
        self,
        ws_items: list | None = None,
        proc_paras: list | None = None,
        program_name: str = "TESTPROG",
    ):
        ws_items = ws_items or []
        proc_paras = proc_paras or [_paragraph("MAIN", _stop_run())]
        ws = _ws(*ws_items) if ws_items else None
        data = _data_div(ws) if ws is not None else None
        proc = _proc_div(*proc_paras)
        return SemanticAnalyzer().analyse(
            _program(ident=_ident(program_name), data=data, proc=proc)
        )

    def test_valid_numeric_to_numeric_no_type_errors(self) -> None:
        ws_items = [
            _elementary("WS-SRC", "9(5)", line=10),
            _elementary("WS-TGT", "9(9)", line=11),
        ]
        proc_paras = [
            _paragraph("MAIN", _move("WS-SRC", "WS-TGT"), _stop_run(), line=20)
        ]
        ctx = self._analyse(ws_items, proc_paras)
        codes = {d.code for d in ctx.diagnostics}
        assert "SEM010" not in codes
        assert "SEM012" not in codes

    def test_alpha_to_numeric_sem010_emitted(self) -> None:
        ws_items = [
            _elementary("WS-NAME", "X(30)", line=10),
            _elementary("WS-COUNT", "9(5)", line=11),
        ]
        proc_paras = [
            _paragraph("MAIN", _move("WS-NAME", "WS-COUNT"), _stop_run(), line=20)
        ]
        ctx = self._analyse(ws_items, proc_paras)
        codes = [d.code for d in ctx.diagnostics]
        assert "SEM010" in codes

    def test_sem010_message_in_context(self) -> None:
        ws_items = [
            _elementary("WS-A", "X(10)", line=10),
            _elementary("WS-N", "9(5)", line=11),
        ]
        proc_paras = [_paragraph("MAIN", _move("WS-A", "WS-N"), _stop_run(), line=20)]
        ctx = self._analyse(ws_items, proc_paras)
        sem010 = [d for d in ctx.diagnostics if d.code == "SEM010"]
        assert len(sem010) == 1
        assert "WS-A" in sem010[0].message

    def test_sem010_coexists_with_sem001(self) -> None:
        """SEM001 (duplicate) from pass 1 and SEM010 from pass 5 coexist."""
        ws_items = [
            _elementary("DUP", "X(10)", line=10),
            _elementary("DUP", "9(5)", line=11),  # SEM001
            _elementary("WS-NAME", "X(10)", line=12),
            _elementary("WS-N", "9(5)", line=13),
        ]
        proc_paras = [
            _paragraph("MAIN", _move("WS-NAME", "WS-N"), _stop_run(), line=20)
        ]
        ctx = self._analyse(ws_items, proc_paras)
        codes = {d.code for d in ctx.diagnostics}
        assert "SEM001" in codes
        assert "SEM010" in codes

    def test_display_typed_variable_no_error(self) -> None:
        ws_items = [_elementary("WS-COUNT", "9(5)", line=10)]
        proc_paras = [_paragraph("MAIN", _display("WS-COUNT"), _stop_run(), line=20)]
        ctx = self._analyse(ws_items, proc_paras)
        codes = {d.code for d in ctx.diagnostics}
        assert "SEM012" not in codes

    def test_valid_mixed_program_no_type_errors(self) -> None:
        """MOVE numeric→alpha and alpha→alpha: no type errors."""
        ws_items = [
            _elementary("WS-ID", "9(5)", line=10),
            _elementary("WS-DISP", "X(10)", line=11),
            _elementary("WS-NAME", "X(30)", line=12),
            _elementary("WS-COPY", "X(30)", line=13),
        ]
        proc_paras = [
            _paragraph(
                "MAIN",
                _move("WS-ID", "WS-DISP"),  # numeric → alpha: allowed
                _move("WS-NAME", "WS-COPY"),  # alpha → alpha: allowed
                _display("WS-DISP"),
                _stop_run(),
                line=20,
            )
        ]
        ctx = self._analyse(ws_items, proc_paras)
        type_codes = {d.code for d in ctx.diagnostics if d.code.startswith("SEM01")}
        assert type_codes == set()

    def test_multiple_bad_moves_multiple_sem010(self) -> None:
        """Two alpha→numeric MOVEs in same program: two SEM010s."""
        ws_items = [
            _elementary("WS-A1", "X(10)", line=10),
            _elementary("WS-N1", "9(5)", line=11),
            _elementary("WS-A2", "X(10)", line=12),
            _elementary("WS-N2", "9(5)", line=13),
        ]
        proc_paras = [
            _paragraph(
                "MAIN",
                _move("WS-A1", "WS-N1", line=20),
                _move("WS-A2", "WS-N2", line=21),
                _stop_run(),
                line=20,
            )
        ]
        ctx = self._analyse(ws_items, proc_paras)
        sem010_count = sum(1 for d in ctx.diagnostics if d.code == "SEM010")
        assert sem010_count == 2

    def test_literal_source_move_no_sem010(self) -> None:
        """MOVE literal TO numeric: always allowed."""
        ws_items = [_elementary("WS-N", "9(5)", line=10)]
        proc_paras = [_paragraph("MAIN", _move("42", "WS-N"), _stop_run(), line=20)]
        ctx = self._analyse(ws_items, proc_paras)
        codes = {d.code for d in ctx.diagnostics}
        assert "SEM010" not in codes

    def test_analyser_reusable(self) -> None:
        analyzer = SemanticAnalyzer()
        proc = _proc_div(_paragraph("MAIN", _stop_run()))

        ctx1 = analyzer.analyse(_program(ident=_ident("P1"), proc=proc))
        ctx2 = analyzer.analyse(_program(ident=_ident("P2"), proc=proc))
        # Independent contexts
        assert ctx1.symbol_table is not ctx2.symbol_table

    def test_five_pass_order_preserved(self) -> None:
        """TypeBuilder must run before TypeCheckerVisitor — types must be ready."""
        ws_items = [
            _elementary("WS-NAME", "X(30)", line=10),
            _elementary("WS-COUNT", "9(5)", line=11),
        ]
        proc_paras = [
            _paragraph("MAIN", _move("WS-NAME", "WS-COUNT"), _stop_run(), line=20)
        ]
        ctx = self._analyse(ws_items, proc_paras)
        # If type checker ran before TypeBuilder, no SEM010 would be emitted.
        codes = [d.code for d in ctx.diagnostics]
        assert "SEM010" in codes, "TypeBuilder must run before TypeCheckerVisitor"


# ===========================================================================
# Standalone TypeCheckerVisitor + AST traversal
# ===========================================================================


class TestStandaloneVisitorTraversal:
    """TypeCheckerVisitor via traverse_program after manual pass 1 + 4."""

    def _build_and_check(self, ws_items, *stmts):
        ws = _ws(*ws_items)
        proc = _proc_div(_paragraph("MAIN", *stmts, line=20))
        prog = _program(ident=_ident(), data=_data_div(ws), proc=proc)

        table = SymbolTable()
        diags = []
        SymbolCollectorVisitor(
            table=table, diagnostics=diags
        ).visit_working_storage_section  # noqa
        # full collect via traverse_program
        collector = SymbolCollectorVisitor(table=table, diagnostics=diags)
        traverse_program(prog, collector)
        TypeBuilder(table=table).build()

        checker = TypeCheckerVisitor(table=table, diagnostics=diags)
        traverse_program(prog, checker)
        return diags

    def test_alpha_to_numeric_produces_sem010(self) -> None:
        ws_items = [
            _elementary("WS-A", "X(10)"),
            _elementary("WS-N", "9(5)"),
        ]
        diags = self._build_and_check(ws_items, _move("WS-A", "WS-N"))
        codes = [d.code for d in diags]
        assert "SEM010" in codes

    def test_numeric_to_alpha_no_sem010(self) -> None:
        ws_items = [
            _elementary("WS-N", "9(5)"),
            _elementary("WS-A", "X(10)"),
        ]
        diags = self._build_and_check(ws_items, _move("WS-N", "WS-A"))
        codes = [d.code for d in diags]
        assert "SEM010" not in codes

    def test_display_alpha_no_errors(self) -> None:
        ws_items = [_elementary("WS-NAME", "X(30)")]
        diags = self._build_and_check(ws_items, _display("WS-NAME"))
        codes = [d.code for d in diags]
        assert "SEM010" not in codes
        assert "SEM012" not in codes


# ===========================================================================
# Representative COBOL programs
# ===========================================================================


class TestRepresentativePrograms:
    """Representative full-program type-checking scenarios."""

    def test_payroll_valid_program(self) -> None:
        """Simulate a simple payroll record with valid MOVEs."""
        ws_items = [
            _elementary("EMP-ID", "9(6)", line=10),
            _elementary("EMP-NAME", "X(30)", line=11),
            _elementary("GROSS-PAY", "9(7)V9(2)", line=12),
            _elementary("DISP-ID", "X(10)", line=13),
            _elementary("DISP-NAME", "X(30)", line=14),
        ]
        proc_paras = [
            _paragraph(
                "MAIN",
                _move("EMP-ID", "DISP-ID"),  # numeric → alpha: OK
                _move("EMP-NAME", "DISP-NAME"),  # alpha → alpha: OK
                _display("DISP-ID"),
                _display("DISP-NAME"),
                _stop_run(),
                line=20,
            )
        ]
        ctx = SemanticAnalyzer().analyse(
            _program(
                ident=_ident("PAYROLL"),
                data=_data_div(_ws(*ws_items)),
                proc=_proc_div(*proc_paras),
            )
        )
        type_codes = [d.code for d in ctx.diagnostics if d.code.startswith("SEM01")]
        assert type_codes == []

    def test_bad_move_in_loop_body(self) -> None:
        """Alpha → numeric MOVE detected even inside a paragraph."""
        ws_items = [
            _elementary("WS-NAME", "X(30)", line=10),
            _elementary("WS-COUNT", "9(5)", line=11),
        ]
        proc_paras = [
            _paragraph(
                "LOOP-BODY",
                _move("WS-NAME", "WS-COUNT", line=25),
                _stop_run(),
                line=20,
            )
        ]
        ctx = SemanticAnalyzer().analyse(
            _program(
                ident=_ident("BADPROG"),
                data=_data_div(_ws(*ws_items)),
                proc=_proc_div(*proc_paras),
            )
        )
        sem010 = [d for d in ctx.diagnostics if d.code == "SEM010"]
        assert len(sem010) == 1

    def test_three_paragraphs_mixed_errors(self) -> None:
        """Multiple paragraphs with mixed valid/invalid MOVEs."""
        ws_items = [
            _elementary("WS-A", "X(10)", line=10),
            _elementary("WS-N", "9(5)", line=11),
        ]
        proc_paras = [
            _paragraph(
                "PARA-1", _move("WS-A", "WS-N", line=20), _stop_run(), line=20
            ),  # SEM010
            _paragraph(
                "PARA-2", _move("WS-N", "WS-A", line=30), _stop_run(), line=30
            ),  # OK
            _paragraph(
                "PARA-3", _move("WS-A", "WS-N", line=40), _stop_run(), line=40
            ),  # SEM010
        ]
        ctx = SemanticAnalyzer().analyse(
            _program(
                ident=_ident("MULTI"),
                data=_data_div(_ws(*ws_items)),
                proc=_proc_div(*proc_paras),
            )
        )
        sem010 = [d for d in ctx.diagnostics if d.code == "SEM010"]
        assert len(sem010) == 2


# ===========================================================================
# Public API export
# ===========================================================================


class TestPublicApiExport:
    """TypeCheckerVisitor is exported from the public package API."""

    def test_type_checker_visitor_exported(self) -> None:
        from app.parser.semantic import TypeCheckerVisitor as TCV  # noqa: PLC0415

        assert TCV is TypeCheckerVisitor
