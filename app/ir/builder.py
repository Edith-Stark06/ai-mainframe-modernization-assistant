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
      provided, walk its PROCEDURE DIVISION to emit MOVE instructions.
    - Translate each ``MoveStatementNode`` into one ``IRMove`` instruction.
    - Emit a structured IR translation warning for unsupported statements while
      continuing translation.
    - Expose reusable operand helpers: :meth:`build_operand`,
      :meth:`build_variable_reference`, :meth:`build_literal`.
    - Remain stateless between :meth:`build` calls.
    - Log lifecycle events via Loguru.

Non-responsibilities:
    - DISPLAY, ACCEPT, CALL, IF, PERFORM, GO TO, arithmetic (TASK-027+).
    - Java code generation.
    - Re-parsing identifiers (uses resolved symbols from SymbolTable).
    - Optimisation passes.

Extension points for future tasks:
    - :meth:`build_entry_block` — iterate through ``ProcedureDivisionNode``
      paragraphs; add new ``elif`` branches for DISPLAY, CALL, PERFORM, etc.
    - :meth:`build_operand` — extend literal/variable detection for typed
      operands (``IROperand`` value type) as types mature.
    - :meth:`build_function` — add multi-block support (IF, PERFORM, GO TO).
    - :meth:`build_module` — emit one ``IRFunction`` per paragraph for
      section-level granularity.

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

from typing import TYPE_CHECKING

from loguru import logger

from app.ir.blocks import IRBasicBlock
from app.ir.instructions import (
    IRAccept,
    IRAdd,
    IRCall,
    IRConditionalBranch,
    IRDisplay,
    IRDivide,
    IRInstruction,
    IRJump,
    IRMove,
    IRMultiply,
    IRSubtract,
)
from app.ir.program import IRFunction, IRModule, IRProgram
from app.parser.semantic.context import SemanticContext
from app.parser.semantic.symbols import ProgramSymbol, SymbolKind

if TYPE_CHECKING:
    from app.parser.ast.paragraphs import ParagraphNode
    from app.parser.ast.procedure import ProcedureDivisionNode
    from app.parser.ast.program import ProgramNode
    from app.parser.ast.statements import (
        AcceptStatementNode,
        AddStatementNode,
        DisplayStatementNode,
        DivideStatementNode,
        GoToStatementNode,
        IfStatementNode,
        MoveStatementNode,
        MultiplyStatementNode,
        PerformStatementNode,
        StatementNode,
        SubtractStatementNode,
    )

