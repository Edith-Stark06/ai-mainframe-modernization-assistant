"""
Tests for :mod:`app.jcl.service` (task #stage46).

Purpose:
    Verify :class:`~app.jcl.service.JclAnalysisService`'s file-reading
    behavior (a missing file is a clean ``success=False`` result, never
    a raised exception) and a full, realistic multi-step job stream
    end to end.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path

from app.jcl.service import JclAnalysisService

_REALISTIC_JOB = """\
//PAYROLL  JOB (ACCT123),'JOHN DOE',CLASS=A,MSGCLASS=X,
//             REGION=4M
//STEP1    EXEC PGM=IEFBR14
//INFILE   DD DSN=PROD.PAYROLL.INPUT,DISP=SHR
//OUTFILE  DD DSN=PROD.PAYROLL.OUTPUT,
//             DISP=(NEW,CATLG,DELETE),
//             SPACE=(CYL,(10,5)),
//             UNIT=SYSDA
//SYSIN    DD *
SOME INSTREAM DATA HERE
MORE DATA
/*
//STEP2    EXEC PGM=SORT,COND=(4,LT,STEP1)
//SORTIN   DD DSN=PROD.PAYROLL.OUTPUT,DISP=SHR
//SORTOUT  DD DSN=PROD.PAYROLL.SORTED,DISP=(NEW,CATLG,DELETE)
//*
//* END OF JOB
//*
"""


class TestFileHandling:
    def test_missing_file_is_a_clean_failure(self) -> None:
        result = JclAnalysisService().analyze_file("/no/such/file.jcl")
        assert result.success is False
        assert isinstance(result.error, FileNotFoundError)
        assert result.program is None

    def test_real_file_is_read_and_parsed(self, tmp_path: Path) -> None:
        path = tmp_path / "job.jcl"
        path.write_text(_REALISTIC_JOB, encoding="utf-8")
        result = JclAnalysisService().analyze_file(path)
        assert result.success is True
        assert result.diagnostics == ()


class TestRealisticJobStream:
    def _analyze(self, tmp_path: Path):
        path = tmp_path / "job.jcl"
        path.write_text(_REALISTIC_JOB, encoding="utf-8")
        return JclAnalysisService().analyze_file(path)

    def test_job_name_and_continued_parameters(self, tmp_path: Path) -> None:
        result = self._analyze(tmp_path)
        job = result.program.job
        assert job.name == "PAYROLL"
        by_key = {p.key: p.value for p in job.parameters if p.key}
        assert by_key["CLASS"] == "A"
        assert by_key["MSGCLASS"] == "X"
        assert by_key["REGION"] == "4M"

    def test_two_steps_with_correct_programs(self, tmp_path: Path) -> None:
        result = self._analyze(tmp_path)
        steps = result.program.steps
        assert [s.name for s in steps] == ["STEP1", "STEP2"]
        assert steps[0].program == "IEFBR14"
        assert steps[1].program == "SORT"

    def test_step1_dd_statements_including_continued_and_instream(
        self, tmp_path: Path
    ) -> None:
        result = self._analyze(tmp_path)
        step1 = result.program.steps[0]
        assert [dd.name for dd in step1.dd_statements] == [
            "INFILE",
            "OUTFILE",
            "SYSIN",
        ]
        outfile = step1.dd_statements[1]
        by_key = {p.key: p.value for p in outfile.parameters}
        assert by_key["DSN"] == "PROD.PAYROLL.OUTPUT"
        assert by_key["DISP"] == "(NEW,CATLG,DELETE)"
        assert by_key["SPACE"] == "(CYL,(10,5))"
        assert by_key["UNIT"] == "SYSDA"

    def test_step2_cond_parameter_and_dd_statements(self, tmp_path: Path) -> None:
        result = self._analyze(tmp_path)
        step2 = result.program.steps[1]
        by_key = {p.key: p.value for p in step2.parameters}
        assert by_key["COND"] == "(4,LT,STEP1)"
        assert [dd.name for dd in step2.dd_statements] == ["SORTIN", "SORTOUT"]

    def test_in_stream_data_never_became_spurious_statements(
        self, tmp_path: Path
    ) -> None:
        result = self._analyze(tmp_path)
        assert result.program.unsupported == ()
        assert result.diagnostics == ()

    def test_which_programs_this_job_runs(self, tmp_path: Path) -> None:
        """A practical use of the parsed structure: listing every
        program a job invokes (the natural tie-in to a future Call
        Graph view -- not built here, but this is the data it would
        read)."""
        result = self._analyze(tmp_path)
        programs = [s.program for s in result.program.steps if s.program]
        assert programs == ["IEFBR14", "SORT"]
