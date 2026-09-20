"""
Signed numeric ``VALUE`` literals (Stage 21).

Purpose:
    The lexer emits ``+`` and ``-`` as their own ``UNKNOWN`` tokens everywhere
    -- deliberately, since they are also the arithmetic operators (see
    ``tests/parser/test_lexer_numeric_prefixed_names.py``, which pins
    ``VALUE -1`` and ``B - C`` that way). The ``VALUE`` clause took only the
    token straight after ``VALUE`` as the whole literal, so for
    ``VALUE +000450000.00`` it took ``+`` and left the digits behind; the
    terminating-period check then failed (``SYN005``) and the *entire data
    item* was abandoned -- no AST node, no symbol, no Java field.

    The clause now joins a sign to the ``NUMBER`` that sits directly against
    it. These tests pin that, that everything else is unchanged, and that the
    recovered value propagates all the way to an executed Java field.

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
from app.parser.lexer.lexer import CobolLexer
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.syntax.program_parser import ProgramParser

SOURCES = Path("data/sources/phase6-v2")

needs_java = pytest.mark.skipif(
    shutil.which("javac") is None or shutil.which("java") is None,
    reason="javac/java not available",
)

_HEAD = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SIGNED.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
"""
_TAIL = """\
       PROCEDURE DIVISION.
       MAIN-PARA.
           STOP RUN.
"""


def _program(*data_lines: str) -> str:
    return _HEAD + "".join(f"       {line}\n" for line in data_lines) + _TAIL


def _items(source: str) -> dict[str, str | None]:
    """``{data-name: VALUE lexeme}`` for every elementary item that parsed."""
    tokens = CobolLexer().tokenize(source, filename="s.cbl")
    program = ProgramParser().parse(tokens)
    out: dict[str, str | None] = {}

    def walk(items) -> None:
        for item in items:
            if hasattr(item, "picture"):
                out[item.name] = item.value
            walk(getattr(item, "children", ()) or ())

    walk(program.data_division.working_storage.items)
    return out


def _analyse(source: str, tmp_path: Path):
    path = tmp_path / "signed.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _syntax_codes(result) -> list[str]:
    return [str(getattr(d, "code", "")) for d in result.syntax_diagnostics]


# ===========================================================================
# 1. The parser keeps the item and its signed literal
# ===========================================================================


@pytest.mark.parametrize(
    ("clause", "expected"),
    [
        ("VALUE +000450000.00", "+000450000.00"),
        ("VALUE -000450000.00", "-000450000.00"),
        ("VALUE +5", "+5"),
        ("VALUE -5", "-5"),
        ("VALUE +0", "+0"),
        ("VALUE -1234567", "-1234567"),
        ("VALUE IS -5", "-5"),
        ("VALUE IS +5", "+5"),
    ],
)
def test_signed_value_keeps_the_item_and_the_whole_literal(clause, expected) -> None:
    items = _items(_program(f"01  A PIC S9(9)V99 {clause}."))
    assert items == {"A": expected}


def test_signed_value_after_and_before_usage_clauses() -> None:
    items = _items(
        _program(
            "01  A PIC S9(9)V99 COMP-3 VALUE +000450000.00.",
            "01  B PIC S9(9)V99 VALUE -12.50 COMP-3.",
        )
    )
    assert items == {"A": "+000450000.00", "B": "-12.50"}


def test_items_after_a_signed_value_are_unaffected() -> None:
    """The bug also swallowed the *recovery region*: the next item must still
    parse normally, with its own value, in declaration order."""
    items = _items(
        _program(
            "01  FIRST-ITEM PIC 9(3) VALUE 7.",
            "01  SIGNED-ITEM PIC S9(3) VALUE -5.",
            "01  LAST-ITEM PIC X(4) VALUE 'ABCD'.",
        )
    )
    assert list(items) == ["FIRST-ITEM", "SIGNED-ITEM", "LAST-ITEM"]
    assert items == {
        "FIRST-ITEM": "7",
        "SIGNED-ITEM": "-5",
        "LAST-ITEM": "'ABCD'",
    }


def test_signed_value_no_longer_produces_a_syntax_error(tmp_path) -> None:
    result = _analyse(
        _program(
            "01  A PIC S9(9)V99 COMP-3 VALUE +000450000.00.",
            "01  B PIC S9(3) VALUE -5.",
        ),
        tmp_path,
    )
    assert "SYN005" not in _syntax_codes(result)
    assert not [
        d
        for d in result.syntax_diagnostics
        if "to terminate data item" in str(getattr(d, "message", ""))
    ]


# ===========================================================================
# 2. Everything that is not a signed literal is unchanged
# ===========================================================================


