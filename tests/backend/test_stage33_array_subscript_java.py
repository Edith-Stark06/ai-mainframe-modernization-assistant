"""
Unit and integration tests for task #stage33 — Java backend lowering of
task #stage32's structured OCCURS/subscript AST/IR representation.

Scope under test:
    - Fixed OCCURS elementary items (own, or an enclosing group's) become
      Java arrays (``int[]``/``double[]``/``String[]``), never a group
      item itself.
    - The ONE shared subscript renderer (``_translate_subscript_index`` /
      ``_render_reference``) applies COBOL's 1-based -> Java 0-based
      adjustment exactly once, for a literal or an identifier subscript,
      reused by every emitter: MOVE (source and target), ADD/SUBTRACT/
      MULTIPLY/DIVIDE, IF (including compound terms), DISPLAY.
    - Stage 31's PICTURE-based DISPLAY formatting keeps working for a
      subscripted array element and is correctly *not* applied to a bare,
      unsubscripted reference to the array itself.

Deliberately NOT covered here (out of Stage 33's scope, per the task):
    - PERFORM VARYING, COMPUTE.
    - OCCURS DEPENDING ON, INDEXED BY, multidimensional tables, arithmetic
      subscripts, reference modification, bounds checking.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.service import AnalysisService
from app.backend.java.field_model import JavaField
from app.backend.java.generator import build_fields_from_symbols
from app.backend.java.statement_emitter import (
    _render_reference,
    _translate_subscript_index,
)
from app.ir.instructions import IRSubscript
from app.parser.lexer.position import Position
from app.parser.semantic.symbols import VariableSymbol
from app.parser.semantic.types import AlphanumericType, GroupType, NumericType

_POS = Position(line=1, column=1, offset=0, filename="test.cbl")


def _var(
    name: str,
    level: int,
    cobol_type=None,
    occurs: int | None = None,
) -> VariableSymbol:
    return VariableSymbol(
        name=name, declared_at=_POS, level=level, cobol_type=cobol_type, occurs=occurs
    )


def _analyze(tmp_path: Path, body: str, header: str = "") -> str:
    """Run the real pipeline and return the generated Java source."""
    source = (
        "IDENTIFICATION DIVISION.\n"
        "PROGRAM-ID. T.\n"
        "DATA DIVISION.\n"
        "WORKING-STORAGE SECTION.\n"
        + header
        + "PROCEDURE DIVISION.\nMAIN-PARA.\n"
        + body
    )
    path = tmp_path / "t.cbl"
    path.write_text(source, encoding="utf-8")
    result = AnalysisService().analyze_file(path)
    assert not result.backend_diagnostics, result.backend_diagnostics
    return result.java_source


_TABLE_HEADER = (
    "01 WS-TABLE.\n"
    "   05 WS-ITEM PIC 9(3) OCCURS 5.\n"
    "   05 WS-I PIC 9(2) VALUE 1.\n"
    "01 WS-TOTAL PIC 9(3).\n"
)


# ===========================================================================
# The shared subscript renderer -- unit level
# ===========================================================================


class TestTranslateSubscriptIndex:
    def test_literal_two_becomes_one(self) -> None:
        assert _translate_subscript_index(IRSubscript(kind="literal", value="2")) == "1"

    def test_literal_one_becomes_zero(self) -> None:
        """Item L: the exact 1-based -> 0-based boundary case."""
        assert _translate_subscript_index(IRSubscript(kind="literal", value="1")) == "0"

    def test_identifier_uses_existing_naming_rules(self) -> None:
        assert (
            _translate_subscript_index(IRSubscript(kind="identifier", value="WS-I"))
            == "wsI - 1"
        )

    def test_identifier_naming_is_not_a_second_algorithm(self) -> None:
        """Item M: CURRENT-IDX renders via to_java_field_name, not a
        bespoke subscript-naming scheme."""
        assert (
            _translate_subscript_index(
                IRSubscript(kind="identifier", value="CURRENT-IDX")
            )
            == "currentIdx - 1"
        )


class TestRenderReference:
    def test_no_subscript_is_plain_field_name(self) -> None:
        assert _render_reference("WS-ITEM") == "wsItem"

    def test_literal_subscript(self) -> None:
        assert (
            _render_reference("WS-ITEM", (IRSubscript(kind="literal", value="2"),))
            == "wsItem[1]"
        )

    def test_identifier_subscript(self) -> None:
        assert (
            _render_reference(
                "WS-ITEM", (IRSubscript(kind="identifier", value="WS-I"),)
            )
            == "wsItem[wsI - 1]"
        )


# ===========================================================================
# build_fields_from_symbols -- array declaration (items A, B)
# ===========================================================================


class TestArrayDeclaration:
    def test_scalar_field_is_unaffected(self) -> None:
        """Item A: a plain PIC 9(3) still generates the existing scalar
        Java field -- no regression from this stage."""
        sym = _var("WS-COUNT", level=1, cobol_type=NumericType(digits=3))
        (fld,) = build_fields_from_symbols([sym])
        assert fld.java_type == "int"
        assert fld.occurs is None
        assert fld.render() == "    private int wsCount;"

    def test_elementary_occurs_becomes_int_array(self) -> None:
        """Item B: PIC 9(3) OCCURS 5 -> int[] of length 5."""
        sym = _var("WS-ITEM", level=5, cobol_type=NumericType(digits=3), occurs=5)
        (fld,) = build_fields_from_symbols([sym])
        assert fld.java_type == "int[]"
        assert fld.initial_value == "new int[5]"
        assert fld.occurs == 5
        assert fld.render() == "    private int[] wsItem = new int[5];"

    def test_elementary_occurs_alphanumeric_becomes_string_array(self) -> None:
        sym = _var("SKU-ID", level=5, cobol_type=AlphanumericType(length=8), occurs=5)
        (fld,) = build_fields_from_symbols([sym])
        assert fld.java_type == "String[]"
        assert fld.initial_value == "new String[5]"

    def test_digits_and_length_describe_one_element_unchanged(self) -> None:
        """The array's element PICTURE metadata (task #stage31) is
        unaffected by array-ification -- needed for per-element DISPLAY
        formatting once indexed."""
        sym = _var("WS-ITEM", level=5, cobol_type=NumericType(digits=3), occurs=5)
        (fld,) = build_fields_from_symbols([sym])
        assert fld.digits == 3
        assert fld.decimal_places == 0
        assert fld.signed is False

    def test_group_with_own_occurs_is_not_array_ified(self) -> None:
        """A GROUP that itself declares OCCURS (the real corpus shape,
        e.g. `05 LINE-ITEM OCCURS 5 TIMES.`) stays scalar String -- never
        turned into an array of an aggregate the backend has no single
        Java type for."""
        sym = _var("LINE-ITEM", level=5, cobol_type=GroupType(), occurs=5)
        (fld,) = build_fields_from_symbols([sym])
        assert fld.java_type == "String"
        assert fld.occurs is None

    def test_elementary_child_of_occurs_group_inherits_the_array(self) -> None:
        """The actual corpus shape: `05 LINE-ITEM OCCURS 5 TIMES.` with
        plain elementary children that carry no OCCURS of their own --
        each child must still become an array of the group's own size, or
        a subscripted reference to it (`SKU-ID(1)`) would index into a
        scalar."""
        symbols = [
            _var("PO-LINE-ITEMS", level=5, cobol_type=GroupType()),
            _var("LINE-COUNT", level=10, cobol_type=NumericType(digits=2)),
            _var("LINE-ITEM", level=10, cobol_type=GroupType(), occurs=5),
            _var("SKU-ID", level=15, cobol_type=AlphanumericType(length=8)),
            _var(
                "UNIT-COST-AMOUNT",
                level=15,
                cobol_type=NumericType(digits=7, decimal_places=2),
            ),
        ]
        fields = {f.cobol_name: f for f in build_fields_from_symbols(symbols)}
        assert fields["PO-LINE-ITEMS"].java_type == "String"  # unrelated group
        assert fields["LINE-COUNT"].java_type == "int"  # sibling, not nested
        assert fields["LINE-ITEM"].java_type == "String"  # the OCCURS group itself
        assert fields["SKU-ID"].java_type == "String[]"
        assert fields["SKU-ID"].initial_value == "new String[5]"
        assert fields["UNIT-COST-AMOUNT"].java_type == "double[]"
        assert fields["UNIT-COST-AMOUNT"].initial_value == "new double[5]"

    def test_sibling_after_an_occurs_group_is_unaffected(self) -> None:
        """A field declared *after* an OCCURS group's children, at the
        same level as the group, must not inherit its OCCURS -- the
        level-number stack must correctly close the group scope."""
        symbols = [
            _var("PO-LINE-ITEMS", level=5, cobol_type=GroupType()),
            _var("LINE-ITEM", level=10, cobol_type=GroupType(), occurs=5),
            _var("SKU-ID", level=15, cobol_type=AlphanumericType(length=8)),
            _var("PO-SHIPPING-CONTAINER", level=5, cobol_type=GroupType()),
            _var("CARRIER-CODE", level=10, cobol_type=AlphanumericType(length=4)),
        ]
        fields = {f.cobol_name: f for f in build_fields_from_symbols(symbols)}
        assert fields["CARRIER-CODE"].java_type == "String"
        assert fields["CARRIER-CODE"].occurs is None

    def test_value_clause_on_an_occurs_item_is_not_applied_to_the_array(
        self,
    ) -> None:
        """Item #8: no generalized array-VALUE semantics are invented --
        an OCCURS item's own VALUE (if any) is ignored, not partially or
        incorrectly translated."""
        sym = VariableSymbol(
            name="WS-ITEM",
            declared_at=_POS,
            level=5,
            cobol_type=NumericType(digits=3),
            occurs=5,
            value="007",
        )
        (fld,) = build_fields_from_symbols([sym])
        assert fld.initial_value == "new int[5]"


# ===========================================================================
# End-to-end pipeline: MOVE (items C, D, E, F)
# ===========================================================================


class TestMoveArraySubscript:
    def test_literal_target(self, tmp_path: Path) -> None:
        """Item C: MOVE 123 TO WS-ITEM(2) -> wsItem[1] = 123;"""
        java = _analyze(
            tmp_path, "    MOVE 123 TO WS-ITEM(2).\n    STOP RUN.\n", _TABLE_HEADER
        )
        assert "wsItem[1] = 123;" in java

    def test_identifier_target(self, tmp_path: Path) -> None:
        """Item D: MOVE 123 TO WS-ITEM(WS-I) -> wsItem[wsI - 1] = 123;"""
        java = _analyze(
            tmp_path, "    MOVE 123 TO WS-ITEM(WS-I).\n    STOP RUN.\n", _TABLE_HEADER
        )
        assert "wsItem[wsI - 1] = 123;" in java

    def test_literal_source(self, tmp_path: Path) -> None:
        """Item E: MOVE WS-ITEM(2) TO WS-TOTAL -> wsTotal = wsItem[1];"""
        java = _analyze(
            tmp_path,
            "    MOVE WS-ITEM(2) TO WS-TOTAL.\n    STOP RUN.\n",
            _TABLE_HEADER,
        )
        assert "wsTotal = wsItem[1];" in java

    def test_identifier_source(self, tmp_path: Path) -> None:
        """Item F: MOVE WS-ITEM(WS-I) TO WS-TOTAL -> wsTotal = wsItem[wsI - 1];"""
        java = _analyze(
            tmp_path,
            "    MOVE WS-ITEM(WS-I) TO WS-TOTAL.\n    STOP RUN.\n",
            _TABLE_HEADER,
        )
        assert "wsTotal = wsItem[wsI - 1];" in java

    def test_both_sides_subscripted(self, tmp_path: Path) -> None:
        """The IR shape the task explicitly names: `MOVE 123 TO
        WS-ITEM(WS-I)` distinguishes source (none) from target
        (identifier) correctly -- and a distinct case with a subscripted
        source AND target together is not confused."""
        java = _analyze(
            tmp_path,
            "    MOVE WS-ITEM(2) TO WS-ITEM(WS-I).\n    STOP RUN.\n",
            _TABLE_HEADER,
        )
        assert "wsItem[wsI - 1] = wsItem[1];" in java


# ===========================================================================
# End-to-end pipeline: arithmetic (item K)
# ===========================================================================


class TestArithmeticArraySubscript:
    def test_add_literal_subscript(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path, "    ADD 1 TO WS-ITEM(2).\n    STOP RUN.\n", _TABLE_HEADER
        )
        assert "wsItem[1] += 1;" in java

    def test_add_identifier_subscript(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path, "    ADD 1 TO WS-ITEM(WS-I).\n    STOP RUN.\n", _TABLE_HEADER
        )
        assert "wsItem[wsI - 1] += 1;" in java

    def test_subtract_identifier_subscript(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path,
            "    SUBTRACT 1 FROM WS-ITEM(WS-I).\n    STOP RUN.\n",
            _TABLE_HEADER,
        )
        assert "wsItem[wsI - 1] -= 1;" in java

    def test_multiply_left_operand_is_never_subscripted_by_accident(
        self, tmp_path: Path
    ) -> None:
        """MULTIPLY WS-I BY WS-ITEM(2) -- the applied operand (WS-I) has
        no subscript of its own; only the accumulator target does."""
        java = _analyze(
            tmp_path,
            "    MULTIPLY WS-I BY WS-ITEM(2).\n    STOP RUN.\n",
            _TABLE_HEADER,
        )
        assert "wsItem[1] *= wsI;" in java

    def test_divide_identifier_subscript(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path,
            "    DIVIDE 2 INTO WS-ITEM(WS-I).\n    STOP RUN.\n",
            _TABLE_HEADER,
        )
        assert "wsItem[wsI - 1] /= 2;" in java


# ===========================================================================
# End-to-end pipeline: IF (items G, H)
# ===========================================================================


class TestIfArraySubscript:
    def test_literal_subscript(self, tmp_path: Path) -> None:
        """Item G: IF WS-ITEM(2) > 100 references wsItem[1]."""
        java = _analyze(
            tmp_path,
            "    IF WS-ITEM(2) > 100\n"
            "        DISPLAY 'HIGH'\n"
            "    END-IF.\n    STOP RUN.\n",
            _TABLE_HEADER,
        )
        assert "if (wsItem[1] > 100) {" in java

    def test_identifier_subscript(self, tmp_path: Path) -> None:
        """Item H: IF WS-ITEM(WS-I) > 100 references wsItem[wsI - 1]."""
        java = _analyze(
            tmp_path,
            "    IF WS-ITEM(WS-I) > 100\n"
            "        DISPLAY 'HIGH'\n"
            "    END-IF.\n    STOP RUN.\n",
            _TABLE_HEADER,
        )
        assert "if (wsItem[wsI - 1] > 100) {" in java

    def test_compound_condition_extra_term_subscript(self, tmp_path: Path) -> None:
        """A subscripted operand inside an AND/OR extra term (not just the
        first condition) must also go through the shared renderer."""
        java = _analyze(
            tmp_path,
            "    IF WS-TOTAL > 0 AND WS-ITEM(WS-I) > 100\n"
            "        DISPLAY 'HIGH'\n"
            "    END-IF.\n    STOP RUN.\n",
            _TABLE_HEADER,
        )
        assert "if (wsTotal > 0 && wsItem[wsI - 1] > 100) {" in java


# ===========================================================================
# End-to-end pipeline: DISPLAY (items I, J) + Stage 31 formatting
# ===========================================================================


class TestDisplayArraySubscript:
    def test_literal_subscript(self, tmp_path: Path) -> None:
        """Item I: DISPLAY WS-ITEM(2) references wsItem[1]."""
        java = _analyze(
            tmp_path, "    DISPLAY WS-ITEM(2).\n    STOP RUN.\n", _TABLE_HEADER
        )
        assert "wsItem[1]" in java

    def test_identifier_subscript(self, tmp_path: Path) -> None:
        """Item J: DISPLAY WS-ITEM(WS-I) references wsItem[wsI - 1]."""
        java = _analyze(
            tmp_path, "    DISPLAY WS-ITEM(WS-I).\n    STOP RUN.\n", _TABLE_HEADER
        )
        assert "wsItem[wsI - 1]" in java

    def test_stage31_formatting_still_applies_to_the_indexed_element(
        self, tmp_path: Path
    ) -> None:
        """PIC 9(3) formatting (zero-pad to 3 digits, task #stage31) is
        preserved for one array element once indexed."""
        java = _analyze(
            tmp_path, "    DISPLAY WS-ITEM(2).\n    STOP RUN.\n", _TABLE_HEADER
        )
        assert 'System.out.println(String.format("%03d", wsItem[1]));' in java

    def test_stage31_formatting_still_applies_for_identifier_subscript(
        self, tmp_path: Path
    ) -> None:
        java = _analyze(
            tmp_path, "    DISPLAY WS-ITEM(WS-I).\n    STOP RUN.\n", _TABLE_HEADER
        )
        assert 'System.out.println(String.format("%03d", wsItem[wsI - 1]));' in java

    def test_bare_unsubscripted_array_reference_is_not_formatted(self) -> None:
        """A hypothetical bare DISPLAY of the whole array (no subscript)
        must not attempt to String.format an int[] as if it were one
        int -- this stays an explicit, checked gap (matching Stage 31's
        own documented "OCCURS/subscripted item DISPLAY" exclusion), not
        a compile error."""
        from app.backend.java.condition_context import ConditionContext
        from app.backend.java.statement_emitter import _format_display_operand

        ctx = ConditionContext(
            fields={
                "wsItem": JavaField(
                    java_name="wsItem",
                    java_type="int[]",
                    digits=3,
                    occurs=5,
                )
            }
        )
        assert _format_display_operand("WS-ITEM", "wsItem", ctx) == "wsItem"
        assert (
            _format_display_operand("WS-ITEM", "wsItem[1]", ctx, subscripted=True)
            == 'String.format("%03d", wsItem[1])'
        )


# ===========================================================================
# Item L: negative regression -- exact 1-based/0-based boundary
# ===========================================================================


class TestNegativeRegression:
    def test_ws_item_2_does_not_become_a_mangled_scalar_name(
        self, tmp_path: Path
    ) -> None:
        java = _analyze(
            tmp_path, "    MOVE 123 TO WS-ITEM(2).\n    STOP RUN.\n", _TABLE_HEADER
        )
        assert "wsItem2" not in java

    def test_ws_item_2_does_not_stay_1_based_in_java(self, tmp_path: Path) -> None:
        """WS-ITEM(2) must not become wsItem[2] -- that would silently
        read/write the WRONG (3rd, 0-based) Java array slot."""
        java = _analyze(
            tmp_path, "    MOVE 123 TO WS-ITEM(2).\n    STOP RUN.\n", _TABLE_HEADER
        )
        assert "wsItem[2]" not in java

    def test_ws_item_2_does_not_become_wsitem_0(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path, "    MOVE 123 TO WS-ITEM(2).\n    STOP RUN.\n", _TABLE_HEADER
        )
        assert "wsItem[0]" not in java

    def test_exact_boundary_mapping(self, tmp_path: Path) -> None:
        """WS-ITEM(1) -> wsItem[0]; WS-ITEM(2) -> wsItem[1] -- both in the
        same program, unambiguously distinct."""
        java = _analyze(
            tmp_path,
            "    MOVE 1 TO WS-ITEM(1).\n"
            "    MOVE 2 TO WS-ITEM(2).\n"
            "    STOP RUN.\n",
            _TABLE_HEADER,
        )
        assert "wsItem[0] = 1;" in java
        assert "wsItem[1] = 2;" in java


# ===========================================================================
# Item M: identifier naming reuses the existing rules end-to-end
# ===========================================================================


class TestIdentifierNamingEndToEnd:
    def test_current_idx_renders_via_existing_naming_rules(
        self, tmp_path: Path
    ) -> None:
        header = (
            "01 WS-TABLE.\n"
            "   05 WS-ITEM PIC 9(3) OCCURS 5.\n"
            "   05 CURRENT-IDX PIC 9(2) VALUE 1.\n"
        )
        java = _analyze(
            tmp_path, "    MOVE 123 TO WS-ITEM(CURRENT-IDX).\n    STOP RUN.\n", header
        )
        assert "wsItem[currentIdx - 1] = 123;" in java


# ===========================================================================
# Item N: Stage 31 DISPLAY formatting regression (scalar, non-OCCURS)
# ===========================================================================


class TestStage31FormattingRegression:
    def test_integer_zero_padding_unaffected(self, tmp_path: Path) -> None:
        header = "01 WS-COUNT PIC 9(3) VALUE 5.\n"
        java = _analyze(tmp_path, "    DISPLAY WS-COUNT.\n    STOP RUN.\n", header)
        assert 'System.out.println(String.format("%03d", wsCount));' in java

    def test_decimal_zero_padding_unaffected(self, tmp_path: Path) -> None:
        header = "01 WS-AMOUNT PIC 9(5)V99 VALUE 12.5.\n"
        java = _analyze(tmp_path, "    DISPLAY WS-AMOUNT.\n    STOP RUN.\n", header)
        assert 'String.format("%07d"' in java

    def test_signed_field_stays_unformatted(self, tmp_path: Path) -> None:
        header = "01 WS-DELTA PIC S9(3) VALUE -5.\n"
        java = _analyze(tmp_path, "    DISPLAY WS-DELTA.\n    STOP RUN.\n", header)
        assert "System.out.println(wsDelta);" in java

    def test_alphanumeric_space_padding_unaffected(self, tmp_path: Path) -> None:
        header = "01 WS-CODE PIC X(5) VALUE 'AB'.\n"
        java = _analyze(tmp_path, "    DISPLAY WS-CODE.\n    STOP RUN.\n", header)
        assert 'System.out.println(String.format("%-5s", wsCode));' in java


# ===========================================================================
# Scalar / whole-program regression -- a plain program's Java is untouched
# ===========================================================================


class TestScalarRegression:
    def test_plain_program_generates_no_array_syntax(self, tmp_path: Path) -> None:
        header = "01 WS-A PIC 9(3).\n01 WS-B PIC X(5).\n"
        java = _analyze(
            tmp_path,
            "    MOVE 5 TO WS-A.\n"
            "    MOVE 'HI' TO WS-B.\n"
            "    IF WS-A > 0\n"
            "        DISPLAY WS-B\n"
            "    END-IF.\n    STOP RUN.\n",
            header,
        )
        # "String[] args" (the main() signature) legitimately contains
        # brackets; exclude it and check only the field declarations + body.
        relevant = "\n".join(
            line for line in java.splitlines() if "String[] args" not in line
        )
        assert "[" not in relevant
        assert "]" not in relevant

    def test_group_program_without_occurs_is_unaffected(self, tmp_path: Path) -> None:
        """A group item with no OCCURS anywhere in the record is completely
        unaffected by Stage 33 (matches pre-#stage32/#33 output)."""
        header = "01 WS-REC.\n   05 WS-FIRST PIC X(5).\n   05 WS-SECOND PIC 9(3).\n"
        java = _analyze(tmp_path, "    MOVE 5 TO WS-SECOND.\n    STOP RUN.\n", header)
        relevant = "\n".join(
            line for line in java.splitlines() if "String[] args" not in line
        )
        assert "[" not in relevant


# ===========================================================================
# Multiple independent subscripted references in one program
# ===========================================================================


class TestMultipleIndependentSubscripts:
    def test_two_different_elements_of_the_same_array(self, tmp_path: Path) -> None:
        java = _analyze(
            tmp_path,
            "    MOVE 111 TO WS-ITEM(1).\n"
            "    MOVE 222 TO WS-ITEM(3).\n"
            "    MOVE WS-ITEM(1) TO WS-TOTAL.\n"
            "    STOP RUN.\n",
            _TABLE_HEADER,
        )
        assert "wsItem[0] = 111;" in java
        assert "wsItem[2] = 222;" in java
        assert "wsTotal = wsItem[0];" in java


# ===========================================================================
# Real-corpus-shaped regression: group-level OCCURS with plain children
# ===========================================================================


class TestGroupOccursWithChildrenEndToEnd:
    """Mirrors the actual shape used by t_order_hierarchy/t_table_indexed:
    a GROUP declares OCCURS, its elementary children do not."""

    _HEADER = (
        "01 PO-LINE-ITEMS.\n"
        "   05 LINE-ITEM OCCURS 5 TIMES.\n"
        "      10 SKU-ID PIC X(8).\n"
        "      10 QUANTITY-ORDERED PIC 9(4).\n"
    )

    def test_child_field_becomes_an_array(self, tmp_path: Path) -> None:
        java = _analyze(tmp_path, "    STOP RUN.\n", self._HEADER)
        assert "private String[] skuId = new String[5];" in java
        assert "private int[] quantityOrdered = new int[5];" in java

    def test_literal_subscripted_move_to_child_compiles_conceptually(
        self, tmp_path: Path
    ) -> None:
        java = _analyze(
            tmp_path,
            "    MOVE 'SKU-001' TO SKU-ID(1).\n    STOP RUN.\n",
            self._HEADER,
        )
        assert 'skuId[0] = "SKU-001";' in java

    def test_group_itself_stays_scalar(self, tmp_path: Path) -> None:
        java = _analyze(tmp_path, "    STOP RUN.\n", self._HEADER)
        assert "private String lineItem;" in java
