from app.modernization.flow.models import Flow
from app.modernization.scoring.models import ModernizationScore
from app.modernization.recommendations.models import Priority, Recommendation
from app.modernization.recommendations.service import generate_recommendations


def test_generate_recommendations_high_complexity() -> None:
    flow = Flow(id="f1", name="F1", nodes=[], edges=[])
    score = ModernizationScore(
        complexity_score=0.9, coupling_score=0.1, overall_readiness=0.5
    )

    recs = generate_recommendations(flow, score)
    assert len(recs) == 1
    assert recs[0].id == "rec_complex_high"
    assert recs[0].priority == Priority.HIGH


def test_generate_recommendations_ready() -> None:
    flow = Flow(id="f1", name="F1", nodes=[], edges=[])
    score = ModernizationScore(
        complexity_score=0.1, coupling_score=0.1, overall_readiness=0.9
    )

    recs = generate_recommendations(flow, score)
    assert len(recs) == 1
    assert recs[0].id == "rec_ready"
    assert recs[0].priority == Priority.LOW


def test_generate_recommendations_multiple_and_ordering() -> None:
    flow = Flow(id="f1", name="F1", nodes=[], edges=[])
    # Triggers complex_high (HIGH), coupling_high (HIGH), readiness_low (HIGH)
    score = ModernizationScore(
        complexity_score=0.9, coupling_score=0.8, overall_readiness=0.2
    )

    recs = generate_recommendations(flow, score)
    assert len(recs) == 3
    # Check ordering by ID within HIGH priority
    # IDs: rec_complex_high, rec_coupling_high, rec_readiness_low
    assert recs[0].id == "rec_complex_high"
    assert recs[1].id == "rec_coupling_high"
    assert recs[2].id == "rec_readiness_low"


def test_generate_recommendations_insufficient_data() -> None:
    flow = Flow(id="f1", name="F1", nodes=[], edges=[])
    score = ModernizationScore(
        complexity_score=0.0,
        coupling_score=0.0,
        overall_readiness=0.0,
        metadata={"insufficient_data": True},
    )

    recs = generate_recommendations(flow, score)
    assert len(recs) == 1
    assert recs[0].id == "rec_insufficient_data"
    assert recs[0].priority == Priority.HIGH


def test_generate_recommendations_boundaries() -> None:
    flow = Flow(id="f1", name="F1", nodes=[], edges=[])
    score = ModernizationScore(
        complexity_score=0.5, coupling_score=0.7, overall_readiness=0.8
    )

    recs = generate_recommendations(flow, score)
    assert len(recs) == 3
    assert recs[0].id == "rec_coupling_high"  # HIGH
    assert recs[1].id == "rec_complex_med"  # MEDIUM
    assert recs[2].id == "rec_ready"  # LOW


def test_recommendation_to_dict() -> None:
    rec = Recommendation(
        id="1", title="Title", description="Desc", priority=Priority.MEDIUM
    )
    d = rec.to_dict()
    assert d["id"] == "1"
    assert d["title"] == "Title"
    assert d["priority"] == "MEDIUM"
