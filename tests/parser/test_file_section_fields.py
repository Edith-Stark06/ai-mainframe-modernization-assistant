"""
FILE SECTION support -- ``FD`` records become Java fields (Stage 27).

Purpose:
    The FILE SECTION was entirely unsupported: ``DataDivisionParser``
    recognised the ``FILE SECTION.`` header only to skip it whole
    (``SYN101 "unsupported DATA DIVISION section 'FILE'"``), so an
    ``FD``'s record fields never entered the AST, the symbol table, or
    the generated Java class. Every real reference to one of those
    fields in the PROCEDURE DIVISION (``IF FD-ACCT-BAL < 500.00``, ...)
    became an undeclared Java identifier -- the sole remaining reason 4
    of the 45 real corpus sources failed ``javac`` (documented since
    ``docs/MMIM_JAVA_IF_EMISSION_FIX.md`` §7 / task #stage12).

    The fix (``app/parser/syntax/data_parser.py`` only, plus the AST/
    traversal/backend wiring needed to carry it through) parses ``FILE
    SECTION.`` and each ``FD <file-name>. <record>`` using the *exact
    same* data-item grammar (``ElementaryItemNode``/``GroupItemNode``/
    ``ConditionNameNode``) a WORKING-STORAGE ``01`` record already uses.
    Because every downstream consumer -- symbol collection
    (``app/parser/semantic/symbol_collector.py``), Java field
    construction (``app/backend/java/generator.py
    ::build_fields_from_symbols``), and condition-type awareness
    (``app/backend/java/condition_context.py::build_condition_context``)
    -- is already generic over *any* registered ``VariableSymbol``, none
    of them needed a FILE-SECTION-specific code path: only
    ``app/parser/semantic/visitors.py::traverse_program`` needed to walk
    the new section the same way it already walks WORKING-STORAGE.

    This closes the loop the negated-comparison and figurative-constant
    stages (25, 26) kept finding blocked by: all 4 affected sources now
    compile with real ``javac`` (§7) -- 45/45, up from 41/45.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.analysis.service import AnalysisService
from app.dataset.corpus import load_training_corpus
from app.parser.ast.data_items import ElementaryItemNode, GroupItemNode
from app.parser.ast.file_section import FileDescriptionNode, FileSectionNode
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.program_parser import ProgramParser

needs_java = pytest.mark.skipif(
    shutil.which("javac") is None or shutil.which("java") is None,
    reason="javac/java not available",
)

_HEAD = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FILETEST.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCT-IN-FILE ASSIGN TO 'ACCTS.DAT'.
       DATA DIVISION.
"""
_TAIL = """\
       PROCEDURE DIVISION.
       MAIN-PARA.
           STOP RUN.
"""


def _tokens(source: str):
    return CobolLexer().tokenize(source, filename="s.cbl")


def _parse(source: str):
    return ProgramParser().parse(_tokens(source))


def _analyse(source: str, tmp_path: Path):
    path = tmp_path / "filetest.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _codes(result) -> list[str]:
    return [str(getattr(d, "code", "")) for d in result.syntax_diagnostics]


# ===========================================================================
# 1. Parser: a single-FD FILE SECTION parses with zero diagnostics
# ===========================================================================

_ONE_FD = _HEAD + """\
       FILE SECTION.
       FD  ACCT-IN-FILE.
       01  FD-ACCT-RECORD.
           05  FD-ACCT-NUM         PIC X(10).
           05  FD-ACCT-BAL         PIC 9(7)V99.
       WORKING-STORAGE SECTION.
       01  WS-COUNT                PIC 9(3).
""" + _TAIL


def test_file_section_present_on_data_division() -> None:
    program = _parse(_ONE_FD)
    fs = program.data_division.file_section
    assert isinstance(fs, FileSectionNode)


