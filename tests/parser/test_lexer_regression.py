"""
COBOL Lexer Regression Tests.

Purpose:
    Guard against regressions in :class:`~app.parser.lexer.lexer.CobolLexer`
    behaviour.  Each test class targets a specific tokenisation rule that
    has historically been a source of bugs in similar lexers.

    Unlike the corpus tests (which use on-disk COBOL files), regression
    tests use inline source strings for precise, self-documenting control
    over the exact input.

Responsibilities:
    - Whitespace regression: spaces, tabs, and newlines never produce tokens.
    - Comment regression: both fixed-format (*) and free-format (*>) comments
      are completely discarded.
    - Identifier regression: hyphenated names, digit-containing names, and
      mixed-case names are handled correctly.
    - Keyword regression: every required keyword is classified as KEYWORD,
      not IDENTIFIER.
    - Punctuation regression: period, comma, lparen, rparen are classified
      to their specific types; operators go to UNKNOWN.

Non-responsibilities:
    - Parsing, AST, or semantic analysis.
    - Modifying the production lexer.

Dependencies:
    - :mod:`app.parser.lexer.lexer`            — subject under test.
    - :mod:`app.parser.lexer.lexer_exceptions` — LexerError.
    - :mod:`app.parser.lexer.token_types`      — TokenType.
    - :mod:`pytest`                            — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pytest

from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.lexer_exceptions import LexerError
from app.parser.lexer.token_types import TokenType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def lex(source: str) -> list:
    """Return token list, excluding EOF."""
    tokens = CobolLexer().tokenize(source, filename="regression.cbl")
    return [t for t in tokens if t.type is not TokenType.EOF]


def types(source: str) -> list[TokenType]:
    return [t.type for t in lex(source)]


def lexemes(source: str) -> list[str]:
    return [t.lexeme for t in lex(source)]


# ---------------------------------------------------------------------------
# Whitespace regressions
# ---------------------------------------------------------------------------


class TestWhitespaceRegressions:
    """No whitespace character ever produces a token."""

    def test_single_space_produces_no_tokens(self) -> None:
        assert lex(" ") == []

    def test_multiple_spaces_produce_no_tokens(self) -> None:
        assert lex("          ") == []

    def test_tab_produces_no_tokens(self) -> None:
        assert lex("\t") == []

    def test_mixed_whitespace_produces_no_tokens(self) -> None:
        assert lex("  \t \t  ") == []

    def test_lf_produces_no_tokens(self) -> None:
        assert lex("\n") == []

    def test_crlf_produces_no_tokens(self) -> None:
        assert lex("\r\n") == []

    def test_cr_produces_no_tokens(self) -> None:
        assert lex("\r") == []

    def test_whitespace_between_tokens_ignored(self) -> None:
        """Whitespace between tokens does not appear in the output."""
        result = lexemes("STOP   \t   RUN")
        assert result == ["STOP", "RUN"]

    def test_leading_whitespace_ignored(self) -> None:
        result = lexemes("    MOVE")
        assert result == ["MOVE"]

    def test_trailing_whitespace_ignored(self) -> None:
        result = lexemes("MOVE    ")
        assert result == ["MOVE"]

    def test_whitespace_on_multiple_lines_ignored(self) -> None:
        result = lexemes("STOP\n\n\nRUN")
        assert result == ["STOP", "RUN"]


# ---------------------------------------------------------------------------
# Comment regressions
# ---------------------------------------------------------------------------


class TestCommentRegressions:
    """Comments are completely discarded — no tokens emitted."""

    def test_fixed_format_line_comment_skipped(self) -> None:
        """A line starting with * at column 1 produces no tokens."""
        assert lex("* THIS IS A COMMENT") == []

    def test_free_format_line_comment_skipped(self) -> None:
        """A line starting with *> produces no tokens."""
        assert lex("*> THIS IS A COMMENT") == []

    def test_comment_between_code_lines_not_tokenised(self) -> None:
        result = lexemes("STOP\n* comment\nRUN")
        assert result == ["STOP", "RUN"]

    def test_inline_comment_discards_trailing_content(self) -> None:
        """Everything after *> on a line is discarded."""
        result = lexemes("MOVE A *> discard this entire tail")
        assert result == ["MOVE", "A"]
        assert "DISCARD" not in result

    def test_multiple_comment_lines_all_skipped(self) -> None:
        source = "* line 1\n* line 2\n* line 3\nSTOP RUN"
        result = lexemes(source)
        assert result == ["STOP", "RUN"]

    def test_comment_text_words_not_keywords(self) -> None:
        """Words inside a comment line must not be classified as keywords."""
        source = "* MOVE DISPLAY STOP RUN\nACCEPT A"
        kws = [t.lexeme for t in lex(source) if t.type is TokenType.KEYWORD]
        assert "ACCEPT" in kws
        assert "MOVE" not in kws
        assert "DISPLAY" not in kws

    def test_code_after_inline_comment_on_next_line(self) -> None:
        source = "MOVE A *> comment\nTO B"
        result = lexemes(source)
        assert "MOVE" in result
        assert "A" in result
        assert "TO" in result
        assert "B" in result


# ---------------------------------------------------------------------------
# Identifier regressions
# ---------------------------------------------------------------------------


class TestIdentifierRegressions:
    """User-defined names classified as IDENTIFIER, not KEYWORD."""

    def test_simple_identifier(self) -> None:
        assert types("TOTAL") == [TokenType.IDENTIFIER]
        assert lexemes("TOTAL") == ["TOTAL"]

    def test_hyphenated_identifier(self) -> None:
        assert types("CUSTOMER-NAME") == [TokenType.IDENTIFIER]
        assert lexemes("CUSTOMER-NAME") == ["CUSTOMER-NAME"]

    def test_identifier_with_leading_digits_is_number_then_id(self) -> None:
        """'01' is lexed as NUMBER; 'WS-FIELD' is an IDENTIFIER."""
        result = lexemes("01 WS-FIELD")
        assert result == ["01", "WS-FIELD"]
        tps = types("01 WS-FIELD")
        assert tps == [TokenType.NUMBER, TokenType.IDENTIFIER]

    def test_deeply_hyphenated_identifier(self) -> None:
        assert types("EMPLOYEE-GROSS-PAY-AMOUNT") == [TokenType.IDENTIFIER]

    def test_mixed_case_identifier_uppercased(self) -> None:
        assert lexemes("customer-name") == ["CUSTOMER-NAME"]

    def test_identifier_not_classified_as_keyword(self) -> None:
        """Identifiers that share a prefix with a keyword are still IDENTIFIER."""
        # 'DATA-FIELD' starts with 'DATA' but is not the keyword DATA.
        result = types("DATA-FIELD")
        assert result == [TokenType.IDENTIFIER]

    def test_trailing_hyphen_stripped(self) -> None:
        """A word ending in '-' has the trailing hyphen stripped."""
        result = lexemes("WS-FIELD-")
        assert "WS-FIELD" in result

    def test_identifier_position_preserved(self) -> None:
        tokens = CobolLexer().tokenize("CUSTOMER", filename="r.cbl")
        tok = tokens[0]
        assert tok.position.line == 1
        assert tok.position.column == 1
        assert tok.position.offset == 0
        assert tok.position.filename == "r.cbl"


# ---------------------------------------------------------------------------
# Keyword regressions
# ---------------------------------------------------------------------------


class TestKeywordRegressions:
    """Every mandatory keyword is classified as KEYWORD, not IDENTIFIER."""

    _KEYWORDS = [
        "IDENTIFICATION",
        "DIVISION",
        "PROGRAM-ID",
        "ENVIRONMENT",
        "DATA",
        "PROCEDURE",
        "WORKING-STORAGE",
        "MOVE",
        "ADD",
        "SUBTRACT",
        "MULTIPLY",
        "DIVIDE",
        "DISPLAY",
        "STOP",
        "RUN",
        "IF",
        "ELSE",
        "END-IF",
        "PERFORM",
        "CALL",
        "ACCEPT",
        "COMPUTE",
    ]

    @pytest.mark.parametrize("kw", _KEYWORDS)
    def test_keyword_classified_as_keyword(self, kw: str) -> None:
        """Each reserved word is classified as KEYWORD."""
        tps = types(kw)
        assert tps == [TokenType.KEYWORD], f"{kw!r} should be KEYWORD"

    @pytest.mark.parametrize("kw", _KEYWORDS)
    def test_keyword_lexeme_uppercased(self, kw: str) -> None:
        """Keyword lexeme is always stored in uppercase."""
        lxms = lexemes(kw.lower())
        assert lxms == [kw.upper()], f"Expected {kw.upper()!r}, got {lxms}"

    def test_keyword_case_insensitive_classification(self) -> None:
        """lowercase 'move' is tokenised as KEYWORD 'MOVE'."""
        assert types("move") == [TokenType.KEYWORD]
        assert lexemes("move") == ["MOVE"]

    def test_keyword_in_multi_token_source(self) -> None:
        result = types("STOP RUN.")
        assert result[0] is TokenType.KEYWORD
        assert result[1] is TokenType.KEYWORD
        assert result[2] is TokenType.PERIOD


# ---------------------------------------------------------------------------
# Punctuation regressions
# ---------------------------------------------------------------------------


class TestPunctuationRegressions:
    """Each punctuation symbol maps to its specific TokenType."""

    def test_period_type(self) -> None:
        assert types(".") == [TokenType.PERIOD]

    def test_comma_type(self) -> None:
        assert types(",") == [TokenType.COMMA]

    def test_lparen_type(self) -> None:
        assert types("(") == [TokenType.LPAREN]

    def test_rparen_type(self) -> None:
        assert types(")") == [TokenType.RPAREN]

    def test_period_lexeme(self) -> None:
        assert lexemes(".") == ["."]

    def test_multiple_periods(self) -> None:
        """Three periods produce three PERIOD tokens."""
        result = types("...")
        assert result == [TokenType.PERIOD, TokenType.PERIOD, TokenType.PERIOD]

    def test_operator_symbols_are_unknown(self) -> None:
        """Arithmetic/comparison operators are UNKNOWN at this milestone."""
        for sym in ("+", "-", "/", "=", "<", ">"):
            result = types(sym)
            assert result == [TokenType.UNKNOWN], f"{sym!r} should be UNKNOWN"

    def test_star_at_column_one_is_comment(self) -> None:
        """A bare * at the start of a line is treated as a comment."""
        assert lex("* NOT A TOKEN") == []

    def test_star_not_at_column_one_is_unknown(self) -> None:
        """A * not at column 1 is the multiply operator (UNKNOWN)."""
        result = types("A * B")
        # A → IDENTIFIER, * → UNKNOWN, B → IDENTIFIER
        assert TokenType.UNKNOWN in result

    def test_colon_is_unknown(self) -> None:
        assert types(":") == [TokenType.UNKNOWN]

    def test_paren_pair(self) -> None:
        result = types("(A)")
        assert result == [TokenType.LPAREN, TokenType.IDENTIFIER, TokenType.RPAREN]

    def test_period_after_keyword(self) -> None:
        result = types("DIVISION.")
        assert result == [TokenType.KEYWORD, TokenType.PERIOD]


# ---------------------------------------------------------------------------
# String literal regressions
# ---------------------------------------------------------------------------


class TestStringRegressions:
    """String literal edge cases that could cause subtle regressions."""

    def test_double_quoted_string(self) -> None:
        assert types('"HELLO"') == [TokenType.STRING]
        assert lexemes('"HELLO"') == ['"HELLO"']

    def test_single_quoted_string(self) -> None:
        assert types("'WORLD'") == [TokenType.STRING]
        assert lexemes("'WORLD'") == ["'WORLD'"]

    def test_empty_double_quoted_string(self) -> None:
        assert types('""') == [TokenType.STRING]

    def test_empty_single_quoted_string(self) -> None:
        assert types("''") == [TokenType.STRING]

    def test_string_with_spaces(self) -> None:
        assert types('"HELLO WORLD"') == [TokenType.STRING]
        assert lexemes('"HELLO WORLD"') == ['"HELLO WORLD"']

    def test_unterminated_double_quote_raises(self) -> None:
        with pytest.raises(LexerError):
            CobolLexer().tokenize('"UNTERMINATED')

    def test_unterminated_single_quote_raises(self) -> None:
        with pytest.raises(LexerError):
            CobolLexer().tokenize("'UNTERMINATED")

    def test_string_at_newline_raises(self) -> None:
        with pytest.raises(LexerError):
            CobolLexer().tokenize('"HELLO\n"')
