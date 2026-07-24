"""
Java Backend Package.

Purpose:
    Provide the Java code-generation layer that consumes an
    :class:`~app.ir.program.IRProgram` and emits valid Java source code.

Public API:
    * :func:`~app.backend.java.generator.generate` — main entry point.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from app.backend.java.generator import generate

__all__ = ["generate"]
