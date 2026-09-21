"""
Fixed-format COBOL through :class:`~app.analysis.service.AnalysisService`.

Purpose:
    Regression tests for wiring the format detector and the
    position-preserving source normalizer into the analysis pipeline.
    Before the wiring a punch-card-layout program (sequence numbers,
    ``*`` comment lines, program-ID area) produced *no* diagnostics and
    *no* PROCEDURE DIVISION; comment lines in otherwise free-length
    sources produced spurious ``SYN003`` errors.

Responsibilities:
    - Card-layout source parses exactly like the same program without the
      card decoration (same AST, including every line/column).
    - Comment, debug, sequence and program-ID text never reach the parser.
    - Diagnostics carry original line/column coordinates.
    - Free-format source and unrecognised formats are not altered.
    - The 45-source corpus is never altered except for column-7 comment lines.
    - Continuation lines stay an explicit, loud limitation.

Dependencies:
    - :class:`app.analysis.service.AnalysisService`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.analysis.serializers.ast import serialize_ast
from app.analysis.service import AnalysisService
from app.dataset.corpus import load_training_corpus
from app.parser.lexer.lexer_exceptions import LexerError


def card(text: str, seq: str = "", ind: str = " ", ident: str = "") -> str:
    """One card image: cols 1-6 sequence, col 7 indicator, 8-72 text, 73-80 id."""
    assert len(text) <= 65
    line = f"{seq:<6}{ind}{text:<65}{ident}"
    return line if ident else line.rstrip()


BODY: list[tuple[str, str]] = [
    ("IDENTIFICATION DIVISION.", " "),
    ("PROGRAM-ID. FIXEDP.", " "),
    ("* THIS COMMENT MUST NOT BECOME TOKENS @#", "*"),
    ("DATA DIVISION.", " "),
    ("WORKING-STORAGE SECTION.", " "),
    ("01  WS-COUNT    PIC 9(2) VALUE 0.", " "),
    ("01  WS-CODE     PIC X(4) VALUE 'AUTO'.", " "),
    ("", " "),
    ("PROCEDURE DIVISION.", " "),
    ("MAIN-PARA.", " "),
    ("* COMMENT INSIDE THE PROCEDURE DIVISION", "*"),
    ("    IF WS-CODE = 'AUTO'", " "),
    ("        DISPLAY 'CODE-IS-AUTO'", " "),
    ("    ELSE", " "),
    ("        DISPLAY 'CODE-NOT-AUTO'", " "),
    ("    END-IF", " "),
    ("    PERFORM UNTIL WS-COUNT >= 3", " "),
    ("        ADD 1 TO WS-COUNT", " "),
    ("    END-PERFORM", " "),
    ("    DISPLAY 'DONE'", " "),
    ("    STOP RUN.", " "),
]


def build(*, seq: bool, ident: bool, comments: bool) -> str:
    """The BODY program as cards; ``comments=False`` blanks the comment lines."""
    out = []
    for n, (text, ind) in enumerate(BODY, start=1):
        s = f"{n * 100:06d}" if seq else ""
        i = f"PAYR{n:04d}" if ident else ""
        if ind == "*" and not comments:
            out.append(card("", seq=s, ident=i))
        else:
            out.append(card(text, seq=s, ind=ind, ident=i))
    return "\n".join(out) + "\n"


def analyze(tmp_path: Path, source: str, name: str = "prog.cbl", sub: str = "run"):
    directory = tmp_path / sub
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(source, encoding="utf-8", newline="\n")
    return AnalysisService().analyze_file(path)


def without_filename(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: without_filename(v) for k, v in obj.items() if k != "filename"}
    if isinstance(obj, list):
        return [without_filename(v) for v in obj]
    return obj


def ast_of(result: Any) -> str:
    return json.dumps(without_filename(serialize_ast(result.ast)), sort_keys=True)


def blank_reference(source: str) -> str:
    """Hand-normalized twin of *source*: same length, non-code columns spaces."""
    out = []
    for line in source.splitlines():
        if len(line) <= 6 or line[6] in "*/":
            out.append(" " * len(line))
        else:
            kept = line[6:72]
            out.append("      " + kept + " " * (len(line) - 6 - len(kept)))
    return "\n".join(out) + "\n"


@pytest.fixture(scope="module")
def reference(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """The full card program with its non-code columns already blank."""
    card_source = build(seq=True, ident=True, comments=True)
    return analyze(tmp_path_factory.mktemp("ref"), blank_reference(card_source))


class TestCardLayoutParsesLikeTheReference:
    def test_reference_itself_is_clean(self, reference: Any) -> None:
        assert reference.success
        assert reference.syntax_diagnostics == []
        assert [p.name for p in reference.ast.procedure_division.paragraphs] == [
            "MAIN-PARA"
        ]

    def test_full_card_layout_has_the_same_ast_as_the_reference(
        self, tmp_path: Path, reference: Any
    ) -> None:
        result = analyze(tmp_path, build(seq=True, ident=True, comments=True))
        assert result.success
        assert result.syntax_diagnostics == []
        assert ast_of(result) == ast_of(reference)  # includes every line/column
        assert result.java_source == reference.java_source

    def test_procedure_division_is_detected(self, tmp_path: Path) -> None:
        result = analyze(tmp_path, build(seq=True, ident=True, comments=True))
        assert result.ast.procedure_division is not None
        assert [p.name for p in result.ast.procedure_division.paragraphs] == [
            "MAIN-PARA"
        ]

    def test_blank_sequence_area_with_comment_lines_has_no_syn003(
        self, tmp_path: Path, reference: Any
    ) -> None:
        """The corpus shape: blank sequence area, ``*`` in column 7."""
        source = build(seq=False, ident=False, comments=True)
        result = analyze(tmp_path, source)
        assert [str(d.code) for d in result.syntax_diagnostics] == []
        twin = analyze(tmp_path, blank_reference(source), sub="twin")
        assert ast_of(result) == ast_of(twin)

    def test_crlf_source_is_equivalent(self, tmp_path: Path, reference: Any) -> None:
        directory = tmp_path / "crlf"
        directory.mkdir()
        path = directory / "prog.cbl"
        path.write_bytes(
            build(seq=True, ident=True, comments=True).replace("\n", "\r\n").encode()
        )
        result = AnalysisService().analyze_file(path)
        assert result.success
        assert ast_of(result) == ast_of(reference)


class TestNonCodeTextNeverReachesTheParser:
    def test_sequence_numbers_and_program_id_area_are_not_code(
        self, tmp_path: Path
    ) -> None:
        result = analyze(tmp_path, build(seq=True, ident=True, comments=True))
        assert "PAYR" not in result.java_source
        assert result.coverage.unknown_token_count == 0

    def test_comment_text_is_ignored_even_with_unlexable_characters(
        self, tmp_path: Path
    ) -> None:
        """``@#`` in a comment would raise LexerError if it were lexed."""
        result = analyze(tmp_path, build(seq=True, ident=True, comments=True))
        assert result.error is None

    def test_debug_and_page_eject_lines_are_ignored(self, tmp_path: Path) -> None:
        lines = build(seq=True, ident=True, comments=True).splitlines()
        lines.insert(12, card("    DISPLAY 'DEBUG-ONLY'", seq="000175", ind="D"))
        lines.insert(13, card("    DISPLAY 'EJECT-ONLY'", seq="000176", ind="/"))
        result = analyze(tmp_path, "\n".join(lines) + "\n")
        assert result.success
        assert "DEBUG-ONLY" not in result.java_source
        assert "EJECT-ONLY" not in result.java_source
        assert "CODE-IS-AUTO" in result.java_source

    def test_a_statement_starting_in_column_7_is_not_mistaken_for_debug(
        self, tmp_path: Path
    ) -> None:
        lines = build(seq=False, ident=False, comments=True).splitlines()
        lines.insert(12, "      DISPLAY 'STARTS-IN-COLUMN-7'")
        result = analyze(tmp_path, "\n".join(lines) + "\n")
        assert "STARTS-IN-COLUMN-7" in result.java_source


