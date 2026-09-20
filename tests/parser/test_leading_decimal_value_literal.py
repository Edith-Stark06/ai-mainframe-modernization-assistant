"""
Leading-decimal-point numeric ``VALUE`` literals (Stage 22).

Purpose:
    The lexer only forms a decimal ``NUMBER`` token when digits come *before*
    the point (``0.50``); a literal that *starts* with the point (``.50``) is
    split into ``PERIOD('.')`` + ``NUMBER('50')``. The ``VALUE`` clause took
    only the first token as the whole literal, so:

    * ``VALUE .50``  -- took ``.`` as the value, left ``50`` behind, failed the
      terminating-period check (``SYN005``) and **dropped the item**;
    * ``VALUE -.50`` / ``VALUE +.50`` -- took the bare sign, kept the item with
      the garbage value ``'-'`` / ``'+'`` and mis-read the leftover ``.50``.

    A ``.`` directly against the digits that follow it is a decimal point (a
    *terminating* period is always followed by whitespace), so the ``VALUE``
    clause now joins ``[sign] . digits`` when -- and only when -- each piece
    sits directly against the next. The fix is parser-only: the lexer contract
    (``+``/``-`` are their own ``UNKNOWN`` tokens; ``.50`` is two tokens) is
    unchanged and re-asserted here, and Stage 21's signed-literal behavior is
    re-pinned.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.analysis.service import AnalysisService
from app.dataset.corpus import load_training_corpus
from app.parser.lexer.lexer import CobolLexer
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.syntax.program_parser import ProgramParser

needs_java = pytest.mark.skipif(
    shutil.which("javac") is None or shutil.which("java") is None,
    reason="javac/java not available",
)

_HEAD = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LEADDEC.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
"""
_TAIL = """\
       PROCEDURE DIVISION.
       MAIN-PARA.
           STOP RUN.
"""


def _program(*data_lines: str, procedure: str = _TAIL) -> str:
    return _HEAD + "".join(f"       {line}\n" for line in data_lines) + procedure


def _tokens(source: str):
    return CobolLexer().tokenize(source, filename="s.cbl")


def _items(source: str) -> dict[str, str | None]:
    """``{data-name: VALUE lexeme}`` for every elementary item that parsed."""
    program = ProgramParser().parse(_tokens(source))
    out: dict[str, str | None] = {}

    def walk(items) -> None:
        for item in items:
            if hasattr(item, "picture"):
                out[item.name] = item.value
            walk(getattr(item, "children", ()) or ())

    walk(program.data_division.working_storage.items)
    return out


def _analyse(source: str, tmp_path: Path):
    path = tmp_path / "leaddec.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _codes(result) -> list[str]:
    return [str(getattr(d, "code", "")) for d in result.syntax_diagnostics]


def _messages(result) -> list[str]:
    return [str(getattr(d, "message", "")) for d in result.syntax_diagnostics]


# ===========================================================================
# 1. The lexer contract is unchanged (the fix is parser-only)
# ===========================================================================


def _after_value(clause: str) -> list[tuple[str, str]]:
    toks = _tokens(_program(f"01  A PIC S9(3)V99 {clause}."))
    i = next(k for k, t in enumerate(toks) if t.lexeme == "VALUE")
    end = next(k for k in range(i, len(toks)) if toks[k].lexeme == "PROCEDURE")
    return [(t.type.name, t.lexeme) for t in toks[i + 1 : end]]


@pytest.mark.parametrize(
    ("clause", "expected"),
    [
        # the leading point is a separate PERIOD token: NOT one NUMBER
        ("VALUE .50", [("PERIOD", "."), ("NUMBER", "50"), ("PERIOD", ".")]),
        (
            "VALUE -.50",
            [("UNKNOWN", "-"), ("PERIOD", "."), ("NUMBER", "50"), ("PERIOD", ".")],
        ),
        (
            "VALUE +.50",
            [("UNKNOWN", "+"), ("PERIOD", "."), ("NUMBER", "50"), ("PERIOD", ".")],
        ),
        # a decimal with a leading digit is ONE number token
        ("VALUE 0.50", [("NUMBER", "0.50"), ("PERIOD", ".")]),
        ("VALUE -0.50", [("UNKNOWN", "-"), ("NUMBER", "0.50"), ("PERIOD", ".")]),
        (
            "VALUE +000450000.00",
            [("UNKNOWN", "+"), ("NUMBER", "000450000.00"), ("PERIOD", ".")],
        ),
    ],
)
def test_lexer_token_streams_are_unchanged(clause, expected) -> None:
    assert _after_value(clause) == expected


