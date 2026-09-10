"""
#131 — compare a COBOL observation and a Java observation for one
:class:`BehavioralTestCase` and decide PASS / FAIL / INCONCLUSIVE.

PASS requires: both sides actually executed, every required observation
(display output and/or field state the test case says is expected) was
present on BOTH sides, and every one of them matched. Any missing
observation, any unexecuted side, or a #129 case already marked
non-executable is INCONCLUSIVE — never silently upgraded. A mismatch in
a required, actually-observed value is FAIL. Matching ASTs/IR/business
rules/compiler success are never consulted here — only the two
:class:`ExecutionResult` objects.
"""

from __future__ import annotations

import hashlib

from app.behavioral.comparison.models import (
    ArtifactVersions,
    BehavioralComparison,
    ComparisonStatus,
    Difference,
)
from app.behavioral.comparison.normalize import (
    normalize_trailing_line_whitespace,
    values_equal,
)
from app.behavioral.execution.models import ExecutionResult
from app.behavioral.extraction.models import BehavioralTestCase

__all__ = ["compare_observation"]


def _stdout_text(obs: ExecutionResult) -> str | None:
    items = sorted(
        (int(k[len("stdout[") : -1]), v)
        for k, v in obs.outputs.items()
        if k.startswith("stdout[") and k.endswith("]")
    )
    if not items:
        return None
    return normalize_trailing_line_whitespace("\n".join(v for _, v in items))


def _field_value(obs: ExecutionResult, name: str) -> str | None:
    if name in obs.state_changes:
        return obs.state_changes[name]
    return obs.outputs.get(name)


def _comparison_id(test_id: str, versions: ArtifactVersions) -> str:
    payload = "\x1f".join(
        (
            test_id,
            versions.cobol_source_hash,
            versions.java_project_hash,
            versions.architecture_hash,
            versions.test_suite_hash,
        )
    )
    return f"CMP-{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


def compare_observation(
    test: BehavioralTestCase,
    cobol_obs: ExecutionResult,
    java_obs: ExecutionResult,
    *,
    artifact_versions: ArtifactVersions,
) -> BehavioralComparison:
    def result(
        status: ComparisonStatus,
        reason: str,
        differences: tuple[Difference, ...] = (),
    ) -> BehavioralComparison:
        return BehavioralComparison(
            comparison_id=_comparison_id(test.test_id, artifact_versions),
            test_id=test.test_id,
            status=status,
            cobol_observation=cobol_obs,
            java_observation=java_obs,
            differences=differences,
            source_refs=test.source_refs,
            business_rule_ids=test.business_rule_ids,
            confidence=test.confidence,
            reason=reason,
            artifact_versions=artifact_versions,
        )

    # --- #129 already said this case cannot be verified ----------------
    if not test.executable:
        return result(
            ComparisonStatus.INCONCLUSIVE,
            test.inconclusive_reason or "test case marked non-executable by #129",
        )

    # --- both sides must have actually run ------------------------------
    if not cobol_obs.executed:
        return result(
            ComparisonStatus.INCONCLUSIVE,
            "COBOL was not executed: "
            + ("; ".join(cobol_obs.diagnostics) or "runtime unavailable"),
        )
    if not java_obs.executed:
        return result(
            ComparisonStatus.INCONCLUSIVE,
            "Java was not executed: "
            + ("; ".join(java_obs.diagnostics) or "execution failed"),
        )
    if not cobol_obs.success:
        return result(
            ComparisonStatus.INCONCLUSIVE,
            "COBOL failed before producing a comparable observation: "
            + ("; ".join(cobol_obs.diagnostics) or "non-zero exit"),
        )
    if not java_obs.success:
        return result(
            ComparisonStatus.INCONCLUSIVE,
            "Java failed before reaching the required behavior: "
            + ("; ".join(java_obs.diagnostics) or "non-zero exit"),
        )

    differences: list[Difference] = []
    missing: list[str] = []
    compared_anything = False

    # --- display output ---------------------------------------------
    display_expected = [o for o in test.expected_outputs if o.kind == "display"]
    if display_expected:
        c_text, j_text = _stdout_text(cobol_obs), _stdout_text(java_obs)
        if c_text is None or j_text is None:
            missing.append("stdout")
        else:
            compared_anything = True
            if not values_equal(c_text, j_text):
                differences.append(
                    Difference(
                        field="stdout",
                        cobol_value=c_text,
                        java_value=j_text,
                        expected_behavior=display_expected[0].expected_value,
                        source_ref=test.source_refs[0] if test.source_refs else None,
                        business_rule_id=(
                            test.business_rule_ids[0]
                            if test.business_rule_ids
                            else None
                        ),
                    )
                )

    # --- field-observable state / outputs ----------------------------
    required_fields = {o.name for o in test.expected_outputs if o.kind == "field"} | {
        s.field for s in test.expected_state_changes
    }
    expected_by_field = {s.field: s.to_value for s in test.expected_state_changes}
    for o in test.expected_outputs:
        if o.kind == "field":
            expected_by_field.setdefault(o.name, o.expected_value)

    for field in sorted(required_fields):
        c_val, j_val = _field_value(cobol_obs, field), _field_value(java_obs, field)
        if c_val is None or j_val is None:
            missing.append(field)
            continue
        compared_anything = True
        if not values_equal(c_val, j_val):
            src = next(
                (s for s in test.expected_state_changes if s.field == field), None
            )
            differences.append(
                Difference(
                    field=field,
                    cobol_value=c_val,
                    java_value=j_val,
                    expected_behavior=expected_by_field.get(field, ""),
                    source_ref=test.source_refs[0] if test.source_refs else None,
                    business_rule_id=(
                        test.business_rule_ids[0] if test.business_rule_ids else None
                    ),
                    severity="behavioral" if src else "informational",
                )
            )

    if missing:
        return result(
            ComparisonStatus.INCONCLUSIVE,
            "required observation(s) not available from both sides: "
            + ", ".join(sorted(set(missing))),
        )

    if differences:
        return result(
            ComparisonStatus.FAIL,
            f"{len(differences)} behavioral difference(s) observed",
            tuple(differences),
        )

    if not compared_anything:
        # nothing was actually asserted (e.g. a "no rule fires" branch
        # test with no observable expectation) — a partial/empty match
        # is never upgraded to PASS
        return result(
            ComparisonStatus.INCONCLUSIVE,
            "no observable expected behavior was available to compare",
        )

    return result(ComparisonStatus.PASS, "all required observations matched")