class TestPositionsStayMeaningful:
    def test_diagnostic_points_at_the_original_line_and_column(
        self, tmp_path: Path
    ) -> None:
        lines = build(seq=True, ident=True, comments=True).splitlines()
        last = len(lines) - 1
        lines[last] = card(
            "    STOP RUN", seq=f"{(last + 1) * 100:06d}", ident="PAYR9999"
        )
        result = analyze(tmp_path, "\n".join(lines) + "\n")
        diags = [d for d in result.syntax_diagnostics if str(d.code) == "SYN002"]
        assert len(diags) == 1
        assert diags[0].line == last + 1
        assert diags[0].column == lines[last].index("RUN") + 1

    def test_ast_positions_equal_original_card_columns(self, tmp_path: Path) -> None:
        source = build(seq=True, ident=True, comments=True)
        raw = source.splitlines()
        result = analyze(tmp_path, source)
        para = result.ast.procedure_division.paragraphs[0]
        assert (
            para.start_position.line
            == raw.index(card("MAIN-PARA.", seq="001000", ident="PAYR0010")) + 1
        )
        assert para.start_position.column == 8


class TestFormatsThatMustNotChange:
    FREE = (
        "IDENTIFICATION DIVISION.\n"
        "PROGRAM-ID. FREEQ.\n"
        "DATA DIVISION.\n"
        "WORKING-STORAGE SECTION.\n"
        "01 WS-A PIC 9(2) VALUE 0.\n"
        "01 WS-LONG-NAME-NUMBER-ONE PIC 9(2) VALUE 0.\n"
        "PROCEDURE DIVISION.\n"
        "MAIN-PARA.\n"
        "    MOVE 5 TO WS-A.\n"
        "    ADD WS-A TO WS-LONG-NAME-NUMBER-ONE GIVING WS-LONG-NAME-NUMBER-ONE.\n"
        "    DISPLAY 'FREE2-OK'.\n"
        "    STOP RUN.\n"
    )

    def test_free_format_source_is_returned_unchanged(self) -> None:
        assert AnalysisService.prepare_source(self.FREE, "f.cbl") is self.FREE

    def test_free_format_with_star_gt_comment_is_unchanged(self) -> None:
        src = self.FREE.replace("MAIN-PARA.\n", "MAIN-PARA. *> note\n")
        assert AnalysisService.prepare_source(src, "f.cbl") is src

    def test_free_format_text_beyond_column_72_is_kept(self, tmp_path: Path) -> None:
        result = analyze(tmp_path, self.FREE)
        assert result.success
        assert result.ast.procedure_division.paragraphs[0].name == "MAIN-PARA"

    def test_undetectable_format_is_returned_unchanged(self) -> None:
        """Fewer than five non-empty lines: the detector says UNKNOWN."""
        tiny = "\n".join(
            [
                card("IDENTIFICATION DIVISION.", seq="000100"),
                card("PROGRAM-ID. TINY.", seq="000200"),
                card("STOP RUN.", seq="000300"),
            ]
        )
        assert AnalysisService.prepare_source(tiny, "t.cbl") is tiny


