"""Chat intent: conversational messages vs questions about the program."""

from __future__ import annotations

import pytest

from app.rag.intent import (
    Intent,
    classify_intent,
    conversational_reply,
    retrieval_query,
    wants_broad_context,
)

# ------------------------------------------------------------ classification


@pytest.mark.parametrize(
    "message",
    [
        "hi",
        "Hi!",
        "hello",
        "Hello there",
        "hey",
        "hey, good morning",
        "good morning",
        "Good evening!",
        "hola",
        "sup",
        "how are you",
        "How are you?",
        "what's up",
    ],
)
def test_greetings(message: str) -> None:
    assert classify_intent(message) is Intent.GREETING


@pytest.mark.parametrize(
    "message",
    [
        "thanks",
        "thank you",
        "thanks a lot",
        "okay cool its wokring good",
        "ok cool",
        "great job",
        "that makes sense",
        "got it, thanks",
        "perfect",
        "nice one",
        "it works",
        "awesome thanks so much",
        "ok",
        "good",
    ],
)
def test_thanks_and_acknowledgements(message: str) -> None:
    assert classify_intent(message) is Intent.THANKS


@pytest.mark.parametrize(
    "message", ["bye", "goodbye", "see you later", "that's all", "good night"]
)
def test_farewells(message: str) -> None:
    assert classify_intent(message) is Intent.FAREWELL


@pytest.mark.parametrize(
    "message",
    [
        "help",
        "what can you do",
        "What can you do?",
        "what can I ask",
        "who are you",
        "how do I use this",
        "how does this work",
    ],
)
def test_help_requests(message: str) -> None:
    assert classify_intent(message) is Intent.HELP


@pytest.mark.parametrize(
    "message",
    [
        # a pleasantry never swallows a real question
        "hi, what does this program do?",
        "hello, explain the discount logic",
        "thanks, what is the tax rate?",
        "ok list the business rules",
        "great, now analyze the converted java code",
        # statements that say something about the program are questions
        "this tax rate looks good",
        "thanks for the help with the tax logic",
        "the discount seems wrong",
        # ordinary questions and requests
        "At what order total does the status become HIGH VALUE?",
        "analyze the converted java code",
        "Explain what this program does",
        "what is WS-TOTAL",
        "does it round the total?",
        "I want to know the discount for R",
        "walk me through an order",
        "yes",
        "no",
        "",
    ],
)
def test_questions_are_never_treated_as_conversation(message: str) -> None:
    assert classify_intent(message) is Intent.QUESTION


def test_a_code_looking_token_makes_it_a_question() -> None:
    assert classify_intent("cool, WS-STATUS") is Intent.QUESTION
    assert classify_intent("nice 50000") is Intent.QUESTION
    assert classify_intent("great wsTotal") is Intent.QUESTION


def test_a_long_message_is_not_a_pleasantry() -> None:
    long_thanks = "thanks " * 20
    assert classify_intent(long_thanks) is Intent.QUESTION


# -------------------------------------------------------------------- replies


@pytest.mark.parametrize(
    "intent", [Intent.GREETING, Intent.THANKS, Intent.FAREWELL, Intent.HELP]
)
def test_replies_name_the_file_when_known(intent: Intent) -> None:
    assert "`sales.cbl`" in conversational_reply(intent, "sales.cbl")


@pytest.mark.parametrize(
    "intent", [Intent.GREETING, Intent.THANKS, Intent.FAREWELL, Intent.HELP]
)
def test_replies_without_a_file_say_this_program(intent: Intent) -> None:
    assert "this program" in conversational_reply(intent, None)


def test_replies_state_no_facts_about_the_code() -> None:
    for intent in (Intent.GREETING, Intent.THANKS, Intent.FAREWELL, Intent.HELP):
        text = conversational_reply(intent, "sales.cbl")
        assert not any(ch.isdigit() for ch in text)
        assert "WS-" not in text and "READY" not in text


def test_help_lists_what_can_be_asked() -> None:
    text = conversational_reply(Intent.HELP, "sales.cbl")
    assert text.count("\n- ") >= 4
    assert "business rules" in text


def test_a_question_has_no_conversational_reply() -> None:
    with pytest.raises(ValueError):
        conversational_reply(Intent.QUESTION, None)


# ------------------------------------------------------------ follow-up search

HISTORY = [
    ("user", "What discount does type R get?"),
    ("assistant", "10%."),
]


def test_a_short_follow_up_is_searched_with_the_previous_question() -> None:
    assert (
        retrieval_query("and for type B?", HISTORY)
        == "What discount does type R get? and for type B?"
    )


@pytest.mark.parametrize(
    "follow_up", ["why?", "what about B", "how about tax", "also the limit"]
)
def test_other_follow_up_shapes(follow_up: str) -> None:
    assert retrieval_query(follow_up, HISTORY).startswith(
        "What discount does type R get?"
    )


def test_a_self_contained_question_is_searched_as_written() -> None:
    question = "What is the tax rate applied to every order in the program?"
    assert retrieval_query(question, HISTORY) == question


def test_no_history_means_no_change() -> None:
    assert retrieval_query("and for type B?", []) == "and for type B?"


def test_a_greeting_is_not_used_as_the_previous_question() -> None:
    history = [
        ("user", "What discount does type R get?"),
        ("user", "thanks"),
        ("assistant", "Glad!"),
    ]
    assert retrieval_query("and B?", history).startswith(
        "What discount does type R get?"
    )
    only_greeting = [("user", "hi"), ("assistant", "Hi!")]
    assert retrieval_query("and B?", only_greeting) == "and B?"


def test_only_user_turns_are_used() -> None:
    assert (
        retrieval_query("and B?", [("assistant", "Something long and detailed.")])
        == "and B?"
    )


# -------------------------------------------------------------- broad questions


@pytest.mark.parametrize(
    "question",
    [
        "List the business rules in this program",
        "what are all the fields",
        "show me every paragraph",
        "Walk me through what happens when an order is processed",
        "explain it step by step",
        "analyze the converted java code",
        "Explain what this program does",
        "How does the program work?",
        "give me an overview",
        "summarize the program",
        "Which paragraphs are performed by main?",
    ],
)
def test_broad_questions_want_more_context(question: str) -> None:
    assert wants_broad_context(question)


@pytest.mark.parametrize(
    "question",
    [
        "What is the tax rate?",
        "At what order total does the status become HIGH VALUE?",
        "what discount does type R get?",
        "and for type B?",
        "When is the zero warning shown?",
        "What does WS-STATUS hold?",
    ],
)
def test_specific_questions_do_not(question: str) -> None:
    assert not wants_broad_context(question)
