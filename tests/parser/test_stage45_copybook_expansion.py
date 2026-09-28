"""
Stage 45 — COPY-book expansion.

Purpose:
    Before this stage, ``COPY member-name [OF|IN library] [REPLACING
    ...].`` was entirely unrepresented: every syntax parser's own module
    docstring listed "COPY book expansion" as a Non-responsibility, and
    the token ``COPY`` reached ``DataDivisionParser``/
    ``ProcedureDivisionParser`` as an ordinary unexpected token --
    confirmed directly: ``COPY CUSTREC.`` in a ``WORKING-STORAGE
    SECTION`` produced ``SYN001 "unexpected token 'COPY'"`` and the
    copybook's fields were simply never seen.

    ``app.parser.resolver.copybook.CopybookExpander`` (task #stage45)
    now runs as its own pipeline stage, right after source-format
    detection/normalization and before lexing
    (``AnalysisService.analyze_file``'s "Stage 0.75"): it tokenizes the
    normalized text with the existing ``CobolLexer`` (reused, not
    duplicated) to find each ``COPY`` statement's exact span, resolves
    the member name to a file via the source file's own directory,
    recursively format-detects/normalizes/expands that file's own
    content (reusing ``AnalysisService.prepare_source``), applies any
    ``REPLACING`` pseudo-text substitutions, and splices the result in
    place of the ``COPY`` statement -- before the lexer/parser ever run.

Corpus evidence:
    Zero. Grep-confirmed directly across all 45 training-corpus and 17
    held-out evaluation-corpus sources: none contain a ``COPY``
    statement. Implemented from the standard ``COPY``/``REPLACING``
    grammar, not a corpus example -- the same category of decision as
    tasks #stage43/#stage44 -- covered here by synthetic copybook
    fixtures instead of a real-source regression test.

Non-responsibilities (see ``app/parser/resolver/copybook.py``'s own
module docstring for the full rationale):
    - Cross-file diagnostic provenance: a diagnostic inside expanded
      copybook content reports its line in the flattened text, under
      the main program's filename, not the copybook's own file/line.
    - The identifier-by-identifier / literal-by-literal ``REPLACING``
      forms, or the standalone ``REPLACE`` statement.
    - A ``COPY`` statement that itself spans a fixed-format
      continuation line.

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
from app.parser.resolver.copybook import (
    CircularCopyError,
    CopybookExpander,
    CopybookNotFoundError,
    MalformedCopyStatementError,
)

_HEADER = (
    "IDENTIFICATION DIVISION.\n"
    "PROGRAM-ID. T.\n"
    "DATA DIVISION.\n"
    "WORKING-STORAGE SECTION.\n"
)


def _write(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


def _analyze(tmp_path: Path, body: str):
    path = _write(tmp_path, "t.cbl", _HEADER + body)
    return AnalysisService().analyze_file(path)


# ===========================================================================
# 1. Basic expansion
# ===========================================================================


class TestBasicExpansion:
    def test_bare_copy_statement_pulls_in_fields(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "CUSTREC.cpy",
            "01 CUSTOMER-RECORD.\n   05 CUST-ID PIC 9(5).\n   05 CUST-NAME PIC X(20).\n",
        )
        result = _analyze(
            tmp_path,
            "COPY CUSTREC.\n"
            "PROCEDURE DIVISION.\nMAIN-PARA.\n"
            "    MOVE 1 TO CUST-ID.\n    STOP RUN.\n",
        )
        assert result.success is True
        assert result.syntax_diagnostics == []
        assert "private int custId;" in result.java_source
        assert "private String custName;" in result.java_source

    def test_copybook_extension_is_optional(self, tmp_path: Path) -> None:
        """The member name is also tried with no extension at all."""
        _write(tmp_path, "CUSTREC", "01 CUST-ID PIC 9(5).\n")
        result = _analyze(
            tmp_path,
            "COPY CUSTREC.\nPROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n",
        )
        assert result.success is True
        assert "private int custId;" in result.java_source

    def test_of_library_narrows_the_search_directory(self, tmp_path: Path) -> None:
        lib = tmp_path / "LIB"
        lib.mkdir()
        _write(lib, "CUSTREC.cpy", "01 CUST-ID PIC 9(5).\n")
        result = _analyze(
            tmp_path,
            "COPY CUSTREC OF LIB.\n" "PROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n",
        )
        assert result.success is True
        assert "private int custId;" in result.java_source

    def test_in_library_is_a_synonym_for_of(self, tmp_path: Path) -> None:
        lib = tmp_path / "LIB"
        lib.mkdir()
        _write(lib, "CUSTREC.cpy", "01 CUST-ID PIC 9(5).\n")
        result = _analyze(
            tmp_path,
            "COPY CUSTREC IN LIB.\n" "PROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n",
        )
        assert result.success is True
        assert "private int custId;" in result.java_source

    def test_expanded_program_compiles_and_runs(self, tmp_path: Path) -> None:
        _write(tmp_path, "CUSTREC.cpy", "01 CUST-ID PIC 9(5).\n")
        result = _analyze(
            tmp_path,
            "COPY CUSTREC.\n"
            "PROCEDURE DIVISION.\nMAIN-PARA.\n"
            "    MOVE 42 TO CUST-ID.\n"
            "    DISPLAY CUST-ID.\n"
            "    STOP RUN.\n",
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
        assert run.stdout.strip() == "00042"

    def test_no_copy_statement_is_unaffected(self, tmp_path: Path) -> None:
        """The fast-path substring pre-check must never change behavior
        for the overwhelming majority of sources with no COPY at all."""
        result = _analyze(
            tmp_path,
            "01 WS-X PIC 9(5).\nPROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n",
        )
        assert result.success is True
        assert result.syntax_diagnostics == []


# ===========================================================================
# 2. REPLACING
# ===========================================================================


class TestReplacing:
    def test_pseudo_text_substitution(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "CUSTREC.cpy",
            "01 :PREFIX:-RECORD.\n   05 :PREFIX:-ID PIC 9(5).\n",
        )
        result = _analyze(
            tmp_path,
            "COPY CUSTREC REPLACING ==:PREFIX:== BY ==CUST==.\n"
            "PROCEDURE DIVISION.\nMAIN-PARA.\n"
            "    MOVE 1 TO CUST-ID.\n    STOP RUN.\n",
        )
        assert result.success is True
        assert result.syntax_diagnostics == []
        assert "private int custId;" in result.java_source

    def test_multiple_replacing_pairs(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "CUSTREC.cpy",
            "01 :A:-REC.\n   05 :A:-ID PIC 9(5).\n   05 :B:-NAME PIC X(10).\n",
        )
        result = _analyze(
            tmp_path,
            "COPY CUSTREC REPLACING ==:A:== BY ==CUST== ==:B:== BY ==CUST==.\n"
            "PROCEDURE DIVISION.\nMAIN-PARA.\n"
            "    MOVE 1 TO CUST-ID.\n    STOP RUN.\n",
        )
        assert result.success is True
        assert "private int custId;" in result.java_source
        assert "private String custName;" in result.java_source

    def test_replacing_is_whitespace_tolerant(self, tmp_path: Path) -> None:
        """COBOL's own REPLACING semantics: the old pseudo-text matches
        regardless of incidental spacing differences in the copybook."""
        _write(tmp_path, "CUSTREC.cpy", "01   :PREFIX:-ID   PIC 9(5).\n")
        result = _analyze(
            tmp_path,
            "COPY CUSTREC REPLACING ==:PREFIX:== BY ==CUST==.\n"
            "PROCEDURE DIVISION.\nMAIN-PARA.\n"
            "    MOVE 1 TO CUST-ID.\n    STOP RUN.\n",
        )
        assert result.success is True
        assert "private int custId;" in result.java_source

    def test_replacing_is_case_insensitive(self, tmp_path: Path) -> None:
        _write(tmp_path, "CUSTREC.cpy", "01 :prefix:-ID PIC 9(5).\n")
        result = _analyze(
            tmp_path,
            "COPY CUSTREC REPLACING ==:PREFIX:== BY ==CUST==.\n"
            "PROCEDURE DIVISION.\nMAIN-PARA.\n"
            "    MOVE 1 TO CUST-ID.\n    STOP RUN.\n",
        )
        assert result.success is True
        assert "private int custId;" in result.java_source


# ===========================================================================
# 3. Nested COPY
# ===========================================================================


class TestNestedCopy:
    def test_a_copybook_may_itself_copy_another(self, tmp_path: Path) -> None:
        _write(tmp_path, "INNER.cpy", "   05 CUST-ID PIC 9(5).\n")
        _write(tmp_path, "OUTER.cpy", "01 CUSTOMER-RECORD.\n   COPY INNER.\n")
        result = _analyze(
            tmp_path,
            "COPY OUTER.\n"
            "PROCEDURE DIVISION.\nMAIN-PARA.\n"
            "    MOVE 1 TO CUST-ID.\n    STOP RUN.\n",
        )
        assert result.success is True
        assert "private int custId;" in result.java_source

    def test_circular_copy_is_detected(self, tmp_path: Path) -> None:
        _write(tmp_path, "A.cpy", "   COPY B.\n")
        _write(tmp_path, "B.cpy", "   COPY A.\n")
        result = _analyze(
            tmp_path,
            "COPY A.\nPROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n",
        )
        assert result.success is False
        assert isinstance(result.error, CircularCopyError)

    def test_self_referencing_copy_is_detected(self, tmp_path: Path) -> None:
        _write(tmp_path, "A.cpy", "   COPY A.\n")
        result = _analyze(
            tmp_path,
            "COPY A.\nPROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n",
        )
        assert result.success is False
        assert isinstance(result.error, CircularCopyError)


# ===========================================================================
# 4. Error handling
# ===========================================================================


class TestErrorHandling:
    def test_missing_copybook_is_a_clean_failure(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "COPY NOPE.\nPROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n",
        )
        assert result.success is False
        assert isinstance(result.error, CopybookNotFoundError)

    def test_copy_with_no_member_name_is_a_clean_failure(self, tmp_path: Path) -> None:
        result = _analyze(
            tmp_path,
            "COPY.\nPROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n",
        )
        assert result.success is False
        assert isinstance(result.error, MalformedCopyStatementError)

    def test_unrelated_lexer_error_still_surfaces_cleanly(self, tmp_path: Path) -> None:
        """CopybookExpander's own internal tokenize pass must not let an
        unrelated LexerError (a genuinely unterminated string literal,
        nothing to do with COPY) escape uncaught -- it should surface
        through the exact same clean ``AnalysisResult(success=False)``
        path Stage 1 (lex) would have produced for it anyway."""
        result = _analyze(tmp_path, "01 WS-X PIC X(4) VALUE 'UNCLOSED.\n")
        assert result.success is False
        assert result.error is not None


# ===========================================================================
# 5. Direct CopybookExpander unit tests
# ===========================================================================


class TestCopybookExpanderUnit:
    def test_expand_is_a_no_op_without_a_copy_statement(self, tmp_path: Path) -> None:
        source = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\n"
        assert CopybookExpander([tmp_path]).expand(source, "t.cbl") == source

    def test_expand_returns_flattened_text(self, tmp_path: Path) -> None:
        _write(tmp_path, "X.cpy", "01 WS-X PIC 9(5).\n")
        out = CopybookExpander([tmp_path]).expand("COPY X.\n", "t.cbl")
        assert "01 WS-X PIC 9(5)." in out
        assert "COPY" not in out.upper()


# ===========================================================================
# 6. Corpus evidence check
# ===========================================================================


def test_no_corpus_source_uses_copy() -> None:
    """Confirmed directly, not assumed: this feature has zero real-corpus
    coverage across both the training and held-out evaluation corpora."""
    hits = [
        rec.source_id
        for rec in list(load_training_corpus()) + list(load_evaluation_corpus())
        if "COPY" in rec.source.upper()
    ]
    assert hits == []
