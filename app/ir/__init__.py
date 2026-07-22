"""
Intermediate Representation (IR) Package.

Purpose:
    Provide the language-independent Intermediate Representation that sits
    between the semantic analysis phase (COBOL AST + semantic context) and the
    back-end code generation phase (Java / Spring Boot).

    The IR models *program behaviour* — operations, data movement, control
    flow — independently of COBOL syntax or Java class structure.

Five-layer architecture:

    * :class:`~app.ir.program.IRProgram`  — top-level compilation unit.
    * :class:`~app.ir.program.IRModule`   — logical grouping (maps to a Java class).
    * :class:`~app.ir.program.IRFunction` — callable unit (maps to a method).
    * :class:`~app.ir.blocks.IRBasicBlock` — straight-line instruction sequence.
    * :class:`~app.ir.instructions.IRInstruction` — atomic operation.

Instruction hierarchy:

    * :class:`~app.ir.instructions.IRAssignment` — literal value assignment.
    * :class:`~app.ir.instructions.IRMove`        — operand-to-operand copy.
    * :class:`~app.ir.instructions.IRDisplay`     — console output (DISPLAY).
    * :class:`~app.ir.instructions.IRAccept`      — console input (ACCEPT).
    * :class:`~app.ir.instructions.IRCall`        — function invocation.
    * :class:`~app.ir.instructions.IRReturn`      — exit function (optionally returning a value).
    * :class:`~app.ir.instructions.IRConditionalBranch` — conditional jump.
    * :class:`~app.ir.instructions.IRJump`        — unconditional jump.

Visitor framework:

    * :class:`~app.ir.visitors.IRVisitor`   — no-op base; subclass to implement passes.
    * :func:`~app.ir.visitors.traverse_ir`  — top-down traversal driver.

Builder:

    * :class:`~app.ir.builder.IRBuilder` — accepts
      :class:`~app.parser.semantic.context.SemanticContext`; scaffold for
      future AST-to-IR translation.

Public API:
    All primary types are exported from this package.

Dependencies:
    - :mod:`app.parser.semantic.context` — ``SemanticContext`` (builder input).
    - Python standard library only (for node/instruction modules).
    - Loguru (for builder).

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from app.ir.blocks import IRBasicBlock
from app.ir.builder import IRBuilder
from app.ir.instructions import (
    IRAccept,
    IRAdd,
    IRAssignment,
    IRCall,
    IRConditionalBranch,
    IRDisplay,
    IRDivide,
    IRInstruction,
    IRJump,
    IRMove,
    IRMultiply,
    IRReturn,
    IRSubtract,
)
from app.ir.nodes import IRNode, IRNodeKind
from app.ir.program import IRFunction, IRModule, IRProgram
from app.ir.visitors import IRVisitor, traverse_ir

__all__ = [
    "IRAccept",
    "IRAdd",
    "IRAssignment",
    "IRCall",
    "IRConditionalBranch",
    "IRDisplay",
    "IRDivide",
    "IRInstruction",
    "IRJump",
    "IRMove",
    "IRMultiply",
    "IRReturn",
    "IRSubtract",
    "IRBasicBlock",
    "IRBuilder",
    "IRFunction",
    "IRModule",
    "IRNode",
    "IRNodeKind",
    "IRProgram",
    "IRVisitor",
    "traverse_ir",
]
