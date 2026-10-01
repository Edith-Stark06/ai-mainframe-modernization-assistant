"""The chat question prompt answers what was asked; it does not explain the program."""

from __future__ import annotations

from app.ai.explanation.prompts import build_explanation_prompt
from app.ai.explanation.service import CodeExplanationService
from app.ai.providers.fake import FakeLLMProvider

CTX = {"rag_query": "What is the tax rate?"}


def prompt(**extra) -> str:
    return build_explanation_prompt(
        "[1]\n01 WS-TAX-RATE PIC 9V99 VALUE 0.18.", {**CTX, **extra}
    )


def test_it_asks_for_exactly_what_was_asked() -> None:
    text = prompt()
    assert "Answer exactly what was asked and only that" in text
    assert "Directly and specifically answer the user's question" in text


def test_it_no_longer_asks_for_a_tour_of_the_program() -> None:
    text = prompt()
    for generic in (
        "Please explain the following COBOL program",
        "Your explanation should include",
        "- What the program does",
        "- Major processing steps",
    ):
        assert generic not in text


def test_small_talk_and_off_topic_get_one_short_sentence() -> None:
    text = prompt()
    assert "not a question about the program" in text
    assert "one short, natural sentence" in text
    assert 'never mention "the user"' in text


def test_context_is_labelled_as_retrieved_context_and_question_comes_last() -> None:
    text = prompt()
    assert "=== RETRIEVED CONTEXT ===" in text
    assert "=== COBOL SOURCE ===" not in text
    assert text.index("=== USER QUESTION ===") > text.index("=== RETRIEVED CONTEXT ===")
    assert "What is the tax rate?" in text


def test_a_one_line_answer_needs_no_explanation_section() -> None:
    assert "a one-line answer needs no explanation" in prompt()


def test_conversation_so_far_is_included_for_follow_ups() -> None:
    text = prompt(
        conversation=[("user", "What discount does type R get?"), ("assistant", "10%.")]
    )
    assert "=== CONVERSATION SO FAR ===" in text
    assert "User: What discount does type R get?" in text
    assert "Assistant: 10%." in text
    assert text.index("=== CONVERSATION SO FAR ===") < text.index(
        "=== USER QUESTION ==="
    )


def test_no_conversation_section_without_history() -> None:
    assert "CONVERSATION SO FAR" not in prompt()


def test_a_long_earlier_turn_is_truncated() -> None:
    text = prompt(conversation=[("assistant", "x" * 5000)])
    assert "x" * 601 not in text


def test_rules_use_the_authoritative_heading() -> None:
    text = prompt(business_rules=["[2]\nBusiness rule BR-007"])
    assert "PARSER-DERIVED BUSINESS RULES" in text


def test_the_general_explanation_prompt_is_unchanged_without_a_question() -> None:
    text = build_explanation_prompt("IDENTIFICATION DIVISION.", {})
    assert "Please explain the following COBOL program." in text
    assert "- What the program does" in text
    assert "=== COBOL SOURCE ===" in text
    assert "Answer exactly what was asked" not in text


# A reply with only "Summary:" (a one-line answer) is shown without the label.


def _explain(reply: str):
    service = CodeExplanationService(FakeLLMProvider(response_text=reply))
    return service.explain_code("src", {"rag_query": "q?"}, allow_unstructured=True)


def test_summary_only_reply_is_shown_without_the_label() -> None:
    result = _explain("Summary: The tax rate is 18%.")
    assert result.chat_text() == "The tax rate is 18%."


def test_label_casing_and_dangling_markers_are_handled() -> None:
    assert _explain("summary:  **  \nIt is 18%.").chat_text() == "It is 18%."


def test_plain_reply_without_any_label_is_unchanged() -> None:
    assert _explain("Glad to help.").chat_text() == "Glad to help."
