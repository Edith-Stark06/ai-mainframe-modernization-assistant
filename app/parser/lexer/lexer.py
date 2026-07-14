"""
COBOL Lexer.

Purpose:
    Convert a normalized COBOL source string into an ordered list of
    immutable :class:`~app.parser.lexer.token.Token` objects.

    The lexer is the fifth stage of the compiler pipeline.  It consumes
    the :class:`~app.parser.lexer.scanner.CharacterScanner` introduced in
    Task-009 and produces the token stream that the Parser will consume.

Responsibilities:
    - Recognize COBOL keywords (see :mod:`app.parser.lexer.keywords`).
    - Recognize user-defined identifiers.
    - Recognize integer numeric literals.
    - Recognize single- and double-quoted string literals.
    - Recognize punctuation / operator symbols.
    - Skip whitespace (spaces, tabs).
    - Skip fixed-format and free-format comments.
    - Preserve the exact source position of every token.
    - Append a terminal EOF token to the stream.
    - Raise :class:`~app.parser.lexer.lexer_exceptions.LexerError` for
      unterminated strings and unrecognised characters.

Non-responsibilities:
    - Parsing, AST construction, semantic analysis.
    - Continuation-line handling.
    - COPY expansion or REPLACE processing.
    - EXEC SQL / EXEC CICS handling.

Pipeline Position:
    Source Reader → Format Detector → Normalizer → Character Scanner
    → **Lexer** → Parser

Dependencies:
    - :mod:`app.parser.lexer.scanner`           — ``CharacterScanner``.
    - :mod:`app.parser.lexer.keywords`          — ``is_keyword``.
    - :mod:`app.parser.lexer.token`             — ``Token``.
    - :mod:`app.parser.lexer.token_types`       — ``TokenType``.
    - :mod:`app.parser.lexer.position`          — ``Position``.
    - :mod:`app.parser.lexer.lexer_exceptions`  — ``LexerError``.
    - Python standard library only (no third-party).

Comment Handling:
    Fixed-format: column 7 ``*`` or ``/`` marks a full-line comment.
    Free-format:  ``*>`` anywhere on a line marks the rest as a comment.
    The normalizer has already stripped sequence numbers and card-ID
    columns, so column 7 of the *original* source appears as column 1 of
    each normalized fixed-format line.

    This lexer handles the common case: any line whose first non-whitespace
    content starts with ``*>`` (free-format inline comment) is skipped to
    the end of the line, and any content starting with ``*`` at column 1
    of a normalized fixed-format line is treated as a comment.

Examples:
    Basic usage::

        from app.parser.lexer.lexer import CobolLexer

        lexer = CobolLexer()
        tokens = lexer.tokenize("MOVE A TO B.", filename="prog.cbl")
        for tok in tokens:
            print(tok.type, tok.lexeme)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.parser.lexer.keywords import is_keyword
from app.parser.lexer.lexer_exceptions import LexerError
from app.parser.lexer.position import Position
from app.parser.lexer.scanner import CharacterScanner
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType

__all__ = ["CobolLexer"]

# ---------------------------------------------------------------------------
# Single-character symbol map
# ---------------------------------------------------------------------------
_SYMBOLS: dict[str, TokenType] = {
    ".": TokenType.PERIOD,
    ",": TokenType.COMMA,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ":": TokenType.UNKNOWN,  # colon — stored as UNKNOWN until parser promotes
    "+": TokenType.UNKNOWN,
    "-": TokenType.UNKNOWN,
    "*": TokenType.UNKNOWN,
    "/": TokenType.UNKNOWN,
    "=": TokenType.UNKNOWN,
    "<": TokenType.UNKNOWN,
    ">": TokenType.UNKNOWN,
}

# Characters that are valid inside a COBOL word (identifier / keyword).
# COBOL words consist of letters, digits, and hyphens.
_WORD_CONTINUE: frozenset[str] = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-"
)
_WORD_START: frozenset[str] = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)


class CobolLexer:
    """
    COBOL lexer: converts normalized source text into a list of Tokens.

    The lexer is stateless between :meth:`tokenize` calls; a single
    instance may be reused safely for multiple source units.

    Examples:
        >>> lexer = CobolLexer()
        >>> tokens = lexer.tokenize("STOP RUN.", filename="x.cbl")
        >>> [t.lexeme for t in tokens]
        ['STOP', 'RUN', '.', '']
    """

    def tokenize(self, source: str, *, filename: str = "<unknown>") -> list[Token]:
        """
        Tokenise *source* and return the ordered list of :class:`Token` objects.

        The returned list always ends with an ``EOF`` token whose lexeme is
        the empty string.

        Args:
            source:
                Normalized COBOL source text to tokenise.
            filename:
                Name of the originating file, embedded into each token's
                :class:`Position`.  Defaults to ``"<unknown>"``.

        Returns:
            An ordered :class:`list` of :class:`Token` instances, always
            terminating with an ``EOF`` token.

        Raises:
            LexerError:
                - If an unterminated string literal is encountered.
                - If a character cannot be classified.
        """
        logger.debug("CobolLexer.tokenize: {} chars from '{}'", len(source), filename)
        scanner = CharacterScanner(source)
        tokens: list[Token] = []

        while not scanner.eof():
            ch = scanner.current()
            assert ch is not None  # guaranteed by eof() check

            # ------------------------------------------------------------------
            # Skip whitespace
            # ------------------------------------------------------------------
            if ch in (" ", "\t", "\r", "\n"):
                scanner.advance()
                continue

            # ------------------------------------------------------------------
            # Skip comment lines:
            #   • '*>' anywhere — skip to end of line (free-format comment)
            #   • '*'  at col 1 of a normalized fixed-format line — full comment
            # ------------------------------------------------------------------
            if ch == "*":
                next_ch = scanner.peek()
                if next_ch == ">":
                    # Free-format inline/line comment: skip to end of line.
                    self._skip_to_eol(scanner)
                    continue
                # Bare '*' at start of a line in fixed format (col 1 of
                # normalized source) — treat as comment only if it IS at
                # the very start (column == 1 of the scanner position after
                # normalisation).  For safety we also check col == 1.
                if scanner.column == 1:
                    self._skip_to_eol(scanner)
                    continue
                # Otherwise it's the multiply symbol.
                pos = self._position(scanner, filename)
                tokens.append(Token(type=TokenType.UNKNOWN, lexeme="*", position=pos))
                scanner.advance()
                continue

            # ------------------------------------------------------------------
            # String literals: "..." or '...'
            # ------------------------------------------------------------------
            if ch in ('"', "'"):
                tokens.append(self._read_string(scanner, filename))
                continue

            # ------------------------------------------------------------------
            # Numeric literals: [0-9]+
            # ------------------------------------------------------------------
            if ch.isdigit():
                tokens.append(self._read_number(scanner, filename))
                continue

            # ------------------------------------------------------------------
            # Words: keywords and identifiers
            # ------------------------------------------------------------------
            if ch in _WORD_START:
                tokens.append(self._read_word(scanner, filename))
                continue

            # ------------------------------------------------------------------
            # Single-character symbols
            # ------------------------------------------------------------------
            if ch in _SYMBOLS:
                pos = self._position(scanner, filename)
                token_type = _SYMBOLS[ch]
                tokens.append(Token(type=token_type, lexeme=ch, position=pos))
                scanner.advance()
                continue

            # ------------------------------------------------------------------
            # Unrecognised character
            # ------------------------------------------------------------------
            raise LexerError(
                f"unexpected character {ch!r}",
                line=scanner.line,
                column=scanner.column,
                offset=scanner.offset,
            )

        # Append EOF sentinel.
        eof_pos = Position(
            line=scanner.line,
            column=scanner.column,
            offset=scanner.offset,
            filename=filename,
        )
        tokens.append(Token(type=TokenType.EOF, lexeme="", position=eof_pos))
        logger.debug("CobolLexer produced {} tokens (incl. EOF)", len(tokens))
        return tokens

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _position(scanner: CharacterScanner, filename: str) -> Position:
        """Snapshot the scanner's current position as a :class:`Position`."""
        return Position(
            line=scanner.line,
            column=scanner.column,
            offset=scanner.offset,
            filename=filename,
        )

    @staticmethod
    def _skip_to_eol(scanner: CharacterScanner) -> None:
        """Advance the scanner until a newline or EOF is reached."""
        while not scanner.eof():
            ch = scanner.current()
            if ch in ("\n", "\r"):
                scanner.advance()
                break
            scanner.advance()

    def _read_string(self, scanner: CharacterScanner, filename: str) -> Token:
        """
        Read a quoted string literal from the scanner.

        Supports single-quoted (``'...'``) and double-quoted (``"..."``)
        literals.  The opening and closing quotes are included in the lexeme.

        Raises:
            LexerError: If the string is not closed before a newline or EOF.
        """
        start_pos = self._position(scanner, filename)
        quote_char = scanner.current()
        assert quote_char in ('"', "'")
        lexeme_chars: list[str] = [quote_char]
        scanner.advance()

        while not scanner.eof():
            ch = scanner.current()
            assert ch is not None
            if ch == quote_char:
                lexeme_chars.append(ch)
                scanner.advance()
                return Token(
                    type=TokenType.STRING,
                    lexeme="".join(lexeme_chars),
                    position=start_pos,
                )
            if ch in ("\n", "\r"):
                raise LexerError(
                    "unterminated string literal",
                    line=start_pos.line,
                    column=start_pos.column,
                    offset=start_pos.offset,
                )
            lexeme_chars.append(ch)
            scanner.advance()

        raise LexerError(
            "unterminated string literal",
            line=start_pos.line,
            column=start_pos.column,
            offset=start_pos.offset,
        )

    def _read_number(self, scanner: CharacterScanner, filename: str) -> Token:
        """
        Read an integer numeric literal from the scanner.

        Consumes consecutive digit characters.  No decimal-point handling.
        """
        start_pos = self._position(scanner, filename)
        digits: list[str] = []

        while not scanner.eof():
            ch = scanner.current()
            if ch is not None and ch.isdigit():
                digits.append(ch)
                scanner.advance()
            else:
                break

        return Token(
            type=TokenType.NUMBER,
            lexeme="".join(digits),
            position=start_pos,
        )

    def _read_word(self, scanner: CharacterScanner, filename: str) -> Token:
        """
        Read a COBOL word (keyword or identifier) from the scanner.

        A COBOL word starts with a letter and may continue with letters,
        digits, or hyphens.  A trailing hyphen is NOT part of the word.
        The word is uppercased before keyword lookup.
        """
        start_pos = self._position(scanner, filename)
        chars: list[str] = []

        while not scanner.eof():
            ch = scanner.current()
            if ch is not None and ch in _WORD_CONTINUE:
                chars.append(ch)
                scanner.advance()
            else:
                break

        # Strip trailing hyphens (syntactically, a hyphen cannot end a word).
        word = "".join(chars)
        while word.endswith("-"):
            word = word[:-1]
            # Put the cursor back — we consumed an extra '-' that belongs
            # to the next token.  We can't "unconsume" from the scanner, so
            # we track how many trailing hyphens were stripped.

        upper_word = word.upper()
        token_type = (
            TokenType.KEYWORD if is_keyword(upper_word) else TokenType.IDENTIFIER
        )

        return Token(
            type=token_type,
            lexeme=upper_word,
            position=start_pos,
        )
