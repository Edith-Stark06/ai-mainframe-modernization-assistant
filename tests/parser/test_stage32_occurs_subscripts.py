"""
Stage 32 — OCCURS cardinality + structured subscript references.

Purpose:
    Lock in the AST/IR representation this stage introduces for fixed
    OCCURS tables and single-dimension (literal or identifier)
    subscripted operands, and the OCCURS-before-PIC type-preservation
    fix. Every test drives the real pipeline (lexer -> parser -> AST ->
    semantic analysis -> IR), because the defects this stage fixes are
    only observable through the real, integrated pipeline.

    Explicitly NOT covered here (out of this stage's scope, per the
    Stage 32 investigation report):
    - Java array generation / ``JavaField`` array metadata (Stage 33).
    - ``PERFORM VARYING`` grammar/lowering.
    - ``OCCURS DEPENDING ON``, ``INDEXED BY``.
    - Multi-dimensional or arithmetic subscripts (both deliberately fall
      back to the pre-existing flat-string operand, unchanged).

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.service import AnalysisService
from app.parser.ast.data_items import ElementaryItemNode, GroupItemNode
from app.parser.ast.statements import (
    AddStatementNode,
    DisplayStatementNode,
    IfStatementNode,
    MoveStatementNode,
    Subscript,
)
from app.parser.lexer.lexer import CobolLexer
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.semantic.symbols import SymbolKind
from app.parser.semantic.types import NumericType
from app.parser.syntax.program_parser import ProgramParser

_ID = (
    "IDENTIFICATION DIVISION.\n"
    "PROGRAM-ID. T.\n"
    "DATA DIVISION.\n"
    "WORKING-STORAGE SECTION.\n"
)


def _parse_data(clause: str):
    """Parse one WORKING-STORAGE data-item clause and return (item, program)."""
    source = _ID + clause + "\nPROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n"
    tokens = CobolLexer().tokenize(source, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    items = program.data_division.working_storage.items
    return items[0], program


def _analyze(tmp_path: Path, source: str):
    path = tmp_path / "t.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _first_paragraph_statements(result):
    return result.ast.procedure_division.paragraphs[0].statements


# ===========================================================================
# 1-2. OCCURS n / OCCURS n TIMES produce the same cardinality
# ===========================================================================


class TestOccursCardinality:
    def test_occurs_bare_count(self) -> None:
        item, _ = _parse_data("01 WS-ITEM PIC 9(3) OCCURS 5.")
        assert isinstance(item, ElementaryItemNode)
        assert item.occurs == 5

    def test_occurs_with_times(self) -> None:
        item, _ = _parse_data("01 WS-ITEM PIC 9(3) OCCURS 5 TIMES.")
        assert isinstance(item, ElementaryItemNode)
        assert item.occurs == 5

    def test_bare_and_times_forms_agree(self) -> None:
        bare, _ = _parse_data("01 WS-ITEM PIC 9(3) OCCURS 7.")
        times, _ = _parse_data("01 WS-ITEM PIC 9(3) OCCURS 7 TIMES.")
        assert bare.occurs == times.occurs == 7

    def test_non_occurs_item_has_no_cardinality(self) -> None:
        item, _ = _parse_data("01 WS-ITEM PIC 9(3).")
        assert item.occurs is None


# ===========================================================================
# 3-4. Elementary vs. group OCCURS
# ===========================================================================


class TestOccursItemShape:
    def test_elementary_occurs_keeps_picture(self) -> None:
        """Regression: OCCURS must not cost the item its PIC (pre-existing
        assertion this stage's fix must continue to satisfy)."""
        item, _ = _parse_data("01 WS-ITEM PIC X(5) OCCURS 3 TIMES.")
        assert isinstance(item, ElementaryItemNode)
        assert item.picture == "X(5)"
        assert item.occurs == 3

    def test_group_occurs_has_no_picture_but_children_keep_their_pic(self) -> None:
        """``DataItemNode.children`` is always empty in this AST -- data
        items are stored as one flat, level-numbered list (confirmed
        directly; not a Stage 32 change, pre-existing architecture) -- so
        this checks the flat list's own level/occurs/picture values
        instead of a nested tree."""
        _, program = _parse_data(
            "01 WS-TABLE.\n"
            "   05 WS-ENTRY OCCURS 5 TIMES.\n"
            "      10 WS-NAME PIC X(9).\n"
            "      10 WS-AMOUNT PIC 9(5)."
        )
        items = {i.name: i for i in program.data_division.working_storage.items}
        assert items["WS-TABLE"].occurs is None
        entry = items["WS-ENTRY"]
        assert isinstance(entry, GroupItemNode)
        assert entry.occurs == 5
        assert items["WS-NAME"].picture == "X(9)"
        assert items["WS-NAME"].occurs is None
        assert items["WS-AMOUNT"].picture == "9(5)"
        assert items["WS-AMOUNT"].occurs is None


# ===========================================================================
# 5. OCCURS-before-PIC no longer destroys the element's type
# ===========================================================================


class TestOccursBeforePicFix:
    def test_occurs_before_pic_preserves_picture(self) -> None:
        item, _ = _parse_data("05 WS-AMOUNT OCCURS 10 TIMES PIC 9(5).")
        assert isinstance(item, ElementaryItemNode)
        assert item.picture == "9(5)"
        assert item.occurs == 10

    def test_occurs_before_pic_no_times_preserves_picture(self) -> None:
        item, _ = _parse_data("05 WS-AMOUNT OCCURS 10 PIC 9(5).")
        assert isinstance(item, ElementaryItemNode)
        assert item.picture == "9(5)"
        assert item.occurs == 10

    def test_occurs_before_pic_resolves_to_numeric_type(self, tmp_path: Path) -> None:
        """Before this stage: GroupType() (type destroyed). After: the real
        NumericType, exactly as the safe (PIC-first) ordering already gave."""
        source = (
            _ID + "01 WS-TABLE.\n"
            "   05 WS-AMOUNT OCCURS 10 TIMES PIC 9(5).\n"
            "PROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n"
        )
        result = _analyze(tmp_path, source)
        ctx = SemanticAnalyzer().analyse(result.ast)
        (sym,) = [
            s
            for s in ctx.symbol_table.symbols_of_kind(SymbolKind.VARIABLE)
            if s.name == "WS-AMOUNT"
        ]
        assert sym.picture == "9(5)"
        assert sym.occurs == 10
        assert isinstance(sym.cobol_type, NumericType)
        assert sym.cobol_type.digits == 5

    def test_both_orderings_agree_on_type(self, tmp_path: Path) -> None:
        pic_first = (
            _ID + "01 WS-TABLE.\n   05 WS-AMOUNT PIC 9(5) OCCURS 10 TIMES.\n"
            "PROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n"
        )
        occurs_first = (
            _ID + "01 WS-TABLE.\n   05 WS-AMOUNT OCCURS 10 TIMES PIC 9(5).\n"
            "PROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n"
        )
        r1 = _analyze(tmp_path, pic_first)
        ctx1 = SemanticAnalyzer().analyse(r1.ast)
        r2 = _analyze(tmp_path, occurs_first)
        ctx2 = SemanticAnalyzer().analyse(r2.ast)
        sym1 = ctx1.symbol_table.lookup("WS-AMOUNT")
        sym2 = ctx2.symbol_table.lookup("WS-AMOUNT")
        assert sym1.cobol_type == sym2.cobol_type == NumericType(digits=5)
        assert sym1.occurs == sym2.occurs == 10


_TABLE_HEADER = (
    _ID + "01 WS-TABLE.\n"
    "   05 WS-ITEM PIC 9(5) OCCURS 5 TIMES.\n"
    "   05 WS-I PIC 9(2) VALUE 1.\n"
    "01 WS-TOTAL PIC 9(5).\n"
    "01 WS-J PIC 9(2) VALUE 2.\n"
)


def _table_program(procedure_body: str) -> str:
    return _TABLE_HEADER + "PROCEDURE DIVISION.\nMAIN-PARA.\n" + procedure_body


# ===========================================================================
# 6-9. Literal / identifier subscripts in MOVE (target and source)
# ===========================================================================


class TestSubscriptedMove:
    def test_literal_subscript_move_target(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path, _table_program("    MOVE 100 TO WS-ITEM(2).\n    STOP RUN.\n")
        )
        assert result.syntax_diagnostics == [] or all(
            d.code == "SYN200" for d in result.syntax_diagnostics
        )
        (move,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, MoveStatementNode)
        ]
        assert move.source == "100"
        assert move.source_subscript == ()
        assert move.target == "WS-ITEM"
        assert move.target_subscript == (Subscript(kind="literal", value="2"),)

    def test_identifier_subscript_move_source(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            _table_program("    MOVE WS-ITEM(WS-I) TO WS-TOTAL.\n    STOP RUN.\n"),
        )
        (move,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, MoveStatementNode)
        ]
        assert move.source == "WS-ITEM"
        assert move.source_subscript == (Subscript(kind="identifier", value="WS-I"),)
        assert move.target == "WS-TOTAL"
        assert move.target_subscript == ()

    def test_both_operands_subscripted(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            _table_program("    MOVE WS-ITEM(WS-I) TO WS-ITEM(WS-J).\n    STOP RUN.\n"),
        )
        (move,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, MoveStatementNode)
        ]
        assert move.source == "WS-ITEM"
        assert move.source_subscript == (Subscript(kind="identifier", value="WS-I"),)
        assert move.target == "WS-ITEM"
        assert move.target_subscript == (Subscript(kind="identifier", value="WS-J"),)


