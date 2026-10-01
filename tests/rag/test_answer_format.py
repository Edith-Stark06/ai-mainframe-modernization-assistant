"""clean_answer: citations, tables, markers, whitespace."""

from __future__ import annotations

from app.rag.answer_format import clean_answer

ID_A = "java_method-e8524fdcdb084683"
ID_B = "business_rule-d4f31d31b4b4f058"
REFS = {ID_A: 3, ID_B: 1}


# ---------------------------------------------------------- citations


def test_raw_chunk_id_becomes_its_evidence_number() -> None:
    assert clean_answer(f"It starts here [{ID_A}].", REFS) == "It starts here [3]."


def test_several_ids_in_one_bracket_become_sorted_numbers() -> None:
    assert clean_answer(f"Both [{ID_A}, {ID_B}].", REFS) == "Both [1, 3]."


def test_an_id_not_in_the_evidence_is_dropped_with_its_space() -> None:
    assert clean_answer("Claim [java_method-0123456789abcdef].", REFS) == "Claim."


def test_numbered_citations_are_left_alone() -> None:
    assert clean_answer("See [2] and [1][3].", REFS) == "See [2] and [1][3]."


def test_ordinary_brackets_are_left_alone() -> None:
    text = "Uses `table[idx]` and [link text]."
    assert clean_answer(text, REFS) == text


# ------------------------------------------------------------- tables

TABLE = (
    "| Step | What the code does | Relevant chunks |\n"
    "|------|--------------------|-----------------|\n"
    "| 1 | Program entry | [x] |\n"
    "| 2 | Run sequence | [y] |"
)


def test_table_becomes_bullets_without_the_citation_column_or_row_numbers() -> None:
    out = clean_answer(TABLE)
    assert out == "- Program entry\n- Run sequence"
    assert "|" not in out


def test_table_keeps_every_other_column() -> None:
    table = "| Name | Role |\n|---|---|\n| run() | entry point |\n| main | starts it |"
    assert clean_answer(table) == "- run() — entry point\n- main — starts it"


def test_text_around_a_table_is_preserved() -> None:
    out = clean_answer(f"Intro.\n\n{TABLE}\n\nOutro.")
    assert out.startswith("Intro.")
    assert out.endswith("Outro.")
    assert "- Program entry" in out


def test_a_pipe_in_ordinary_text_is_not_a_table() -> None:
    text = "Use a | b for alternatives."
    assert clean_answer(text) == text


# --------------------------------------------------------- markers / space


def test_dangling_bold_marker_lines_are_removed() -> None:
    assert clean_answer("Answer.\n\n**\n\nMore.") == "Answer.\n\nMore."


def test_real_emphasis_is_kept() -> None:
    assert clean_answer("This is **HIGH VALUE** now.") == "This is **HIGH VALUE** now."


def test_trailing_double_space_line_breaks_are_tidied() -> None:
    assert clean_answer("line one  \nline two") == "line one\nline two"


def test_blank_line_runs_collapse_and_edges_are_trimmed() -> None:
    assert clean_answer("\n\nA\n\n\n\n\nB\n\n") == "A\n\nB"


def test_code_spacing_is_never_altered() -> None:
    text = "Set `x = 1 ;` then `IF A > B`."
    assert clean_answer(text) == text


def test_empty_text_stays_empty() -> None:
    assert clean_answer("") == ""
