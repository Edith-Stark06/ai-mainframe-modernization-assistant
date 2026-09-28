"""
JCL Statement Lexer (task #stage46).

Purpose:
    Convert raw JCL text into an ordered list of :class:`RawStatement`
    records -- one per logical JCL statement, with continuation lines
    already joined and comment/in-stream-data lines already skipped.
    This is the JCL analogue of :class:`~app.parser.lexer.lexer.CobolLexer`,
    but line-oriented rather than character-oriented, matching JCL's own
    much simpler, positional grammar: every statement is a ``//`` line of
    the shape ``//name operation parameters  comments``.

Responsibilities:
    - Recognise a JCL statement line's four fields: ``name`` (columns
      3+, ending at the first whitespace; absent on a continuation
      line), ``operation`` (``JOB``/``EXEC``/``DD``/... or a
      continuation's absent operation), ``parameters`` (comma-separated,
      quote- and paren-aware), and free-text ``comments``.
    - Join a statement's continuation lines (a parameter list ending in
      a trailing comma continues on the next ``//`` line, which has a
      blank name field) into one logical statement.
    - Skip ``//*`` comment lines and in-stream data (the lines between a
      ``DD *``/``DD DATA`` statement and its terminating ``/*`` or the
      next ``//`` statement) -- neither is tokenized as JCL syntax.
    - Split a statement's raw parameter text into individual
      :class:`JclParameter` values, respecting quoted strings and
      parenthesised sub-lists so an embedded comma never splits a
      parameter it belongs to.

Non-responsibilities:
    - AST construction (:mod:`app.jcl.parser`).
    - Symbolic parameter substitution, ``PROC`` expansion, conditional
      JCL evaluation -- see :mod:`app.jcl`'s own module docstring.
    - Column-71 fixed-width line wrapping -- only the explicit
      trailing-comma continuation convention is recognised (unevidenced
      either way; this is the far more common modern authoring style
      and is unambiguous to detect).

Dependencies:
    - loguru -- structured logging
    - Python standard library (dataclasses).

Examples:
    Tokenizing a JCL job stream::

        from app.jcl.lexer import tokenize

        statements = tokenize(source)
        assert all(s.operation for s in statements if s.name)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

__all__ = ["JclParameter", "RawStatement", "parse_parameters", "tokenize"]

_STMT_PREFIX = "//"
_COMMENT_PREFIX = "//*"
_DELIMITER_STATEMENT = "/*"


@dataclass(frozen=True)
class JclParameter:
    """
    One parameter of a JCL statement.

    Attributes:
        key:
            The keyword name (e.g. ``"DSN"`` in ``DSN=MY.DATA``), or
            ``None`` for a positional parameter (e.g. the accounting
            information in ``JOB (ACCT123),'NAME'``).
        value:
            The parameter's raw text, exactly as written. A
            parenthesised sub-list (e.g. ``DISP=(NEW,CATLG,DELETE)``)
            keeps its parentheses and internal commas -- it is not
            further decomposed (a documented simplification; see the
            module docstring).
    """

    key: str | None
    value: str


@dataclass(frozen=True)
class RawStatement:
    """
    One logical JCL statement, continuation lines already joined.

    Attributes:
        name:
            The name field (e.g. the job name, step name, or DD name),
            or ``None`` if the statement has none (a continuation line
            always has none; a bare ``//`` null statement has none
            either).
        operation:
            The operation field (``"JOB"``, ``"EXEC"``, ``"DD"``, or
            any other JCL keyword statement), uppercased, or ``None``
            for a null statement (``//`` alone).
        parameters:
            The parsed parameter list (see :func:`parse_parameters`).
        comment_text:
            Free-text content after the parameter field, or a bare
            ``//*`` comment line's own text. Never semantically
            interpreted.
        line:
            The 1-based source line number the statement started on
            (its first physical line, before any continuation joining).
    """

    name: str | None
    operation: str | None
    parameters: tuple[JclParameter, ...]
    comment_text: str
    line: int
    is_comment: bool = field(default=False)


def tokenize(source: str) -> list[RawStatement]:
    """
    Convert raw JCL *source* into an ordered list of :class:`RawStatement`.

    Args:
        source: The complete raw JCL text.

    Returns:
        One :class:`RawStatement` per logical statement (continuation
        lines already joined), in source order. ``//*`` comment lines
        and in-stream data lines contribute nothing.
    """
    lines = source.splitlines()
    statements: list[RawStatement] = []
    i = 0
    n = len(lines)
    in_stream_data = False

    while i < n:
        raw_line = lines[i]

        if in_stream_data:
            if raw_line.startswith(_DELIMITER_STATEMENT) or raw_line.startswith(
                _STMT_PREFIX
            ):
                in_stream_data = False
                # Re-process this line as ordinary JCL (falls through).
            else:
                i += 1
                continue

        if not raw_line.startswith(_STMT_PREFIX):
            # Blank line, or text outside any recognised structure --
            # neither is JCL syntax; skip it silently, matching the
            # COBOL lexer's own "never crash on stray text" precedent.
            i += 1
            continue

        if raw_line.startswith(_COMMENT_PREFIX):
            statements.append(
                RawStatement(
                    name=None,
                    operation=None,
                    parameters=(),
                    comment_text=raw_line[len(_COMMENT_PREFIX) :],
                    line=i + 1,
                    is_comment=True,
                )
            )
            i += 1
            continue

        start_line = i + 1
        body = raw_line[len(_STMT_PREFIX) :]
        name, rest = _split_name(body)
        operation, param_text, comment_text = _split_operation(rest)
        i += 1

        # Join continuation lines: a parameter list ending in a
        # trailing comma continues on the next "//" line, which has a
        # blank name field and (unlike the opening line) no operation
        # field of its own -- its whole remainder is more parameter
        # text, split the same way the parameter/comment boundary
        # always is.
        while param_text.rstrip().endswith(",") and i < n:
            cont_line = lines[i]
            if not cont_line.startswith(_STMT_PREFIX) or cont_line.startswith(
                _COMMENT_PREFIX
            ):
                break
            cont_body = cont_line[len(_STMT_PREFIX) :]
            cont_name, cont_rest = _split_name(cont_body)
            if cont_name is not None:
                # A genuine new statement, not a continuation -- stop.
                break
            cont_param_text, cont_comment_text = _split_params_and_comment(cont_rest)
            param_text = (
                param_text.rstrip().rstrip(",") + "," + cont_param_text.lstrip()
            )
            if cont_comment_text:
                comment_text = cont_comment_text
            i += 1

        parameters = parse_parameters(param_text)

        if name is None and operation is None and not param_text.strip():
            logger.debug("JclLexer: null statement '//' at line {}.", start_line)

        if operation is not None and operation.upper() == "DD":
            for p in parameters:
                if p.key is None and p.value.upper() in ("*", "DATA"):
                    in_stream_data = True
                    break

        statements.append(
            RawStatement(
                name=name,
                operation=operation.upper() if operation else None,
                parameters=parameters,
                comment_text=comment_text,
                line=start_line,
            )
        )

    return statements


def _split_name(body: str) -> tuple[str | None, str]:
    """Split ``body`` (the text after ``//``) into ``(name, rest)``.

    A continuation line, or a null statement, has no name -- ``body``
    starts with whitespace (or is empty), and ``name`` is ``None``.
    """
    if not body or body[0].isspace():
        return None, body.lstrip()
    idx = 0
    while idx < len(body) and not body[idx].isspace():
        idx += 1
    return body[:idx], body[idx:].lstrip()


def _split_operation(rest: str) -> tuple[str | None, str, str]:
    """Split the text after the name field into ``(operation, params, comment)``."""
    rest = rest.lstrip()
    if not rest:
        return None, "", ""
    idx = 0
    while idx < len(rest) and not rest[idx].isspace():
        idx += 1
    operation = rest[:idx]
    remainder = rest[idx:].lstrip()
    param_text, comment_text = _split_params_and_comment(remainder)
    return operation, param_text, comment_text


def _split_params_and_comment(remainder: str) -> tuple[str, str]:
    """
    Split the text after the operation field into ``(parameters, comment)``.

    The parameter field ends at the first whitespace that is not inside
    a quoted string or parenthesised sub-list; everything after that is
    free-text comment.
    """
    depth = 0
    in_quote = False
    for idx, ch in enumerate(remainder):
        if in_quote:
            if ch == "'":
                in_quote = False
            continue
        if ch == "'":
            in_quote = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch.isspace() and depth == 0:
            return remainder[:idx], remainder[idx:].lstrip()
    return remainder, ""


def parse_parameters(text: str) -> tuple[JclParameter, ...]:
    """
    Split raw parameter *text* into individual :class:`JclParameter` values.

    Splits on top-level commas only -- a comma inside a quoted string
    (``'...'``) or a parenthesised sub-list (``(...)``) does not end a
    parameter. Each resulting segment is a keyword parameter
    (``key=value``, split on the first top-level ``=``) if it contains
    one outside quotes/parens, otherwise a positional parameter.

    Args:
        text: The raw parameter field text (e.g.
            ``"PGM=IEFBR14,PARM='X,Y'"``).

    Returns:
        A tuple of :class:`JclParameter`, in order. Empty when *text* is
        blank.
    """
    segments = _split_top_level(text, ",")
    params: list[JclParameter] = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        eq_segments = _split_top_level(seg, "=")
        if len(eq_segments) >= 2:
            key = eq_segments[0].strip()
            value = "=".join(eq_segments[1:]).strip()
            params.append(JclParameter(key=key, value=value))
        else:
            params.append(JclParameter(key=None, value=seg))
    return tuple(params)


def _split_top_level(text: str, sep: str) -> list[str]:
    """Split *text* on *sep* at paren/quote depth 0 only."""
    parts: list[str] = []
    depth = 0
    in_quote = False
    current: list[str] = []
    for ch in text:
        if in_quote:
            current.append(ch)
            if ch == "'":
                in_quote = False
            continue
        if ch == "'":
            in_quote = True
            current.append(ch)
        elif ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts
