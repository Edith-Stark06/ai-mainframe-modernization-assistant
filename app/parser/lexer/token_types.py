"""
Token Type Enumeration.

Purpose:
    Enumerate the complete set of terminal symbol categories recognised
    by the COBOL lexer.  This enumeration is the authoritative source
    of truth for every token classification decision made during lexical
    analysis, parsing, and semantic analysis.

Responsibilities:
    - Provide a closed, exhaustive set of token categories.
    - Remain stable across lexer implementations so that parser and
      semantic layers can be written against a fixed vocabulary.
    - Represent only structural / syntactic token families at this
      foundation milestone; COBOL-specific keyword variants will be
      added in subsequent tasks.

Dependencies:
    - Python standard library only (``enum``).

Examples:
    Checking whether a token is a numeric literal::

        from app.parser.lexer.token_types import TokenType

        token_type = TokenType.NUMBER
        assert token_type is TokenType.NUMBER
        print(token_type.value)
        # number

    Iterating over all defined token types::

        for tt in TokenType:
            print(tt.name, tt.value)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from enum import Enum, unique

__all__ = ["TokenType"]


@unique
class TokenType(Enum):
    """
    Enumeration of all recognised COBOL token categories.

    Each member maps a symbolic name to a lowercase string value.
    The string value is used for serialisation (e.g. JSON API
    responses, diagnostic messages) while the member identity is
    used for all internal comparisons.

    Members:
        IDENTIFIER:
            A user-defined name: program names, data names, paragraph
            names, section names, and COPY-book member identifiers.
        KEYWORD:
            A reserved COBOL word (e.g. ``IDENTIFICATION``, ``MOVE``,
            ``PERFORM``).  The precise keyword set is established by
            the lexer; this category simply marks that classification.
        STRING:
            A quoted alphanumeric literal, delimited by single or
            double quotation marks depending on the source dialect.
        NUMBER:
            A numeric literal, including integer and fixed-point forms
            (e.g. ``42``, ``3.14``, ``-0.001``).
        LEVEL_NUMBER:
            A data-division level indicator (``01``–``49``, ``66``,
            ``77``, ``78``, ``88``).
        PIC:
            The ``PIC`` or ``PICTURE`` keyword and its immediately
            following picture clause string, treated as a single
            logical unit by the lexer.
        PERIOD:
            A full stop (```.```) used as a COBOL statement terminator.
        COMMA:
            A comma (``,``) used as a separator between operands.
        LPAREN:
            A left parenthesis (``(``), used in subscripts and
            reference modification.
        RPAREN:
            A right parenthesis (``)``) closing a subscript or
            reference modification expression.
        EOF:
            A sentinel token injected at the end of the token stream
            to simplify parser termination logic.
        UNKNOWN:
            A character sequence that could not be classified by the
            lexer.  Treated as a recoverable error.

    Examples:
        >>> TokenType.IDENTIFIER.value
        'identifier'
        >>> TokenType.EOF.value
        'eof'
        >>> TokenType["NUMBER"] is TokenType.NUMBER
        True
    """

    IDENTIFIER = "identifier"
    KEYWORD = "keyword"
    STRING = "string"
    NUMBER = "number"
    LEVEL_NUMBER = "level_number"
    PIC = "pic"
    PERIOD = "period"
    COMMA = "comma"
    LPAREN = "lparen"
    RPAREN = "rparen"
    EOF = "eof"
    UNKNOWN = "unknown"
