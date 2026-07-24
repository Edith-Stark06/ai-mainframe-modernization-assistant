"""
Backend Package.

Purpose:
    Provide the language-specific code generation backends that consume
    an :class:`~app.ir.program.IRProgram` and emit target-language source code.

    The backend is intentionally separate from the compiler frontend (lexer,
    parser, semantic analysis, IR) so that each layer evolves independently.

Current backends:

    * :mod:`app.backend.java` — Java / Spring Boot generation.

Non-responsibilities:
    - Parsing, lexing, or semantic analysis.
    - IR construction or optimisation.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

__all__: list[str] = []
