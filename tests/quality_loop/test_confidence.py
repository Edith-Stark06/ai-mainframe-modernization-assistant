"""Phase 11 — evidence-based heuristic confidence, never the model's own claim."""

from __future__ import annotations

from app.java_modernization.architecture.models import SourceRef
from app.quality_loop.confidence import (
    ConfidenceAction,
    ConfidenceFactors,
    compute_confidence,
    decide_confidence_action,
    factors_from_failure_group,
)
from app.quality_loop.failure import FailureCategory, FailureRecord
from app.quality_loop.models import QualityLoopConfig

_SM = SourceRef(source_id="S1", source_path="S1.cbl", line_start=1, line_end=2)


class TestComputeConfidence:
    def test_all_factors_true_gives_full_score(self):
        factors = ConfidenceFactors(
            has_source_mapping=True,
            has_business_rule=True,
            single_affected_artifact=True,
            diagnostic_precise=True,
            localized=True,
            context_complete=True,
        )
        score = compute_confidence(factors)
        assert score.value == 1.0
        assert "heuristic" in score.label
        assert "calibrated" not in score.label or "not calibrated" in score.label

    def test_all_factors_false_gives_zero(self):
        factors = ConfidenceFactors(
            has_source_mapping=False,
            has_business_rule=False,
            single_affected_artifact=False,
            diagnostic_precise=False,
            localized=False,
            context_complete=False,
        )
        assert compute_confidence(factors).value == 0.0

    def test_structurally_invalid_patch_caps_confidence_regardless_of_other_factors(
        self,
    ):
        factors = ConfidenceFactors(
            has_source_mapping=True,
            has_business_rule=True,
            single_affected_artifact=True,
            diagnostic_precise=True,
            localized=True,
            context_complete=True,
            patch_structurally_valid=False,
        )
        score = compute_confidence(factors)
        assert score.value <= 0.10

    def test_model_cannot_influence_the_score_directly(self):
        # ConfidenceFactors has no "self_reported_confidence" field at all --
        # the model's own claim about itself is structurally impossible to feed in.
        assert "self_reported" not in ConfidenceFactors.model_fields
        assert "llm_confidence" not in ConfidenceFactors.model_fields


class TestDecideConfidenceAction:
    def test_below_human_review_threshold_never_proposes_a_patch(self):
        cfg = QualityLoopConfig()
        action, _ = decide_confidence_action(0.50, cfg)
        assert action is ConfidenceAction.NO_PATCH_PROPOSE

    def test_between_human_review_and_repair_threshold_requires_review(self):
        cfg = QualityLoopConfig()
        action, _ = decide_confidence_action(0.70, cfg)
        assert action is ConfidenceAction.PROPOSE_FOR_REVIEW

    def test_between_repair_and_auto_apply_threshold_requires_review(self):
        cfg = QualityLoopConfig()
        action, _ = decide_confidence_action(0.85, cfg)
        assert action is ConfidenceAction.PROPOSE_FOR_REVIEW

    def test_at_or_above_auto_apply_threshold_auto_applies(self):
        cfg = QualityLoopConfig()
        action, _ = decide_confidence_action(0.95, cfg)
        assert action is ConfidenceAction.AUTO_APPLY

    def test_exact_boundary_values_are_inclusive_on_the_upper_side(self):
        cfg = QualityLoopConfig()
        below, _ = decide_confidence_action(0.5999, cfg)
        at, _ = decide_confidence_action(0.60, cfg)
        assert below is ConfidenceAction.NO_PATCH_PROPOSE
        assert at is ConfidenceAction.PROPOSE_FOR_REVIEW

    def test_thresholds_are_operator_configured_not_hardcoded(self):
        cfg = QualityLoopConfig(
            human_review_threshold=0.10,
            repair_confidence_threshold=0.20,
            auto_apply_threshold=0.30,
        )
        action, _ = decide_confidence_action(0.25, cfg)
        assert action is ConfidenceAction.PROPOSE_FOR_REVIEW
        action2, _ = decide_confidence_action(0.35, cfg)
        assert action2 is ConfidenceAction.AUTO_APPLY


class TestFactorsFromFailureGroup:
    def test_single_precise_failure_scores_high(self):
        f = FailureRecord(
            failure_id="F1",
            category=FailureCategory.COMPILATION_ERROR,
            severity="HIGH",
            message="e",
            affected_artifact="A.java",
            source_mapping=_SM,
            business_rule_ids=("BR-1",),
        )
        factors = factors_from_failure_group((f,), context_complete=True)
        assert factors.has_source_mapping is True
        assert factors.has_business_rule is True
        assert factors.single_affected_artifact is True
        assert factors.localized is True

    def test_multiple_artifacts_lowers_single_affected_artifact_factor(self):
        f1 = FailureRecord(
            failure_id="F1",
            category=FailureCategory.COMPILATION_ERROR,
            severity="HIGH",
            message="e1",
            affected_artifact="A.java",
            source_mapping=_SM,
        )
        f2 = FailureRecord(
            failure_id="F2",
            category=FailureCategory.COMPILATION_ERROR,
            severity="HIGH",
            message="e2",
            affected_artifact="B.java",
            source_mapping=_SM,
        )
        factors = factors_from_failure_group((f1, f2), context_complete=True)
        assert factors.single_affected_artifact is False
        assert factors.localized is False
