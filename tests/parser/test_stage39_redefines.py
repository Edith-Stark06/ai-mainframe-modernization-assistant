"""
Stage 39 — ``REDEFINES base-name`` clause parsing.

Purpose:
    Before this stage, ``REDEFINES`` was lumped into
    ``_UNMODELLED_CLAUSE_WORDS`` and opaquely skipped by
    ``_skip_one_unmodelled_clause`` -- the base item's own name was
    discarded along with the keyword, and a ``SYN200`` "not represented
    in the AST" diagnostic was recorded. ``_parse_elementary_or_group``
    now recognises ``REDEFINES base-name`` specifically (mirroring how
    ``OCCURS`` was already pulled out of the same opaque-skip set at
    task #stage32) and captures the uppercased base name on
    :attr:`~app.parser.ast.data_items.ElementaryItemNode.redefines` /
    :attr:`~app.parser.ast.data_items.GroupItemNode.redefines`. Since the
    clause's entire grammar is now represented, no ``SYN200`` is recorded
    for it any more.

    Deriving a redefining group's children's actual *values* from the
    base item's own ``VALUE`` literal is a separate, backend-layer
    concern -- see ``tests/backend/test_stage39_redefines_java.py``.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.service import AnalysisService
from app.parser.ast.data_items import ElementaryItemNode, GroupItemNode
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.program_parser import ProgramParser

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nDATA DIVISION.\nWORKING-STORAGE SECTION.\n"


def _items(body: str):
    source = _ID + body + "PROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n"
    tokens = CobolLexer().tokenize(source, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    return program.data_division.working_storage.items


def _by_name(items) -> dict:
    return {item.name: item for item in items}


class TestRealCorpusShape:
    """t_policy_redefines.cbl's exact real shape: a group redefining a
    plain elementary PIC X item."""

    def test_group_redefines_captures_base_name(self) -> None:
        items = _items(
            "01 POLICY-RAW-PAYLOAD PIC X(10) VALUE 'ABCDEFGHIJ'.\n"
            "01 AUTO-PAYLOAD REDEFINES POLICY-RAW-PAYLOAD.\n"
            "   05 VEHICLE-VIN PIC X(5).\n"
            "   05 BODY-STYLE PIC X(5).\n"
        )
        by_name = _by_name(items)
        auto = by_name["AUTO-PAYLOAD"]
        assert isinstance(auto, GroupItemNode)
        assert auto.redefines == "POLICY-RAW-PAYLOAD"

    def test_no_syn200_for_redefines_anymore(self) -> None:
        source = (
            _ID
            + "01 POLICY-RAW-PAYLOAD PIC X(10) VALUE 'ABCDEFGHIJ'.\n"
            + "01 AUTO-PAYLOAD REDEFINES POLICY-RAW-PAYLOAD.\n"
            + "   05 VEHICLE-VIN PIC X(5).\n"
            + "   05 BODY-STYLE PIC X(5).\n"
            + "PROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n"
        )
        tokens = CobolLexer().tokenize(source, filename="t.cbl")
        result = ProgramParser().parse_with_diagnostics(tokens)
        redefines_diags = [
            d for d in result.diagnostics if "REDEFINES" in d.message.upper()
        ]
        assert redefines_diags == []

    def test_base_item_itself_unaffected(self) -> None:
        items = _items(
            "01 POLICY-RAW-PAYLOAD PIC X(10) VALUE 'ABCDEFGHIJ'.\n"
            "01 AUTO-PAYLOAD REDEFINES POLICY-RAW-PAYLOAD.\n"
            "   05 VEHICLE-VIN PIC X(5).\n"
            "   05 BODY-STYLE PIC X(5).\n"
        )
        by_name = _by_name(items)
        base = by_name["POLICY-RAW-PAYLOAD"]
        assert isinstance(base, ElementaryItemNode)
        assert base.redefines is None
        assert base.value == "'ABCDEFGHIJ'"

    def test_children_of_redefining_group_are_plain_elementary_items(
        self,
    ) -> None:
        items = _items(
            "01 POLICY-RAW-PAYLOAD PIC X(10) VALUE 'ABCDEFGHIJ'.\n"
            "01 AUTO-PAYLOAD REDEFINES POLICY-RAW-PAYLOAD.\n"
            "   05 VEHICLE-VIN PIC X(5).\n"
            "   05 BODY-STYLE PIC X(5).\n"
        )
        by_name = _by_name(items)
        vin = by_name["VEHICLE-VIN"]
        assert isinstance(vin, ElementaryItemNode)
        assert vin.redefines is None
        assert vin.picture == "X(5)"


class TestRedefinesWithOccursAndValueCombinations:
    """REDEFINES must compose correctly regardless of clause order,
    mirroring OCCURS's own established before/after-VALUE flexibility."""

    def test_redefines_before_pic(self) -> None:
        items = _items(
            "01 WS-A PIC X(5) VALUE 'HELLO'.\n" "01 WS-B REDEFINES WS-A PIC X(5).\n"
        )
        by_name = _by_name(items)
        assert by_name["WS-B"].redefines == "WS-A"
        assert by_name["WS-B"].picture == "X(5)"

    def test_redefines_after_pic(self) -> None:
        items = _items(
            "01 WS-A PIC X(5) VALUE 'HELLO'.\n" "01 WS-B PIC X(5) REDEFINES WS-A.\n"
        )
        by_name = _by_name(items)
        assert by_name["WS-B"].redefines == "WS-A"
        assert by_name["WS-B"].picture == "X(5)"


