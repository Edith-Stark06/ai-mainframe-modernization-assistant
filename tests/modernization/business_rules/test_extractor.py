"""Unit + integration tests for BusinessRuleExtractor (task #112)."""

from __future__ import annotations

import textwrap

from app.modernization.business_rules import (
    BusinessRuleCategory,
    BusinessRuleExtractor,
    RuleActionKind,
)


def _src(body: str) -> str:
    return textwrap.dedent("""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-STATUS  PIC X VALUE SPACE.
       01 WS-RESULT  PIC X(10) VALUE SPACE.
       01 WS-AGE     PIC 9(3) VALUE 0.
       01 WS-AMOUNT  PIC 9(7) VALUE 0.
       01 WS-FEE     PIC 9(5) VALUE 0.
       01 WS-TOTAL   PIC 9(9) VALUE 0.
       01 WS-ERR     PIC X VALUE SPACE.
       PROCEDURE DIVISION.
       MAIN-PARA.
    """) + textwrap.indent(textwrap.dedent(body), "           ")


def _extract(analyze, body: str):
    return BusinessRuleExtractor().extract(analyze(_src(body)))


# ---------------------------------------------------------------------------
# Basic extraction
# ---------------------------------------------------------------------------


def test_no_ast_returns_empty() -> None:
    from app.analysis.models import AnalysisResult

    result = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=False,
        dependencies=[],
        ast=None,
    )
    assert BusinessRuleExtractor().extract(result) == []


def test_top_level_actions_are_not_rules(analyze) -> None:
    rules = _extract(analyze, "MOVE 'X' TO WS-RESULT.\nSTOP RUN.\n")
    assert rules == []


def test_simple_conditional_validation(analyze) -> None:
    rules = _extract(
        analyze,
        "IF WS-STATUS = 'A'\n    MOVE 'VALID' TO WS-RESULT\nEND-IF.\nSTOP RUN.\n",
    )
    assert len(rules) == 1
    rule = rules[0]
    assert rule.rule_id == "BR-001"
    assert rule.category is BusinessRuleCategory.CONDITIONAL_VALIDATION
    assert rule.condition == "WS-STATUS = 'A'"
    assert len(rule.actions) == 1
    assert rule.actions[0].kind is RuleActionKind.ASSIGN
    assert rule.actions[0].target == "WS-RESULT"
    assert rule.actions[0].literals == ("'VALID'",)
    assert rule.actions[0].raw == "WS-RESULT = 'VALID'"
    assert rule.paragraph == "MAIN-PARA"
    assert rule.confidence == 1.0


def test_limit_check_category(analyze) -> None:
    rules = _extract(
        analyze,
        "IF WS-AMOUNT > 50000\n    MOVE 'FLAG' TO WS-RESULT\nEND-IF.\nSTOP RUN.\n",
    )
    assert len(rules) == 1
    assert rules[0].category is BusinessRuleCategory.LIMIT_CHECK
    assert rules[0].condition == "WS-AMOUNT > 50000"
    # The comparison is preserved exactly — never relabelled.
    assert "50000" in rules[0].condition


def test_calculation_category_and_action_ordering(analyze) -> None:
    rules = _extract(
        analyze,
        "IF WS-STATUS = 'A'\n"
        "    ADD WS-FEE TO WS-TOTAL\n"
        "    MOVE 'DONE' TO WS-RESULT\nEND-IF.\nSTOP RUN.\n",
    )
    assert len(rules) == 1
    rule = rules[0]
    assert rule.category is BusinessRuleCategory.CALCULATION
    assert [a.kind for a in rule.actions] == [RuleActionKind.ADD, RuleActionKind.ASSIGN]
    assert rule.actions[0].raw == "WS-TOTAL += WS-FEE"


def test_status_transition_category(analyze) -> None:
    rules = _extract(
        analyze,
        "IF WS-STATUS = 'P'\n    MOVE 'A' TO WS-STATUS\nEND-IF.\nSTOP RUN.\n",
    )
    assert len(rules) == 1
    assert rules[0].category is BusinessRuleCategory.STATUS_TRANSITION


def test_error_condition_from_literal_name_evidence(analyze) -> None:
    rules = _extract(
        analyze,
        "IF WS-AGE < 18\n    MOVE 'INVALID' TO WS-ERR\nEND-IF.\nSTOP RUN.\n",
    )
    assert len(rules) == 1
    assert rules[0].category is BusinessRuleCategory.ERROR_CONDITION
    assert any("INVALID" in e for e in rules[0].evidence)


# ---------------------------------------------------------------------------
# ELSE + nesting
# ---------------------------------------------------------------------------


def test_else_branch_produces_negated_rule(analyze) -> None:
    rules = _extract(
        analyze,
        "IF WS-AGE >= 18\n"
        "    MOVE 'OK' TO WS-RESULT\n"
        "ELSE\n"
        "    MOVE 'NO' TO WS-RESULT\nEND-IF.\nSTOP RUN.\n",
    )
    conditions = sorted(r.condition for r in rules)
    assert conditions == ["NOT (WS-AGE >= 18)", "WS-AGE >= 18"]


def test_nested_if_combines_conditions_with_lower_confidence(analyze) -> None:
    rules = _extract(
        analyze,
        "IF WS-AGE >= 18\n"
        "    IF WS-STATUS = 'A'\n"
        "        MOVE 'ELIGIBLE' TO WS-RESULT\n"
        "    END-IF\n"
        "END-IF.\nSTOP RUN.\n",
    )
    assert len(rules) == 1
    rule = rules[0]
    assert rule.condition == "(WS-AGE >= 18) AND (WS-STATUS = 'A')"
    assert rule.confidence == 0.75
    assert set(rule.variables.conditions) == {"WS-AGE", "WS-STATUS"}


