"""Per-field ``data_item`` chunks from the DATA DIVISION."""

from __future__ import annotations

from app.knowledge.chunk import ChunkType
from app.knowledge.chunkers import chunk_cobol_source

_SOURCE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ITEMS.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-TAX-RATE            PIC 9V99 VALUE 0.18.
       01  WS-LONG-ITEM           PIC X(30)
                                  VALUE 'A LONG INITIAL VALUE'.
       01  FILLER                 PIC X(5).
       01  WS-FLAGS.
           05  WS-ON              PIC X VALUE 'Y'.
           88  IS-ON              VALUE 'Y'.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE 5 TO WS-TAX-RATE.
           STOP RUN.
"""


def _items():
    chunks = chunk_cobol_source("ITEMS", _SOURCE, paragraph_names=["MAIN-PARA"])
    return [c for c in chunks if c.chunk_type is ChunkType.DATA_ITEM]


def test_each_named_field_gets_its_own_chunk() -> None:
    contents = " | ".join(c.content for c in _items())
    for name in ("WS-TAX-RATE", "WS-LONG-ITEM", "WS-FLAGS", "WS-ON", "IS-ON"):
        assert f"Data item {name} " in contents


def test_chunk_carries_the_picture_and_initial_value() -> None:
    (tax,) = [c for c in _items() if "WS-TAX-RATE" in c.content.split(":")[0]]
    assert "PIC 9V99 VALUE 0.18" in tax.content
    assert "level 01" in tax.content


def test_declaration_continued_over_lines_stays_in_one_chunk() -> None:
    (item,) = [c for c in _items() if "WS-LONG-ITEM" in c.content]
    assert "PIC X(30)" in item.content
    assert "A LONG INITIAL VALUE" in item.content
    assert item.provenance.line_end > item.provenance.line_start


def test_filler_is_skipped() -> None:
    assert not any("FILLER" in c.content for c in _items())


def test_procedure_statements_are_not_mistaken_for_data_items() -> None:
    assert not any("MOVE 5" in c.content for c in _items())


def test_provenance_points_at_the_declaration_line() -> None:
    (tax,) = [c for c in _items() if "WS-TAX-RATE" in c.content.split(":")[0]]
    assert tax.provenance.line_start == 5
    assert tax.provenance.section == "DATA DIVISION"


def test_chunk_ids_are_stable_across_runs() -> None:
    assert [c.chunk_id for c in _items()] == [c.chunk_id for c in _items()]


def test_program_without_a_data_division_has_no_data_items() -> None:
    src = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. X.\n       PROCEDURE DIVISION.\n       MAIN-PARA.\n           STOP RUN.\n"
    chunks = chunk_cobol_source("X", src, paragraph_names=["MAIN-PARA"])
    assert not [c for c in chunks if c.chunk_type is ChunkType.DATA_ITEM]
