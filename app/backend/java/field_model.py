"""
Java Field Model.

Purpose:
    Define :class:`JavaField` — an immutable value object that represents
    a single Java instance field to be emitted by the backend generator.

    :class:`JavaField` is the intermediate representation between the COBOL
    data-item symbol table and the rendered Java source string.  The generator
    builds a list of :class:`JavaField` objects from the IR and then renders
    them into field declarations.

Responsibilities:
    - Carry the field's Java name, Java type, and optional initial value.
    - Carry the declared PICTURE width/scale (``digits``, ``decimal_places``,
      ``signed``, ``length``) so a later stage can reproduce COBOL DISPLAY
      formatting (zero-padding, space-padding) without recomputing it from
      the raw PIC string (task #stage31; see
      :mod:`app.backend.java.condition_context` and
      :func:`~app.backend.java.statement_emitter.emit_display`). ``None``/
      defaults mean "not a formattable elementary item" (a group, or a
      symbol with no resolved ``cobol_type``).
    - Provide :meth:`render` to format the field as a Java source line.

Non-responsibilities:
    - COBOL name conversion (handled by :mod:`app.backend.java.naming`).
    - COBOL type mapping (handled by :mod:`app.backend.java.type_mapper`).
    - Code emission (handled by :mod:`app.backend.java.generator`).
    - Applying the formatting these attributes describe (handled by
      :mod:`app.backend.java.statement_emitter`).

Examples:
    Creating and rendering a field::

        from app.backend.java.field_model import JavaField

        f = JavaField(java_name="wsCount", java_type="int", initial_value="0")
        f.render()
        # 'private int wsCount = 0;'

        f2 = JavaField(java_name="customerName", java_type="String")
        f2.render()
        # 'private String customerName;'

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["JavaField"]


@dataclass(frozen=True)
class JavaField:
    """
    Immutable representation of a single Java instance field.

    Attributes:
        java_name:
            The lowerCamelCase Java field identifier (e.g. ``"wsCount"``).
        java_type:
            The Java type string (e.g. ``"String"``, ``"int"``, ``"double"``).
        initial_value:
            Optional initial value literal as a Java expression string
            (e.g. ``'"WELCOME"'``, ``"0"``, ``"0.0"``).  ``None`` means no
            initializer is emitted.
        cobol_name:
            The original COBOL data-item name, preserved for diagnostics and
            documentation comments.  Optional.
        digits:
            Total declared PICTURE digit width (integer + decimal places
            combined, e.g. ``9`` for ``PIC 9(7)V99``) for a numeric
            elementary item, straight from
            :attr:`~app.parser.semantic.types.NumericType.digits`.  ``None``
            for a non-numeric field or one with no resolved type.
        decimal_places:
            Number of digits to the right of the assumed decimal point (the
            ``V`` position), straight from
            :attr:`~app.parser.semantic.types.NumericType.decimal_places`.
            ``0`` for an integer field or a non-numeric field.
        signed:
            ``True`` when the PIC clause began with ``S``, straight from
            :attr:`~app.parser.semantic.types.NumericType.signed`.  Signed
            DISPLAY formatting is out of scope for task #stage31; carried
            here only so a formatter can *decline* to format such a field
            rather than guess. Defaults to ``False``.
        length:
            Declared character width of an alphanumeric elementary item,
            straight from
            :attr:`~app.parser.semantic.types.AlphanumericType.length`.
            ``None`` for a non-alphanumeric field or one with no resolved
            type.

    Examples:
        >>> from app.backend.java.field_model import JavaField
        >>> f = JavaField(java_name="wsCount", java_type="int", initial_value="0")
        >>> f.render()
        'private int wsCount = 0;'
        >>> JavaField(java_name="customerName", java_type="String").render()
        'private String customerName;'
    """

    java_name: str = field(default="")
    java_type: str = field(default="String")
    initial_value: str | None = field(default=None)
    cobol_name: str = field(default="")
    digits: int | None = field(default=None)
    decimal_places: int = field(default=0)
    signed: bool = field(default=False)
    length: int | None = field(default=None)

    def render(self, indent: str = "    ") -> str:
        """
        Return a formatted Java field declaration string.

        Args:
            indent:
                Leading whitespace for the declaration.  Defaults to four spaces.

        Returns:
            A Java field declaration such as::

                private int wsCount = 0;
                private String customerName;

        Examples:
            >>> JavaField(java_name="x", java_type="int", initial_value="1").render()
            '    private int x = 1;'
            >>> JavaField(java_name="y", java_type="String").render()
            '    private String y;'
        """
        base = f"{indent}private {self.java_type} {self.java_name}"
        if self.initial_value is not None:
            return f"{base} = {self.initial_value};"
        return f"{base};"
