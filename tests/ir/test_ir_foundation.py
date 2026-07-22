"""
Comprehensive tests for TASK-024: Intermediate Representation (IR) Foundation.

Purpose:
    Verify that all IR node types are correctly constructed, immutable, and
    hashable; that the instruction hierarchy is correct; that the visitor
    framework dispatches correctly; that the traversal driver visits nodes in
    the right order; and that IRBuilder is correctly initialised.

Coverage:
    IRNodeKind enum:
        - All five values present and correct.
        - Unique values.

    IRNode base (via concrete subclasses):
        - Is abstract — cannot be instantiated directly.
        - kind field is set correctly on all subclasses.
        - name field defaults to "".

    IRBasicBlock:
        - Constructs with default empty instructions tuple.
        - label stored correctly.
        - name synced to label via __post_init__.
        - len() == number of instructions.
        - kind == IRNodeKind.BASIC_BLOCK.
        - Frozen — cannot mutate.
        - Hashable.
        - Equality on same values.
        - accept() dispatches to visitor.visit_basic_block().

    IRInstruction (via concrete subclasses):
        - kind == IRNodeKind.INSTRUCTION on all instruction types.
        - result defaults to "".
        - comment defaults to "".
        - Frozen — cannot mutate.
        - Hashable.

    IRAssignment:
        - value field stored.
        - accept() calls visitor.visit_assignment().
        - Equality.

    IRMove:
        - source field stored.
        - accept() calls visitor.visit_move().
        - Equality.

    IRCall:
        - target field stored.
        - args defaults to empty tuple.
        - args stored when provided.
        - accept() calls visitor.visit_call().
        - Equality.

    IRReturn:
        - operand defaults to "".
        - operand stored when provided.
        - accept() calls visitor.visit_return().
        - Equality.

    IRBranch:
        - target field stored.
        - condition defaults to "".
        - condition stored when provided.
        - accept() calls visitor.visit_branch().
        - Unconditional branch (condition="").
        - Conditional branch (condition set).
        - Equality.

    IRFunction:
        - name stored.
        - blocks defaults to empty tuple.
        - params defaults to empty tuple.
        - return_type defaults to "void".
        - len() == number of blocks.
        - kind == IRNodeKind.FUNCTION.
        - Frozen — cannot mutate.
        - Hashable.
        - accept() dispatches to visitor.visit_function().

    IRModule:
        - name stored.
        - functions defaults to empty tuple.
        - len() == number of functions.
        - kind == IRNodeKind.MODULE.
        - Frozen — cannot mutate.
        - accept() dispatches to visitor.visit_module().

    IRProgram:
        - name stored.
        - modules defaults to empty tuple.
        - len() == number of modules.
        - kind == IRNodeKind.PROGRAM.
        - Frozen — cannot mutate.
        - accept() dispatches to visitor.visit_program().

    IRVisitor (no-op base):
        - All visit_* hooks return None by default.
        - Subclass can override individual hooks.

    traverse_ir():
        - Visits program, modules, functions, blocks, instructions in order.
        - All five instruction types are dispatched to correct hooks.
        - Empty program (no modules) — no crash.
        - Empty module (no functions) — no crash.
        - Empty function (no blocks) — no crash.
        - Empty block (no instructions) — no crash.
        - Visit order is top-down, pre-order.
        - accept() fallback: unknown visitor attribute → None.

    IRBuilder:
        - Accepts a valid SemanticContext.
        - Raises TypeError for non-SemanticContext input.
        - context property returns the supplied context.
        - build() returns IRProgram.
        - build() returns empty IRProgram (scaffold).
        - current_program() delegates to build().
        - Logs warning when context has errors.
        - Reusable — build() callable multiple times.

    Public API exports:
        - All types exported from app.ir package.

Non-responsibilities:
    - Parser/lexer behaviour.
    - AST-to-IR translation.
    - Java generation.

Dependencies:
    - :mod:`app.ir`                      — full public API.
    - :mod:`app.parser.semantic.context` — SemanticContext, SymbolTable.
    - :mod:`pytest`                      — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pytest

from app.ir import (
    IRAssignment,
    IRBasicBlock,
    IRBuilder,
    IRCall,
    IRConditionalBranch,
    IRFunction,
    IRInstruction,
    IRJump,
    IRModule,
    IRMove,
    IRNode,
    IRNodeKind,
    IRProgram,
    IRReturn,
    IRVisitor,
    traverse_ir,
)
from app.parser.semantic.context import SemanticContext, SymbolTable

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_ctx() -> SemanticContext:
    return SemanticContext(symbol_table=SymbolTable(), diagnostics=[])


def _simple_program(name: str = "PROG") -> IRProgram:
    """Build a minimal fully-populated IRProgram for traversal tests."""
    assign = IRAssignment(result="WS-COUNT", value="0")
    move = IRMove(result="WS-OUT", source="WS-IN")
    call = IRCall(target="PROCESS-RECORD", args=("ARG1",))
    ret = IRReturn(operand="WS-RESULT")
    jump = IRJump(target="EOF-HANDLER")
    bb = IRBasicBlock(label="entry", instructions=(assign, move, call, ret, jump))
    fn = IRFunction(name="MAIN", blocks=(bb,))
    mod = IRModule(name="MODULE-A", functions=(fn,))
    return IRProgram(name=name, modules=(mod,))


# ===========================================================================
# IRNodeKind enum
# ===========================================================================


class TestIRNodeKind:
    """IRNodeKind enum completeness and values."""

    def test_program_value(self) -> None:
        assert IRNodeKind.PROGRAM.value == "program"

    def test_module_value(self) -> None:
        assert IRNodeKind.MODULE.value == "module"

    def test_function_value(self) -> None:
        assert IRNodeKind.FUNCTION.value == "function"

    def test_basic_block_value(self) -> None:
        assert IRNodeKind.BASIC_BLOCK.value == "basic_block"

    def test_instruction_value(self) -> None:
        assert IRNodeKind.INSTRUCTION.value == "instruction"

    def test_all_five_members(self) -> None:
        assert len(list(IRNodeKind)) == 5

    def test_unique_values(self) -> None:
        values = [k.value for k in IRNodeKind]
        assert len(values) == len(set(values))


# ===========================================================================
# IRNode abstract base
# ===========================================================================


class TestIRNodeAbstract:
    """IRNode cannot be instantiated directly (it is abstract)."""

    def test_cannot_instantiate_ir_node(self) -> None:
        with pytest.raises(TypeError):
            IRNode(kind=IRNodeKind.PROGRAM)  # type: ignore[abstract]


# ===========================================================================
# IRBasicBlock
# ===========================================================================


class TestIRBasicBlock:
    """IRBasicBlock construction, immutability, and visitor dispatch."""

    def test_default_empty_instructions(self) -> None:
        bb = IRBasicBlock(label="entry")
        assert bb.instructions == ()

    def test_label_stored(self) -> None:
        bb = IRBasicBlock(label="MAIN-BODY")
        assert bb.label == "MAIN-BODY"

    def test_name_synced_to_label(self) -> None:
        bb = IRBasicBlock(label="LOOP-TOP")
        assert bb.name == "LOOP-TOP"

    def test_len_empty(self) -> None:
        assert len(IRBasicBlock(label="x")) == 0

    def test_len_with_instructions(self) -> None:
        bb = IRBasicBlock(label="x", instructions=(IRReturn(), IRReturn()))
        assert len(bb) == 2

    def test_kind_is_basic_block(self) -> None:
        assert IRBasicBlock(label="x").kind is IRNodeKind.BASIC_BLOCK

    def test_frozen_cannot_mutate(self) -> None:
        bb = IRBasicBlock(label="x")
        with pytest.raises((AttributeError, TypeError)):
            bb.label = "y"  # type: ignore[misc]

    def test_hashable(self) -> None:
        bb1 = IRBasicBlock(label="x")
        bb2 = IRBasicBlock(label="x")
        s = {bb1, bb2}
        assert len(s) == 1

    def test_equality(self) -> None:
        bb1 = IRBasicBlock(label="x", instructions=(IRReturn(),))
        bb2 = IRBasicBlock(label="x", instructions=(IRReturn(),))
        assert bb1 == bb2

    def test_accept_dispatches_to_visitor(self) -> None:
        visited = []

        class V(IRVisitor):
            def visit_basic_block(self, node: IRBasicBlock) -> None:
                visited.append(node)

        bb = IRBasicBlock(label="x")
        bb.accept(V())
        assert bb in visited

    def test_accept_noop_if_no_method(self) -> None:
        bb = IRBasicBlock(label="x")
        result = bb.accept(object())
        assert result is None


# ===========================================================================
# IRInstruction (abstract)
# ===========================================================================


class TestIRInstructionAbstract:
    """IRInstruction cannot be instantiated directly."""

    def test_cannot_instantiate_ir_instruction(self) -> None:
        with pytest.raises(TypeError):
            IRInstruction()  # type: ignore[abstract]


# ===========================================================================
# IRAssignment
# ===========================================================================


class TestIRAssignment:
    """IRAssignment construction, immutability, visitor dispatch."""

    def test_kind_is_instruction(self) -> None:
        assert IRAssignment(result="X", value="0").kind is IRNodeKind.INSTRUCTION

    def test_result_stored(self) -> None:
        assert IRAssignment(result="WS-COUNT", value="0").result == "WS-COUNT"

    def test_value_stored(self) -> None:
        assert IRAssignment(result="WS-COUNT", value="42").value == "42"

    def test_defaults(self) -> None:
        a = IRAssignment()
        assert a.result == ""
        assert a.value == ""
        assert a.comment == ""

    def test_frozen(self) -> None:
        a = IRAssignment(result="X", value="0")
        with pytest.raises((AttributeError, TypeError)):
            a.value = "1"  # type: ignore[misc]

    def test_hashable(self) -> None:
        s = {IRAssignment(result="X", value="0"), IRAssignment(result="X", value="0")}
        assert len(s) == 1

    def test_equality(self) -> None:
        assert IRAssignment(result="X", value="0") == IRAssignment(
            result="X", value="0"
        )

    def test_accept_dispatches(self) -> None:
        called = []

        class V(IRVisitor):
            def visit_assignment(self, node: IRAssignment) -> None:
                called.append(node)

        a = IRAssignment(result="X", value="1")
        a.accept(V())
        assert a in called

    def test_accept_no_method_returns_none(self) -> None:
        assert IRAssignment().accept(object()) is None


# ===========================================================================
# IRMove
# ===========================================================================


class TestIRMove:
    """IRMove construction, immutability, visitor dispatch."""

    def test_result_stored(self) -> None:
        assert IRMove(result="WS-TGT", source="WS-SRC").result == "WS-TGT"

    def test_source_stored(self) -> None:
        assert IRMove(result="WS-TGT", source="WS-SRC").source == "WS-SRC"

    def test_defaults(self) -> None:
        mv = IRMove()
        assert mv.result == ""
        assert mv.source == ""

    def test_kind_is_instruction(self) -> None:
        assert IRMove().kind is IRNodeKind.INSTRUCTION

    def test_frozen(self) -> None:
        mv = IRMove(result="X", source="Y")
        with pytest.raises((AttributeError, TypeError)):
            mv.source = "Z"  # type: ignore[misc]

    def test_hashable(self) -> None:
        s = {IRMove(result="A", source="B"), IRMove(result="A", source="B")}
        assert len(s) == 1

    def test_equality(self) -> None:
        assert IRMove(result="A", source="B") == IRMove(result="A", source="B")

    def test_accept_dispatches(self) -> None:
        called = []

        class V(IRVisitor):
            def visit_move(self, node: IRMove) -> None:
                called.append(node)

        mv = IRMove(result="A", source="B")
        mv.accept(V())
        assert mv in called

    def test_accept_no_method_returns_none(self) -> None:
        assert IRMove().accept(object()) is None


# ===========================================================================
# IRCall
# ===========================================================================


class TestIRCall:
    """IRCall construction, immutability, visitor dispatch."""

    def test_target_stored(self) -> None:
        assert IRCall(target="PROCESS-RECORD").target == "PROCESS-RECORD"

    def test_args_default_empty(self) -> None:
        assert IRCall(target="X").args == ()

    def test_args_stored(self) -> None:
        call = IRCall(target="X", args=("A", "B"))
        assert call.args == ("A", "B")

    def test_result_default_empty(self) -> None:
        assert IRCall(target="X").result == ""

    def test_kind_is_instruction(self) -> None:
        assert IRCall(target="X").kind is IRNodeKind.INSTRUCTION

    def test_frozen(self) -> None:
        call = IRCall(target="X")
        with pytest.raises((AttributeError, TypeError)):
            call.target = "Y"  # type: ignore[misc]

    def test_hashable(self) -> None:
        s = {IRCall(target="X", args=("A",)), IRCall(target="X", args=("A",))}
        assert len(s) == 1

    def test_equality(self) -> None:
        assert IRCall(target="X", args=("A",)) == IRCall(target="X", args=("A",))

    def test_accept_dispatches(self) -> None:
        called = []

        class V(IRVisitor):
            def visit_call(self, node: IRCall) -> None:
                called.append(node)

        call = IRCall(target="X")
        call.accept(V())
        assert call in called

    def test_accept_no_method_returns_none(self) -> None:
        assert IRCall(target="X").accept(object()) is None


# ===========================================================================
# IRReturn
# ===========================================================================


class TestIRReturn:
    """IRReturn construction, immutability, visitor dispatch."""

    def test_operand_default_empty(self) -> None:
        assert IRReturn().operand == ""

    def test_operand_stored(self) -> None:
        assert IRReturn(operand="WS-RESULT").operand == "WS-RESULT"

    def test_result_always_empty(self) -> None:
        assert IRReturn(operand="X").result == ""

    def test_kind_is_instruction(self) -> None:
        assert IRReturn().kind is IRNodeKind.INSTRUCTION

    def test_frozen(self) -> None:
        ret = IRReturn(operand="X")
        with pytest.raises((AttributeError, TypeError)):
            ret.operand = "Y"  # type: ignore[misc]

    def test_hashable(self) -> None:
        s = {IRReturn(operand="X"), IRReturn(operand="X")}
        assert len(s) == 1

    def test_equality(self) -> None:
        assert IRReturn(operand="X") == IRReturn(operand="X")

    def test_accept_dispatches(self) -> None:
        called = []

        class V(IRVisitor):
            def visit_return(self, node: IRReturn) -> None:
                called.append(node)

        ret = IRReturn(operand="X")
        ret.accept(V())
        assert ret in called

    def test_accept_no_method_returns_none(self) -> None:
        assert IRReturn().accept(object()) is None


# ===========================================================================
# IRConditionalBranch and IRJump
# ===========================================================================


class TestBranching:
    """Branching instruction construction and behaviour."""

    def test_conditional_branch(self) -> None:
        cond = IRConditionalBranch(
            condition="WS-FLAG", then_target="TRUE-BLOCK", else_target="FALSE-BLOCK"
        )
        assert cond.condition == "WS-FLAG"
        assert cond.then_target == "TRUE-BLOCK"
        assert cond.else_target == "FALSE-BLOCK"

    def test_jump(self) -> None:
        jmp = IRJump(target="EXIT-BLOCK")
        assert jmp.target == "EXIT-BLOCK"

    def test_kinds(self) -> None:
        assert (
            IRConditionalBranch(condition="C", then_target="T", else_target="F").kind
            is IRNodeKind.INSTRUCTION
        )
        assert IRJump(target="T").kind is IRNodeKind.INSTRUCTION

    def test_hashable(self) -> None:
        s = {
            IRConditionalBranch(condition="WS-EOF", then_target="L1", else_target="L2"),
            IRConditionalBranch(condition="WS-EOF", then_target="L1", else_target="L2"),
        }
        assert len(s) == 1

    def test_accept_dispatches(self) -> None:
        called: list[IRInstruction] = []

        class V(IRVisitor):
            def visit_conditional_branch(self, node: IRConditionalBranch) -> None:
                called.append(node)

            def visit_jump(self, node: IRJump) -> None:
                called.append(node)

        cond = IRConditionalBranch(condition="C", then_target="T", else_target="F")
        jmp = IRJump(target="T")
        cond.accept(V())
        jmp.accept(V())
        assert cond in called
        assert jmp in called


# ===========================================================================
# IRFunction
# ===========================================================================


class TestIRFunction:
    """IRFunction construction, immutability, visitor dispatch."""

    def test_name_stored(self) -> None:
        assert IRFunction(name="MAIN").name == "MAIN"

    def test_blocks_default_empty(self) -> None:
        assert IRFunction(name="X").blocks == ()

    def test_params_default_empty(self) -> None:
        assert IRFunction(name="X").params == ()

    def test_return_type_default_void(self) -> None:
        assert IRFunction(name="X").return_type == "void"

    def test_len_empty(self) -> None:
        assert len(IRFunction(name="X")) == 0

    def test_len_with_blocks(self) -> None:
        bb = IRBasicBlock(label="entry")
        assert len(IRFunction(name="X", blocks=(bb, bb))) == 2

    def test_kind_is_function(self) -> None:
        assert IRFunction(name="X").kind is IRNodeKind.FUNCTION

    def test_frozen(self) -> None:
        fn = IRFunction(name="X")
        with pytest.raises((AttributeError, TypeError)):
            fn.name = "Y"  # type: ignore[misc]

    def test_hashable(self) -> None:
        fn1 = IRFunction(name="X")
        fn2 = IRFunction(name="X")
        assert {fn1, fn2} == {fn1}

    def test_accept_dispatches(self) -> None:
        called = []

        class V(IRVisitor):
            def visit_function(self, node: IRFunction) -> None:
                called.append(node)

        fn = IRFunction(name="X")
        fn.accept(V())
        assert fn in called

    def test_accept_no_method_returns_none(self) -> None:
        assert IRFunction(name="X").accept(object()) is None


# ===========================================================================
# IRModule
# ===========================================================================


class TestIRModule:
    """IRModule construction, immutability, visitor dispatch."""

    def test_name_stored(self) -> None:
        assert IRModule(name="PAYROLL").name == "PAYROLL"

    def test_functions_default_empty(self) -> None:
        assert IRModule(name="X").functions == ()

    def test_len_empty(self) -> None:
        assert len(IRModule(name="X")) == 0

    def test_len_with_functions(self) -> None:
        fn = IRFunction(name="F")
        assert len(IRModule(name="X", functions=(fn, fn))) == 2

    def test_kind_is_module(self) -> None:
        assert IRModule(name="X").kind is IRNodeKind.MODULE

    def test_frozen(self) -> None:
        mod = IRModule(name="X")
        with pytest.raises((AttributeError, TypeError)):
            mod.name = "Y"  # type: ignore[misc]

    def test_accept_dispatches(self) -> None:
        called = []

        class V(IRVisitor):
            def visit_module(self, node: IRModule) -> None:
                called.append(node)

        mod = IRModule(name="X")
        mod.accept(V())
        assert mod in called

    def test_accept_no_method_returns_none(self) -> None:
        assert IRModule(name="X").accept(object()) is None


# ===========================================================================
# IRProgram
# ===========================================================================


class TestIRProgram:
    """IRProgram construction, immutability, visitor dispatch."""

    def test_name_stored(self) -> None:
        assert IRProgram(name="MY-PROG").name == "MY-PROG"

    def test_modules_default_empty(self) -> None:
        assert IRProgram(name="X").modules == ()

    def test_len_empty(self) -> None:
        assert len(IRProgram(name="X")) == 0

    def test_len_with_modules(self) -> None:
        mod = IRModule(name="M")
        assert len(IRProgram(name="X", modules=(mod,))) == 1

    def test_kind_is_program(self) -> None:
        assert IRProgram(name="X").kind is IRNodeKind.PROGRAM

    def test_frozen(self) -> None:
        prog = IRProgram(name="X")
        with pytest.raises((AttributeError, TypeError)):
            prog.name = "Y"  # type: ignore[misc]

    def test_hashable(self) -> None:
        p1 = IRProgram(name="X")
        p2 = IRProgram(name="X")
        assert {p1, p2} == {p1}

    def test_accept_dispatches(self) -> None:
        called = []

        class V(IRVisitor):
            def visit_program(self, node: IRProgram) -> None:
                called.append(node)

        prog = IRProgram(name="X")
        prog.accept(V())
        assert prog in called

    def test_accept_no_method_returns_none(self) -> None:
        assert IRProgram(name="X").accept(object()) is None


# ===========================================================================
# IRVisitor no-op base
# ===========================================================================


class TestIRVisitorNoops:
    """IRVisitor base returns None for all hooks."""

    _v = IRVisitor()

    def test_visit_program_returns_none(self) -> None:
        assert self._v.visit_program(IRProgram(name="X")) is None  # type: ignore[arg-type]

    def test_visit_module_returns_none(self) -> None:
        assert self._v.visit_module(IRModule(name="X")) is None  # type: ignore[arg-type]

    def test_visit_function_returns_none(self) -> None:
        assert self._v.visit_function(IRFunction(name="X")) is None  # type: ignore[arg-type]

    def test_visit_basic_block_returns_none(self) -> None:
        assert self._v.visit_basic_block(IRBasicBlock(label="x")) is None  # type: ignore[arg-type]

    def test_visit_assignment_returns_none(self) -> None:
        assert self._v.visit_assignment(IRAssignment()) is None  # type: ignore[arg-type]

    def test_visit_move_returns_none(self) -> None:
        assert self._v.visit_move(IRMove()) is None  # type: ignore[arg-type]

    def test_visit_call_returns_none(self) -> None:
        assert self._v.visit_call(IRCall(target="X")) is None  # type: ignore[arg-type]

    def test_visit_return_returns_none(self) -> None:
        assert self._v.visit_return(IRReturn()) is None  # type: ignore[arg-type]

    def test_visit_conditional_branch_returns_none(self) -> None:
        assert self._v.visit_conditional_branch(IRConditionalBranch(condition="C", then_target="T", else_target="F")) is None  # type: ignore[arg-type]

    def test_visit_jump_returns_none(self) -> None:
        assert self._v.visit_jump(IRJump(target="T")) is None  # type: ignore[arg-type]

    def test_visit_instruction_returns_none(self) -> None:
        assert self._v.visit_instruction(IRAssignment()) is None  # type: ignore[arg-type]


# ===========================================================================
# traverse_ir()
# ===========================================================================


class TestTraverseIr:
    """traverse_ir() traversal driver."""

    def _recording_visitor(self) -> tuple[list[str], IRVisitor]:
        """Return (log, visitor) where visitor appends 'type:name' to log."""
        log: list[str] = []

        class Recorder(IRVisitor):
            def visit_program(self, node: IRProgram) -> None:
                log.append(f"program:{node.name}")

            def visit_module(self, node: IRModule) -> None:
                log.append(f"module:{node.name}")

            def visit_function(self, node: IRFunction) -> None:
                log.append(f"function:{node.name}")

            def visit_basic_block(self, node: IRBasicBlock) -> None:
                log.append(f"block:{node.label}")

            def visit_assignment(self, node: IRAssignment) -> None:
                log.append(f"assignment:{node.result}")

            def visit_move(self, node: IRMove) -> None:
                log.append(f"move:{node.result}")

            def visit_call(self, node: IRCall) -> None:
                log.append(f"call:{node.target}")

            def visit_return(self, node: IRReturn) -> None:
                log.append(f"return:{node.operand}")

            def visit_conditional_branch(self, node: IRConditionalBranch) -> None:
                log.append(f"conditional_branch:{node.then_target}")

            def visit_jump(self, node: IRJump) -> None:
                log.append(f"jump:{node.target}")

        return log, Recorder()

    def test_empty_program_no_crash(self) -> None:
        traverse_ir(IRProgram(name="EMPTY"), IRVisitor())  # must not raise

    def test_program_visited_first(self) -> None:
        log, visitor = self._recording_visitor()
        traverse_ir(IRProgram(name="P"), visitor)
        assert log[0] == "program:P"

    def test_module_visited_after_program(self) -> None:
        log, visitor = self._recording_visitor()
        prog = IRProgram(name="P", modules=(IRModule(name="M"),))
        traverse_ir(prog, visitor)
        assert log.index("module:M") > log.index("program:P")

    def test_function_visited_after_module(self) -> None:
        log, visitor = self._recording_visitor()
        fn = IRFunction(name="MAIN")
        mod = IRModule(name="M", functions=(fn,))
        prog = IRProgram(name="P", modules=(mod,))
        traverse_ir(prog, visitor)
        assert log.index("function:MAIN") > log.index("module:M")

    def test_block_visited_after_function(self) -> None:
        log, visitor = self._recording_visitor()
        bb = IRBasicBlock(label="entry")
        fn = IRFunction(name="MAIN", blocks=(bb,))
        mod = IRModule(name="M", functions=(fn,))
        prog = IRProgram(name="P", modules=(mod,))
        traverse_ir(prog, visitor)
        assert log.index("block:entry") > log.index("function:MAIN")

    def test_all_instruction_types_dispatched(self) -> None:
        log, visitor = self._recording_visitor()
        traverse_ir(_simple_program("P"), visitor)
        types_seen = {entry.split(":")[0] for entry in log}
        assert "assignment" in types_seen
        assert "move" in types_seen
        assert "call" in types_seen
        assert "return" in types_seen
        assert "jump" in types_seen

    def test_full_visit_order(self) -> None:
        log, visitor = self._recording_visitor()
        traverse_ir(_simple_program("PAYROLL"), visitor)
        # Check high-level order: program → module → function → block → instructions
        assert log[0] == "program:PAYROLL"
        assert log[1] == "module:MODULE-A"
        assert log[2] == "function:MAIN"
        assert log[3] == "block:entry"
        assert "assignment:WS-COUNT" in log
        assert "move:WS-OUT" in log
        assert "call:PROCESS-RECORD" in log

    def test_multiple_modules_all_visited(self) -> None:
        log, visitor = self._recording_visitor()
        mod1 = IRModule(name="MOD-A")
        mod2 = IRModule(name="MOD-B")
        prog = IRProgram(name="P", modules=(mod1, mod2))
        traverse_ir(prog, visitor)
        assert "module:MOD-A" in log
        assert "module:MOD-B" in log

    def test_multiple_functions_all_visited(self) -> None:
        log, visitor = self._recording_visitor()
        fn1 = IRFunction(name="FN-1")
        fn2 = IRFunction(name="FN-2")
        mod = IRModule(name="M", functions=(fn1, fn2))
        prog = IRProgram(name="P", modules=(mod,))
        traverse_ir(prog, visitor)
        assert "function:FN-1" in log
        assert "function:FN-2" in log

    def test_multiple_blocks_all_visited(self) -> None:
        log, visitor = self._recording_visitor()
        bb1 = IRBasicBlock(label="entry")
        bb2 = IRBasicBlock(label="exit")
        fn = IRFunction(name="MAIN", blocks=(bb1, bb2))
        mod = IRModule(name="M", functions=(fn,))
        prog = IRProgram(name="P", modules=(mod,))
        traverse_ir(prog, visitor)
        assert "block:entry" in log
        assert "block:exit" in log

    def test_empty_module_no_crash(self) -> None:
        traverse_ir(IRProgram(name="P", modules=(IRModule(name="M"),)), IRVisitor())

    def test_empty_function_no_crash(self) -> None:
        fn = IRFunction(name="F")
        mod = IRModule(name="M", functions=(fn,))
        traverse_ir(IRProgram(name="P", modules=(mod,)), IRVisitor())

    def test_empty_block_no_crash(self) -> None:
        bb = IRBasicBlock(label="x")
        fn = IRFunction(name="F", blocks=(bb,))
        mod = IRModule(name="M", functions=(fn,))
        traverse_ir(IRProgram(name="P", modules=(mod,)), IRVisitor())

    def test_counting_visitor_counts_instructions(self) -> None:
        counts: dict[str, int] = {
            "assignment": 0,
            "move": 0,
            "call": 0,
            "return": 0,
            "jump": 0,
        }

        class Counter(IRVisitor):
            def visit_assignment(self, node: IRAssignment) -> None:
                counts["assignment"] += 1

            def visit_move(self, node: IRMove) -> None:
                counts["move"] += 1

            def visit_call(self, node: IRCall) -> None:
                counts["call"] += 1

            def visit_return(self, node: IRReturn) -> None:
                counts["return"] += 1

            def visit_jump(self, node: IRJump) -> None:
                counts["jump"] += 1

        traverse_ir(_simple_program(), Counter())
        for k, v in counts.items():
            assert v == 1, f"Expected 1 {k}, got {v}"


# ===========================================================================
# IRBuilder
# ===========================================================================


class TestIRBuilder:
    """IRBuilder initialisation and behaviour (TASK-024 + TASK-025)."""

    def test_accepts_valid_context(self) -> None:
        ctx = _empty_ctx()
        builder = IRBuilder(context=ctx)
        assert builder.context is ctx

    def test_raises_type_error_for_non_context(self) -> None:
        with pytest.raises(TypeError, match="SemanticContext"):
            IRBuilder(context="not-a-context")  # type: ignore[arg-type]

    def test_raises_type_error_for_none(self) -> None:
        with pytest.raises(TypeError):
            IRBuilder(context=None)  # type: ignore[arg-type]

    def test_raises_type_error_for_dict(self) -> None:
        with pytest.raises(TypeError):
            IRBuilder(context={})  # type: ignore[arg-type]

    def test_context_property(self) -> None:
        ctx = _empty_ctx()
        assert IRBuilder(context=ctx).context is ctx

    def test_build_returns_ir_program(self) -> None:
        ctx = _empty_ctx()
        result = IRBuilder(context=ctx).build()
        assert isinstance(result, IRProgram)

    def test_build_returns_one_module(self) -> None:
        """TASK-025: build() always returns exactly one module."""
        ctx = _empty_ctx()
        prog = IRBuilder(context=ctx).build()
        assert len(prog) == 1

    def test_build_callable_multiple_times(self) -> None:
        ctx = _empty_ctx()
        builder = IRBuilder(context=ctx)
        p1 = builder.build()
        p2 = builder.build()
        assert isinstance(p1, IRProgram)
        assert isinstance(p2, IRProgram)

    def test_current_program_returns_ir_program(self) -> None:
        ctx = _empty_ctx()
        result = IRBuilder(context=ctx).current_program()
        assert isinstance(result, IRProgram)

    def test_current_program_same_as_build(self) -> None:
        ctx = _empty_ctx()
        builder = IRBuilder(context=ctx)
        assert builder.current_program() == builder.build()

    def test_accepts_context_with_errors(self) -> None:
        """Builder should not raise for contexts with semantic errors."""
        from app.parser.lexer.position import Position
        from app.parser.semantic.diagnostics import SemanticDiagnostic, SemanticSeverity

        pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        diag = SemanticDiagnostic(
            message="test error",
            position=pos,
            severity=SemanticSeverity.ERROR,
            code="SEM001",
        )
        ctx = SemanticContext(symbol_table=SymbolTable(), diagnostics=[diag])
        builder = IRBuilder(context=ctx)  # must not raise
        assert builder.context.has_errors is True


# ===========================================================================
# Instruction hierarchy — isinstance checks
# ===========================================================================


class TestInstructionHierarchy:
    """Instruction concrete types are IRInstruction and IRNode subclasses."""

    @pytest.mark.parametrize(
        "inst",
        [
            IRAssignment(result="X", value="0"),
            IRMove(result="A", source="B"),
            IRCall(target="FN"),
            IRReturn(operand="X"),
            IRJump(target="L"),
        ],
    )
    def test_is_ir_instruction(self, inst: IRInstruction) -> None:
        assert isinstance(inst, IRInstruction)

    @pytest.mark.parametrize(
        "inst",
        [
            IRAssignment(result="X", value="0"),
            IRMove(result="A", source="B"),
            IRCall(target="FN"),
            IRReturn(operand="X"),
            IRJump(target="L"),
        ],
    )
    def test_is_ir_node(self, inst: IRInstruction) -> None:
        assert isinstance(inst, IRNode)

    @pytest.mark.parametrize(
        "inst",
        [
            IRAssignment(result="X", value="0"),
            IRMove(result="A", source="B"),
            IRCall(target="FN"),
            IRReturn(operand="X"),
            IRJump(target="L"),
        ],
    )
    def test_kind_is_instruction(self, inst: IRInstruction) -> None:
        assert inst.kind is IRNodeKind.INSTRUCTION


# ===========================================================================
# Public API exports
# ===========================================================================


class TestPublicApiExports:
    """All types are exported from app.ir."""

    def test_ir_program_exported(self) -> None:
        from app.ir import IRProgram as P  # noqa: PLC0415

        assert P is IRProgram

    def test_ir_module_exported(self) -> None:
        from app.ir import IRModule as M  # noqa: PLC0415

        assert M is IRModule

    def test_ir_function_exported(self) -> None:
        from app.ir import IRFunction as F  # noqa: PLC0415

        assert F is IRFunction

    def test_ir_basic_block_exported(self) -> None:
        from app.ir import IRBasicBlock as BB  # noqa: PLC0415

        assert BB is IRBasicBlock

    def test_ir_instruction_exported(self) -> None:
        from app.ir import IRInstruction as I  # noqa: PLC0415

        assert I is IRInstruction

    def test_ir_assignment_exported(self) -> None:
        from app.ir import IRAssignment as A  # noqa: PLC0415

        assert A is IRAssignment

    def test_ir_move_exported(self) -> None:
        from app.ir import IRMove as MV  # noqa: PLC0415

        assert MV is IRMove

    def test_ir_call_exported(self) -> None:
        from app.ir import IRCall as C  # noqa: PLC0415

        assert C is IRCall

    def test_ir_return_exported(self) -> None:
        from app.ir import IRReturn as R  # noqa: PLC0415

        assert R is IRReturn

    def test_ir_conditional_branch_exported(self) -> None:
        from app.ir import IRConditionalBranch as CB  # noqa: PLC0415

        assert CB is IRConditionalBranch

    def test_ir_jump_exported(self) -> None:
        from app.ir import IRJump as J  # noqa: PLC0415

        assert J is IRJump

    def test_ir_builder_exported(self) -> None:
        from app.ir import IRBuilder as B  # noqa: PLC0415

        assert B is IRBuilder

    def test_ir_visitor_exported(self) -> None:
        from app.ir import IRVisitor as V  # noqa: PLC0415

        assert V is IRVisitor

    def test_traverse_ir_exported(self) -> None:
        from app.ir import traverse_ir as ti  # noqa: PLC0415

        assert ti is traverse_ir

    def test_ir_node_kind_exported(self) -> None:
        from app.ir import IRNodeKind as NK  # noqa: PLC0415

        assert NK is IRNodeKind

    def test_ir_node_exported(self) -> None:
        from app.ir import IRNode as N  # noqa: PLC0415

        assert N is IRNode


# ===========================================================================
# TASK-025: IRBuilder — AST-to-IR Translation Foundation
# ===========================================================================

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _pos(line: int = 1):  # returns Position  # noqa: ANN201
    from app.parser.lexer.position import Position  # noqa: PLC0415

    return Position(line=line, column=1, offset=0, filename="test.cbl")


def _ctx_with_program(name: str) -> SemanticContext:
    """Return a SemanticContext that contains one ProgramSymbol."""
    from app.parser.semantic.symbols import ProgramSymbol  # noqa: PLC0415

    table = SymbolTable()
    table.register(ProgramSymbol(name=name, declared_at=_pos()))
    return SemanticContext(symbol_table=table, diagnostics=[])


def _ctx_with_paragraphs(*names: str) -> SemanticContext:
    """Return a SemanticContext with one ProgramSymbol + N ParagraphSymbols."""
    from app.parser.semantic.symbols import (  # noqa: PLC0415
        ParagraphSymbol,
        ProgramSymbol,
    )

    table = SymbolTable()
    table.register(ProgramSymbol(name="TESTPROG", declared_at=_pos()))
    for i, n in enumerate(names, start=10):
        table.register(ParagraphSymbol(name=n, declared_at=_pos(line=i)))
    return SemanticContext(symbol_table=table, diagnostics=[])


class TestIRBuilderTranslation:
    """
    TASK-025: IRBuilder.build() translation tests.

    Covers:
    - Empty context (no ProgramSymbol) → one unnamed module.
    - Named program → correct names at every IR level.
    - One module per context.
    - One entry function per module.
    - One entry basic block per function (labelled "entry").
    - Entry block is initially empty (no instructions).
    - build() is deterministic across multiple calls.
    - build() is stateless (two calls return equal but distinct objects).
    - IRProgram is traversable via traverse_ir.
    - Context with semantic errors doesn't raise.
    - Helper method contracts (build_program, build_module, build_function,
      build_entry_block).
    - Naming helpers (_program_name, _module_name, _function_name).
    - Subclass can override naming without changing orchestration.
    """

    # ------------------------------------------------------------------
    # Empty context (no ProgramSymbol)
    # ------------------------------------------------------------------

    def test_empty_ctx_produces_ir_program(self) -> None:
        prog = IRBuilder(context=_empty_ctx()).build()
        assert isinstance(prog, IRProgram)

    def test_empty_ctx_program_name_is_empty(self) -> None:
        prog = IRBuilder(context=_empty_ctx()).build()
        assert prog.name == ""

    def test_empty_ctx_has_one_module(self) -> None:
        prog = IRBuilder(context=_empty_ctx()).build()
        assert len(prog) == 1

    def test_empty_ctx_module_name_is_empty(self) -> None:
        prog = IRBuilder(context=_empty_ctx()).build()
        assert prog.modules[0].name == ""

    def test_empty_ctx_module_has_one_function(self) -> None:
        prog = IRBuilder(context=_empty_ctx()).build()
        assert len(prog.modules[0]) == 1

    def test_empty_ctx_function_name_is_entry(self) -> None:
        prog = IRBuilder(context=_empty_ctx()).build()
        assert prog.modules[0].functions[0].name == "__entry__"

    def test_empty_ctx_function_has_one_block(self) -> None:
        prog = IRBuilder(context=_empty_ctx()).build()
        assert len(prog.modules[0].functions[0]) == 1

    def test_empty_ctx_entry_block_label(self) -> None:
        prog = IRBuilder(context=_empty_ctx()).build()
        assert prog.modules[0].functions[0].blocks[0].label == "entry"

    def test_empty_ctx_entry_block_is_empty(self) -> None:
        prog = IRBuilder(context=_empty_ctx()).build()
        assert prog.modules[0].functions[0].blocks[0].instructions == ()

    # ------------------------------------------------------------------
    # Named program
    # ------------------------------------------------------------------

    def test_named_program_sets_prog_name(self) -> None:
        prog = IRBuilder(context=_ctx_with_program("PAYROLL")).build()
        assert prog.name == "PAYROLL"

    def test_named_program_sets_module_name(self) -> None:
        prog = IRBuilder(context=_ctx_with_program("PAYROLL")).build()
        assert prog.modules[0].name == "PAYROLL"

    def test_named_program_function_still_entry(self) -> None:
        prog = IRBuilder(context=_ctx_with_program("PAYROLL")).build()
        assert prog.modules[0].functions[0].name == "__entry__"

    def test_named_program_block_still_entry(self) -> None:
        prog = IRBuilder(context=_ctx_with_program("PAYROLL")).build()
        assert prog.modules[0].functions[0].blocks[0].label == "entry"

    def test_named_program_block_still_empty(self) -> None:
        prog = IRBuilder(context=_ctx_with_program("PAYROLL")).build()
        assert prog.modules[0].functions[0].blocks[0].instructions == ()

    def test_different_program_names(self) -> None:
        for name in ("BILLING", "INVENTORY", "CUSTOMER-MGT"):
            prog = IRBuilder(context=_ctx_with_program(name)).build()
            assert prog.name == name
            assert prog.modules[0].name == name

    # ------------------------------------------------------------------
    # IR node kinds
    # ------------------------------------------------------------------

    def test_module_kind(self) -> None:
        prog = IRBuilder(context=_empty_ctx()).build()
        assert prog.modules[0].kind is IRNodeKind.MODULE

    def test_function_kind(self) -> None:
        prog = IRBuilder(context=_empty_ctx()).build()
        assert prog.modules[0].functions[0].kind is IRNodeKind.FUNCTION

    def test_entry_block_kind(self) -> None:
        prog = IRBuilder(context=_empty_ctx()).build()
        assert prog.modules[0].functions[0].blocks[0].kind is IRNodeKind.BASIC_BLOCK

    # ------------------------------------------------------------------
    # Determinism and statelessness
    # ------------------------------------------------------------------

    def test_build_deterministic(self) -> None:
        ctx = _ctx_with_program("PAYROLL")
        b = IRBuilder(context=ctx)
        assert b.build() == b.build()

    def test_build_returns_distinct_objects(self) -> None:
        ctx = _ctx_with_program("PAYROLL")
        b = IRBuilder(context=ctx)
        p1 = b.build()
        p2 = b.build()
        assert p1 is not p2

    def test_current_program_equals_build(self) -> None:
        ctx = _ctx_with_program("PAYROLL")
        b = IRBuilder(context=ctx)
        assert b.current_program() == b.build()

    # ------------------------------------------------------------------
    # Traversability via traverse_ir
    # ------------------------------------------------------------------

    def test_built_program_traversable(self) -> None:
        visited: list[str] = []

        class Rec(IRVisitor):
            def visit_program(self, node: IRProgram) -> None:
                visited.append(f"prog:{node.name}")

            def visit_module(self, node: IRModule) -> None:
                visited.append(f"mod:{node.name}")

            def visit_function(self, node: IRFunction) -> None:
                visited.append(f"fn:{node.name}")

            def visit_basic_block(self, node: IRBasicBlock) -> None:
                visited.append(f"bb:{node.label}")

        prog = IRBuilder(context=_ctx_with_program("PAYROLL")).build()
        traverse_ir(prog, Rec())
        assert "prog:PAYROLL" in visited
        assert "mod:PAYROLL" in visited
        assert "fn:__entry__" in visited
        assert "bb:entry" in visited

    def test_traversal_order(self) -> None:
        visited: list[str] = []

        class Rec(IRVisitor):
            def visit_program(self, node: IRProgram) -> None:
                visited.append("prog")

            def visit_module(self, node: IRModule) -> None:
                visited.append("mod")

            def visit_function(self, node: IRFunction) -> None:
                visited.append("fn")

            def visit_basic_block(self, node: IRBasicBlock) -> None:
                visited.append("bb")

        traverse_ir(IRBuilder(context=_empty_ctx()).build(), Rec())
        assert visited == ["prog", "mod", "fn", "bb"]

    # ------------------------------------------------------------------
    # Error-context tolerance
    # ------------------------------------------------------------------

    def test_error_context_does_not_raise(self) -> None:
        from app.parser.semantic.diagnostics import (  # noqa: PLC0415
            SemanticDiagnostic,
            SemanticSeverity,
        )

        diag = SemanticDiagnostic(
            message="dummy",
            position=_pos(),
            severity=SemanticSeverity.ERROR,
            code="SEM001",
        )
        ctx = SemanticContext(symbol_table=SymbolTable(), diagnostics=[diag])
        prog = IRBuilder(context=ctx).build()
        assert isinstance(prog, IRProgram)

    def test_error_context_still_produces_module(self) -> None:
        from app.parser.semantic.diagnostics import (  # noqa: PLC0415
            SemanticDiagnostic,
            SemanticSeverity,
        )

        diag = SemanticDiagnostic(
            message="dummy",
            position=_pos(),
            severity=SemanticSeverity.ERROR,
            code="SEM001",
        )
        ctx = SemanticContext(symbol_table=SymbolTable(), diagnostics=[diag])
        prog = IRBuilder(context=ctx).build()
        assert len(prog) == 1

    # ------------------------------------------------------------------
    # Individual helper methods
    # ------------------------------------------------------------------

    def test_build_program_returns_ir_program(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        assert isinstance(b.build_program("MY-PROG"), IRProgram)

    def test_build_program_sets_name(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        prog = b.build_program("MY-PROG")
        assert prog.name == "MY-PROG"

    def test_build_program_has_one_module(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        prog = b.build_program("X")
        assert len(prog) == 1

    def test_build_module_returns_ir_module(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        assert isinstance(b.build_module("MOD"), IRModule)

    def test_build_module_sets_name(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        mod = b.build_module("MOD-A")
        assert mod.name == "MOD-A"

    def test_build_module_has_one_function(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        mod = b.build_module("X")
        assert len(mod) == 1

    def test_build_function_returns_ir_function(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        assert isinstance(b.build_function("FN"), IRFunction)

    def test_build_function_sets_name(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        fn = b.build_function("MY-FN")
        assert fn.name == "MY-FN"

    def test_build_function_has_one_block(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        fn = b.build_function("FN")
        assert len(fn) == 1

    def test_build_function_block_labelled_entry(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        fn = b.build_function("FN")
        assert fn.blocks[0].label == "entry"

    def test_build_entry_block_returns_ir_basic_block(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        assert isinstance(b.build_entry_block(), IRBasicBlock)

    def test_build_entry_block_label(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        bb = b.build_entry_block()
        assert bb.label == "entry"

    def test_build_entry_block_is_empty(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        bb = b.build_entry_block()
        assert bb.instructions == ()

    def test_build_entry_block_name_synced_to_label(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        bb = b.build_entry_block()
        assert bb.name == "entry"

    # ------------------------------------------------------------------
    # Naming helpers
    # ------------------------------------------------------------------

    def test_program_name_empty_when_no_program_symbol(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        assert b._program_name() == ""

    def test_program_name_from_program_symbol(self) -> None:
        b = IRBuilder(context=_ctx_with_program("PAYROLL"))
        assert b._program_name() == "PAYROLL"

    def test_module_name_equals_program_name(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        assert b._module_name("PAYROLL") == "PAYROLL"

    def test_module_name_empty_string(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        assert b._module_name("") == ""

    def test_function_name_is_entry(self) -> None:
        b = IRBuilder(context=_empty_ctx())
        assert b._function_name() == "__entry__"

    # ------------------------------------------------------------------
    # Subclass extensibility
    # ------------------------------------------------------------------

    def test_subclass_can_override_function_name(self) -> None:
        """Subclass overrides _function_name without breaking build()."""

        class CustomBuilder(IRBuilder):
            def _function_name(self) -> str:
                return "custom_main"

        prog = CustomBuilder(context=_ctx_with_program("P")).build()
        assert prog.modules[0].functions[0].name == "custom_main"

    def test_subclass_can_override_module_name(self) -> None:
        """Subclass overrides _module_name to apply a prefix."""

        class PrefixBuilder(IRBuilder):
            def _module_name(self, prog_name: str) -> str:
                return f"com.example.{prog_name.lower()}"

        prog = PrefixBuilder(context=_ctx_with_program("PAYROLL")).build()
        assert prog.modules[0].name == "com.example.payroll"

    def test_subclass_can_override_build_entry_block(self) -> None:
        """Subclass overrides build_entry_block to pre-populate instructions."""
        from app.parser.ast.procedure import (  # noqa: PLC0415
            ProcedureDivisionNode,
        )

        class InstrBuilder(IRBuilder):
            def build_entry_block(
                self,
                proc_div: ProcedureDivisionNode | None = None,
            ) -> IRBasicBlock:
                return IRBasicBlock(
                    label="entry",
                    instructions=(IRReturn(operand=""),),
                )

        prog = InstrBuilder(context=_ctx_with_program("P")).build()
        bb = prog.modules[0].functions[0].blocks[0]
        assert len(bb) == 1
        assert isinstance(bb.instructions[0], IRReturn)

    # ------------------------------------------------------------------
    # Structure invariants
    # ------------------------------------------------------------------

    def test_program_contains_ir_module_instances(self) -> None:
        prog = IRBuilder(context=_ctx_with_program("P")).build()
        assert all(isinstance(m, IRModule) for m in prog.modules)

    def test_module_contains_ir_function_instances(self) -> None:
        prog = IRBuilder(context=_ctx_with_program("P")).build()
        mod = prog.modules[0]
        assert all(isinstance(f, IRFunction) for f in mod.functions)

    def test_function_contains_ir_basic_block_instances(self) -> None:
        prog = IRBuilder(context=_ctx_with_program("P")).build()
        fn = prog.modules[0].functions[0]
        assert all(isinstance(b, IRBasicBlock) for b in fn.blocks)

    def test_entry_block_instructions_is_tuple(self) -> None:
        prog = IRBuilder(context=_ctx_with_program("P")).build()
        bb = prog.modules[0].functions[0].blocks[0]
        assert isinstance(bb.instructions, tuple)

    def test_function_return_type_is_void(self) -> None:
        prog = IRBuilder(context=_ctx_with_program("P")).build()
        fn = prog.modules[0].functions[0]
        assert fn.return_type == "void"

    def test_function_params_is_empty(self) -> None:
        prog = IRBuilder(context=_ctx_with_program("P")).build()
        fn = prog.modules[0].functions[0]
        assert fn.params == ()

    def test_result_is_frozen_program(self) -> None:
        """IRProgram is a frozen dataclass — cannot be mutated."""
        prog = IRBuilder(context=_ctx_with_program("P")).build()
        with pytest.raises((AttributeError, TypeError)):
            prog.name = "CHANGED"  # type: ignore[misc]

    def test_result_is_hashable(self) -> None:
        prog = IRBuilder(context=_ctx_with_program("P")).build()
        assert hash(prog) is not None

    # ------------------------------------------------------------------
    # Context with multiple symbol kinds (paragraphs, variables)
    # ------------------------------------------------------------------

    def test_context_with_paragraphs_still_one_module(self) -> None:
        ctx = _ctx_with_paragraphs("PARA-1", "PARA-2", "PARA-3")
        prog = IRBuilder(context=ctx).build()
        assert len(prog) == 1

    def test_context_with_paragraphs_program_name(self) -> None:
        ctx = _ctx_with_paragraphs("PARA-1")
        prog = IRBuilder(context=ctx).build()
        assert prog.name == "TESTPROG"

    def test_context_with_paragraphs_one_entry_function(self) -> None:
        ctx = _ctx_with_paragraphs("PARA-1", "PARA-2")
        prog = IRBuilder(context=ctx).build()
        assert len(prog.modules[0]) == 1

    # ------------------------------------------------------------------
    # current_program()
    # ------------------------------------------------------------------

    def test_current_program_returns_ir_program(self) -> None:
        ctx = _ctx_with_program("P")
        assert isinstance(IRBuilder(context=ctx).current_program(), IRProgram)

    def test_current_program_has_same_structure_as_build(self) -> None:
        ctx = _ctx_with_program("PAYROLL")
        b = IRBuilder(context=ctx)
        assert b.current_program() == b.build()
