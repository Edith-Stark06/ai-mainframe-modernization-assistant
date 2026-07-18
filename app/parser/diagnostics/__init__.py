"""
Diagnostics Sub-package.

Purpose:
    Compiler diagnostic collection and reporting layer for the COBOL
    recursive-descent parser.  All parser components emit structured
    :class:`~app.parser.diagnostics.recovery.SyntaxDiagnostic` records
    rather than raising exceptions for recoverable errors, enabling the
    parser to continue past the first error and deliver a complete error
    report in a single parse pass.

Responsibilities:
    - Re-export the public API of :mod:`app.parser.diagnostics.recovery`
      so that callers can import from this package directly.

Exported Names:
    - :class:`~app.parser.diagnostics.recovery.SyntaxDiagnostic`
    - :class:`~app.parser.diagnostics.recovery.RecoveryContext`
    - :class:`~app.parser.diagnostics.recovery.SynchronisationPoint`
    - :class:`~app.parser.diagnostics.recovery.RecoveryManager`
    - :func:`~app.parser.diagnostics.recovery.synchronise`

Dependencies:
    - :mod:`app.parser.diagnostics.recovery` — implementation module.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from app.parser.diagnostics.recovery import (
    RecoveryContext,
    RecoveryManager,
    SynchronisationPoint,
    SyntaxDiagnostic,
    synchronise,
)

__all__ = [
    "RecoveryContext",
    "RecoveryManager",
    "SynchronisationPoint",
    "SyntaxDiagnostic",
    "synchronise",
]