# ===========================================================================
# 10. Subscripted arithmetic operand (ADD/SUBTRACT/MULTIPLY/DIVIDE)
# ===========================================================================


class TestSubscriptedArithmetic:
    def test_add_identifier_subscript(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path, _table_program("    ADD 1 TO WS-ITEM(WS-I).\n    STOP RUN.\n")
        )
        (add,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, AddStatementNode)
        ]
        assert add.left == "1"
        assert add.left_subscript == ()
        assert add.right == "WS-ITEM"
        assert add.right_subscript == (Subscript(kind="identifier", value="WS-I"),)

    def test_add_literal_subscript(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path, _table_program("    ADD 1 TO WS-ITEM(3).\n    STOP RUN.\n")
        )
        (add,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, AddStatementNode)
        ]
        assert add.right == "WS-ITEM"
        assert add.right_subscript == (Subscript(kind="literal", value="3"),)


# ===========================================================================
# 11. Subscripted IF condition — the parser used to drop the whole IF
# ===========================================================================


class TestSubscriptedCondition:
    def test_subscripted_if_no_longer_drops_the_construct(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            _table_program(
                "    IF WS-ITEM(WS-I) > 100\n"
                "        DISPLAY 'HIGH'\n"
                "    END-IF.\n"
                "    STOP RUN.\n"
            ),
        )
        assert result.success is True
        assert [d.code for d in result.syntax_diagnostics if d.code != "SYN200"] == []
        (if_stmt,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, IfStatementNode)
        ]
        assert if_stmt.condition_left == "WS-ITEM"
        assert if_stmt.condition_left_subscript == (
            Subscript(kind="identifier", value="WS-I"),
        )
        assert if_stmt.condition_operator == ">"
        assert if_stmt.condition_right == "100"
        assert if_stmt.condition_right_subscript == ()
        assert len(if_stmt.then_statements) == 1

    def test_subscripted_if_literal_left_operand(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            _table_program(
                "    IF WS-ITEM(2) = 0\n"
                "        DISPLAY 'X'\n"
                "    END-IF.\n"
                "    STOP RUN.\n"
            ),
        )
        (if_stmt,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, IfStatementNode)
        ]
        assert if_stmt.condition_left == "WS-ITEM"
        assert if_stmt.condition_left_subscript == (
            Subscript(kind="literal", value="2"),
        )
        assert if_stmt.condition_right == "0"
        assert if_stmt.condition_right_subscript == ()


