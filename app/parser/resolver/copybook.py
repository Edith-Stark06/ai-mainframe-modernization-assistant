"""
COPY-book Expansion (task #stage45).

Purpose:
    Locate, read, and textually inline every ``COPY member-name [OF|IN
    library-name] [REPLACING ==old== BY ==new== ...].`` statement in a
    COBOL source, producing a single, flattened source text ready for
    the existing lexer/parser pipeline -- exactly as if the copybook's
    content had been typed in place of the ``COPY`` statement.

    ``COPY`` statement boundaries are found by tokenizing the
    (already format-detected and normalized) source with the existing
    :class:`~app.parser.lexer.lexer.CobolLexer` -- reused, not
    duplicated -- rather than a second, hand-rolled text scanner. This
    is what correctly ignores a ``COPY``-looking word inside a comment
    or a quoted literal for free: the lexer already strips comments and
    already knows what is and is not inside a string.

    Each resolved copybook is independently format-detected and
    normalized (:meth:`~app.analysis.service.AnalysisService.prepare_source`,
    reused) before being spliced in, so a copybook may be authored in
    either COBOL source format regardless of the program that ``COPY``
    -s it.

Position/provenance (a deliberate scope decision):
    A diagnostic whose position falls inside expanded copybook content
    reports a line number counted from the top of the *flattened*
    source, under the main program's own filename -- not the copybook's
    original file and line. Tracking true cross-file provenance would
    mean threading a line-by-line origin map through
    :class:`~app.parser.lexer.scanner.CharacterScanner`/
    :class:`~app.parser.lexer.position.Position` construction, touching
    every single diagnostic-producing call site in the entire pipeline,
    for a feature this project's own 45-source training corpus (and its
    17-source held-out evaluation corpus) has zero examples of to
    validate that machinery against. Confirmed directly, not assumed --
    see ``test_no_corpus_source_uses_copy`` in
    ``tests/parser/test_stage45_copybook_expansion.py``. This module
    keeps every character it inserts, so nothing is dropped or
    corrupted; only the *reported line number* for copybook-internal
    diagnostics is coarser than a real compiler's listing would be.

REPLACING (a deliberate scope decision):
    Only the pseudo-text form (``==old-text== BY ==new-text==``) is
    supported -- the identifier-by-identifier and literal-by-literal
    forms are not. Matching is token-sequence-based and whitespace-
    tolerant (COBOL's own ``REPLACING`` semantics: two pseudo-texts are
    "the same" if they contain the same token sequence, regardless of
    incidental spacing), built by tokenizing the pseudo-text spans with
    the same lexer and joining the resulting lexemes with a
    zero-or-more-whitespace regex, case-insensitively. ``new-text`` is
    substituted verbatim, exactly as captured from the source (not
    reconstructed from tokens), so its own original formatting survives.

Search path:
    A member name is resolved by trying, in order, against each search
    directory (the source file's own directory, plus any additional
    directories the caller supplies): the bare name, then with ``.cpy``,
    ``.CPY``, and ``.cbl`` appended -- each tried as written, upper-
    cased, and lower-cased, to tolerate case-sensitive filesystems.
    ``OF``/``IN library-name`` narrows the search to
    ``search_path / library-name`` instead of trying every directory.

Non-responsibilities:
    - ``REPLACE`` (the standalone, file-wide statement -- distinct from
      ``COPY ... REPLACING``).
    - The identifier-by-identifier / literal-by-literal ``REPLACING``
      forms.
    - Cross-file provenance for diagnostics (see above).
    - A copybook whose own ``COPY`` statement itself spans a fixed-
      format continuation line -- unevidenced, out of scope, matching
      task #stage43's own scope decision.

Responsibilities:
    - :class:`CopybookExpander` -- its :meth:`~CopybookExpander.expand`
      method resolves and inlines every ``COPY`` statement in a source,
      recursively, with circular-COPY detection.
    - :class:`CopybookNotFoundError`, :class:`MalformedCopyStatementError`,
      :class:`CircularCopyError` -- the specific, catchable failure modes.

Dependencies:
    - app.parser.lexer.lexer -- CobolLexer (reused, not duplicated)
    - app.parser.lexer.token -- Token
    - app.parser.lexer.token_types -- TokenType
    - loguru -- structured logging
    - Python standard library (re, dataclasses, pathlib).

Examples:
    Expanding a source's COPY statements::

        from app.parser.resolver.copybook import CopybookExpander

        expander = CopybookExpander(search_paths=[program_path.parent])
        expanded = expander.expand(source, filename=program_path.name)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType

__all__ = [
    "CircularCopyError",
    "CopybookExpander",
    "CopybookNotFoundError",
    "MalformedCopyStatementError",
]

_COPYBOOK_EXTENSIONS: tuple[str, ...] = ("", ".cpy", ".CPY", ".cbl")


class CopybookNotFoundError(Exception):
    """Raised when a ``COPY`` member name cannot be resolved to a file."""

    def __init__(self, member: str, search_paths: list[Path]) -> None:
        self.member = member
        self.search_paths = search_paths
        super().__init__(
            f"copybook {member!r} not found in: "
            + ", ".join(str(p) for p in search_paths)
        )


class MalformedCopyStatementError(Exception):
    """Raised when a ``COPY`` statement's grammar cannot be parsed (a
    missing member name, an unterminated ``REPLACING`` pseudo-text
    span, or the like)."""


class CircularCopyError(Exception):
    """Raised when a chain of ``COPY`` statements loops back on itself."""

    def __init__(self, member: str, chain: list[str]) -> None:
        self.member = member
        self.chain = chain
        super().__init__(
            f"circular COPY: {member!r} is already being expanded "
            f"({' -> '.join(chain)} -> {member})"
        )


@dataclass(frozen=True)
class _CopyStatement:
    """One recognised ``COPY ... .`` statement span within a token stream."""

    member: str
    library: str | None
    replacing: tuple[tuple[str, str], ...]
    start_offset: int
    end_offset: int  # exclusive, one past the terminating period


class CopybookExpander:
    """
    Recursively expand ``COPY`` statements in a COBOL source text.

    Instantiate once per analysis with the search directories to use;
    call :meth:`expand` with the main program's already-normalized text.
    """

    def __init__(self, search_paths: list[Path]) -> None:
        self._search_paths = search_paths

    def expand(self, source: str, filename: str, _stack: tuple[str, ...] = ()) -> str:
        """
        Return *source* with every ``COPY`` statement replaced by its
        resolved, normalized, ``REPLACING``-applied copybook content.

        Args:
            source: Already format-detected and normalized text (see
                :meth:`~app.analysis.service.AnalysisService.prepare_source`).
            filename: The originating file's name, used for diagnostics
                and to compute the default search directory once, by
                the caller -- this method does not read *filename* from
                disk itself.
            _stack: Internal recursion guard -- the uppercased member
                names currently being expanded, for circular-``COPY``
                detection. Callers never pass this.

        Returns:
            The fully expanded text. Unchanged from *source* (no
            copy, no cost beyond one tokenize-and-scan) when it
            contains no ``COPY`` statement.

        Raises:
            CopybookNotFoundError: A member name resolves to no file.
            CircularCopyError: A copybook (directly or transitively)
                copies itself.
        """
        text = source
        while "COPY" in text.upper():
            # Cheap fast-path: tokenizing (below) is the only way to
            # know for certain whether a "COPY" substring is a real
            # statement (versus part of a longer identifier, or inside
            # a comment/literal already stripped by normalization), but
            # that full tokenize pass is needless overhead for the
            # overwhelming majority of sources that contain the word
            # nowhere at all -- this substring pre-check is a strict
            # superset (every real statement contains this substring)
            # that costs O(n) string search instead of a full tokenize.
            tokens = CobolLexer().tokenize(text, filename=filename)
            stmt = _find_first_copy_statement(tokens, text)
            if stmt is None:
                return text

            member_key = stmt.member.upper()
            if member_key in _stack:
                raise CircularCopyError(stmt.member, list(_stack))

            path = self._resolve(stmt.member, stmt.library)
            logger.debug(
                "CopybookExpander: expanding COPY {!r} -> '{}'.", stmt.member, path
            )
            raw = path.read_text(encoding="utf-8")

            # Reuse AnalysisService's own format-detect + normalize --
            # imported here (not at module scope) to avoid a circular
            # import (app.analysis.service imports this module).
            from app.analysis.service import AnalysisService

            normalized = AnalysisService.prepare_source(raw, path)
            for old_text, new_text in stmt.replacing:
                normalized = _apply_replacing(normalized, old_text, new_text)

            expanded = self.expand(normalized, str(path), _stack + (member_key,))

            text = text[: stmt.start_offset] + expanded + text[stmt.end_offset :]

        return text

    def _resolve(self, member: str, library: str | None) -> Path:
        """Resolve *member* (optionally within *library*) to a file path."""
        directories = (
            [p / library for p in self._search_paths]
            if library
            else list(self._search_paths)
        )
        candidates: list[Path] = []
        for directory in directories:
            for name in (member, member.upper(), member.lower()):
                for ext in _COPYBOOK_EXTENSIONS:
                    candidates.append(directory / f"{name}{ext}")

        for candidate in candidates:
            if candidate.is_file():
                return candidate

        raise CopybookNotFoundError(member, directories)


def _find_first_copy_statement(
    tokens: list[Token], source: str
) -> _CopyStatement | None:
    """
    Scan *tokens* for the first ``COPY ... .`` statement.

    Args:
        tokens: The full token stream of *source* (including EOF).
        source: The exact text *tokens* was produced from, used to
            slice out each ``REPLACING`` pseudo-text span verbatim.

    Returns:
        The first :class:`_CopyStatement` found, or ``None`` if no
        ``COPY`` statement is present.
    """
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok.type is TokenType.IDENTIFIER and tok.lexeme.upper() == "COPY":
            return _parse_copy_statement(tokens, i, source)
        i += 1
    return None


def _parse_copy_statement(
    tokens: list[Token], start: int, source: str
) -> _CopyStatement:
    """Parse one ``COPY`` statement starting at ``tokens[start]``."""
    i = start + 1
    n = len(tokens)

    if i >= n or tokens[i].type is TokenType.PERIOD:
        raise MalformedCopyStatementError(
            "'COPY' with no member name before the terminating period"
        )
    member = tokens[i].lexeme
    i += 1

    library: str | None = None
    if i < n and tokens[i].lexeme.upper() in ("OF", "IN"):
        i += 1
        if i < n and tokens[i].type is not TokenType.PERIOD:
            library = tokens[i].lexeme
            i += 1

    replacing: list[tuple[str, str]] = []
    if i < n and tokens[i].lexeme.upper() == "REPLACING":
        i += 1
        while i < n and tokens[i].type is not TokenType.PERIOD:
            old_text, i = _consume_pseudo_text(tokens, i, source)
            if i < n and tokens[i].lexeme.upper() == "BY":
                i += 1
            new_text, i = _consume_pseudo_text(tokens, i, source)
            replacing.append((old_text, new_text))

    end = tokens[i].position.offset + 1 if i < n else len(source)
    return _CopyStatement(
        member=member,
        library=library,
        replacing=tuple(replacing),
        start_offset=tokens[start].position.offset,
        end_offset=end,
    )


def _consume_pseudo_text(tokens: list[Token], i: int, source: str) -> tuple[str, int]:
    """
    Consume one ``==...==`` pseudo-text span starting at ``tokens[i]``.

    Returns:
        A ``(text, next_index)`` pair: *text* is the exact source
        substring between the two ``==`` delimiters (not the delimiters
        themselves), and *next_index* is the token index immediately
        after the closing ``==``.
    """
    n = len(tokens)
    if i >= n or tokens[i].lexeme != "==":
        raise MalformedCopyStatementError(
            "'REPLACING' operand does not start with '==' pseudo-text delimiter"
        )
    open_end = tokens[i].position.offset + len(tokens[i].lexeme)
    i += 1
    while i < n and tokens[i].lexeme != "==":
        i += 1
    if i >= n:
        raise MalformedCopyStatementError("unterminated '==' pseudo-text span")
    close_start = tokens[i].position.offset
    text = source[open_end:close_start].strip()
    i += 1
    return text, i


def _apply_replacing(text: str, old_text: str, new_text: str) -> str:
    """
    Replace every occurrence of *old_text* in *text* with *new_text*.

    Matching is token-sequence-based and whitespace-tolerant, per
    COBOL's own ``REPLACING`` semantics -- see the module docstring.
    An *old_text* that tokenizes to nothing (blank pseudo-text) matches
    nothing and leaves *text* unchanged, rather than matching
    everywhere.
    """
    old_tokens = [
        t
        for t in CobolLexer().tokenize(old_text, filename="<replacing>")
        if t.type is not TokenType.EOF
    ]
    if not old_tokens:
        return text
    pattern = r"\s*".join(re.escape(t.lexeme) for t in old_tokens)
    return re.sub(pattern, lambda _m: new_text, text, flags=re.IGNORECASE)