@pytest.mark.parametrize(
    ("clause", "expected"),
    [
        ("VALUE 5", "5"),
        ("VALUE 000450000.00", "000450000.00"),
        ("VALUE 0", "0"),
        ("VALUE ZERO", "ZERO"),
        ("VALUE ZEROS", "ZEROS"),
        ("VALUE 'TEXT'", "'TEXT'"),
        ("VALUE SPACES", "SPACES"),
        ("VALUE IS 5", "5"),
    ],
)
def test_unsigned_and_non_numeric_values_are_unchanged(clause, expected) -> None:
    assert _items(_program(f"01  A PIC X(9) {clause}.")) == {"A": expected}


@pytest.mark.parametrize("clause", ["VALUE + 5", "VALUE - 5", "VALUE IS + 5"])
def test_a_detached_sign_is_not_joined_to_the_number(clause, tmp_path) -> None:
    """COBOL requires the sign directly against the digits, so ``+ 5`` is not
    a signed literal: it is *not* silently accepted as ``+5``. The item is
    abandoned exactly as before (with the same ``SYN005``), and the next item
    still parses."""
    source = _program(f"01  A PIC S9(3) {clause}.", "01  B PIC 9(3) VALUE 1.")
    assert _items(source) == {"B": "1"}
    assert "SYN005" in _syntax_codes(_analyse(source, tmp_path))


def test_the_lexer_still_emits_the_sign_as_its_own_token() -> None:
    """The fix is in the parser; the lexer contract (also pinned by
    test_lexer_numeric_prefixed_names.py) is untouched."""
    tokens = CobolLexer().tokenize(
        _program("01  A PIC S9(3) VALUE +5."), filename="s.cbl"
    )
    i = next(k for k, t in enumerate(tokens) if t.lexeme == "VALUE")
    assert [(t.type.name, t.lexeme) for t in tokens[i : i + 3]] == [
        ("KEYWORD", "VALUE"),
        ("UNKNOWN", "+"),
        ("NUMBER", "5"),
    ]


def test_arithmetic_operators_are_not_touched_by_the_value_fix() -> None:
    """``+``/``-`` outside a VALUE clause are operators; a signed VALUE in the
    data division must not change how the procedure division parses them."""
    procedure = (
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           ADD WS-B TO WS-A\n"
        "           SUBTRACT 1 FROM WS-A\n"
        "           STOP RUN.\n"
    )

    def statements(value_clause: str):
        source = (
            _HEAD
            + f"       01  WS-A PIC S9(5) {value_clause}.\n"
            + "       01  WS-B PIC S9(5) VALUE 20.\n"
            + procedure
        )
        program = ProgramParser().parse(CobolLexer().tokenize(source, filename="s.cbl"))
        return [
            (
                type(s).__name__,
                {k: v for k, v in vars(s).items() if "position" not in k},
            )
            for s in program.procedure_division.paragraphs[0].statements
        ]

    assert statements("VALUE -10") == statements("VALUE 10")


# ===========================================================================
# 3. Propagation: AST -> symbol -> Java field
# ===========================================================================

_SIGNED_PROGRAM = _program(
    "01  WS-BAL     PIC S9(9)V99 COMP-3 VALUE +000450000.00.",
    "01  WS-NEG-BAL PIC S9(9)V99 COMP-3 VALUE -000012.50.",
    "01  WS-INT-POS PIC S9(5) VALUE +7.",
    "01  WS-INT-NEG PIC S9(5) VALUE -5.",
    "01  WS-ZERO    PIC S9(5)V99 VALUE +000000.00.",
    "01  WS-NEG-ZERO PIC S9(5)V99 VALUE -000000.00.",
    "01  WS-PLAIN   PIC 9(3) VALUE 035.",
)


@pytest.fixture(scope="module")
def signed_result(tmp_path_factory):
    return _analyse(_SIGNED_PROGRAM, tmp_path_factory.mktemp("signed"))


def _field_lines(java: str) -> dict[str, str]:
    return {
        m.group(2): m.group(0).strip()
        for m in re.finditer(
            r"^\s+private (String|int|double) (\w+)( = [^;\n]*)?;", java, re.M
        )
    }


def test_symbol_table_carries_the_signed_value(signed_result) -> None:
    ctx = SemanticAnalyzer().analyse(signed_result.ast)
    by_name = {s.name: s for s in ctx.symbol_table.all_symbols()}
    assert by_name["WS-BAL"].value == "+000450000.00"
    assert by_name["WS-NEG-BAL"].value == "-000012.50"
    assert by_name["WS-INT-POS"].value == "+7"
    assert by_name["WS-INT-NEG"].value == "-5"
    assert by_name["WS-PLAIN"].value == "035"


