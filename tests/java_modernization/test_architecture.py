"""#125 — architecture schema, evidence, traceability, determinism."""

from __future__ import annotations

import json

from app.java_modernization.architecture import (
    ComponentType,
    JavaArchitecture,
    build_architecture,
)


def test_architecture_is_serialisable_and_deterministic(elig_bundle):
    a = build_architecture(elig_bundle)
    b = build_architecture(elig_bundle)
    assert isinstance(a, JavaArchitecture)
    json.dumps(a.to_dict())
    assert a.architecture_id == b.architecture_id
    assert a.content_hash() == b.content_hash()
    assert a.to_dict() == b.to_dict()
    assert a.semantic_equivalence_verified is False


def test_architecture_id_is_content_derived(elig_bundle, if_else_bundle):
    assert build_architecture(elig_bundle).architecture_id.startswith(
        "arch-ELIGIBILITY-"
    )
    assert (
        build_architecture(elig_bundle).architecture_id
        != build_architecture(if_else_bundle).architecture_id
    )


def test_every_component_has_evidence_and_a_source_ref(elig_bundle):
    a = build_architecture(elig_bundle)
    assert a.components
    for c in a.components:
        assert c.source_refs, f"{c.name} has no source ref"
        assert c.evidence, f"{c.name} has no evidence"
        for e in c.evidence:
            assert e.kind in {
                "dependency",
                "business_rule",
                "risk",
                "strategy",
                "data_item",
                "coverage",
            }


def test_business_rules_are_referenced_not_duplicated(elig_bundle):
    a = build_architecture(elig_bundle)
    all_rule_ids = {rid for c in a.components for rid in c.business_rule_ids}
    real = {r["rule_id"] for r in (elig_bundle.business_rules or [])}
    assert all_rule_ids
    assert all_rule_ids <= real  # only real rule ids, referenced by id
    # the architecture stores rule IDs, not rule logic
    for c in a.components:
        assert "MOVE " not in c.responsibility


def test_source_mappings_point_at_real_lines(elig_bundle):
    a = build_architecture(elig_bundle)
    n_lines = len(elig_bundle.source.splitlines())
    for refs in a.source_mappings.values():
        for r in refs:
            if r.line_start is not None:
                assert 1 <= r.line_start <= n_lines
            assert r.source_id == "ELIGIBILITY"


def test_external_call_becomes_an_interface_and_assumption(call_bundle):
    a = build_architecture(call_bundle)
    assert a.external_interfaces
    iface = a.external_interfaces[0]
    assert iface.kind == "CALL"
    assert iface.modeled is False
    assert any(c.type is ComponentType.INTEGRATION for c in a.components)
    assert any("unavailable" in x.statement.lower() for x in a.assumptions)


def test_no_evidence_means_no_interface(if_else_bundle):
    a = build_architecture(if_else_bundle)
    assert a.external_interfaces == ()  # if_else.cbl has no CALL
    assert all(c.type is not ComponentType.INTEGRATION for c in a.components)


def test_strategy_mapping_is_from_phase4_not_invented(elig_bundle):
    a = build_architecture(elig_bundle)
    assert a.primary_strategy is not None
    assert a.primary_strategy.recommendation_id == (
        elig_bundle.strategy["primary"]["recommendation_id"]
    )
    assert a.primary_strategy.strategy == elig_bundle.strategy["primary"]["strategy"]


def test_generator_stub_becomes_explicit_unsupported_behavior(elig_bundle):
    a = build_architecture(elig_bundle)
    # eligibility's PERFORM'd paragraphs are emitted as TODO stubs by the
    # existing generator -> must be surfaced, not hidden
    assert any(u.diagnostic_code == "BE009" for u in a.unsupported_behaviors)
    for u in a.unsupported_behaviors:
        assert "NOT" in u.impact.upper()


def test_data_model_maps_working_storage_fields(elig_bundle):
    a = build_architecture(elig_bundle)
    assert a.data_model
    names = {d.name for d in a.data_model}
    assert "wsAge" in names
    assert any(c.type is ComponentType.DTO for c in a.components)
