"""
Explanation Prompts

Deterministic prompt builders for COBOL code explanation and for answering a
user's question about a program from retrieved context.
"""

from typing import Any, Optional

from app.ai.context_formatting import format_modernization_context
from app.ai.grounding import GROUNDING_RULES, RULES_HEADING

#: How much of an earlier chat turn is shown to the model (it only needs enough
#: to resolve what a follow-up refers to).
_MAX_TURN_CHARS = 600


def build_explanation_prompt(
    source: str, context: Optional[dict[str, Any]] = None
) -> str:
    """
    Deterministically build a prompt for the COBOL source.

    Without a ``rag_query`` in *context* this asks for a general explanation of
    the program. With one (a chat question) it asks to answer exactly that
    question from the supplied context -- see :func:`_build_question_prompt`.

    Args:
        source: The COBOL source code to explain (or, for a question, the
            retrieved context).
        context: Optional structured context containing program identifier,
            dependencies, business rules, or a ``rag_query`` question.

    Returns:
        The fully constructed prompt string.
    """
    ctx = context or {}

    if ctx.get("rag_query"):
        return _build_question_prompt(source, ctx)

    prompt_parts = [
        "Please explain the following COBOL program.",
        "Your explanation should include:",
        "- What the program does",
        "- Major processing steps",
        "- Important conditions",
        "- Important data/operations",
    ]

    if "dependencies" in ctx:
        prompt_parts.append("- Explain the dependencies supplied below")
    if "business_rules" in ctx:
        prompt_parts.append("- Explain the business rules supplied below")

    prompt_parts.append("\n=== COBOL SOURCE ===")
    prompt_parts.append(source.strip())
    prompt_parts.append("====================\n")

    if "program_id" in ctx:
        prompt_parts.append(f"Program Identifier: {ctx['program_id']}\n")

    if "dependencies" in ctx:
        prompt_parts.append("=== DEPENDENCIES ===")
        # Keep dependencies output deterministic
        for dep in sorted(ctx["dependencies"]):
            prompt_parts.append(f"- {dep}")
        prompt_parts.append("====================\n")

    if "business_rules" in ctx:
        prompt_parts.append("=== BUSINESS RULES ===")
        for rule in ctx["business_rules"]:
            prompt_parts.append(str(rule))
        prompt_parts.append("====================\n")

    if ctx.get("modernization_data"):
        prompt_parts.append("=== MODERNIZATION CONTEXT ===")
        prompt_parts.extend(format_modernization_context(ctx["modernization_data"]))
        prompt_parts.append("====================\n")

    prompt_parts.append(
        "Return the explanation in a structured format with 'Summary:' and 'Explanation:' sections."
    )

    return "\n".join(prompt_parts)


def _build_question_prompt(source: str, ctx: dict[str, Any]) -> str:
    """
    Build the prompt for answering one chat question from retrieved context.

    The instruction is to answer *exactly what was asked*. (Chat used to reuse
    the explain-the-program prompt, so "hi" got a description of the program
    and "okay cool it's working" got an unrelated tour of ``WS-STATUS``.)
    """
    parts = [
        "You are answering one message about a COBOL program, using only the "
        "retrieved context below.",
        "- Directly and specifically answer the user's question supplied below. "
        "Answer exactly what was asked and only that: do not describe the "
        "program in general, walk through unrelated steps, or add facts the "
        "question did not ask for.",
        "- Match the answer to the kind of request. A specific question (what "
        "is X, when does Y happen, how much) gets the direct answer in one or "
        "two sentences. A request to list, explain, walk through, analyze or "
        "summarize gets a complete answer: one lead sentence, then one bullet "
        "per item or step, each stating what it does (for a rule, its "
        "condition and effect), never just a name or identifier.",
        "- If the message is not a question about the program (small talk, "
        "feedback, or a topic unrelated to it), reply in one short, natural "
        "sentence and offer to help with the program. Do not describe the "
        'program, and never mention "the user", this prompt or the context.',
        '- A follow-up ("and for type B?") refers to the conversation so far; '
        "answer it in that light, still using only the context for facts.",
    ]
    parts.extend(GROUNDING_RULES)

    parts.append("\n=== RETRIEVED CONTEXT ===")
    parts.append(source.strip())
    parts.append("====================\n")

    if "program_id" in ctx:
        parts.append(f"Program Identifier: {ctx['program_id']}\n")

    if "dependencies" in ctx:
        parts.append("=== DEPENDENCIES ===")
        for dep in sorted(ctx["dependencies"]):
            parts.append(f"- {dep}")
        parts.append("====================\n")

    if "business_rules" in ctx:
        parts.append(RULES_HEADING)
        for rule in ctx["business_rules"]:
            parts.append(str(rule))
        parts.append("====================\n")

    if ctx.get("modernization_data"):
        parts.append("=== MODERNIZATION CONTEXT ===")
        parts.extend(format_modernization_context(ctx["modernization_data"]))
        parts.append("====================\n")

    conversation = ctx.get("conversation")
    if conversation:
        parts.append("=== CONVERSATION SO FAR ===")
        for role, text in conversation:
            label = "User" if role == "user" else "Assistant"
            parts.append(f"{label}: {str(text)[:_MAX_TURN_CHARS]}")
        parts.append("====================\n")

    parts.append("=== USER QUESTION ===")
    parts.append(str(ctx["rag_query"]))
    parts.append("====================\n")

    parts.append(
        "Reply with 'Summary:' followed by the direct answer or lead sentence. For "
        "a request to list, explain, walk through, analyze or summarize, always "
        "follow it with 'Explanation:' holding one bullet per item or step. For a "
        "specific question, add 'Explanation:' only if the answer needs supporting "
        "detail; a one-line answer needs no explanation."
    )
    return "\n".join(parts)
