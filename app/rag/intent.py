"""
Chat Intent Detection.

Purpose:
    Decide, before any retrieval or model call, whether a chat message is a
    *question about the program* or just conversation ("hi", "thanks, that
    works", "bye", "what can you do?"). Treating every message as a code
    question made the assistant describe the program in reply to "hi" and
    invent relevance for "okay cool it's working good". Conversational
    messages now get a short, fitting reply instantly; only real questions go
    through retrieval and the model.

Responsibilities:
    - :func:`classify_intent` -- deterministic, rule-based classification.
    - :func:`conversational_reply` -- the reply for a non-question intent.
    - :func:`retrieval_query` -- expand a short follow-up with the previous
      question so retrieval can find what it refers to.

Non-responsibilities:
    - Answering questions (see :mod:`app.rag.orchestration.service`).

Design note:
    Rules, not a model: the result is instant, free, repeatable and testable.
    The rules are deliberately conservative -- when a message contains any
    question word, a question mark, a code-looking token or a request verb it is
    a question, so a real question is never swallowed by a pleasantry.

Dependencies:
    - re, enum (standard library)

Examples:
    >>> classify_intent("hi there")
    <Intent.GREETING: 'greeting'>
    >>> classify_intent("thanks, what is the tax rate?")
    <Intent.QUESTION: 'question'>

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Sequence
from enum import Enum

__all__ = [
    "Intent",
    "classify_intent",
    "conversational_reply",
    "retrieval_query",
    "wants_broad_context",
    "wants_validation_context",
]


class Intent(str, Enum):
    """What a chat message is for."""

    GREETING = "greeting"
    THANKS = "thanks"
    FAREWELL = "farewell"
    HELP = "help"
    QUESTION = "question"


_WORD = re.compile(r"[a-z']+")

#: Any of these makes a message a question or a request, never a pleasantry.
_REQUEST_WORDS = frozenset("""
    what whats when where which who whom whose why how explain describe list show
    tell analyze analyse summarize summarise walk find give compare trace identify
    check verify calculate convert generate write document define display print
    rules rule program code java cobol paragraph field variable risk risks
    """.split())

_GREETING_WORDS = frozenset("""
    hi hii hello hey heya hiya hola yo greetings howdy sup morning afternoon
    evening namaste
    """.split())
#: Filler that may follow a greeting without making it a question.
_GREETING_FILLER = frozenset("""
    there bot assistant everyone all team again good how are you doing u r
    today is it going whats up buddy friend mate
    """.split())
_TIME_GREETING = re.compile(r"^\W*good (morning|afternoon|evening|day)\b")
_PLEASANTRY = re.compile(
    r"\b(how are you|how r u|how('s| is) it going|what'?s up|sup|how do you do)\b"
)

_ACK_WORDS = frozenset("""
    thanks thank thx ty cheers appreciate appreciated cool great nice awesome
    perfect good excellent wonderful amazing fine ok okay okey got understood
    works working worked helpful brilliant fantastic sweet noted alright wow
    super love loved clear makes sense fair enough
    """.split())

#: Words that may accompany an acknowledgement without adding content.
_ACK_FILLER = frozenset("""
    its it is was a an the so very really much lot lots that this all you your
    for help helps answer answers response job one thing things now just pretty
    quite too also again and but i im me my we ya bro man dude yes yeah yep sure
    to be been been being are were am as of on in with
    """.split())

_FAREWELL = re.compile(
    r"\b(bye|goodbye|good ?night|see (you|ya)|cya|talk (to you )?later|that'?s all|"
    r"that is all|nothing else|i'?m done|im done|take care)\b"
)

_HELP = re.compile(
    r"^\W*(help|help me|what can you do|what do you do|what can i ask( you)?|"
    r"what (can|could) you (help|assist)( me)? with|who are you|what are you|"
    r"how (do|does) (i|this|you|it) (use|work)( this| you| it)?|how can you help( me)?|"
    r"what are your capabilities|capabilities|commands|usage)\W*$"
)

# A code-looking token: WS-TOTAL, 50000, 0.18, wsTotal, PIC9.
_CODE_TOKEN = re.compile(r"[A-Za-z]+-[A-Za-z0-9-]+|\d|[a-z]+[A-Z][A-Za-z]*")

_MAX_PLEASANTRY_WORDS = 12

# Words that signal a follow-up that cannot be searched on its own.
_FOLLOW_UP_START = re.compile(
    r"^\W*(and|also|then|what about|how about|what if|why|how so|and for|"
    r"same for|what of|but)\b"
)
_FOLLOW_UP_MAX_WORDS = 6


#: A request that needs the *whole picture* rather than one fact: a set ("list
#: the rules", "all the fields", "every paragraph") or a flow ("walk me
#: through", "step by step", "analyze", "overview", "explain the program"). The
#: answer is spread over many chunks, so the best few are not enough.
_BROAD = re.compile(
    r"\b("
    r"list|enumerate|all|every|each|what are (the|all)|which .{0,40}\b(are|exist)|"
    r"walk (me )?through|step[- ]by[- ]step|end[- ]to[- ]end|overview|"
    r"analy[sz]e|summari[sz]e|"
    r"(explain|describe) (what|how) (this|the|that)\b.{0,30}(program|code|does|works)|"
    r"how does (this|the) (program|code|java|application) work"
    r")\b",
    re.IGNORECASE,
)


#: Words that make a question about the validation / compilation / test results
#: of the converted Java rather than about the program's own code.
_VALIDATION = re.compile(
    r"\b("
    r"validat\w*|compil\w*|javac|build|builds|"
    r"tests?|testing|unit[- ]tests?|coverage|"
    r"equivalen\w*|behaviou?ral|self[- ]repair|"
    r"unsupported (syntax|constructs?)|"
    r"verified|verification|confidence|"
    r"ready (to|for)|production[- ]ready|"
    r"(did|does|do|has|have|will|would) (it|this|the (java|code|program|conversion)) (pass|fail|work|run)"
    r")\b",
    re.IGNORECASE,
)


def wants_validation_context(question: str) -> bool:
    """
    ``True`` if *question* is about the validation results of the converted
    Java (compilation, tests, coverage, equivalence, readiness).

    Those results are not part of the searchable code, so the chat adds them
    as evidence when this is true. A false positive costs only an extra
    evidence item, so the pattern errs toward matching.

    Args:
        question: The user's question.

    Returns:
        Whether to attach the Validation Center results.
    """
    return bool(_VALIDATION.search(question))


def wants_broad_context(question: str) -> bool:
    """
    ``True`` if *question* needs many chunks rather than the best few.

    Args:
        question: The user's question.

    Returns:
        Whether retrieval should fetch more chunks than for a specific lookup
        (the router raises ``top_k`` for these).
    """
    return bool(_BROAD.search(question))


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _ack_like(word: str) -> bool:
    """An acknowledgement word, tolerating a typo ("wokring" -> "working")."""
    if word in _ACK_WORDS:
        return True
    return len(word) >= 4 and bool(
        difflib.get_close_matches(word, _ACK_WORDS, n=1, cutoff=0.8)
    )


def classify_intent(message: str) -> Intent:
    """
    Classify a chat message.

    Args:
        message: What the user typed.

    Returns:
        :attr:`Intent.QUESTION` unless the message is clearly a greeting,
        thanks/acknowledgement, farewell, or request for help. Anything
        containing a question mark, a question/request word, or a
        code-looking token is a question.
    """
    text = message.strip()
    lowered = text.lower()
    if not text:
        return Intent.QUESTION

    if _HELP.match(lowered):
        return Intent.HELP

    words = _words(text)
    has_question_mark = "?" in text
    has_request = any(w in _REQUEST_WORDS for w in words)
    has_code = bool(_CODE_TOKEN.search(text))

    # A pleasantry such as "how are you" contains a question word on purpose.
    if (
        _PLEASANTRY.search(lowered)
        and len(words) <= _MAX_PLEASANTRY_WORDS
        and not has_code
    ):
        return Intent.GREETING

    if has_request or has_code:
        return Intent.QUESTION

    if _FAREWELL.search(lowered) and len(words) <= _MAX_PLEASANTRY_WORDS:
        return Intent.FAREWELL

    if _TIME_GREETING.match(lowered) and len(words) <= 6:
        return Intent.GREETING

    if words and words[0] in _GREETING_WORDS and len(words) <= 6:
        if all(w in _GREETING_WORDS or w in _GREETING_FILLER for w in words):
            return Intent.GREETING

    if has_question_mark:
        return Intent.QUESTION

    # Thanks / acknowledgement: short, at least one real ack word, and *every*
    # word is an ack word or filler -- so "this tax rate looks good", which says
    # something about the program, stays a question.
    if (
        words
        and len(words) <= _MAX_PLEASANTRY_WORDS
        and all(_ack_like(w) or w in _ACK_FILLER for w in words)
        and any(_ack_like(w) for w in words)
    ):
        return Intent.THANKS

    return Intent.QUESTION


_EXAMPLES = (
    "what the program does",
    "which business rules it applies",
    "what a specific field, paragraph or condition does",
    "how the converted Java works",
    "whether the converted Java compiles and passes validation",
    "what the modernization risks are",
)


def conversational_reply(intent: Intent, filename: str | None = None) -> str:
    """
    The reply to a non-question message.

    Args:
        intent: A conversational intent (not :attr:`Intent.QUESTION`).
        filename: The file being discussed, if any.

    Returns:
        Short markdown text. Mentions no program facts: none were retrieved,
        so none may be stated.

    Raises:
        ValueError: *intent* is :attr:`Intent.QUESTION`.
    """
    subject = f"`{filename}`" if filename else "this program"
    if intent is Intent.GREETING:
        return (
            f"Hi! I can answer questions about {subject}. Ask what it does, which "
            "business rules it applies, or what a particular field or paragraph does."
        )
    if intent is Intent.THANKS:
        return (
            f"Glad that helps! Ask me anything else about {subject} whenever you like."
        )
    if intent is Intent.FAREWELL:
        return f"Goodbye! Come back any time you have more questions about {subject}."
    if intent is Intent.HELP:
        lines = [
            f"I answer questions about {subject}, using the analysis of its code. For example:"
        ]
        lines += [f"- {example}" for example in _EXAMPLES]
        lines.append(
            "Ask a specific question and you get a specific answer, with numbered "
            "references to the evidence."
        )
        return "\n".join(lines)
    raise ValueError("conversational_reply is only for non-question intents")


def retrieval_query(question: str, history: Sequence[tuple[str, str]] = ()) -> str:
    """
    The text to search with for *question*.

    A short follow-up ("and for type B?", "why?") means nothing on its own, so
    it is searched together with the previous user question. Any other
    question is searched as written.

    Args:
        question: The current question.
        history: Earlier ``(role, text)`` turns, oldest first.

    Returns:
        *question*, or the previous user question followed by *question*.
    """
    previous = next(
        (
            text
            for role, text in reversed(history)
            if role == "user" and classify_intent(text) is Intent.QUESTION
        ),
        "",
    )
    if not previous:
        return question
    words = _words(question)
    if len(words) <= _FOLLOW_UP_MAX_WORDS or _FOLLOW_UP_START.match(question.lower()):
        return f"{previous.strip()} {question.strip()}"
    return question