def test_one_fd_record_with_two_fields() -> None:
    """``record.items`` is a *flat* sequence -- the same convention a
    WORKING-STORAGE ``01`` record already uses (level numbers convey the
    hierarchy; the AST does not nest subordinate items under a parent
    group's ``children``, confirmed directly: every ``GroupItemNode``'s
    ``children`` is always ``()``)."""
    program = _parse(_ONE_FD)
    fs = program.data_division.file_section
    (record,) = fs.records
    assert isinstance(record, FileDescriptionNode)
    assert record.name == "ACCT-IN-FILE"
    group, num, bal = record.items
    assert isinstance(group, GroupItemNode)
    assert group.name == "FD-ACCT-RECORD"
    assert group.level == 1
    assert isinstance(num, ElementaryItemNode)
    assert (num.name, num.level, num.picture) == ("FD-ACCT-NUM", 5, "X(10)")
    assert isinstance(bal, ElementaryItemNode)
    assert (bal.name, bal.level, bal.picture) == ("FD-ACCT-BAL", 5, "9(7)V99")


def test_working_storage_after_file_section_is_unaffected() -> None:
    program = _parse(_ONE_FD)
    ws = program.data_division.working_storage
    assert [i.name for i in ws.items] == ["WS-COUNT"]


def test_one_fd_record_produces_zero_syntax_diagnostics(tmp_path: Path) -> None:
    result = _analyse(_ONE_FD, tmp_path)
    assert "SYN101" not in _codes(result)
    assert result.syntax_diagnostics == []


# ===========================================================================
# 2. Multiple FD entries in one FILE SECTION
# ===========================================================================

_TWO_FD = _HEAD + """\
       FILE SECTION.
       FD  TX-IN-FILE.
       01  FD-TX-IN-RECORD.
           05  FD-TX-ID            PIC X(12).
           05  FD-TX-VAL           PIC 9(7)V99.
       FD  RPT-OUT-FILE.
       01  FD-RPT-LINE             PIC X(80).
       WORKING-STORAGE SECTION.
       01  WS-COUNT                PIC 9(3).
""" + _TAIL


def test_two_fd_entries_both_parsed() -> None:
    program = _parse(_TWO_FD)
    fs = program.data_division.file_section
    assert [r.name for r in fs.records] == ["TX-IN-FILE", "RPT-OUT-FILE"]


def test_second_fd_is_a_bare_elementary_01_with_no_subordinates() -> None:
    """``01 FD-RPT-LINE PIC X(80).`` -- a PIC directly on the 01, the same
    shape a WORKING-STORAGE 01 already supports; no ``05`` subordinates."""
    program = _parse(_TWO_FD)
    fs = program.data_division.file_section
    second = fs.records[1]
    (item,) = second.items
    assert isinstance(item, ElementaryItemNode)
    assert item.name == "FD-RPT-LINE"
    assert item.picture == "X(80)"


def test_two_fd_entries_zero_syntax_diagnostics(tmp_path: Path) -> None:
    result = _analyse(_TWO_FD, tmp_path)
    assert result.syntax_diagnostics == []


# ===========================================================================
# 3. Recovery: a malformed FD does not lose WORKING-STORAGE or the rest of
#    the FILE SECTION
# ===========================================================================


def test_fd_with_no_file_name_is_recoverable(tmp_path: Path) -> None:
    src = _HEAD + """\
       FILE SECTION.
       FD  .
       FD  TX-IN-FILE.
       01  FD-TX-ID                PIC X(12).
       WORKING-STORAGE SECTION.
       01  WS-COUNT                PIC 9(3).
""" + _TAIL
    result = _analyse(src, tmp_path)
    codes = _codes(result)
    assert "SYN005" in codes
    fs = result.ast.data_division.file_section
    # the malformed FD is skipped; the well-formed one that follows survives
    assert [r.name for r in fs.records] == ["TX-IN-FILE"]
    ws = result.ast.data_division.working_storage
    assert [i.name for i in ws.items] == ["WS-COUNT"]


# ===========================================================================
# 4. Symbol table / Java field construction -- generic, no FILE-SECTION-
#    specific code needed downstream
# ===========================================================================


def test_fd_fields_become_java_fields_with_correct_types(tmp_path: Path) -> None:
    result = _analyse(_ONE_FD, tmp_path)
    fields = {
        name: java_type
        for java_type, name in re.findall(
            r"private (\S+) (\w+)[ ;=]", result.java_source
        )
    }
    assert fields["fdAcctNum"] == "String"
    assert fields["fdAcctBal"] == "double"
    assert fields["wsCount"] == "int"


