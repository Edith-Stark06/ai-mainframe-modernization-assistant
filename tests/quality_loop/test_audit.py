"""Phase 11 — append-only, hash-chained audit log."""

from __future__ import annotations

from app.quality_loop.audit import AuditEventType, AuditLog


def _log_with_events(n: int = 3) -> AuditLog:
    log = AuditLog(loop_id="loop-1")
    for i in range(n):
        log = log.append(
            timestamp=f"t{i}",
            iteration_number=0,
            event_type=AuditEventType.ITERATION_COMPLETED,
            actor="quality_loop",
            decision=f"step-{i}",
        )
    return log


class TestAppendOnly:
    def test_append_returns_a_new_log_never_mutates(self):
        log = AuditLog(loop_id="loop-1")
        appended = log.append(
            timestamp="t0",
            iteration_number=0,
            event_type=AuditEventType.ANALYSIS_STARTED,
            actor="quality_loop",
        )
        assert log.events == ()
        assert len(appended.events) == 1

    def test_sequence_numbers_are_ordered_and_stable(self):
        log = _log_with_events(4)
        assert [e.sequence for e in log.events] == [0, 1, 2, 3]

    def test_events_are_never_rewritten_by_further_appends(self):
        log = _log_with_events(2)
        first_event = log.events[0]
        log2 = log.append(
            timestamp="t9",
            iteration_number=1,
            event_type=AuditEventType.LOOP_COMPLETED,
            actor="quality_loop",
        )
        assert log2.events[0] == first_event


class TestHashChain:
    def test_chain_is_valid_after_several_appends(self):
        log = _log_with_events(5)
        assert log.verify_chain() is True

    def test_each_event_references_the_previous_hash(self):
        log = _log_with_events(3)
        assert log.events[0].prev_event_hash is None
        assert log.events[1].prev_event_hash == log.events[0].event_hash
        assert log.events[2].prev_event_hash == log.events[1].event_hash

    def test_tampering_with_an_event_breaks_the_chain(self):
        log = _log_with_events(3)
        tampered_event = log.events[1].model_copy(update={"decision": "TAMPERED"})
        tampered_log = log.model_copy(
            update={"events": (log.events[0], tampered_event, log.events[2])}
        )
        assert tampered_log.verify_chain() is False


class TestReconstruction:
    def test_events_for_iteration_filters_correctly(self):
        log = AuditLog(loop_id="loop-1")
        log = log.append(
            timestamp="t0",
            iteration_number=0,
            event_type=AuditEventType.COMPILATION_STARTED,
            actor="quality_loop",
        )
        log = log.append(
            timestamp="t1",
            iteration_number=1,
            event_type=AuditEventType.COMPILATION_STARTED,
            actor="quality_loop",
        )
        assert len(log.events_for_iteration(0)) == 1
        assert len(log.events_for_iteration(1)) == 1

    def test_every_major_event_type_can_be_recorded_in_order(self):
        log = AuditLog(loop_id="loop-1")
        ordered_types = [
            AuditEventType.ANALYSIS_STARTED,
            AuditEventType.ANALYSIS_COMPLETED,
            AuditEventType.GENERATION_STARTED,
            AuditEventType.GENERATION_COMPLETED,
            AuditEventType.COMPILATION_STARTED,
            AuditEventType.COMPILATION_COMPLETED,
            AuditEventType.TEST_STARTED,
            AuditEventType.TEST_COMPLETED,
            AuditEventType.COMPARISON_STARTED,
            AuditEventType.COMPARISON_COMPLETED,
            AuditEventType.FAILURE_DETECTED,
            AuditEventType.REPAIR_REQUESTED,
            AuditEventType.REPAIR_PROPOSED,
            AuditEventType.REPAIR_REJECTED,
            AuditEventType.REPAIR_APPLIED,
            AuditEventType.HUMAN_REVIEW_REQUESTED,
            AuditEventType.HUMAN_REVIEW_COMPLETED,
            AuditEventType.ITERATION_COMPLETED,
            AuditEventType.LOOP_STOPPED,
            AuditEventType.LOOP_COMPLETED,
        ]
        for i, et in enumerate(ordered_types):
            log = log.append(
                timestamp=f"t{i}",
                iteration_number=0,
                event_type=et,
                actor="quality_loop",
            )
        assert [e.event_type for e in log.events] == ordered_types
        assert log.verify_chain() is True

    def test_to_dict_reports_chain_validity(self):
        log = _log_with_events(2)
        d = log.to_dict()
        assert d["chain_valid"] is True
        assert d["event_count"] == 2
        assert len(d["events"]) == 2