# ===========================================================================
# 2. Leading-decimal literals parse as ONE literal and keep the item
# ===========================================================================


@pytest.mark.parametrize(
    ("clause", "expected"),
    [
        ("VALUE .50", ".50"),
        ("VALUE -.50", "-.50"),
        ("VALUE +.50", "+.50"),
        ("VALUE .5", ".5"),
        ("VALUE .05", ".05"),
        ("VALUE .123456", ".123456"),
        ("VALUE -.5", "-.5"),
        ("VALUE IS .50", ".50"),
        ("VALUE IS -.50", "-.50"),
        ("VALUE IS +.50", "+.50"),
    ],
)
def test_leading_decimal_value_is_one_literal(clause, expected) -> None:
    assert _items(_program(f"01  A PIC S9(3)V99 {clause}.")) == {"A": expected}


def test_leading_decimal_before_and_after_usage_clauses() -> None:
    items = _items(
        _program(
            "01  A PIC S9(3)V99 COMP-3 VALUE -.50.",
            "01  B PIC S9(3)V99 VALUE .25 COMP-3.",
        )
    )
    assert items == {"A": "-.50", "B": ".25"}


def test_items_around_a_leading_decimal_are_unaffected(tmp_path) -> None:
    """The bug left ``50`` in the stream, which the item loop then read as an
    (invalid) level number and reported -- so the *next* item was at risk."""
    source = _program(
        "01  FIRST-ITEM PIC 9(3) VALUE 7.",
        "01  DEC-ITEM PIC 9V99 VALUE .50.",
        "01  NEG-ITEM PIC S9V99 VALUE -.25.",
        "01  LAST-ITEM PIC X(4) VALUE 'ABCD'.",
    )
    items = _items(source)
    assert list(items) == ["FIRST-ITEM", "DEC-ITEM", "NEG-ITEM", "LAST-ITEM"]
    assert items == {
        "FIRST-ITEM": "7",
        "DEC-ITEM": ".50",
        "NEG-ITEM": "-.25",
        "LAST-ITEM": "'ABCD'",
    }
    result = _analyse(source, tmp_path)
    assert result.syntax_diagnostics == []


def test_leading_decimal_no_longer_produces_a_syntax_error(tmp_path) -> None:
    result = _analyse(
        _program("01  A PIC 9V99 VALUE .50.", "01  B PIC S9V99 VALUE -.50."), tmp_path
    )
    assert "SYN005" not in _codes(result)
    assert "SYN001" not in _codes(result)


def test_a_terminating_period_is_never_mistaken_for_a_decimal_point() -> None:
    """``VALUE 5.`` then another item -- on the next line or after whitespace on
    the same line -- keeps its period as a terminator: the digits that follow
    are not *directly* against it."""
    assert _items(_program("01  A PIC 9 VALUE 5.", "01  B PIC 9 VALUE 6.")) == {
        "A": "5",
        "B": "6",
    }
    assert _items(_program("01  A PIC 9 VALUE 5. 01  B PIC 9 VALUE 6.")) == {
        "A": "5",
        "B": "6",
    }
    assert _items(_program("01  A PIC 9V9 VALUE .5. 01  B PIC 9 VALUE 6.")) == {
        "A": ".5",
        "B": "6",
    }


# ===========================================================================
# 3. Regression: everything that is not a leading-decimal literal
# ===========================================================================


@pytest.mark.parametrize(
    ("clause", "expected"),
    [
        ("VALUE 0.50", "0.50"),
        ("VALUE -0.50", "-0.50"),
        ("VALUE +0.50", "+0.50"),
        ("VALUE 000450000.00", "000450000.00"),
        ("VALUE +000450000.00", "+000450000.00"),  # Stage 21
        ("VALUE -000450000.00", "-000450000.00"),  # Stage 21
        ("VALUE +5", "+5"),  # Stage 21
        ("VALUE -5", "-5"),  # Stage 21
        ("VALUE IS -5", "-5"),  # Stage 21
        ("VALUE 5", "5"),
        ("VALUE 0", "0"),
        ("VALUE 'TEXT'", "'TEXT'"),
        ("VALUE 'HAS .50 IN IT'", "'HAS .50 IN IT'"),
        ("VALUE ZERO", "ZERO"),
        ("VALUE ZEROS", "ZEROS"),
        ("VALUE SPACES", "SPACES"),
        ("VALUE SPACE", "SPACE"),
        ("VALUE HIGH-VALUES", "HIGH-VALUES"),
    ],
)
def test_other_value_forms_are_unchanged(clause, expected) -> None:
    assert _items(_program(f"01  A PIC X(20) {clause}.")) == {"A": expected}


