"""
Tests for :meth:`SourceNormalizer.normalize_preserving_positions`.

Purpose:
    Pin the contract the analysis pipeline relies on: fixed-format noise
    (sequence numbers, comment/debug lines, the program-ID area) is
    overwritten with spaces, never deleted, so every surviving character
    keeps its original line, column and offset.

Responsibilities:
    - Free format is returned unchanged; UNKNOWN and non-str are rejected.
    - Line terminators and per-line lengths are preserved exactly.
    - Sequence area, indicator column and columns 73-80 behave per rule.
    - A file wider than an 80-column card is never truncated.
    - Lexer positions on the normalized text equal original coordinates.

Dependencies:
    - :mod:`app.parser.lexer.normalizer`, :mod:`app.parser.lexer.lexer`.
"""

from __future__ import annotations

import pytest

from app.parser.lexer.exceptions import NormalizationError
from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.normalizer import SourceNormalizer
from app.parser.lexer.source_format import SourceFormat

FIXED = SourceFormat.FIXED


def card(text: str, seq: str = "", ind: str = " ", ident: str = "") -> str:
    """Build one card: cols 1-6 sequence, col 7 indicator, cols 8-72 text, 73-80 id."""
    assert len(text) <= 65
    line = f"{seq:<6}{ind}{text:<65}{ident}"
    return line if ident else line.rstrip()


def norm(source: str) -> str:
    return SourceNormalizer().normalize_preserving_positions(source, FIXED)


class TestContract:
    def test_free_format_is_returned_unchanged(self) -> None:
        src = "000100 IDENTIFICATION DIVISION.\n* not a comment here\n"
        assert (
            SourceNormalizer().normalize_preserving_positions(src, SourceFormat.FREE)
            is src
        )

    def test_unknown_format_is_rejected(self) -> None:
        with pytest.raises(NormalizationError):
            SourceNormalizer().normalize_preserving_positions("x", SourceFormat.UNKNOWN)

    def test_non_str_is_rejected(self) -> None:
        with pytest.raises(NormalizationError):
            SourceNormalizer().normalize_preserving_positions(b"x", FIXED)  # type: ignore[arg-type]

    def test_empty_source(self) -> None:
        assert norm("") == ""

    @pytest.mark.parametrize("eol", ["\n", "\r\n", "\r"])
    def test_line_terminators_and_lengths_are_preserved(self, eol: str) -> None:
        lines = [
            card("IDENTIFICATION DIVISION.", seq="000100", ident="PAYR0001"),
            card("* remark", seq="000200", ind="*", ident="PAYR0002"),
            "",
            card("    STOP RUN.", seq="000400"),
        ]
        src = eol.join(lines) + eol
        out = norm(src)
        assert len(out) == len(src)
        assert out.count(eol) == src.count(eol)
        for original, result in zip(src.splitlines(), out.splitlines()):
            assert len(result) == len(original)

    def test_idempotent(self) -> None:
        src = card("MOVE 1 TO X.", seq="000100", ident="PAYR0001") + "\n"
        assert norm(norm(src)) == norm(src)


class TestSequenceAndMargin:
    def test_sequence_area_is_blanked_not_deleted(self) -> None:
        src = card("MOVE 1 TO X.", seq="000100") + "\n"
        out = norm(src)
        assert out[:6] == "      "
        assert out[7:] == src[7:]

    def test_sequence_only_line_is_blanked(self) -> None:
        assert norm("000100\n") == "      \n"

    def test_program_id_area_is_blanked_when_file_is_a_card_image(self) -> None:
        src = "\n".join(
            [
                card("MOVE 1 TO X.", seq="000100", ident="PAYR0001"),
                card("STOP RUN.", seq="000200", ident="PAYR0002"),
            ]
        )
        out = norm(src).splitlines()
        assert [ln[72:] for ln in out] == ["        ", "        "]
        assert out[0][7:20] == "MOVE 1 TO X. "

    def test_non_card_line_is_left_untouched(self) -> None:
        """Letters in columns 1-6 mean the line is not card-formatted."""
        stray = "MOVE 1 TO X."
        src = stray + "\n" + card("STOP RUN.", seq="000200") + "\n"
        assert norm(src).splitlines()[0] == stray

    def test_text_beyond_column_80_means_wide_margin_and_nothing_is_cut(self) -> None:
        wide = card("MOVE A TO B", seq="000100").ljust(80) + "TO-A-FIELD-BEYOND-80"
        assert len(wide) > 80
        tail_only = card("STOP RUN.", seq="000200", ident="PAYR0002")
        out = norm(wide + "\n" + tail_only + "\n").splitlines()
        assert out[0][72:] == wide[72:]
        assert out[1][72:] == "PAYR0002"  # whole file keeps its columns 73+

    def test_word_straddling_column_72_means_wide_margin(self) -> None:
        line = "000100     MOVE SOMETHING TO ".ljust(60) + "TARGETNAMEPASTCOL72"
        assert line[71].isalnum() and line[72].isalnum() and len(line) <= 80
        assert norm(line + "\n") == "      " + line[6:] + "\n"

    def test_period_ending_at_column_72_is_not_a_straddle(self) -> None:
        line = card("MOVE 1 TO X.", seq="000100").ljust(71) + "." + "PAYR0001"
        assert line[71] == "." and len(line) == 80
        assert norm(line + "\n").rstrip("\n")[72:] == "        "


