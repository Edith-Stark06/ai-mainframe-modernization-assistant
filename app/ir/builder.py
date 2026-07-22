"""
IR Builder — AST-to-IR Translation Foundation.

Purpose:
    Provide :class:`IRBuilder` — the primary entry point for the AST-to-IR
    translation pipeline.  The builder accepts a validated
    :class:`~app.parser.semantic.context.SemanticContext` and translates the
    *structural* elements of the compiled COBOL program into a complete
    :class:`~app.ir.program.IRProgram`.

    TASK-025 implements the structural translation foundation:

    * One :class:`~app.ir.program.IRModule` per COBOL program (keyed by the
      ``PROGRAM-ID`` name from the
      :class:`~app.parser.semantic.symbols.ProgramSymbol`).
    * One :class:`~app.ir.program.IRFunction` per module (an ``"__entry__"``
      function that represents the program's top-level execution body).
    * One :class:`~app.ir.blocks.IRBasicBlock` (labelled ``"entry"``) as the
      initial block of the entry function.  Future tasks will populate this
      block by emitting instructions for MOVE, DISPLAY, CALL, etc.

    The builder is composed of focused helper methods, one per IR node level,
    so that future tasks can extend individual helpers without touching the
    overall orchestration logic.

Translation pipeline::

    SemanticContext
         │
         ▼  build()
    IRProgram                ← build_program()
         │
         ▼  (one per ProgramSymbol)
    IRModule                 ← build_module()
         │
         ▼  (always one entry function)
    IRFunction               ← build_function()
         │
         ▼  (always one entry block)
    IRBasicBlock("entry")    ← build_entry_block()
         │
         ▼  (future tasks: MOVE, DISPLAY, CALL, IF, PERFORM, …)
    IRInstruction *

Responsibilities:
    - Validate the supplied :class:`~app.parser.semantic.context.SemanticContext`.
    - Derive a program name from the first ``PROGRAM-ID`` symbol; fall back to
      an empty string if no program symbol is present.
    - Derive module / function names from paragraph and program symbols.
    - Emit lifecycle log events via Loguru at ``DEBUG`` level.
    - Log a ``WARNING`` if the context contains semantic errors, but continue
      translation so that downstream tools receive a partial IR.
    - Remain fully stateless between calls to :meth:`build` so that the same
      :class:`IRBuilder` instance can be called multiple times and always
      returns a freshly-constructed :class:`~app.ir.program.IRProgram`.

Non-responsibilities:
    - AST traversal (no references to ``app.parser.ast``).
    - Executable-statement translation (MOVE, DISPLAY, CALL, IF, PERFORM,
      GO TO, arithmetic) — deferred to TASK-026+.
    - Java code generation.
    - Optimisation passes.
    - Type coercion or implicit conversion.

Extension points for future tasks:
    - :meth:`build_entry_block` — add instruction emission here per
      statement type.
    - :meth:`build_function` — add multi-block support (IF, PERFORM,
      GO TO) by building additional :class:`~app.ir.blocks.IRBasicBlock`
      instances and adding them to the function's block tuple.
    - :meth:`build_module` — add multiple functions per module when
      COBOL sections or nested programs are supported.
    - :meth:`_program_name` / :meth:`_module_name` / :meth:`_function_name` —
      override naming conventions without touching orchestration logic.

Dependencies:
    - :mod:`app.parser.semantic.context`   — ``SemanticContext``.
    - :mod:`app.parser.semantic.symbols`   — ``ProgramSymbol``, ``SymbolKind``.
    - :mod:`app.ir.blocks`                 — ``IRBasicBlock``.
    - :mod:`app.ir.program`                — ``IRProgram``, ``IRModule``,
                                             ``IRFunction``.
    - Loguru for structured logging.

Examples:
    Translating a clean semantic context::

        from app.parser.semantic.context import SemanticContext, SymbolTable
        from app.ir.builder import IRBuilder

        ctx = SemanticContext(symbol_table=SymbolTable(), diagnostics=[])
        prog = IRBuilder(context=ctx).build()
        # Empty program (no ProgramSymbol registered) → one empty module.
        len(prog)               # 1
        prog.modules[0].name    # ''

    Translating a context with a named program::

        from app.parser.lexer.position import Position
        from app.parser.semantic.symbols import ProgramSymbol
        from app.parser.semantic.context import SemanticContext, SymbolTable

        pos = Position(line=1, column=1, offset=0, filename="p.cbl")
        table = SymbolTable()
        table.register(ProgramSymbol(name="PAYROLL", declared_at=pos))
        ctx = SemanticContext(symbol_table=table, diagnostics=[])
        prog = IRBuilder(context=ctx).build()
        prog.name                          # 'PAYROLL'
        prog.modules[0].name               # 'PAYROLL'
        prog.modules[0].functions[0].name  # '__entry__'
        prog.modules[0].functions[0].blocks[0].label  # 'entry'

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.ir.blocks import IRBasicBlock
from app.ir.program import IRFunction, IRModule, IRProgram
from app.parser.semantic.context import SemanticContext
from app.parser.semantic.symbols import ProgramSymbol, SymbolKind

__all__ = ["IRBuilder"]

# Name used for the top-level entry function in every generated module.
_ENTRY_FUNCTION_NAME: str = "__entry__"

# Label for the entry basic block of the entry function.
_ENTRY_BLOCK_LABEL: str = "entry"


class IRBuilder:
    """
    Translate a validated :class:`~app.parser.semantic.context.SemanticContext`
    into an :class:`~app.ir.program.IRProgram`.

    :class:`IRBuilder` is the bridge between the semantic analysis pipeline
    (passes 1–5) and the IR.  It reads the populated
    :class:`~app.parser.semantic.context.SymbolTable` and constructs a
    structurally correct IR tree.

    **TASK-025 translation scope:**

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
    | COBOL statements           | *(deferred to TASK-026+)*     |
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
        >>> len(prog)
        1
        >>> prog.modules[0].functions[0].blocks[0].label
        'entry'
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
                f"IRBuilder requires a SemanticContext, got {type(context).__name__!r}."
            )
        self._context: SemanticContext = context
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

    def build(self) -> IRProgram:
        """
        Translate the semantic context into a fully-structured
        :class:`~app.ir.program.IRProgram`.

        **Translation pipeline (TASK-025):**

        1. Resolve the program name from the first
           :class:`~app.parser.semantic.symbols.ProgramSymbol` in the symbol
           table, or fall back to ``""`` if none is registered.
        2. Delegate to :meth:`build_program` to construct the
           :class:`~app.ir.program.IRProgram` with exactly one
           :class:`~app.ir.program.IRModule`.
        3. Return the freshly-constructed program.

        The method is safe to call multiple times; each call returns a new,
        independent :class:`~app.ir.program.IRProgram`.

        Returns:
            A complete :class:`~app.ir.program.IRProgram` reflecting the
            structural content of the semantic context.
        """
        prog_name = self._program_name()
        logger.debug("IRBuilder.build(): program_name={!r}.", prog_name)
        program = self.build_program(prog_name)
        logger.debug(
            "IRBuilder.build(): built IRProgram with {} module(s).", len(program)
        )
        return program

    def current_program(self) -> IRProgram:
        """
        Return the :class:`~app.ir.program.IRProgram` constructed so far.

        This method is a convenience accessor for incremental builders that
        emit IR in stages.  It delegates to :meth:`build`.

        Returns:
            The partially or fully constructed
            :class:`~app.ir.program.IRProgram`.
        """
        return self.build()

    # ------------------------------------------------------------------
    # Structural helpers — one per IR node level
    # ------------------------------------------------------------------

    def build_program(self, prog_name: str) -> IRProgram:
        """
        Construct the top-level :class:`~app.ir.program.IRProgram`.

        Creates exactly one :class:`~app.ir.program.IRModule` by calling
        :meth:`build_module`.  Future tasks may extend this method to produce
        multiple modules when COBOL nested programs or COPY books introduce
        additional compilation units.

        Args:
            prog_name:
                Human-readable program name (from the PROGRAM-ID clause or
                the empty string if absent).

        Returns:
            A :class:`~app.ir.program.IRProgram` containing one module.
        """
        module = self.build_module(self._module_name(prog_name))
        logger.debug("IRBuilder.build_program(): module name={!r}.", module.name)
        return IRProgram(name=prog_name, modules=(module,))

    def build_module(self, module_name: str) -> IRModule:
        """
        Construct an :class:`~app.ir.program.IRModule` for a single COBOL
        program or compilation unit.

        Creates exactly one :class:`~app.ir.program.IRFunction` by calling
        :meth:`build_function`.  Future tasks may extend this method to
        produce multiple functions per module (e.g. one per COBOL section).

        Args:
            module_name:
                Human-readable module name (typically the program name).

        Returns:
            An :class:`~app.ir.program.IRModule` containing one entry function.
        """
        function = self.build_function(self._function_name())
        logger.debug("IRBuilder.build_module(): function name={!r}.", function.name)
        return IRModule(name=module_name, functions=(function,))

    def build_function(self, function_name: str) -> IRFunction:
        """
        Construct the entry :class:`~app.ir.program.IRFunction`.

        Creates one :class:`~app.ir.blocks.IRBasicBlock` by calling
        :meth:`build_entry_block`.  Future tasks may extend this method to
        produce additional basic blocks for control-flow constructs (IF,
        PERFORM, GO TO).

        Args:
            function_name:
                Name of the function (defaults to ``"__entry__"``).

        Returns:
            An :class:`~app.ir.program.IRFunction` containing one entry block.
        """
        entry_block = self.build_entry_block()
        logger.debug(
            "IRBuilder.build_function(): entry block label={!r}.",
            entry_block.label,
        )
        return IRFunction(name=function_name, blocks=(entry_block,))

    def build_entry_block(self) -> IRBasicBlock:
        """
        Construct the entry :class:`~app.ir.blocks.IRBasicBlock`.

        The entry block is currently always empty.  Future tasks (TASK-026+)
        will extend this method to emit :class:`~app.ir.instructions.IRInstruction`
        objects for each COBOL statement encountered in the PROCEDURE DIVISION:

        * MOVE statement → :class:`~app.ir.instructions.IRMove`
        * DISPLAY statement → :class:`~app.ir.instructions.IRCall`
        * CALL statement → :class:`~app.ir.instructions.IRCall`
        * STOP RUN / GOBACK → :class:`~app.ir.instructions.IRReturn`
        * Arithmetic statements → :class:`~app.ir.instructions.IRAssignment`
        * IF / EVALUATE → additional :class:`~app.ir.blocks.IRBasicBlock`
          instances + :class:`~app.ir.instructions.IRBranch`

        Returns:
            An empty :class:`~app.ir.blocks.IRBasicBlock` labelled ``"entry"``.
        """
        logger.debug("IRBuilder.build_entry_block(): creating empty entry block.")
        return IRBasicBlock(label=_ENTRY_BLOCK_LABEL)

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

        By default the module name equals the program name.  Override this
        method to apply custom naming (e.g. Java class-name conventions).

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

        Returns the constant ``"__entry__"``.  Override to use a different
        naming scheme (e.g. derive from the first paragraph name).

        Returns:
            The entry-function name string.
        """
        return _ENTRY_FUNCTION_NAME
