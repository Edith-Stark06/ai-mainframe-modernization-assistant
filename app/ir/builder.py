"""
IR Builder — AST-to-IR Translation with MOVE Statement Lowering.

Purpose:
    Provide :class:`IRBuilder` — the primary entry point for the AST-to-IR
    translation pipeline.  The builder accepts a validated
    :class:`~app.parser.semantic.context.SemanticContext` and an optional
    :class:`~app.parser.ast.program.ProgramNode`, and translates the COBOL
    program structure (TASK-025) plus executable MOVE statements (TASK-026)
    into a complete :class:`~app.ir.program.IRProgram`.

    TASK-025 established the structural translation framework:
        * One :class:`~app.ir.program.IRModule` per COBOL program.
        * One :class:`~app.ir.program.IRFunction` (``"__entry__"``) per module.
        * One :class:`~app.ir.blocks.IRBasicBlock` (``"entry"``) per function.

    TASK-026 extends the builder to lower executable COBOL ``MOVE`` statements
    into :class:`~app.ir.instructions.IRMove` instructions and append them to
    the entry basic block in source order.

    The builder also introduces reusable operand-translation helpers
    (:meth:`build_operand`, :meth:`build_variable_reference`,
    :meth:`build_literal`) designed for reuse by future arithmetic and CALL
    translation passes.

Translation pipeline::

    ProgramNode + SemanticContext
         │
         ▼  build(program_node)
    IRProgram                       ← build_program()
         │
         ▼  (one per ProgramSymbol)
    IRModule                        ← build_module()
         │
         ▼  (always one entry function)
    IRFunction("__entry__")         ← build_function()
         │
         ▼  (entry block with translated MOVE statements)
    IRBasicBlock("entry")           ← build_entry_block(procedure_division)
         │
         ├── IRMove(source, result)  ← build_move_instruction()
         ├── IRMove(source, result)
         ╎   ...
         └── (future: DISPLAY, CALL, arithmetic, IF, PERFORM, GO TO)

Operand translation::

    COBOL operand text
         │
         ▼  build_operand(text)
         ├── if quoted string ("...") → build_literal() → literal text
         ├── if numeric literal       → build_literal() → literal text
         └── if identifier            → build_variable_reference() → var name

Responsibilities:
    - Validate the supplied :class:`~app.parser.semantic.context.SemanticContext`.
    - Accept an optional :class:`~app.parser.ast.program.ProgramNode`; when
      provided, walk its PROCEDURE DIVISION and translate every currently
      supported statement type: MOVE, DISPLAY, ACCEPT, ADD, SUBTRACT,
      MULTIPLY, DIVIDE, IF (with nested statements and ELSE), PERFORM,
      PERFORM UNTIL, GO TO, CALL, STOP RUN, and GOBACK (task #109 audit
      and completeness pass; see ``_translate_statement`` for the exact
      dispatch and ``tests/ir/test_ir_ast_node_coverage.py`` for the full
      AST -> IR mapping matrix, including which of these are actually
      reachable from real COBOL source today).
    - Stamp every emitted instruction with the source position of the AST
      statement it came from and the name of the enclosing paragraph
      (task #109; see :meth:`_emit` and
      :attr:`~app.ir.instructions.IRInstruction.source_position` /
      :attr:`~app.ir.instructions.IRInstruction.paragraph`).
    - Emit a structured IR translation warning for unsupported statements while
      continuing translation.
    - Expose reusable operand helpers: :meth:`build_operand`,
      :meth:`build_variable_reference`, :meth:`build_literal`.
    - Remain stateless between :meth:`build` calls.
    - Log lifecycle events via Loguru.

Non-responsibilities:
    - EVALUATE, OPEN/CLOSE/READ/WRITE, COMPUTE, STRING/UNSTRING/INSPECT,
      and every other verb the parser itself classifies as unsupported
      (task #105/#108) -- these have no AST representation to translate,
      so there is nothing for this module to lose; see task #108's audit
      for the parser-side accounting of these.
    - Java code generation.
    - Re-parsing identifiers (uses resolved symbols from SymbolTable).
    - Optimisation passes.

Architectural note -- why paragraphs and IF/PERFORM branches are NOT
split into separate IRBasicBlock/IRFunction instances (task #109):
    The IR model already supports it structurally --
    :class:`~app.ir.program.IRFunction` holds a tuple of
    :class:`~app.ir.blocks.IRBasicBlock` objects, and
    :class:`~app.ir.instructions.IRConditionalBranch` /
    :class:`~app.ir.instructions.IRJump` already exist for wiring blocks
    together -- and one IRFunction per paragraph would be the more
    natural mapping (see :class:`~app.ir.program.IRFunction`'s own
    docstring). It was deliberately not done, because
    :mod:`app.backend.java.generator` and
    :func:`app.backend.java.generator._collect_statements` currently
    read only ``module.functions[0]`` and ``function.blocks[0]`` --
    splitting either would silently drop every paragraph/branch after
    the first from generated Java output, and fixing that is a Java
    generation change explicitly out of task #109/#110's scope.

    Instead, paragraph identity and structured control flow (IF/ELSE,
    PERFORM UNTIL) are preserved *within* the single flat block: every
    instruction is stamped with its paragraph (see above), and IF/ELSE/
    PERFORM UNTIL still lower to the existing ``IRIf``/``IRElse``/
    ``IREndIf``/``IRPerformUntil``/``IREndPerform`` marker instructions
    (unchanged from before task #109) that the Java backend already
    consumes correctly. Task #110's control-flow graph is built by
    interpreting this marker sequence as a downstream analysis pass,
    rather than by restructuring the IR itself -- see
    :mod:`app.modernization.flow.generator`.

Dependencies:
    - :mod:`app.parser.semantic.context`     — ``SemanticContext``.
    - :mod:`app.parser.semantic.symbols`     — ``ProgramSymbol``, ``SymbolKind``.
    - :mod:`app.parser.ast.program`          — ``ProgramNode`` (TYPE_CHECKING).
    - :mod:`app.parser.ast.procedure`        — ``ProcedureDivisionNode``
                                               (TYPE_CHECKING).
    - :mod:`app.parser.ast.statements`       — ``MoveStatementNode``
                                               (TYPE_CHECKING).
    - :mod:`app.ir.blocks`                   — ``IRBasicBlock``.
    - :mod:`app.ir.instructions`             — ``IRMove``.
    - :mod:`app.ir.program`                  — ``IRProgram``, ``IRModule``,
                                               ``IRFunction``.
    - Loguru for structured logging.

Examples:
    Translating a program with MOVE statements::

        from app.parser.lexer.position import Position
        from app.parser.ast.program import ProgramNode
        from app.parser.ast.procedure import ProcedureDivisionNode
        from app.parser.ast.paragraphs import ParagraphNode
        from app.parser.ast.statements import MoveStatementNode
        from app.parser.semantic.context import SemanticContext, SymbolTable
        from app.parser.semantic.symbols import ProgramSymbol
        from app.ir.builder import IRBuilder

        pos = Position(line=1, column=1, offset=0, filename="p.cbl")
        move = MoveStatementNode(
            start_position=pos, end_position=pos,
            source="WS-IN", target="WS-OUT",
        )
        para = ParagraphNode(
            start_position=pos, end_position=pos,
            name="MAIN-PARA", statements=(move,),
        )
        proc = ProcedureDivisionNode(
            start_position=pos, end_position=pos, paragraphs=(para,),
        )
        program_node = ProgramNode(
            start_position=pos, end_position=pos,
            procedure_division=proc,
        )
        table = SymbolTable()
        table.register(ProgramSymbol(name="PAYROLL", declared_at=pos))
        ctx = SemanticContext(symbol_table=table, diagnostics=[])

        prog = IRBuilder(context=ctx).build(program_node)
        bb = prog.modules[0].functions[0].blocks[0]
        bb.instructions[0]  # IRMove(source='WS-IN', result='WS-OUT')

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, TypeVar

from loguru import logger

from app.ir.blocks import IRBasicBlock
from app.ir.instructions import (
    IREndIf,
    IRIf,
    IRElse,
    IRPerformUntil,
    IREndPerform,
    IRAccept,
    IRAdd,
    IRCall,
    IRDisplay,
    IRDivide,
    IRInstruction,
    IRJump,
    IRMove,
    IRMultiply,
    IRReturn,
    IRSubtract,
)
from app.ir.program import IRFunction, IRModule, IRProgram
from app.parser.lexer.position import Position
from app.parser.semantic.context import SemanticContext
from app.parser.semantic.symbols import ProgramSymbol, SymbolKind
from app.parser.semantic.diagnostics import SemanticDiagnostic, SemanticSeverity

if TYPE_CHECKING:
    from app.parser.ast.paragraphs import ParagraphNode
    from app.parser.ast.procedure import ProcedureDivisionNode
    from app.parser.ast.program import ProgramNode
    from app.parser.ast.statements import (
        PerformUntilStatementNode,
        AcceptStatementNode,
        AddStatementNode,
        CallStatementNode,
        DisplayStatementNode,
        DivideStatementNode,
        GoToStatementNode,
        IfStatementNode,
        MoveStatementNode,
        MultiplyStatementNode,
        PerformStatementNode,
        StatementNode,
        StopRunStatementNode,
        GobackStatementNode,
        SubtractStatementNode,
    )

__all__ = ["IRBuilder"]

_InstrT = TypeVar("_InstrT", bound=IRInstruction)

# Name used for the top-level entry function in every generated module.
_ENTRY_FUNCTION_NAME: str = "__entry__"

# Label for the entry basic block of the entry function.
_ENTRY_BLOCK_LABEL: str = "entry"


class IRBuilder:
    """
    Translate a validated :class:`~app.parser.semantic.context.SemanticContext`
    and optional :class:`~app.parser.ast.program.ProgramNode` into an
    :class:`~app.ir.program.IRProgram`.

    **TASK-025 + TASK-026 translation scope:**

    +----------------------------+-------------------------------+
    | Input element              | Output IR                     |
    +============================+===============================+
    | ``SemanticContext``        | ``IRProgram``                 |
    +----------------------------+-------------------------------+
    | ``ProgramSymbol`` (or      | ``IRModule``                  |
    | absence thereof)           |                               |
    +----------------------------+-------------------------------+
    | Module (always one)        | ``IRFunction("__entry__")``   |
    +----------------------------+-------------------------------+
    | Entry function (always)    | ``IRBasicBlock("entry")``     |
    +----------------------------+-------------------------------+
    | ``MoveStatementNode``      | ``IRMove(source, result)``    |
    +----------------------------+-------------------------------+
    | ``DisplayStatementNode``   | ``IRDisplay(operand)``        |
    +----------------------------+-------------------------------+
    | ``AcceptStatementNode``    | ``IRAccept(result)``          |
    +----------------------------+-------------------------------+
    | Unsupported statements     | Warning log + skip            |
    +----------------------------+-------------------------------+

    The builder is **stateless** between :meth:`build` calls — each call
    constructs and returns a fresh :class:`~app.ir.program.IRProgram` without
    modifying any instance state.

    Attributes:
        _context:
            The :class:`~app.parser.semantic.context.SemanticContext` supplied
            at construction time.

    Examples:
        >>> from app.parser.semantic.context import SemanticContext, SymbolTable
        >>> from app.ir.builder import IRBuilder
        >>> ctx = SemanticContext(symbol_table=SymbolTable(), diagnostics=[])
        >>> prog = IRBuilder(context=ctx).build()
        >>> isinstance(prog, IRProgram)
        True
        >>> prog.modules[0].functions[0].blocks[0].instructions
        ()
    """

    def __init__(self, context: SemanticContext) -> None:
        """
        Initialise the builder with a validated semantic context.

        Args:
            context:
                The :class:`~app.parser.semantic.context.SemanticContext`
                produced by
                :class:`~app.parser.semantic.analyzer.SemanticAnalyzer`.
                Must be a :class:`~app.parser.semantic.context.SemanticContext`
                instance.

        Raises:
            TypeError: If *context* is not a
                :class:`~app.parser.semantic.context.SemanticContext`.
        """
        if not isinstance(context, SemanticContext):
            raise TypeError(
                f"context must be a SemanticContext, got {type(context).__name__}"
            )
        self._context = context
        self._blocks: list[IRBasicBlock] = []
        self._current_instructions: list[IRInstruction] = []
        self._current_label: str = _ENTRY_BLOCK_LABEL
        self._block_counter: int = 0
        self._current_paragraph: str = ""
        logger.debug("IRBuilder: initialised with semantic context.")

        if context.has_errors:
            logger.warning(
                "IRBuilder: semantic context contains {} error(s); "
                "resulting IR may be incomplete.",
                context.error_count,
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def context(self) -> SemanticContext:
        """
        Return the :class:`~app.parser.semantic.context.SemanticContext`
        supplied at construction time.

        Returns:
            The semantic context.
        """
        return self._context

    def build(self, program_node: ProgramNode | None = None) -> IRProgram:
        """
        Translate the semantic context into a fully-structured
        :class:`~app.ir.program.IRProgram`.

        When *program_node* is supplied the builder walks the
        ``PROCEDURE DIVISION`` and emits
        :class:`~app.ir.instructions.IRMove` instructions for every
        ``MOVE`` statement encountered.  When *program_node* is ``None``
        (or has no ``PROCEDURE DIVISION``) the entry basic block is empty.

        The method is safe to call multiple times; each call returns a new,
        independent :class:`~app.ir.program.IRProgram`.

        Args:
            program_node:
                Optional :class:`~app.parser.ast.program.ProgramNode` whose
                ``PROCEDURE DIVISION`` should be translated.  Pass ``None``
                to generate the structural IR skeleton only.

        Returns:
            A complete :class:`~app.ir.program.IRProgram` reflecting the
            structural content of the semantic context and, if supplied,
            the executable MOVE statements in the program node.
        """
        prog_name = self._program_name()
        proc_div = self._extract_procedure_division(program_node)
        logger.debug(
            "IRBuilder.build(): program_name={!r}, procedure_division={!r}.",
            prog_name,
            type(proc_div).__name__ if proc_div is not None else "None",
        )
        program = self.build_program(prog_name, proc_div)
        logger.debug(
            "IRBuilder.build(): built IRProgram with {} module(s).", len(program)
        )
        return program

    def current_program(self, program_node: ProgramNode | None = None) -> IRProgram:
        """
        Return the :class:`~app.ir.program.IRProgram` constructed so far.

        This method is a convenience accessor for incremental builders that
        emit IR in stages.  It delegates to :meth:`build`.

        Args:
            program_node:
                Optional :class:`~app.parser.ast.program.ProgramNode` passed
                through to :meth:`build`.

        Returns:
            The partially or fully constructed
            :class:`~app.ir.program.IRProgram`.
        """
        return self.build(program_node)

    # ------------------------------------------------------------------
    # Structural helpers — one per IR node level
    # ------------------------------------------------------------------

    def build_program(
        self,
        prog_name: str,
        proc_div: ProcedureDivisionNode | None = None,
    ) -> IRProgram:
        """
        Construct the top-level :class:`~app.ir.program.IRProgram`.

        Creates exactly one :class:`~app.ir.program.IRModule` by calling
        :meth:`build_module`.

        Args:
            prog_name:
                Human-readable program name (from the PROGRAM-ID clause or
                the empty string if absent).
            proc_div:
                Optional :class:`~app.parser.ast.procedure.ProcedureDivisionNode`
                to translate.

        Returns:
            A :class:`~app.ir.program.IRProgram` containing one module.
        """
        module = self.build_module(self._module_name(prog_name), proc_div)
        logger.debug("IRBuilder.build_program(): module name={!r}.", module.name)
        return IRProgram(name=prog_name, modules=(module,))

    def build_module(
        self,
        module_name: str,
        proc_div: ProcedureDivisionNode | None = None,
    ) -> IRModule:
        """
        Construct an :class:`~app.ir.program.IRModule` for a single COBOL
        program or compilation unit.

        Creates exactly one :class:`~app.ir.program.IRFunction` by calling
        :meth:`build_function`.

        Args:
            module_name:
                Human-readable module name.
            proc_div:
                Optional :class:`~app.parser.ast.procedure.ProcedureDivisionNode`
                to translate.

        Returns:
            An :class:`~app.ir.program.IRModule` containing one entry function.
        """
        function = self.build_function(self._function_name(), proc_div)
        logger.debug("IRBuilder.build_module(): function name={!r}.", function.name)
        return IRModule(name=module_name, functions=(function,))

    def build_function(
        self,
        function_name: str,
        proc_div: ProcedureDivisionNode | None = None,
    ) -> IRFunction:
        """
        Construct the entry :class:`~app.ir.program.IRFunction`.

        Creates one :class:`~app.ir.blocks.IRBasicBlock` by calling
        :meth:`build_entry_block`.  The block is populated with
        :class:`~app.ir.instructions.IRMove` instructions derived from
        the MOVE statements found in *proc_div* (if supplied).

        Args:
            function_name:
                Name of the function.
            proc_div:
                Optional :class:`~app.parser.ast.procedure.ProcedureDivisionNode`
                to translate.

        Returns:
            An :class:`~app.ir.program.IRFunction` containing one entry block.
        """
        entry_block = self.build_entry_block(proc_div)
        blocks = tuple(self._blocks) if self._blocks else (entry_block,)
        logger.debug(
            "IRBuilder.build_function(): entry block label={!r}, " "total blocks={}.",
            blocks[0].label,
            len(blocks),
        )
        return IRFunction(name=function_name, blocks=blocks)

    def build_entry_block(
        self,
        proc_div: ProcedureDivisionNode | None = None,
    ) -> IRBasicBlock:
        """
        Construct the entry :class:`~app.ir.blocks.IRBasicBlock`.

        When *proc_div* is supplied the builder iterates all paragraphs and
        their statements in source order, translating every currently
        supported statement type (see
        :meth:`_translate_statement` for the exact dispatch and
        :mod:`app.ir.builder`'s module docstring for the AST-to-IR
        coverage matrix).  Unsupported statement types emit a
        ``DEBUG``-level log and are skipped; translation continues.

        Every emitted instruction is stamped (task #109) with the source
        position of the AST statement it came from and the name of the
        paragraph it belongs to, via :meth:`_emit`.

        Remaining known gap (task #109; documented, not fixed here):
        EVALUATE has no AST representation at all yet, so it cannot be
        translated regardless of this block's structure.

        Args:
            proc_div:
                Optional :class:`~app.parser.ast.procedure.ProcedureDivisionNode`
                whose paragraphs and statements are translated.

        Returns:
            An :class:`~app.ir.blocks.IRBasicBlock` labelled ``"entry"``
            containing zero or more :class:`~app.ir.instructions.IRInstruction`
            instructions.
        """
        self._blocks = []
        self._current_instructions = []
        self._current_label = _ENTRY_BLOCK_LABEL
        self._block_counter = 0
        self._current_paragraph = ""

        if proc_div is not None:
            for para in proc_div.paragraphs:
                self._translate_paragraph(para)

        self._flush_block()
        blocks = tuple(self._blocks)

        logger.debug(
            "IRBuilder.build_entry_block(): emitted {} blocks.",
            len(blocks),
        )
        # To not break tests that expect a single block from build_entry_block,
        # we return the first block (which is always the entry block).
        # Functions should use blocks from `_blocks` in build_function.
        return (
            blocks[0]
            if blocks
            else IRBasicBlock(label=_ENTRY_BLOCK_LABEL, instructions=())
        )

    # ------------------------------------------------------------------
    # Block management
    # ------------------------------------------------------------------

    def _generate_label(self, prefix: str) -> str:
        self._block_counter += 1
        return f"{prefix}_{self._block_counter}"

    def _flush_block(self) -> None:
        block = IRBasicBlock(
            label=self._current_label,
            instructions=tuple(self._current_instructions),
        )
        self._blocks.append(block)
        self._current_instructions = []

    def _start_block(self, label: str) -> None:
        self._flush_block()
        self._current_label = label

    def _emit(self, instr: _InstrT, position: Position | None = None) -> _InstrT:
        """
        Stamp *instr* with the current paragraph/source position and append it.

        Centralising the stamp-and-append step here (task #109) means
        every emission site records source mapping and paragraph
        identity the same way, rather than each ``build_*_instruction``
        method needing to remember to do it individually.  Since
        :class:`~app.ir.instructions.IRInstruction` is frozen,
        stamping is done via :func:`dataclasses.replace`, producing a
        new instance rather than mutating *instr*.

        Args:
            instr:
                The instruction to stamp and append.
            position:
                The AST position this instruction was lowered from, or
                ``None`` for structural marker instructions
                (:class:`~app.ir.instructions.IRElse`,
                :class:`~app.ir.instructions.IREndIf`,
                :class:`~app.ir.instructions.IREndPerform`) that have no
                position of their own; callers should pass the enclosing
                statement's position for those instead of leaving this
                unset.

        Returns:
            The stamped instruction, already appended to
            ``self._current_instructions``.
        """
        stamped = dataclasses.replace(
            instr,
            source_position=position,
            paragraph=self._current_paragraph,
        )
        self._current_instructions.append(stamped)
        return stamped

    # ------------------------------------------------------------------
    # Statement translation helpers
    # ------------------------------------------------------------------

    def _translate_paragraph(self, para: ParagraphNode) -> None:
        """
        Translate supported statements in a paragraph into IR instructions.

        Unsupported statements are logged at DEBUG level and skipped.

        Sets :attr:`_current_paragraph` for the duration of the call so
        that every instruction emitted for this paragraph's statements
        is stamped with its paragraph identity (task #109), and restores
        the previous value afterwards -- COBOL paragraphs do not nest,
        but this keeps the method correct even if it is ever called
        recursively.

        Args:
            para:
                The :class:`~app.parser.ast.paragraphs.ParagraphNode` to
                translate.
        """
        previous_paragraph = self._current_paragraph
        self._current_paragraph = para.name
        try:
            for stmt in para.statements:
                self._translate_statement(stmt)
        finally:
            self._current_paragraph = previous_paragraph

    def _translate_statement(self, stmt: StatementNode) -> IRInstruction | None:
        """
        Translate a single statement into an IR instruction.

        Currently only :class:`~app.parser.ast.statements.MoveStatementNode`
        is handled.  All other statement types are logged and skipped,
        returning ``None``.

        Args:
            stmt:
                The :class:`~app.parser.ast.statements.StatementNode` to
                translate.

        Returns:
            An :class:`~app.ir.instructions.IRInstruction` if the statement was
            supported; ``None`` otherwise.
        """
        from app.parser.ast.statements import (
            AcceptStatementNode,
            AddStatementNode,
            CallStatementNode,
            DisplayStatementNode,
            DivideStatementNode,
            GobackStatementNode,
            GoToStatementNode,
            IfStatementNode,
            MoveStatementNode,
            MultiplyStatementNode,
            PerformStatementNode,
            PerformUntilStatementNode,
            StopRunStatementNode,
            SubtractStatementNode,
        )

        if isinstance(stmt, MoveStatementNode):
            instr_move = self.build_move_instruction(stmt)
            if instr_move:
                instr_move = self._emit(instr_move, stmt.start_position)
            return instr_move
        if isinstance(stmt, DisplayStatementNode):
            instr_disp = self.build_display_instruction(stmt)
            if instr_disp:
                instr_disp = self._emit(instr_disp, stmt.start_position)
            return instr_disp
        if isinstance(stmt, AcceptStatementNode):
            instr_acc = self.build_accept_instruction(stmt)
            if instr_acc:
                instr_acc = self._emit(instr_acc, stmt.start_position)
            return instr_acc
        if isinstance(stmt, AddStatementNode):
            instr_add = self.build_add_instruction(stmt)
            if instr_add:
                instr_add = self._emit(instr_add, stmt.start_position)
            return instr_add
        if isinstance(stmt, SubtractStatementNode):
            instr_sub = self.build_subtract_instruction(stmt)
            if instr_sub:
                instr_sub = self._emit(instr_sub, stmt.start_position)
            return instr_sub
        if isinstance(stmt, MultiplyStatementNode):
            instr_mul = self.build_multiply_instruction(stmt)
            if instr_mul:
                instr_mul = self._emit(instr_mul, stmt.start_position)
            return instr_mul
        if isinstance(stmt, DivideStatementNode):
            instr_div = self.build_divide_instruction(stmt)
            if instr_div:
                instr_div = self._emit(instr_div, stmt.start_position)
            return instr_div
        if isinstance(stmt, IfStatementNode):
            self.build_if_statement(stmt)
            return None
        if isinstance(stmt, PerformStatementNode):
            self.build_perform_statement(stmt)
            return None
        if isinstance(stmt, PerformUntilStatementNode):
            self.build_perform_until_statement(stmt)
            return None
        if isinstance(stmt, GoToStatementNode):
            self.build_go_to_statement(stmt)
            return None
        if isinstance(stmt, CallStatementNode):
            instr_call = self.build_call_instruction(stmt)
            if instr_call:
                instr_call = self._emit(instr_call, stmt.start_position)
            return instr_call
        if isinstance(stmt, StopRunStatementNode):
            # task #109, confirmed AST-node-loss fix: STOP RUN previously
            # fell through to the generic "unsupported" log below and
            # produced no IR instruction at all, despite IRReturn
            # existing specifically for this purpose.
            instr_stop = self.build_stop_run_instruction(stmt)
            instr_stop = self._emit(instr_stop, stmt.start_position)
            return instr_stop
        if isinstance(stmt, GobackStatementNode):
            # task #109, same fix as StopRunStatementNode above.
            instr_goback = self.build_goback_instruction(stmt)
            instr_goback = self._emit(instr_goback, stmt.start_position)
            return instr_goback

        logger.debug(
            "IRBuilder._translate_statement(): skipping unsupported "
            "statement type {!r}.",
            type(stmt).__name__,
        )
        return None

    def build_move_instruction(self, stmt: MoveStatementNode) -> IRMove:
        """
        Lower a single ``MoveStatementNode`` into an
        :class:`~app.ir.instructions.IRMove`.

        The COBOL ``MOVE source TO target`` maps to::

            IRMove(source=build_operand(source), result=build_operand(target))

        Args:
            stmt:
                The :class:`~app.parser.ast.statements.MoveStatementNode`
                to lower.

        Returns:
            An :class:`~app.ir.instructions.IRMove` instruction.
        """
        ir_source = self.build_operand(stmt.source)
        ir_target = self.build_operand(stmt.target)
        logger.debug(
            "IRBuilder.build_move_instruction(): MOVE {!r} TO {!r} "
            "→ IRMove(source={!r}, result={!r}).",
            stmt.source,
            stmt.target,
            ir_source,
            ir_target,
        )
        return IRMove(source=ir_source, result=ir_target)

    def build_display_instruction(self, stmt: DisplayStatementNode) -> IRDisplay:
        """
        Lower a single ``DisplayStatementNode`` into an
        :class:`~app.ir.instructions.IRDisplay`.

        Args:
            stmt:
                The :class:`~app.parser.ast.statements.DisplayStatementNode`
                to lower.

        Returns:
            An :class:`~app.ir.instructions.IRDisplay` instruction.
        """
        ir_operand = self.build_operand(stmt.operand)
        logger.debug(
            "IRBuilder.build_display_instruction(): DISPLAY {!r} "
            "→ IRDisplay(operand={!r}).",
            stmt.operand,
            ir_operand,
        )
        return IRDisplay(operand=ir_operand)

    def build_accept_instruction(self, stmt: AcceptStatementNode) -> IRAccept:
        """
        Lower a single ``AcceptStatementNode`` into an
        :class:`~app.ir.instructions.IRAccept`.

        Args:
            stmt:
                The :class:`~app.parser.ast.statements.AcceptStatementNode`
                to lower.

        Returns:
            An :class:`~app.ir.instructions.IRAccept` instruction.
        """
        ir_target = self.build_variable_reference(stmt.target.strip())
        logger.debug(
            "IRBuilder.build_accept_instruction(): ACCEPT {!r} "
            "→ IRAccept(result={!r}).",
            stmt.target,
            ir_target,
        )
        return IRAccept(result=ir_target)

    def build_add_instruction(self, stmt: AddStatementNode) -> IRAdd:
        ir_left = self.build_operand(stmt.left)
        ir_right = self.build_operand(stmt.right)
        logger.debug(
            "IRBuilder.build_add_instruction(): ADD {!r} TO {!r} → IRAdd(left={!r}, right={!r}).",
            stmt.left,
            stmt.right,
            ir_left,
            ir_right,
        )
        return IRAdd(left=ir_left, right=ir_right, result=ir_right)

    def build_subtract_instruction(self, stmt: SubtractStatementNode) -> IRSubtract:
        ir_left = self.build_operand(stmt.left)
        ir_right = self.build_operand(stmt.right)
        logger.debug(
            "IRBuilder.build_subtract_instruction(): SUBTRACT {!r} FROM {!r} → IRSubtract(left={!r}, right={!r}).",
            stmt.left,
            stmt.right,
            ir_left,
            ir_right,
        )
        return IRSubtract(left=ir_left, right=ir_right, result=ir_right)

    def build_multiply_instruction(self, stmt: MultiplyStatementNode) -> IRMultiply:
        ir_left = self.build_operand(stmt.left)
        ir_right = self.build_operand(stmt.right)
        logger.debug(
            "IRBuilder.build_multiply_instruction(): MULTIPLY {!r} BY {!r} → IRMultiply(left={!r}, right={!r}).",
            stmt.left,
            stmt.right,
            ir_left,
            ir_right,
        )
        return IRMultiply(left=ir_left, right=ir_right, result=ir_right)

    def build_divide_instruction(self, stmt: DivideStatementNode) -> IRDivide:
        ir_left = self.build_operand(stmt.left)
        ir_right = self.build_operand(stmt.right)
        logger.debug(
            "IRBuilder.build_divide_instruction(): DIVIDE {!r} INTO {!r} → IRDivide(left={!r}, right={!r}).",
            stmt.left,
            stmt.right,
            ir_left,
            ir_right,
        )
        return IRDivide(left=ir_left, right=ir_right, result=ir_right)

    def build_if_statement(self, stmt: IfStatementNode) -> None:
        ir_left = self.build_operand(stmt.condition_left)
        ir_right = self.build_operand(stmt.condition_right)
        self._emit(
            IRIf(left=ir_left, operator=stmt.condition_operator, right=ir_right),
            stmt.start_position,
        )
        for then_stmt in stmt.then_statements:
            self._translate_statement(then_stmt)
        if stmt.else_statements:
            self._emit(IRElse(), stmt.start_position)
            for else_stmt in stmt.else_statements:
                self._translate_statement(else_stmt)
        self._emit(IREndIf(), stmt.start_position)

    def build_perform_statement(self, stmt: PerformStatementNode) -> None:
        """
        Lower a single ``PerformStatementNode`` into an ``IRCall``.

        Tagged ``comment="PERFORM"`` (task #110) so that
        control-flow-graph construction can tell a PERFORM apart from a
        genuine :class:`~app.parser.ast.statements.CallStatementNode`
        (see :meth:`build_call_instruction`) once both have lowered to
        the identically-shaped ``IRCall`` -- without this, a PERFORM to
        a paragraph name that does not resolve locally was
        indistinguishable from, and mis-treated as, an external CALL.
        """
        if not stmt.target:
            logger.warning("Unsupported PERFORM form: missing target. Continuing.")
        else:
            self._emit(
                IRCall(target=stmt.target, comment="PERFORM"), stmt.start_position
            )

    def build_go_to_statement(self, stmt: GoToStatementNode) -> None:
        """
        Lower a single ``GoToStatementNode`` into an ``IRJump``.
        """
        if not stmt.target:
            logger.warning("Unresolved target in GO TO statement. Continuing.")
        else:
            self._emit(IRJump(target=stmt.target), stmt.start_position)

    def build_stop_run_instruction(self, stmt: StopRunStatementNode) -> IRReturn:
        """
        Lower a single ``StopRunStatementNode`` into an ``IRReturn``.

        ``STOP RUN`` terminates the whole program with no return value,
        so the resulting instruction carries an empty ``operand``.

        Args:
            stmt:
                The :class:`~app.parser.ast.statements.StopRunStatementNode`
                to lower.

        Returns:
            An :class:`~app.ir.instructions.IRReturn` instruction, with
            ``comment="STOP RUN"`` so #110's control-flow analysis can
            distinguish this from :meth:`build_goback_instruction`'s
            identically-shaped result.
        """
        return IRReturn(operand="", comment="STOP RUN")

    def build_goback_instruction(self, stmt: GobackStatementNode) -> IRReturn:
        """
        Lower a single ``GobackStatementNode`` into an ``IRReturn``.

        ``GOBACK`` returns control to the caller with no return value, so
        the resulting instruction carries an empty ``operand`` -- the
        same shape as :meth:`build_stop_run_instruction`.  The two are
        kept as separate methods (rather than one shared helper) because
        they lower distinct AST node types and #110's control-flow
        analysis needs to be able to tell a program-terminating ``STOP
        RUN`` apart from a caller-returning ``GOBACK`` by the *AST* node
        that produced the instruction, even though today's IR shape is
        identical.

        Args:
            stmt:
                The :class:`~app.parser.ast.statements.GobackStatementNode`
                to lower.

        Returns:
            An :class:`~app.ir.instructions.IRReturn` instruction, with
            ``comment="GOBACK"`` so #110's control-flow analysis can
            distinguish this from :meth:`build_stop_run_instruction`'s
            identically-shaped result.
        """
        return IRReturn(operand="", comment="GOBACK")

    # ------------------------------------------------------------------
    # Operand translation helpers (reusable by future passes)
    # ------------------------------------------------------------------

    def build_operand(self, text: str) -> str:
        """
        Translate a raw COBOL operand text token into an IR operand string.

        Classification logic:

        1. If *text* is enclosed in double quotes (``"..."``), treat as a
           string literal → :meth:`build_literal`.
        2. If *text* is a pure numeric string (including leading sign), treat
           as a numeric literal → :meth:`build_literal`.
        3. Otherwise treat as a variable reference → :meth:`build_variable_reference`.

        This classification is intentionally simple and covers the common cases
        present in real COBOL MOVE statements.  Future tasks may enrich this
        with type information from the :class:`SymbolTable`.

        Args:
            text:
                Raw operand text from the AST node (e.g. ``'WS-NAME'``,
                ``'"HELLO"'``, ``'42'``, ``'-1'``).

        Returns:
            A canonical IR operand string.

        Examples:
            >>> b = IRBuilder(context=ctx)
            >>> b.build_operand('"HELLO"')
            '"HELLO"'
            >>> b.build_operand('42')
            '42'
            >>> b.build_operand('WS-COUNT')
            'WS-COUNT'
        """
        stripped = text.strip()
        if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2:
            return self.build_literal(stripped)
        if self._is_numeric_literal(stripped):
            return self.build_literal(stripped)
        return self.build_variable_reference(stripped)

    def build_variable_reference(self, name: str) -> str:
        """
        Translate a COBOL identifier into an IR variable-reference operand.

        The identifier is looked up in the :class:`SymbolTable`.  If found,
        the canonical (registered) name is used; if not found, the uppercased
        text is used as-is and a ``DEBUG`` log is emitted.  No error is raised
        here — semantic validation has already been performed by earlier passes.

        Args:
            name:
                The identifier text from the AST node.

        Returns:
            The canonical IR operand string for this variable.

        Examples:
            >>> b.build_variable_reference('ws-count')
            'WS-COUNT'
        """
        canonical = name.upper()
        sym = self._context.symbol_table.lookup(canonical)
        if sym is not None:
            canonical = sym.name
        else:
            logger.debug(
                "IRBuilder.build_variable_reference(): {!r} not found in "
                "symbol table; using uppercased name as operand.",
                name,
            )
        return canonical

    def build_literal(self, text: str) -> str:
        """
        Translate a COBOL literal token into an IR literal operand.

        The literal is returned as-is (its string form is already the IR
        representation).  Future tasks may convert this to a typed
        ``IRLiteral`` value object.

        Args:
            text:
                The raw literal text (e.g. ``'"HELLO"'``, ``'42'``,
                ``'-1'``).

        Returns:
            The literal text unchanged.

        Examples:
            >>> b.build_literal('"HELLO"')
            '"HELLO"'
            >>> b.build_literal('0')
            '0'
        """
        return text

    # ------------------------------------------------------------------
    # Naming helpers — override to customise naming conventions
    # ------------------------------------------------------------------

    def _program_name(self) -> str:
        """
        Derive the program name from the first
        :class:`~app.parser.semantic.symbols.ProgramSymbol` in the symbol
        table.

        Returns:
            The ``PROGRAM-ID`` name, or ``""`` if no program symbol is
            registered.
        """
        program_symbols = self._context.symbol_table.symbols_of_kind(SymbolKind.PROGRAM)
        if not program_symbols:
            logger.debug("IRBuilder._program_name(): no ProgramSymbol found; using ''.")
            return ""
        prog_sym = program_symbols[0]
        assert isinstance(prog_sym, ProgramSymbol)
        return prog_sym.name

    def _module_name(self, prog_name: str) -> str:
        """
        Derive the module name from the program name.

        By default the module name equals the program name.

        Args:
            prog_name:
                The program name resolved by :meth:`_program_name`.

        Returns:
            The module name string.
        """
        return prog_name

    def _function_name(self) -> str:
        """
        Derive the name for the entry function.

        Returns:
            ``"__entry__"``.
        """
        return _ENTRY_FUNCTION_NAME

    # ------------------------------------------------------------------
    # Private utility
    # ------------------------------------------------------------------

    @staticmethod
    def _is_numeric_literal(text: str) -> bool:
        """
        Return ``True`` if *text* represents a COBOL numeric literal.

        Handles:
        * Plain integers: ``'0'``, ``'42'``, ``'100'``.
        * Signed integers: ``'-1'``, ``'+5'``.
        * Decimal numbers: ``'3.14'``, ``'-0.5'``.

        Args:
            text:
                Stripped operand text.

        Returns:
            ``True`` if *text* is a numeric literal, ``False`` otherwise.
        """
        if not text:
            return False
        candidate = text.lstrip("+-")
        if not candidate:
            return False
        # Allow at most one decimal point.
        parts = candidate.split(".")
        if len(parts) > 2:
            return False
        return all(p.isdigit() for p in parts if p)

    @staticmethod
    def _extract_procedure_division(
        program_node: ProgramNode | None,
    ) -> ProcedureDivisionNode | None:
        """
        Safely extract the ``PROCEDURE DIVISION`` node from *program_node*.

        Args:
            program_node:
                The optional :class:`~app.parser.ast.program.ProgramNode`.

        Returns:
            The :class:`~app.parser.ast.procedure.ProcedureDivisionNode`, or
            ``None`` if *program_node* is ``None`` or has no procedure division.
        """
        if program_node is None:
            return None
        return program_node.procedure_division

    def build_call_instruction(self, stmt: CallStatementNode) -> IRCall | None:
        """
        Lower a single ``CallStatementNode`` into an
        :class:`~app.ir.instructions.IRCall`.
        """
        if not stmt.target:
            self._context._diagnostics.append(
                SemanticDiagnostic(
                    severity=SemanticSeverity.ERROR,
                    message="Missing target in CALL statement.",
                    position=stmt.start_position,
                    code="SEM009",
                )
            )
            return None

        target = self.build_operand(stmt.target)
        if target.startswith('"') and target.endswith('"'):
            target = target[1:-1]
        elif target.startswith("'") and target.endswith("'"):
            target = target[1:-1]

        args = []
        for arg in stmt.arguments:
            args.append(self.build_operand(arg))

        # Tagged ``comment="CALL"`` (task #110) -- see the matching note
        # on build_perform_statement.
        return IRCall(
            target=target,
            args=tuple(args),
            comment="CALL",
        )

    def build_perform_until_statement(self, stmt: PerformUntilStatementNode) -> None:
        ir_left = self.build_operand(stmt.condition_left)
        ir_right = self.build_operand(stmt.condition_right)
        self._emit(
            IRPerformUntil(
                left=ir_left, operator=stmt.condition_operator, right=ir_right
            ),
            stmt.start_position,
        )
        for body_stmt in stmt.statements:
            self._translate_statement(body_stmt)
        self._emit(IREndPerform(), stmt.start_position)
