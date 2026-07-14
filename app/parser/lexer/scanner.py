"""
COBOL Character Scanner.

Purpose:
    Provide the fourth stage of the COBOL compiler pipeline: a
    character-by-character cursor over normalized COBOL source text.

    The Character Scanner exposes a simple positional interface that the
    Lexer will use to read one character at a time, look ahead without
    consuming characters, and track precise source positions for error
    reporting and token construction.

Responsibilities:
    - Iterate over normalized source text one character at a time.
    - Support configurable lookahead without advancing the cursor.
    - Track the absolute byte offset, 1-based line number, and 1-based
      column number of the current character.
    - Detect and handle newline sequences (LF, CRLF, bare CR) so that
      line and column counts are always accurate.
    - Signal end-of-input via :meth:`eof`.
    - Raise :class:`~app.parser.lexer.scanner_exceptions.ScannerError`
      for invalid construction arguments.

Non-responsibilities:
    - Keyword recognition.
    - Identifier or number scanning.
    - Token creation of any kind.
    - Lexical analysis.
    - Parsing or AST construction.

Dependencies:
    - :mod:`app.parser.lexer.scanner_exceptions` — ``ScannerError``.
    - Python standard library only.

Pipeline Position:
    Source Reader → Format Detector → Normalizer → **Character Scanner**
    → Lexer → Parser

Examples:
    Iterating over every character in a source string::

        from app.parser.lexer.scanner import CharacterScanner

        scanner = CharacterScanner("HELLO\\nWORLD")
        while not scanner.eof():
            ch = scanner.current()
            print(ch, scanner.line, scanner.column)
            scanner.advance()

    Lookahead without consuming::

        scanner = CharacterScanner("AB")
        assert scanner.current() == "A"
        assert scanner.peek() == "B"      # peek offset=1 (default)
        assert scanner.current() == "A"   # cursor did not move

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.parser.lexer.scanner_exceptions import ScannerError

__all__ = ["CharacterScanner"]


class CharacterScanner:
    """
    A character-by-character cursor over normalized COBOL source text.

    The scanner maintains three position counters that are updated as
    :meth:`advance` is called:

    - ``offset``  — Zero-based index of the current character in *source*.
    - ``line``    — One-based line number of the current character.
    - ``column``  — One-based column number of the current character.

    Newline handling
    ~~~~~~~~~~~~~~~~
    When :meth:`advance` moves past a newline character the line counter is
    incremented and the column counter is reset to 1.  Both ``\\n`` and
    ``\\r`` are treated as line terminators; a ``\\r\\n`` sequence counts as
    a single newline (the ``\\n`` following a ``\\r`` does not increment the
    line counter again).

    EOF semantics
    ~~~~~~~~~~~~~
    :meth:`current` and :meth:`advance` return ``None`` when the cursor is
    at or past the end of the source.  :meth:`eof` returns ``True`` in that
    state.

    Args:
        source:
            The normalized COBOL source text to scan.  Must be a :class:`str`.

    Raises:
        ScannerError: If *source* is not a :class:`str`.

    Examples:
        >>> s = CharacterScanner("AB")
        >>> s.current()
        'A'
        >>> s.peek()
        'B'
        >>> s.advance()
        'B'
        >>> s.eof()
        False
        >>> s.advance()
        >>> s.eof()
        True
    """

    def __init__(self, source: str) -> None:
        if not isinstance(source, str):
            raise ScannerError(f"source must be a str, got {type(source).__name__!r}")

        self._source: str = source
        self._length: int = len(source)
        self._offset: int = 0
        self._line: int = 1
        self._column: int = 1

        # Flag to suppress the line-increment for the '\n' that follows a
        # '\r' (i.e. the second byte of a CRLF sequence).
        self._just_saw_cr: bool = False

        logger.debug("CharacterScanner initialized: {} chars", self._length)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def offset(self) -> int:
        """
        Zero-based absolute index of the current character in the source.

        Returns ``len(source)`` when :meth:`eof` is ``True``.

        Returns:
            Current offset as a non-negative :class:`int`.
        """
        return self._offset

    @property
    def line(self) -> int:
        """
        One-based line number of the current character.

        Starts at 1 and increments each time :meth:`advance` moves past a
        newline character.

        Returns:
            Current line number as a positive :class:`int`.
        """
        return self._line

    @property
    def column(self) -> int:
        """
        One-based column number of the current character.

        Starts at 1, increments with each :meth:`advance` call, and resets
        to 1 after a newline.

        Returns:
            Current column number as a positive :class:`int`.
        """
        return self._column

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def current(self) -> str | None:
        """
        Return the character at the current cursor position.

        Does **not** advance the cursor.

        Returns:
            The current character as a single-character :class:`str`, or
            ``None`` if the scanner has reached EOF.

        Examples:
            >>> CharacterScanner("A").current()
            'A'
            >>> CharacterScanner("").current() is None
            True
        """
        if self._offset >= self._length:
            return None
        return self._source[self._offset]

    def peek(self, offset: int = 1) -> str | None:
        """
        Return the character *offset* positions ahead of the cursor.

        The cursor is **not** moved.  ``peek(0)`` is equivalent to
        :meth:`current`; ``peek(1)`` (the default) returns the next
        character.

        Args:
            offset:
                Number of positions ahead to look.  Must be a non-negative
                integer.  Defaults to ``1``.

        Returns:
            The character at ``current_position + offset`` as a
            single-character :class:`str`, or ``None`` if that position is
            at or past EOF.

        Raises:
            ScannerError: If *offset* is negative.

        Examples:
            >>> s = CharacterScanner("ABC")
            >>> s.peek(0)
            'A'
            >>> s.peek(1)
            'B'
            >>> s.peek(2)
            'C'
            >>> s.peek(3) is None
            True
        """
        if offset < 0:
            raise ScannerError(f"peek offset must be non-negative, got {offset}")
        target = self._offset + offset
        if target >= self._length:
            return None
        return self._source[target]

    def advance(self) -> str | None:
        """
        Advance the cursor by one position and return the **new** current
        character.

        Position counters (``offset``, ``line``, ``column``) are updated
        before the new character is returned.  Calling :meth:`advance` when
        at EOF is safe and returns ``None``.

        Returns:
            The character now at the cursor (after advancing), or ``None``
            if the cursor has moved to or past EOF.

        Examples:
            >>> s = CharacterScanner("AB")
            >>> s.advance()
            'B'
            >>> s.advance() is None
            True
        """
        if self._offset >= self._length:
            return None

        ch = self._source[self._offset]
        self._update_position(ch)
        self._offset += 1

        if self._offset >= self._length:
            return None
        return self._source[self._offset]

    def eof(self) -> bool:
        """
        Return ``True`` when the cursor is at or past the end of the source.

        Returns:
            ``True`` if there are no more characters to consume, ``False``
            otherwise.

        Examples:
            >>> CharacterScanner("").eof()
            True
            >>> s = CharacterScanner("A")
            >>> s.eof()
            False
            >>> s.advance()
            >>> s.eof()
            True
        """
        return self._offset >= self._length

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_position(self, ch: str) -> None:
        """
        Update ``line`` and ``column`` counters as the scanner leaves *ch*.

        Called by :meth:`advance` with the character that is being consumed
        (i.e. the character *at* the current offset before the offset is
        incremented).

        Newline rules
        ~~~~~~~~~~~~~
        - ``\\n``  after a ``\\r`` (CRLF):  treat as a single newline; the
          ``\\r`` already incremented the line counter so the ``\\n`` is
          silently consumed (column resets but line does not increment again).
        - ``\\n``  standalone:  increment line, reset column.
        - ``\\r``  always increments line and resets column (and sets the
          ``_just_saw_cr`` flag so the following ``\\n`` is absorbed).
        - Any other character:  increment column only.

        Args:
            ch: The character currently at the cursor (before advance).
        """
        if ch == "\r":
            self._line += 1
            self._column = 1
            self._just_saw_cr = True
        elif ch == "\n":
            if self._just_saw_cr:
                # The '\r' already incremented the line; this '\n' is the
                # second byte of CRLF — absorb it without double-counting.
                self._just_saw_cr = False
            else:
                self._line += 1
                self._column = 1
        else:
            self._just_saw_cr = False
            self._column += 1