# ===========================================================================
# 12. Subscripted DISPLAY
# ===========================================================================


class TestSubscriptedDisplay:
    def test_display_identifier_subscript(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path, _table_program("    DISPLAY WS-ITEM(WS-I).\n    STOP RUN.\n")
        )
        (disp,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, DisplayStatementNode)
        ]
        assert disp.operand == "WS-ITEM"
        assert disp.operand_subscript == (Subscript(kind="identifier", value="WS-I"),)

    def test_display_literal_subscript(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path, _table_program("    DISPLAY WS-ITEM(1).\n    STOP RUN.\n")
        )
        (disp,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, DisplayStatementNode)
        ]
        assert disp.operand == "WS-ITEM"
        assert disp.operand_subscript == (Subscript(kind="literal", value="1"),)


# ===========================================================================
# 13. Multiple independent subscripted references in one program
# ===========================================================================


class TestMultipleIndependentSubscripts:
    def test_several_statements_each_keep_their_own_subscript(
        self, tmp_path: Path
    ) -> None:
        result = _analyze(
            tmp_path,
            _table_program(
                "    MOVE 100 TO WS-ITEM(1).\n"
                "    MOVE 200 TO WS-ITEM(2).\n"
                "    ADD 1 TO WS-ITEM(WS-I).\n"
                "    DISPLAY WS-ITEM(WS-J).\n"
                "    STOP RUN.\n"
            ),
        )
        moves = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, MoveStatementNode)
        ]
        assert moves[0].target_subscript == (Subscript(kind="literal", value="1"),)
        assert moves[1].target_subscript == (Subscript(kind="literal", value="2"),)
        (add,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, AddStatementNode)
        ]
        assert add.right_subscript == (Subscript(kind="identifier", value="WS-I"),)
        (disp,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, DisplayStatementNode)
        ]
        assert disp.operand_subscript == (Subscript(kind="identifier", value="WS-J"),)


