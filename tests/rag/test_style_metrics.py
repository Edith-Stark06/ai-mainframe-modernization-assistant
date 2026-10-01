"""measure_style: the readability-noise counts."""

from __future__ import annotations

from app.rag.style import measure_style

NOISY = (
    "Summary: Presumably it is likely fine [java_method-e8524fdcdb084683].\n\n"
    "Explanation: **\n"
    "| a | b |\n|---|---|\n| 1 | 2 |\n"
    "Typically it works [business_rule-d4f31d31b4b4f058]."
)


def test_clean_answer_has_no_noise() -> None:
    report = measure_style("It flags orders at 50000.\n\n- `WS-TOTAL >= 50000` [2]")
    assert report.noise == 0
    assert report.words > 0


def test_each_kind_of_noise_is_counted() -> None:
    report = measure_style(NOISY)
    assert report.chunk_id_citations == 2
    assert report.table_rows == 3
    assert report.section_labels == 2
    assert report.hedges == 3  # presumably, likely, typically
    assert report.stray_bold_markers == 1
    assert report.noise == 2 + 3 + 3 + 2 + 1


def test_numbered_citations_are_not_noise() -> None:
    assert measure_style("See [1] and [2][3].").chunk_id_citations == 0


def test_word_count() -> None:
    assert measure_style("one two  three\nfour").words == 4


def test_balanced_bold_is_not_a_stray_marker() -> None:
    assert measure_style("This is **fine** here.").stray_bold_markers == 0
