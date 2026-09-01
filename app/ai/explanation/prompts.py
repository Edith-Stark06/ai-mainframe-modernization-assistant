"""
Explanation Prompts

Deterministic prompt builders for COBOL code explanation.
"""

from typing import Any, Optional

from app.ai.context_formatting import format_modernization_context


def build_explanation_prompt(
    source: str, context: Optional[dict[str, Any]] = None
) -> str:
    """
    Deterministically build a prompt requesting explanation of the COBOL source.

    Args:
        source: The COBOL source code to explain.
        context: Optional structured context containing program identifier,
            dependencies, or business rules.

    Returns:
        The fully constructed prompt string.
    """
    prompt_parts = [
        "Please explain the following COBOL program.",
        "Your explanation should include:",
        "- What the program does",
        "- Major processing steps",
        "- Important conditions",
        "- Important data/operations",
    ]

    ctx = context or {}

    if "dependencies" in ctx:
        prompt_parts.append("- Explain the dependencies supplied below")
    if "business_rules" in ctx:
        prompt_parts.append("- Explain the business rules supplied below")
    if ctx.get("rag_query"):
        prompt_parts.append(
            "- Directly and specifically answer the user's question supplied below"
        )

    prompt_parts.append("\n=== COBOL SOURCE ===")
    prompt_parts.append(source.strip())
    prompt_parts.append("====================\n")

    if "program_id" in ctx:
        prompt_parts.append(f"Program Identifier: {ctx['program_id']}\n")

    if ctx.get("rag_query"):
        prompt_parts.append("=== USER QUESTION ===")
        prompt_parts.append(str(ctx["rag_query"]))
        prompt_parts.append("====================\n")

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
