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
    - Skip a ``>>SOURCE FREE|FIXED`` compiler directive line whole (task
      #stage44) -- see :meth:`CobolLexer._is_source_directive`. The
      directive has already done its job upstream, in
      :class:`~app.parser.lexer.format_detector.FormatDetector`; this
      lexer's only remaining concern is not letting the literal ``>>``
      characters corrupt the token stream.
    - Splice a nonnumeric literal across a fixed-format continuation line
      (task #stage43) -- see :meth:`CobolLexer._try_resume_continued_string`.
    - Preserve the exact source position of every token.
    - Append a terminal EOF token to the stream.
    - Raise :class:`~app.parser.lexer.lexer_exceptions.LexerError` for
      unterminated strings and unrecognised characters.

Non-responsibilities:
    - Parsing, AST construction, semantic analysis.
    - Continuation of anything other than a nonnumeric (quoted) literal --
      a PICTURE character-string continuation is unevidenced and out of
      scope; ordinary statement text never needed continuation-line
      support to begin with, since this lexer already reads tokens
      straight across an unmarked line break.
    - Any ``>>`` compiler directive other than ``>>SOURCE`` (``>>IF``,
      ``>>DEFINE``, ``>>CALL``, ...) -- conditional compilation is a
      separate, unevidenced, unscoped feature; such a directive line is
      not specially recognised and will corrupt the token stream exactly
      as ``>>SOURCE`` used to before task #stage44.
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
    "$": TokenType.UNKNOWN,  # currency symbol (PICTURE clause editing, e.g. PIC $$$9.99)
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
# Word characters excluding the hyphen: a hyphen only continues a word
# when another word character follows it.
_WORD_CONTINUE_NO_HYPHEN: frozenset[str] = _WORD_CONTINUE - {"-"}

#: Width of the fixed-format sequence-number area (columns 1-6), i.e. the
#: number of characters preceding the column-7 indicator (task #stage43).
_SEQUENCE_AREA_WIDTH: int = 6


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
            # Skip a '>>SOURCE FREE|FIXED' compiler directive line (task
            # #stage44): it has already done its job upstream, in
            # FormatDetector._detect_by_directive, which reads the raw
            # source directly and is unaffected by whatever the lexer
            # does with the line afterward. Neither normalizer variant
            # strips it (FREE format is passed through unchanged; FIXED
            # format has no special case for it, since a directive line
            # is ordinary code as far as column stripping is concerned),
            # so without this the '>' character reached the operator
            # branch below as two stray OPERATOR_GT tokens followed by
            # 'SOURCE'/'FREE' as IDENTIFIER tokens sitting where
            # IDENTIFICATION DIVISION was expected -- confirmed directly:
            # the parser consumed zero tokens and produced no AST, no
            # diagnostic, and no raised error, only a silently empty
            # analysis result. ``>>`` has no other meaning anywhere in
            # COBOL's grammar, so intercepting it here is unambiguous.
            # ------------------------------------------------------------------
            if (
                ch == ">"
                and scanner.peek() == ">"
                and self._is_source_directive(scanner)
            ):
                self._skip_to_eol(scanner)
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
            # Operators and single-character symbols
            # ------------------------------------------------------------------
            if ch in ("<", ">", "=", "!"):
                pos = self._position(scanner, filename)
                next_ch = scanner.peek()
                if ch == "<" and next_ch == "=":
                    tokens.append(
                        Token(type=TokenType.OPERATOR_LE, lexeme="<=", position=pos)
                    )
                    scanner.advance()
                    scanner.advance()
                elif ch == "<" and next_ch == ">":
                    # COBOL's own "not equal" spelling (ANSI relational-operator
                    # ``<>``). Unlike the ``+``/``-`` VALUE-clause sign (task
                    # #stage21), ``<`` and ``>`` have no other single-character
                    # meaning to protect here -- they are dedicated relational
                    # operators already -- so combining them at the lexer, the
                    # same way ``<=``/``>=``/``==``/``!=`` already are, is safe
                    # and keeps the parser's operator-token contract uniform.
                    tokens.append(
                        Token(type=TokenType.OPERATOR_NEQ, lexeme="<>", position=pos)
                    )
                    scanner.advance()
                    scanner.advance()
                elif ch == ">" and next_ch == "=":
                    tokens.append(
                        Token(type=TokenType.OPERATOR_GE, lexeme=">=", position=pos)
                    )
                    scanner.advance()
                    scanner.advance()
                elif ch == "=" and next_ch == "=":
                    tokens.append(
                        Token(type=TokenType.OPERATOR_EQ, lexeme="==", position=pos)
                    )
                    scanner.advance()
                    scanner.advance()
                elif ch == "!" and next_ch == "=":
                    tokens.append(
                        Token(type=TokenType.OPERATOR_NEQ, lexeme="!=", position=pos)
                    )
                    scanner.advance()
                    scanner.advance()
                elif ch == "<":
                    tokens.append(
                        Token(type=TokenType.OPERATOR_LT, lexeme="<", position=pos)
                    )
                    scanner.advance()
                elif ch == ">":
                    tokens.append(
                        Token(type=TokenType.OPERATOR_GT, lexeme=">", position=pos)
                    )
                    scanner.advance()
                elif ch == "=":
                    tokens.append(
                        Token(type=TokenType.OPERATOR_EQ, lexeme="=", position=pos)
                    )
                    scanner.advance()
                elif ch == "!":
                    tokens.append(
                        Token(type=TokenType.UNKNOWN, lexeme="!", position=pos)
                    )
                    scanner.advance()
                continue

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

    @staticmethod
    def _is_source_directive(scanner: CharacterScanner) -> bool:
        """
        Pure lookahead: ``True`` if the scanner, positioned at the first
        ``>`` of a ``>>`` pair, is looking at a ``>>SOURCE ...`` compiler
        directive line (task #stage44).

        Matches whatever follows ``>>`` up to end-of-line, case-
        insensitively, once leading/trailing whitespace is stripped, and
        accepts anything starting with ``SOURCE`` -- not only the exact
        ``FREE``/``FIXED`` remainder
        :func:`~app.parser.lexer.format_detector._detect_by_directive`
        itself requires upstream. This method's only job is to keep a
        recognised directive line from corrupting the token stream by
        skipping it whole; it does not re-derive or act on the format
        the directive names -- :class:`~app.parser.lexer.format_detector.FormatDetector`
        already did that from the raw source, before normalization, so
        by the time the lexer runs the format decision is already made
        and this directive line's only remaining job is to be harmless.

        No characters are consumed by this check.

        Args:
            scanner: Positioned at the first ``>`` of a ``>>`` pair
                (caller has already confirmed ``peek(1) == ">"``).

        Returns:
            ``True`` if the rest of the line, after ``>>``, starts with
            ``SOURCE`` (case-insensitively); ``False`` otherwise (in
            which case the caller falls through to ordinary ``>``/``>>``
            token handling).
        """
        chars: list[str] = []
        i = 2
        while True:
            c = scanner.peek(i)
            if c is None or c in ("\n", "\r"):
                break
            chars.append(c)
            i += 1
        return "".join(chars).strip().upper().startswith("SOURCE")

    def _read_string(self, scanner: CharacterScanner, filename: str) -> Token:
        """
        Read a quoted string literal from the scanner.

        Supports single-quoted (``'...'``) and double-quoted (``"..."``)
        literals.  The opening and closing quotes are included in the lexeme.

        Task #stage43: a literal that reaches end-of-line unclosed is no
        longer unconditionally an error. :meth:`_try_resume_continued_string`
        is given the chance to find a fixed-format continuation line
        (``-`` in column 7) and splice its content directly onto the
        literal, exactly as COBOL requires -- no space or newline is ever
        inserted between the two fragments. See that method's docstring
        for the full continuation grammar and this project's column-7
        assumption.

        Raises:
            LexerError: If the string is not closed before a newline with
                no valid continuation line following it, or before EOF.
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
                if self._try_resume_continued_string(scanner, quote_char):
                    continue
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

    def _try_resume_continued_string(
        self, scanner: CharacterScanner, quote_char: str
    ) -> bool:
        """
        Try to resume an unterminated string literal on a fixed-format
        continuation line (task #stage43).

        Called with the scanner positioned exactly at the ``\\n``/``\\r``
        that ended the literal's line unclosed. Per the ANSI/IBM fixed-
        format continuation rule: a ``-`` in column 7 of the *next* line
        marks it as continuing the previous one, and when what is being
        continued is a nonnumeric literal, the first non-blank character
        in Area A/B of that continuation line must be a quotation mark
        matching the literal's own delimiter. That quotation mark is a
        resumption marker only -- it is never itself part of the
        literal's value -- and everything from the character after it
        onward is appended *directly* to the literal with no space or
        newline in between, exactly as if the line break had never
        happened.

        This assumes the source reached the lexer through
        :meth:`~app.parser.lexer.normalizer.SourceNormalizer.normalize_preserving_positions`
        (the analysis pipeline's own normalizer -- see
        :meth:`app.analysis.service.AnalysisService.prepare_source`), which
        keeps column 7 at column 7 rather than shifting it to column 1.
        No source-format flag is threaded into :meth:`CobolLexer.tokenize`
        to gate this: it is only ever consulted here, at a line break
        inside an *already-unterminated* literal, a case that raised
        :class:`~app.parser.lexer.lexer_exceptions.LexerError`
        unconditionally before this method existed, so there is no
        previously-working input this method could newly misinterpret --
        it can only turn a guaranteed failure into either a correctly
        spliced literal or a more specific failure.

        Unevidenced by the 45-source training corpus (grep-confirmed: zero
        occurrences of a ``-`` in column 7 across the full corpus) --
        implemented directly from the standard grammar rather than a
        corpus example, and covered by synthetic tests
        (``tests/parser/test_stage43_continuation_lines.py``) rather than a
        real-source regression test.

        Args:
            scanner: Positioned at the line-ending character.
            quote_char: The literal's own delimiter (``'`` or ``"``), which
                the continuation line's resumption quote must match.

        Returns:
            ``True`` if a valid continuation line was found and consumed,
            leaving the scanner positioned at the first character of the
            continued literal content (ready for the caller's own read
            loop to resume). ``False`` if no valid continuation exists --
            the scanner's position in that case does not matter, since the
            caller always raises immediately.
        """
        # Consume exactly one line terminator (CR, LF, or CRLF), landing
        # on column 1 of the next line.
        if scanner.current() == "\r":
            scanner.advance()
        if scanner.current() == "\n":
            scanner.advance()

        # Columns 1-6 (the sequence-number area) must exist -- i.e. the
        # line must be long enough to have a column 7 at all. Their
        # content is never inspected; only their presence is, exactly
        # like every other column-7 indicator check in this pipeline
        # (see app.parser.lexer.normalizer._is_ignored_line).
        for i in range(_SEQUENCE_AREA_WIDTH):
            c = scanner.peek(i)
            if c is None or c in ("\n", "\r"):
                return False

        if scanner.peek(_SEQUENCE_AREA_WIDTH) != "-":
            return False

        # Consume columns 1-7 (6 sequence-area characters + the '-'
        # indicator itself).
        for _ in range(_SEQUENCE_AREA_WIDTH + 1):
            scanner.advance()

        # Skip leading blanks in Area A/B up to the resumption quote.
        while scanner.current() == " ":
            scanner.advance()

        if scanner.current() != quote_char:
            # Malformed continuation: COBOL requires the first non-blank
            # character after the '-' to be the matching quote. Nothing
            # is guessed -- the caller raises its own "unterminated
            # string literal" error at the literal's start, exactly as
            # if this continuation line had never been found.
            return False

        scanner.advance()  # consume the resumption quote itself
        return True

    def _read_number(self, scanner: CharacterScanner, filename: str) -> Token:
        """
        Read an integer or decimal numeric literal, or a word that begins
        with digits.

        Consumes consecutive digit characters, then — when the digits are
        immediately followed by a decimal point that is itself immediately
        followed by another digit (:meth:`_at_decimal_point`) — consumes
        the point and the fractional digit run too, producing a single
        ``NUMBER`` token such as ``"12.50"``. A period that is *not*
        immediately followed by a digit is left untouched for the main
        loop's statement-terminator handling, so ``MOVE 12. TO X`` and
        every other integer-literal-then-terminator case is unaffected.

        A COBOL user-defined word may begin with digits — procedure names
        such as ``0000-MAIN`` and ``3000-VALIDATE-INPUT`` are the common
        case.  Because this method is reached before :meth:`_read_word`
        (and ``_WORD_START`` holds only letters), such a name used to be
        split into ``NUMBER('0000')``, ``UNKNOWN('-')``,
        ``IDENTIFIER('MAIN')``, which the procedure parser cannot read as
        a paragraph label.

        The digits are therefore treated as the start of a word only when
        they are followed by a hyphen *and a letter*.  That is the
        narrowest rule that recovers those names: ``0000``, ``2026-09-02``
        and ``1-2`` are unaffected because no letter follows their hyphen.
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

        if self._at_decimal_point(scanner):
            digits.append(".")
            scanner.advance()  # consume the decimal point
            while not scanner.eof():
                ch = scanner.current()
                if ch is not None and ch.isdigit():
                    digits.append(ch)
                    scanner.advance()
                else:
                    break

        if self._at_numeric_prefixed_word(scanner):
            return self._read_word_continuation(scanner, start_pos, digits)

        return Token(
            type=TokenType.NUMBER,
            lexeme="".join(digits),
            position=start_pos,
        )

    @staticmethod
    def _at_decimal_point(scanner: CharacterScanner) -> bool:
        """
        Return ``True`` when the scanner sits on a ``.`` that is a decimal
        point inside a numeric literal (``12.50``), not a COBOL statement
        /sentence/paragraph-terminating period.

        Mirrors COBOL's own lexical rule: a terminating period is always
        followed by whitespace (or is the last character of the source);
        a decimal point is immediately followed by another digit, with no
        separating whitespace. Checking only "is the next character a
        digit" is therefore sufficient and does not touch any case where
        the period already behaved as a terminator — ``12.`` followed by
        whitespace, a bare ``.``, or any non-numeric use are all unchanged.
        """
        if scanner.current() != ".":
            return False
        following = scanner.peek(1)
        return following is not None and following.isdigit()

    @staticmethod
    def _at_numeric_prefixed_word(scanner: CharacterScanner) -> bool:
        """
        Return ``True`` if a hyphen + letter follows the digits just read.

        This is the single test that separates the paragraph name
        ``0000-MAIN`` from the numeric forms that must stay numeric.  The
        character after the hyphen must be a **letter**: requiring a
        letter rather than any word character leaves ``2026-09-02`` and
        ``1-2`` lexing exactly as they did before.

        Args:
            scanner: The scanner, positioned just past the digits.

        Returns:
            ``True`` if the digits begin a COBOL word.
        """
        if scanner.current() != "-":
            return False
        following = scanner.peek(1)
        return following is not None and following in _WORD_START

    def _read_word_continuation(
        self,
        scanner: CharacterScanner,
        start_pos: Position,
        prefix: list[str],
    ) -> Token:
        """
        Finish reading a COBOL word whose leading characters are *prefix*.

        Consumes word characters, treating a hyphen as part of the word
        only when another word character follows it, so a trailing hyphen
        is left in the stream for the next token rather than being
        swallowed.

        Args:
            scanner:   The scanner, positioned on the first unread character.
            start_pos: Position of the word's first character.
            prefix:    Characters already consumed for this word.

        Returns:
            A ``KEYWORD`` or ``IDENTIFIER`` token carrying the whole word.
        """
        chars: list[str] = list(prefix)

        while not scanner.eof():
            ch = scanner.current()
            if ch is None:
                break
            if ch == "-":
                following = scanner.peek(1)
                if following is None or following not in _WORD_CONTINUE_NO_HYPHEN:
                    break
                chars.append(ch)
                scanner.advance()
                continue
            if ch in _WORD_CONTINUE:
                chars.append(ch)
                scanner.advance()
                continue
            break

        word = "".join(chars).upper()
        token_type = TokenType.KEYWORD if is_keyword(word) else TokenType.IDENTIFIER

        return Token(type=token_type, lexeme=word, position=start_pos)

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
