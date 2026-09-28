"""
Stage 43 — fixed-format continuation-line support for string literals.

Purpose:
    A ``-`` in column 7 of a fixed-format COBOL line marks it as
    continuing the line before it. For an ordinary statement that simply
    runs long, this lexer already reads tokens straight across the line
    break with no special handling needed -- whitespace and newlines are
    both just token separators. The one case that actually *requires*
    continuation-line support is a quoted (nonnumeric) literal that does
    not fit on one line: before this stage, ``CobolLexer._read_string``
    hit the line's end still inside the quotes and unconditionally raised
    ``LexerError("unterminated string literal")`` -- confirmed directly,
    not assumed: every test below that expects success used to raise that
    exact error prior to this stage's fix.

    ``CobolLexer._try_resume_continued_string`` (called from
    ``_read_string`` exactly at that failure point) checks whether the
    next line has ``-`` in column 7; if so, per the ANSI/IBM rule, the
    first non-blank character in that line's Area A/B must be a
    quotation mark matching the literal's own delimiter. That quote is a
    resumption marker only -- never part of the value -- and everything
    after it is appended *directly* to the literal with no space or
    newline inserted, exactly as COBOL requires. Chained continuations
    (a continuation line that is itself too long) work by the same
    check re-firing at the next line break, with no extra code.

    This assumes the analysis pipeline's own
    ``SourceNormalizer.normalize_preserving_positions`` output, which
    keeps column 7 at column 7 (never shifts it) -- see
    ``app/parser/lexer/lexer.py``'s own docstring on
    ``_try_resume_continued_string`` for why no source-format flag is
    threaded through ``CobolLexer.tokenize`` to gate this.

Corpus evidence:
    Zero. Grep-confirmed directly: none of the 45 training-corpus sources
    (nor the 17 held-out benchmark sources) contain a ``-`` in column 7
    anywhere (see ``test_no_corpus_source_has_a_continuation_line``
    below). This feature is implemented from the standard fixed-format
    grammar rule, not from a real corpus example, and is covered here by
    synthetic sources instead of a real-source regression test -- the
    same category of decision as, e.g., the ``COMPUTATIONAL*`` USAGE
    aliases (task #stage41), which are equally unevidenced but equally
    unambiguous, standard COBOL syntax.

Non-responsibilities:
    - Continuation of anything other than a quoted literal (a PICTURE
      character-string continuation is a separate, rarer, unevidenced
      case -- out of scope).
    - The ``>>SOURCE FREE|FIXED`` compiler directive -- a separate
      roadmap item, deliberately not touched here.
    - COBOL's doubled-quote literal-escaping rule (``'IT''S'`` meaning
      ``IT'S``) -- a separate, pre-existing gap this lexer never
      implemented either way; unaffected by this stage.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.analysis.service import AnalysisService
from app.dataset.corpus import load_evaluation_corpus, load_training_corpus
from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.lexer_exceptions import LexerError
from app.parser.lexer.token_types import TokenType

_HEADER = (
    "000100 IDENTIFICATION DIVISION.\n"
    "000200 PROGRAM-ID. T.\n"
    "000300 DATA DIVISION.\n"
    "000400 WORKING-STORAGE SECTION.\n"
    "000500 01 WS-MSG PIC X(80).\n"
    "000600 PROCEDURE DIVISION.\n"
    "000700 MAIN-PARA.\n"
)


def _analyze(body: str, tmp_path: Path):
    path = tmp_path / "t.cbl"
    path.write_text(_HEADER + body, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _move_value(java: str) -> str:
    import re

    m = re.search(r"wsMsg = (.*?);", java)
    assert m, java
    return m.group(1)


# ===========================================================================
# 1. Real pipeline: the literal splices correctly
# ===========================================================================


class TestLiteralSplicing:
    def test_single_continuation_single_quote(self, tmp_path: Path) -> None:
        result = _analyze(
            "000800     MOVE 'THIS IS A VERY LONG MESSAGE THAT NEEDS TO CONT\n"
            "000900-    'INUE ONTO A SECOND LINE' TO WS-MSG.\n"
            "001000     STOP RUN.\n",
            tmp_path,
        )
        assert result.success is True
        assert result.syntax_diagnostics == []
        assert _move_value(result.java_source) == (
            '"THIS IS A VERY LONG MESSAGE THAT NEEDS TO CONTINUE ONTO A SECOND LINE"'
        )

    def test_single_continuation_double_quote(self, tmp_path: Path) -> None:
        result = _analyze(
            '000800     MOVE "AAAA\n'
            '000900-    "BBBB" TO WS-MSG.\n'
            "001000     STOP RUN.\n",
            tmp_path,
        )
        assert result.success is True
        assert _move_value(result.java_source) == '"AAAABBBB"'

    def test_chained_three_line_continuation(self, tmp_path: Path) -> None:
        result = _analyze(
            "000800     MOVE 'AAAA\n"
            "000900-    'BBBB\n"
            "001000-    'CCCC' TO WS-MSG.\n"
            "001100     STOP RUN.\n",
            tmp_path,
        )
        assert result.success is True
        assert _move_value(result.java_source) == '"AAAABBBBCCCC"'

    def test_leading_blanks_before_resumption_quote_are_skipped(
        self, tmp_path: Path
    ) -> None:
        """The resumption quote may sit anywhere in Area A/B, not only
        immediately after column 7."""
        result = _analyze(
            "000800     MOVE 'AAAA\n"
            "000900-        'BBBB' TO WS-MSG.\n"
            "001000     STOP RUN.\n",
            tmp_path,
        )
        assert result.success is True
        assert _move_value(result.java_source) == '"AAAABBBB"'

    def test_no_space_or_newline_at_the_splice_point(self, tmp_path: Path) -> None:
        """The two fragments join directly -- proven with fragments that
        would visibly show a stray space or newline if one leaked in."""
        result = _analyze(
            "000800     MOVE 'LEFT\n"
            "000900-    'RIGHT' TO WS-MSG.\n"
            "001000     STOP RUN.\n",
            tmp_path,
        )
        assert _move_value(result.java_source) == '"LEFTRIGHT"'

    def test_spliced_literal_compiles_and_runs(self, tmp_path: Path) -> None:
        result = _analyze(
            "000800     MOVE 'THIS IS A VERY LONG MESSAGE THAT NEEDS TO CONT\n"
            "000900-    'INUE ONTO A SECOND LINE' TO WS-MSG.\n"
            "001000     DISPLAY WS-MSG.\n"
            "001100     STOP RUN.\n",
            tmp_path,
        )
        java_file = tmp_path / "T.java"
        java_file.write_text(result.java_source, encoding="utf-8")
        javac = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_file)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert javac.returncode == 0, javac.stderr
        run = subprocess.run(
            ["java", "-cp", str(tmp_path), "T"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert run.returncode == 0, run.stderr
        assert (
            run.stdout.strip()
            == "THIS IS A VERY LONG MESSAGE THAT NEEDS TO CONTINUE ONTO A SECOND LINE"
        )


# ===========================================================================
# 2. Malformed continuations still fail -- nothing is guessed
# ===========================================================================


class TestMalformedContinuationStillFails:
    def test_no_continuation_line_follows(self, tmp_path: Path) -> None:
        """Unchanged from before this stage: a genuinely unterminated
        literal with no ``-`` on the next line is still an error."""
        result = _analyze(
            "000800     MOVE 'AAAA\n"
            "000900     BBBB' TO WS-MSG.\n"
            "001000     STOP RUN.\n",
            tmp_path,
        )
        assert result.success is False
        assert isinstance(result.error, LexerError)

    def test_continuation_line_without_leading_quote(self, tmp_path: Path) -> None:
        """A ``-`` line whose first non-blank character is not a quote is
        not a valid literal continuation."""
        result = _analyze(
            "000800     MOVE 'AAAA\n"
            "000900-    BBBB' TO WS-MSG.\n"
            "001000     STOP RUN.\n",
            tmp_path,
        )
        assert result.success is False
        assert isinstance(result.error, LexerError)

    def test_continuation_line_with_mismatched_quote_type(self, tmp_path: Path) -> None:
        """The resumption quote must match the literal's own delimiter."""
        result = _analyze(
            "000800     MOVE 'AAAA\n"
            "000900-    \"BBBB' TO WS-MSG.\n"
            "001000     STOP RUN.\n",
            tmp_path,
        )
        assert result.success is False
        assert isinstance(result.error, LexerError)

    def test_short_next_line_cannot_have_column_7(self, tmp_path: Path) -> None:
        """A next line too short to reach column 7 is never mistaken for a
        continuation -- no crash, the ordinary unterminated error fires."""
        result = _analyze(
            "000800     MOVE 'AAAA\n" "00\n" "000900     STOP RUN.\n",
            tmp_path,
        )
        assert result.success is False
        assert isinstance(result.error, LexerError)

    def test_blank_next_line_is_not_a_continuation(self, tmp_path: Path) -> None:
        result = _analyze(
            "000800     MOVE 'AAAA\n" "\n" "000900     STOP RUN.\n",
            tmp_path,
        )
        assert result.success is False
        assert isinstance(result.error, LexerError)

    def test_unterminated_at_true_eof_still_fails(self, tmp_path: Path) -> None:
        result = _analyze("000800     MOVE 'AAAA", tmp_path)
        assert result.success is False
        assert isinstance(result.error, LexerError)


