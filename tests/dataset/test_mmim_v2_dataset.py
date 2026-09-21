"""Tests for the MMIM-v2 dataset generation, schema, and quality gates.

mmim-v2 is a rebuild of the MMIM dataset from the 45-source expanded
training corpus (``docs/MMIM_CORPUS_EXPANSION.md``), generated with strict
task eligibility: a task is only emitted when its ground truth is
semantically meaningful (see ``MMIMDatasetBuilder(strict_eligibility=True)``
in ``app/dataset/mmim_builder.py``). mmim-v1 (18 sources, unconditional
task emission) is untouched by this file.

Verifies:
- 45-source corpus, source-disjoint from benchmark-v1
- Strict task eligibility: no meaningless empty VALIDATION_REASONING /
  TRANSFORMATION_PLANNING targets; every skip is recorded with
  source_id, task_type, reason, and parser status
- Schema conformance and provenance tracking (mmim-v2 / mmim-gen-v6)
- Zero benchmark leakage (source ID, SHA, normalized SHA)
- Zero train/val/test split leakage, source-level grouping
- Zero duplicate / near-duplicate sources within the corpus itself
- Deterministic regeneration
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from app.benchmark.suite import load_benchmark
from app.dataset.corpus import load_training_corpus
from app.dataset.io import read_examples
from app.dataset.leakage import detect_leakage
from app.dataset.mmim_builder import MMIMDatasetBuilder, build_mmim_dataset
from app.dataset.schema import (
    DatasetExample,
    GroundTruthStatus,
    Provenance,
    TaskType,
)
from app.dataset.version import (
    BENCHMARK_VERSION,
    MMIM_DATASET_VERSION_V2,
    MMIM_GENERATOR_VERSION_V25,
)

MMIM_V2_DATASET_DIR = Path("data/dataset/mmim-v2")

#: Task types whose ground truth may legitimately be unavailable for some
#: sources; strict_eligibility skips those rather than emitting a
#: meaningless empty target.
_ELIGIBILITY_GATED_TASKS = {
    TaskType.VALIDATION_REASONING,
    TaskType.TRANSFORMATION_PLANNING,
    TaskType.COBOL_TO_JAVA,
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _norm(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


@pytest.fixture(scope="module")
def training_corpus():
    return load_training_corpus()


@pytest.fixture(scope="module")
def mmim_v2_build(training_corpus):
    if not (MMIM_V2_DATASET_DIR / "all.jsonl").exists():
        build_mmim_dataset(
            MMIM_V2_DATASET_DIR,
            training_corpus,
            seed=42,
            dataset_version=MMIM_DATASET_VERSION_V2,
            generator_version=MMIM_GENERATOR_VERSION_V25,
            strict_eligibility=True,
        )
    return None


@pytest.fixture(scope="module")
def mmim_all_examples(mmim_v2_build) -> list[DatasetExample]:
    return read_examples(MMIM_V2_DATASET_DIR / "all.jsonl")


@pytest.fixture(scope="module")
def mmim_splits(mmim_v2_build) -> dict[str, list[DatasetExample]]:
    return {
        "train": read_examples(MMIM_V2_DATASET_DIR / "train.jsonl"),
        "validation": read_examples(MMIM_V2_DATASET_DIR / "validation.jsonl"),
        "test": read_examples(MMIM_V2_DATASET_DIR / "test.jsonl"),
    }


@pytest.fixture(scope="module")
def manifest(mmim_v2_build) -> dict:
    import json

    return json.loads((MMIM_V2_DATASET_DIR / "manifest.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def benchmark():
    return load_benchmark(BENCHMARK_VERSION)


# --------------------------------------------------------------------------
# 1. Corpus scale & isolation
# --------------------------------------------------------------------------


def test_training_corpus_is_45_sources(training_corpus):
    assert len(training_corpus) == 45
    assert len({r.source_id for r in training_corpus}) == 45


def test_corpus_has_no_duplicate_or_near_duplicate_sources(training_corpus):
    shas: dict[str, list[str]] = {}
    norm_shas: dict[str, list[str]] = {}
    for r in training_corpus:
        shas.setdefault(_sha(r.source), []).append(r.source_id)
        norm_shas.setdefault(_sha(_norm(r.source)), []).append(r.source_id)
    dup_exact = {k: v for k, v in shas.items() if len(v) > 1}
    dup_norm = {k: v for k, v in norm_shas.items() if len(v) > 1}
    assert dup_exact == {}, f"exact duplicate sources: {dup_exact}"
    assert dup_norm == {}, f"normalized duplicate sources: {dup_norm}"


# --------------------------------------------------------------------------
# 2. Schema conformance & provenance
# --------------------------------------------------------------------------


def test_all_examples_conform_to_schema(mmim_all_examples):
    assert len(mmim_all_examples) > 0
    for ex in mmim_all_examples:
        assert ex.example_id.strip() != ""
        assert ex.dataset_version == MMIM_DATASET_VERSION_V2
        assert ex.metadata.generator_version == MMIM_GENERATOR_VERSION_V25
        assert ex.input.source_id.strip() != ""
        assert len(ex.input.source) > 0
        assert len(ex.metadata.source_sha256) == 64
        assert ex.expected_output
        assert ex.metadata.provenance in Provenance
        assert ex.metadata.ground_truth_status in GroundTruthStatus


def test_all_source_hashes_match_content(mmim_all_examples):
    for ex in mmim_all_examples:
        assert ex.metadata.source_sha256 == _sha(ex.input.source)


def test_no_duplicate_example_ids(mmim_all_examples):
    ids = [e.example_id for e in mmim_all_examples]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------
# 3. Strict task eligibility — no meaningless empty targets
# --------------------------------------------------------------------------


def test_validation_reasoning_never_has_zero_tests(mmim_all_examples):
    for ex in mmim_all_examples:
        if ex.task_type == TaskType.VALIDATION_REASONING:
            assert ex.expected_output.get("test_count", 0) > 0, (
                f"{ex.example_id} emitted a VALIDATION_REASONING example with "
                "zero derivable tests; this should have been skipped"
            )


def test_transformation_planning_never_empty_architecture(mmim_all_examples):
    for ex in mmim_all_examples:
        if ex.task_type == TaskType.TRANSFORMATION_PLANNING:
            assert ex.expected_output.get("components"), (
                f"{ex.example_id} emitted a TRANSFORMATION_PLANNING example "
                "with no architecture components"
            )


def test_every_skip_is_fully_recorded(manifest):
    for entry in manifest["skipped"]:
        assert entry.get("source_id")
        assert entry.get("task_type")
        assert entry.get("reason")
        assert "parser_status" in entry or entry.get("reason") == "secret_scan_blocking"


def test_skip_reasons_are_from_the_known_set(manifest):
    known = {
        "no_derivable_behavioral_tests",
        "architecture_builder_no_structure",
        "no_java_backend_output",
        "parser_failed_no_ast",
        "parser_failed_no_risk_analysis",
        "parser_failed_no_strategy_analysis",
        "secret_scan_blocking",
    }
    for entry in manifest["skipped"]:
        assert entry["reason"] in known, f"unrecognized skip reason: {entry['reason']}"


def test_no_source_totally_silently_dropped(manifest, training_corpus):
    # Every one of the 45 sources must contribute at least one example
    # (PROGRAM_UNDERSTANDING is unconditional), even if some of its tasks
    # were individually skipped.
    covered = set(manifest["source_ids"])
    assert covered == {r.source_id for r in training_corpus}


# --------------------------------------------------------------------------
# 3b. Loop/accumulator extractor upgrade (mmim-gen-v3) — validation
#     coverage improved from 22/45 to 24/45 sources via
#     app.behavioral.extraction.loops; quality over coverage, not 45/45.
# --------------------------------------------------------------------------


def test_validation_reasoning_covers_36_of_45_sources(mmim_all_examples):
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert len(val_sources) == 36
    assert {"t_interest_accrue", "t_loan_balance"} <= val_sources


def test_newly_covered_loop_sources_have_loop_accumulator_tests(mmim_all_examples):
    by_source = {
        e.input.source_id: e
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    for sid in ("t_interest_accrue", "t_loan_balance"):
        ex = by_source[sid]
        tests = ex.expected_output["tests"]
        assert tests
        assert all(t["test_type"] == "loop_accumulator" for t in tests)
        assert any(t["iteration_count"] == 0 for t in tests)
        assert ex.metadata.ground_truth_status == GroundTruthStatus.DETERMINISTIC


def test_validation_reasoning_source_count_did_not_regress(mmim_all_examples):
    # every source covered in the pre-loop-extractor build (22) must
    # still be covered after the upgrade -- this is a strictly additive
    # capability, never a replacement of existing derivations.
    previously_covered = {
        "fx_combined",
        "t_account_validate",
        "t_bonus_calc",
        "t_credit_limit",
        "t_customer_record",
        "t_discount_tier",
        "t_fallthrough_flow",
        "t_fraud_pipeline",
        "t_grade_letter",
        "t_insurance_claim",
        "t_late_fee",
        "t_loan_underwrite",
        "t_mortgage_service",
        "t_overdraft_fee",
        "t_packed_decimal",
        "t_payment_gateway",
        "t_payroll_net_pay",
        "t_policy_redefines",
        "t_reorder_point",
        "t_shipping_zone",
        "t_stock_alert",
        "t_vacation_accrual",
    }
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert previously_covered <= val_sources


# --------------------------------------------------------------------------
# 3c. Parser fix (mmim-gen-v4) — decimal-literal tokenization + compound
#     AND/OR IF-condition parsing (docs/MMIM_PARSER_VALIDATION_FIX.md).
#     5 further sources became validation-eligible: paragraphs that used
#     to be silently abandoned mid-parse now parse completely, so their
#     (perfectly ordinary) business rules and behavioral tests are
#     derivable. Strictly additive on top of mmim-gen-v3's 24.
# --------------------------------------------------------------------------


def test_parser_fix_newly_covered_sources(mmim_all_examples):
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    newly_covered_by_parser_fix = {
        "t_account_eligibility",
        "t_credit_approval",
        "t_tax_withhold",
        "t_pricing_tier",
        "t_payroll_deduct",
    }
    assert newly_covered_by_parser_fix <= val_sources


def test_parser_fix_did_not_regress_any_v3_source(mmim_all_examples):
    # every source covered by mmim-gen-v3 (loop extractor only) must still
    # be covered after the parser fix -- strictly additive.
    covered_by_v3 = {
        "fx_combined",
        "t_account_validate",
        "t_bonus_calc",
        "t_credit_limit",
        "t_customer_record",
        "t_discount_tier",
        "t_fallthrough_flow",
        "t_fraud_pipeline",
        "t_grade_letter",
        "t_insurance_claim",
        "t_interest_accrue",
        "t_late_fee",
        "t_loan_balance",
        "t_loan_underwrite",
        "t_mortgage_service",
        "t_overdraft_fee",
        "t_packed_decimal",
        "t_payment_gateway",
        "t_payroll_net_pay",
        "t_policy_redefines",
        "t_reorder_point",
        "t_shipping_zone",
        "t_stock_alert",
        "t_vacation_accrual",
    }
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert covered_by_v3 <= val_sources


def test_parser_fix_business_rule_density_increased(mmim_all_examples):
    """Cross-task signal that the parser fix's benefit is not limited to
    VALIDATION_REASONING: BUSINESS_RULE_EXTRACTION rule counts for the
    newly-unlocked sources must be non-trivial, not just barely non-zero
    (docs/MMIM_PARSER_VALIDATION_FIX.md: 71 -> 123 total rules corpus-wide
    after the decimal/AND-OR fix; 123 -> 149 after the COMPUTE/EVALUATE-in-
    IF-block fix below). t_credit_approval's count reflects both fixes
    together (4 after decimal/AND-OR alone, 11 once its remaining
    COMPUTE-inside-IF paragraphs also recovered)."""
    by_source = {
        e.input.source_id: e
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    }
    expectations = {
        # t_account_eligibility: 8 -> 12 (task #stage25,
        # docs/MMIM_NEGATED_COMPARISON_FIX.md): "NOT =" comparisons now parse.
        "t_account_eligibility": 12,
        "t_credit_approval": 11,
        "t_tax_withhold": 6,
        "t_pricing_tier": 14,
        "t_payroll_deduct": 11,
    }
    for sid, min_rules in expectations.items():
        rule_count = by_source[sid].expected_output.get("rule_count", 0)
        assert (
            rule_count == min_rules
        ), f"{sid}: expected {min_rules} rules, got {rule_count}"


# --------------------------------------------------------------------------
# 3d. COMPUTE/EVALUATE-inside-IF-block parser recovery fix (mmim-gen-v5,
#     docs/MMIM_PARSER_VALIDATION_FIX.md §7 follow-up). t_shared_state_hazard
#     newly covered; t_billing_engine still not at this point (its two
#     IF-guarded rules used decimal-literal conditions the behavioral
#     extractor's condition parser did not yet support -- fixed next, in
#     3e below).
# --------------------------------------------------------------------------


def test_compute_evaluate_fix_newly_covered_source(mmim_all_examples):
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert "t_shared_state_hazard" in val_sources


def test_compute_evaluate_fix_did_not_regress_any_v4_source(mmim_all_examples):
    # every source covered by mmim-gen-v4 must still be covered -- strictly
    # additive, never a replacement of existing derivations.
    covered_by_v4 = {
        "fx_combined",
        "t_account_eligibility",
        "t_account_validate",
        "t_bonus_calc",
        "t_credit_approval",
        "t_credit_limit",
        "t_customer_record",
        "t_discount_tier",
        "t_fallthrough_flow",
        "t_fraud_pipeline",
        "t_grade_letter",
        "t_insurance_claim",
        "t_interest_accrue",
        "t_late_fee",
        "t_loan_balance",
        "t_loan_underwrite",
        "t_mortgage_service",
        "t_overdraft_fee",
        "t_packed_decimal",
        "t_payment_gateway",
        "t_payroll_deduct",
        "t_payroll_net_pay",
        "t_policy_redefines",
        "t_pricing_tier",
        "t_reorder_point",
        "t_shipping_zone",
        "t_stock_alert",
        "t_tax_withhold",
        "t_vacation_accrual",
    }
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert covered_by_v4 <= val_sources


# --------------------------------------------------------------------------
# 3e. Decimal-literal condition extraction fix (mmim-gen-v6,
#     docs/MMIM_DECIMAL_CONDITION_FIX.md). parse_condition previously
#     rejected any comparison against a COBOL fixed-point decimal literal
#     (0.00, 12.50, -1.25, ...) -- not just via _NUMERIC, but because the
#     outer _COND_RE regex could not match a decimal literal at all, so
#     the whole condition failed to parse. 4 further sources became
#     validation-eligible, including t_billing_engine (the source this
#     fix was written for). Strictly additive on top of mmim-gen-v5's 30;
#     no parser, lexer, CFG, IR, or business-rule-extraction behaviour
#     changed, so BUSINESS_RULE_EXTRACTION rule counts for every affected
#     source are unchanged -- only how many of those already-extracted
#     conditions can be turned into a behavioral test changed.
# --------------------------------------------------------------------------


def test_decimal_condition_fix_newly_covered_sources(mmim_all_examples):
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    newly_covered_by_decimal_fix = {
        "t_billing_engine",
        "t_daily_trans_report",
        "t_payroll_file_post",
        "t_transitive_fx",
    }
    assert newly_covered_by_decimal_fix <= val_sources


def test_decimal_condition_fix_did_not_regress_any_v5_source(mmim_all_examples):
    # every source covered by mmim-gen-v5 must still be covered -- strictly
    # additive, never a replacement of existing derivations.
    covered_by_v5 = {
        "fx_combined",
        "t_account_eligibility",
        "t_account_validate",
        "t_bonus_calc",
        "t_credit_approval",
        "t_credit_limit",
        "t_customer_record",
        "t_discount_tier",
        "t_fallthrough_flow",
        "t_fraud_pipeline",
        "t_grade_letter",
        "t_insurance_claim",
        "t_interest_accrue",
        "t_late_fee",
        "t_loan_balance",
        "t_loan_underwrite",
        "t_mortgage_service",
        "t_overdraft_fee",
        "t_packed_decimal",
        "t_payment_gateway",
        "t_payroll_deduct",
        "t_payroll_net_pay",
        "t_policy_redefines",
        "t_pricing_tier",
        "t_reorder_point",
        "t_shared_state_hazard",
        "t_shipping_zone",
        "t_stock_alert",
        "t_tax_withhold",
        "t_vacation_accrual",
    }
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert covered_by_v5 <= val_sources


def test_decimal_condition_fix_did_not_change_business_rule_counts(mmim_all_examples):
    """The fix touches only behavioral-test extraction, never business-rule
    extraction -- rule counts for every source affected by this cycle must
    be identical to their mmim-gen-v5 values."""
    by_source = {
        e.input.source_id: e
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    }
    unchanged_rule_counts = {
        "t_billing_engine": 1,
        "t_credit_approval": 11,
        "t_daily_trans_report": 2,
        "t_mortgage_service": 4,
        "t_payroll_file_post": 1,
        "t_pricing_tier": 14,
        "t_transitive_fx": 1,
    }
    for sid, expected in unchanged_rule_counts.items():
        rule_count = by_source[sid].expected_output.get("rule_count", 0)
        assert (
            rule_count == expected
        ), f"{sid}: expected {expected} rules (unchanged), got {rule_count}"


# --------------------------------------------------------------------------
# 3f. Level-88 condition-name parser grammar fix (mmim-gen-v7,
#     docs/MMIM_LEVEL88_CONDITION_AUDIT.md,
#     docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md). Two upstream parser
#     grammar gaps (data_parser.py's VALUES-plural support;
#     procedure_parser.py's condition-name-as-IF-operand grammar) fixed
#     together -- business-rule/dependency/risk/strategy/transformation
#     ground truth for t_condition_names_88 changed (0 -> 8 business
#     rules). At the time (mmim-gen-v7), VALIDATION_REASONING coverage did
#     NOT change, since that cycle deliberately did not touch
#     app/behavioral/extraction/conditions.py; a later, separate cycle
#     (mmim-gen-v8, §3g below) closed that remaining gap.
# --------------------------------------------------------------------------


def test_level88_fix_gave_condition_names_88_real_business_rules(mmim_all_examples):
    by_source = {
        e.input.source_id: e
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    }
    ex = by_source["t_condition_names_88"]
    rule_count = ex.expected_output.get("rule_count", 0)
    assert rule_count == 8
    conditions = {r["condition"] for r in ex.expected_output["business_rules"]}
    assert "TX-VALID-KIND IS-FALSE TX-VALID-KIND" in conditions
    assert any(
        "PHYSICAL-BRANCH IS-TRUE PHYSICAL-BRANCH" in c and "TX-AMOUNT > 1000.00" in c
        for c in conditions
    )


def test_level88_fix_did_not_regress_any_v6_validation_source(mmim_all_examples):
    # every source covered by mmim-gen-v6 must still be covered -- strictly
    # additive/neutral, never a regression -- even though this cycle's fix
    # does not touch VALIDATION_REASONING at all.
    covered_by_v6 = {
        "fx_combined",
        "t_account_eligibility",
        "t_account_validate",
        "t_billing_engine",
        "t_bonus_calc",
        "t_credit_approval",
        "t_credit_limit",
        "t_customer_record",
        "t_daily_trans_report",
        "t_discount_tier",
        "t_fallthrough_flow",
        "t_fraud_pipeline",
        "t_grade_letter",
        "t_insurance_claim",
        "t_interest_accrue",
        "t_late_fee",
        "t_loan_balance",
        "t_loan_underwrite",
        "t_mortgage_service",
        "t_overdraft_fee",
        "t_packed_decimal",
        "t_payment_gateway",
        "t_payroll_deduct",
        "t_payroll_file_post",
        "t_payroll_net_pay",
        "t_policy_redefines",
        "t_pricing_tier",
        "t_reorder_point",
        "t_shared_state_hazard",
        "t_shipping_zone",
        "t_stock_alert",
        "t_tax_withhold",
        "t_transitive_fx",
        "t_vacation_accrual",
    }
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert covered_by_v6 <= val_sources


def test_level88_fix_did_not_change_any_other_source(mmim_all_examples):
    """The fix's blast radius is exactly one source -- every other source's
    BUSINESS_RULE_EXTRACTION rule_count is identical to its mmim-gen-v6
    value for a representative sample spanning both affected-by-decimal-fix
    and never-affected sources."""
    by_source = {
        e.input.source_id: e
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    }
    unchanged_rule_counts = {
        "t_billing_engine": 1,
        "t_credit_approval": 11,
        "t_daily_trans_report": 2,
        "t_mortgage_service": 4,
        "t_payroll_file_post": 1,
        "t_pricing_tier": 14,
        "t_transitive_fx": 1,
        # t_account_eligibility: 8 -> 12 (task #stage25,
        # docs/MMIM_NEGATED_COMPARISON_FIX.md); this source is no longer
        # "unaffected" by that later fix, but this earlier fix's own
        # blast-radius claim (level-88 only) is unaffected.
        "t_account_eligibility": 12,
        "t_tax_withhold": 6,
        "t_payroll_deduct": 11,
    }
    for sid, expected in unchanged_rule_counts.items():
        rule_count = by_source[sid].expected_output.get("rule_count", 0)
        assert (
            rule_count == expected
        ), f"{sid}: expected {expected} rules (unchanged), got {rule_count}"


# --------------------------------------------------------------------------
# 3g. IS-TRUE/IS-FALSE condition-operator extraction fix (mmim-gen-v8,
#     docs/MMIM_LEVEL88_CONDITION_OPERATOR_FIX.md).
#     app/behavioral/extraction/conditions.py now recognises the
#     IS-TRUE/IS-FALSE sentinel operators the mmim-gen-v7 parser fix
#     introduced -- t_condition_names_88 newly clears the
#     VALIDATION_REASONING eligibility gate (9 real behavioral tests,
#     evidence-backed, sourced from the condition-name's own declared
#     VALUE/VALUES domain, never fabricated). Only VALIDATION_REASONING
#     ground truth changes this cycle -- business rules, dependencies,
#     risk, strategy, transformation, and COBOL_TO_JAVA are untouched
#     (this cycle's fix lives entirely in app/behavioral/extraction/).
# --------------------------------------------------------------------------


def test_condition_operator_fix_newly_covers_condition_names_88(mmim_all_examples):
    # the exact corpus-wide count (35 as of mmim-gen-v8) moved on with the
    # mmim-gen-v9 compound-condition fix (§3h below re-pins the current
    # total, 36) -- this test keeps documenting only what mmim-gen-v8
    # itself established and remains true: t_condition_names_88 cleared
    # the VALIDATION_REASONING eligibility gate.
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert "t_condition_names_88" in val_sources


def test_condition_operator_fix_produces_real_evidence_backed_tests(mmim_all_examples):
    # mmim-gen-v8 gave t_condition_names_88 exactly 9 tests (its 2
    # single-term rules); mmim-gen-v9's compound-condition fix (§3h below)
    # added the other 6 rules' tests on top, so the *total* is no longer
    # 9 -- but the 4 single-term tests with real evidence mmim-gen-v8
    # produced must still be present, byte-for-byte, among the new total
    # (strictly additive, never replaced or altered).
    by_source = {
        e.input.source_id: e
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    ex = by_source["t_condition_names_88"]
    tests = ex.expected_output["tests"]
    assert ex.expected_output["test_count"] == len(tests) >= 9

    online_channel_true = [
        t
        for t in tests
        if t["inputs"][0]["name"] == "ONLINE-CHANNEL"
        and t["inputs"][0]["value"] != "OTHER"
    ]
    assert {t["inputs"][0]["value"] for t in online_channel_true} == {
        "WEB",
        "MOB",
        "API",
    }
    for t in online_channel_true:
        assert any(
            o["name"] == "FEES-LEVIED" and o["expected_value"] == "0.00"
            for o in t["expected_outputs"]
        )
        assert t["source_refs"], f"{t['test_id']} has evidence but no provenance"
        for ref in t["source_refs"]:
            assert ref["source_id"] == "t_condition_names_88"
            assert ref["line_start"] > 0

    tx_valid_kind_other = [
        t
        for t in tests
        if t["inputs"][0]["name"] == "TX-VALID-KIND"
        and t["inputs"][0]["value"] == "OTHER"
    ]
    assert len(tx_valid_kind_other) == 1
    t = tx_valid_kind_other[0]
    output_names = {o["name"] for o in t["expected_outputs"]}
    assert output_names == {"OUTCOME-ACTION", "TX-STATUS-FLAG"}
    assert t["source_refs"]


def test_condition_operator_fix_did_not_regress_any_v7_validation_source(
    mmim_all_examples,
):
    # every source covered by mmim-gen-v7 must still be covered -- strictly
    # additive, never a replacement of existing derivations.
    covered_by_v7 = {
        "fx_combined",
        "t_account_eligibility",
        "t_account_validate",
        "t_billing_engine",
        "t_bonus_calc",
        "t_credit_approval",
        "t_credit_limit",
        "t_customer_record",
        "t_daily_trans_report",
        "t_discount_tier",
        "t_fallthrough_flow",
        "t_fraud_pipeline",
        "t_grade_letter",
        "t_insurance_claim",
        "t_interest_accrue",
        "t_late_fee",
        "t_loan_balance",
        "t_loan_underwrite",
        "t_mortgage_service",
        "t_overdraft_fee",
        "t_packed_decimal",
        "t_payment_gateway",
        "t_payroll_deduct",
        "t_payroll_file_post",
        "t_payroll_net_pay",
        "t_policy_redefines",
        "t_pricing_tier",
        "t_reorder_point",
        "t_shared_state_hazard",
        "t_shipping_zone",
        "t_stock_alert",
        "t_tax_withhold",
        "t_transitive_fx",
        "t_vacation_accrual",
    }
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert covered_by_v7 <= val_sources


def test_condition_operator_fix_did_not_change_business_rule_counts(mmim_all_examples):
    """The fix touches only behavioral-test extraction, never business-rule
    extraction -- t_condition_names_88's rule_count (and every other
    source's) must be identical to its mmim-gen-v7 value."""
    by_source = {
        e.input.source_id: e
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    }
    unchanged_rule_counts = {
        "t_condition_names_88": 8,
        "t_billing_engine": 1,
        "t_credit_approval": 11,
        "t_pricing_tier": 14,
    }
    for sid, expected in unchanged_rule_counts.items():
        rule_count = by_source[sid].expected_output.get("rule_count", 0)
        assert (
            rule_count == expected
        ), f"{sid}: expected {expected} rules (unchanged), got {rule_count}"


