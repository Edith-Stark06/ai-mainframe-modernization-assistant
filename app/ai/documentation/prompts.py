"""
Documentation Prompts

Deterministic prompt builders for COBOL code documentation.
"""

from typing import Any, Optional


def _serialize_context_value(val: Any) -> str:
    """Deterministically serialize a context value without memory addresses."""
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float, bool, type(None))):
        return str(val)
    if isinstance(val, dict):
        parts = []
        for k in sorted(val.keys(), key=str):
            parts.append(f"{k}: {_serialize_context_value(val[k])}")
        return "{" + ", ".join(parts) + "}"
    if isinstance(val, (set, frozenset)):
        parts = [_serialize_context_value(item) for item in val]
        return "{" + ", ".join(sorted(parts)) + "}"
    if isinstance(val, (list, tuple)):
        parts = [_serialize_context_value(item) for item in val]
        return "[" + ", ".join(parts) + "]"

    if hasattr(val, "model_dump") and callable(val.model_dump):
        return _serialize_context_value(val.model_dump())
    if hasattr(val, "dict") and callable(val.dict):
        return _serialize_context_value(val.dict())
    if hasattr(val, "__dict__"):
        return _serialize_context_value(vars(val))
    if hasattr(val, "__slots__"):
        d = {k: getattr(val, k) for k in getattr(val, "__slots__") if hasattr(val, k)}
        return _serialize_context_value(d)

    # Fallback to a deterministic class identifier for unsupported objects
    # to avoid leaking memory addresses via default str() or repr()
    return f"<{type(val).__module__}.{type(val).__qualname__}>"


def _serialize_collection(collection: Any) -> list[str]:
    """Serialize a collection into a deterministic list of strings."""
    if isinstance(collection, (set, frozenset)):
        return sorted(_serialize_context_value(item) for item in collection)
    if isinstance(collection, dict):
        return sorted(
            f"{k}: {_serialize_context_value(v)}" for k, v in collection.items()
        )
    if isinstance(collection, (list, tuple)):
        return [_serialize_context_value(item) for item in collection]
    return [_serialize_context_value(collection)]


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
        for dep_str in _serialize_collection(ctx["dependencies"]):
            prompt_parts.append(f"- {dep_str}")
        prompt_parts.append("====================\n")

    if "business_rules" in ctx:
        prompt_parts.append("=== BUSINESS RULES ===")
        for rule_str in _serialize_collection(ctx["business_rules"]):
            prompt_parts.append(rule_str)
        prompt_parts.append("====================\n")

    if "diagnostics" in ctx:
        prompt_parts.append("=== DIAGNOSTICS ===")
        for diag_str in _serialize_collection(ctx["diagnostics"]):
            prompt_parts.append(diag_str)
        prompt_parts.append("====================\n")

    if "analysis_metadata" in ctx:
        prompt_parts.append("=== ANALYSIS METADATA ===")
        for meta_str in _serialize_collection(ctx["analysis_metadata"]):
            prompt_parts.append(meta_str)
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