# ===========================================================================
# 3. Direct lexer-level tests (pre-normalized text, no sequence numbers)
# ===========================================================================


def _lex(source: str) -> list:
    return CobolLexer().tokenize(source, filename="t.cbl")


class TestLexerLevel:
    """The same behavior, driven directly at the lexer, on text shaped
    exactly like ``normalize_preserving_positions`` output (column 7 is
    index 6, not shifted)."""

    def test_ordinary_unterminated_strings_are_unaffected(self) -> None:
        """Every pre-existing unterminated-string case in
        ``test_lexer.py``/``test_lexer_regression.py`` has no column-7
        structure at all, so the short-line guard rejects them exactly as
        before -- confirmed here directly, not only by the full suite
        still passing."""
        with pytest.raises(LexerError):
            _lex('"HELLO\n"')
        with pytest.raises(LexerError):
            _lex("'WORLD")

    def test_column_7_continuation_spliced_at_lexer_level(self) -> None:
        source = "      MOVE 'AAAA\n" + " " * 6 + "-    'BBBB' TO X.\n"
        tokens = [t for t in _lex(source) if t.type is not TokenType.EOF]
        strings = [t for t in tokens if t.type is TokenType.STRING]
        assert len(strings) == 1
        assert strings[0].lexeme == "'AAAABBBB'"

    def test_spliced_token_keeps_its_start_position(self) -> None:
        """The token's own ``position`` is where the literal *opened*,
        unaffected by how many lines its content actually spans."""
        source = "      MOVE 'AAAA\n" + " " * 6 + "-    'BBBB' TO X.\n"
        tokens = [t for t in _lex(source) if t.type is TokenType.STRING]
        assert tokens[0].position.line == 1


# ===========================================================================
# 4. Corpus evidence check
# ===========================================================================


def test_no_corpus_source_has_a_continuation_line() -> None:
    """Confirmed directly, not assumed: this feature has zero real-corpus
    coverage across both the training and held-out evaluation corpora."""
    hits = []
    for rec in list(load_training_corpus()) + list(load_evaluation_corpus()):
        for i, line in enumerate(rec.source.splitlines()):
            if len(line) >= 7 and line[6] == "-":
                hits.append((rec.source_id, i + 1))
    assert hits == []