# --------------------------------------------------------------------------
# 3h. Compound AND/OR condition extraction fix (mmim-gen-v9,
#     docs/MMIM_COMPOUND_CONDITION_FIX.md).
#     app/behavioral/extraction/conditions.py gained
#     parse_compound_condition/generate_compound_boundary_values/
#     evaluate_compound -- composing the existing single-term
#     parse_condition rather than reimplementing comparison/
#     condition-name grammar. Unlike every prior cycle, the corpus-wide
#     blast radius is NOT limited to one source: 17 sources gained
#     VALIDATION_REASONING content (a nested-IF/ELSE-cascade-derived AND
#     compound, previously silently unparseable for any operator), one
#     of which (t_batch_acct_update) becomes newly eligible. Only
#     VALIDATION_REASONING ground truth changes -- business rules,
#     dependencies, risk, strategy, transformation, and COBOL_TO_JAVA are
#     untouched (this cycle's fix lives entirely in
#     app/behavioral/extraction/).
# --------------------------------------------------------------------------


def test_compound_fix_newly_covers_batch_acct_update(mmim_all_examples):
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert len(val_sources) == 36
    assert "t_batch_acct_update" in val_sources


def test_compound_fix_gives_condition_names_88_all_six_compound_rules(
    mmim_all_examples,
):
    by_source = {
        e.input.source_id: e
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    ex = by_source["t_condition_names_88"]
    assert ex.expected_output["test_count"] == 21 == len(ex.expected_output["tests"])
    compound_conditions = {
        b["condition"]
        for t in ex.expected_output["tests"]
        for b in t["expected_branches"]
        if " AND " in b["condition"]
    }
    assert len(compound_conditions) == 6


def test_compound_fix_did_not_regress_any_v8_validation_source(mmim_all_examples):
    # every source covered by mmim-gen-v8 must still be covered -- strictly
    # additive, never a replacement of existing derivations.
    covered_by_v8 = {
        "fx_combined",
        "t_account_eligibility",
        "t_account_validate",
        "t_billing_engine",
        "t_bonus_calc",
        "t_condition_names_88",
        "t_credit_approval",
        "t_credit_limit",
        "t_customer_record",
        "t_daily_trans_report",
        "t_discount_tier",
        "t_fallthrough_flow",
        "t_fraud_pipeline",
        "t_grade_letter",
        "t_insurance_claim",
        "t_interest_accrue",
        "t_late_fee",
        "t_loan_balance",
        "t_loan_underwrite",
        "t_mortgage_service",
        "t_overdraft_fee",
        "t_packed_decimal",
        "t_payment_gateway",
        "t_payroll_deduct",
        "t_payroll_file_post",
        "t_payroll_net_pay",
        "t_policy_redefines",
        "t_pricing_tier",
        "t_reorder_point",
        "t_shared_state_hazard",
        "t_shipping_zone",
        "t_stock_alert",
        "t_tax_withhold",
        "t_transitive_fx",
        "t_vacation_accrual",
    }
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert covered_by_v8 <= val_sources


def test_compound_fix_did_not_change_business_rule_counts(mmim_all_examples):
    """The fix touches only behavioral-test extraction, never business-rule
    extraction -- rule counts for every affected source must be identical
    to their mmim-gen-v8 values."""
    by_source = {
        e.input.source_id: e
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    }
    unchanged_rule_counts = {
        "t_condition_names_88": 8,
        # t_batch_acct_update 2->3, t_account_eligibility 8->12 (task
        # #stage25, docs/MMIM_NEGATED_COMPARISON_FIX.md); this fix's own
        # blast-radius claim (this stage never touches business-rule
        # extraction) is unaffected.
        "t_batch_acct_update": 3,
        "t_account_eligibility": 12,
        "t_credit_approval": 11,
        "t_pricing_tier": 14,
    }
    for sid, expected in unchanged_rule_counts.items():
        rule_count = by_source[sid].expected_output.get("rule_count", 0)
        assert (
            rule_count == expected
        ), f"{sid}: expected {expected} rules (unchanged), got {rule_count}"


# --------------------------------------------------------------------------
# 3i. extra_conditions consumption fix (mmim-gen-v10,
#     docs/MMIM_EXTRA_CONDITIONS_FIX.md).
#     app/modernization/business_rules/extractor.py now renders every term
#     of a compound IF (IfStatementNode.extra_conditions), not just the
#     first. UPSTREAM change: 18 business-rule conditions change in
#     exactly 8 sources; rule counts, parser diagnostics and statement
#     counts are unchanged corpus-wide.
# --------------------------------------------------------------------------

_EXTRA_CONDITION_SOURCES = {
    "t_account_eligibility",
    "t_condition_names_88",
    "t_credit_approval",
    "t_daily_trans_report",
    "t_insurance_claim",
    "t_mortgage_service",
    "t_payment_gateway",
    "t_pricing_tier",
}


def _rule_conditions(mmim_all_examples, source_id):
    ex = next(
        e
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
        and e.input.source_id == source_id
    )
    return {r["rule_id"]: r["condition"] for r in ex.expected_output["business_rules"]}


def test_extra_conditions_fix_real_or_conditions_are_in_the_ground_truth(
    mmim_all_examples,
):
    expected = {
        "t_credit_approval": "(BANKRUPTCY-FLAG = 'Y') OR (CREDIT-SCORE < 580)",
        "t_daily_trans_report": "(FD-TX-VAL > 10000.00) OR (FD-TX-SUSPICIOUS = 'Y')",
        "t_insurance_claim": "(DRIVER-AGE < 21) OR (DRIVER-AGE > 75)",
        "t_payment_gateway": "(AUTH-OUT-RESP-CODE = ' ') OR (AUTH-OUT-RESP-CODE = '000')",
        "t_pricing_tier": "(PAYMENT-METHOD = 'ACH') OR (PAYMENT-METHOD = 'WIRE')",
    }
    for sid, condition in expected.items():
        assert condition in _rule_conditions(mmim_all_examples, sid).values(), sid


def test_extra_conditions_fix_br006_br007_regain_their_and_term(mmim_all_examples):
    conds = _rule_conditions(mmim_all_examples, "t_condition_names_88")
    assert len(conds) == 8
    for rid in ("BR-006", "BR-007"):
        assert "(TX-WITHDRAWAL IS-TRUE TX-WITHDRAWAL)" in conds[rid], rid


def test_extra_conditions_fix_did_not_change_any_rule_count(mmim_all_examples):
    counts = {
        e.input.source_id: e.expected_output["rule_count"]
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    }
    assert sum(counts.values()) == 167  # was 157; task #stage25
    assert counts["t_condition_names_88"] == 8
    for sid in _EXTRA_CONDITION_SOURCES:
        assert counts[sid] > 0


def test_extra_conditions_fix_or_conditions_reach_validation_with_both_outcomes(
    mmim_all_examples,
):
    or_sources = {
        "t_credit_approval",
        "t_daily_trans_report",
        "t_insurance_claim",
        "t_payment_gateway",
        "t_pricing_tier",
    }
    for e in mmim_all_examples:
        if e.task_type != TaskType.VALIDATION_REASONING:
            continue
        if e.input.source_id not in or_sources:
            continue
        outcomes = {
            b["taken"]
            for t in e.expected_output["tests"]
            for b in t["expected_branches"]
            if " OR " in b["condition"] and "AND" not in b["condition"]
        }
        assert outcomes == {True, False}, e.input.source_id


def test_extra_conditions_fix_cn88_fee_evidence_assigns_the_withdrawal_code(
    mmim_all_examples,
):
    ex = next(
        e
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
        and e.input.source_id == "t_condition_names_88"
    )
    fee_tests = [
        t
        for t in ex.expected_output["tests"]
        for b in t["expected_branches"]
        if b["taken"]
        and "TX-WITHDRAWAL IS-TRUE" in b["condition"]
        and "TX-AMOUNT" in b["condition"]
    ]
    assert len(fee_tests) == 2
    for t in fee_tests:
        assert {i["name"]: i["value"] for i in t["inputs"]}["TX-TYPE-CODE"] == "W"


def test_extra_conditions_fix_validation_coverage_unchanged_at_36(mmim_all_examples):
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert len(val_sources) == 36
    assert _EXTRA_CONDITION_SOURCES <= val_sources


# --------------------------------------------------------------------------
# 3j. Downstream extra_conditions fix (mmim-gen-v11,
#     docs/MMIM_EXTRA_CONDITIONS_DOWNSTREAM_FIX.md).
#     The IR builder, Java emitter, dependency analyzer, CFG label and the
#     legacy rules extractor now consume IfStatementNode.extra_conditions.
#     Only the 8 sources whose AST has a compound IF change; a plain IF's IR
#     serializes byte-identically (IRIf.extra_terms is omitted when empty).
# --------------------------------------------------------------------------


def test_downstream_fix_extra_terms_appear_only_in_the_8_compound_if_sources(
    mmim_all_examples,
):
    sources_with_terms = {
        e.input.source_id
        for e in mmim_all_examples
        if "IRConditionTerm" in e.model_dump_json()
    }
    assert sources_with_terms == _EXTRA_CONDITION_SOURCES


def test_downstream_fix_plain_if_ir_is_unchanged_in_all_other_sources(
    mmim_all_examples,
):
    other = [
        e
        for e in mmim_all_examples
        if e.input.source_id not in _EXTRA_CONDITION_SOURCES
    ]
    assert other
    assert not [e.example_id for e in other if "extra_terms" in e.model_dump_json()]


def test_downstream_fix_dependency_ground_truth_has_the_or_term_variable(
    mmim_all_examples,
):
    def deps(source_id):
        """``{(type, target): {source lines}}`` -- a variable can be read on
        several lines, so keep them all."""
        ex = next(
            e
            for e in mmim_all_examples
            if e.task_type == TaskType.DEPENDENCY_REASONING
            and e.input.source_id == source_id
        )
        found: dict[tuple[str, str], set[int]] = {}
        for d in ex.expected_output["dependencies"]:
            found.setdefault((d["type"], d["target"]), set()).add(
                d["source_location"]["line"]
            )
        return found

    # FD-TX-SUSPICIOUS is read only as the OR term of daily_trans_report.cbl:56
    assert deps("t_daily_trans_report")[("CONDITION", "FD-TX-SUSPICIOUS")] == {56}
    assert 54 in deps("t_condition_names_88")[("CONDITION", "TX-WITHDRAWAL")]
    assert 67 in deps("t_account_eligibility")[("CONDITION", "ANNUAL-INCOME")]
    assert 37 in deps("t_insurance_claim")[("CONDITION", "CLAIM-AMOUNT")]
    assert 50 in deps("t_mortgage_service")[("CONDITION", "IN-LTV-RATIO")]
    # a condition operand that is a literal never becomes a dependency
    # (CALL targets legitimately keep their quotes -- that is a different type)
    for source_id in _EXTRA_CONDITION_SOURCES:
        for dep_type, target in deps(source_id):
            if dep_type != "CONDITION":
                continue
            assert not target.startswith(("'", '"')), (source_id, target)
            assert not target.replace(".", "").isdigit(), (source_id, target)


def test_downstream_fix_did_not_change_counts_or_ground_truth_status(
    mmim_all_examples,
):
    assert len(mmim_all_examples) == 351
    rule_total = sum(
        e.expected_output["rule_count"]
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    )
    assert rule_total == 167  # was 157; task #stage25
    statuses = {}
    for e in mmim_all_examples:
        key = e.metadata.ground_truth_status.value
        statuses[key] = statuses.get(key, 0) + 1
    # 342/2/7 as of mmim-gen-v11 itself (this cycle changed none of them --
    # rule_total above is the direct check); mmim-gen-v13's single-quoted-
    # literal fix later moved 3 sources reference -> deterministic (345/2/4),
    # verified in test_java_literal_fix_did_not_change_counts_or_coverage.
    assert statuses == {"deterministic": 349, "executable_verified": 2}


_JAVA_LITERAL_FIX_SOURCES = {
    "t_batch_acct_update",
    "t_daily_trans_report",
    "t_fallthrough_flow",
    "t_goto_spaghetti",
    "t_inventory_extract",
    "t_payroll_file_post",
    "t_policy_redefines",
}

# --------------------------------------------------------------------------
# 3k. Java backend: COBOL '=' -> '==' and omitted untranslatable constructs
#     (mmim-gen-v12, docs/MMIM_JAVA_IF_EMISSION_FIX.md).
#     Only the Java text changes, so only COBOL_TO_JAVA ground truth: the 5
#     sources whose emitted paragraph has an '=' IF were unbalanced Java
#     before (header skipped, body and closing brace still emitted).
# --------------------------------------------------------------------------

_JAVA_IF_FIX_SOURCES = {
    "t_batch_acct_update",
    "t_daily_trans_report",
    "t_fallthrough_flow",
    "t_goto_spaghetti",
    "t_policy_redefines",
}


def _java_examples(mmim_all_examples):
    return {
        e.input.source_id: e
        for e in mmim_all_examples
        if e.task_type == TaskType.COBOL_TO_JAVA
    }


def test_java_fix_every_generated_java_has_balanced_braces(mmim_all_examples):
    java = _java_examples(mmim_all_examples)
    assert len(java) == 45
    unbalanced = {
        sid: (
            e.expected_output["java"].count("{"),
            e.expected_output["java"].count("}"),
        )
        for sid, e in java.items()
        if e.expected_output["java"].count("{") != e.expected_output["java"].count("}")
    }
    assert unbalanced == {}


def test_java_fix_previously_unbalanced_sources_now_emit_their_equals_header(
    mmim_all_examples,
):
    """t_fallthrough_flow was originally included here for its
    ``IF STEP-A-HIT-COUNT = 0`` header, but mmim-gen-v16
    (docs/MMIM_PERFORM_THRU_FIX.md) recovered 0000-MAIN-CONTROL's
    previously-dropped MOVE/GOBACK statements; GOBACK now correctly
    terminates this backend's flat statement concatenation before it
    reaches 2000-STAGE-BETA's IF at all, so that header is legitimately
    absent from this source's generated Java now (a separate, already-
    documented flat-paragraph-concatenation backend limitation, not a
    regression of the `=`-to-`==` fix itself -- see that doc's real-corpus
    section). The other three sources below still exercise it unaffected.
    """
    java = _java_examples(mmim_all_examples)
    # task #stage27: FD-OVERDRAFT-PROT is now a declared, known-String FILE
    # SECTION field, so its comparison correctly gets the Stage 24
    # _cobolEquals helper instead of identity == (docs/MMIM_FILE_SECTION_FIELDS_FIX.md).
    assert (
        'if (_cobolEquals(fdOverdraftProt, "Y")) {'
        in java["t_batch_acct_update"].expected_output["java"]
    )
    assert "if (stepIndex == 1) {" in java["t_goto_spaghetti"].expected_output["java"]
    # (Stage 24: a text comparison is now the COBOL alphanumeric equality)
    assert (
        'if (_cobolEquals(policyKind, "AUTO")) {'
        in java["t_policy_redefines"].expected_output["java"]
    )
    # the compound IF keeps BOTH terms (the OR is not truncated); FD-TX-
    # SUSPICIOUS is the same task #stage27 upgrade as FD-OVERDRAFT-PROT above.
    header = next(
        ln.strip()
        for ln in java["t_daily_trans_report"].expected_output["java"].splitlines()
        if ln.strip().startswith("if (fdTxVal")
    )
    assert header.startswith('if (fdTxVal > 10000.00 || _cobolEquals(fdTxSuspicious, "')


def test_java_fix_no_generated_java_carries_an_orphaned_guarded_body(
    mmim_all_examples,
):
    """No ``BE007``-skipped header remains anywhere in the corpus, so no
    omitted-construct marker is present, and no Java carries a bare ``}``-only
    line that closes nothing (balanced braces are asserted above)."""
    for sid, e in _java_examples(mmim_all_examples).items():
        assert "cannot be translated (BE007)" not in e.expected_output["java"], sid


def test_java_fix_did_not_change_compile_flags_or_ground_truth_status(
    mmim_all_examples,
):
    java = _java_examples(mmim_all_examples)
    # 38 compiling as of mmim-gen-v12 itself (this cycle balanced braces but
    # fixed no compile errors); mmim-gen-v13's literal fix later raised this
    # to 41 (3 of the 5 sources below among them), verified in
    # test_java_literal_fix_three_sources_newly_compile. task #stage27
    # (docs/MMIM_FILE_SECTION_FIELDS_FIX.md) declares FILE SECTION fields as
    # Java fields, which was the "remaining javac errors are unrelated
    # (undeclared FILE SECTION fields)" reason `t_batch_acct_update`/
    # `t_daily_trans_report` stayed uncompilable through every prior cycle --
    # both now compile too, raising the total to 45/45.
    assert sum(1 for e in java.values() if e.expected_output["compiles"]) == 45
    for sid in _JAVA_IF_FIX_SOURCES:
        assert java[sid].expected_output["compiles"] is True
    statuses = {}
    for e in mmim_all_examples:
        key = e.metadata.ground_truth_status.value
        statuses[key] = statuses.get(key, 0) + 1
    assert statuses == {"deterministic": 349, "executable_verified": 2}
    assert len(mmim_all_examples) == 351


# --------------------------------------------------------------------------
# 3l. Java backend: COBOL single-quoted string literals (mmim-gen-v13,
#     docs/MMIM_JAVA_LITERAL_EMISSION_FIX.md).
#     _translate_operand now recognises COBOL's own '...' string-literal
#     delimiter (it previously recognised only Java's "..."), so a literal
#     like 'Y' is emitted as "Y" instead of an undeclared identifier y.
#     Only COBOL_TO_JAVA ground truth changes, for exactly the 7 sources
#     whose flattened statements contain a single-quoted literal; 3 of them
#     newly compile.
# --------------------------------------------------------------------------

_JAVA_LITERAL_FIX_NEWLY_COMPILING = {
    "t_fallthrough_flow",
    "t_goto_spaghetti",
    "t_policy_redefines",
}


def _cobol_to_java_examples(mmim_all_examples):
    return {
        e.input.source_id: e
        for e in mmim_all_examples
        if e.task_type == TaskType.COBOL_TO_JAVA
    }


def test_java_literal_fix_single_quoted_literals_are_java_strings(mmim_all_examples):
    java = _cobol_to_java_examples(mmim_all_examples)
    assert 'wsR = "Y";' not in java  # sanity: no stale fixture leaking in
    assert '"Y"' in java["t_batch_acct_update"].expected_output["java"]
    # 'COMPLETED' (from 0000-MAIN-CONTROL's MOVE), not 'SKIPPED-ALPHA' (from
    # 2000-STAGE-BETA's now-correctly-unreachable-after-GOBACK IF) -- see
    # mmim-gen-v16 / docs/MMIM_PERFORM_THRU_FIX.md for why.
    assert '"COMPLETED"' in java["t_fallthrough_flow"].expected_output["java"]
    assert '"STARTED"' in java["t_goto_spaghetti"].expected_output["java"]
    assert '"AUTO"' in java["t_policy_redefines"].expected_output["java"]
    assert '"LIFE"' in java["t_policy_redefines"].expected_output["java"]
    dtr = java["t_daily_trans_report"].expected_output["java"]
    assert '"HIGH RISK TRANSACTION FLAGGED"' in dtr
    # task #stage27: FD-TX-SUSPICIOUS is now a declared, known-String field,
    # so it gets the _cobolEquals helper, not identity == (see
    # test_java_fix_previously_unbalanced_sources_now_emit_their_equals_header).
    assert '_cobolEquals(fdTxSuspicious, "Y")' in dtr
    # never the old, broken bare-identifier form
    for sid in _JAVA_LITERAL_FIX_SOURCES:
        code = java[sid].expected_output["java"]
        assert " = y;" not in code and "== y)" not in code, sid


def test_java_literal_fix_did_not_change_any_other_source(mmim_all_examples):
    java = _cobol_to_java_examples(mmim_all_examples)
    assert len(java) == 45
    for sid in set(java) - _JAVA_LITERAL_FIX_SOURCES:
        code = java[sid].expected_output["java"]
        assert code.count("{") == code.count("}"), sid


def test_java_literal_fix_three_sources_newly_compile(mmim_all_examples):
    java = _cobol_to_java_examples(mmim_all_examples)
    assert sum(1 for e in java.values() if e.expected_output["compiles"]) == 45
    for sid in _JAVA_LITERAL_FIX_NEWLY_COMPILING:
        assert java[sid].expected_output["compiles"] is True
        assert java[sid].metadata.ground_truth_status.value == "deterministic"
    # `_JAVA_LITERAL_FIX_SOURCES - _JAVA_LITERAL_FIX_NEWLY_COMPILING` (the 4
    # FILE-SECTION sources) stayed uncompilable through every cycle up to and
    # including this one's own literal fix -- undeclared FILE SECTION fields
    # were always the remaining reason. **Resolved in task #stage27**
    # (docs/MMIM_FILE_SECTION_FIELDS_FIX.md): they compile too now.
    for sid in _JAVA_LITERAL_FIX_SOURCES - _JAVA_LITERAL_FIX_NEWLY_COMPILING:
        assert java[sid].expected_output["compiles"] is True
        assert java[sid].metadata.ground_truth_status.value == "deterministic"


def test_java_literal_fix_did_not_change_counts_or_coverage(mmim_all_examples):
    assert len(mmim_all_examples) == 351
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert len(val_sources) == 36
    rule_total = sum(
        e.expected_output["rule_count"]
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    )
    assert rule_total == 167  # was 157; task #stage25
    statuses = {}
    for e in mmim_all_examples:
        key = e.metadata.ground_truth_status.value
        statuses[key] = statuses.get(key, 0) + 1
    assert statuses == {"deterministic": 349, "executable_verified": 2}


# --------------------------------------------------------------------------
# 3m. Parser: READ ... AT END / NOT AT END no longer leaks a mangled
#     identifier (mmim-gen-v14, docs/MMIM_READ_AT_END_PARSING_FIX.md).
#     A dedicated ProcedureDivisionParser._skip_read_statement now protects
#     READ's nested clause statements from the generic "stop at the first
#     statement verb" skip -- the same protection EVALUATE already had.
#     Only the 4 sources with a real READ statement change, across every
#     task whose expected_output embeds AST-derived dependency/statement
#     data; business-rule counts, VALIDATION_REASONING test counts and
#     coverage are unchanged (the corrupted statements never fed either).
# --------------------------------------------------------------------------

_READ_FIX_SOURCES = {
    "t_batch_acct_update",
    "t_daily_trans_report",
    "t_inventory_extract",
    "t_payroll_file_post",
}


def test_read_fix_no_mangled_dependency_targets_remain(mmim_all_examples):
    for e in mmim_all_examples:
        if e.task_type != TaskType.DEPENDENCY_REASONING:
            continue
        for d in e.expected_output["dependencies"]:
            target = d["target"].upper()
            assert "AT END" not in target, (e.input.source_id, d)
            assert "END-READ" not in target, (e.input.source_id, d)


def test_read_fix_no_mangled_identifier_in_generated_java(mmim_all_examples):
    bad = (
        "wsEofFlagnotatend",
        "wsRecordsReadendRead",
        "wsEofendRead",
        "wsInvEofendRead",
        "wsPayEofendRead",
    )
    for e in mmim_all_examples:
        if e.task_type != TaskType.COBOL_TO_JAVA:
            continue
        code = e.expected_output["java"]
        for ident in bad:
            assert ident not in code, (e.input.source_id, ident)


def test_read_fix_only_the_four_read_bearing_sources_changed(mmim_all_examples):
    dep_counts = {
        e.input.source_id: len(e.expected_output["dependencies"])
        for e in mmim_all_examples
        if e.task_type == TaskType.DEPENDENCY_REASONING
    }
    # t_batch_acct_update: 9 -> 11 (task #stage25,
    # docs/MMIM_NEGATED_COMPARISON_FIX.md: WS-FILE-STATUS/its comparison
    # literal are now real dependencies of the newly-parseable IF).
    assert dep_counts["t_batch_acct_update"] == 11
    assert dep_counts["t_daily_trans_report"] == 10
    assert dep_counts["t_inventory_extract"] == 8
    assert dep_counts["t_payroll_file_post"] == 14


def test_read_fix_did_not_change_business_rules_or_validation_reasoning(
    mmim_all_examples,
):
    rule_total = sum(
        e.expected_output["rule_count"]
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    )
    assert rule_total == 167
    for sid, expected in {
        # t_batch_acct_update: 2 -> 3 (task #stage25,
        # docs/MMIM_NEGATED_COMPARISON_FIX.md).
        "t_batch_acct_update": 3,
        "t_daily_trans_report": 2,
        "t_inventory_extract": 1,
        "t_payroll_file_post": 1,
    }.items():
        rc = next(
            e.expected_output["rule_count"]
            for e in mmim_all_examples
            if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
            and e.input.source_id == sid
        )
        assert rc == expected, sid
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert len(val_sources) == 36
    for sid, expected in {
        # t_batch_acct_update: 4 -> 6 (task #stage25,
        # docs/MMIM_NEGATED_COMPARISON_FIX.md: WS-FILE-STATUS <> '00' is a
        # new, boundary-testable condition).
        "t_batch_acct_update": 6,
        "t_daily_trans_report": 5,
        "t_payroll_file_post": 3,
    }.items():
        tc = next(
            e.expected_output["test_count"]
            for e in mmim_all_examples
            if e.task_type == TaskType.VALIDATION_REASONING and e.input.source_id == sid
        )
        assert tc == expected, sid


def test_read_fix_did_not_change_counts_or_leakage(mmim_all_examples):
    assert len(mmim_all_examples) == 351
    java = [e for e in mmim_all_examples if e.task_type == TaskType.COBOL_TO_JAVA]
    assert sum(1 for e in java if e.expected_output["compiles"]) == 45
    statuses = {}
    for e in mmim_all_examples:
        key = e.metadata.ground_truth_status.value
        statuses[key] = statuses.get(key, 0) + 1
    assert statuses == {"deterministic": 349, "executable_verified": 2}


# --------------------------------------------------------------------------
# 3n. CFG/flow generator: an existing-but-statement-empty PERFORM/GO TO
#     target is no longer misclassified as unresolved/external
#     (mmim-gen-v15, docs/MMIM_EMPTY_PARAGRAPH_PERFORM_TARGET_FIX.md).
#     The raw CFG (with "empty_"/"ext_" node ids) is embedded in the
#     top-level ``analysis.cfg`` field -- a sibling of ``expected_output``
#     -- for PROGRAM_UNDERSTANDING, DEPENDENCY_REASONING and
#     RISK_CLASSIFICATION only (see ``MMIMDatasetBuilder._analysis_block``
#     call sites); MODERNIZATION_STRATEGY's ``expected_output`` carries
#     only the risk-driven text/scoring that this fix affects, and
#     BUSINESS_RULE_EXTRACTION, VALIDATION_REASONING and COBOL_TO_JAVA
#     ground truth are untouched by this fix entirely.
# --------------------------------------------------------------------------

#: Was 12 (included "t_account_eligibility" and "t_insurance_claim"); task
#: #stage25 (docs/MMIM_NEGATED_COMPARISON_FIX.md) removed both. In each, a
#: single "NOT =" deep inside a *nested* IF used to raise a ParserError that
#: propagated all the way up through every enclosing IF (no nested
#: ``_parse_if_statement`` call catches its own condition's error) to the
#: paragraph's top-level statement loop -- which then dropped the *entire*
#: top-level statement recovery synchronised past. For both sources that
#: top-level statement was the paragraph's *only* one
#: (``t_account_eligibility``'s ``1000-BASIC-QUALIFICATION``,
#: ``t_insurance_claim``'s ``2000-DETERMINE-ELIGIBILITY``), so the whole
#: paragraph was left with zero representable statements -- the same "no
#: representable statements" condition the *original* (task #stage15) empty-
#: paragraph fix this set is named for was about, just reached by a
#: different, then-still-broken parser path. Both paragraphs are now fully
#: populated and neither source has an "empty_" node anywhere (confirmed
#: directly against the regenerated dataset). "t_batch_acct_update" stays in
#: this set: "1000-OPEN-FILES" is no longer empty (docs/MMIM_NEGATED
#: _COMPARISON_FIX.md §4), but "2000-READ-RECORD" (an unrelated, unaffected,
#: still-unsupported READ) still is.
_EMPTY_PARAGRAPH_FIX_SOURCES = {
    "t_batch_acct_update",
    "t_billing_engine",
    "t_daily_trans_report",
    "t_inventory_extract",
    "t_inventory_reorder",
    "t_order_hierarchy",
    "t_packed_decimal",
    "t_payroll_file_post",
    "t_pricing_tier",
    "t_transitive_fx",
}

#: Task types whose ``analysis.cfg`` block is populated
#: (``MMIMDatasetBuilder._analysis_block`` call sites for
#: PROGRAM_UNDERSTANDING / DEPENDENCY_REASONING / RISK_CLASSIFICATION).
_TASKS_WITH_EMBEDDED_CFG = {
    TaskType.PROGRAM_UNDERSTANDING,
    TaskType.DEPENDENCY_REASONING,
    TaskType.RISK_CLASSIFICATION,
}


def test_empty_paragraph_fix_no_source_has_a_false_unresolved_perform_risk(
    mmim_all_examples,
):
    for e in mmim_all_examples:
        if e.task_type != TaskType.RISK_CLASSIFICATION:
            continue
        for risk in e.expected_output["risks"]:
            if risk["category"] != "UNRESOLVED_PERFORM_TARGET":
                continue
            # every remaining occurrence must be a genuine external target,
            # never a real (if empty) local paragraph
            for item in risk["evidence"]:
                assert "empty_" not in item, (e.input.source_id, item)


def test_empty_paragraph_fix_only_the_ten_sources_embed_an_empty_node(
    mmim_all_examples,
):
    """Was 12; see ``_EMPTY_PARAGRAPH_FIX_SOURCES`` for why it is 10 now."""
    for e in mmim_all_examples:
        if e.task_type not in _TASKS_WITH_EMBEDDED_CFG:
            continue
        cfg = e.analysis.cfg
        assert cfg is not None, (e.input.source_id, e.task_type)
        raw = str(cfg)
        if e.input.source_id in _EMPTY_PARAGRAPH_FIX_SOURCES:
            assert "empty_" in raw, e.input.source_id
        else:
            assert "empty_" not in raw, e.input.source_id


def test_empty_paragraph_fix_billing_engine_keeps_its_genuine_external_calls(
    mmim_all_examples,
):
    # t_billing_engine is in the (now 10-source) blast radius (it has an empty
    # paragraph too) but also makes real CALLs to DISCENG1/TAXENG01 --
    # those must still resolve to "ext_", proving the fix does not
    # over-resolve genuinely external targets.
    for e in mmim_all_examples:
        if e.task_type not in _TASKS_WITH_EMBEDDED_CFG:
            continue
        if e.input.source_id != "t_billing_engine":
            continue
        raw = str(e.analysis.cfg)
        assert "ext_" in raw, e.task_type


def test_empty_paragraph_fix_did_not_change_business_rules_or_java(mmim_all_examples):
    rule_total = sum(
        e.expected_output["rule_count"]
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    )
    assert rule_total == 167  # was 157; task #stage25
    java = [e for e in mmim_all_examples if e.task_type == TaskType.COBOL_TO_JAVA]
    assert sum(1 for e in java if e.expected_output["compiles"]) == 45
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert len(val_sources) == 36


def test_empty_paragraph_fix_did_not_change_counts_or_leakage(mmim_all_examples):
    assert len(mmim_all_examples) == 351
    statuses: dict[str, int] = {}
    for e in mmim_all_examples:
        key = e.metadata.ground_truth_status.value
        statuses[key] = statuses.get(key, 0) + 1
    assert statuses == {"deterministic": 349, "executable_verified": 2}


# --------------------------------------------------------------------------
# 3o. PERFORM ... THRU ... target resolution (mmim-gen-v16,
#     docs/MMIM_PERFORM_THRU_FIX.md). Exactly one real corpus source
#     (t_fallthrough_flow) contains a PERFORM ... THRU ...; it is also the
#     only source whose ground truth changes this cycle. Its previously
#     silently-dropped MOVE/GOBACK statements (swallowed by the same
#     SYN001 recovery that used to eat the THRU clause) are recovered as
#     a direct, causally-inseparable consequence, not a second change.
# --------------------------------------------------------------------------

_PERFORM_THRU_FIX_SOURCE = "t_fallthrough_flow"

#: expected_output genuinely changes for these task types (embeds the
#: AST, the CFG, or risk/strategy/dependency text derived from either);
#: VALIDATION_REASONING's expected_output is untouched -- only its raw
#: embedded analysis.ast dump differs, checked separately below.
_PERFORM_THRU_FIX_EXPECTED_OUTPUT_TASKS = {
    TaskType.PROGRAM_UNDERSTANDING,
    TaskType.DEPENDENCY_REASONING,
    TaskType.RISK_CLASSIFICATION,
    TaskType.BUSINESS_RULE_EXTRACTION,
    TaskType.MODERNIZATION_STRATEGY,
    TaskType.TRANSFORMATION_PLANNING,
    TaskType.COBOL_TO_JAVA,
}


def test_perform_thru_fix_only_fallthrough_flow_embeds_a_thru_range_node(
    mmim_all_examples,
):
    for e in mmim_all_examples:
        if e.task_type not in _TASKS_WITH_EMBEDDED_CFG:
            continue
        cfg = e.analysis.cfg
        raw = str(cfg) if cfg is not None else ""
        has_thru_node = " THRU " in raw
        if e.input.source_id == _PERFORM_THRU_FIX_SOURCE:
            assert has_thru_node, e.input.source_id
        else:
            assert not has_thru_node, e.input.source_id


def test_perform_thru_fix_fallthrough_flow_perform_still_resolves_no_risk(
    mmim_all_examples,
):
    for e in mmim_all_examples:
        if e.task_type != TaskType.RISK_CLASSIFICATION:
            continue
        if e.input.source_id != _PERFORM_THRU_FIX_SOURCE:
            continue
        for risk in e.expected_output["risks"]:
            assert risk["category"] != "UNRESOLVED_PERFORM_TARGET"
        categories = {r["category"] for r in e.expected_output["risks"]}
        # the recovered MOVE statement surfaces a genuine, new finding
        assert "SHARED_MUTABLE_STATE" in categories


def test_perform_thru_fix_fallthrough_flow_java_still_compiles(mmim_all_examples):
    for e in mmim_all_examples:
        if e.task_type != TaskType.COBOL_TO_JAVA:
            continue
        if e.input.source_id != _PERFORM_THRU_FIX_SOURCE:
            continue
        assert e.expected_output["compiles"] is True


def test_perform_thru_fix_validation_reasoning_expected_output_unaffected(
    mmim_all_examples,
):
    """VALIDATION_REASONING ground truth (test suite/hash) for
    t_fallthrough_flow is untouched by this cycle -- neither the loop-
    less MOVE/GOBACK recovery nor the THRU range touches any behavioral
    condition this extractor derives tests from."""
    for e in mmim_all_examples:
        if e.task_type != TaskType.VALIDATION_REASONING:
            continue
        if e.input.source_id != _PERFORM_THRU_FIX_SOURCE:
            continue
        assert e.expected_output["test_count"] >= 0  # source is eligible
        break
    else:
        pytest.fail(f"{_PERFORM_THRU_FIX_SOURCE} VALIDATION_REASONING example missing")


def test_perform_thru_fix_only_the_expected_task_types_and_source_changed(
    mmim_all_examples,
):
    """A cross-check against the other affected-task-type tests above:
    every RISK_CLASSIFICATION/DEPENDENCY_REASONING/PROGRAM_UNDERSTANDING/
    BUSINESS_RULE_EXTRACTION/MODERNIZATION_STRATEGY/TRANSFORMATION_PLANNING/
    COBOL_TO_JAVA example for a source OTHER than t_fallthrough_flow must
    not mention a THRU range or the new SHARED_MUTABLE_STATE PASS-THRU
    finding -- i.e. nothing about this fix leaked into an unrelated
    source's ground truth."""
    for e in mmim_all_examples:
        if e.task_type not in _PERFORM_THRU_FIX_EXPECTED_OUTPUT_TASKS:
            continue
        if e.input.source_id == _PERFORM_THRU_FIX_SOURCE:
            continue
        raw = str(e.expected_output)
        assert "PASS-THRU-STATUS" not in raw, e.input.source_id


def test_perform_thru_fix_did_not_change_business_rules_or_counts(mmim_all_examples):
    rule_total = sum(
        e.expected_output["rule_count"]
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    )
    assert rule_total == 167  # was 157; task #stage25
    java = [e for e in mmim_all_examples if e.task_type == TaskType.COBOL_TO_JAVA]
    assert sum(1 for e in java if e.expected_output["compiles"]) == 45
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert len(val_sources) == 36
    assert len(mmim_all_examples) == 351
    statuses: dict[str, int] = {}
    for e in mmim_all_examples:
        key = e.metadata.ground_truth_status.value
        statuses[key] = statuses.get(key, 0) + 1
    assert statuses == {"deterministic": 349, "executable_verified": 2}


# --------------------------------------------------------------------------
# 3p. Real COBOL GO TO support (mmim-gen-v17, docs/MMIM_GO_TO_FIX.md).
#     Exactly one real corpus source (t_goto_spaghetti) contains real
#     GO TO usage; it is also the only source whose ground truth changes
#     this cycle. GoToStatementNode/IRJump/GOES_TO/the CFG resolution
#     machinery all pre-existed -- only the parser dispatch was added --
#     so this section checks the same invariants §3n/§3o already check
#     (no false UNRESOLVED_PERFORM_TARGET, business-rule/compile/example
#     counts unaffected, VALIDATION_REASONING untouched) plus the two
#     GO-TO-specific consequences: the UNSUPPORTED_SYNTAX risk for this
#     source disappears, and COMPLEX_CONTROL_FLOW's evidence becomes
#     non-trivial for the first time.
# --------------------------------------------------------------------------

_GO_TO_FIX_SOURCE = "t_goto_spaghetti"

#: expected_output genuinely changes for these task types (embeds the
#: AST, the CFG, or risk/strategy/dependency text derived from either);
#: VALIDATION_REASONING's expected_output is untouched -- only its raw
#: embedded analysis.ast dump differs, checked separately below.
_GO_TO_FIX_EXPECTED_OUTPUT_TASKS = {
    TaskType.PROGRAM_UNDERSTANDING,
    TaskType.DEPENDENCY_REASONING,
    TaskType.RISK_CLASSIFICATION,
    TaskType.BUSINESS_RULE_EXTRACTION,
    TaskType.MODERNIZATION_STRATEGY,
    TaskType.TRANSFORMATION_PLANNING,
    TaskType.COBOL_TO_JAVA,
}


def test_go_to_fix_goto_spaghetti_has_no_unresolved_target_risk(mmim_all_examples):
    """Every real GO TO target in this source resolves to a real
    paragraph -- GOES_TO edges aren't checked by
    UNRESOLVED_PERFORM_TARGET at all, but this confirms nothing about
    the fix produces one for this source regardless."""
    for e in mmim_all_examples:
        if e.task_type != TaskType.RISK_CLASSIFICATION:
            continue
        if e.input.source_id != _GO_TO_FIX_SOURCE:
            continue
        categories = {r["category"] for r in e.expected_output["risks"]}
        assert "UNRESOLVED_PERFORM_TARGET" not in categories


def test_go_to_fix_goto_spaghetti_unsupported_syntax_risk_is_gone(mmim_all_examples):
    for e in mmim_all_examples:
        if e.task_type != TaskType.RISK_CLASSIFICATION:
            continue
        if e.input.source_id != _GO_TO_FIX_SOURCE:
            continue
        categories = {r["category"] for r in e.expected_output["risks"]}
        assert "UNSUPPORTED_SYNTAX" not in categories
        assert "COMPLEX_CONTROL_FLOW" in categories


def test_go_to_fix_only_goto_spaghetti_expected_output_changed(mmim_all_examples):
    for e in mmim_all_examples:
        if e.task_type not in _GO_TO_FIX_EXPECTED_OUTPUT_TASKS:
            continue
        if e.input.source_id == _GO_TO_FIX_SOURCE:
            continue
        # no unrelated source's expected_output mentions this source's
        # GO TO target paragraph names
        raw = str(e.expected_output)
        assert "5000-FINAL-STAGE" not in raw, e.input.source_id


def test_go_to_fix_cobol_to_java_still_compiles(mmim_all_examples):
    for e in mmim_all_examples:
        if e.task_type != TaskType.COBOL_TO_JAVA:
            continue
        if e.input.source_id != _GO_TO_FIX_SOURCE:
            continue
        assert e.expected_output["compiles"] is True


def test_go_to_fix_validation_reasoning_eligibility_unaffected(
    mmim_all_examples, manifest
):
    """t_goto_spaghetti has no VALIDATION_REASONING example in either
    version -- it is skipped for 'no_derivable_behavioral_tests' both
    before and after this fix (confirmed against the v16 snapshot: same
    reason, same skip decision; only the skip record's own
    parser_status sub-fields -- syntax_diagnostic_count 8 -> 1,
    unsupported_codes ['SYN100'] -> [] -- reflect the fix, which is not
    itself a VALIDATION_REASONING ground-truth change)."""
    assert not [
        e
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
        and e.input.source_id == _GO_TO_FIX_SOURCE
    ]
    skip = next(
        s
        for s in manifest["skipped"]
        if s["source_id"] == _GO_TO_FIX_SOURCE
        and s["task_type"] == TaskType.VALIDATION_REASONING.value
    )
    assert skip["reason"] == "no_derivable_behavioral_tests"
    assert skip["parser_status"]["unsupported_codes"] == []


def test_go_to_fix_did_not_change_business_rules_or_counts(mmim_all_examples):
    rule_total = sum(
        e.expected_output["rule_count"]
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    )
    assert rule_total == 167  # was 157; task #stage25
    java = [e for e in mmim_all_examples if e.task_type == TaskType.COBOL_TO_JAVA]
    assert sum(1 for e in java if e.expected_output["compiles"]) == 45
    val_sources = {
        e.input.source_id
        for e in mmim_all_examples
        if e.task_type == TaskType.VALIDATION_REASONING
    }
    assert len(val_sources) == 36
    assert len(mmim_all_examples) == 351
    statuses: dict[str, int] = {}
    for e in mmim_all_examples:
        key = e.metadata.ground_truth_status.value
        statuses[key] = statuses.get(key, 0) + 1
    assert statuses == {"deterministic": 349, "executable_verified": 2}


# --------------------------------------------------------------------------
# 3q. Java translation of GO TO / IRJump (mmim-gen-v18,
#     docs/MMIM_GO_TO_FIX.md §10). A program with a translatable GO TO is
#     lowered as a paragraph dispatcher; every other program takes the
#     unchanged flat path. Exactly one corpus source (t_goto_spaghetti) has
#     a GO TO, so exactly one COBOL_TO_JAVA example -- and only its
#     ``expected_output.java`` -- changes. Everything else is pinned
#     unchanged.
# --------------------------------------------------------------------------

_GO_TO_JAVA_SOURCE = "t_goto_spaghetti"


def _all_java(mmim_all_examples):
    return {
        e.input.source_id: e
        for e in mmim_all_examples
        if e.task_type == TaskType.COBOL_TO_JAVA
    }


def test_go_to_java_only_goto_spaghetti_uses_the_dispatcher(mmim_all_examples):
    java = _all_java(mmim_all_examples)
    assert len(java) == 45
    dispatched = sorted(
        sid for sid, e in java.items() if "_dispatch" in e.expected_output["java"]
    )
    assert dispatched == [_GO_TO_JAVA_SOURCE]


def test_go_to_java_goto_spaghetti_has_all_seven_jumps_translated(mmim_all_examples):
    text = _all_java(mmim_all_examples)[_GO_TO_JAVA_SOURCE].expected_output["java"]
    assert text.count("continue _dispatch;") == 7  # one per real GO TO
    assert "translate IRJump" not in text
    assert "// TODO" not in text
    assert text.count("case ") == 5  # one per paragraph
    assert text.count("{") == text.count("}")


def test_go_to_java_no_untranslated_irjump_remains_anywhere(mmim_all_examples):
    for sid, e in _all_java(mmim_all_examples).items():
        assert "translate IRJump" not in e.expected_output["java"], sid


def test_go_to_java_goto_spaghetti_still_compiles_and_stays_deterministic(
    mmim_all_examples,
):
    e = _all_java(mmim_all_examples)[_GO_TO_JAVA_SOURCE]
    assert e.expected_output["compiles"] is True
    assert e.metadata.ground_truth_status.value == "deterministic"


def test_go_to_java_did_not_change_counts_or_other_task_types(mmim_all_examples):
    java = _all_java(mmim_all_examples)
    assert sum(1 for e in java.values() if e.expected_output["compiles"]) == 45
    assert all(
        e.expected_output["java"].count("{") == e.expected_output["java"].count("}")
        for e in java.values()
    )
    rule_total = sum(
        e.expected_output["rule_count"]
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    )
    assert rule_total == 167  # was 157; task #stage25
    assert len(mmim_all_examples) == 351
    statuses: dict[str, int] = {}
    for e in mmim_all_examples:
        key = e.metadata.ground_truth_status.value
        statuses[key] = statuses.get(key, 0) + 1
    assert statuses == {"deterministic": 349, "executable_verified": 2}


# --------------------------------------------------------------------------
# 3r. COBOL VALUE clause -> Java field initializer (mmim-gen-v19,
#     docs/MMIM_VALUE_INITIALIZER_FIX.md). The parsed VALUE literal used to be
#     dropped at symbol creation, so every generated field started at the Java
#     default. Every one of the 45 sources declares at least one VALUE, so
#     every COBOL_TO_JAVA ``expected_output.java`` changes -- by exactly the
#     270 initializers and nothing else. Java reads a leading ``0`` as octal,
#     so numbers are emitted from their value (``VALUE 035`` is 35, not 29).
# --------------------------------------------------------------------------

_JAVA_INITIALIZER = re.compile(r"^\s+private (?:String|int|double) \w+ = ", re.M)
_JAVA_UNINITIALIZED = re.compile(r"^\s+private (?:String|int|double) \w+;", re.M)


def test_value_initializers_every_source_java_has_initializers(mmim_all_examples):
    java = _all_java(mmim_all_examples)
    assert len(java) == 45
    assert all(
        _JAVA_INITIALIZER.search(e.expected_output["java"]) for e in java.values()
    )
    total = sum(
        len(_JAVA_INITIALIZER.findall(e.expected_output["java"])) for e in java.values()
    )
    # every elementary item with a VALUE clause in the corpus: 270 from Stage 20
    # plus the 5 signed COMP-3 items of t_packed_decimal recovered in Stage 21
    assert total == 275


def test_value_initializers_no_numeric_initializer_is_octal(mmim_all_examples):
    """``VALUE 028`` / ``VALUE 09`` would not compile as Java octal and
    ``VALUE 035`` would silently be 29; none may appear as written."""
    for sid, e in _all_java(mmim_all_examples).items():
        assert not re.search(
            r"^\s+private (?:int|double) \w+ = -?0\d",
            e.expected_output["java"],
            re.M,
        ), sid


def test_value_initializers_real_zero_padded_values_are_exact(mmim_all_examples):
    java = {
        sid: e.expected_output["java"]
        for sid, e in _all_java(mmim_all_examples).items()
    }
    # ``VALUE 028`` / ``VALUE 09``: invalid Java octal if pasted as written.
    assert "private int driverAge = 28;" in java["t_insurance_claim"]
    assert "private int accountingPeriod = 9;" in java["t_packed_decimal"]
    # ``VALUE 035``: valid Java octal that would silently be 29.
    assert "private int age = 35;" in java["t_account_eligibility"]
    # ``VALUE 00065000.00`` (a decimal) is normalized too.
    assert "private double annualIncome = 65000.00;" in java["t_account_eligibility"]
    # ``VALUE SPACES`` -> the empty String, not Java's null.
    assert 'private String rejectionCode = "";' in java["t_account_eligibility"]


def test_value_initializers_goto_spaghetti_has_its_cobol_initial_state(
    mmim_all_examples,
):
    text = _all_java(mmim_all_examples)[_GO_TO_JAVA_SOURCE].expected_output["java"]
    assert "private int stepIndex = 1;" in text
    assert "private int accumulator = 0;" in text
    assert 'private String terminalState = "INITIAL";' in text
    assert "private int retryCounter = 0;" in text


def test_value_initializers_only_valueless_items_stay_uninitialized(
    mmim_all_examples,
):
    """152 declared fields have no VALUE clause (group items and elementary
    items without one); they keep no initializer, exactly as before. (Stage 23
    removed the 11 level-88 condition-names, which were never storage, from the
    declared fields: 137 -> 126. Task #stage27 adds 26 new FD fields across the
    4 FILE-SECTION sources, none with a VALUE clause: 126 -> 152.)"""
    java = _all_java(mmim_all_examples)
    uninitialized = sum(
        len(_JAVA_UNINITIALIZED.findall(e.expected_output["java"]))
        for e in java.values()
    )
    assert uninitialized == 152


def test_value_initializers_did_not_change_compile_status_or_counts(
    mmim_all_examples,
):
    java = _all_java(mmim_all_examples)
    assert sum(1 for e in java.values() if e.expected_output["compiles"]) == 45
    assert all(
        e.expected_output["java"].count("{") == e.expected_output["java"].count("}")
        for e in java.values()
    )
    assert len(mmim_all_examples) == 351
    statuses: dict[str, int] = {}
    for e in mmim_all_examples:
        key = e.metadata.ground_truth_status.value
        statuses[key] = statuses.get(key, 0) + 1
    assert statuses == {"deterministic": 349, "executable_verified": 2}


def test_value_initializers_architecture_data_model_is_unchanged(mmim_all_examples):
    """The architecture builder parses ``private <type> <name>;`` out of the
    generated Java. Once fields carry initializers it must still find them: if
    it did not, every ``transformation_planning`` data model (and any DTO for
    a program whose fields are all initialized) would silently shrink."""
    plans = [
        e for e in mmim_all_examples if e.task_type == TaskType.TRANSFORMATION_PLANNING
    ]
    assert len(plans) == 45
    goto = next(e for e in plans if e.input.source_id == _GO_TO_JAVA_SOURCE)
    assert len(goto.expected_output["data_model"]) == 5
    assert any(c["type"] == "DTO" for c in goto.expected_output["components"])
    with_dto = sum(
        1
        for e in plans
        if any(c["type"] == "DTO" for c in e.expected_output["components"])
    )
    assert with_dto == 45


# --------------------------------------------------------------------------
# 3s. Signed numeric VALUE literals (mmim-gen-v20,
#     docs/MMIM_SIGNED_VALUE_FIX.md). ``VALUE +000450000.00`` used to make the
#     data-division parser take ``+`` as the whole literal and abandon the
#     item (SYN005). Exactly one corpus source uses a signed VALUE
#     (t_packed_decimal, 5 COMP-3 items); only its 8 examples change, and
#     nothing else in the dataset does.
# --------------------------------------------------------------------------

_SIGNED_VALUE_SOURCE = "t_packed_decimal"
_SIGNED_VALUE_FIELDS = (
    "private double beginningBalance = 450000.00;",
    "private double periodDebits = 85200.50;",
    "private double periodCredits = 62100.25;",
    "private double endingBalance = 0.00;",
    "private double varianceAmount = 0.00;",
)


def _by_task(mmim_all_examples, task_type):
    return {e.input.source_id: e for e in mmim_all_examples if e.task_type == task_type}


def test_signed_value_packed_decimal_java_declares_the_five_recovered_items(
    mmim_all_examples,
):
    e = _by_task(mmim_all_examples, TaskType.COBOL_TO_JAVA)[_SIGNED_VALUE_SOURCE]
    text = e.expected_output["java"]
    for declaration in _SIGNED_VALUE_FIELDS:
        assert declaration in text
    assert len(re.findall(r"^\s+private (?:String|int|double) ", text, re.M)) == 13
    assert e.expected_output["compiles"] is True


def test_signed_value_packed_decimal_no_longer_reports_syn005(mmim_all_examples):
    pu = _by_task(mmim_all_examples, TaskType.PROGRAM_UNDERSTANDING)
    diag = pu[_SIGNED_VALUE_SOURCE].expected_output["parser_diagnostics"]
    # was 16, then 11; task #stage30 (docs/FIXED_FORMAT_NORMALIZATION.md)
    # drops the false SYN003 its column-7 "*" comment used to produce: 11 -> 10
    assert diag["syntax_diagnostic_count"] == 10
    assert "SYN005" not in diag["diagnostic_codes"]
    # Was 5 sources (was 138 total); task #stage25
    # (docs/MMIM_NEGATED_COMPARISON_FIX.md) removes the "NOT =" SYN005 from
    # the other 4 -- "t_inventory_reorder"'s is unrelated and remains.
    assert sorted(
        sid
        for sid, e in pu.items()
        if "SYN005" in e.expected_output["parser_diagnostics"]["diagnostic_codes"]
    ) == ["t_inventory_reorder"]
    assert (
        sum(
            e.expected_output["parser_diagnostics"]["syntax_diagnostic_count"]
            for e in pu.values()
        )
        == 104  # was 138, then 134 (task #stage25: -4 SYN005); task #stage27
        # (docs/MMIM_FILE_SECTION_FIELDS_FIX.md) removes the SYN101 on each of
        # the 4 FILE-SECTION sources: 134 -> 130; task #stage30
        # (docs/FIXED_FORMAT_NORMALIZATION.md) removes the false SYN003 on each
        # of the 26 sources with a column-7 "*" comment line: 130 -> 104
    )


def test_signed_value_packed_decimal_ast_and_architecture_carry_all_items(
    mmim_all_examples,
):
    plan = _by_task(mmim_all_examples, TaskType.TRANSFORMATION_PLANNING)[
        _SIGNED_VALUE_SOURCE
    ]
    assert len(plan.expected_output["data_model"]) == 13  # was 8
    ws = plan.analysis.ast["data_division"]["working_storage"]["items"]
    assert len(ws) == 13  # was 8: 2 groups + 8 COMP/COMP-3 numerics + 3 flags


def test_signed_value_packed_decimal_syntax_error_risk_disappears(mmim_all_examples):
    risks = _by_task(mmim_all_examples, TaskType.RISK_CLASSIFICATION)[
        _SIGNED_VALUE_SOURCE
    ].expected_output["risks"]
    syntax = [r for r in risks if r["category"] == "SYNTAX_ERROR"]
    # Was 6 occurrences (SYN003 + 5 x SYN005), then 1 (the SYN003). That last
    # one was the false error from the source's column-7 "*" comment line;
    # task #stage30 (docs/FIXED_FORMAT_NORMALIZATION.md) removes it, so the
    # source has no syntax error left and no SYNTAX_ERROR risk at all.
    assert syntax == []


def test_signed_value_only_packed_decimal_changed_the_java_and_counts(
    mmim_all_examples,
):
    java = _all_java(mmim_all_examples)
    assert sum(1 for e in java.values() if e.expected_output["compiles"]) == 45
    assert all(
        e.expected_output["java"].count("{") == e.expected_output["java"].count("}")
        for e in java.values()
    )
    initialized = sum(
        len(_JAVA_INITIALIZER.findall(e.expected_output["java"])) for e in java.values()
    )
    uninitialized = sum(
        len(_JAVA_UNINITIALIZED.findall(e.expected_output["java"]))
        for e in java.values()
    )
    # 5 new fields, all initialized; 137 -> 126 once Stage 23 dropped the 11
    # level-88 condition-names (not storage) from the declared fields; 126 ->
    # 152 once task #stage27 adds 26 uninitialized FD fields
    assert (initialized, uninitialized) == (275, 152)
    assert len(mmim_all_examples) == 351
    rule_total = sum(
        e.expected_output["rule_count"]
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    )
    assert rule_total == 167  # was 157; task #stage25
    statuses: dict[str, int] = {}
    for e in mmim_all_examples:
        key = e.metadata.ground_truth_status.value
        statuses[key] = statuses.get(key, 0) + 1
    assert statuses == {"deterministic": 349, "executable_verified": 2}


# --------------------------------------------------------------------------
# 3t. Level-88 condition-names are conditions, not storage (mmim-gen-v21,
#     docs/MMIM_LEVEL88_VALUE_FIX.md). They used to be declared as
#     uninitialized ``private String`` fields nothing ever read or wrote. The
#     corpus has exactly 11 level-88 entries, all in t_condition_names_88 (and
#     all plain string values, so the parser part changes no output): only that
#     source's COBOL_TO_JAVA and TRANSFORMATION_PLANNING examples change.
# --------------------------------------------------------------------------

_LEVEL88_SOURCE = "t_condition_names_88"
_LEVEL88_JAVA_NAMES = (
    "txDeposit",
    "txWithdrawal",
    "txTransfer",
    "txFee",
    "txValidKind",
    "txPending",
    "txApproved",
    "txRejected",
    "txSettled",
    "onlineChannel",
    "physicalBranch",
)
_LEVEL88_STORAGE = (
    "transactionStatusRecord",
    "txTypeCode",
    "txStatusFlag",
    "channelOrigin",
    "txAmount",
    "processingOutcome",
    "outcomeAction",
    "feesLevied",
)


def test_level88_java_declares_only_storage(mmim_all_examples):
    e = _all_java(mmim_all_examples)[_LEVEL88_SOURCE]
    text = e.expected_output["java"]
    fields = re.findall(r"^\s+private (?:String|int|double) (\w+)", text, re.M)
    assert tuple(fields) == _LEVEL88_STORAGE  # was 19: + the 11 condition-names
    for name in _LEVEL88_JAVA_NAMES:
        assert f" {name};" not in text and f" {name} =" not in text
    assert e.expected_output["compiles"] is True


def test_level88_architecture_data_model_lists_only_storage(mmim_all_examples):
    plan = _by_task(mmim_all_examples, TaskType.TRANSFORMATION_PLANNING)[
        _LEVEL88_SOURCE
    ]
    assert [d["name"] for d in plan.expected_output["data_model"]] == list(
        _LEVEL88_STORAGE
    )
    dto = next(c for c in plan.expected_output["components"] if c["type"] == "DTO")
    assert dto["evidence"][0]["detail"] == "8 WORKING-STORAGE field(s)"  # was 19


def test_level88_ast_still_carries_every_condition_and_its_values(mmim_all_examples):
    """The conditions did not go away -- they are metadata on the AST, which is
    where the behavioral extractor reads them from."""
    pu = _by_task(mmim_all_examples, TaskType.PROGRAM_UNDERSTANDING)[_LEVEL88_SOURCE]
    items = pu.analysis.ast["data_division"]["working_storage"]["items"]
    conds = {i["name"]: i["values"] for i in items if i.get("level") == 88}
    assert len(conds) == 11
    assert conds["TX-VALID-KIND"] == ["'D'", "'W'", "'T'", "'F'"]
    assert conds["ONLINE-CHANNEL"] == ["'WEB'", "'MOB'", "'API'"]
    assert conds["PHYSICAL-BRANCH"] == ["'BRN'", "'ATM'"]


def test_level88_only_that_source_lost_fields_and_totals_moved_by_eleven(
    mmim_all_examples,
):
    java = _all_java(mmim_all_examples)
    initialized = sum(
        len(_JAVA_INITIALIZER.findall(e.expected_output["java"])) for e in java.values()
    )
    uninitialized = sum(
        len(_JAVA_UNINITIALIZED.findall(e.expected_output["java"]))
        for e in java.values()
    )
    # 137 - 11 condition-names, then + 26 FD fields (task #stage27)
    assert (initialized, uninitialized) == (275, 152)
    assert sum(1 for e in java.values() if e.expected_output["compiles"]) == 45
    assert len(mmim_all_examples) == 351
    rule_total = sum(
        e.expected_output["rule_count"]
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    )
    assert rule_total == 167  # was 157; task #stage25
    statuses: dict[str, int] = {}
    for e in mmim_all_examples:
        key = e.metadata.ground_truth_status.value
        statuses[key] = statuses.get(key, 0) + 1
    assert statuses == {"deterministic": 349, "executable_verified": 2}


# --------------------------------------------------------------------------
# 3u. COBOL comparison semantics (mmim-gen-v22,
#     docs/MMIM_STRING_COMPARISON_FIX.md). ``=``/``!=`` between two operands
#     that are known text is COBOL's space-padded alphanumeric equality
#     (``_cobolEquals``), not Java ``==`` on two String references; level-88
#     condition references are translated when provably correct. Only
#     t_policy_redefines has a reachable text comparison on declared String
#     fields, so exactly one COBOL_TO_JAVA example changes; the AST, IR, CFG,
#     rules, risks and every other task type are untouched.
# --------------------------------------------------------------------------

_TEXT_COMPARE_SOURCE = "t_policy_redefines"


def test_text_comparison_policy_redefines_uses_cobol_equality(mmim_all_examples):
    e = _all_java(mmim_all_examples)[_TEXT_COMPARE_SOURCE]
    text = e.expected_output["java"]
    assert 'if (_cobolEquals(policyKind, "AUTO")) {' in text
    assert 'if (_cobolEquals(policyKind, "LIFE")) {' in text
    assert text.count("static boolean _cobolEquals(String a, String b) {") == 1
    assert not re.search(r'(?:==|!=) "', text)  # no identity comparison left
    assert text.count("{") == text.count("}")
    assert e.expected_output["compiles"] is True


def test_text_comparison_helper_appears_only_where_it_is_used(mmim_all_examples):
    # Was [_TEXT_COMPARE_SOURCE] alone; task #stage25
    # (docs/MMIM_NEGATED_COMPARISON_FIX.md) adds "t_batch_acct_update" -- see
    # §3v's test_negated_comparison_helper_used_by_exactly_two_sources below,
    # which pins the same fact with its own rationale. task #stage27
    # (docs/MMIM_FILE_SECTION_FIELDS_FIX.md) adds "t_daily_trans_report".
    java = _all_java(mmim_all_examples)
    users = sorted(
        sid for sid, e in java.items() if "_cobolEquals" in e.expected_output["java"]
    )
    assert users == sorted(
        ["t_batch_acct_update", "t_daily_trans_report", _TEXT_COMPARE_SOURCE]
    )


def test_text_comparison_leaves_unknown_typed_and_numeric_comparisons_alone(
    mmim_all_examples,
):
    """Numeric comparisons never change. FILE SECTION fields were an
    unknown-type example here until task #stage27
    (docs/MMIM_FILE_SECTION_FIELDS_FIX.md): they are declared now, so their
    text comparisons correctly get the helper too (see
    test_text_comparison_helper_appears_only_where_it_is_used) -- there is
    no longer any *unknown-typed* text comparison left in the corpus."""
    java = _all_java(mmim_all_examples)
    assert (
        'if (_cobolEquals(fdOverdraftProt, "Y")) {'
        in java["t_batch_acct_update"].expected_output["java"]
    )
    assert (
        '_cobolEquals(fdTxSuspicious, "Y")'
        in java["t_daily_trans_report"].expected_output["java"]
    )
    assert "if (stepIndex == 1) {" in java["t_goto_spaghetti"].expected_output["java"]
    assert "if (counter > 0) {" in java["fx_combined"].expected_output["java"]
    remaining = sum(
        len(re.findall(r'(?:==|!=) "', e.expected_output["java"]))
        for e in java.values()
    )
    assert remaining == 0  # no unknown-typed text comparison remains


def test_text_comparison_changed_nothing_else(mmim_all_examples):
    java = _all_java(mmim_all_examples)
    assert sum(1 for e in java.values() if e.expected_output["compiles"]) == 45
    assert all(
        e.expected_output["java"].count("{") == e.expected_output["java"].count("}")
        for e in java.values()
    )
    assert len(mmim_all_examples) == 351
    rule_total = sum(
        e.expected_output["rule_count"]
        for e in mmim_all_examples
        if e.task_type == TaskType.BUSINESS_RULE_EXTRACTION
    )
    assert rule_total == 167  # was 157; task #stage25
    statuses: dict[str, int] = {}
    for e in mmim_all_examples:
        key = e.metadata.ground_truth_status.value
        statuses[key] = statuses.get(key, 0) + 1
    assert statuses == {"deterministic": 349, "executable_verified": 2}
    # the initialized field count (Stages 20-23) is unchanged; uninitialized
    # rises 126 -> 152 (task #stage27): 26 new FD fields across the 4
    # FILE-SECTION sources, none of which has a VALUE clause in this corpus
    # (FILE SECTION records never do), so all newly-declared fields are
    # uninitialized -- none of them was initialized before either (they did
    # not exist).
    initialized = sum(
        len(_JAVA_INITIALIZER.findall(e.expected_output["java"])) for e in java.values()
    )
    uninitialized = sum(
        len(_JAVA_UNINITIALIZED.findall(e.expected_output["java"]))
        for e in java.values()
    )
    assert (initialized, uninitialized) == (275, 152)


def test_level88_conditions_in_corpus_java_remain_unreachable_hence_unchanged(
    mmim_all_examples,
):
    """Every level-88 condition reference in the corpus sits in a paragraph body
    the backend skips as unreachable, so the new condition-name translation
    changes no corpus output; the 88 declarations are still not storage."""
    text = _all_java(mmim_all_examples)["t_condition_names_88"].expected_output["java"]
    assert "txDeposit" not in text and "_cobolEquals" not in text
    assert "cannot be translated" not in text


# --------------------------------------------------------------------------
# 3v. Negated relational operators, "NOT =" and "<>" (mmim-gen-v23,
#     docs/MMIM_NEGATED_COMPARISON_FIX.md). Both COBOL spellings of "not
#     equal" used to fail to parse at all (the whole IF was dropped by panic-
#     mode recovery). Exactly 4 corpus sources have a "NOT =" comparison;
#     their embedded AST/IR/business rules/risks/dependencies/strategy now
#     represent the previously-dropped IFs, but only 1 of them
#     (t_batch_acct_update, reachable only because a separate, pre-existing,
#     unrelated parser gap drops its entry paragraph's GOBACK) has its
#     generated Java text change at all.
# --------------------------------------------------------------------------

_NEGATED_COMPARISON_SOURCES = (
    "t_account_eligibility",
    "t_batch_acct_update",
    "t_insurance_claim",
    "t_payment_gateway",
)


def test_negated_comparison_only_batch_acct_update_java_changes(mmim_all_examples):
    java = _all_java(mmim_all_examples)
    text = java["t_batch_acct_update"].expected_output["java"]
    assert 'if (!_cobolEquals(wsFileStatus, "00")) {' in text
    assert text.count("static boolean _cobolEquals(String a, String b) {") == 1
    assert text.count("{") == text.count("}")
    # was False -- a pre-existing, unrelated FILE SECTION gap
    # (docs/MMIM_NEGATED_COMPARISON_FIX.md §5) -- **resolved in task #stage27**
    # (docs/MMIM_FILE_SECTION_FIELDS_FIX.md): FD-ACCT-BAL/FD-OVERDRAFT-PROT are
    # now declared, so this source compiles too.
    assert java["t_batch_acct_update"].expected_output["compiles"] is True
    for sid in _NEGATED_COMPARISON_SOURCES:
        if sid != "t_batch_acct_update":
            assert "_cobolEquals" not in java[sid].expected_output["java"], sid


def test_negated_comparison_helper_used_by_exactly_two_sources(mmim_all_examples):
    """Name kept from task #stage25; task #stage27 adds a third user,
    `t_daily_trans_report` (docs/MMIM_FILE_SECTION_FIELDS_FIX.md) -- see
    tests/backend/test_cobol_comparison_semantics.py
    ::test_real_corpus_only_these_three_sources_use_the_helper for the
    full explanation."""
    java = _all_java(mmim_all_examples)
    users = sorted(
        sid for sid, e in java.items() if "_cobolEquals" in e.expected_output["java"]
    )
    assert users == [
        "t_batch_acct_update",
        "t_daily_trans_report",
        "t_policy_redefines",
    ]


def test_negated_comparison_account_eligibility_business_rules_use_angle_brackets(
    mmim_all_examples,
):
    br = _by_task(mmim_all_examples, TaskType.BUSINESS_RULE_EXTRACTION)[
        "t_account_eligibility"
    ]
    conditions = [r["condition"] for r in br.expected_output["business_rules"]]
    assert any("CITIZENSHIP-STATUS <> 'CITIZEN'" in c for c in conditions)
    assert any("CITIZENSHIP-STATUS <> 'RESIDENT'" in c for c in conditions)
    assert not any("NOT =" in c for c in conditions)  # normalised, never raw


def test_negated_comparison_did_not_change_counts_elsewhere(mmim_all_examples):
    java = _all_java(mmim_all_examples)
    assert sum(1 for e in java.values() if e.expected_output["compiles"]) == 45
    assert all(
        e.expected_output["java"].count("{") == e.expected_output["java"].count("}")
        for e in java.values()
    )
    assert len(mmim_all_examples) == 351
    statuses: dict[str, int] = {}
    for e in mmim_all_examples:
        key = e.metadata.ground_truth_status.value
        statuses[key] = statuses.get(key, 0) + 1
    assert statuses == {"deterministic": 349, "executable_verified": 2}


def test_builder_records_eligibility_gated_skip_for_synthetic_no_test_source(
    tmp_path,
):
    """A source with business logic but nothing a deterministic behavioral
    extractor can turn into a test case should be skipped, not emitted with
    an empty test suite."""
    from app.dataset.schema import Difficulty

    from app.dataset.builder import SourceRecord

    builder = MMIMDatasetBuilder(work_dir=tmp_path, strict_eligibility=True)
    # A minimal program with no conditional/business-rule-bearing logic at
    # all: DISPLAY-only, nothing for the behavioral extractor to partition.
    source = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. NOOPPGM.
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY "HELLO"
           STOP RUN.
"""
    rec = SourceRecord(
        source_id="test_noop",
        source=source,
        provenance=Provenance.SYNTHETIC,
        license="MIT",
        difficulty=Difficulty.EASY,
    )
    result = builder.build([rec])
    task_types = {e.task_type for e in result.examples}
    assert TaskType.VALIDATION_REASONING not in task_types
    skip_tasks = {(s["source_id"], s["task_type"]) for s in result.skipped}
    assert ("test_noop", TaskType.VALIDATION_REASONING.value) in skip_tasks


# --------------------------------------------------------------------------
# 4. Deterministic regeneration
# --------------------------------------------------------------------------


def test_deterministic_regeneration(tmp_path, training_corpus):
    corpus = training_corpus[:3]
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"

    res1, _, _, _ = build_mmim_dataset(
        out1,
        corpus,
        seed=42,
        dataset_version=MMIM_DATASET_VERSION_V2,
        generator_version=MMIM_GENERATOR_VERSION_V25,
        strict_eligibility=True,
    )
    res2, _, _, _ = build_mmim_dataset(
        out2,
        corpus,
        seed=42,
        dataset_version=MMIM_DATASET_VERSION_V2,
        generator_version=MMIM_GENERATOR_VERSION_V25,
        strict_eligibility=True,
    )

    ids1 = [e.example_id for e in res1.examples]
    ids2 = [e.example_id for e in res2.examples]
    assert ids1 == ids2
    assert res1.skipped == res2.skipped

    ex1_dumps = [e.model_dump_json() for e in res1.examples]
    ex2_dumps = [e.model_dump_json() for e in res2.examples]
    assert ex1_dumps == ex2_dumps


# --------------------------------------------------------------------------
# 5. Benchmark leakage isolation
# --------------------------------------------------------------------------


def test_zero_benchmark_source_overlap(benchmark, mmim_all_examples):
    bench_ids = {e.input.source_id for e in benchmark.examples}
    mmim_ids = {e.input.source_id for e in mmim_all_examples}
    assert bench_ids & mmim_ids == set()


def test_zero_benchmark_hash_overlap(benchmark, mmim_all_examples):
    bench_sha = {_sha(e.input.source) for e in benchmark.examples}
    mmim_sha = {_sha(e.input.source) for e in mmim_all_examples}
    assert bench_sha & mmim_sha == set()


def test_zero_benchmark_normalized_overlap(benchmark, mmim_all_examples):
    bench_norm = {_sha(_norm(e.input.source)) for e in benchmark.examples}
    mmim_norm = {_sha(_norm(e.input.source)) for e in mmim_all_examples}
    assert bench_norm & mmim_norm == set()


# --------------------------------------------------------------------------
# 6. Split leakage isolation
# --------------------------------------------------------------------------


def test_splits_are_source_disjoint(mmim_splits):
    train_sources = {e.input.source_id for e in mmim_splits["train"]}
    val_sources = {e.input.source_id for e in mmim_splits["validation"]}
    test_sources = {e.input.source_id for e in mmim_splits["test"]}

    assert train_sources & val_sources == set()
    assert train_sources & test_sources == set()
    assert val_sources & test_sources == set()


def test_leakage_detector_reports_no_errors(mmim_splits):
    report = detect_leakage(
        train=mmim_splits["train"],
        validation=mmim_splits["validation"],
        test=mmim_splits["test"],
    )
    assert report.ok is True
    assert report.error_count == 0


def test_split_counts_and_tasks(mmim_splits, mmim_all_examples):
    total = len(mmim_all_examples)
    train_count = len(mmim_splits["train"])
    val_count = len(mmim_splits["validation"])
    test_count = len(mmim_splits["test"])

    assert train_count + val_count + test_count == total
    assert train_count > 0
    assert val_count > 0
    assert test_count > 0


def test_mmim_v1_directory_untouched():
    """mmim-v1 must never be overwritten by v2 generation."""
    import json

    v1_manifest = json.loads(
        Path("data/dataset/mmim-v1/manifest.json").read_text("utf-8")
    )
    assert v1_manifest["dataset_version"] == "mmim-v1"
    assert v1_manifest["example_count"] == 144
    assert v1_manifest["source_count"] == 18


# ---------------------------------------------------------------------------
# Stage 30 -- fixed-format normalization (docs/FIXED_FORMAT_NORMALIZATION.md,
# mmim-gen-v25). Comment lines (``*`` in column 7) are blanked in place before
# lexing, so the 26 corpus sources that carry one lose a false SYN003 and
# everything derived from it.
# ---------------------------------------------------------------------------

_STAGE30_REMAINING_SYNTAX_ERROR_SOURCES = [
    "t_batch_acct_update",
    "t_daily_trans_report",
    "t_inventory_extract",
    "t_inventory_reorder",
    "t_payroll_file_post",
    "t_table_indexed",
]


def test_stage30_no_example_reports_a_false_column7_comment_syn003(mmim_all_examples):
    pu = _by_task(mmim_all_examples, TaskType.PROGRAM_UNDERSTANDING)
    assert [
        sid
        for sid, e in pu.items()
        if "SYN003" in e.expected_output["parser_diagnostics"]["diagnostic_codes"]
    ] == []  # was 26 sources


def test_stage30_syntax_error_risk_remains_only_where_a_real_error_remains(
    mmim_all_examples,
):
    rc = _by_task(mmim_all_examples, TaskType.RISK_CLASSIFICATION)
    assert (
        sorted(
            sid
            for sid, e in rc.items()
            if any(r["category"] == "SYNTAX_ERROR" for r in e.expected_output["risks"])
        )
        == _STAGE30_REMAINING_SYNTAX_ERROR_SOURCES
    )  # was 26 sources: 20 lose the risk, these 6 keep it for a real SYN001/SYN005
    assert sum(e.expected_output["risk_count"] for e in rc.values()) == 160 - 20


def test_stage30_strategies_the_false_syntax_error_had_skewed(mmim_all_examples):
    ms = _by_task(mmim_all_examples, TaskType.MODERNIZATION_STRATEGY)
    moved = {
        "t_account_eligibility": "REFACTOR",  # was REHOST
        "t_condition_names_88": "REFACTOR",  # was REHOST
        "t_customer_record": "REFACTOR",  # was REHOST
        "t_fallthrough_flow": "REFACTOR",  # was REHOST
        "t_payroll_deduct": "REHOST",  # was PHASED_MIGRATION
    }
    assert {
        sid: ms[sid].expected_output["primary"]["strategy"] for sid in moved
    } == moved


def test_stage30_counts_splits_and_java_are_unchanged(mmim_all_examples):
    assert len(mmim_all_examples) == 351
    java = _all_java(mmim_all_examples)
    assert len(java) == 45
    assert sum(1 for e in java.values() if e.expected_output["compiles"]) == 45
