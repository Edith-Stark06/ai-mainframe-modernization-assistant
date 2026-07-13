"""
COBOL Lexer Sub-package.

Purpose:
    Expose the shared immutable models and structural contracts that
    form the foundation of the COBOL lexical analysis layer.  This
    sub-package is the single import boundary between the lexer
    foundation and all downstream compiler stages.

Responsibilities:
    - Re-export :class:`Position`, :class:`Token`, :class:`TokenType`,
      and :class:`ILexer` so that callers need only import from
      ``app.parser.lexer``.
    - Own no scanning, regex, or COBOL-specific knowledge at this
      milestone; those concerns belong in :mod:`app.parser.lexer.lexer`
      which is implemented in a subsequent task.

Dependencies:
    - :mod:`app.parser.lexer.position`    — ``Position`` value type.
    - :mod:`app.parser.lexer.token`       — ``Token`` value type.
    - :mod:`app.parser.lexer.token_types` — ``TokenType`` enumeration.
    - :mod:`app.parser.lexer.interfaces`  — ``ILexer`` protocol.

Examples:
    Importing the public API::

        from app.parser.lexer import ILexer, Position, Token, TokenType

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from app.parser.lexer.interfaces import ILexer
from app.parser.lexer.position import Position
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType

__all__ = [
    "ILexer",
    "Position",
    "Token",
    "TokenType",
]