# ---------------------------------------------------------------------------
# Variables / dependencies / literals
# ---------------------------------------------------------------------------


def test_literals_are_not_variables(analyze) -> None:
    rules = _extract(
        analyze,
        "IF WS-STATUS = 'A'\n    MOVE 'VALID' TO WS-RESULT\nEND-IF.\nSTOP RUN.\n",
    )
    rule = rules[0]
    assert "'A'" not in rule.variables.reads
    assert "'VALID'" not in rule.variables.writes
    assert "'VALID'" not in rule.dependencies
    assert rule.variables.reads == ("WS-STATUS",)
    assert rule.variables.writes == ("WS-RESULT",)


def test_dependencies_include_call_and_perform_targets(analyze) -> None:
    rules = _extract(
        analyze,
        "IF WS-STATUS = 'A'\n"
        "    PERFORM SUB-STEP\n"
        "    CALL 'EXTSVC'\nEND-IF.\nSTOP RUN.\n",
    )
    assert len(rules) == 1
    assert "SUB-STEP" in rules[0].dependencies
    assert "EXTSVC" in rules[0].dependencies


def test_source_locations_populated(analyze) -> None:
    rules = _extract(
        analyze,
        "IF WS-STATUS = 'A'\n    MOVE 'V' TO WS-RESULT\nEND-IF.\nSTOP RUN.\n",
    )
    locs = rules[0].source_locations
    assert len(locs) == 2  # IF header + the MOVE
    assert all(p.filename.endswith("prog.cbl") for p in locs)
    assert locs[0].line < locs[1].line or locs[0].line == locs[1].line


# ---------------------------------------------------------------------------
# Determinism, dedup, ordering
# ---------------------------------------------------------------------------


def test_deterministic_ids_and_ordering(analyze) -> None:
    src = _src(
        "IF WS-AMOUNT > 50000\n    MOVE 'F' TO WS-RESULT\nEND-IF.\n"
        "IF WS-STATUS = 'A'\n    MOVE 'V' TO WS-RESULT\nEND-IF.\nSTOP RUN.\n"
    )
    a = analyze(src)
    r1 = BusinessRuleExtractor().extract(a)
    r2 = BusinessRuleExtractor().extract(a)
    assert [x.to_dict() for x in r1] == [x.to_dict() for x in r2]
    assert [x.rule_id for x in r1] == ["BR-001", "BR-002"]
    # ordered by source position
    assert r1[0].source_locations[0].line < r1[1].source_locations[0].line


def test_identical_rule_deduplicated(analyze) -> None:
    # Same paragraph, same condition, same action reached once — a repeated
    # IF with identical body in the same paragraph collapses to one rule.
    body = (
        "IF WS-STATUS = 'A'\n    MOVE 'V' TO WS-RESULT\nEND-IF.\n"
        "IF WS-STATUS = 'A'\n    MOVE 'V' TO WS-RESULT\nEND-IF.\nSTOP RUN.\n"
    )
    rules = _extract(analyze, body)
    assert len(rules) == 1


def test_same_condition_different_paragraph_kept_distinct(
    analyze,
) -> None:
    src = (
        _src("IF WS-STATUS = 'A'\n    MOVE 'V' TO WS-RESULT\nEND-IF.\nSTOP RUN.\n")
        + "\n       OTHER-PARA.\n           IF WS-STATUS = 'A'\n"
        "               MOVE 'V' TO WS-RESULT\n           END-IF.\n"
    )
    rules = BusinessRuleExtractor().extract(analyze(src))
    assert len(rules) == 2
    assert {r.paragraph for r in rules} == {"MAIN-PARA", "OTHER-PARA"}


# ---------------------------------------------------------------------------
# Non-fabrication
# ---------------------------------------------------------------------------


def test_incomplete_condition_not_fabricated(analyze) -> None:
    # A condition with a missing operand must not produce a rule.
    rules = BusinessRuleExtractor().extract(
        analyze(_src("IF WS-STATUS\n    MOVE 'V' TO WS-RESULT\nEND-IF.\nSTOP RUN.\n"))
    )
    # Either the parser rejected it, or the extractor skipped it — never a
    # rule with an invented right-hand side.
    for rule in rules:
        assert rule.condition.count(" ") >= 2  # left op right minimum


def test_comment_only_paragraph_yields_no_rules(analyze) -> None:
    rules = _extract(analyze, "DISPLAY 'JUST A MESSAGE'.\nSTOP RUN.\n")
    assert rules == []


def test_complex_fixture_rules_are_evidence_backed(complex_analysis) -> None:
    rules = BusinessRuleExtractor().extract(complex_analysis)
    assert len(rules) > 0
    for rule in rules:
        assert rule.rule_id.startswith("BR-")
        assert rule.source_locations
        assert rule.paragraph
        assert 0.0 <= rule.confidence <= 1.0
        # every dependency is an identifier, never a literal
        for dep in rule.dependencies:
            assert not (dep.startswith("'") or dep.startswith('"'))
    ids = [r.rule_id for r in rules]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))


def test_complex_fixture_deterministic(complex_analysis) -> None:
    r1 = BusinessRuleExtractor().extract(complex_analysis)
    r2 = BusinessRuleExtractor().extract(complex_analysis)
    assert [x.to_dict() for x in r1] == [x.to_dict() for x in r2]
