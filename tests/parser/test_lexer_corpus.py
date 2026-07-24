"""
COBOL Lexer Corpus Tests.

Purpose:
    Validate :class:`~app.parser.lexer.lexer.CobolLexer` against a set of
    representative COBOL source programs stored in ``tests/parser/corpus/``.

    Each corpus file exercises a specific subset of the lexer's token
    recognition capabilities.  Tests verify token counts, token ordering,
    keyword recognition, identifier recognition, string recognition, numeric
    literal recognition, and the presence of the mandatory EOF sentinel.

Responsibilities:
    - Load corpus COBOL files from disk.
    - Tokenise them with :class:`CobolLexer`.
    - Assert deterministic, expected token sequences.

Non-responsibilities:
    - Modifying the lexer or any production file.
    - Parsing or semantic analysis.

Dependencies:
    - :mod:`app.parser.lexer.lexer`            — subject under test.
    - :mod:`app.parser.lexer.lexer_exceptions` — LexerError.
    - :mod:`app.parser.lexer.token_types`      — TokenType.
    - :mod:`pathlib`                           — corpus file loading.
    - :mod:`pytest`                            — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pathlib

import pytest

from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.lexer_exceptions import LexerError
from app.parser.lexer.token_types import TokenType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CORPUS = pathlib.Path(__file__).parent / "corpus"


def load(name: str) -> str:
    """Load a corpus file by stem (without extension)."""
    return (_CORPUS / f"{name}.cbl").read_text(encoding="utf-8")


def tokenize(name: str) -> list:
    """Return the full token list for corpus file *name*."""
    tokens = CobolLexer().tokenize(load(name), filename=f"{name}.cbl")

    if name == "variables":
        print("\n===== VARIABLES TOKENS =====")
        for t in tokens:
            print(f"{t.type.name:12} {t.lexeme}")

    return tokens


def types_of(name: str) -> list[TokenType]:
    """Return token types (excluding EOF) for corpus file *name*."""
    return [t.type for t in tokenize(name) if t.type is not TokenType.EOF]


def lexemes_of(name: str) -> list[str]:
    """Return token lexemes (excluding EOF) for corpus file *name*."""
    return [t.lexeme for t in tokenize(name) if t.type is not TokenType.EOF]


def count(name: str, tt: TokenType) -> int:
    """Count tokens of *tt* type in corpus file *name*."""
    return sum(1 for t in tokenize(name) if t.type is tt)


# ---------------------------------------------------------------------------
# Identification Division
# ---------------------------------------------------------------------------


class TestIdentificationCorpus:
    """identification.cbl — division header keywords and program-id."""

    def test_eof_present(self) -> None:
        tokens = tokenize("identification")
        assert tokens[-1].type is TokenType.EOF

    def test_keyword_count(self) -> None:
        assert count("identification", TokenType.KEYWORD) == 3

    def test_keywords_are(self) -> None:
        kws = [
            t.lexeme for t in tokenize("identification") if t.type is TokenType.KEYWORD
        ]
        assert "IDENTIFICATION" in kws
        assert "DIVISION" in kws
        assert "PROGRAM-ID" in kws

    def test_identifier_present(self) -> None:
        ids = [
            t.lexeme
            for t in tokenize("identification")
            if t.type is TokenType.IDENTIFIER
        ]
        assert "HELLO-WORLD" in ids

    def test_period_present(self) -> None:
        assert count("identification", TokenType.PERIOD) >= 2

    def test_total_token_count(self) -> None:
        # IDENTIFICATION DIVISION . PROGRAM-ID . HELLO-WORLD . EOF
        tokens = tokenize("identification")
        assert len(tokens) == 8

    def test_ordering(self) -> None:
        lexs = lexemes_of("identification")
        assert lexs[0] == "IDENTIFICATION"
        assert lexs[1] == "DIVISION"
        assert lexs[2] == "."
        assert lexs[3] == "PROGRAM-ID"


# ---------------------------------------------------------------------------
# Procedure Division
# ---------------------------------------------------------------------------


class TestProcedureCorpus:
    """procedure.cbl — procedure verbs, identifiers, numbers, strings."""

    def test_eof_present(self) -> None:
        tokens = tokenize("procedure")
        assert tokens[-1].type is TokenType.EOF

    def test_keyword_count(self) -> None:
        # PROCEDURE DIVISION DISPLAY MOVE ADD SUBTRACT MULTIPLY DIVIDE STOP RUN
        assert count("procedure", TokenType.KEYWORD) == 10

    def test_procedure_keyword_present(self) -> None:
        kws = [t.lexeme for t in tokenize("procedure") if t.type is TokenType.KEYWORD]
        assert "PROCEDURE" in kws
        assert "DIVISION" in kws
        assert "STOP" in kws
        assert "RUN" in kws

    def test_number_count(self) -> None:
        assert count("procedure", TokenType.NUMBER) == 5

    def test_string_present(self) -> None:
        assert count("procedure", TokenType.STRING) == 1

    def test_string_lexeme(self) -> None:
        strs = [t.lexeme for t in tokenize("procedure") if t.type is TokenType.STRING]
        assert "'START'" in strs

    def test_total_token_count(self) -> None:
        tokens = tokenize("procedure")
        assert len(tokens) == 37


# ---------------------------------------------------------------------------
# Variables (DATA DIVISION)
# ---------------------------------------------------------------------------


class TestVariablesCorpus:
    """variables.cbl — DATA DIVISION with WORKING-STORAGE identifiers."""

    def test_eof_present(self) -> None:
        tokens = tokenize("variables")
        assert tokens[-1].type is TokenType.EOF

    def test_keywords_present(self) -> None:
        kws = [t.lexeme for t in tokenize("variables") if t.type is TokenType.KEYWORD]
        assert "DATA" in kws
        assert "WORKING-STORAGE" in kws

    def test_identifier_count(self) -> None:
        assert count("variables", TokenType.IDENTIFIER) == 6

    def test_identifier_names(self) -> None:
        ids = [
            t.lexeme for t in tokenize("variables") if t.type is TokenType.IDENTIFIER
        ]
        assert "WS-COUNT" in ids
        assert "CUSTOMER-NAME" in ids
        assert "PAYROLL-RECORD" in ids
        assert "EMPLOYEE-ID" in ids

    def test_numbers_are_level_numbers(self) -> None:
        """Level numbers (01) are lexed as NUMBER tokens at this stage."""
        assert count("variables", TokenType.NUMBER) == 5


# ---------------------------------------------------------------------------
# Strings
# ---------------------------------------------------------------------------


class TestStringsCorpus:
    """strings.cbl — double and single quoted string literals."""

    def test_eof_present(self) -> None:
        tokens = tokenize("strings")
        assert tokens[-1].type is TokenType.EOF

    def test_string_count(self) -> None:
        assert count("strings", TokenType.STRING) == 6

    def test_double_quoted_string(self) -> None:
        strs = [t.lexeme for t in tokenize("strings") if t.type is TokenType.STRING]
        assert '"HELLO, WORLD!"' in strs

    def test_single_quoted_string(self) -> None:
        strs = [t.lexeme for t in tokenize("strings") if t.type is TokenType.STRING]
        assert "'SINGLE QUOTED'" in strs

    def test_empty_string(self) -> None:
        strs = [t.lexeme for t in tokenize("strings") if t.type is TokenType.STRING]
        assert '""' in strs

    def test_no_numbers(self) -> None:
        assert count("strings", TokenType.NUMBER) == 0

    def test_total_token_count(self) -> None:
        tokens = tokenize("strings")
        assert len(tokens) == 23


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------


class TestNumbersCorpus:
    """numbers.cbl — integer numeric literals in MOVE statements."""

    def test_eof_present(self) -> None:
        tokens = tokenize("numbers")
        assert tokens[-1].type is TokenType.EOF

    def test_number_count(self) -> None:
        assert count("numbers", TokenType.NUMBER) == 5

    def test_number_values(self) -> None:
        nums = [t.lexeme for t in tokenize("numbers") if t.type is TokenType.NUMBER]
        assert "0" in nums
        assert "1" in nums
        assert "100" in nums
        assert "12345" in nums
        assert "9999" in nums

    def test_no_strings(self) -> None:
        assert count("numbers", TokenType.STRING) == 0

    def test_total_token_count(self) -> None:
        tokens = tokenize("numbers")
        assert len(tokens) == 32


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


class TestCommentsCorpus:
    """comments.cbl — fixed-format and free-format comments ignored."""

    def test_eof_present(self) -> None:
        tokens = tokenize("comments")
        assert tokens[-1].type is TokenType.EOF

    def test_comment_marker_not_in_tokens(self) -> None:
        """Comment lines must not produce tokens."""
        lexs = lexemes_of("comments")
        assert "*" not in lexs
        assert "*>" not in lexs

    def test_keywords_not_in_comment_lines(self) -> None:
        """Words inside comment lines are not tokenised."""
        kws = [t.lexeme for t in tokenize("comments") if t.type is TokenType.KEYWORD]
        # The comment text 'LINE COMMENT: identification header' must not
        # produce IDENTIFICATION as a keyword token
        assert kws.count("IDENTIFICATION") == 1  # only from the real division line

    def test_code_tokens_preserved(self) -> None:
        kws = [t.lexeme for t in tokenize("comments") if t.type is TokenType.KEYWORD]
        assert "IDENTIFICATION" in kws
        assert "DIVISION" in kws
        assert "PROGRAM-ID" in kws
        assert "PROCEDURE" in kws

    def test_total_token_count(self) -> None:
        tokens = tokenize("comments")
        assert len(tokens) == 17


# ---------------------------------------------------------------------------
# Invalid characters
# ---------------------------------------------------------------------------


class TestInvalidCharactersCorpus:
    """invalid_characters.cbl — LexerError raised for @ character."""

    def test_raises_lexer_error(self) -> None:
        with pytest.raises(LexerError):
            tokenize("invalid_characters")

    def test_error_has_message(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize("invalid_characters")
        assert exc_info.value.message

    def test_error_has_position(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize("invalid_characters")
        err = exc_info.value
        assert err.line >= 1
        assert err.column >= 1


# ---------------------------------------------------------------------------
# Unterminated string
# ---------------------------------------------------------------------------


class TestUnterminatedStringCorpus:
    """unterminated_string.cbl — LexerError raised for unclosed string."""

    def test_raises_lexer_error(self) -> None:
        with pytest.raises(LexerError):
            tokenize("unterminated_string")

    def test_error_has_message(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize("unterminated_string")
        assert exc_info.value.message

    def test_error_position_on_string_start(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize("unterminated_string")
        err = exc_info.value
        assert err.line >= 1
        assert err.column >= 1


# ---------------------------------------------------------------------------
# Mixed program
# ---------------------------------------------------------------------------


class TestMixedProgramCorpus:
    """mixed_program.cbl — all token categories exercised together."""

    def test_eof_present(self) -> None:
        tokens = tokenize("mixed_program")
        assert tokens[-1].type is TokenType.EOF

    def test_total_token_count(self) -> None:
        tokens = tokenize("mixed_program")
        assert len(tokens) == 87

    def test_keyword_count(self) -> None:
        assert count("mixed_program", TokenType.KEYWORD) == 25

    def test_identifier_count(self) -> None:
        assert count("mixed_program", TokenType.IDENTIFIER) == 21

    def test_number_count(self) -> None:
        assert count("mixed_program", TokenType.NUMBER) == 8

    def test_string_count(self) -> None:
        assert count("mixed_program", TokenType.STRING) == 3

    def test_keywords_present(self) -> None:
        kws = [
            t.lexeme for t in tokenize("mixed_program") if t.type is TokenType.KEYWORD
        ]
        for kw in (
            "IDENTIFICATION",
            "DIVISION",
            "PROGRAM-ID",
            "ENVIRONMENT",
            "DATA",
            "WORKING-STORAGE",
            "PROCEDURE",
            "ACCEPT",
            "MOVE",
            "COMPUTE",
            "IF",
            "DISPLAY",
            "ELSE",
            "END-IF",
            "PERFORM",
            "STOP",
            "RUN",
        ):
            assert kw in kws, f"Expected keyword {kw!r} in mixed program"

    def test_identifiers_present(self) -> None:
        ids = [
            t.lexeme
            for t in tokenize("mixed_program")
            if t.type is TokenType.IDENTIFIER
        ]
        for ident in ("PAYROLL", "EMPLOYEE-ID", "EMPLOYEE-NAME", "SALARY", "NET-PAY"):
            assert ident in ids

    def test_strings_present(self) -> None:
        strs = [
            t.lexeme for t in tokenize("mixed_program") if t.type is TokenType.STRING
        ]
        assert '"NET PAY: "' in strs
        assert '"NO PAY"' in strs

    def test_ordering_starts_correctly(self) -> None:
        lexs = lexemes_of("mixed_program")
        assert lexs[0] == "IDENTIFICATION"
        assert lexs[1] == "DIVISION"

    def test_periods_present(self) -> None:
        assert count("mixed_program", TokenType.PERIOD) >= 5

    def test_all_positions_have_filename(self) -> None:
        tokens = tokenize("mixed_program")
        for tok in tokens:
            assert tok.position.filename == "mixed_program.cbl"

    def test_offsets_non_decreasing(self) -> None:
        tokens = tokenize("mixed_program")
        offsets = [t.position.offset for t in tokens]
        assert offsets == sorted(offsets)