__all__ = ["IRBuilder"]

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
        their statements in source order, emitting one
        :class:`~app.ir.instructions.IRMove` per ``MOVE`` statement.
        Unsupported statement types emit a ``DEBUG``-level log and are
        skipped; translation continues.

        Extension guide for future tasks:

        * **DISPLAY** — add ``elif isinstance(stmt, DisplayStatementNode):``
          and emit :class:`~app.ir.instructions.IRCall`.
        * **STOP RUN / GOBACK** — emit :class:`~app.ir.instructions.IRReturn`.
        * **IF / EVALUATE** — emit additional ``IRBasicBlock`` instances +
          :class:`~app.ir.instructions.IRBranch`; wire them into the function
          rather than this block alone.
        * **PERFORM / CALL** — emit :class:`~app.ir.instructions.IRCall`.
        * **Arithmetic** — emit :class:`~app.ir.instructions.IRAssignment`.

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

    # ------------------------------------------------------------------
    # Statement translation helpers
    # ------------------------------------------------------------------

    def _translate_paragraph(self, para: ParagraphNode) -> None:
        """
        Translate supported statements in a paragraph into IR instructions.

        Unsupported statements are logged at DEBUG level and skipped.

        Args:
            para:
                The :class:`~app.parser.ast.paragraphs.ParagraphNode` to
                translate.
        """
        for stmt in para.statements:
            self._translate_statement(stmt)

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
        from app.parser.ast.statements import (  # noqa: PLC0415
            AcceptStatementNode,
            AddStatementNode,
            DisplayStatementNode,
            DivideStatementNode,
            GoToStatementNode,
            IfStatementNode,
            MoveStatementNode,
            MultiplyStatementNode,
            PerformStatementNode,
            SubtractStatementNode,
        )

        if isinstance(stmt, MoveStatementNode):
            instr_move = self.build_move_instruction(stmt)
            if instr_move:
                self._current_instructions.append(instr_move)
            return instr_move
        if isinstance(stmt, DisplayStatementNode):
            instr_disp = self.build_display_instruction(stmt)
            if instr_disp:
                self._current_instructions.append(instr_disp)
            return instr_disp
        if isinstance(stmt, AcceptStatementNode):
            instr_acc = self.build_accept_instruction(stmt)
            if instr_acc:
                self._current_instructions.append(instr_acc)
            return instr_acc
        if isinstance(stmt, AddStatementNode):
            instr_add = self.build_add_instruction(stmt)
            if instr_add:
                self._current_instructions.append(instr_add)
            return instr_add
        if isinstance(stmt, SubtractStatementNode):
            instr_sub = self.build_subtract_instruction(stmt)
            if instr_sub:
                self._current_instructions.append(instr_sub)
            return instr_sub
        if isinstance(stmt, MultiplyStatementNode):
            instr_mul = self.build_multiply_instruction(stmt)
            if instr_mul:
                self._current_instructions.append(instr_mul)
            return instr_mul
        if isinstance(stmt, DivideStatementNode):
            instr_div = self.build_divide_instruction(stmt)
            if instr_div:
                self._current_instructions.append(instr_div)
            return instr_div
        if isinstance(stmt, IfStatementNode):
            self.build_if_statement(stmt)
            return None
        if isinstance(stmt, PerformStatementNode):
            self.build_perform_statement(stmt)
            return None
        if isinstance(stmt, GoToStatementNode):
            self.build_go_to_statement(stmt)
            return None

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
        return IRAdd(left=ir_left, right=ir_right)

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
        return IRSubtract(left=ir_left, right=ir_right)

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
        return IRMultiply(left=ir_left, right=ir_right)

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
        return IRDivide(left=ir_left, right=ir_right)

    def build_if_statement(self, stmt: IfStatementNode) -> None:
        """
        Lower a single ``IfStatementNode`` into a control flow graph.
        """
        if not stmt.condition:
            logger.warning("Incomplete IF node: missing condition. Continuing.")
            condition_operand = ""
        else:
            condition_operand = self.build_operand(stmt.condition)

        then_label = self._generate_label("if_then")
        merge_label = self._generate_label("if_merge")
        else_label = (
            self._generate_label("if_else") if stmt.else_statements else merge_label
        )

        branch = IRConditionalBranch(
            condition=condition_operand, then_target=then_label, else_target=else_label
        )
        self._current_instructions.append(branch)

        self._start_block(then_label)
        for then_stmt in stmt.then_statements:
            self._translate_statement(then_stmt)
        self._current_instructions.append(IRJump(target=merge_label))

        if stmt.else_statements:
            self._start_block(else_label)
            for else_stmt in stmt.else_statements:
                self._translate_statement(else_stmt)
            self._current_instructions.append(IRJump(target=merge_label))

        self._start_block(merge_label)

    def build_perform_statement(self, stmt: PerformStatementNode) -> None:
        """
        Lower a single ``PerformStatementNode`` into an ``IRCall``.
        """
        if not stmt.target:
            logger.warning("Unsupported PERFORM form: missing target. Continuing.")
        else:
            self._current_instructions.append(IRCall(target=stmt.target))

    def build_go_to_statement(self, stmt: GoToStatementNode) -> None:
        """
        Lower a single ``GoToStatementNode`` into an ``IRJump``.
        """
        if not stmt.target:
            logger.warning("Unresolved target in GO TO statement. Continuing.")
        else:
            self._current_instructions.append(IRJump(target=stmt.target))

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
