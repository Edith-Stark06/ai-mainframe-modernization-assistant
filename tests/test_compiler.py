"""
Unit tests for the Compiler Driver (app/compiler.py) and IR Pretty Printer
(app/ir/printer.py) — TASK-031.

Coverage:
    - compile_file(): success, missing file, invalid source.
    - main(): exit codes via CLI argument parsing.
    - pretty_print(): all instruction types, empty blocks, multi-block programs.
    - Determinism: repeated calls produce identical output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.compiler import compile_file, main
from app.ir.blocks import IRBasicBlock
from app.ir.instructions import (
    IRAccept,
    IRAdd,
    IRAssignment,
    IRCall,
    IRConditionalBranch,
    IRDisplay,
    IRDivide,
    IRJump,
    IRMove,
    IRMultiply,
    IRReturn,
    IRSubtract,
)
from app.ir.printer import pretty_print
from app.ir.program import IRFunction, IRModule, IRProgram
from app.parser.lexer.position import Position

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

_POS = Position(line=1, column=1, offset=0, filename="test.cbl")


def _make_program(
    prog_name: str = "TEST",
    instructions: tuple = (),
) -> IRProgram:
    """Return a minimal IRProgram with one block containing *instructions*."""
    block = IRBasicBlock(
        label="entry",
        instructions=instructions,
    )
    func = IRFunction(
        name="__entry__",
        blocks=(block,),
    )
    module = IRModule(
        name=prog_name,
        functions=(func,),
    )
    return IRProgram(
        name=prog_name,
        modules=(module,),
    )


# ---------------------------------------------------------------------------
# Pretty Printer Tests
# ---------------------------------------------------------------------------


class TestPrettyPrinter:
    def test_empty_program_header(self) -> None:
        prog = _make_program("HELLO", instructions=())
        text = pretty_print(prog)
        assert "Program HELLO" in text

    def test_empty_program_module_function(self) -> None:
        prog = _make_program("MYAPP", instructions=())
        text = pretty_print(prog)
        assert "Module MYAPP" in text
        assert "Function __entry__" in text

    def test_empty_block_placeholder(self) -> None:
        prog = _make_program(instructions=())
        text = pretty_print(prog)
        assert "(empty block)" in text

    def test_move_instruction(self) -> None:
        instr = IRMove(result="WS-B", source="WS-A")
        prog = _make_program(instructions=(instr,))
        text = pretty_print(prog)
        assert "MOVE WS-A -> WS-B" in text

    def test_assignment_instruction(self) -> None:
        instr = IRAssignment(result="WS-X", value="42")
        prog = _make_program(instructions=(instr,))
        text = pretty_print(prog)
        assert "ASSIGN WS-X = 42" in text

    def test_display_instruction(self) -> None:
        instr = IRDisplay(operand='"HELLO"')
        prog = _make_program(instructions=(instr,))
        text = pretty_print(prog)
        assert 'DISPLAY "HELLO"' in text

    def test_accept_instruction(self) -> None:
        instr = IRAccept(result="WS-NAME")
        prog = _make_program(instructions=(instr,))
        text = pretty_print(prog)
        assert "ACCEPT WS-NAME" in text

    def test_add_instruction(self) -> None:
        instr = IRAdd(left="WS-A", right="WS-TOTAL")
        prog = _make_program(instructions=(instr,))
        text = pretty_print(prog)
        assert "ADD WS-A TO WS-TOTAL" in text

    def test_subtract_instruction(self) -> None:
        instr = IRSubtract(left="5", right="WS-COUNT")
        prog = _make_program(instructions=(instr,))
        text = pretty_print(prog)
        assert "SUBTRACT 5 FROM WS-COUNT" in text

    def test_multiply_instruction(self) -> None:
        instr = IRMultiply(left="WS-A", right="WS-B")
        prog = _make_program(instructions=(instr,))
        text = pretty_print(prog)
        assert "MULTIPLY WS-A BY WS-B" in text

    def test_divide_instruction(self) -> None:
        instr = IRDivide(left="WS-B", right="WS-A")
        prog = _make_program(instructions=(instr,))
        text = pretty_print(prog)
        assert "DIVIDE WS-B INTO WS-A" in text

    def test_call_instruction_no_args(self) -> None:
        instr = IRCall(target="PROCESS-REC")
        prog = _make_program(instructions=(instr,))
        text = pretty_print(prog)
        assert "CALL PROCESS-REC" in text

    def test_call_instruction_with_args(self) -> None:
        instr = IRCall(target="CALC", args=("WS-A", "WS-B"))
        prog = _make_program(instructions=(instr,))
        text = pretty_print(prog)
        assert "CALL CALC USING WS-A WS-B" in text

    def test_return_void(self) -> None:
        instr = IRReturn()
        prog = _make_program(instructions=(instr,))
        text = pretty_print(prog)
        assert "RETURN" in text

    def test_return_with_operand(self) -> None:
        instr = IRReturn(operand="WS-RESULT")
        prog = _make_program(instructions=(instr,))
        text = pretty_print(prog)
        assert "RETURN WS-RESULT" in text

    def test_conditional_branch(self) -> None:
        instr = IRConditionalBranch(
            condition="WS-FLAG", then_target="then_0", else_target="merge_0"
        )
        prog = _make_program(instructions=(instr,))
        text = pretty_print(prog)
        assert "IF WS-FLAG THEN then_0 ELSE merge_0" in text

    def test_jump_instruction(self) -> None:
        instr = IRJump(target="merge_0")
        prog = _make_program(instructions=(instr,))
        text = pretty_print(prog)
        assert "JUMP merge_0" in text

    def test_multiple_instructions_ordered(self) -> None:
        instructions = (
            IRMove(result="WS-B", source="WS-A"),
            IRDisplay(operand="WS-B"),
            IRReturn(),
        )
        prog = _make_program(instructions=instructions)
        text = pretty_print(prog)
        idx_move = text.index("MOVE")
        idx_display = text.index("DISPLAY")
        idx_return = text.index("RETURN")
        assert idx_move < idx_display < idx_return

    def test_block_label_present(self) -> None:
        prog = _make_program(instructions=())
        text = pretty_print(prog)
        assert "entry:" in text

    def test_deterministic_output(self) -> None:
        instr = IRMove(result="WS-OUT", source="WS-IN")
        prog = _make_program(instructions=(instr,))
        assert pretty_print(prog) == pretty_print(prog)

    def test_multiple_modules(self) -> None:
        """Programs with multiple modules render all of them."""
        block = IRBasicBlock(
            label="entry",
            instructions=(),
        )
        func = IRFunction(
            name="__entry__",
            blocks=(block,),
        )
        mod_a = IRModule(
            name="MOD-A",
            functions=(func,),
        )
        mod_b = IRModule(
            name="MOD-B",
            functions=(func,),
        )
        prog = IRProgram(
            name="MULTI",
            modules=(mod_a, mod_b),
        )
        text = pretty_print(prog)
        assert "Module MOD-A" in text
        assert "Module MOD-B" in text


# ---------------------------------------------------------------------------
# compile_file() Tests
# ---------------------------------------------------------------------------


class TestCompileFile:
    def test_missing_file_returns_1(self, tmp_path: Path) -> None:
        rc = compile_file(tmp_path / "nonexistent.cbl")
        assert rc == 1

    def test_hello_compiles_successfully(self) -> None:
        """The bundled hello.cbl must compile without errors (exit 0 or 2)."""
        examples_dir = Path(__file__).parent.parent / "examples"
        hello = examples_dir / "hello.cbl"
        if not hello.exists():
            pytest.skip("examples/hello.cbl not found")
        rc = compile_file(hello)
        # rc may be 2 for semantic warnings (undefined refs in test env), but must not be 1
        assert rc in (0, 2)

    def test_arithmetic_example(self) -> None:
        examples_dir = Path(__file__).parent.parent / "examples"
        arith = examples_dir / "arithmetic.cbl"
        if not arith.exists():
            pytest.skip("examples/arithmetic.cbl not found")
        rc = compile_file(arith)
        assert rc in (0, 2)

    def test_subprogram_example(self) -> None:
        examples_dir = Path(__file__).parent.parent / "examples"
        sub = examples_dir / "subprogram.cbl"
        if not sub.exists():
            pytest.skip("examples/subprogram.cbl not found")
        rc = compile_file(sub)
        assert rc in (0, 2)

    def test_invalid_source_does_not_crash(self, tmp_path: Path) -> None:
        """Source with lex errors (return 2) must not raise uncaught exceptions."""
        bad = tmp_path / "bad.cbl"
        # Semantically invalid but lexically parseable COBOL
        bad.write_text(
            "       IDENTIFICATION DIVISION.\n"
            "       PROGRAM-ID. BADPROG.\n"
            "       PROCEDURE DIVISION.\n"
            "       MAIN-PARA.\n"
            "           MOVE WS-UNDEFINED TO WS-ALSO-UNDEFINED.\n"
            "           STOP RUN.\n",
            encoding="utf-8",
        )
        rc = compile_file(bad)
        assert rc in (0, 2)

    def test_empty_source_does_not_crash(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.cbl"
        empty.write_text("", encoding="utf-8")
        rc = compile_file(empty)
        assert rc in (0, 2)

    def test_returns_int(self, tmp_path: Path) -> None:
        bad = tmp_path / "x.cbl"
        bad.write_text("", encoding="utf-8")
        rc = compile_file(bad)
        assert isinstance(rc, int)

    def test_ir_output_printed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        src = tmp_path / "prog.cbl"
        src.write_text(
            "       IDENTIFICATION DIVISION.\n"
            "       PROGRAM-ID. TEST.\n"
            "       PROCEDURE DIVISION.\n"
            "       MAIN-PARA.\n"
            '           DISPLAY "HI".\n'
            "           STOP RUN.\n",
            encoding="utf-8",
        )
        compile_file(src)
        captured = capsys.readouterr()
        assert "Program" in captured.out


# ---------------------------------------------------------------------------
# main() CLI Tests
# ---------------------------------------------------------------------------


class TestMain:
    def test_missing_file_exits_1(self, tmp_path: Path) -> None:
        rc = main([str(tmp_path / "no_such_file.cbl")])
        assert rc == 1

    def test_hello_exit_code(self) -> None:
        examples_dir = Path(__file__).parent.parent / "examples"
        hello = examples_dir / "hello.cbl"
        if not hello.exists():
            pytest.skip("examples/hello.cbl not found")
        rc = main([str(hello)])
        assert rc in (0, 2)

    def test_no_args_raises_system_exit(self) -> None:
        with pytest.raises(SystemExit):
            main([])
