"""
Tests for :mod:`app.jcl.parser` (task #stage46).

Purpose:
    Verify that ``JOB``/``EXEC``/``DD`` statements are grouped into the
    real AST (:mod:`app.jcl.ast`), that every other recognised operation
    is captured whole as :class:`~app.jcl.ast.JclUnsupportedStatement`
    with a diagnostic, and that a missing ``JOB`` or an orphaned ``DD``
    is diagnosed rather than raised.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.jcl.models import JclSeverity
from app.jcl.parser import JclParser


def _parse(source: str):
    return JclParser().parse(source)


class TestJobStatement:
    def test_job_name_and_parameters_captured(self) -> None:
        program, diags = _parse("//PAYROLL JOB CLASS=A,MSGCLASS=X\n")
        assert diags == []
        assert program.job is not None
        assert program.job.name == "PAYROLL"
        assert [p.key for p in program.job.parameters] == ["CLASS", "MSGCLASS"]

    def test_missing_job_is_diagnosed_as_an_error(self) -> None:
        program, diags = _parse("//STEP1 EXEC PGM=X\n")
        assert program.job is None
        codes = [(d.code, d.severity) for d in diags]
        assert ("JCL001", JclSeverity.ERROR) in codes

    def test_a_second_job_statement_is_ignored_and_diagnosed(self) -> None:
        program, diags = _parse(
            "//A JOB CLASS=A\n//B JOB CLASS=B\n//STEP1 EXEC PGM=X\n"
        )
        assert program.job is not None
        assert program.job.name == "A"
        assert any(d.code == "JCL002" for d in diags)


class TestStepsAndDD:
    def test_exec_starts_a_new_step(self) -> None:
        program, diags = _parse(
            "//J JOB\n//STEP1 EXEC PGM=IEFBR14\n//STEP2 EXEC PGM=SORT\n"
        )
        assert diags == []
        assert [s.name for s in program.steps] == ["STEP1", "STEP2"]
        assert program.steps[0].program == "IEFBR14"
        assert program.steps[1].program == "SORT"

    def test_dd_statements_attach_to_the_current_step(self) -> None:
        program, _ = _parse(
            "//J JOB\n"
            "//STEP1 EXEC PGM=X\n"
            "//IN  DD DSN=A.B,DISP=SHR\n"
            "//OUT DD DSN=C.D,DISP=(NEW,CATLG)\n"
        )
        step = program.steps[0]
        assert [dd.name for dd in step.dd_statements] == ["IN", "OUT"]
        assert dict((p.key, p.value) for p in step.dd_statements[0].parameters) == {
            "DSN": "A.B",
            "DISP": "SHR",
        }

    def test_dd_statements_reset_between_steps(self) -> None:
        program, _ = _parse(
            "//J JOB\n"
            "//STEP1 EXEC PGM=X\n"
            "//IN1 DD DSN=A.B,DISP=SHR\n"
            "//STEP2 EXEC PGM=Y\n"
            "//IN2 DD DSN=C.D,DISP=SHR\n"
        )
        assert [dd.name for dd in program.steps[0].dd_statements] == ["IN1"]
        assert [dd.name for dd in program.steps[1].dd_statements] == ["IN2"]

    def test_orphaned_dd_before_any_exec_is_diagnosed_not_crashed(self) -> None:
        program, diags = _parse("//J JOB\n//X DD DSN=A.B,DISP=SHR\n")
        assert program.steps == ()
        assert any(d.code == "JCL003" for d in diags)

    def test_step_proc_property_reads_explicit_proc_keyword(self) -> None:
        program, _ = _parse("//J JOB\n//S EXEC PROC=MYPROC\n")
        assert program.steps[0].program is None
        assert program.steps[0].procedure == "MYPROC"

    def test_step_proc_property_reads_bare_positional_form(self) -> None:
        """``EXEC MYPROC`` (no ``PROC=`` keyword) is also a valid,
        common procedure-call form."""
        program, _ = _parse("//J JOB\n//S EXEC MYPROC\n")
        assert program.steps[0].program is None
        assert program.steps[0].procedure == "MYPROC"


class TestUnsupportedStatements:
    def test_unrecognised_operation_is_captured_and_diagnosed(self) -> None:
        program, diags = _parse("//J JOB\n//S EXEC PGM=X\n//X IF (RC=0) THEN\n")
        assert len(program.unsupported) == 1
        assert program.unsupported[0].operation == "IF"
        assert program.unsupported[0].name == "X"
        assert any(d.code == "JCL100" for d in diags)

    def test_proc_and_pend_are_captured_not_expanded(self) -> None:
        program, diags = _parse(
            "//J JOB\n//MYPROC PROC\n//S EXEC PGM=X\n//MYPROC PEND\n"
        )
        ops = [s.operation for s in program.unsupported]
        assert ops == ["PROC", "PEND"]
        assert sum(1 for d in diags if d.code == "JCL100") == 2


class TestGracefulDegradation:
    def test_empty_source_produces_no_crash(self) -> None:
        program, diags = _parse("")
        assert program.job is None
        assert any(d.code == "JCL001" for d in diags)

    def test_only_comments_produces_no_crash(self) -> None:
        program, diags = _parse("//* JUST A COMMENT\n//* ANOTHER\n")
        assert program.job is None
        assert program.steps == ()
