"""
Append-only audit log (Phase 11).

Every major action the quality loop takes is recorded as an
:class:`AuditEvent`. The log is the thing a human reviewer must be able
to use to reconstruct, from nothing else, what failed, why a repair was
attempted, what evidence backed it, what the AI proposed, what exactly
changed, who/what approved it, whether compile/tests/behavior improved,
whether there was a regression, and why the loop stopped.

Events are never rewritten. Each event references the event before it
(``prev_event_hash``) so the sequence is tamper-evident; each event's
own ``event_hash`` is a deterministic sha256 over its own fields plus
``prev_event_hash`` — reproducible, not random.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.quality_loop.version import AUDIT_SCHEMA_VERSION

__all__ = [
    "AuditEventType",
    "AuditEvent",
    "AuditLog",
]


class AuditEventType(str, Enum):
    ANALYSIS_STARTED = "ANALYSIS_STARTED"
    ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
    GENERATION_STARTED = "GENERATION_STARTED"
    GENERATION_COMPLETED = "GENERATION_COMPLETED"
    COMPILATION_STARTED = "COMPILATION_STARTED"
    COMPILATION_COMPLETED = "COMPILATION_COMPLETED"
    TEST_STARTED = "TEST_STARTED"
    TEST_COMPLETED = "TEST_COMPLETED"
    COMPARISON_STARTED = "COMPARISON_STARTED"
    COMPARISON_COMPLETED = "COMPARISON_COMPLETED"
    FAILURE_DETECTED = "FAILURE_DETECTED"
    REPAIR_REQUESTED = "REPAIR_REQUESTED"
    REPAIR_PROPOSED = "REPAIR_PROPOSED"
    REPAIR_REJECTED = "REPAIR_REJECTED"
    REPAIR_APPLIED = "REPAIR_APPLIED"
    HUMAN_REVIEW_REQUESTED = "HUMAN_REVIEW_REQUESTED"
    HUMAN_REVIEW_COMPLETED = "HUMAN_REVIEW_COMPLETED"
    ITERATION_COMPLETED = "ITERATION_COMPLETED"
    LOOP_STOPPED = "LOOP_STOPPED"
    LOOP_COMPLETED = "LOOP_COMPLETED"


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    audit_schema_version: str = AUDIT_SCHEMA_VERSION
    sequence: int = Field(ge=0)
    timestamp: str
    loop_id: str
    iteration_number: int = Field(ge=0)
    event_type: AuditEventType
    actor: str
    input_refs: tuple[str, ...] = ()
    output_refs: tuple[str, ...] = ()
    decision: str = ""
    reason: str = ""
    prev_event_hash: str | None = None
    event_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _compute_event_hash(event: AuditEvent) -> str:
    payload = "\x1f".join(
        [
            str(event.sequence),
            event.timestamp,
            event.loop_id,
            str(event.iteration_number),
            event.event_type.value,
            event.actor,
            "|".join(event.input_refs),
            "|".join(event.output_refs),
            event.decision,
            event.reason,
            event.prev_event_hash or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditLog(BaseModel):
    """Append-only, hash-chained sequence of :class:`AuditEvent`.

    ``append`` never mutates ``self`` — it returns a new :class:`AuditLog`
    with one more event, so historical events can never be rewritten.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    loop_id: str
    events: tuple[AuditEvent, ...] = ()

    def append(
        self,
        *,
        timestamp: str,
        iteration_number: int,
        event_type: AuditEventType,
        actor: str,
        input_refs: tuple[str, ...] = (),
        output_refs: tuple[str, ...] = (),
        decision: str = "",
        reason: str = "",
    ) -> AuditLog:
        prev_hash = self.events[-1].event_hash if self.events else None
        event = AuditEvent(
            sequence=len(self.events),
            timestamp=timestamp,
            loop_id=self.loop_id,
            iteration_number=iteration_number,
            event_type=event_type,
            actor=actor,
            input_refs=input_refs,
            output_refs=output_refs,
            decision=decision,
            reason=reason,
            prev_event_hash=prev_hash,
        )
        event = event.model_copy(update={"event_hash": _compute_event_hash(event)})
        return self.model_copy(update={"events": (*self.events, event)})

    def verify_chain(self) -> bool:
        """Recompute every event's hash and confirm the chain is intact."""
        prev: str | None = None
        for i, event in enumerate(self.events):
            if event.sequence != i or event.prev_event_hash != prev:
                return False
            expected = _compute_event_hash(event.model_copy(update={"event_hash": ""}))
            if event.event_hash != expected:
                return False
            prev = event.event_hash
        return True

    def events_for_iteration(self, iteration_number: int) -> tuple[AuditEvent, ...]:
        return tuple(e for e in self.events if e.iteration_number == iteration_number)

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "event_count": len(self.events),
            "chain_valid": self.verify_chain(),
            "events": [e.to_dict() for e in self.events],
        }