def test_fd_group_item_also_becomes_a_field(tmp_path: Path) -> None:
    """The FD's own 01-level group item (``FD-ACCT-RECORD``) becomes a bare
    ``String`` field with no initializer -- exactly like a WORKING-STORAGE
    group item without a PIC clause already does."""
    result = _analyse(_ONE_FD, tmp_path)
    assert "private String fdAcctRecord;" in result.java_source


# ===========================================================================
# 5. ConditionContext: FD field types are known, so a text comparison over
#    an FD field gets the correct _cobolEquals translation, not identity ==
# ===========================================================================


def test_fd_string_field_comparison_uses_cobol_equals(tmp_path: Path) -> None:
    src = _HEAD + """\
       FILE SECTION.
       FD  ACCT-IN-FILE.
       01  FD-ACCT-RECORD.
           05  FD-STATUS           PIC X(1).
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF FD-STATUS = 'Y'
               STOP RUN
           END-IF.
"""
    result = _analyse(src, tmp_path)
    assert '_cobolEquals(fdStatus, "Y")' in result.java_source
    assert "fdStatus == " not in result.java_source


# ===========================================================================
# 6. Real corpus: exactly the 4 known FILE-SECTION sources, SYN101 gone,
#    every FD field declared, javac now compiles all 4
# ===========================================================================

_FILE_SECTION_SOURCES = (
    "t_batch_acct_update",
    "t_daily_trans_report",
    "t_inventory_extract",
    "t_payroll_file_post",
)


def test_exactly_four_corpus_sources_have_a_file_section() -> None:
    hits = [
        rec.source_id for rec in load_training_corpus() if "FILE SECTION" in rec.source
    ]
    assert set(hits) == set(_FILE_SECTION_SOURCES)


@pytest.mark.parametrize("source_id", _FILE_SECTION_SOURCES)
def test_real_file_section_sources_no_longer_report_syn101(source_id: str) -> None:
    p = Path(f"data/sources/phase6-v2/{source_id.removeprefix('t_')}.cbl")
    result = AnalysisService().analyze_file(p)
    assert "SYN101" not in [str(d.code) for d in result.syntax_diagnostics]


@needs_java
@pytest.mark.parametrize("source_id", _FILE_SECTION_SOURCES)
def test_real_file_section_sources_now_compile_with_javac(
    source_id: str, tmp_path: Path
) -> None:
    p = Path(f"data/sources/phase6-v2/{source_id.removeprefix('t_')}.cbl")
    result = AnalysisService().analyze_file(p)
    m = re.search(r"public class (\w+)", result.java_source)
    assert m is not None
    java_path = tmp_path / f"{m.group(1)}.java"
    java_path.write_text(result.java_source, encoding="utf-8")
    proc = subprocess.run(
        ["javac", "-d", str(tmp_path), str(java_path)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr


@needs_java
def test_full_corpus_javac_pass_rate_is_now_45_of_45(tmp_path: Path) -> None:
    """The exact real-corpus regression this stage exists to fix: `javac`
    was 41/45 (docs/MMIM_JAVA_IF_EMISSION_FIX.md §7 onward) purely because
    of undeclared FILE SECTION fields; it is 45/45 now."""
    ok = 0
    corpus = load_training_corpus()
    for rec in corpus:
        p = tmp_path / f"_src_{rec.source_id}.cbl"
        p.write_text(rec.source, encoding="utf-8")
        result = AnalysisService().analyze_file(p)
        m = re.search(r"public class (\w+)", result.java_source)
        class_name = m.group(1) if m else rec.source_id
        java_path = tmp_path / f"{class_name}.java"
        java_path.write_text(result.java_source, encoding="utf-8")
        proc = subprocess.run(
            ["javac", "-d", str(tmp_path), str(java_path)],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            ok += 1
    assert ok == len(corpus) == 45


# ===========================================================================
# 7. Sources with no FILE SECTION are untouched
# ===========================================================================


def test_source_without_file_section_is_unaffected() -> None:
    p = Path("data/sources/phase6-v2/goto_spaghetti.cbl")
    result = AnalysisService().analyze_file(p)
    assert "SYN101" not in [str(d.code) for d in result.syntax_diagnostics]
    assert result.ast.data_division.file_section is None
