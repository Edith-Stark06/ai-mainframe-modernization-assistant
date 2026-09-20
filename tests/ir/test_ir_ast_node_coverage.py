"""
AST -> IR completeness and node-loss detection (task #109).

Purpose:
    Provide the deterministic mechanism task #109 requires: a mapping of
    every meaningful AST statement category to its expected IR
    representation, asserted so that a supported construct silently
    ceasing to produce IR is caught by CI rather than discovered later
    on a real fixture.

    Node counting alone is deliberately avoided (one AST statement can
    legitimately produce zero, one, or several IR instructions -- see
    ``IfStatementNode``, which recursively lowers its nested statements
    and therefore has no single corresponding instruction). Instead,
    each category has an explicit expected-IR-type assertion, and any
    statement type without one is treated as a coverage gap by
    :func:`test_every_ast_statement_type_is_classified`.

Coverage as of task #stage17 (see the module-level ``EXPECTED_IR_MAPPING``
table below for specifics):

    Supported + mapped:
        MOVE, DISPLAY, ADD, SUBTRACT, MULTIPLY, DIVIDE, IF, PERFORM,
        PERFORM UNTIL, CALL, STOP RUN, GOBACK, GO TO.
        (STOP RUN and GOBACK were the confirmed #109 node-loss bugs
        fixed by that task -- previously they silently produced no IR
        instruction at all despite IRReturn existing for exactly this
        purpose. GO TO's ``build_go_to_statement`` -> ``IRJump`` mapping
        existed since before #109 but was unreachable from real source
        until task #stage17 gave the parser a dispatch path for it --
        see ``docs/MMIM_GO_TO_FIX.md`` and
        ``tests/parser/test_go_to_parsing_fix.py``.)

    Supported by the IR builder, but still unreachable from real COBOL
    source:
        ACCEPT. ``build_accept_instruction`` correctly lowers an
        ``AcceptStatementNode`` to ``IRAccept`` (proven below by
        constructing the AST node directly), but the parser deliberately
        classifies ``ACCEPT`` (task #108 -- to fix the
        phantom-paragraph/syntax-error bug at ``_parse_statement``'s
        fallback -- see #108's PR) as an unsupported statement, so no
        real COBOL source can produce that AST node today. This is a
        confirmed parser limitation, not an IR gap, and is deliberately
        NOT touched by task #stage17 (its own scope is GO TO only) -- see
        ``docs/MMIM_GO_TO_FIX.md`` §13.

    Unsupported/unmodelled (no AST representation to translate):
        EVALUATE, OPEN, CLOSE, READ, WRITE, COMPUTE, STRING, and every
        other verb in the parser's ``_UNSUPPORTED_STATEMENT_LEXEMES``
        set. These never reach the IR builder because the parser never
        constructs an AST node for them; the parser reports them
        explicitly (task #108, ``SYN100``) rather than silently
        dropping them. This is correctly out of #109's scope: there is
        nothing for the IR to lose, because nothing was ever
        represented in the AST to begin with.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any

from app.ir.builder import IRBuilder
from app.ir.instructions import (
    IRAccept,
    IRAdd,
    IRCall,
    IRDisplay,
    IRDivide,
    IRIf,
    IRInstruction,
    IRJump,
    IRMove,
    IRMultiply,
    IRPerformUntil,
    IRReturn,
    IRSubtract,
)
from app.parser.ast import statements as ast_statements
from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.position import Position
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.syntax.program_parser import ProgramParser

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\n"


def _build(source: str) -> tuple[Any, list[IRInstruction]]:
    """
    Run *source* through the real lexer/parser/semantic/IR pipeline.

    Returns:
        ``(program_node, instructions)`` where ``instructions`` is the
        flat instruction list of the single entry block.
    """
    tokens = CobolLexer().tokenize(source, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    ctx = SemanticAnalyzer().analyse(program)
    ir_program = IRBuilder(context=ctx).build(program)
    block = ir_program.modules[0].functions[0].blocks[0]
    return program, list(block.instructions)


# ===========================================================================
# The completeness table: every concrete StatementNode subclass this
# repository defines, and the IR instruction type(s) task #109 requires
# it to produce.  ``None`` marks a type this test suite proves is
# reachable only by constructing the AST node directly (the parser
# cannot currently produce one from real source) -- see the module
# docstring's "unreachable from real COBOL source" section.
# ===========================================================================
EXPECTED_IR_MAPPING: dict[type, tuple[type[IRInstruction], ...] | None] = {
    ast_statements.MoveStatementNode: (IRMove,),
    ast_statements.DisplayStatementNode: (IRDisplay,),
    ast_statements.AcceptStatementNode: None,  # see module docstring
    ast_statements.AddStatementNode: (IRAdd,),
    ast_statements.SubtractStatementNode: (IRSubtract,),
    ast_statements.MultiplyStatementNode: (IRMultiply,),
    ast_statements.DivideStatementNode: (IRDivide,),
    ast_statements.IfStatementNode: (IRIf,),  # + nested + IREndIf; see below
    ast_statements.PerformStatementNode: (IRCall,),
    ast_statements.PerformUntilStatementNode: (IRPerformUntil,),  # + IREndPerform
    ast_statements.CallStatementNode: (IRCall,),
    ast_statements.StopRunStatementNode: (IRReturn,),
    ast_statements.GobackStatementNode: (IRReturn,),
    ast_statements.GoToStatementNode: (IRJump,),  # task #stage17; was None
}


def test_every_ast_statement_type_is_classified() -> None:
    """
    Every concrete ``StatementNode`` subclass this repository defines
    must appear in :data:`EXPECTED_IR_MAPPING`.

    This is the actual node-loss guard: if a new statement type is
    added to ``app/parser/ast/statements.py`` without a corresponding
    entry here (and without deliberately being added to the
    "intentionally unmapped" list), this test fails -- forcing a
    conscious decision about its IR representation instead of letting
    it silently fall through ``_translate_statement``'s generic
    "unsupported statement type" debug log.
    """
    concrete_statement_types = {
        cls
        for name in ast_statements.__all__
        if (cls := getattr(ast_statements, name)) is not ast_statements.StatementNode
        and isinstance(cls, type)
        and issubclass(cls, ast_statements.StatementNode)
    }

    missing = concrete_statement_types - EXPECTED_IR_MAPPING.keys()
    assert not missing, (
        f"AST statement type(s) {sorted(t.__name__ for t in missing)} have no "
        "entry in EXPECTED_IR_MAPPING -- task #109 requires every meaningful "
        "AST construct to have an identified, tested IR mapping (or an "
        "explicit, documented reason it does not)."
    )


class TestAssignmentMapping:
    """MOVE: operands, source/target ordering, literals, identifiers."""

    def test_move_identifier_to_identifier(self) -> None:
        _, instrs = _build(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    MOVE WS-SOURCE TO WS-TARGET.\n    STOP RUN.\n"
        )
        move = next(i for i in instrs if isinstance(i, IRMove))
        assert move.source == "WS-SOURCE"
        assert move.result == "WS-TARGET"

    def test_move_literal_to_identifier(self) -> None:
        _, instrs = _build(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n    MOVE 42 TO WS-X.\n    STOP RUN.\n"
        )
        move = next(i for i in instrs if isinstance(i, IRMove))
        assert move.source == "42"
        assert move.result == "WS-X"

    def test_move_does_not_swap_source_and_target(self) -> None:
        """Negative case: source and target must never be transposed."""
        _, instrs = _build(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    MOVE WS-A TO WS-B.\n    STOP RUN.\n"
        )
        move = next(i for i in instrs if isinstance(i, IRMove))
        assert move.source == "WS-A" and move.result != "WS-A"
        assert move.result == "WS-B" and move.source != "WS-B"


class TestArithmeticMapping:
    """ADD/SUBTRACT/MULTIPLY/DIVIDE: operands and instruction type."""

    def test_add(self) -> None:
        _, instrs = _build(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    ADD 1 TO WS-COUNT.\n    STOP RUN.\n"
        )
        add = next(i for i in instrs if isinstance(i, IRAdd))
        assert (add.left, add.right) == ("1", "WS-COUNT")

    def test_subtract(self) -> None:
        _, instrs = _build(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    SUBTRACT 1 FROM WS-COUNT.\n    STOP RUN.\n"
        )
        sub = next(i for i in instrs if isinstance(i, IRSubtract))
        assert (sub.left, sub.right) == ("1", "WS-COUNT")

    def test_multiply(self) -> None:
        _, instrs = _build(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    MULTIPLY 2 BY WS-COUNT.\n    STOP RUN.\n"
        )
        mul = next(i for i in instrs if isinstance(i, IRMultiply))
        assert (mul.left, mul.right) == ("2", "WS-COUNT")

    def test_divide(self) -> None:
        _, instrs = _build(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    DIVIDE 2 INTO WS-COUNT.\n    STOP RUN.\n"
        )
        div = next(i for i in instrs if isinstance(i, IRDivide))
        assert (div.left, div.right) == ("2", "WS-COUNT")


class TestConditionAndBranchMapping:
    """IF: condition preservation, operator preservation, both branches."""

    def test_if_condition_operands_and_operator_preserved(self) -> None:
        _, instrs = _build(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            '    IF WS-STATUS = "A" DISPLAY "MATCH" END-IF.\n    STOP RUN.\n'
        )
        cond = next(i for i in instrs if isinstance(i, IRIf))
        assert cond.left == "WS-STATUS"
        assert cond.operator == "="  # raw COBOL operator, not normalized
        assert cond.right == '"A"'

    def test_if_then_branch_statements_reach_ir(self) -> None:
        _, instrs = _build(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            '    IF WS-X = 1 DISPLAY "THEN-BRANCH" END-IF.\n    STOP RUN.\n'
        )
        displays = [i for i in instrs if isinstance(i, IRDisplay)]
        assert any(d.operand == '"THEN-BRANCH"' for d in displays)

    def test_if_else_branch_statements_reach_ir(self) -> None:
        _, instrs = _build(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            '    IF WS-X = 1 DISPLAY "THEN" ELSE DISPLAY "ELSE-BRANCH" END-IF.\n'
            "    STOP RUN.\n"
        )
        displays = [i for i in instrs if isinstance(i, IRDisplay)]
        assert any(d.operand == '"ELSE-BRANCH"' for d in displays)

    def test_nested_if_both_levels_reach_ir(self) -> None:
        """
        IF
            MOVE ...
            IF ...
                DISPLAY ...
            END-IF
        ELSE
            ...
        END-IF

        Both the outer and inner conditions, and every branch's
        statements, must survive lowering.
        """
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    IF WS-OUTER = 1\n"
            "        MOVE 1 TO WS-FLAG\n"
            "        IF WS-INNER = 2\n"
            '            DISPLAY "NESTED"\n'
            "        END-IF\n"
            "    ELSE\n"
            '        DISPLAY "OUTER-ELSE"\n'
            "    END-IF.\n"
            "    STOP RUN.\n"
        )
        _, instrs = _build(source)

        conditions = [i for i in instrs if isinstance(i, IRIf)]
        assert {c.left for c in conditions} == {"WS-OUTER", "WS-INNER"}

        moves = [i for i in instrs if isinstance(i, IRMove)]
        assert any(m.result == "WS-FLAG" for m in moves)

        displays = [i for i in instrs if isinstance(i, IRDisplay)]
        assert {d.operand for d in displays} == {'"NESTED"', '"OUTER-ELSE"'}


class TestLoopMapping:
    """PERFORM UNTIL: condition preservation and body ordering."""

    def test_perform_until_condition_preserved(self) -> None:
        _, instrs = _build(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            '    PERFORM UNTIL WS-DONE = "Y" DISPLAY "LOOP" END-PERFORM.\n'
            "    STOP RUN.\n"
        )
        loop = next(i for i in instrs if isinstance(i, IRPerformUntil))
        assert loop.left == "WS-DONE"
        assert loop.operator == "="  # raw COBOL operator, not normalized
        assert loop.right == '"Y"'

    def test_perform_until_body_ordering_preserved(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    PERFORM UNTIL WS-DONE = 1\n"
            "        ADD 1 TO WS-COUNT\n"
            "        DISPLAY WS-COUNT\n"
            "    END-PERFORM.\n"
            "    STOP RUN.\n"
        )
        _, instrs = _build(source)
        kinds = [type(i).__name__ for i in instrs]
        # ADD must appear before its own DISPLAY, in source order.
        assert kinds.index("IRAdd") < kinds.index("IRDisplay")


class TestPerformMapping:
    """PERFORM <paragraph>: target operand and control-flow meaning."""

    def test_inline_perform_target_preserved(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    PERFORM SUB1.\n    STOP RUN.\n"
            'SUB1.\n    DISPLAY "IN-SUB".\n'
        )
        _, instrs = _build(source)
        call = next(i for i in instrs if isinstance(i, IRCall) and i.target == "SUB1")
        assert call.args == ()


class TestCallMapping:
    """CALL: target operand, USING arguments."""

    def test_call_target_and_arguments(self) -> None:
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            '    CALL "SUBPROG" USING WS-A WS-B.\n    STOP RUN.\n'
        )
        _, instrs = _build(source)
        call = next(
            i for i in instrs if isinstance(i, IRCall) and i.target == "SUBPROG"
        )
        assert call.args == ("WS-A", "WS-B")

    def test_call_without_arguments(self) -> None:
        source = (
            _ID + 'PROCEDURE DIVISION.\nMAIN.\n    CALL "SUBPROG".\n    STOP RUN.\n'
        )
        _, instrs = _build(source)
        call = next(
            i for i in instrs if isinstance(i, IRCall) and i.target == "SUBPROG"
        )
        assert call.args == ()


class TestDisplayAcceptMapping:
    """
    DISPLAY: represented in IR from real source.

    ACCEPT: the IR mapping (``build_accept_instruction`` -> ``IRAccept``)
    exists and works (verified directly in ``TestAcceptUnreachableFromParser``
    below -- GO TO shared this same "IR-ready, parser-unreachable" status
    until task #stage17 fixed it) but is no longer reachable from real
    COBOL source: task #108 deliberately moved ``ACCEPT`` into the
    parser's unsupported-statement set to fix
    a phantom-paragraph/syntax-error bug, which means the parser can no
    longer construct an ``AcceptStatementNode`` at all. This is
    confirmed below and must not be mistaken for a #109 IR gap.
    """

    def test_display_is_represented(self) -> None:
        _, instrs = _build(
            _ID + 'PROCEDURE DIVISION.\nMAIN.\n    DISPLAY "HELLO".\n    STOP RUN.\n'
        )
        assert any(isinstance(i, IRDisplay) and i.operand == '"HELLO"' for i in instrs)

    def test_accept_is_explicitly_diagnosed_not_silently_lost(self) -> None:
        """
        Real ACCEPT syntax produces an explicit UNSUPPORTED diagnostic
        (task #108, SYN100) rather than either a syntax error or a
        silently-dropped statement -- confirming the parser-side half
        of ACCEPT's status is exactly as documented.
        """
        program, instrs = _build(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n    ACCEPT WS-INPUT.\n    STOP RUN.\n"
        )
        assert not any(isinstance(i, IRAccept) for i in instrs)
        paragraph = program.procedure_division.paragraphs[0]
        assert not any(
            isinstance(s, ast_statements.AcceptStatementNode)
            for s in paragraph.statements
        )


class TestReturnAndExitMapping:
    """
    GOBACK / STOP RUN: the confirmed #109 node-loss fix.

    Before this task, both statement types reached
    ``_translate_statement``'s generic "unsupported statement type"
    fallback and produced *no* IR instruction at all -- despite
    ``IRReturn`` existing in the instruction set specifically for this
    purpose.  Every fixture used throughout this project's prior tasks
    ends in ``STOP RUN.``, so this bug affected essentially every
    program ever analysed.
    """

    def test_stop_run_produces_ir_return(self) -> None:
        _, instrs = _build(_ID + "PROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n")
        returns = [i for i in instrs if isinstance(i, IRReturn)]
        assert len(returns) == 1
        assert returns[0].comment == "STOP RUN"

    def test_goback_produces_ir_return(self) -> None:
        _, instrs = _build(_ID + "PROCEDURE DIVISION.\nMAIN.\n    GOBACK.\n")
        returns = [i for i in instrs if isinstance(i, IRReturn)]
        assert len(returns) == 1
        assert returns[0].comment == "GOBACK"

    def test_stop_run_and_goback_are_distinguishable(self) -> None:
        """
        Both lower to the identically-shaped IRReturn(operand=""), so
        the ``comment`` field is what lets downstream analysis (task
        #110) tell a program-terminating STOP RUN apart from a
        caller-returning GOBACK.
        """
        _, stop_instrs = _build(_ID + "PROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n")
        _, goback_instrs = _build(_ID + "PROCEDURE DIVISION.\nMAIN.\n    GOBACK.\n")

        stop_return = next(i for i in stop_instrs if isinstance(i, IRReturn))
        goback_return = next(i for i in goback_instrs if isinstance(i, IRReturn))

        assert stop_return.comment != goback_return.comment


def _empty_semantic_context() -> Any:
    """A minimal, valid SemanticContext for direct IRBuilder unit tests."""
    from app.parser.semantic.context import SemanticContext, SymbolTable

    return SemanticContext(symbol_table=SymbolTable(), diagnostics=[])


class TestGoToLowersDirectlyAndAcceptStillUnreachable:
    """
    GO TO: the IR mapping (``build_go_to_statement`` -> ``IRJump``)
    existed since before task #109 and is proven here two ways -- direct
    AST construction (unaffected by any parser change) and, since task
    #stage17 gave the parser a dispatch path for ``GO TO``, from real
    source too (``test_parser_now_produces_goto_from_real_source``).

    ACCEPT: still unreachable from real source (task #108's deliberate,
    untouched decision) -- proven here by direct AST construction only;
    the parser-side proof is
    ``TestDisplayAcceptMapping.test_accept_is_explicitly_diagnosed_not_silently_lost``
    above.
    """

    def test_goto_ast_node_lowers_to_ir_jump_directly(self) -> None:
        pos = Position(line=1, column=1, offset=0, filename="t.cbl")
        node = ast_statements.GoToStatementNode(
            start_position=pos, end_position=pos, target="SOME-PARA"
        )
        builder = IRBuilder(context=_empty_semantic_context())
        result = builder._translate_statement(node)  # noqa: SLF001

        assert result is None  # build_go_to_statement appends, returns nothing
        assert any(
            isinstance(i, IRJump) and i.target == "SOME-PARA"
            for i in builder._current_instructions  # noqa: SLF001
        )

    def test_accept_ast_node_lowers_to_ir_accept_directly(self) -> None:
        pos = Position(line=1, column=1, offset=0, filename="t.cbl")
        node = ast_statements.AcceptStatementNode(
            start_position=pos, end_position=pos, target="WS-INPUT"
        )
        builder = IRBuilder(context=_empty_semantic_context())
        result = builder._translate_statement(node)  # noqa: SLF001

        assert isinstance(result, IRAccept)
        assert result.result == "WS-INPUT"

    def test_parser_now_produces_goto_from_real_source(self) -> None:
        """
        Confirms the task #stage17 fix: real ``GO TO`` syntax now reaches
        the AST as a ``GoToStatementNode`` and lowers to a real ``IRJump``
        -- the opposite of this test's pre-#stage17 name and assertions
        (``test_parser_cannot_produce_goto_from_real_source``), kept here
        under its old name's former location so the file's git history
        stays legible about exactly what changed.
        """
        program, instrs = _build(
            _ID + "PROCEDURE DIVISION.\nMAIN.\n    GO TO OTHER-PARA.\n    STOP RUN.\n"
        )
        assert any(isinstance(i, IRJump) and i.target == "OTHER-PARA" for i in instrs)
        paragraph = program.procedure_division.paragraphs[0]
        assert any(
            isinstance(s, ast_statements.GoToStatementNode) and s.target == "OTHER-PARA"
            for s in paragraph.statements
        )
