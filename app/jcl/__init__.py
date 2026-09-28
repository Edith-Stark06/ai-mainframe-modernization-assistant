"""
JCL (Job Control Language) Analysis Sub-package (task #stage46).

Purpose:
    Parse IBM z/OS JCL job streams -- ``JOB``/``EXEC``/``DD`` statements,
    continuation lines, comments, and in-stream data -- into a small AST
    that the rest of the platform can inspect (which programs a job
    runs, which datasets each step reads/writes), mirroring the COBOL
    pipeline's own lexer -> AST -> analysis-service shape at a scale
    matched to JCL's much smaller grammar.

Responsibilities:
    - :mod:`app.jcl.lexer` -- tokenize raw JCL text.
    - :mod:`app.jcl.ast` -- immutable AST node types (``JclJob``,
      ``JclStep``, ``JclDDStatement``, ...).
    - :mod:`app.jcl.parser` -- build the AST from tokens, degrading
      gracefully (never fabricating, never crashing) on any construct
      out of this stage's scope.
    - :mod:`app.jcl.service` -- ``JclAnalysisService``, the production
      entry point, mirroring :class:`app.analysis.service.AnalysisService`.
    - :mod:`app.jcl.models` -- result/diagnostic dataclasses.

Non-responsibilities (see each module's own docstring for the full
rationale):
    - Cataloged/in-stream ``PROC`` expansion -- a ``PROC`` reference is
      captured by name, never textually expanded.
    - Conditional JCL (``IF``/``THEN``/``ELSE``/``ENDIF``, ``COND=``
      evaluation, ``SET``, ``INCLUDE``, ``OUTPUT``) -- recognised as
      present, not interpreted.
    - Symbolic parameter substitution (``&SYSUID.``, ``&&TEMP``) --
      captured as literal text, never substituted.
    - Execution: nothing in this sub-package runs a job or predicts its
      outcome; it only describes the job stream's static structure.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""
