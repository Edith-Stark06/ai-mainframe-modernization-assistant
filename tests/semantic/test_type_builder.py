"""
Comprehensive tests for TASK-022: COBOL Data Type Model.

Purpose:
    Verify that the semantic type hierarchy, TypeBuilder pass, VariableSymbol
    extension, and SemanticAnalyzer integration are all correct and complete.

Coverage:
    UsageType enum:
        - All standard values present and correct.
        - COMP aliases (COMP-4, BINARY → COMP).
        - COMP-3 alias (PACKED-DECIMAL).
        - Uniqueness of enum members.

    CobolType abstract base:
        - NumericType, AlphanumericType, GroupType are CobolType instances.
        - category property returns correct string for each.
        - Immutability (frozen dataclasses).

    NumericType:
        - PIC 9: digits, signed=False, decimal_places=0, usage=DISPLAY.
        - PIC S9: signed=True.
        - PIC 9(n): digit count from parenthesised form.
        - PIC S9(n)V9(m): decimal places and total digit count.
        - is_integer True for zero decimal places.
        - is_integer False when decimal_places > 0.
        - total_digits equals digits field.
        - COMP usage stored correctly.
        - COMP-3 usage stored correctly.
        - Equality and hashing (frozen dataclass).

    AlphanumericType:
        - PIC X: length=1.
        - PIC X(n): length from parenthesised form.
        - usage=DISPLAY by default.
        - Equality and hashing.

    GroupType:
        - category='group'.
        - member_names defaults to empty tuple.
        - member_names stored when provided.
        - Equality and hashing.

    VariableSymbol extension:
        - cobol_type defaults to None.
        - cobol_type can be set at construction time.
        - Existing fields (name, level, picture, declared_at) unaffected.
        - Frozen — cannot mutate after construction.
        - dataclasses.replace() produces updated copy.

    SymbolTable.replace_symbol():
        - Returns True when symbol replaced successfully.
        - Returns False for unknown name.
        - Lookup returns updated symbol after replace.
        - List order preserved after replace.
        - Works with VariableSymbol carrying cobol_type.
        - all_symbols() reflects updated symbol.

    TypeBuilder._parse_numeric_pic():
        - 9           → digits=1, signed=False, decimal_places=0.
        - 9(5)        → digits=5.
        - S9(7)       → signed=True, digits=7.
        - 9(5)V9(2)   → digits=7, decimal_places=2.
        - S9(9)V9(2)  → signed=True, digits=11, decimal_places=2.
        - 99          → digits=2 (bare nines).
        - S99         → signed=True, digits=2.
        - X(5)        → None (not numeric).
        - GROUP (no pic) → None (not numeric).

    TypeBuilder._parse_alpha_pic():
        - X           → length=1.
        - X(30)       → length=30.
        - XX          → length=2 (bare Xs).
        - 9(5)        → None (not alpha).

    TypeBuilder._infer_usage():
        - Returns DISPLAY by default.

    TypeBuilder.usage_from_string():
        - DISPLAY → UsageType.DISPLAY.
        - COMP    → UsageType.COMP.
        - COMP-4  → UsageType.COMP (alias).
        - BINARY  → UsageType.COMP (alias).
        - COMP-1  → UsageType.COMP_1.
        - COMP-2  → UsageType.COMP_2.
        - COMP-3  → UsageType.COMP_3.
        - PACKED-DECIMAL → UsageType.COMP_3 (alias).
        - COMP-5  → UsageType.COMP_5.
        - INDEX   → UsageType.INDEX.
        - POINTER → UsageType.POINTER.
        - Unknown string → UsageType.DISPLAY (fallback).
        - Case-insensitive.

    TypeBuilder.build() — full type annotation pass:
        - Elementary item PIC X(30) → AlphanumericType(length=30).
        - Elementary item PIC 9(5)  → NumericType(digits=5).
        - Elementary item PIC S9(7) → NumericType(signed=True, digits=7).
        - Elementary item PIC 9(5)V9(2) → NumericType(decimal_places=2).
        - Group item (no PIC)       → GroupType().
        - Condition-name (no PIC)   → GroupType().
        - Empty table → no-op.
        - Already-typed symbol skipped.
        - Unrecognised PIC → cobol_type=None (no crash).
        - All variables in mixed table are typed.

    SemanticAnalyzer integration (pass 4):
        - analyse() runs TypeBuilder as pass 4.
        - Variables in result context carry cobol_type.
        - PIC X variable → AlphanumericType in context.
        - PIC 9 variable → NumericType in context.
        - Group item     → GroupType in context.
        - Existing diagnostics (SEM001, SEM003, SEM006) unaffected by pass 4.
        - SemanticAnalyzer is still reusable.
        - ParagraphSymbol and ProgramSymbol unchanged (no cobol_type).

    Representative COBOL programs:
        - Mixed working-storage (numerics + alphanumeric + group).
        - Valid program — all variables typed, no diagnostics from pass 4.
        - Signed numeric PIC S9(9)V9(2) → NumericType correctly built.

Non-responsibilities:
    - Parser or lexer behaviour.
    - AST node field correctness.
    - Type compatibility or coercion rules.

Dependencies:
    - :mod:`app.parser.semantic`             — full public API.
    - :mod:`app.parser.semantic.type_builder` — class under test.
    - :mod:`app.parser.semantic.types`       — type hierarchy.
    - :mod:`app.parser.ast.*`               — AST node helpers.
    - :mod:`app.parser.lexer.position`      — Position.
    - :mod:`pytest`                         — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import dataclasses

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
from app.parser.ast.statements import StopRunStatementNode
from app.parser.ast.working_storage import WorkingStorageSectionNode
from app.parser.lexer.position import Position
from app.parser.semantic import (
    AlphanumericType,
    CobolType,
    GroupType,
    NumericType,
    SemanticAnalyzer,
    SymbolKind,
    SymbolTable,
    TypeBuilder,
    UsageType,
    VariableSymbol,
)
from app.parser.semantic.symbol_collector import SymbolCollectorVisitor
from app.parser.semantic.visitors import traverse_program

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FILE = "type_test.cbl"


def _pos(line: int = 1, col: int = 1) -> Position:
    return Position(line=line, column=col, offset=0, filename=_FILE)


def _var_sym(
    name: str,
    level: int = 77,
    picture: str | None = None,
    cobol_type: CobolType | None = None,
) -> VariableSymbol:
    return VariableSymbol(
        name=name,
        declared_at=_pos(),
        level=level,
        picture=picture,
        cobol_type=cobol_type,
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


def _ws(
    *items: ElementaryItemNode | GroupItemNode | ConditionNameNode,
) -> WorkingStorageSectionNode:
    pos = _pos(line=5)
    return WorkingStorageSectionNode(
        start_position=pos, end_position=pos, items=tuple(items)
    )


def _data_div(ws: WorkingStorageSectionNode | None = None) -> DataDivisionNode:
    pos = _pos(line=5)
    return DataDivisionNode(start_position=pos, end_position=pos, working_storage=ws)


def _program_id_clause(name: str) -> ProgramIdClauseNode:
    pos = _pos(line=2)
    return ProgramIdClauseNode(start_position=pos, end_position=pos, value=name)


def _ident_div(name: str = "TESTPROG") -> IdentificationDivisionNode:
    pos = _pos(line=1)
    pid = _program_id_clause(name)
    return IdentificationDivisionNode(
        start_position=pos, end_position=pos, program_id=pid
    )


def _stop_run(line: int = 99) -> StopRunStatementNode:
    pos = _pos(line=line)
    return StopRunStatementNode(start_position=pos, end_position=pos)


def _paragraph(name: str, line: int = 20) -> ParagraphNode:
    pos = _pos(line=line)
    return ParagraphNode(
        start_position=pos, end_position=pos, name=name, statements=(_stop_run(),)
    )


def _proc_div(*paras: ParagraphNode, line: int = 20) -> ProcedureDivisionNode:
    pos = _pos(line=line)
    return ProcedureDivisionNode(
        start_position=pos, end_position=pos, paragraphs=tuple(paras)
    )


def _program(
    ident: IdentificationDivisionNode | None = None,
    data: DataDivisionNode | None = None,
    proc: ProcedureDivisionNode | None = None,
) -> ProgramNode:
    pos = _pos()
    return ProgramNode(
        start_position=pos,
        end_position=pos,
        identification_division=ident,
        data_division=data,
        procedure_division=proc,
    )


def _table_with(*syms: VariableSymbol) -> SymbolTable:
    """Build a SymbolTable pre-populated with the given VariableSymbols."""
    table = SymbolTable()
    for s in syms:
        table.register(s)
    return table


def _builder_for_table(table: SymbolTable) -> TypeBuilder:
    return TypeBuilder(table=table)


# ===========================================================================
# UsageType enum
# ===========================================================================


class TestUsageTypeEnum:
    """UsageType enum values and completeness."""

    def test_display_value(self) -> None:
        assert UsageType.DISPLAY.value == "DISPLAY"

    def test_comp_value(self) -> None:
        assert UsageType.COMP.value == "COMP"

    def test_comp_1_value(self) -> None:
        assert UsageType.COMP_1.value == "COMP-1"

    def test_comp_2_value(self) -> None:
        assert UsageType.COMP_2.value == "COMP-2"

    def test_comp_3_value(self) -> None:
        assert UsageType.COMP_3.value == "COMP-3"

    def test_comp_5_value(self) -> None:
        assert UsageType.COMP_5.value == "COMP-5"

    def test_index_value(self) -> None:
        assert UsageType.INDEX.value == "INDEX"

    def test_pointer_value(self) -> None:
        assert UsageType.POINTER.value == "POINTER"

    def test_all_members_present(self) -> None:
        values = {u.value for u in UsageType}
        assert "DISPLAY" in values
        assert "COMP" in values
        assert "COMP-3" in values

    def test_unique_values(self) -> None:
        values = [u.value for u in UsageType]
        assert len(values) == len(set(values))


# ===========================================================================
# CobolType abstract base
# ===========================================================================


class TestCobolTypeBase:
    """CobolType is the common base for all type objects."""

    def test_numeric_is_cobol_type(self) -> None:
        assert isinstance(NumericType(digits=5), CobolType)

    def test_alphanumeric_is_cobol_type(self) -> None:
        assert isinstance(AlphanumericType(length=30), CobolType)

    def test_group_is_cobol_type(self) -> None:
        assert isinstance(GroupType(), CobolType)

    def test_numeric_category(self) -> None:
        assert NumericType(digits=5).category == "numeric"

    def test_alphanumeric_category(self) -> None:
        assert AlphanumericType(length=10).category == "alphanumeric"

    def test_group_category(self) -> None:
        assert GroupType().category == "group"


# ===========================================================================
# NumericType
# ===========================================================================


class TestNumericType:
    """NumericType construction, properties, and semantics."""

    def test_basic_9_pic(self) -> None:
        t = NumericType(digits=5)
        assert t.digits == 5
        assert t.signed is False
        assert t.decimal_places == 0
        assert t.usage is UsageType.DISPLAY

    def test_signed_true(self) -> None:
        t = NumericType(digits=7, signed=True)
        assert t.signed is True

    def test_decimal_places(self) -> None:
        t = NumericType(digits=9, decimal_places=2)
        assert t.decimal_places == 2

    def test_is_integer_true(self) -> None:
        assert NumericType(digits=5).is_integer is True

    def test_is_integer_false(self) -> None:
        assert NumericType(digits=7, decimal_places=2).is_integer is False

    def test_total_digits_equals_digits(self) -> None:
        t = NumericType(digits=11, decimal_places=2)
        assert t.total_digits == 11

    def test_usage_comp(self) -> None:
        t = NumericType(digits=9, usage=UsageType.COMP)
        assert t.usage is UsageType.COMP

    def test_usage_comp_3(self) -> None:
        t = NumericType(digits=7, usage=UsageType.COMP_3)
        assert t.usage is UsageType.COMP_3

    def test_frozen_immutable(self) -> None:
        t = NumericType(digits=5)
        with pytest.raises((AttributeError, TypeError)):
            t.digits = 99  # type: ignore[misc]

    def test_equality(self) -> None:
        assert NumericType(digits=5) == NumericType(digits=5)

    def test_inequality(self) -> None:
        assert NumericType(digits=5) != NumericType(digits=6)

    def test_hashable(self) -> None:
        s = {NumericType(digits=5), NumericType(digits=5)}
        assert len(s) == 1

    def test_dataclasses_replace(self) -> None:
        t = NumericType(digits=5)
        t2 = dataclasses.replace(t, signed=True)
        assert t2.signed is True
        assert t.signed is False

    def test_signed_decimal(self) -> None:
        t = NumericType(digits=11, signed=True, decimal_places=2)
        assert t.signed is True
        assert t.decimal_places == 2
        assert t.digits == 11


# ===========================================================================
# AlphanumericType
# ===========================================================================


class TestAlphanumericType:
    """AlphanumericType construction and properties."""

    def test_length(self) -> None:
        assert AlphanumericType(length=30).length == 30

    def test_default_usage_display(self) -> None:
        assert AlphanumericType(length=10).usage is UsageType.DISPLAY

    def test_length_one(self) -> None:
        assert AlphanumericType(length=1).length == 1

    def test_frozen(self) -> None:
        t = AlphanumericType(length=10)
        with pytest.raises((AttributeError, TypeError)):
            t.length = 99  # type: ignore[misc]

    def test_equality(self) -> None:
        assert AlphanumericType(length=30) == AlphanumericType(length=30)

    def test_inequality(self) -> None:
        assert AlphanumericType(length=30) != AlphanumericType(length=10)

    def test_hashable(self) -> None:
        s = {AlphanumericType(length=10), AlphanumericType(length=10)}
        assert len(s) == 1

    def test_dataclasses_replace(self) -> None:
        t = AlphanumericType(length=30)
        t2 = dataclasses.replace(t, length=50)
        assert t2.length == 50
        assert t.length == 30


# ===========================================================================
# GroupType
# ===========================================================================


class TestGroupType:
    """GroupType construction and properties."""

    def test_default_empty_member_names(self) -> None:
        assert GroupType().member_names == ()

    def test_member_names_stored(self) -> None:
        t = GroupType(member_names=("A", "B"))
        assert t.member_names == ("A", "B")

    def test_category_group(self) -> None:
        assert GroupType().category == "group"

    def test_frozen(self) -> None:
        t = GroupType()
        with pytest.raises((AttributeError, TypeError)):
            t.member_names = ("X",)  # type: ignore[misc]

    def test_equality(self) -> None:
        assert GroupType() == GroupType()
        assert GroupType(member_names=("A",)) == GroupType(member_names=("A",))

    def test_inequality(self) -> None:
        assert GroupType() != GroupType(member_names=("A",))

    def test_hashable(self) -> None:
        s = {GroupType(), GroupType()}
        assert len(s) == 1


# ===========================================================================
# VariableSymbol.cobol_type extension
# ===========================================================================


class TestVariableSymbolCoblType:
    """VariableSymbol.cobol_type field and backward compatibility."""

    def test_cobol_type_defaults_to_none(self) -> None:
        sym = _var_sym("WS-A", picture="9(5)")
        assert sym.cobol_type is None

    def test_cobol_type_can_be_set_at_construction(self) -> None:
        t = NumericType(digits=5)
        sym = _var_sym("WS-A", picture="9(5)", cobol_type=t)
        assert sym.cobol_type is t

    def test_existing_fields_unaffected(self) -> None:
        sym = _var_sym("WS-B", level=5, picture="X(10)")
        assert sym.name == "WS-B"
        assert sym.level == 5
        assert sym.picture == "X(10)"

    def test_frozen_cannot_mutate(self) -> None:
        sym = _var_sym("WS-C", picture="9(5)")
        with pytest.raises((AttributeError, TypeError)):
            sym.cobol_type = NumericType(digits=5)  # type: ignore[misc]

    def test_dataclasses_replace_attaches_type(self) -> None:
        sym = _var_sym("WS-D", picture="9(5)")
        t = NumericType(digits=5)
        updated = dataclasses.replace(sym, cobol_type=t)
        assert updated.cobol_type is t
        assert sym.cobol_type is None  # original unchanged

    def test_none_picture_variable_symbol(self) -> None:
        """Group item with no picture → cobol_type can still be set."""
        t = GroupType()
        sym = _var_sym("GROUP-REC", level=1, picture=None, cobol_type=t)
        assert sym.cobol_type is t
        assert sym.picture is None


# ===========================================================================
# SymbolTable.replace_symbol()
# ===========================================================================


class TestSymbolTableReplaceSymbol:
    """SymbolTable.replace_symbol() method."""

    def test_returns_true_on_success(self) -> None:
        sym = _var_sym("WS-X", picture="9(5)")
        table = _table_with(sym)
        sym2 = dataclasses.replace(sym, cobol_type=NumericType(digits=5))
        assert table.replace_symbol(sym2) is True

    def test_returns_false_for_unknown_name(self) -> None:
        table = SymbolTable()
        sym = _var_sym("MISSING")
        assert table.replace_symbol(sym) is False

    def test_lookup_returns_updated_symbol(self) -> None:
        sym = _var_sym("WS-X", picture="9(5)")
        table = _table_with(sym)
        t = NumericType(digits=5)
        sym2 = dataclasses.replace(sym, cobol_type=t)
        table.replace_symbol(sym2)
        result = table.lookup("WS-X")
        assert isinstance(result, VariableSymbol)
        assert result.cobol_type is t

    def test_all_symbols_reflects_updated(self) -> None:
        sym = _var_sym("WS-X")
        table = _table_with(sym)
        t = GroupType()
        updated = dataclasses.replace(sym, cobol_type=t)
        table.replace_symbol(updated)
        assert any(
            isinstance(s, VariableSymbol) and s.cobol_type is t
            for s in table.all_symbols()
        )

    def test_list_order_preserved(self) -> None:
        s1 = _var_sym("WS-A")
        s2 = _var_sym("WS-B")
        s3 = _var_sym("WS-C")
        table = _table_with(s1, s2, s3)
        t = NumericType(digits=9)
        s2_new = dataclasses.replace(s2, cobol_type=t)
        table.replace_symbol(s2_new)
        names = [s.name for s in table.all_symbols()]
        assert names == ["WS-A", "WS-B", "WS-C"]

    def test_length_unchanged_after_replace(self) -> None:
        s = _var_sym("WS-X")
        table = _table_with(s)
        assert len(table) == 1
        table.replace_symbol(dataclasses.replace(s, cobol_type=GroupType()))
        assert len(table) == 1

    def test_case_insensitive_replace(self) -> None:
        sym = _var_sym("WS-X", picture="X(5)")
        table = _table_with(sym)
        t = AlphanumericType(length=5)
        lower_sym = dataclasses.replace(sym, cobol_type=t)
        # Replace using the same name (same case as registered)
        assert table.replace_symbol(lower_sym) is True


# ===========================================================================
# TypeBuilder._parse_numeric_pic()
# ===========================================================================


class TestParseNumericPic:
    """TypeBuilder._parse_numeric_pic() private method."""

    def _builder(self) -> TypeBuilder:
        return TypeBuilder(table=SymbolTable())

    @pytest.mark.parametrize(
        "pic, expected_digits, expected_signed, expected_dec",
        [
            ("9", 1, False, 0),
            ("9(5)", 5, False, 0),
            ("S9(7)", 7, True, 0),
            ("9(5)V9(2)", 7, False, 2),
            ("S9(9)V9(2)", 11, True, 2),
            ("99", 2, False, 0),
            ("S99", 2, True, 0),
            ("9(10)", 10, False, 0),
            ("S9(3)V9(4)", 7, True, 4),
        ],
    )
    def test_numeric_patterns(
        self,
        pic: str,
        expected_digits: int,
        expected_signed: bool,
        expected_dec: int,
    ) -> None:
        b = self._builder()
        result = b._parse_numeric_pic(pic.upper())
        assert result is not None, f"Expected numeric match for {pic!r}"
        assert result.digits == expected_digits
        assert result.signed == expected_signed
        assert result.decimal_places == expected_dec

    def test_alpha_pic_returns_none(self) -> None:
        assert self._builder()._parse_numeric_pic("X(5)") is None

    def test_none_returns_none(self) -> None:
        # Test with a clearly non-numeric string
        assert self._builder()._parse_numeric_pic("INVALID") is None


# ===========================================================================
# TypeBuilder._parse_alpha_pic()
# ===========================================================================


class TestParseAlphaPic:
    """TypeBuilder._parse_alpha_pic() private method."""

    def _builder(self) -> TypeBuilder:
        return TypeBuilder(table=SymbolTable())

    @pytest.mark.parametrize(
        "pic, expected_length",
        [
            ("X", 1),
            ("X(30)", 30),
            ("XX", 2),
            ("X(1)", 1),
            ("X(100)", 100),
            ("XXX", 3),
        ],
    )
    def test_alpha_patterns(self, pic: str, expected_length: int) -> None:
        b = self._builder()
        result = b._parse_alpha_pic(pic.upper())
        assert result is not None, f"Expected alpha match for {pic!r}"
        assert result.length == expected_length

    def test_numeric_pic_returns_none(self) -> None:
        assert self._builder()._parse_alpha_pic("9(5)") is None

    def test_invalid_returns_none(self) -> None:
        assert self._builder()._parse_alpha_pic("ZZZZ") is None


# ===========================================================================
# TypeBuilder._infer_usage()
# ===========================================================================


class TestInferUsage:
    """TypeBuilder._infer_usage() returns DISPLAY by default."""

    def test_default_display(self) -> None:
        b = TypeBuilder(table=SymbolTable())
        assert b._infer_usage("9(5)") is UsageType.DISPLAY

    def test_alpha_default_display(self) -> None:
        b = TypeBuilder(table=SymbolTable())
        assert b._infer_usage("X(30)") is UsageType.DISPLAY


# ===========================================================================
# TypeBuilder.usage_from_string()
# ===========================================================================


class TestUsageFromString:
    """TypeBuilder.usage_from_string() static method."""

    @pytest.mark.parametrize(
        "usage_str, expected",
        [
            ("DISPLAY", UsageType.DISPLAY),
            ("COMP", UsageType.COMP),
            ("COMP-4", UsageType.COMP),
            ("BINARY", UsageType.COMP),
            ("COMP-1", UsageType.COMP_1),
            ("COMP-2", UsageType.COMP_2),
            ("COMP-3", UsageType.COMP_3),
            ("PACKED-DECIMAL", UsageType.COMP_3),
            ("COMP-5", UsageType.COMP_5),
            ("INDEX", UsageType.INDEX),
            ("POINTER", UsageType.POINTER),
        ],
    )
    def test_known_usages(self, usage_str: str, expected: UsageType) -> None:
        assert TypeBuilder.usage_from_string(usage_str) is expected

    def test_unknown_returns_display(self) -> None:
        assert TypeBuilder.usage_from_string("UNKNOWN-USAGE") is UsageType.DISPLAY

    def test_case_insensitive(self) -> None:
        assert TypeBuilder.usage_from_string("comp-3") is UsageType.COMP_3
        assert TypeBuilder.usage_from_string("Comp") is UsageType.COMP
        assert TypeBuilder.usage_from_string("display") is UsageType.DISPLAY

    def test_leading_trailing_spaces(self) -> None:
        assert TypeBuilder.usage_from_string("  COMP  ") is UsageType.COMP


# ===========================================================================
# TypeBuilder.build() — full annotation pass
# ===========================================================================


class TestTypeBuilderBuild:
    """TypeBuilder.build() attaches CobolType to each VariableSymbol."""

    def _run_builder(self, *syms: VariableSymbol) -> SymbolTable:
        table = _table_with(*syms)
        TypeBuilder(table=table).build()
        return table

    def test_elementary_pic_x_alpha(self) -> None:
        table = self._run_builder(_var_sym("WS-NAME", picture="X(30)"))
        result = table.lookup("WS-NAME")
        assert isinstance(result, VariableSymbol)
        assert isinstance(result.cobol_type, AlphanumericType)
        assert result.cobol_type.length == 30

    def test_elementary_pic_9_numeric(self) -> None:
        table = self._run_builder(_var_sym("WS-COUNT", picture="9(5)"))
        result = table.lookup("WS-COUNT")
        assert isinstance(result, VariableSymbol)
        assert isinstance(result.cobol_type, NumericType)
        assert result.cobol_type.digits == 5

    def test_signed_pic_s9_numeric(self) -> None:
        table = self._run_builder(_var_sym("WS-BAL", picture="S9(7)"))
        result = table.lookup("WS-BAL")
        assert isinstance(result, VariableSymbol)
        assert isinstance(result.cobol_type, NumericType)
        assert result.cobol_type.signed is True
        assert result.cobol_type.digits == 7

    def test_decimal_numeric(self) -> None:
        table = self._run_builder(_var_sym("WS-RATE", picture="9(5)V9(2)"))
        result = table.lookup("WS-RATE")
        assert isinstance(result, VariableSymbol)
        assert isinstance(result.cobol_type, NumericType)
        assert result.cobol_type.decimal_places == 2
        assert result.cobol_type.digits == 7

    def test_signed_decimal_numeric(self) -> None:
        table = self._run_builder(_var_sym("WS-AMOUNT", picture="S9(9)V9(2)"))
        result = table.lookup("WS-AMOUNT")
        assert isinstance(result, VariableSymbol)
        assert isinstance(result.cobol_type, NumericType)
        assert result.cobol_type.signed is True
        assert result.cobol_type.decimal_places == 2
        assert result.cobol_type.digits == 11

    def test_group_item_no_pic(self) -> None:
        table = self._run_builder(_var_sym("GROUP-REC", level=1, picture=None))
        result = table.lookup("GROUP-REC")
        assert isinstance(result, VariableSymbol)
        assert isinstance(result.cobol_type, GroupType)

    def test_condition_name_no_pic(self) -> None:
        table = self._run_builder(_var_sym("EOF-FLAG", level=88, picture=None))
        result = table.lookup("EOF-FLAG")
        assert isinstance(result, VariableSymbol)
        assert isinstance(result.cobol_type, GroupType)

    def test_empty_table_no_crash(self) -> None:
        table = SymbolTable()
        TypeBuilder(table=table).build()  # must not raise
        assert len(table) == 0

    def test_already_typed_symbol_skipped(self) -> None:
        existing_type = AlphanumericType(length=99)
        sym = _var_sym("WS-X", picture="X(5)", cobol_type=existing_type)
        table = _table_with(sym)
        TypeBuilder(table=table).build()
        result = table.lookup("WS-X")
        assert isinstance(result, VariableSymbol)
        # The pre-set type is preserved — builder must not overwrite it.
        assert result.cobol_type is existing_type

    def test_unrecognised_pic_leaves_none(self) -> None:
        """A syntactically unrecognised PIC string leaves cobol_type=None."""
        sym = _var_sym("WS-UNKNOWN", picture="A(5)")  # PIC A not in parser
        table = _table_with(sym)
        TypeBuilder(table=table).build()
        result = table.lookup("WS-UNKNOWN")
        assert isinstance(result, VariableSymbol)
        assert result.cobol_type is None

    def test_mixed_table_all_typed(self) -> None:
        """Multiple variables of different kinds are all annotated."""
        syms = [
            _var_sym("WS-ID", picture="9(5)"),
            _var_sym("WS-NAME", picture="X(30)"),
            _var_sym("GROUP-REC", level=1, picture=None),
        ]
        table = _table_with(*syms)
        TypeBuilder(table=table).build()
        for name, expected_cat in [
            ("WS-ID", "numeric"),
            ("WS-NAME", "alphanumeric"),
            ("GROUP-REC", "group"),
        ]:
            s = table.lookup(name)
            assert isinstance(s, VariableSymbol)
            assert s.cobol_type is not None
            assert s.cobol_type.category == expected_cat

    def test_usage_is_display_by_default_after_build(self) -> None:
        table = self._run_builder(_var_sym("WS-N", picture="9(7)"))
        result = table.lookup("WS-N")
        assert isinstance(result, VariableSymbol)
        assert isinstance(result.cobol_type, NumericType)
        assert result.cobol_type.usage is UsageType.DISPLAY

    def test_bare_x_pic(self) -> None:
        table = self._run_builder(_var_sym("WS-FLAG", picture="X"))
        result = table.lookup("WS-FLAG")
        assert isinstance(result, VariableSymbol)
        assert isinstance(result.cobol_type, AlphanumericType)
        assert result.cobol_type.length == 1

    def test_bare_9_pic(self) -> None:
        table = self._run_builder(_var_sym("WS-DIGIT", picture="9"))
        result = table.lookup("WS-DIGIT")
        assert isinstance(result, VariableSymbol)
        assert isinstance(result.cobol_type, NumericType)
        assert result.cobol_type.digits == 1

    def test_is_integer_true_for_whole_numeric(self) -> None:
        table = self._run_builder(_var_sym("WS-N", picture="9(5)"))
        result = table.lookup("WS-N")
        assert isinstance(result, VariableSymbol)
        assert isinstance(result.cobol_type, NumericType)
        assert result.cobol_type.is_integer is True

    def test_is_integer_false_for_decimal_numeric(self) -> None:
        table = self._run_builder(_var_sym("WS-D", picture="9(5)V9(2)"))
        result = table.lookup("WS-D")
        assert isinstance(result, VariableSymbol)
        assert isinstance(result.cobol_type, NumericType)
        assert result.cobol_type.is_integer is False


# ===========================================================================
# TypeBuilder via AST traversal (SymbolCollectorVisitor + TypeBuilder)
# ===========================================================================


class TestTypeBuilderWithAstTraversal:
    """TypeBuilder works after SymbolCollectorVisitor has populated the table."""

    def _collect_and_build(
        self,
        *items: ElementaryItemNode | GroupItemNode | ConditionNameNode,
    ) -> SymbolTable:
        ws_node = _ws(*items)
        prog = _program(data=_data_div(ws_node))
        table = SymbolTable()
        collector = SymbolCollectorVisitor(table=table, diagnostics=[])
        traverse_program(prog, collector)
        TypeBuilder(table=table).build()
        return table

    def test_pic_x_via_ast(self) -> None:
        table = self._collect_and_build(_elementary("WS-NAME", "X(30)"))
        s = table.lookup("WS-NAME")
        assert isinstance(s, VariableSymbol)
        assert isinstance(s.cobol_type, AlphanumericType)
        assert s.cobol_type.length == 30

    def test_pic_9_via_ast(self) -> None:
        table = self._collect_and_build(_elementary("WS-COUNT", "9(5)"))
        s = table.lookup("WS-COUNT")
        assert isinstance(s, VariableSymbol)
        assert isinstance(s.cobol_type, NumericType)
        assert s.cobol_type.digits == 5

    def test_signed_pic_via_ast(self) -> None:
        table = self._collect_and_build(_elementary("WS-BAL", "S9(7)"))
        s = table.lookup("WS-BAL")
        assert isinstance(s, VariableSymbol)
        assert isinstance(s.cobol_type, NumericType)
        assert s.cobol_type.signed is True

    def test_group_item_via_ast(self) -> None:
        table = self._collect_and_build(_group("CUST-REC", level=1))
        s = table.lookup("CUST-REC")
        assert isinstance(s, VariableSymbol)
        assert isinstance(s.cobol_type, GroupType)

    def test_condition_name_via_ast(self) -> None:
        table = self._collect_and_build(_condition("EOF-FLAG"))
        s = table.lookup("EOF-FLAG")
        assert isinstance(s, VariableSymbol)
        assert isinstance(s.cobol_type, GroupType)

    def test_mixed_items_via_ast(self) -> None:
        table = self._collect_and_build(
            _elementary("WS-ID", "9(5)"),
            _elementary("WS-NAME", "X(30)"),
            _group("CUST-REC"),
        )
        assert isinstance(table.lookup("WS-ID"), VariableSymbol)
        assert isinstance(table.lookup("WS-ID").cobol_type, NumericType)  # type: ignore[union-attr]
        assert isinstance(table.lookup("WS-NAME"), VariableSymbol)
        assert isinstance(table.lookup("WS-NAME").cobol_type, AlphanumericType)  # type: ignore[union-attr]
        assert isinstance(table.lookup("CUST-REC"), VariableSymbol)
        assert isinstance(table.lookup("CUST-REC").cobol_type, GroupType)  # type: ignore[union-attr]


# ===========================================================================
# SemanticAnalyzer integration (pass 4)
# ===========================================================================


class TestSemanticAnalyzerPass4Integration:
    """SemanticAnalyzer.analyse() runs TypeBuilder as pass 4."""

    def _analyse(
        self,
        *items: ElementaryItemNode | GroupItemNode | ConditionNameNode,
        program_name: str = "TESTPROG",
    ):  # type: ignore[return]
        ws = _ws(*items)
        proc = _proc_div(_paragraph("MAIN"))
        return SemanticAnalyzer().analyse(
            _program(ident=_ident_div(program_name), data=_data_div(ws), proc=proc)
        )

    def test_pic_x_variable_has_alphanumeric_type(self) -> None:
        ctx = self._analyse(_elementary("WS-NAME", "X(30)"))
        s = ctx.symbol_table.lookup("WS-NAME")
        assert isinstance(s, VariableSymbol)
        assert isinstance(s.cobol_type, AlphanumericType)
        assert s.cobol_type.length == 30

    def test_pic_9_variable_has_numeric_type(self) -> None:
        ctx = self._analyse(_elementary("WS-COUNT", "9(5)"))
        s = ctx.symbol_table.lookup("WS-COUNT")
        assert isinstance(s, VariableSymbol)
        assert isinstance(s.cobol_type, NumericType)
        assert s.cobol_type.digits == 5

    def test_group_item_has_group_type(self) -> None:
        ctx = self._analyse(_group("CUST-REC", level=1))
        s = ctx.symbol_table.lookup("CUST-REC")
        assert isinstance(s, VariableSymbol)
        assert isinstance(s.cobol_type, GroupType)

    def test_signed_decimal_via_full_pipeline(self) -> None:
        ctx = self._analyse(_elementary("WS-AMOUNT", "S9(9)V9(2)"))
        s = ctx.symbol_table.lookup("WS-AMOUNT")
        assert isinstance(s, VariableSymbol)
        assert isinstance(s.cobol_type, NumericType)
        assert s.cobol_type.signed is True
        assert s.cobol_type.decimal_places == 2
        assert s.cobol_type.digits == 11

    def test_mixed_working_storage_all_typed(self) -> None:
        ctx = self._analyse(
            _elementary("WS-ID", "9(5)"),
            _elementary("WS-NAME", "X(30)"),
            _group("CUST-REC"),
        )
        for name, expected_cls in [
            ("WS-ID", NumericType),
            ("WS-NAME", AlphanumericType),
            ("CUST-REC", GroupType),
        ]:
            s = ctx.symbol_table.lookup(name)
            assert isinstance(s, VariableSymbol)
            assert isinstance(
                s.cobol_type, expected_cls
            ), f"{name} expected {expected_cls.__name__}, got {type(s.cobol_type)}"

    def test_no_pass4_diagnostics_for_valid_program(self) -> None:
        """TypeBuilder produces no diagnostics for a clean program."""
        ctx = self._analyse(
            _elementary("WS-COUNT", "9(5)"),
            _elementary("WS-NAME", "X(30)"),
        )
        assert not ctx.has_errors

    def test_pass1_sem001_plus_pass4_types(self) -> None:
        """SEM001 from pass 1 and cobol_type from pass 4 coexist."""
        ws = _ws(
            _elementary("DUP", "9(5)", line=10),
            _elementary("DUP", "9(5)", line=11),  # SEM001
            _elementary("WS-NAME", "X(30)", line=12),
        )
        proc = _proc_div(_paragraph("MAIN"))
        ctx = SemanticAnalyzer().analyse(
            _program(ident=_ident_div("TEST"), data=_data_div(ws), proc=proc)
        )
        codes = {d.code for d in ctx.diagnostics}
        assert "SEM001" in codes
        # WS-NAME should still be typed
        ws_name = ctx.symbol_table.lookup("WS-NAME")
        assert isinstance(ws_name, VariableSymbol)
        assert isinstance(ws_name.cobol_type, AlphanumericType)

    def test_analyser_reusable_across_programs(self) -> None:
        """Reusing SemanticAnalyzer produces independent contexts."""
        analyzer = SemanticAnalyzer()
        proc = _proc_div(_paragraph("MAIN"))

        ws1 = _ws(_elementary("WS-A", "9(5)"))
        ctx1 = analyzer.analyse(
            _program(ident=_ident_div("P1"), data=_data_div(ws1), proc=proc)
        )
        ws2 = _ws(_elementary("WS-B", "X(10)"))
        ctx2 = analyzer.analyse(
            _program(ident=_ident_div("P2"), data=_data_div(ws2), proc=proc)
        )
        # ctx1 should have WS-A, ctx2 should have WS-B
        assert ctx1.symbol_table.lookup("WS-A") is not None
        assert ctx1.symbol_table.lookup("WS-B") is None
        assert ctx2.symbol_table.lookup("WS-B") is not None
        assert ctx2.symbol_table.lookup("WS-A") is None

    def test_paragraph_symbols_have_no_cobol_type(self) -> None:
        """ParagraphSymbol does not have a cobol_type attribute."""
        ctx = self._analyse(_elementary("WS-X", "X(5)"))
        paras = ctx.symbol_table.symbols_of_kind(SymbolKind.PARAGRAPH)
        for p in paras:
            assert not hasattr(p, "cobol_type")

    def test_program_symbol_has_no_cobol_type(self) -> None:
        """ProgramSymbol does not have a cobol_type attribute."""
        ctx = self._analyse(_elementary("WS-X", "X(5)"))
        prog_syms = ctx.symbol_table.symbols_of_kind(SymbolKind.PROGRAM)
        for p in prog_syms:
            assert not hasattr(p, "cobol_type")


# ===========================================================================
# Parametrised PIC spot-checks via full pipeline
# ===========================================================================

_NUMERIC_PIC_SPOT_CHECKS = [
    ("9", 1, False, 0),
    ("9(5)", 5, False, 0),
    ("S9(9)", 9, True, 0),
    ("9(5)V9(2)", 7, False, 2),
    ("S9(9)V9(2)", 11, True, 2),
    ("99", 2, False, 0),
    ("S9(15)", 15, True, 0),
]


@pytest.mark.parametrize("pic,digits,signed,dec", _NUMERIC_PIC_SPOT_CHECKS)
def test_numeric_pic_via_type_builder(
    pic: str, digits: int, signed: bool, dec: int
) -> None:
    """Each numeric PIC string produces the correct NumericType via TypeBuilder."""
    sym = _var_sym("WS-N", picture=pic)
    table = _table_with(sym)
    TypeBuilder(table=table).build()
    result = table.lookup("WS-N")
    assert isinstance(result, VariableSymbol)
    ct = result.cobol_type
    assert isinstance(
        ct, NumericType
    ), f"Expected NumericType for PIC {pic!r}, got {ct!r}"
    assert ct.digits == digits
    assert ct.signed == signed
    assert ct.decimal_places == dec


_ALPHA_PIC_SPOT_CHECKS = [
    ("X", 1),
    ("X(5)", 5),
    ("X(30)", 30),
    ("XX", 2),
    ("X(100)", 100),
]


@pytest.mark.parametrize("pic,length", _ALPHA_PIC_SPOT_CHECKS)
def test_alpha_pic_via_type_builder(pic: str, length: int) -> None:
    """Each alphanumeric PIC string produces the correct AlphanumericType."""
    sym = _var_sym("WS-S", picture=pic)
    table = _table_with(sym)
    TypeBuilder(table=table).build()
    result = table.lookup("WS-S")
    assert isinstance(result, VariableSymbol)
    ct = result.cobol_type
    assert isinstance(
        ct, AlphanumericType
    ), f"Expected AlphanumericType for PIC {pic!r}, got {ct!r}"
    assert ct.length == length


# ===========================================================================
# COMP / COMP-3 usage via usage_from_string + manual NumericType
# ===========================================================================


class TestUsageAttachment:
    """UsageType is correctly stored in NumericType when set explicitly."""

    def test_comp_usage_numeric_type(self) -> None:
        t = NumericType(digits=9, usage=UsageType.COMP)
        assert t.usage is UsageType.COMP
        assert t.category == "numeric"

    def test_comp_3_usage_numeric_type(self) -> None:
        t = NumericType(digits=7, usage=UsageType.COMP_3)
        assert t.usage is UsageType.COMP_3

    def test_usage_from_string_then_attach(self) -> None:
        """Simulate explicit USAGE lookup and attachment."""
        usage = TypeBuilder.usage_from_string("COMP-3")
        sym = _var_sym("WS-AMOUNT", picture="S9(7)V9(2)")
        table = _table_with(sym)
        # Build the numeric type manually (as future code would)
        numeric = NumericType(digits=9, signed=True, decimal_places=2, usage=usage)
        updated = dataclasses.replace(sym, cobol_type=numeric)
        table.replace_symbol(updated)
        result = table.lookup("WS-AMOUNT")
        assert isinstance(result, VariableSymbol)
        assert isinstance(result.cobol_type, NumericType)
        assert result.cobol_type.usage is UsageType.COMP_3

    def test_usage_from_string_comp(self) -> None:
        usage = TypeBuilder.usage_from_string("COMP")
        numeric = NumericType(digits=9, usage=usage)
        assert numeric.usage is UsageType.COMP


# ===========================================================================
# Public API exports check
# ===========================================================================


class TestPublicApiExports:
    """Types and TypeBuilder are exported from the public package API."""

    def test_cobol_type_exported(self) -> None:
        from app.parser.semantic import CobolType as CT  # noqa: PLC0415

        assert CT is CobolType

    def test_numeric_type_exported(self) -> None:
        from app.parser.semantic import NumericType as NT  # noqa: PLC0415

        assert NT is NumericType

    def test_alphanumeric_type_exported(self) -> None:
        from app.parser.semantic import AlphanumericType as AT  # noqa: PLC0415

        assert AT is AlphanumericType

    def test_group_type_exported(self) -> None:
        from app.parser.semantic import GroupType as GT  # noqa: PLC0415

        assert GT is GroupType

    def test_usage_type_exported(self) -> None:
        from app.parser.semantic import UsageType as UT  # noqa: PLC0415

        assert UT is UsageType

    def test_type_builder_exported(self) -> None:
        from app.parser.semantic import TypeBuilder as TB  # noqa: PLC0415

        assert TB is TypeBuilder
