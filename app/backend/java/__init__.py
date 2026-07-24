"""
Java Backend Package.

Purpose:
    Provide the Java code-generation layer that consumes an
    :class:`~app.ir.program.IRProgram` and emits valid Java source code.

Public API:
    * :func:`~app.backend.java.generator.generate` — main entry point.
    * :func:`~app.backend.java.generator.generate_with_diagnostics` — returns source + diagnostics.
    * :func:`~app.backend.java.generator.build_fields_from_symbols` — convert symbols to Java fields.
    * :func:`~app.backend.java.naming.to_java_field_name` — COBOL → lowerCamelCase.
    * :func:`~app.backend.java.type_mapper.map_cobol_type` — CobolType → Java type string.
    * :class:`~app.backend.java.field_model.JavaField` — field value object.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from app.backend.java.field_model import JavaField
from app.backend.java.generator import (
    BackendDiagnostic,
    BackendSeverity,
    GenerationResult,
    build_fields_from_symbols,
    generate,
    generate_with_diagnostics,
)
from app.backend.java.naming import to_java_field_name
from app.backend.java.type_mapper import map_cobol_type

__all__ = [
    "BackendDiagnostic",
    "BackendSeverity",
    "GenerationResult",
    "JavaField",
    "build_fields_from_symbols",
    "generate",
    "generate_with_diagnostics",
    "map_cobol_type",
    "to_java_field_name",
]