class TestWideMarginFilesAreNeverTruncated:
    def test_code_past_column_72_survives(self, tmp_path: Path) -> None:
        wide = "          DISPLAY '" + "A" * 70 + "'"
        lines = build(seq=False, ident=False, comments=True).splitlines()
        assert len(wide) > 80
        lines.insert(12, wide)
        result = analyze(tmp_path, "\n".join(lines) + "\n")
        assert result.success
        assert "A" * 70 in result.java_source


class TestContinuationRemainsAnExplicitLimitation:
    def test_continued_literal_fails_loudly_instead_of_corrupting(
        self, tmp_path: Path
    ) -> None:
        """Continuation lines are not supported; the failure must be visible."""
        first = "000800" + " " + ("    DISPLAY '" + "A" * (65 - len("    DISPLAY '")))
        cont = "000900" + "-" + "      'BBBB'."
        lines = [
            card("IDENTIFICATION DIVISION.", seq="000100"),
            card("PROGRAM-ID. CONTP.", seq="000200"),
            card("DATA DIVISION.", seq="000300"),
            card("WORKING-STORAGE SECTION.", seq="000400"),
            card("01  WS-X    PIC X.", seq="000500"),
            card("PROCEDURE DIVISION.", seq="000600"),
            card("MAIN-PARA.", seq="000700"),
            first,
            cont,
            card("    STOP RUN.", seq="001000"),
        ]
        result = analyze(tmp_path, "\n".join(lines) + "\n")
        assert not result.success
        assert isinstance(result.error, LexerError)


class TestCorpusIsNeverAltered:
    """No corpus code may be dropped or moved by normalization."""

    @pytest.mark.parametrize(
        "record", load_training_corpus(), ids=lambda r: r.source_id
    )
    def test_only_column_7_comment_lines_change(self, record: Any) -> None:
        original = record.source
        prepared = AnalysisService.prepare_source(original, f"{record.source_id}.cbl")
        assert len(prepared) == len(original)
        for before, after in zip(original.splitlines(), prepared.splitlines()):
            assert len(after) == len(before)
            if after != before:
                assert before[6] == "*", before
                assert after.strip() == ""
