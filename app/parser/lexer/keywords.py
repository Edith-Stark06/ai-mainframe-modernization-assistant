"""
COBOL Reserved Keyword Set.

Purpose:
    Provide the authoritative set of COBOL reserved words recognised by
    the :class:`~app.parser.lexer.lexer.CobolLexer` at this milestone.
    Centralising the keyword list here decouples it from the lexer
    implementation so it can evolve independently.

Responsibilities:
    - Expose :data:`KEYWORDS` — a frozenset of uppercase reserved words.
    - Provide :func:`is_keyword` for O(1) membership testing.

Non-responsibilities:
    - Lexical scanning, token creation, or parsing logic.

Dependencies:
    - Python standard library only.

Examples:
    Checking membership::

        from app.parser.lexer.keywords import is_keyword

        is_keyword("MOVE")        # True
        is_keyword("CUSTOMER")    # False
        is_keyword("move")        # False  (case-sensitive)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

__all__ = ["KEYWORDS", "is_keyword"]

# ---------------------------------------------------------------------------
# The canonical set of COBOL reserved words for milestone Task-010.
# All entries are uppercase strings; the lexer normalises identifiers to
# uppercase before testing membership.
# ---------------------------------------------------------------------------
KEYWORDS: frozenset[str] = frozenset(
    {
        "ACCEPT",
        "ADD",
        "CALL",
        "COMPUTE",
        "DATA",
        "DISPLAY",
        "DIVIDE",
        "DIVISION",
        "ELSE",
        "END-IF",
        "ENVIRONMENT",
        "IDENTIFICATION",
        "IF",
        "MOVE",
        "MULTIPLY",
        "PERFORM",
        "PIC",
        "PROCEDURE",
        "PROGRAM-ID",
        "RUN",
        "STOP",
        "SUBTRACT",
        "VALUE",
        "WORKING-STORAGE",
        "ZEROS",
        "SPACES",
    }
)


def is_keyword(word: str) -> bool:
    """
    Return ``True`` if *word* is a COBOL reserved keyword.

    Comparison is case-sensitive; COBOL keywords are always stored in
    uppercase.  The lexer is responsible for uppercasing the candidate
    word before calling this function.

    Args:
        word: The candidate word to test, expected in uppercase.

    Returns:
        ``True`` if *word* is in :data:`KEYWORDS`, ``False`` otherwise.

    Examples:
        >>> is_keyword("MOVE")
        True
        >>> is_keyword("move")
        False
        >>> is_keyword("CUSTOMER-NAME")
        False
    """
    return word in KEYWORDS
