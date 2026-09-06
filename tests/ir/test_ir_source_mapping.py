"""
IR source-mapping regression tests (task #109).

Purpose:
    Prove that :attr:`~app.ir.instructions.IRInstruction.source_position`
    and :attr:`~app.ir.instructions.IRInstruction.paragraph` -- the two
    fields added to :class:`~app.ir.instructions.IRInstruction` by task
    #109 -- survive AST -> IR lowering for every currently-supported
    statement type, carry the *real* filename/line/column from the
    source file (never a fabricated position), and correctly identify
    which paragraph each instruction came from.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any

from app.ir.builder import IRBuilder
from app.ir.instructions import IRDisplay, IRMove, IRReturn
from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.position import Position
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.syntax.program_parser import ProgramParser

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\n"


def _build(source: str, filename: str = "source_mapping_test.cbl") -> list[Any]:
    """Run *source* through the real pipeline; return the flat instruction list."""
    tokens = CobolLexer().tokenize(source, filename=filename)
    program = ProgramParser().parse(tokens)
    ctx = SemanticAnalyzer().analyse(program)
    ir_program = IRBuilder(context=ctx).build(program)
    block = ir_program.modules[0].functions[0].blocks[0]
    return list(block.instructions)


class TestSourcePositionSurvivesLowering:
    """Every mapped instruction carries a real, non-fabricated position."""

    def test_move_carries_its_own_line(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\n"  # line 3
            "MAIN.\n"  # line 4
            "    MOVE 1 TO WS-X.\n"  # line 5
            "    STOP RUN.\n"  # line 6
        )
        instrs = _build(source)
        move = next(i for i in instrs if isinstance(i, IRMove))
        assert move.source_position is not None
        assert move.source_position.line == 5

    def test_every_supported_statement_carries_a_position(self) -> None:
        """No mapped instruction is left with source_position=None."""
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    MOVE 1 TO WS-X.\n"
            '    DISPLAY "A".\n'
            "    ADD 1 TO WS-X.\n"
            "    SUBTRACT 1 FROM WS-X.\n"
            "    MULTIPLY 2 BY WS-X.\n"
            "    DIVIDE 2 INTO WS-X.\n"
            '    IF WS-X = 1 DISPLAY "B" END-IF.\n'
            "    STOP RUN.\n"
        )
        instrs = _build(source)
        assert instrs, "expected at least one instruction"
        for instr in instrs:
            assert instr.source_position is not None, (
                f"{type(instr).__name__} at index "
                f"{instrs.index(instr)} has no source_position"
            )

    def test_position_filename_matches_source_file(self) -> None:
        """The position must carry the real filename, never a placeholder."""
        source = _ID + 'PROCEDURE DIVISION.\nMAIN.\n    DISPLAY "A".\n    STOP RUN.\n'
        instrs = _build(source, filename="my_program.cbl")
        display = next(i for i in instrs if isinstance(i, IRDisplay))
        assert display.source_position.filename == "my_program.cbl"

    def test_distinct_statements_get_distinct_positions(self) -> None:
        """
        Negative case: two different statements on different lines must
        not collapse onto the same fabricated position.
        """
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    MOVE 1 TO WS-X.\n"  # line 5
            "    MOVE 2 TO WS-Y.\n"  # line 6
            "    STOP RUN.\n"
        )
        instrs = _build(source)
        moves = [i for i in instrs if isinstance(i, IRMove)]
        assert len(moves) == 2
        assert moves[0].source_position.line != moves[1].source_position.line
        assert {moves[0].source_position.line, moves[1].source_position.line} == {
            5,
            6,
        }

    def test_nested_if_branches_carry_their_own_statement_position(self) -> None:
        """
        Even nested statements (inside IF branches) keep the position of
        the specific AST statement they were lowered from, not the
        enclosing IF's position.
        """
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    IF WS-X = 1\n"  # line 5
            '        DISPLAY "THEN"\n'  # line 6
            "    END-IF.\n"
            "    STOP RUN.\n"
        )
        instrs = _build(source)
        display = next(i for i in instrs if isinstance(i, IRDisplay))
        assert display.source_position.line == 6

    def test_marker_instructions_use_enclosing_statement_position(self) -> None:
        """
        IREndIf/IRElse have no AST statement of their own; they are
        stamped with the enclosing IF statement's position rather than
        being left unmapped (``None``), since a real position (the IF's)
        is available and using it is more useful than fabricating
        nothing at all.
        """
        from app.ir.instructions import IREndIf

        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            '    IF WS-X = 1 DISPLAY "A" END-IF.\n'
            "    STOP RUN.\n"
        )
        instrs = _build(source)
        end_if = next(i for i in instrs if isinstance(i, IREndIf))
        assert end_if.source_position is not None


class TestParagraphIdentitySurvivesLowering:
    """
    Paragraph identity (task #109's other confirmed loss) survives
    lowering despite every paragraph's statements sharing one flat
    IRBasicBlock -- see the ``paragraph`` field on IRInstruction.
    """

    def test_single_paragraph_stamps_every_instruction(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN-PARA.\n"
            "    MOVE 1 TO WS-X.\n"
            '    DISPLAY "A".\n'
            "    STOP RUN.\n"
        )
        instrs = _build(source)
        assert instrs
        assert all(i.paragraph == "MAIN-PARA" for i in instrs)

    def test_multiple_paragraphs_are_correctly_attributed(self) -> None:
        """
        Negative case: instructions from paragraph B must not be
        attributed to paragraph A, and vice versa.
        """
        source = (
            _ID + "PROCEDURE DIVISION.\n"
            "FIRST-PARA.\n"
            "    MOVE 1 TO WS-X.\n"
            "    PERFORM SECOND-PARA.\n"
            "    STOP RUN.\n"
            "SECOND-PARA.\n"
            '    DISPLAY "IN-SECOND".\n'
        )
        instrs = _build(source)

        move = next(i for i in instrs if isinstance(i, IRMove))
        assert move.paragraph == "FIRST-PARA"

        display = next(i for i in instrs if isinstance(i, IRDisplay))
        assert display.paragraph == "SECOND-PARA"

        stop_run = next(i for i in instrs if isinstance(i, IRReturn))
        assert stop_run.paragraph == "FIRST-PARA"

    def test_nested_statements_inherit_their_paragraph(self) -> None:
        """Statements inside an IF branch still belong to the outer paragraph."""
        source = (
            _ID + "PROCEDURE DIVISION.\nONLY-PARA.\n"
            '    IF WS-X = 1 DISPLAY "NESTED" END-IF.\n'
            "    STOP RUN.\n"
        )
        instrs = _build(source)
        display = next(i for i in instrs if isinstance(i, IRDisplay))
        assert display.paragraph == "ONLY-PARA"

    def test_program_without_paragraphs_has_no_fabricated_paragraph_name(
        self,
    ) -> None:
        """
        IR built with no PROCEDURE DIVISION at all must not invent a
        paragraph name for the (nonexistent) instructions.
        """
        ctx = SemanticAnalyzer().analyse(
            ProgramParser().parse(CobolLexer().tokenize(_ID, filename="t.cbl"))
        )
        ir_program = IRBuilder(context=ctx).build(
            ProgramParser().parse(CobolLexer().tokenize(_ID, filename="t.cbl"))
        )
        block = ir_program.modules[0].functions[0].blocks[0]
        assert block.instructions == ()


class TestSourceMappingDoesNotAffectEquality:
    """
    The new fields must not break existing code that compares IR
    instructions for equality by operand values alone (task #109
    explicitly requires backward compatibility for existing consumers).
    """

    def test_instructions_with_different_positions_still_compare_equal(self) -> None:
        pos_a = Position(line=1, column=1, offset=0, filename="a.cbl")
        pos_b = Position(line=99, column=5, offset=500, filename="b.cbl")

        move_a = IRMove(source="X", result="Y", source_position=pos_a, paragraph="A")
        move_b = IRMove(source="X", result="Y", source_position=pos_b, paragraph="B")

        assert move_a == move_b