# ===========================================================================
# 4. Detached / malformed forms are rejected, not silently accepted
# ===========================================================================


@pytest.mark.parametrize(
    "clause",
    [
        "VALUE + .50",  # detached sign
        "VALUE - .50",
        "VALUE IS + .50",
        "VALUE . 50",  # detached point
        "VALUE IS . 50",
        "VALUE -.",  # sign, point, nothing
        "VALUE + 5",  # Stage 21: detached sign before an integer
        "VALUE - 5",
    ],
)
def test_detached_or_incomplete_forms_are_rejected(clause, tmp_path) -> None:
    """COBOL requires the sign and the point to sit directly against the digits.
    None of these is accepted as a numeric literal: the item is abandoned with a
    ``SYN005`` (never kept with a garbage value such as ``'+'``), and the item
    after it still parses."""
    source = _program(f"01  A PIC S9(3)V99 {clause}.", "01  B PIC 9(3) VALUE 1.")
    assert _items(source) == {"B": "1"}
    assert "SYN005" in _codes(_analyse(source, tmp_path))


def test_a_detached_sign_before_an_integer_keeps_its_stage_21_diagnostic(
    tmp_path,
) -> None:
    result = _analyse(
        _program("01  A PIC S9(3) VALUE + 5.", "01  B PIC 9(3) VALUE 1."), tmp_path
    )
    assert any(
        "expected '.' to terminate data item" in m for m in _messages(result)
    ), _messages(result)


def test_a_detached_sign_before_a_point_names_the_sign_problem(tmp_path) -> None:
    result = _analyse(
        _program("01  A PIC S9V99 VALUE + .50.", "01  B PIC 9(3) VALUE 1."), tmp_path
    )
    assert any(
        "numeric literal directly after the sign" in m for m in _messages(result)
    ), _messages(result)


def test_a_malformed_fraction_is_not_joined(tmp_path) -> None:
    """``.5.5`` lexes as ``PERIOD`` + ``NUMBER('5.5')``: the second token is not a
    run of digits, so it is not a fraction and the item is abandoned."""
    source = _program("01  A PIC 9V99 VALUE .5.5.", "01  B PIC 9(3) VALUE 1.")
    assert _items(source) == {"B": "1"}
    assert "SYN005" in _codes(_analyse(source, tmp_path))


# ===========================================================================
# 5. Isolation: nothing outside the elementary-item VALUE clause moved
# ===========================================================================


def _diag_messages(source: str, tmp_path: Path) -> list[str]:
    return _messages(_analyse(source, tmp_path))


def test_procedure_division_leading_decimals_are_untouched(tmp_path) -> None:
    """Known, separate gap (a leading ``.`` in a *procedure* operand): the
    same PERIOD+NUMBER tokens still fail there, exactly as before. The fix
    lives only in the data-item ``VALUE`` clause."""
    for stmt, expected in (
        ("MOVE .5 TO WS-A", "expected source operand after MOVE"),
        ("ADD .5 TO WS-A", "expected operand after ADD"),
        ("IF WS-A > .5 DISPLAY 'X' END-IF", "expected operand for IF condition"),
    ):
        source = _program(
            "01  WS-A PIC 9V99 VALUE 1.00.",
            procedure=(
                "       PROCEDURE DIVISION.\n       MAIN-PARA.\n"
                f"           {stmt}\n           STOP RUN.\n"
            ),
        )
        assert any(expected in m for m in _diag_messages(source, tmp_path)), stmt


def test_picture_leading_decimals_are_untouched(tmp_path) -> None:
    """``PIC .99`` is a different production and is deliberately not part of
    this stage; it behaves as before. (Level-88 ``VALUE .5`` was also left
    alone here and was fixed separately in Stage 23 --
    ``tests/parser/test_level88_value_literals.py``.)"""
    pic = _analyse(_program("01  P PIC .99 VALUE 0.5."), tmp_path)
    assert any("expected picture string after PIC" in m for m in _messages(pic))


# ===========================================================================
# 6. Propagation: AST -> symbol -> Java field -> executed value
# ===========================================================================