class TestMalformedRedefines:
    def test_redefines_with_no_base_name_does_not_crash(self) -> None:
        """A malformed REDEFINES (no identifier follows) leaves
        ``redefines`` unset rather than raising -- nothing is guessed."""
        items = _items("01 WS-A PIC X(5) VALUE 'HELLO'.\n01 WS-B REDEFINES.\n")
        by_name = _by_name(items)
        assert by_name["WS-B"].redefines is None


class TestRegressionOtherClauses:
    """Every other data-item clause path stays unaffected."""

    def test_occurs_unaffected(self) -> None:
        items = _items("01 WS-TABLE.\n   05 WS-ITEM PIC 9(3) OCCURS 4.\n")
        by_name = _by_name(items)
        assert by_name["WS-ITEM"].occurs == 4
        assert by_name["WS-ITEM"].redefines is None

    def test_comp3_now_represented_not_reported_unsupported(self) -> None:
        """task #stage41: ``COMP-3``/``USAGE`` now has a real parser/AST
        field (:attr:`~app.parser.ast.data_items.ElementaryItemNode.usage`),
        so this REDEFINES-fix regression guard's original claim ("COMP-3
        stays reported unsupported, unaffected by the REDEFINES fix") no
        longer holds -- updated to its new true value: COMP-3 is
        represented (``usage == "COMP-3"``) with zero diagnostics,
        confirming task #stage39's REDEFINES fix still does not disturb
        USAGE clause handling either way."""
        source = (
            _ID
            + "01 WS-AMOUNT PIC 9(7)V99 COMP-3.\n"
            + "PROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n"
        )
        tokens = CobolLexer().tokenize(source, filename="t.cbl")
        result = ProgramParser().parse_with_diagnostics(tokens)
        comp3_diags = [d for d in result.diagnostics if "COMP-3" in d.message.upper()]
        assert comp3_diags == []
        items = _by_name(result.program.data_division.working_storage.items)
        assert items["WS-AMOUNT"].usage == "COMP-3"

    def test_plain_elementary_item_unaffected(self) -> None:
        items = _items("01 WS-COUNT PIC 9(3) VALUE 0.\n")
        assert items[0].redefines is None
        assert items[0].value == "0"


class TestRealCorpusIntegration:
    """Direct integration against the real, unmodified corpus source."""

    _PATH = Path("data/sources/phase6-v2/policy_redefines.cbl")

    def test_no_syn200_diagnostics(self) -> None:
        result = AnalysisService().analyze_file(self._PATH)
        codes = {d.code for d in result.syntax_diagnostics}
        assert "SYN200" not in codes

    def test_both_redefines_groups_captured(self) -> None:
        result = AnalysisService().analyze_file(self._PATH)
        by_name = _by_name(result.ast.data_division.working_storage.items)
        assert by_name["AUTO-PAYLOAD"].redefines == "POLICY-RAW-PAYLOAD"
        assert by_name["LIFE-PAYLOAD"].redefines == "POLICY-RAW-PAYLOAD"