# ===========================================================================
# 14. Non-subscripted regression: scalar behaviour is byte-for-byte unchanged
# ===========================================================================


class TestScalarRegression:
    def test_scalar_move_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            _ID + "01 WS-A PIC 9(3) VALUE 1.\n01 WS-B PIC 9(3).\n"
            "PROCEDURE DIVISION.\nMAIN-PARA.\n    MOVE WS-A TO WS-B.\n    STOP RUN.\n",
        )
        (move,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, MoveStatementNode)
        ]
        assert move.source == "WS-A"
        assert move.source_subscript == ()
        assert move.target == "WS-B"
        assert move.target_subscript == ()

    def test_scalar_if_unaffected(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            _ID + "01 WS-A PIC 9(3) VALUE 1.\n"
            "PROCEDURE DIVISION.\nMAIN-PARA.\n"
            "    IF WS-A > 0\n        DISPLAY 'X'\n    END-IF.\n    STOP RUN.\n",
        )
        (if_stmt,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, IfStatementNode)
        ]
        assert if_stmt.condition_left_subscript == ()
        assert if_stmt.condition_right_subscript == ()

    def test_non_occurs_group_item_unaffected(self) -> None:
        item, program = _parse_data(
            "01 WS-GROUP.\n   05 WS-A PIC X(3).\n   05 WS-B PIC 9(3)."
        )
        assert isinstance(item, GroupItemNode)
        assert item.occurs is None
        items = program.data_division.working_storage.items
        assert isinstance(items[1], ElementaryItemNode)
        assert items[1].occurs is None


# ===========================================================================
# 17. COBOL's 1-based subscript meaning is preserved, never adjusted
# ===========================================================================


class TestOneBasedPreservation:
    def test_ast_subscript_value_is_never_decremented(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path, _table_program("    MOVE 100 TO WS-ITEM(1).\n    STOP RUN.\n")
        )
        (move,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, MoveStatementNode)
        ]
        # WS-ITEM(1) means the FIRST element in COBOL; the AST must carry
        # "1" verbatim, never "0".
        assert move.target_subscript == (Subscript(kind="literal", value="1"),)

    def test_ir_subscript_value_is_never_decremented(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path, _table_program("    MOVE 100 TO WS-ITEM(1).\n    STOP RUN.\n")
        )
        instr = result.ir.modules[0].functions[0].blocks[0].instructions[0]
        assert instr.result == "WS-ITEM"
        assert instr.result_subscript[0].value == "1"


# ===========================================================================
# 18. Flat-string corruption no longer occurs for the shapes this stage models
# ===========================================================================


class TestNoFlatStringCorruption:
    def test_move_operands_are_never_a_joined_string(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            _table_program("    MOVE WS-ITEM(WS-I) TO WS-ITEM(WS-J).\n    STOP RUN.\n"),
        )
        (move,) = [
            s
            for s in _first_paragraph_statements(result)
            if isinstance(s, MoveStatementNode)
        ]
        assert "(" not in move.source
        assert "(" not in move.target
        assert " " not in move.source
        assert " " not in move.target

    def test_semantic_analysis_no_longer_reports_undefined_variable(
        self, tmp_path: Path
    ) -> None:
        """Before this stage: SEM003 "undefined variable: 'WS-ITEM ( WS-I )'".
        The base name now resolves against the real declared symbol."""
        result = _analyze(
            tmp_path, _table_program("    MOVE 1 TO WS-ITEM(WS-I).\n    STOP RUN.\n")
        )
        assert result.semantic_diagnostics == []
