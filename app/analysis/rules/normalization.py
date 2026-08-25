"""
Business Rule Normalization.

Purpose:
    Normalizes BusinessRule expressions into a canonical string representation
    while preserving exact token semantics.
"""

from app.analysis.rules.models import BusinessRule
from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.token_types import TokenType
from app.parser.lexer.lexer_exceptions import LexerError


def normalize_business_rule(rule: BusinessRule) -> BusinessRule:
    """
    Return a new BusinessRule with its condition and actions normalized
    to a canonical string representation.

    Semantic meaning and source locations are preserved.
    """

    def _normalize_string(s: str) -> str:
        s = s.strip()
        if not s:
            return s

        try:
            lexer = CobolLexer()
            tokens = lexer.tokenize(s, filename="")

            normalized_parts = []
            for token in tokens:
                if token.type == TokenType.EOF:
                    continue

                if token.type == TokenType.STRING:
                    normalized_parts.append(token.lexeme)
                else:
                    normalized_parts.append(token.lexeme.upper())

            return " ".join(normalized_parts)
        except LexerError:
            # Fallback for unsupported or invalid syntax
            parts = s.split()
            return " ".join(parts).upper()

    return BusinessRule(
        condition=_normalize_string(rule.condition),
        actions=tuple(_normalize_string(a) for a in rule.actions),
        source_location=rule.source_location,
    )
