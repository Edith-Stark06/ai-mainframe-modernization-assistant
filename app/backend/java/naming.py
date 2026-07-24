"""
Java Field Name Converter.

Purpose:
    Convert COBOL data-item names (e.g. ``WS-COUNT``, ``CUSTOMER-NAME``) into
    valid lowerCamelCase Java field identifiers.

Responsibilities:
    - Split COBOL names on hyphens and underscores.
    - Lowercase the first segment; capitalise subsequent segments (lowerCamelCase).
    - Strip characters that are not legal in Java identifiers.
    - Prepend ``"f"`` if the result starts with a digit.
    - Return ``"field"`` if the sanitised result is empty.

Non-responsibilities:
    - Class name derivation (handled by :func:`~app.backend.java.generator._to_java_class_name`).
    - Type mapping.
    - Field value formatting.

Examples:
    >>> from app.backend.java.naming import to_java_field_name
    >>> to_java_field_name("WS-COUNT")
    'wsCount'
    >>> to_java_field_name("CUSTOMER-NAME")
    'customerName'
    >>> to_java_field_name("EMPLOYEE-ID")
    'employeeId'

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re

__all__ = ["to_java_field_name"]


def to_java_field_name(cobol_name: str) -> str:
    """
    Convert *cobol_name* to a lowerCamelCase Java field identifier.

    Args:
        cobol_name:
            A COBOL data-item name such as ``"WS-COUNT"`` or
            ``"CUSTOMER-NAME"``.

    Returns:
        A non-empty string that is a valid Java identifier in lowerCamelCase.

    Examples:
        >>> to_java_field_name("WS-COUNT")
        'wsCount'
        >>> to_java_field_name("CUSTOMER-NAME")
        'customerName'
        >>> to_java_field_name("")
        'field'
        >>> to_java_field_name("1INVALID")
        'f1Invalid'
    """
    if not cobol_name or not cobol_name.strip():
        return "field"

    # Split on hyphens and underscores (COBOL naming conventions)
    segments = re.split(r"[-_]+", cobol_name.strip())
    segments = [s for s in segments if s]

    if not segments:
        return "field"

    # First segment → lowercase; subsequent segments → capitalised
    parts: list[str] = []
    for i, seg in enumerate(segments):
        if i == 0:
            parts.append(seg.lower())
        else:
            parts.append(seg.capitalize())

    camel = "".join(parts)

    # Strip invalid Java identifier characters
    camel = re.sub(r"[^A-Za-z0-9$_]", "", camel)

    if not camel:
        return "field"

    # Ensure it starts with a letter or underscore
    if camel[0].isdigit():
        camel = "f" + camel

    return camel
