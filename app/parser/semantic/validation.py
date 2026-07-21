"""
Semantic Validation Visitor.

Purpose:
    Implement the third semantic analysis pass that traverses the COBOL AST
    and validates semantic rules *after* symbol collection (pass 1) and
    reference resolution (pass 2) have completed.

    :class:`SemanticValidationVisitor` is the **public, reusable** visitor
    responsible for structural and semantic constraint checking.  It
    separates validation concerns from both symbol collection and reference
    resolution, allowing each pass to be composed independently.

Responsibilities:
    - Detect a missing or empty PROGRAM-ID declaration (``"SEM006"``).
    - Detect an empty PROCEDURE DIVISION — present in the AST but containing
      no paragraphs (``"SEM007"``).
    - Detect reserved-word misuse — data-item names that collide with
      well-known COBOL reserved words (``"SEM008"``).
    - Detect an invalid static CALL target — a ``CALL`` literal whose value
      is blank or syntactically invalid (``"SEM009"``).  Forward-looking;
      the AST does not yet carry CALL nodes, but the hook is provided for
      future use.
    - Continue traversal after every error — never abort.

Non-responsibilities:
    - Symbol registration (pass 1, delegated to
      :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`).
    - Reference resolution (pass 2, delegated to
      :class:`~app.parser.semantic.reference_resolver.ReferenceResolverVisitor`).
    - Driving the AST traversal (delegated to
      :func:`~app.parser.semantic.visitors.traverse_program`).
    - Type checking, data-flow analysis, or control-flow analysis.
    - Constant folding or optimisation.

Design for extensibility:
    The visitor is deliberately rule-oriented:

    * Each validation rule is an independent private method (``_check_*``).
    * New rules are added by writing a new ``_check_*`` method and calling
      it from the appropriate visitor hook.
    * The public :meth:`visit_*` hooks delegate to one or more ``_check_*``
      helpers — no rule logic lives inside a hook directly.
    * Future passes can subclass :class:`SemanticValidationVisitor` and
      override individual ``_check_*`` methods to tighten or relax rules
      without touching the traversal logic.

Diagnostic codes emitted by this pass:

    ========  =====================================================
    Code      Rule
    ========  =====================================================
    SEM006    Missing or empty PROGRAM-ID
    SEM007    Empty PROCEDURE DIVISION (present but no paragraphs)
    SEM008    Reserved word used as a data-item identifier
    SEM009    Invalid static CALL target (blank or whitespace-only)
    ========  =====================================================

Dependencies:
    - :mod:`app.parser.ast.data_items`       — ``DataItemNode``.
    - :mod:`app.parser.ast.identification`   — ``IdentificationDivisionNode``.
    - :mod:`app.parser.ast.procedure`        — ``ProcedureDivisionNode``.
    - :mod:`app.parser.semantic.diagnostics` — ``SemanticDiagnostic``,
      ``SemanticSeverity``.
    - :mod:`app.parser.semantic.visitors`    — ``SemanticVisitor`` base.
    - Loguru for structured logging.

Examples:
    Using the validator as a standalone third pass::

        from app.parser.semantic.validation import SemanticValidationVisitor
        from app.parser.semantic.visitors import traverse_program

        diagnostics = []
        validator = SemanticValidationVisitor(diagnostics=diagnostics)
        traverse_program(program_node, validator)

        diagnostics  # any SEM006 / SEM007 / SEM008 / SEM009 errors

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.parser.ast.data_items import DataItemNode
from app.parser.ast.identification import IdentificationDivisionNode
from app.parser.ast.procedure import ProcedureDivisionNode
from app.parser.semantic.diagnostics import SemanticDiagnostic, SemanticSeverity
from app.parser.semantic.visitors import SemanticVisitor

__all__ = ["SemanticValidationVisitor"]

# ---------------------------------------------------------------------------
# Reserved-word list
# ---------------------------------------------------------------------------

#: A curated subset of COBOL 2014 reserved words that are most commonly
#: mis-used as data-item names.  The list is intentionally conservative:
#: only unambiguous reserved words are included so that normal working-
#: storage names are never falsely flagged.
#:
#: Extend this frozenset as new validation rules are added.
COBOL_RESERVED_WORDS: frozenset[str] = frozenset(
    {
        "ACCEPT",
        "ADD",
        "ALPHABETIC",
        "ALPHANUMERIC",
        "ALTER",
        "AND",
        "CALL",
        "CANCEL",
        "CLOSE",
        "COMPUTE",
        "CONTINUE",
        "DATA",
        "DELETE",
        "DISPLAY",
        "DIVIDE",
        "ELSE",
        "END",
        "EVALUATE",
        "EXIT",
        "FILE",
        "GO",
        "GOBACK",
        "IF",
        "INITIALIZE",
        "INSPECT",
        "MERGE",
        "MOVE",
        "MULTIPLY",
        "NEXT",
        "NOT",
        "OPEN",
        "OR",
        "PERFORM",
        "PROCEDURE",
        "READ",
        "RELEASE",
        "RETURN",
        "REWRITE",
        "SEARCH",
        "SECTION",
        "SET",
        "SORT",
        "START",
        "STOP",
        "STRING",
        "SUBTRACT",
        "THEN",
        "UNSTRING",
        "WHEN",
        "WRITE",
    }
)


# ===========================================================================
# SemanticValidationVisitor
# ===========================================================================


class SemanticValidationVisitor(SemanticVisitor):
    """
    Public semantic visitor that enforces structural and semantic constraints.

    :class:`SemanticValidationVisitor` is the **third semantic pass**.  It
    expects that symbol collection (pass 1) and reference resolution (pass 2)
    have already completed.  The validator traverses the AST looking for
    semantic rule violations and appends a structured
    :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic` for each
    violation found.  Traversal always continues — no error aborts the walk.

    **Rules enforced**

    - ``PROGRAM-ID`` absent or blank → ``"SEM006"`` diagnostic.
    - ``PROCEDURE DIVISION`` present but empty → ``"SEM007"`` diagnostic.
    - Data-item name matching a reserved COBOL word → ``"SEM008"`` diagnostic.
    - Static ``CALL`` target blank or whitespace-only → ``"SEM009"``
      diagnostic (hook provided; CALL AST nodes are not yet emitted).

    **Adding new rules**

    1. Write a private ``_check_<rule>(node, …)`` method.
    2. Call it from the relevant ``visit_*`` hook.
    3. Register the new code in
       :data:`~app.parser.semantic.diagnostics.DIAGNOSTIC_CODES`.

    No existing visitor method needs to be modified.

    Attributes:
        _diagnostics:
            Mutable list of
            :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic`
            records accumulated during traversal.

    Examples:
        >>> from app.parser.semantic.validation import SemanticValidationVisitor
        >>> from app.parser.semantic.diagnostics import SemanticDiagnostic
        >>> diags: list[SemanticDiagnostic] = []
        >>> validator = SemanticValidationVisitor(diagnostics=diags)
        >>> validator._diagnostics is diags
        True
    """

    def __init__(self, diagnostics: list[SemanticDiagnostic]) -> None:
        """
        Initialise the validator with a shared diagnostics list.

        Args:
            diagnostics:
                A mutable list to which
                :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic`
                records are appended when violations are detected.
        """
        self._diagnostics = diagnostics

    # ------------------------------------------------------------------
    # Visitor hooks
    # ------------------------------------------------------------------

    def visit_identification_division(self, node: IdentificationDivisionNode) -> None:
        """
        Validate the IDENTIFICATION DIVISION.

        Checks:
            - ``PROGRAM-ID`` clause is present and non-empty (``"SEM006"``).

        Args:
            node: The identification division node.
        """
        logger.debug("SemanticValidationVisitor: visiting IDENTIFICATION DIVISION.")
        self._check_program_id(node)

    def visit_procedure_division(self, node: ProcedureDivisionNode) -> None:
        """
        Validate the PROCEDURE DIVISION.

        Checks:
            - At least one paragraph is present (``"SEM007"``).

        Args:
            node: The procedure division node.
        """
        logger.debug(
            "SemanticValidationVisitor: visiting PROCEDURE DIVISION "
            "with {} paragraph(s).",
            len(node.paragraphs),
        )
        self._check_empty_procedure_division(node)

    def visit_elementary_item(self, node: DataItemNode) -> None:
        """
        Validate an elementary data item.

        Checks:
            - Data-item name is not a COBOL reserved word (``"SEM008"``).

        Args:
            node: The elementary item node.
        """
        self._check_reserved_word_identifier(node)

    def visit_group_item(self, node: DataItemNode) -> None:
        """
        Validate a group data item.

        Checks:
            - Group-name is not a COBOL reserved word (``"SEM008"``).

        Args:
            node: The group item node.
        """
        self._check_reserved_word_identifier(node)

    def visit_condition_name(self, node: DataItemNode) -> None:
        """
        Validate a condition-name (level 88) data item.

        Checks:
            - Condition-name is not a COBOL reserved word (``"SEM008"``).

        Args:
            node: The condition-name node.
        """
        self._check_reserved_word_identifier(node)

    # ------------------------------------------------------------------
    # Rule implementations
    # ------------------------------------------------------------------

    def _check_program_id(self, node: IdentificationDivisionNode) -> None:
        """
        Rule SEM006 — PROGRAM-ID must be present and non-blank.

        A COBOL program without a PROGRAM-ID is not valid.  This check
        fires when:

        - The ``program_id`` field of the identification division is
          ``None`` (clause entirely absent from the source), **or**
        - The ``value`` of the PROGRAM-ID clause is blank / whitespace-
          only.

        Args:
            node: The identification division node to inspect.
        """
        pid = node.program_id
        if pid is None or not pid.value.strip():
            msg = "PROGRAM-ID is missing or blank"
            logger.warning(
                "SemanticValidationVisitor: SEM006 — {} at {}:{}.",
                msg,
                node.start_position.filename,
                node.start_position.line,
            )
            self._emit(
                message=msg,
                position=node.start_position,
                code="SEM006",
            )

    def _check_empty_procedure_division(self, node: ProcedureDivisionNode) -> None:
        """
        Rule SEM007 — PROCEDURE DIVISION must contain at least one paragraph.

        An empty PROCEDURE DIVISION (the keyword appears but no paragraphs
        follow) is a common authoring mistake.  The program would be valid
        COBOL but typically indicates a work-in-progress or accidental
        truncation.

        Args:
            node: The procedure division node to inspect.
        """
        if not node.paragraphs:
            msg = "PROCEDURE DIVISION is empty — no paragraphs declared"
            logger.warning(
                "SemanticValidationVisitor: SEM007 — {} at {}:{}.",
                msg,
                node.start_position.filename,
                node.start_position.line,
            )
            self._emit(
                message=msg,
                position=node.start_position,
                code="SEM007",
            )

    def _check_reserved_word_identifier(self, node: DataItemNode) -> None:
        """
        Rule SEM008 — data-item name must not be a COBOL reserved word.

        COBOL reserved words carry special syntactic meaning and must not
        be used as data names.  This check is case-insensitive.

        Args:
            node: The data item node whose ``name`` is tested.
        """
        name_upper = node.name.upper()
        if name_upper in COBOL_RESERVED_WORDS:
            msg = f"data-item name {node.name!r} is a COBOL reserved word"
            logger.warning(
                "SemanticValidationVisitor: SEM008 — {} at {}:{}.",
                msg,
                node.start_position.filename,
                node.start_position.line,
            )
            self._emit(
                message=msg,
                position=node.start_position,
                code="SEM008",
            )

    def _check_static_call_target(self, target: str, position: object) -> None:
        """
        Rule SEM009 — static CALL target must not be blank.

        This hook is provided for future use when CALL statement AST nodes
        are available.  A static CALL literal (string constant naming the
        called program) must not be empty or whitespace-only.

        Args:
            target:
                The raw CALL target literal extracted from the statement.
            position:
                The source position of the CALL statement for the
                diagnostic.
        """
        from app.parser.lexer.position import Position

        if not isinstance(position, Position):  # pragma: no cover
            return
        if not target.strip():
            msg = f"static CALL target {target!r} is blank or invalid"
            logger.warning(
                "SemanticValidationVisitor: SEM009 — {} at {}:{}.",
                msg,
                position.filename,
                position.line,
            )
            self._emit(
                message=msg,
                position=position,
                code="SEM009",
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit(
        self,
        message: str,
        position: object,
        code: str,
        severity: SemanticSeverity = SemanticSeverity.ERROR,
    ) -> None:
        """
        Append a :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic`
        to the diagnostics list.

        Args:
            message:
                Human-readable description of the violation.
            position:
                Source position of the offending construct.
            code:
                Short rule identifier (e.g. ``"SEM006"``).
            severity:
                :class:`~app.parser.semantic.diagnostics.SemanticSeverity`
                level; defaults to ``ERROR``.
        """
        self._diagnostics.append(
            SemanticDiagnostic(
                message=message,
                position=position,  # type: ignore[arg-type]
                severity=severity,
                code=code,
            )
        )
