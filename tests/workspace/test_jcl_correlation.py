"""
Tests for :mod:`app.workspace.jcl_correlation`.

Purpose:
    Verify :func:`find_invoking_jobs` correctly matches ``EXEC PGM=``
    targets against a program name, across multiple JCL files, and
    degrades gracefully for malformed job streams and non-JCL files.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.workspace.jcl_correlation import find_invoking_jobs
from app.workspace.models import FileType, ScannedFile, WorkspaceInventory

_JCL_ONE_STEP = """\
//PAYROLL  JOB (ACCT),'RUN PAYROLL'
//STEP01   EXEC PGM=PAYCALC
//INFILE   DD DSN=PAY.INPUT,DISP=SHR
"""

_JCL_NO_MATCH = """\
//OTHERJOB JOB (ACCT),'OTHER'
//STEP01   EXEC PGM=SOMEOTHER
"""

_JCL_NO_JOB_STATEMENT = """\
//STEP01   EXEC PGM=PAYCALC
"""


def _scanned(path: Path, file_type: FileType = FileType.JCL) -> ScannedFile:
    data = path.read_bytes()
    return ScannedFile(
        path=str(path),
        filename=path.name,
        extension=path.suffix.lower(),
        sha256="0" * 64,
        size_bytes=len(data),
        file_type=file_type,
        scanned_at=datetime.now(UTC),
    )


def _inventory(
    tmp_path: Path, files: dict[str, tuple[str, FileType]]
) -> WorkspaceInventory:
    scanned = []
    for name, (content, file_type) in files.items():
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        scanned.append(_scanned(p, file_type))
    return WorkspaceInventory(
        workspace_id="ws",
        files=scanned,
        total_files=len(scanned),
        scanned_at=datetime.now(UTC),
    )


def test_finds_matching_step(tmp_path: Path) -> None:
    inv = _inventory(tmp_path, {"payroll.jcl": (_JCL_ONE_STEP, FileType.JCL)})
    invocations = find_invoking_jobs("PAYCALC", inv)
    assert len(invocations) == 1
    inv0 = invocations[0]
    assert inv0.jcl_filename == "payroll.jcl"
    assert inv0.job_name == "PAYROLL"
    assert inv0.step_name == "STEP01"
    assert inv0.line == 2


def test_case_insensitive_match(tmp_path: Path) -> None:
    inv = _inventory(tmp_path, {"payroll.jcl": (_JCL_ONE_STEP, FileType.JCL)})
    invocations = find_invoking_jobs("paycalc", inv)
    assert len(invocations) == 1


def test_no_match_returns_empty(tmp_path: Path) -> None:
    inv = _inventory(tmp_path, {"other.jcl": (_JCL_NO_MATCH, FileType.JCL)})
    assert find_invoking_jobs("PAYCALC", inv) == ()


def test_blank_program_name_returns_empty(tmp_path: Path) -> None:
    inv = _inventory(tmp_path, {"payroll.jcl": (_JCL_ONE_STEP, FileType.JCL)})
    assert find_invoking_jobs("   ", inv) == ()


def test_non_jcl_files_are_skipped(tmp_path: Path) -> None:
    inv = _inventory(
        tmp_path,
        {
            "payroll.cbl": (
                "IDENTIFICATION DIVISION.\nPROGRAM-ID. PAYCALC.\n",
                FileType.COBOL,
            )
        },
    )
    assert find_invoking_jobs("PAYCALC", inv) == ()


def test_job_stream_without_job_statement_still_matches_step(
    tmp_path: Path,
) -> None:
    """A malformed/partial job stream (no JOB line) is still usable --
    the step-level EXEC PGM= match does not depend on the job name."""
    inv = _inventory(tmp_path, {"headless.jcl": (_JCL_NO_JOB_STATEMENT, FileType.JCL)})
    invocations = find_invoking_jobs("PAYCALC", inv)
    assert len(invocations) == 1
    assert invocations[0].job_name is None


def test_multiple_jcl_files_all_scanned(tmp_path: Path) -> None:
    inv = _inventory(
        tmp_path,
        {
            "payroll.jcl": (_JCL_ONE_STEP, FileType.JCL),
            "other.jcl": (_JCL_NO_MATCH, FileType.JCL),
        },
    )
    invocations = find_invoking_jobs("PAYCALC", inv)
    assert len(invocations) == 1
    assert invocations[0].jcl_filename == "payroll.jcl"


def test_malformed_jcl_file_does_not_crash(tmp_path: Path) -> None:
    """A JCL file with no recognisable statements at all must be skipped,
    not raise -- matching WorkspaceSearcher's own graceful-degradation
    convention."""
    inv = _inventory(
        tmp_path, {"garbage.jcl": ("this is not JCL at all\n", FileType.JCL)}
    )
    assert find_invoking_jobs("PAYCALC", inv) == ()
