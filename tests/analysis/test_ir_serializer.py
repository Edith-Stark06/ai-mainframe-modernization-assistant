"""
Tests for IR serialization.

Coverage:
    - IRProgram
    - nested module/function/block structure
    - instruction serialization
    - instruction ordering
    - representative instructions
    - deterministic output
    - JSON-safe result
"""

from __future__ import annotations

from typing import Any

from app.analysis.serializers.ir import serialize_ir
from app.ir.blocks import IRBasicBlock
from app.ir.instructions import (
    IRAccept,
    IRAdd,
    IRAssignment,
    IRCall,
    IRConditionalBranch,
    IRDisplay,
    IRDivide,
    IRElse,
    IREndIf,
    IREndPerform,
    IRIf,
    IRJump,
    IRMove,
    IRMultiply,
    IRPerformUntil,
    IRReturn,
    IRSubtract,
)
from app.ir.program import IRFunction, IRModule, IRProgram
from app.parser.lexer.position import Position

_POS = Position(line=1, column=1, offset=0, filename="test.cbl")


def _instr(cls, **kwargs):
    return cls(**kwargs)


class TestIRSerialization:
    def test_program_serialization(self) -> None:
        prog = IRProgram(name="HELLO")
        data = serialize_ir(prog)
        assert data["type"] == "IRProgram"
        assert data["name"] == "HELLO"
        assert data["modules"] == []

    def test_nested_structure(self) -> None:
        block = IRBasicBlock(
            label="entry",
            instructions=(
                _instr(IRAssignment, value="0"),
                _instr(IRMove, source="WS-IN", result="WS-OUT"),
                _instr(IRReturn),
            ),
        )
        func = IRFunction(name="MAIN", blocks=(block,))
        module = IRModule(name="HELLO", functions=(func,))
        prog = IRProgram(name="HELLO", modules=(module,))

        data = serialize_ir(prog)
        assert data["type"] == "IRProgram"
        assert data["modules"][0]["type"] == "IRModule"
        assert data["modules"][0]["functions"][0]["type"] == "IRFunction"
        assert data["modules"][0]["functions"][0]["blocks"][0]["type"] == "IRBasicBlock"
        assert data["modules"][0]["functions"][0]["blocks"][0]["label"] == "entry"

    def test_instruction_ordering_preserved(self) -> None:
        instructions = (
            _instr(IRMove, source="WS-SRC", result="WS-TARGET"),
            _instr(IRDisplay, operand="WS-TARGET"),
            _instr(IRReturn),
        )
        block = IRBasicBlock(label="entry", instructions=instructions)
        data = serialize_ir(block)
        types = [instr["type"] for instr in data["instructions"]]
        assert types == ["IRMove", "IRDisplay", "IRReturn"]

    def test_control_flow_instructions(self) -> None:
        instructions = (
            _instr(IRIf, left="WS-COUNT", operator=">", right="0"),
            _instr(IRElse),
            _instr(IREndIf),
            _instr(IRPerformUntil, left="WS-I", operator="<", right="10"),
            _instr(IREndPerform),
        )
        block = IRBasicBlock(label="main", instructions=instructions)
        data = serialize_ir(block)
        types = [instr["type"] for instr in data["instructions"]]
        assert types == [
            "IRIf",
            "IRElse",
            "IREndIf",
            "IRPerformUntil",
            "IREndPerform",
        ]

    def test_arithmetic_instructions(self) -> None:
        instructions = (
            _instr(IRAdd, left="WS-A", right="WS-B"),
            _instr(IRSubtract, left="WS-A", right="WS-B"),
            _instr(IRMultiply, left="WS-A", right="WS-B"),
            _instr(IRDivide, left="WS-A", right="WS-B"),
        )
        block = IRBasicBlock(label="arith", instructions=instructions)
        data = serialize_ir(block)
        left_vals = [instr["left"] for instr in data["instructions"]]
        assert left_vals == ["WS-A", "WS-A", "WS-A", "WS-A"]

    def test_call_and_branch_instructions(self) -> None:
        instructions = (
            _instr(IRCall, target="PROCESS-RECORD", args=("EMP-ID",), result="RETVAL"),
            _instr(
                IRConditionalBranch,
                condition="WS-FLAG",
                then_target="HANDLER",
                else_target="SKIP",
            ),
            _instr(IRJump, target="END"),
        )
        block = IRBasicBlock(label="flow", instructions=instructions)
        data = serialize_ir(block)
        assert data["instructions"][0]["target"] == "PROCESS-RECORD"
        assert data["instructions"][0]["args"] == ["EMP-ID"]
        assert data["instructions"][1]["then_target"] == "HANDLER"
        assert data["instructions"][2]["target"] == "END"

    def test_display_accept_instructions(self) -> None:
        instructions = (
            _instr(IRDisplay, operand='"HELLO"'),
            _instr(IRAccept, result="WS-INPUT"),
        )
        block = IRBasicBlock(label="io", instructions=instructions)
        data = serialize_ir(block)
        assert data["instructions"][0]["operand"] == '"HELLO"'
        assert data["instructions"][1]["result"] == "WS-INPUT"

    def test_deterministic_output(self) -> None:
        block = IRBasicBlock(
            label="entry",
            instructions=(_instr(IRAssignment, value="0"),),
        )
        func = IRFunction(name="MAIN", blocks=(block,))
        module = IRModule(name="HELLO", functions=(func,))
        prog1 = IRProgram(name="HELLO", modules=(module,))
        prog2 = IRProgram(name="HELLO", modules=(module,))
        assert serialize_ir(prog1) == serialize_ir(prog2)

    def test_json_safe_result(self) -> None:
        block = IRBasicBlock(
            label="entry",
            instructions=(_instr(IRMove, source="A", result="B"),),
        )
        data = serialize_ir(block)
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
