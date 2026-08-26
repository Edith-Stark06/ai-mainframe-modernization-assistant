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

            normalized_parts: list[str] = []
            prev_token = None

            for token in tokens:
                if token.type == TokenType.EOF:
                    continue

                lexeme = (
                    token.lexeme
                    if token.type == TokenType.STRING
                    else token.lexeme.upper()
                )

                # Check if we should glue this token to the previous one
                glue = False
                if prev_token:
                    # Check if they were adjacent in the original source
                    adjacent = token.position.offset == (
                        prev_token.position.offset + len(prev_token.lexeme)
                    )

                    if adjacent:
                        if (
                            prev_token.type == TokenType.NUMBER
                            and token.type == TokenType.PERIOD
                        ):
                            glue = True
                        elif (
                            prev_token.type == TokenType.PERIOD
                            and token.type == TokenType.NUMBER
                        ):
                            glue = True

                if glue:
                    normalized_parts[-1] += lexeme
                else:
                    normalized_parts.append(lexeme)

                prev_token = token

            return " ".join(normalized_parts)
        except LexerError:
            # Fallback for unsupported or invalid syntax
            # Preserve quoted/string literal content while safely upper-casing the rest.
            result = []
            in_quote = None
            for char in s:
                if in_quote:
                    result.append(char)
                    if char == in_quote:
                        in_quote = None
                else:
                    if char in ("'", '"'):
                        in_quote = char
                        result.append(char)
                    else:
                        result.append(char.upper())
            return " ".join("".join(result).split())

    return BusinessRule(
        condition=_normalize_string(rule.condition),
        actions=tuple(_normalize_string(a) for a in rule.actions),
        source_location=rule.source_location,
    )
