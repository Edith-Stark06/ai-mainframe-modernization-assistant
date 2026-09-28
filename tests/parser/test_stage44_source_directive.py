"""
Stage 44 — consume the ``>>SOURCE FREE|FIXED`` compiler directive.

Purpose:
    ``FormatDetector._detect_by_directive`` already recognised
    ``>>SOURCE FREE``/``>>SOURCE FIXED`` and used it as the highest-
    priority signal for the whole file's :class:`SourceFormat` -- that
    part of the roadmap item ("consume ... directives") was already done.
    What was missing is in the name too: *consuming* the directive line
    itself, so it does not reach the lexer as literal text. Neither
    normalizer path strips it (``FREE`` format is passed through
    unchanged; ``FIXED`` format has no special case for a directive line,
    since column-stripping does not know or care what the line's content
    means), so before this stage the two ``>`` characters reached the
    lexer's operator branch as two stray ``OPERATOR_GT`` tokens, followed
    by ``SOURCE``/``FREE`` (or ``FIXED``) as ordinary ``IDENTIFIER``
    tokens -- sitting exactly where ``IDENTIFICATION DIVISION`` was
    expected. Confirmed directly, not assumed: before this stage's fix,
    every "success" case below instead produced ``AnalysisResult(
    success=False, error=None)`` with zero syntax diagnostics and zero
    AST -- ``ProgramParser`` consumed 0 of the file's tokens and simply
    gave up, silently.

    ``CobolLexer`` now recognises ``>>SOURCE ...`` (case-insensitively,
    anywhere the ``>>`` pair appears) and skips the whole line, exactly
    like a comment -- see ``CobolLexer._is_source_directive``. It does
    not re-derive or act on the ``FREE``/``FIXED`` value itself:
    ``FormatDetector`` already made that call from the raw source, before
    normalization even ran, so by the time the lexer sees the directive
    line its only remaining job is to be harmless.

Corpus evidence:
    Zero. Grep-confirmed directly across all 45 training-corpus and 17
    held-out evaluation-corpus sources: none contain ``>>SOURCE``
    anywhere. Implemented from the standard compiler-directive grammar,
    not a corpus example -- the same category of decision as task
    #stage43 (continuation lines), covered here by synthetic sources.

Non-responsibilities:
    - Any ``>>`` directive other than ``>>SOURCE`` (``>>IF``,
      ``>>DEFINE``, ``>>CALL``, ...) -- conditional compilation is a
      separate, unevidenced, unscoped feature.
    - Re-deriving the source format at the lexer level -- that remains
      ``FormatDetector``'s job alone, run once, before normalization.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.analysis.service import AnalysisService
from app.dataset.corpus import load_evaluation_corpus, load_training_corpus
from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.token_types import TokenType


def _analyze(source: str, tmp_path: Path):
    path = tmp_path / "t.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


# ===========================================================================
# 1. Real pipeline: the directive no longer corrupts parsing
# ===========================================================================


class TestDirectiveIsConsumed:
    def test_source_free_at_top_parses(self, tmp_path: Path) -> None:
        result = _analyze(
            "       >>SOURCE FREE\n"
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. T.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-X PIC X(4) VALUE 'AUTO'.\n"
            "PROCEDURE DIVISION.\n"
            "MAIN-PARA.\n"
            "    DISPLAY WS-X.\n"
            "    STOP RUN.\n",
            tmp_path,
        )
        assert result.success is True
        assert result.error is None
        assert result.syntax_diagnostics == []
        assert "public class T {" in result.java_source

    def test_source_fixed_at_top_parses(self, tmp_path: Path) -> None:
        result = _analyze(
            "000100>>SOURCE FIXED\n"
            "000200 IDENTIFICATION DIVISION.\n"
            "000300 PROGRAM-ID. T.\n"
            "000400 DATA DIVISION.\n"
            "000500 WORKING-STORAGE SECTION.\n"
            "000600 01 WS-X PIC X(4) VALUE 'AUTO'.\n"
            "000700 PROCEDURE DIVISION.\n"
            "000800 MAIN-PARA.\n"
            "000900     DISPLAY WS-X.\n"
            "001000     STOP RUN.\n",
            tmp_path,
        )
        assert result.success is True
        assert result.error is None
        assert "public class T {" in result.java_source

    def test_directive_is_case_insensitive(self, tmp_path: Path) -> None:
        result = _analyze(
            "       >>source free\n"
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. T.\n"
            "PROCEDURE DIVISION.\n"
            "MAIN-PARA.\n"
            "    STOP RUN.\n",
            tmp_path,
        )
        assert result.success is True
        assert result.syntax_diagnostics == []

    def test_directive_after_some_code_still_consumed(self, tmp_path: Path) -> None:
        """``FormatDetector`` scans every line for the directive, so it
        need not be the first line to set the whole file's format; the
        lexer must likewise consume it wherever it appears, not only at
        column 1 of line 1."""
        result = _analyze(
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. T.\n"
            "       >>SOURCE FREE\n"
            "PROCEDURE DIVISION.\n"
            "MAIN-PARA.\n"
            "    STOP RUN.\n",
            tmp_path,
        )
        assert result.success is True
        assert result.syntax_diagnostics == []

    def test_spliced_program_compiles_and_runs(self, tmp_path: Path) -> None:
        result = _analyze(
            "       >>SOURCE FREE\n"
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. T.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-X PIC X(4) VALUE 'AUTO'.\n"
            "PROCEDURE DIVISION.\n"
            "MAIN-PARA.\n"
            "    DISPLAY WS-X.\n"
            "    STOP RUN.\n",
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
        assert run.stdout.strip() == "AUTO"


# ===========================================================================
# 2. Regression guard: ordinary '>' / '>=' usage is unaffected
# ===========================================================================


class TestOrdinaryOperatorsUnaffected:
    def test_greater_than_and_greater_equal_conditions(self, tmp_path: Path) -> None:
        result = _analyze(
            "IDENTIFICATION DIVISION.\n"
            "PROGRAM-ID. T.\n"
            "DATA DIVISION.\n"
            "WORKING-STORAGE SECTION.\n"
            "01 WS-A PIC 9(3) VALUE 5.\n"
            "PROCEDURE DIVISION.\n"
            "MAIN-PARA.\n"
            "    IF WS-A > 3\n"
            "        DISPLAY 'BIG'\n"
            "    END-IF.\n"
            "    IF WS-A >= 5\n"
            "        DISPLAY 'GE'\n"
            "    END-IF.\n"
            "    STOP RUN.\n",
            tmp_path,
        )
        assert result.success is True
        assert result.syntax_diagnostics == []

    def test_double_gt_not_followed_by_source_is_not_a_directive(self) -> None:
        """A lone ``>>`` that is not a ``SOURCE`` directive falls through
        to ordinary two-token ``>``/``>`` handling, unaffected."""
        tokens = CobolLexer().tokenize("A >> B\n", filename="t.cbl")
        kinds = [t.type for t in tokens if t.type is not TokenType.EOF]
        assert kinds == [
            TokenType.IDENTIFIER,
            TokenType.OPERATOR_GT,
            TokenType.OPERATOR_GT,
            TokenType.IDENTIFIER,
        ]


# ===========================================================================
# 3. Direct lexer-level: the directive line contributes zero tokens
# ===========================================================================


class TestLexerLevel:
    def test_directive_line_produces_no_tokens(self) -> None:
        tokens = CobolLexer().tokenize(
            "       >>SOURCE FREE\nMOVE A TO B.\n", filename="t.cbl"
        )
        non_eof = [t for t in tokens if t.type is not TokenType.EOF]
        assert [t.type for t in non_eof] == [
            TokenType.KEYWORD,
            TokenType.IDENTIFIER,
            TokenType.IDENTIFIER,
            TokenType.IDENTIFIER,
            TokenType.PERIOD,
        ]
        assert [t.lexeme for t in non_eof] == ["MOVE", "A", "TO", "B", "."]

    def test_directive_line_does_not_consume_the_following_line(self) -> None:
        """``_skip_to_eol`` stops at the newline; the next line's tokens
        are unaffected."""
        tokens = CobolLexer().tokenize(
            "       >>SOURCE FIXED\nSTOP RUN.\n", filename="t.cbl"
        )
        lexemes = [t.lexeme for t in tokens if t.type is not TokenType.EOF]
        assert lexemes == ["STOP", "RUN", "."]


# ===========================================================================
# 4. Corpus evidence check
# ===========================================================================


def test_no_corpus_source_has_a_source_directive() -> None:
    """Confirmed directly, not assumed: this feature has zero real-corpus
    coverage across both the training and held-out evaluation corpora."""
    hits = [
        rec.source_id
        for rec in list(load_training_corpus()) + list(load_evaluation_corpus())
        if ">>SOURCE" in rec.source.upper()
    ]
    assert hits == []
