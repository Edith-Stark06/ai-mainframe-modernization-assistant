"""
Grammar-Word Matching Predicate.

Purpose:
    Provide a single, explicit predicate for recognising a COBOL
    grammar word at a specific grammar position, independently of
    whether the lexer classified it as ``KEYWORD`` or ``IDENTIFIER``.

    The lexer's reserved-word set is deliberately small (see
    :data:`app.parser.lexer.keywords.KEYWORDS`), so most COBOL grammar
    words — ``SECTION``, ``FILE``, ``PICTURE``, ``IS``, ``REDEFINES``,
    ``OCCURS`` and many more — are emitted as
    :attr:`~app.parser.lexer.token_types.TokenType.IDENTIFIER`.  Parser
    code that gates a lexeme test behind
    ``if tok.type is TokenType.KEYWORD`` therefore contains unreachable
    branches.  Task #104 audited every such site and found six sets with
    dead members, two of them entirely dead.

Design constraint (important):
    This predicate always requires an **explicit set of permitted
    lexemes** supplied by the calling grammar rule.  It deliberately
    offers no way to ask "is this token any keyword?", because that
    would let an arbitrary user-defined data name be mistaken for
    grammar.  A data item legitimately named ``FILE`` is only a section
    header where the grammar expects a section header — the caller,
    not this module, owns that decision.

Responsibilities:
    - Answer whether a token is a word token whose uppercased lexeme is
      in a caller-supplied set.

Non-responsibilities:
    - Deciding which words are valid at which grammar position.
    - Any knowledge of COBOL grammar itself; this module holds no word
      lists of its own.

Dependencies:
    - :mod:`app.parser.lexer.token`       — ``Token``.
    - :mod:`app.parser.lexer.token_types` — ``TokenType``.
    - Python standard library only.

Examples:
    Matching a section name regardless of lexer classification::

        from app.parser.grammar_words import matches_grammar_word

        matches_grammar_word(tok, {"FILE", "LINKAGE"})

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from collections.abc import Container

from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType

__all__ = ["WORD_TOKEN_TYPES", "matches_grammar_word"]

#: Token types that can carry a COBOL word.  A grammar word may reach the
#: parser as either of these, depending only on whether it happens to be
#: in the lexer's reserved-word set.
WORD_TOKEN_TYPES: frozenset[TokenType] = frozenset(
    {
        TokenType.KEYWORD,
        TokenType.IDENTIFIER,
    }
)


def matches_grammar_word(token: Token, permitted: Container[str]) -> bool:
    """
    Return ``True`` if *token* is a word token listed in *permitted*.

    The token's type must be ``KEYWORD`` or ``IDENTIFIER``; its lexeme is
    uppercased before the membership test, matching COBOL's
    case-insensitive source rules.

    Args:
        token:
            The :class:`~app.parser.lexer.token.Token` to test.
        permitted:
            The explicit set of uppercase lexemes valid at this grammar
            position.  Callers must pass a specific set — there is
            intentionally no "any keyword" mode.

    Returns:
        ``True`` if the token is a word token whose uppercased lexeme is
        in *permitted*, ``False`` otherwise.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> from app.parser.lexer.token import Token
        >>> from app.parser.lexer.token_types import TokenType
        >>> pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        >>> tok = Token(type=TokenType.IDENTIFIER, lexeme="FILE", position=pos)
        >>> matches_grammar_word(tok, {"FILE", "LINKAGE"})
        True
        >>> matches_grammar_word(tok, {"WORKING-STORAGE"})
        False
        >>> num = Token(type=TokenType.NUMBER, lexeme="01", position=pos)
        >>> matches_grammar_word(num, {"01"})
        False
    """
    if token.type not in WORD_TOKEN_TYPES:
        return False
    return token.lexeme.upper() in permitted
