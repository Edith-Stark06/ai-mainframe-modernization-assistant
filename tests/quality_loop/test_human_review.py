"""Phase 11 — the human-review boundary: the model can never approve its own repair."""

from __future__ import annotations

import pytest

from app.quality_loop.errors import ReviewError
from app.quality_loop.review import (
    HumanReviewBoard,
    HumanReviewCheckpoint,
    ReviewDecision,
    ReviewStatus,
)


def _checkpoint(cid: str = "chk-1") -> HumanReviewCheckpoint:
    return HumanReviewCheckpoint(
        checkpoint_id=cid,
        loop_id="loop-1",
        iteration_number=0,
        reason="confidence below threshold",
        evidence=("javac: cannot find symbol",),
        proposed_action="replace missing semicolon",
    )


class TestCheckpointLifecycle:
    def test_new_checkpoint_starts_pending(self):
        board = HumanReviewBoard().open_checkpoint(_checkpoint())
        assert board.get("chk-1").status is ReviewStatus.PENDING
        assert board.pending() == (board.get("chk-1"),)

    def test_approve_records_decision(self):
        board = HumanReviewBoard().open_checkpoint(_checkpoint())
        board = board.review(
            "chk-1",
            ReviewDecision.APPROVE,
            "alice",
            "looks correct",
            candidate_id="cand-1",
            timestamp="t1",
        )
        assert board.get("chk-1").status is ReviewStatus.APPROVED
        record = board.review_for("chk-1")
        assert record is not None
        assert record.reviewer == "alice"
        assert record.decision is ReviewDecision.APPROVE
        assert record.comment == "looks correct"

    def test_reject_records_decision(self):
        board = HumanReviewBoard().open_checkpoint(_checkpoint())
        board = board.review(
            "chk-1",
            ReviewDecision.REJECT,
            "bob",
            "",
            candidate_id="cand-1",
            timestamp="t1",
        )
        assert board.get("chk-1").status is ReviewStatus.REJECTED

    def test_request_new_repair_and_stop_are_recorded(self):
        board = (
            HumanReviewBoard()
            .open_checkpoint(_checkpoint("chk-a"))
            .open_checkpoint(_checkpoint("chk-b"))
        )
        board = board.review(
            "chk-a",
            ReviewDecision.REQUEST_NEW_REPAIR,
            "carol",
            "",
            candidate_id="cand-1",
            timestamp="t1",
        )
        board = board.review(
            "chk-b",
            ReviewDecision.STOP,
            "carol",
            "",
            candidate_id="cand-1",
            timestamp="t2",
        )
        assert len(board.reviews) == 2
        assert {r.decision for r in board.reviews} == {
            ReviewDecision.REQUEST_NEW_REPAIR,
            ReviewDecision.STOP,
        }

    def test_unknown_checkpoint_raises(self):
        board = HumanReviewBoard()
        with pytest.raises(ReviewError):
            board.get("does-not-exist")

    def test_double_review_of_same_checkpoint_is_rejected(self):
        board = HumanReviewBoard().open_checkpoint(_checkpoint())
        board = board.review(
            "chk-1",
            ReviewDecision.APPROVE,
            "alice",
            "",
            candidate_id="cand-1",
            timestamp="t1",
        )
        with pytest.raises(ReviewError):
            board.review(
                "chk-1",
                ReviewDecision.REJECT,
                "bob",
                "",
                candidate_id="cand-1",
                timestamp="t2",
            )

    def test_review_is_never_silently_applied_without_a_record(self):
        board = HumanReviewBoard().open_checkpoint(_checkpoint())
        assert board.review_for("chk-1") is None  # nothing recorded yet
        board = board.review(
            "chk-1",
            ReviewDecision.APPROVE,
            "alice",
            "",
            candidate_id="cand-1",
            timestamp="t1",
        )
        assert board.review_for("chk-1") is not None  # now it is, explicitly

    def test_board_is_immutable_per_call(self):
        original = HumanReviewBoard()
        updated = original.open_checkpoint(_checkpoint())
        assert original.checkpoints == ()
        assert len(updated.checkpoints) == 1
