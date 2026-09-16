"""
Business Rule Models (task #112 — Phase 4 Modernization Intelligence).

Purpose:
    Define the structured, immutable representation of a *business rule*
    extracted deterministically from the Phase 1–3 analysis outputs
    (AST, IR, CFG, dependency analysis).

    This is a **Phase 4** model and is intentionally distinct from the
    lightweight :class:`app.analysis.rules.models.BusinessRule` primitive
    used by the earlier ``/analysis`` endpoint (tasks #61–#64): that type
    carries only a condition string and action strings, while this one
    carries category, structured actions, variable read/write/condition
    sets, dependency identifiers, per-statement source locations, the
    owning paragraph, and a deterministic evidence-based confidence.
    The older type is left untouched for backward compatibility.

Design:
    * Every field is derived from concrete AST/IR/dependency evidence.
      Nothing is inferred with an LLM, and no domain terminology is
      invented — a rule that tests ``WS-AMOUNT > 50000`` is recorded with
      exactly that comparison, never relabelled "fraud limit".
    * ``rule_id`` is assigned by
      :class:`~app.modernization.business_rules.extractor.BusinessRuleExtractor`
      only after a total deterministic sort, so identical source always
      yields identical IDs (``BR-001``, ``BR-002`` …). The model itself
      never generates an ID.
    * The dataclass is frozen; ``to_dict`` produces a JSON-safe structure
      via the shared :func:`app.analysis.serializers._common.serialize_value`
      helper, matching the serialization convention already used for
      dependencies.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Any

from app.analysis.serializers._common import serialize_value
from app.parser.lexer.position import Position

__all__ = [
    "BusinessRuleCategory",
    "RuleActionKind",
    "RuleAction",
    "RuleVariables",
    "BusinessRule",
]


@unique
class BusinessRuleCategory(Enum):
    """
    Deterministic classification of an extracted rule.

    The category is decided purely from structural evidence (see
    :func:`~app.modernization.business_rules.extractor.classify_rule`).
    It never encodes domain meaning that the source does not state.

    Members:
        CONDITIONAL_VALIDATION:
            An equality/inequality test that gates one or more actions
            (``IF WS-STATUS = 'A' ...``).
        CALCULATION:
            The rule performs arithmetic (ADD/SUBTRACT/MULTIPLY/DIVIDE).
        STATUS_TRANSITION:
            A variable that appears in the condition is also assigned by
            one of the actions (``IF WS-STATUS = 'P' MOVE 'A' TO WS-STATUS``).
        LIMIT_CHECK:
            A relational comparison (``>``/``<``/``>=``/``<=``) against a
            numeric literal.
        ERROR_CONDITION:
            An action target or literal whose *name text itself* contains
            an error/rejection keyword (``ERROR``, ``INVALID``, ``REJECT``
            …). This is name evidence present in the source, not inferred
            business meaning.
        GENERAL:
            A conditionally-guarded action that matches none of the above.
    """

    CONDITIONAL_VALIDATION = "CONDITIONAL_VALIDATION"
    CALCULATION = "CALCULATION"
    STATUS_TRANSITION = "STATUS_TRANSITION"
    LIMIT_CHECK = "LIMIT_CHECK"
    ERROR_CONDITION = "ERROR_CONDITION"
    GENERAL = "GENERAL"


@unique
class RuleActionKind(Enum):
    """The concrete AST/IR instruction a rule action was lowered from."""

    ASSIGN = "ASSIGN"  # MOVE
    ADD = "ADD"
    SUBTRACT = "SUBTRACT"
    MULTIPLY = "MULTIPLY"
    DIVIDE = "DIVIDE"
    CALL = "CALL"
    PERFORM = "PERFORM"
    TERMINATE = "TERMINATE"  # STOP RUN / GOBACK
    DISPLAY = "DISPLAY"


@dataclass(frozen=True)
class RuleAction:
    """
    One action executed when a rule's condition holds.

    Attributes:
        kind:
            Which instruction produced this action.
        target:
            The written variable, CALL target, or PERFORM target. Empty
            for :attr:`RuleActionKind.TERMINATE` and
            :attr:`RuleActionKind.DISPLAY`.
        sources:
            Non-literal operands read by the action, in source order.
        literals:
            Literal operands (quoted strings / numbers) used by the
            action, in source order. Never merged into :attr:`sources`.
        raw:
            The canonical single-line text form of the action, e.g.
            ``"WS-RESULT = 'VALID'"`` or ``"WS-TOTAL += WS-FEE"``.
        source_location:
            Position of the statement, or ``None`` if unavailable.
    """

    kind: RuleActionKind
    target: str
    sources: tuple[str, ...]
    literals: tuple[str, ...]
    raw: str
    source_location: Position | None = None


@dataclass(frozen=True)
class RuleVariables:
    """
    The variables a rule touches, split by how it touches them.

    All three tuples are sorted and de-duplicated. Literals are never
    included (they are filtered with the same predicate the Phase 3
    dependency analyzer uses).

    Attributes:
        reads:
            Variables whose value the rule reads (condition operands and
            action source operands).
        writes:
            Variables the rule assigns to (ASSIGN / arithmetic targets).
        conditions:
            Variables that appear in the rule's guarding condition.
    """

    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class BusinessRule:
    """
    A deterministically extracted business rule.

    Attributes:
        rule_id:
            Stable identifier (``BR-001`` …) assigned by the extractor
            after a total deterministic sort. Unique within one analyzed
            program; identical for identical source.
        category:
            Structural classification — see :class:`BusinessRuleCategory`.
        description:
            A templated, evidence-only sentence. Contains no domain
            terminology beyond the identifiers/literals in the source.
        condition:
            The canonical condition text. A single AST comparison
            (``WS-AGE >= 18``) or, for a nested IF, the parenthesised
            conjunction of the enclosing comparisons
            (``(A = 1) AND (B = 2)``), or a negated form for an ELSE
            branch (``NOT (A = 1)``).
        actions:
            The ordered actions executed when :attr:`condition` holds.
        variables:
            Read / write / condition variable sets.
        dependencies:
            Sorted identifiers this rule depends on — condition and
            source variables plus any CALL/PERFORM targets it invokes.
            Derived from the same operand/target evidence the Phase 3
            dependency analyzer uses.
        source_locations:
            Positions of the originating statements (the IF header first,
            then each action), in order.
        paragraph:
            The COBOL paragraph the rule was extracted from.
        section:
            Always ``None`` — the parser does not model PROCEDURE
            DIVISION sections (``visit_section`` is an unimplemented
            future capability). The field exists for forward
            compatibility and API stability.
        confidence:
            Deterministic, evidence-based. ``1.0`` when the condition is
            a single complete AST comparison and every action maps to a
            concrete instruction; ``0.75`` when the condition is a
            conjunction reconstructed from nested IFs (a mild but real
            structural inference). Never probabilistic.

    Raises:
        ValueError: if ``condition`` is empty, ``actions`` is empty, or
            ``confidence`` is outside ``[0.0, 1.0]``.
    """

    rule_id: str
    category: BusinessRuleCategory
    description: str
    condition: str
    actions: tuple[RuleAction, ...]
    variables: RuleVariables
    dependencies: tuple[str, ...]
    source_locations: tuple[Position, ...]
    paragraph: str
    section: str | None = None
    confidence: float = 1.0
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.condition or not self.condition.strip():
            raise ValueError("BusinessRule condition cannot be empty.")
        if not self.actions:
            raise ValueError("BusinessRule must have at least one action.")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"BusinessRule confidence must be within [0.0, 1.0], "
                f"got {self.confidence!r}."
            )

    def dedup_key(self) -> tuple[str, str, tuple[str, ...]]:
        """
        Structural identity used for deduplication.

        Two rules from the same paragraph with the same condition and the
        same ordered action texts are the same logical rule even if
        reached through different traversal paths. Rules from different
        paragraphs are always distinct.
        """
        return (
            self.paragraph,
            self.condition,
            tuple(a.raw for a in self.actions),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a deterministic JSON-safe dictionary."""
        return {
            "rule_id": self.rule_id,
            "category": self.category.value,
            "description": self.description,
            "condition": self.condition,
            "actions": [serialize_value(a) for a in self.actions],
            "variables": serialize_value(self.variables),
            "dependencies": list(self.dependencies),
            "source_locations": [serialize_value(p) for p in self.source_locations],
            "paragraph": self.paragraph,
            "section": self.section,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }
