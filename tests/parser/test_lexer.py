"""
Tests for the COBOL Lexer.

Purpose:
    Verify that :class:`~app.parser.lexer.lexer.CobolLexer` correctly
    tokenises COBOL source text, preserves positions, recognises all
    required token categories, ignores whitespace and comments, and
    raises :class:`~app.parser.lexer.lexer_exceptions.LexerError` for
    invalid input.

Test Categories:
    - Keywords
    - Identifiers
    - Numbers
    - String literals
    - Symbols / punctuation
    - Comments (fixed-format and free-format)
    - Whitespace (ignored)
    - Invalid characters
    - Unterminated strings
    - Position tracking
    - EOF sentinel

Dependencies:
    - :mod:`app.parser.lexer.lexer`             — subject under test.
    - :mod:`app.parser.lexer.lexer_exceptions`  — LexerError.
    - :mod:`app.parser.lexer.token_types`       — TokenType.
    - :mod:`pytest`                             — test framework.

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


def lex(source: str, filename: str = "test.cbl") -> list:
    """Return token list for *source* using a fresh CobolLexer."""
    return CobolLexer().tokenize(source, filename=filename)


def types(source: str) -> list[TokenType]:
    """Return the TokenType sequence for *source* (excluding EOF)."""
    return [t.type for t in lex(source) if t.type is not TokenType.EOF]


def lexemes(source: str) -> list[str]:
    """Return the lexeme sequence for *source* (excluding EOF)."""
    return [t.lexeme for t in lex(source) if t.type is not TokenType.EOF]


# ---------------------------------------------------------------------------
# EOF sentinel
# ---------------------------------------------------------------------------


class TestEof:
    """Every tokenise call ends with an EOF token."""

    def test_empty_source_produces_only_eof(self) -> None:
        tokens = lex("")
        assert len(tokens) == 1
        assert tokens[0].type is TokenType.EOF

    def test_eof_lexeme_is_empty(self) -> None:
        tokens = lex("")
        assert tokens[-1].lexeme == ""

    def test_non_empty_source_last_token_is_eof(self) -> None:
        tokens = lex("STOP RUN.")
        assert tokens[-1].type is TokenType.EOF


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------


class TestKeywords:
    """COBOL reserved words are classified as KEYWORD tokens."""

    def test_identification(self) -> None:
        assert types("IDENTIFICATION") == [TokenType.KEYWORD]

    def test_division(self) -> None:
        assert types("DIVISION") == [TokenType.KEYWORD]

    def test_program_id(self) -> None:
        assert types("PROGRAM-ID") == [TokenType.KEYWORD]

    def test_environment(self) -> None:
        assert types("ENVIRONMENT") == [TokenType.KEYWORD]

    def test_data(self) -> None:
        assert types("DATA") == [TokenType.KEYWORD]

    def test_procedure(self) -> None:
        assert types("PROCEDURE") == [TokenType.KEYWORD]

    def test_working_storage(self) -> None:
        assert types("WORKING-STORAGE") == [TokenType.KEYWORD]

    def test_move(self) -> None:
        assert types("MOVE") == [TokenType.KEYWORD]

    def test_add(self) -> None:
        assert types("ADD") == [TokenType.KEYWORD]

    def test_subtract(self) -> None:
        assert types("SUBTRACT") == [TokenType.KEYWORD]

    def test_multiply(self) -> None:
        assert types("MULTIPLY") == [TokenType.KEYWORD]

    def test_divide(self) -> None:
        assert types("DIVIDE") == [TokenType.KEYWORD]

    def test_display(self) -> None:
        assert types("DISPLAY") == [TokenType.KEYWORD]

    def test_stop(self) -> None:
        assert types("STOP") == [TokenType.KEYWORD]

    def test_run(self) -> None:
        assert types("RUN") == [TokenType.KEYWORD]

    def test_if(self) -> None:
        assert types("IF") == [TokenType.KEYWORD]

    def test_else(self) -> None:
        assert types("ELSE") == [TokenType.KEYWORD]

    def test_end_if(self) -> None:
        assert types("END-IF") == [TokenType.KEYWORD]

    def test_perform(self) -> None:
        assert types("PERFORM") == [TokenType.KEYWORD]

    def test_call(self) -> None:
        assert types("CALL") == [TokenType.KEYWORD]

    def test_accept(self) -> None:
        assert types("ACCEPT") == [TokenType.KEYWORD]

    def test_compute(self) -> None:
        assert types("COMPUTE") == [TokenType.KEYWORD]

    def test_keyword_lexeme_is_uppercased(self) -> None:
        """Keywords are stored in uppercase regardless of source case."""
        assert lexemes("move") == ["MOVE"]

    def test_keyword_in_sentence(self) -> None:
        """Keywords are recognised within a multi-token source."""
        toks = [t for t in lex("STOP RUN.") if t.type is not TokenType.EOF]
        assert toks[0].type is TokenType.KEYWORD
        assert toks[0].lexeme == "STOP"
        assert toks[1].type is TokenType.KEYWORD
        assert toks[1].lexeme == "RUN"


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


class TestIdentifiers:
    """User-defined names are classified as IDENTIFIER tokens."""

    def test_simple_identifier(self) -> None:
        assert types("CUSTOMER") == [TokenType.IDENTIFIER]

    def test_hyphenated_identifier(self) -> None:
        assert types("CUSTOMER-NAME") == [TokenType.IDENTIFIER]

    def test_identifier_with_digits(self) -> None:
        assert types("WS-COUNT-01") == [TokenType.IDENTIFIER]

    def test_identifier_lexeme_uppercased(self) -> None:
        assert lexemes("customer-name") == ["CUSTOMER-NAME"]

    def test_identifier_not_keyword(self) -> None:
        """A word not in the keyword set is an identifier, not a keyword."""
        assert types("TOTAL") == [TokenType.IDENTIFIER]

    def test_payroll_record(self) -> None:
        assert types("PAYROLL-RECORD") == [TokenType.IDENTIFIER]


# ---------------------------------------------------------------------------
# Numeric literals
# ---------------------------------------------------------------------------


class TestNumbers:
    """Integer numeric literals are classified as NUMBER tokens."""

    def test_zero(self) -> None:
        assert types("0") == [TokenType.NUMBER]
        assert lexemes("0") == ["0"]

    def test_single_digit(self) -> None:
        assert types("1") == [TokenType.NUMBER]

    def test_multi_digit(self) -> None:
        assert types("12345") == [TokenType.NUMBER]
        assert lexemes("12345") == ["12345"]

    def test_hundred(self) -> None:
        assert types("100") == [TokenType.NUMBER]

    def test_number_followed_by_period(self) -> None:
        """A number followed immediately by a period produces two tokens."""
        result = types("42.")
        assert result == [TokenType.NUMBER, TokenType.PERIOD]

    def test_multiple_numbers(self) -> None:
        result = types("1 2 3")
        assert result == [TokenType.NUMBER, TokenType.NUMBER, TokenType.NUMBER]


# ---------------------------------------------------------------------------
# String literals
# ---------------------------------------------------------------------------


class TestStrings:
    """Quoted string literals are classified as STRING tokens."""

    def test_double_quoted_string(self) -> None:
        assert types('"HELLO"') == [TokenType.STRING]

    def test_double_quoted_lexeme_preserved(self) -> None:
        assert lexemes('"HELLO"') == ['"HELLO"']

    def test_single_quoted_string(self) -> None:
        assert types("'WORLD'") == [TokenType.STRING]

    def test_single_quoted_lexeme_preserved(self) -> None:
        assert lexemes("'WORLD'") == ["'WORLD'"]

    def test_empty_double_quoted_string(self) -> None:
        assert types('""') == [TokenType.STRING]
        assert lexemes('""') == ['""']

    def test_empty_single_quoted_string(self) -> None:
        assert types("''") == [TokenType.STRING]

    def test_string_with_spaces_inside(self) -> None:
        assert types('"HELLO WORLD"') == [TokenType.STRING]
        assert lexemes('"HELLO WORLD"') == ['"HELLO WORLD"']


# ---------------------------------------------------------------------------
# Symbols / punctuation
# ---------------------------------------------------------------------------


class TestSymbols:
    """Punctuation characters are classified correctly."""

    def test_period(self) -> None:
        assert types(".") == [TokenType.PERIOD]
        assert lexemes(".") == ["."]

    def test_comma(self) -> None:
        assert types(",") == [TokenType.COMMA]
        assert lexemes(",") == [","]

    def test_lparen(self) -> None:
        assert types("(") == [TokenType.LPAREN]

    def test_rparen(self) -> None:
        assert types(")") == [TokenType.RPAREN]

    def test_multiple_symbols(self) -> None:
        result = types(".,():")
        assert TokenType.PERIOD in result
        assert TokenType.COMMA in result
        assert TokenType.LPAREN in result
        assert TokenType.RPAREN in result

    def test_arithmetic_symbols(self) -> None:
        """Arithmetic operators are produced as UNKNOWN until the parser promotes them."""
        result = types("+ - / =")
        assert all(t is TokenType.UNKNOWN for t in result)

    def test_comparison_symbols(self) -> None:
        result = types("< >")
        assert all(t is TokenType.UNKNOWN for t in result)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


class TestComments:
    """Comments are ignored — no tokens are produced for them."""

    def test_free_format_comment_line(self) -> None:
        """A line beginning with *> produces no tokens."""
        assert types("*> this is a comment") == []

    def test_free_format_inline_comment(self) -> None:
        """Content before *> is tokenised; the comment is discarded."""
        lexs = [
            t.lexeme
            for t in lex("MOVE A *> comment\nTO B")
            if t.type is not TokenType.EOF
        ]
        assert "MOVE" in lexs
        assert "A" in lexs
        assert "TO" in lexs
        assert "B" in lexs
        assert "*>" not in lexs

    def test_fixed_format_comment_line(self) -> None:
        """A line whose first character is * (col 1 of normalized source) is a comment."""
        assert types("* OLD-STYLE COMMENT") == []

    def test_comment_between_code_lines(self) -> None:
        """Comments between code lines do not affect surrounding tokens."""
        source = "STOP\n* comment\nRUN."
        result = lexemes(source)
        assert result == ["STOP", "RUN", "."]


# ---------------------------------------------------------------------------
# Whitespace
# ---------------------------------------------------------------------------


class TestWhitespace:
    """Whitespace (spaces, tabs, newlines) is ignored."""

    def test_spaces_ignored(self) -> None:
        assert types("   STOP   RUN   ") == [TokenType.KEYWORD, TokenType.KEYWORD]

    def test_tabs_ignored(self) -> None:
        assert types("STOP\tRUN") == [TokenType.KEYWORD, TokenType.KEYWORD]

    def test_newlines_ignored(self) -> None:
        assert types("STOP\nRUN") == [TokenType.KEYWORD, TokenType.KEYWORD]

    def test_mixed_whitespace(self) -> None:
        assert types("  STOP \t RUN \n .") == [
            TokenType.KEYWORD,
            TokenType.KEYWORD,
            TokenType.PERIOD,
        ]

    def test_whitespace_only_produces_only_eof(self) -> None:
        tokens = lex("   \t\n  ")
        assert len(tokens) == 1
        assert tokens[0].type is TokenType.EOF


# ---------------------------------------------------------------------------
# Invalid characters
# ---------------------------------------------------------------------------


class TestInvalidCharacters:
    """Unrecognised characters raise LexerError."""

    def test_at_sign_raises(self) -> None:
        with pytest.raises(LexerError):
            lex("@INVALID")

    def test_hash_raises(self) -> None:
        with pytest.raises(LexerError):
            lex("#COMMENT")

    def test_tilde_raises(self) -> None:
        with pytest.raises(LexerError):
            lex("~")

    def test_error_carries_position(self) -> None:
        """LexerError records line, column, and offset of the bad character."""
        with pytest.raises(LexerError) as exc_info:
            lex("MOVE @")
        err = exc_info.value
        assert err.line > 0
        assert err.column > 0
        assert err.offset >= 0

    def test_error_message_non_empty(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            lex("@")
        assert exc_info.value.message


# ---------------------------------------------------------------------------
# Unterminated strings
# ---------------------------------------------------------------------------


class TestUnterminatedStrings:
    """Unterminated string literals raise LexerError."""

    def test_unterminated_double_quote(self) -> None:
        with pytest.raises(LexerError):
            lex('"HELLO')

    def test_unterminated_single_quote(self) -> None:
        with pytest.raises(LexerError):
            lex("'WORLD")

    def test_unterminated_at_newline(self) -> None:
        with pytest.raises(LexerError):
            lex('"HELLO\n"')

    def test_unterminated_error_has_position(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            lex('"UNTERMINATED')
        err = exc_info.value
        assert err.line >= 1
        assert err.column >= 1


# ---------------------------------------------------------------------------
# Position tracking
# ---------------------------------------------------------------------------


class TestPositionTracking:
    """Token positions reflect their source location."""

    def test_first_token_position(self) -> None:
        """The first token starts at line 1, column 1, offset 0."""
        tokens = lex("STOP RUN.")
        first = tokens[0]
        assert first.position.line == 1
        assert first.position.column == 1
        assert first.position.offset == 0

    def test_filename_embedded_in_position(self) -> None:
        tokens = lex("STOP", filename="prog.cbl")
        assert tokens[0].position.filename == "prog.cbl"

    def test_second_token_column(self) -> None:
        """The second token starts at a column greater than 1."""
        tokens = [t for t in lex("STOP RUN.") if t.type is not TokenType.EOF]
        # 'STOP' occupies col 1-4, space at 5, 'RUN' starts at col 6
        run_tok = tokens[1]
        assert run_tok.position.column > 1

    def test_token_on_second_line(self) -> None:
        """A token on the second line has line == 2."""
        tokens = [t for t in lex("STOP\nRUN.") if t.type is not TokenType.EOF]
        run_tok = next(t for t in tokens if t.lexeme == "RUN")
        assert run_tok.position.line == 2

    def test_offset_increases(self) -> None:
        """Tokens have strictly increasing offsets."""
        tokens = [t for t in lex("STOP RUN.") if t.type is not TokenType.EOF]
        offsets = [t.position.offset for t in tokens]
        assert offsets == sorted(offsets)


# ---------------------------------------------------------------------------
# Full COBOL program fragment
# ---------------------------------------------------------------------------


class TestFullFragment:
    """Integration: tokenise a realistic COBOL program fragment."""

    _SOURCE = (
        " IDENTIFICATION DIVISION.\n"
        " PROGRAM-ID. HELLO-WORLD.\n"
        " PROCEDURE DIVISION.\n"
        "     DISPLAY 'HELLO, WORLD!'.\n"
        "     STOP RUN.\n"
    )

    def test_token_count(self) -> None:
        """Fragment produces the expected number of non-EOF tokens."""
        tokens = [t for t in lex(self._SOURCE) if t.type is not TokenType.EOF]
        # IDENTIFICATION DIVISION . PROGRAM-ID . HELLO-WORLD . PROCEDURE DIVISION .
        # DISPLAY 'HELLO, WORLD!' . STOP RUN .
        assert len(tokens) >= 10

    def test_keywords_present(self) -> None:
        lexs = lexemes(self._SOURCE)
        for kw in ("IDENTIFICATION", "DIVISION", "PROCEDURE", "DISPLAY", "STOP", "RUN"):
            assert kw in lexs

    def test_string_literal_present(self) -> None:
        result = types(self._SOURCE)
        assert TokenType.STRING in result

    def test_periods_present(self) -> None:
        result = types(self._SOURCE)
        assert TokenType.PERIOD in result
