"""
IR Builder Scaffold.

Purpose:
    Provide :class:`IRBuilder` — the public entry point for the AST-to-IR
    translation pipeline.  The builder accepts a validated
    :class:`~app.parser.semantic.context.SemanticContext` and exposes the
    interface that future translation passes will call to emit IR nodes.

    In this version (TASK-024) :class:`IRBuilder` is a *scaffold*: it
    validates its inputs, initialises internal state, and exposes the planned
    API surface without performing any actual AST traversal or instruction
    emission.  Translation logic will be added in subsequent tasks.

Responsibilities:
    - Accept and validate a :class:`~app.parser.semantic.context.SemanticContext`.
    - Maintain an ordered list of :class:`~app.ir.program.IRModule` objects
      being built (empty initially).
    - Provide :meth:`build` as the future entry point for translation.
    - Provide :meth:`current_program` to retrieve the (possibly empty)
      :class:`~app.ir.program.IRProgram` constructed so far.
    - Log lifecycle events via Loguru.

Non-responsibilities:
    - AST traversal or node inspection.
    - COBOL-specific translation logic.
    - Optimisation passes.
    - Java code generation.
    - Type coercion or implicit conversion.

Dependencies:
    - :mod:`app.parser.semantic.context` — ``SemanticContext``.
    - :mod:`app.ir.program`              — ``IRProgram``, ``IRModule``,
      ``IRFunction``.
    - :mod:`app.ir.nodes`                — ``IRNodeKind``.
    - Loguru for structured logging.

Examples:
    Creating an :class:`IRBuilder` from a semantic context::

        from app.parser.semantic.context import SemanticContext, SymbolTable
        from app.ir.builder import IRBuilder

        ctx = SemanticContext(symbol_table=SymbolTable(), diagnostics=[])
        builder = IRBuilder(context=ctx)
        prog = builder.build()  # returns empty IRProgram (scaffold)
        prog.name               # ''
        len(prog)               # 0

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.ir.program import IRProgram
from app.parser.semantic.context import SemanticContext

__all__ = ["IRBuilder"]


class IRBuilder:
    """
    Scaffold for translating a validated
    :class:`~app.parser.semantic.context.SemanticContext` into an
    :class:`~app.ir.program.IRProgram`.

    :class:`IRBuilder` is the primary consumer of the semantic analysis
    result.  Downstream tasks will extend :meth:`build` and helper methods
    to walk the AST, consult the symbol table and type information, and emit
    IR nodes.

    At this stage (TASK-024) the builder:

    * Validates that *context* is a :class:`~app.parser.semantic.context.SemanticContext`.
    * Logs a warning if the context contains errors (translation will still
      proceed; errors may surface as incomplete IR).
    * Exposes :meth:`build` which currently returns an empty
      :class:`~app.ir.program.IRProgram`.

    Attributes:
        _context:
            The :class:`~app.parser.semantic.context.SemanticContext` supplied
            at construction time.

    Examples:
        >>> from app.parser.semantic.context import SemanticContext, SymbolTable
        >>> from app.ir.builder import IRBuilder
        >>> ctx = SemanticContext(symbol_table=SymbolTable(), diagnostics=[])
        >>> builder = IRBuilder(context=ctx)
        >>> prog = builder.build()
        >>> isinstance(prog, IRProgram)
        True
        >>> len(prog)
        0
    """

    def __init__(self, context: SemanticContext) -> None:
        """
        Initialise the builder with a validated semantic context.

        Args:
            context:
                The :class:`~app.parser.semantic.context.SemanticContext`
                produced by :class:`~app.parser.semantic.analyzer.SemanticAnalyzer`.
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
        Translate the semantic context into an
        :class:`~app.ir.program.IRProgram`.

        **Scaffold implementation (TASK-024):** Returns an empty
        :class:`~app.ir.program.IRProgram` with no modules.  Translation
        logic will be added in subsequent tasks.

        Returns:
            An :class:`~app.ir.program.IRProgram` representing the compiled
            program.  Currently always empty.
        """
        logger.debug("IRBuilder.build(): scaffold — returning empty IRProgram.")
        return IRProgram(name="")

    def current_program(self) -> IRProgram:
        """
        Return the :class:`~app.ir.program.IRProgram` constructed so far.

        This method is a convenience accessor for incremental builders that
        emit IR in stages.  In the scaffold implementation it delegates to
        :meth:`build`.

        Returns:
            The partially or fully constructed
            :class:`~app.ir.program.IRProgram`.
        """
        return self.build()
