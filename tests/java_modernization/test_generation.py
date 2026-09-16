"""#126 — project assembly, traceability, unsupported behavior, no equivalence claim."""

from __future__ import annotations

import json

from app.java_modernization.architecture import build_architecture
from app.java_modernization.generation import MappingStatus, generate_project


def _project(bundle):
    return generate_project(bundle, build_architecture(bundle))


def test_project_is_deterministic_and_serialisable(elig_bundle):
    a = _project(elig_bundle)
    b = _project(elig_bundle)
    assert a.project_id == b.project_id
    assert a.content_hash() == b.content_hash()
    assert a.files == b.files
    json.dumps(a.manifest())
    assert a.semantic_equivalence_verified is False
    assert "candidate" in a.manifest()["note"].lower()


def test_translated_logic_is_the_existing_backend_output(elig_bundle):
    p = _project(elig_bundle)
    main = p.files[f"src/{p.main_class}.java"]
    assert main == elig_bundle.java_backend_output  # not re-translated


def test_methods_map_back_to_paragraphs_and_rules(elig_bundle):
    p = _project(elig_bundle)
    methods = {a.method_name: a for a in p.artifacts if a.kind == "method"}
    assert "checkEligibility" in methods
    m = methods["checkEligibility"]
    assert m.mapping_status == MappingStatus.MAPPED
    assert m.architecture_component_id
    assert set(m.business_rule_ids) == {"BR-001", "BR-002"}
    assert m.source_locations[0].paragraph == "CHECK-ELIGIBILITY"


def test_unmapped_method_is_marked_unavailable_not_fabricated(elig_bundle):
    p = _project(elig_bundle)
    run = next(a for a in p.artifacts if a.method_name == "run")
    assert run.mapping_status == MappingStatus.UNAVAILABLE
    assert run.architecture_component_id is None


def test_data_record_is_generated_from_working_storage(elig_bundle):
    p = _project(elig_bundle)
    rec_path = f"src/{p.main_class}State.java"
    assert rec_path in p.files
    assert "record" in p.files[rec_path]
    assert "wsAge" in p.files[rec_path]


def test_unsupported_behavior_is_carried_forward(elig_bundle):
    p = _project(elig_bundle)
    assert p.unsupported_behaviors
    assert any(u.diagnostic_code == "BE009" for u in p.unsupported_behaviors)
    assert p.generator_diagnostics


def test_manifest_lists_artifacts_and_assumptions(call_bundle):
    p = _project(call_bundle)
    man = p.manifest()
    assert man["artifacts"]
    assert man["semantic_equivalence_verified"] is False
    assert man["assumptions"]  # CALL target unavailable


def test_write_lays_out_the_project(elig_bundle, tmp_path):
    p = _project(elig_bundle)
    root = p.write(tmp_path)
    assert (root / "src" / f"{p.main_class}.java").exists()
    assert (root / "MODERNIZATION_MANIFEST.json").exists()