def test_java_fields_are_declared_with_value_correct_initializers(
    signed_result,
) -> None:
    fields = _field_lines(signed_result.java_source)
    assert fields["wsBal"] == "private double wsBal = 450000.00;"
    assert fields["wsNegBal"] == "private double wsNegBal = -12.50;"
    assert fields["wsIntPos"] == "private int wsIntPos = 7;"
    assert fields["wsIntNeg"] == "private int wsIntNeg = -5;"
    assert fields["wsZero"] == "private double wsZero = 0.00;"
    assert fields["wsNegZero"] == "private double wsNegZero = 0.00;"  # no -0.0
    assert fields["wsPlain"] == "private int wsPlain = 35;"  # Stage 20 unchanged
    assert not re.search(r"= \+", signed_result.java_source)  # never a leading '+'


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


def _read_fields(java: str, tmp_path: Path) -> dict[str, str]:
    cls = re.search(r"\bclass\s+(\w+)", java).group(1)
    d = tmp_path / "jrun"
    d.mkdir(exist_ok=True)
    (d / f"{cls}.java").write_text(java, encoding="utf-8")
    (d / "Reader.java").write_text(_READER, encoding="utf-8")
    comp = subprocess.run(
        ["javac", "Reader.java", f"{cls}.java"], cwd=d, capture_output=True, text=True
    )
    assert comp.returncode == 0, comp.stderr
    run = subprocess.run(["java", "Reader", cls], cwd=d, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    return dict(line.split("=", 1) for line in run.stdout.splitlines())


@needs_java
def test_executed_java_holds_the_signed_cobol_values(signed_result, tmp_path) -> None:
    state = _read_fields(signed_result.java_source, tmp_path)
    assert float(state["wsBal"]) == 450000.0
    assert float(state["wsNegBal"]) == -12.5
    assert state["wsIntPos"] == "7"
    assert state["wsIntNeg"] == "-5"
    assert float(state["wsZero"]) == 0.0
    assert state["wsNegZero"] == "0.0"  # not "-0.0"
    assert state["wsPlain"] == "35"


# ===========================================================================
# 4. The real corpus source the defect was found on
# ===========================================================================

_PACKED = {
    "BEGINNING-BALANCE": ("+000450000.00", "beginningBalance", "450000.00"),
    "PERIOD-DEBITS": ("+000085200.50", "periodDebits", "85200.50"),
    "PERIOD-CREDITS": ("+000062100.25", "periodCredits", "62100.25"),
    "ENDING-BALANCE": ("+000000000.00", "endingBalance", "0.00"),
    "VARIANCE-AMOUNT": ("+000000000.00", "varianceAmount", "0.00"),
}


@pytest.fixture(scope="module")
def packed_decimal():
    return AnalysisService().analyze_file(SOURCES / "packed_decimal.cbl")


def test_packed_decimal_recovers_all_five_dropped_items(packed_decimal) -> None:
    assert "SYN005" not in _syntax_codes(packed_decimal)  # was 5 of them
    names: dict[str, str | None] = {}

    def walk(items) -> None:
        for item in items:
            if hasattr(item, "picture"):
                names[item.name] = item.value
            walk(getattr(item, "children", ()) or ())

    walk(packed_decimal.ast.data_division.working_storage.items)
    assert len(names) == 11  # 8 -> 13 data items counting the 2 groups
    for cobol_name, (literal, _, _) in _PACKED.items():
        assert names[cobol_name] == literal


def test_packed_decimal_java_declares_them_with_their_initial_values(
    packed_decimal,
) -> None:
    fields = _field_lines(packed_decimal.java_source)
    for _, java_name, initializer in _PACKED.values():
        assert fields[java_name] == f"private double {java_name} = {initializer};"
    assert len(fields) == 13
    # the three unsigned COMP items and the flags are exactly as in Stage 20
    assert fields["glAccountNumber"] == "private int glAccountNumber = 10042000;"
    assert fields["accountingPeriod"] == "private int accountingPeriod = 9;"


@needs_java
def test_packed_decimal_generated_java_compiles_and_holds_the_values(
    packed_decimal, tmp_path
) -> None:
    state = _read_fields(packed_decimal.java_source, tmp_path)
    assert float(state["beginningBalance"]) == 450000.0
    assert float(state["periodDebits"]) == 85200.5
    assert float(state["periodCredits"]) == 62100.25
    assert float(state["endingBalance"]) == 0.0
    assert float(state["varianceAmount"]) == 0.0
    assert state["glAccountNumber"] == "10042000"


def test_only_the_packed_decimal_source_uses_a_signed_value() -> None:
    """Every signed ``VALUE`` in the 45-source corpus is one of these five."""
    signed = []
    for path in sorted(SOURCES.glob("*.cbl")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if (
                len(line) > 6
                and line[6] not in "*/"
                and re.search(r"\bVALUES?(\s+IS)?\s+[-+]\s*\d", line[6:72], re.I)
            ):
                signed.append((path.name, n))
    assert signed == [("packed_decimal.cbl", n) for n in range(11, 16)]