class TestIndicatorColumn:
    @pytest.mark.parametrize("indicator", ["*", "/"])
    def test_comment_and_page_eject_lines_are_blanked_whole(
        self, indicator: str
    ) -> None:
        line = card("MOVE 1 TO X. STOP RUN.", seq="000100", ind=indicator)
        assert norm(line + "\n") == " " * len(line) + "\n"

    def test_comment_without_sequence_number(self) -> None:
        line = "      * a comment"
        assert norm(line + "\n") == " " * len(line) + "\n"

    def test_debug_line_is_blanked(self) -> None:
        line = card("    DISPLAY 'DBG'", seq="000100", ind="D")
        assert norm(line + "\n").strip() == ""

    def test_lowercase_debug_indicator_is_blanked(self) -> None:
        line = card("    DISPLAY 'DBG'", ind="d")
        assert norm(line + "\n").strip() == ""

    def test_d_starting_a_statement_in_column_7_is_code_not_debug(self) -> None:
        line = "      DISPLAY 'X'."
        assert norm(line + "\n") == line + "\n"

    def test_continuation_indicator_is_left_untouched(self) -> None:
        line = card("      'TAIL'.", seq="000900", ind="-")
        out = norm(line + "\n").rstrip("\n")
        assert out[6] == "-"
        assert out[7:] == line[7:]

    def test_regular_indicator_blank_is_kept(self) -> None:
        out = norm(card("STOP RUN.", seq="000100") + "\n")
        assert out[6] == " "


class TestPositionsSurviveLexing:
    """The whole point: token coordinates equal the original card's."""

    SOURCE = "\n".join(
        [
            card("IDENTIFICATION DIVISION.", seq="000100", ident="PAYR0001"),
            card(
                "* NOTE @#$ THAT MUST NOT LEX", seq="000200", ind="*", ident="PAYR0002"
            ),
            card("PROGRAM-ID. POSP.", seq="000300", ident="PAYR0003"),
            card("    MOVE 1 TO WS-X.", seq="000400", ident="PAYR0004"),
        ]
    )

    def test_token_positions_equal_original_coordinates(self) -> None:
        raw_lines = self.SOURCE.splitlines()
        tokens = CobolLexer().tokenize(norm(self.SOURCE), filename="p.cbl")
        by_lexeme = {t.lexeme: t for t in tokens if t.lexeme}
        for lexeme, line_no in (("IDENTIFICATION", 1), ("PROGRAM-ID", 3), ("MOVE", 4)):
            tok = by_lexeme[lexeme]
            assert tok.position.line == line_no
            assert tok.position.column == raw_lines[line_no - 1].index(lexeme) + 1
        assert by_lexeme["WS-X"].position.column == raw_lines[3].index("WS-X") + 1

    def test_no_sequence_comment_or_id_text_becomes_a_token(self) -> None:
        tokens = CobolLexer().tokenize(norm(self.SOURCE), filename="p.cbl")
        lexemes = {t.lexeme for t in tokens}
        assert not lexemes & {"000100", "000200", "PAYR0001", "PAYR0004", "NOTE", "@"}
        assert "PROGRAM-ID" in lexemes
