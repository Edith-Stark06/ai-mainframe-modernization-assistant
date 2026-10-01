"""Grounding instructions in the explanation/documentation prompts."""

from __future__ import annotations

import pytest

from app.ai.documentation.prompts import build_documentation_prompt
from app.ai.explanation.prompts import build_explanation_prompt
from app.ai.grounding import GROUNDING_RULES, RULES_HEADING

BUILDERS = [build_explanation_prompt, build_documentation_prompt]


@pytest.mark.parametrize("build", BUILDERS)
def test_question_adds_the_grounding_rules(build) -> None:
    prompt = build("[c1]\nIF X > 5", {"rag_query": "When is X large?"})
    for line in GROUNDING_RULES:
        assert line in prompt
    assert "never guess numbers" in prompt
    assert "not in the retrieved context" in prompt
    assert "Cite sources by their number" in prompt
    assert "Never write chunk ids" in prompt
    assert "No tables" in prompt
    assert "presumably" in prompt  # told not to hedge


@pytest.mark.parametrize("build", BUILDERS)
def test_no_question_means_no_grounding_rules(build) -> None:
    prompt = build("IF X > 5", {})
    assert "Grounding rules" not in prompt
    assert "never guess" not in prompt


@pytest.mark.parametrize("build", BUILDERS)
def test_rules_get_the_authoritative_heading_only_when_answering_a_question(
    build,
) -> None:
    rules = ["[br1]\nBusiness rule BR-007"]
    asked = build("src", {"rag_query": "q?", "business_rules": rules})
    plain = build("src", {"business_rules": rules})
    assert RULES_HEADING in asked
    assert "=== BUSINESS RULES ===" not in asked
    assert "=== BUSINESS RULES ===" in plain
    assert RULES_HEADING not in plain


@pytest.mark.parametrize("build", BUILDERS)
def test_existing_question_contract_is_preserved(build) -> None:
    prompt = build("src", {"rag_query": "What is X?"})
    assert "=== USER QUESTION ===" in prompt
    assert "Directly and specifically answer the user's question" in prompt


def test_grounded_prompt_is_deterministic() -> None:
    ctx = {"rag_query": "q?", "business_rules": ["[a]\nr1", "[b]\nr2"]}
    assert build_explanation_prompt("s", ctx) == build_explanation_prompt("s", ctx)