_PROGRAM = _program(
    "01  WS-HALF     PIC S9(3)V99 VALUE .50.",
    "01  WS-NEG-HALF PIC S9(3)V99 VALUE -.50.",
    "01  WS-POS-HALF PIC S9(3)V99 VALUE +.50.",
    "01  WS-LEAD0    PIC S9(3)V99 VALUE 0.50.",
    "01  WS-NEG-LEAD0 PIC S9(3)V99 VALUE -0.50.",
    "01  WS-SMALL    PIC 9V9(4) VALUE .0125.",
    "01  WS-BAL      PIC S9(9)V99 COMP-3 VALUE +000450000.00.",
    "01  WS-TEXT     PIC X(6) VALUE 'ABC'.",
    "01  WS-BLANK    PIC X(4) VALUE SPACES.",
)


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    return _analyse(_PROGRAM, tmp_path_factory.mktemp("leaddec"))


def _field_lines(java: str) -> dict[str, str]:
    return {
        m.group(2): m.group(0).strip()
        for m in re.finditer(
            r"^\s+private (String|int|double) (\w+)( = [^;\n]*)?;", java, re.M
        )
    }


def test_symbol_table_carries_the_leading_decimal_value(result) -> None:
    # only the (unrelated, expected) SYN200 for the skipped COMP-3 clause
    assert set(_codes(result)) == {"SYN200"}
    by_name = {
        s.name: s
        for s in SemanticAnalyzer().analyse(result.ast).symbol_table.all_symbols()
    }
    assert by_name["WS-HALF"].value == ".50"
    assert by_name["WS-NEG-HALF"].value == "-.50"
    assert by_name["WS-POS-HALF"].value == "+.50"
    assert by_name["WS-SMALL"].value == ".0125"


def test_java_fields_carry_value_correct_initializers(result) -> None:
    fields = _field_lines(result.java_source)
    assert fields["wsHalf"] == "private double wsHalf = 0.50;"
    assert fields["wsNegHalf"] == "private double wsNegHalf = -0.50;"
    assert fields["wsPosHalf"] == "private double wsPosHalf = 0.50;"
    assert fields["wsLead0"] == "private double wsLead0 = 0.50;"
    assert fields["wsNegLead0"] == "private double wsNegLead0 = -0.50;"
    assert fields["wsSmall"] == "private double wsSmall = 0.0125;"
    assert fields["wsBal"] == "private double wsBal = 450000.00;"  # Stage 21
    assert fields["wsText"] == 'private String wsText = "ABC";'
    assert fields["wsBlank"] == 'private String wsBlank = "";'
    assert not re.search(r"= \+|= \.|= -\.", result.java_source)


_READER = """\
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Comparator;

public class Reader {
    public static void main(String[] args) throws Exception {
        Class<?> c = Class.forName(args[0]);
        Object o = c.getDeclaredConstructor().newInstance();
        Field[] fs = c.getDeclaredFields();
        Arrays.sort(fs, Comparator.comparing(Field::getName));
        for (Field f : fs) { f.setAccessible(true); System.out.println(f.getName() + "=" + f.get(o)); }
    }
}
"""


@needs_java
def test_executed_java_holds_the_leading_decimal_values(result, tmp_path) -> None:
    cls = re.search(r"\bclass\s+(\w+)", result.java_source).group(1)
    (tmp_path / f"{cls}.java").write_text(result.java_source, encoding="utf-8")
    (tmp_path / "Reader.java").write_text(_READER, encoding="utf-8")
    comp = subprocess.run(
        ["javac", "Reader.java", f"{cls}.java"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert comp.returncode == 0, comp.stderr
    run = subprocess.run(
        ["java", "Reader", cls], cwd=tmp_path, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stderr
    state = dict(line.split("=", 1) for line in run.stdout.splitlines())
    assert float(state["wsHalf"]) == 0.5
    assert float(state["wsNegHalf"]) == -0.5
    assert float(state["wsPosHalf"]) == 0.5
    assert float(state["wsLead0"]) == 0.5
    assert float(state["wsNegLead0"]) == -0.5
    assert float(state["wsSmall"]) == 0.0125
    assert float(state["wsBal"]) == 450000.0
    assert state["wsText"] == "ABC"


# ===========================================================================
# 7. Corpus: none of the 45 sources uses a leading-decimal VALUE
# ===========================================================================


def test_no_corpus_source_uses_a_leading_decimal_value() -> None:
    """This is why the fix changes no generated MMIM output: no source has a
    ``VALUE`` literal that starts with ``.`` (with or without a sign)."""
    pattern = re.compile(r"\bVALUES?(\s+IS)?\s+[-+]?\s*\.\d", re.I)
    offenders = []
    for rec in load_training_corpus():
        for n, line in enumerate(rec.source.splitlines(), 1):
            if len(line) > 6 and line[6] not in "*/" and pattern.search(line[6:72]):
                offenders.append((rec.source_id, n))
    assert offenders == []
