"""
JCL Invocation Correlation.

Purpose:
    Given a COBOL program name and a workspace inventory, find every
    JCL job step in the workspace that actually runs it, via
    ``EXEC PGM=<name>``. This is the honest, buildable half of
    "JCL/workspace correlation": which job/step invokes a given
    program is directly readable from the ``EXEC`` statement's own
    ``PGM=`` parameter -- unlike VSAM-ness, which standard JCL syntax
    never states at all (a VSAM dataset's ``DD`` statement looks
    identical to a sequential one; VSAM-ness is a catalog attribute
    assigned when the dataset was defined via IDCAMS, not something the
    ``DD`` statement that merely references it declares). This module
    builds exactly the correlation JCL syntax actually supports, and
    does not claim VSAM detection it cannot honestly provide.

Responsibilities:
    - :func:`find_invoking_jobs` -- scan every ``.jcl`` file already
      discovered in a :class:`~app.workspace.models.WorkspaceInventory`,
      parse each with :class:`~app.jcl.service.JclAnalysisService`, and
      collect every step whose ``PGM=`` target matches *program_name*
      (case-insensitive, matching COBOL's own case-insensitive
      ``PROGRAM-ID`` convention).

Non-responsibilities:
    - ``PROC=`` steps that indirectly run *program_name* via a
      cataloged procedure -- :mod:`app.jcl.parser` does not expand
      ``PROC``, so a procedure's own ``PGM=`` is invisible here (see
      :mod:`app.jcl`'s own module docstring for why).
    - VSAM dataset detection from ``DD`` statements (see Purpose above).
    - Malformed/unparseable ``.jcl`` files -- skipped silently (already
      diagnosed, if at all, by :mod:`app.jcl` itself); this module
      never raises for one bad file among many, matching
      :mod:`app.workspace.search`'s own convention.

Dependencies:
    - app.jcl.service -- JclAnalysisService
    - app.workspace.models -- FileType, WorkspaceInventory
    - Python standard library (dataclasses, pathlib).

Examples:
    Finding which job steps invoke ``PAYROLL``::

        from app.workspace.jcl_correlation import find_invoking_jobs

        invocations = find_invoking_jobs("PAYROLL", inventory)
        for inv in invocations:
            print(inv.jcl_filename, inv.job_name, inv.step_name)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.jcl.service import JclAnalysisService
from app.workspace.models import FileType, WorkspaceInventory

__all__ = ["JclInvocation", "find_invoking_jobs"]


@dataclass(frozen=True)
class JclInvocation:
    """
    One JCL job step that runs a program via ``EXEC PGM=``.

    Attributes:
        jcl_filename: Basename of the ``.jcl`` file this invocation was
            found in.
        job_name: The enclosing job's name, or ``None`` if the job
            stream had no recognisable ``JOB`` statement.
        step_name: The ``EXEC`` statement's own step name.
        line: 1-based source line the ``EXEC`` statement started on.
    """

    jcl_filename: str
    job_name: str | None
    step_name: str
    line: int


def find_invoking_jobs(
    program_name: str, inventory: WorkspaceInventory
) -> tuple[JclInvocation, ...]:
    """
    Find every JCL job step in *inventory* that runs *program_name*.

    Args:
        program_name: The COBOL program's ``PROGRAM-ID``, matched
            case-insensitively.
        inventory: The workspace's already-built file inventory (see
            :class:`~app.workspace.inventory.InventoryBuilder`).

    Returns:
        Every matching invocation, in inventory file order then source
        order within each file. Empty if *program_name* is blank or no
        ``.jcl`` file in the workspace has a matching ``EXEC PGM=`` --
        never fabricated.
    """
    target = program_name.strip().upper()
    if not target:
        return ()

    service = JclAnalysisService()
    found: list[JclInvocation] = []
    for scanned in inventory.files:
        if scanned.file_type != FileType.JCL:
            continue

        result = service.analyze_file(Path(scanned.path))
        if not result.success or result.program is None:
            continue

        job_name = result.program.job.name if result.program.job else None
        for step in result.program.steps:
            if step.program is not None and step.program.strip().upper() == target:
                found.append(
                    JclInvocation(
                        jcl_filename=scanned.filename,
                        job_name=job_name,
                        step_name=step.name,
                        line=step.line,
                    )
                )
    return tuple(found)
