"""
Tests for AST serialization.

Coverage:
    - representative AST nodes
    - nested structures
    - statement ordering
    - source locations
    - primitive values
    - deterministic output
    - JSON-safe result
"""

from __future__ import annotations

from typing import Any

from app.analysis.serializers.ast import serialize_ast
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
    CallStatementNode,
    DisplayStatementNode,
    IfStatementNode,
    MoveStatementNode,
    PerformUntilStatementNode,
    StopRunStatementNode,
)
from app.parser.ast.working_storage import WorkingStorageSectionNode
from app.parser.lexer.position import Position
from app.parser.semantic.diagnostics import SemanticSeverity

_POS = Position(line=1, column=1, offset=0, filename="test.cbl")


def _stmt(node_cls, **kwargs):
    start_position = kwargs.pop("start_position", _POS)
    end_position = kwargs.pop("end_position", _POS)
    return node_cls(start_position=start_position, end_position=end_position, **kwargs)


class TestASTSerialization:
    def test_position_serialization(self) -> None:
        data = serialize_ast(_POS)
        assert data == {
            "type": "Position",
            "line": 1,
            "column": 1,
            "offset": 0,
            "filename": "test.cbl",
        }

    def test_none_preserved(self) -> None:
        assert serialize_ast(None) is None

    def test_primitive_passthrough(self) -> None:
        assert serialize_ast("hello") == "hello"
        assert serialize_ast(42) == 42
        assert serialize_ast(3.14) == 3.14
        assert serialize_ast(True) is True

    def test_program_node(self) -> None:
        ident = IdentificationDivisionNode(
            start_position=_POS,
            end_position=_POS,
            program_id=ProgramIdClauseNode(
                start_position=_POS, end_position=_POS, value="HELLO"
            ),
        )
        data_div = DataDivisionNode(
            start_position=_POS,
            end_position=_POS,
            working_storage=WorkingStorageSectionNode(
                start_position=_POS,
                end_position=_POS,
                items=(
                    ElementaryItemNode(
                        start_position=_POS,
                        end_position=_POS,
                        level=1,
                        name="WS-GREETING",
                        picture="X(12)",
                    ),
                ),
            ),
        )
        proc_div = ProcedureDivisionNode(
            start_position=_POS,
            end_position=_POS,
            paragraphs=(
                ParagraphNode(
                    start_position=_POS,
                    end_position=_POS,
                    name="MAIN",
                    statements=(
                        _stmt(DisplayStatementNode, operand='"HELLO WORLD"'),
                        _stmt(StopRunStatementNode),
                    ),
                ),
            ),
        )
        program = ProgramNode(
            start_position=_POS,
            end_position=_POS,
            identification_division=ident,
            data_division=data_div,
            procedure_division=proc_div,
        )

        data = serialize_ast(program)
        assert data["type"] == "ProgramNode"
        assert data["identification_division"]["type"] == "IdentificationDivisionNode"
        assert data["identification_division"]["program_id"]["value"] == "HELLO"
        assert (
            data["data_division"]["working_storage"]["items"][0]["name"]
            == "WS-GREETING"
        )
        assert data["procedure_division"]["paragraphs"][0]["name"] == "MAIN"
        assert (
            data["procedure_division"]["paragraphs"][0]["statements"][0]["type"]
            == "DisplayStatementNode"
        )

    def test_statement_ordering_preserved(self) -> None:
        statements = (
            _stmt(MoveStatementNode, source="1", target="WS-COUNT"),
            _stmt(DisplayStatementNode, operand="WS-COUNT"),
            _stmt(StopRunStatementNode),
        )
        para = ParagraphNode(
            start_position=_POS,
            end_position=_POS,
            name="MAIN",
            statements=statements,
        )
        data = serialize_ast(para)
        types = [s["type"] for s in data["statements"]]
        assert types == [
            "MoveStatementNode",
            "DisplayStatementNode",
            "StopRunStatementNode",
        ]

    def test_source_location_preserved(self) -> None:
        pos = Position(line=10, column=4, offset=200, filename="prog.cbl")
        node = _stmt(
            DisplayStatementNode,
            operand='"HELLO"',
            start_position=pos,
            end_position=pos,
        )
        data = serialize_ast(node)
        assert data["start_position"] == {
            "type": "Position",
            "line": 10,
            "column": 4,
            "offset": 200,
            "filename": "prog.cbl",
        }
        assert data["end_position"] == data["start_position"]

    def test_group_item_with_children(self) -> None:
        child = ElementaryItemNode(
            start_position=_POS,
            end_position=_POS,
            level=5,
            name="WS-ID",
            picture="9(5)",
        )
        group = GroupItemNode(
            start_position=_POS,
            end_position=_POS,
            level=1,
            name="CUSTOMER-REC",
            children=(child,),
        )
        data = serialize_ast(group)
        assert data["type"] == "GroupItemNode"
        assert data["children"][0]["type"] == "ElementaryItemNode"
        assert data["children"][0]["name"] == "WS-ID"

    def test_condition_name_node(self) -> None:
        node = ConditionNameNode(
            start_position=_POS,
            end_position=_POS,
            level=88,
            name="END-OF-FILE",
            value="'Y'",
        )
        data = serialize_ast(node)
        assert data["type"] == "ConditionNameNode"
        assert data["level"] == 88
        assert data["value"] == "'Y'"

    def test_if_statement_with_branches(self) -> None:
        if_stmt = IfStatementNode(
            start_position=_POS,
            end_position=_POS,
            condition_left="WS-COUNT",
            condition_operator=">",
            condition_right="0",
            then_statements=(_stmt(DisplayStatementNode, operand="POSITIVE"),),
            else_statements=(_stmt(DisplayStatementNode, operand="NEGATIVE"),),
        )
        data = serialize_ast(if_stmt)
        assert data["then_statements"][0]["type"] == "DisplayStatementNode"
        assert data["else_statements"][0]["type"] == "DisplayStatementNode"

    def test_perform_until_statement(self) -> None:
        stmt = PerformUntilStatementNode(
            start_position=_POS,
            end_position=_POS,
            condition_left="WS-I",
            condition_operator="<",
            condition_right="10",
            statements=(_stmt(MoveStatementNode, source="1", target="WS-I"),),
        )
        data = serialize_ast(stmt)
        assert data["condition_operator"] == "<"
        assert data["statements"][0]["type"] == "MoveStatementNode"

    def test_call_statement_with_arguments(self) -> None:
        stmt = CallStatementNode(
            start_position=_POS,
            end_position=_POS,
            target="CALCULATE-TOTAL",
            arguments=("WS-ID", "WS-AMOUNT"),
        )
        data = serialize_ast(stmt)
        assert data["target"] == "CALCULATE-TOTAL"
        assert data["arguments"] == ["WS-ID", "WS-AMOUNT"]

    def test_deterministic_output(self) -> None:
        node1 = _stmt(MoveStatementNode, source="1", target="WS-COUNT")
        node2 = _stmt(MoveStatementNode, source="1", target="WS-COUNT")
        assert serialize_ast(node1) == serialize_ast(node2)

    def test_json_safe_result(self) -> None:
        node = _stmt(DisplayStatementNode, operand='"HELLO"')
        data = serialize_ast(node)
        _assert_json_safe(data)

    def test_nested_dict_serialization(self) -> None:
        data = serialize_ast(
            {
                "program": "HELLO",
                "items": [1, 2, 3],
                "nested": {
                    "flag": True,
                    "names": ["A", "B"],
                },
            }
        )
        assert data["program"] == "HELLO"
        assert data["items"] == [1, 2, 3]
        assert data["nested"]["flag"] is True
        assert data["nested"]["names"] == ["A", "B"]
        _assert_json_safe(data)

    def test_dict_with_enum_and_dataclass(self) -> None:
        pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        data = serialize_ast(
            {
                "kind": SemanticSeverity.ERROR,
                "position": pos,
                "meta": {
                    "line": 10,
                },
            }
        )
        assert data["kind"] == "error"
        assert data["position"]["type"] == "Position"
        assert data["meta"]["line"] == 10
        _assert_json_safe(data)


def _assert_json_safe(value: Any) -> None:
    """Recursively verify that *value* contains only JSON-native types."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_json_safe(item)
        return
    if isinstance(value, dict):
        for v in value.values():
            _assert_json_safe(v)
        return
    raise TypeError(f"Non-JSON-safe value: {type(value).__name__}")
