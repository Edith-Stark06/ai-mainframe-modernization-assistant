"""
Documentation Prompts

Deterministic prompt builders for COBOL code documentation.
"""

from typing import Any, Optional


def build_documentation_prompt(
    source: str, context: Optional[dict[str, Any]] = None
) -> str:
    """
    Deterministically build a prompt requesting technical documentation for the COBOL source.

    Args:
        source: The COBOL source code to document.
        context: Optional structured context containing program identifier,
            dependencies, business rules, diagnostics, or analysis metadata.

    Returns:
        The fully constructed prompt string.
    """
    prompt_parts = [
        "Please generate technical documentation for the following COBOL program.",
        "Your documentation should explain, where applicable:",
        "- Program purpose",
        "- Major processing flow",
        "- Important data operations",
        "- Conditions and business rules",
        "- Dependencies",
        "- Significant paragraphs/sections",
    ]

    ctx = context or {}

    if "diagnostics" in ctx:
        prompt_parts.append("- Diagnostics or limitations supplied below")

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

    if "diagnostics" in ctx:
        prompt_parts.append("=== DIAGNOSTICS ===")
        for diag in ctx["diagnostics"]:
            prompt_parts.append(str(diag))
        prompt_parts.append("====================\n")

    if "analysis_metadata" in ctx:
        prompt_parts.append("=== ANALYSIS METADATA ===")
        for key, value in sorted(ctx["analysis_metadata"].items()):
            prompt_parts.append(f"{key}: {value}")
        prompt_parts.append("====================\n")

    prompt_parts.append(
        "Return the documentation in the following structured format exactly:\n"
        "Title:\n"
        "<title>\n\n"
        "Overview:\n"
        "<overview>\n\n"
        "Section:\n"
        "<heading>\n"
        "<content>\n\n"
        "(Add as many sections as needed)"
    )

    return "\n".join(prompt_parts)
