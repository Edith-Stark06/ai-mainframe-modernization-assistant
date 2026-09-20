"""
COBOL ``VALUE`` clause -> Java field initializer (Stage 20).

Purpose:
    The parser captured every ``VALUE`` literal, but it was dropped when the
    symbol was created (``VariableSymbol`` had no field for it) and
    ``build_fields_from_symbols`` hardcoded ``initial_value=None``. Every
    generated field therefore started at the Java default (``0`` / ``null``)
    instead of its COBOL initial contents, e.g. ``STEP-INDEX ... VALUE 01`` was
    ``private int stepIndex;``.

    The literal cannot be pasted into Java as written: a leading ``0`` is
    *octal* there (``VALUE 035`` would silently be 29, ``VALUE 028``/``09``
    would not compile), so numbers are re-emitted from their value. These
    tests pin the translation table, the wiring from the parsed program to the
    emitted field, the octal hazard against the *real* corpus values, and --
    the strong check -- the generated Java is compiled and *executed* to show
    the fields really hold the COBOL initial state.

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
from app.backend.java.generator import build_fields_from_symbols
from app.backend.java.value_initializer import translate_value_literal
from app.parser.lexer.position import Position
from app.parser.semantic.symbols import VariableSymbol
from app.parser.semantic.types import AlphanumericType, GroupType, NumericType

SOURCES = Path("data/sources/phase6-v2")

needs_java = pytest.mark.skipif(
    shutil.which("javac") is None or shutil.which("java") is None,
    reason="javac/java not available",
)

_POS = Position(line=1, column=1, offset=0, filename="t.cbl")

# ===========================================================================
# 1. The translation table
# ===========================================================================


@pytest.mark.parametrize(
    ("literal", "java_type", "expected"),
    [
        # --- String: quoted literals are re-quoted, kept unpadded like MOVE ---
        ("'INITIAL'", "String", '"INITIAL"'),
        ("'N'", "String", '"N"'),
        ('"DOUBLE"', "String", '"DOUBLE"'),
        ("'HAS \"QUOTES\"'", "String", '"HAS \\"QUOTES\\""'),
        ("'BACK\\SLASH'", "String", '"BACK\\\\SLASH"'),
        ("'A;B'", "String", '"A;B"'),
        ("SPACE", "String", '""'),
        ("SPACES", "String", '""'),
        ("spaces", "String", '""'),
        # --- int: value, never spelling (Java reads a leading 0 as octal) ---
        ("1", "int", "1"),
        ("01", "int", "1"),
        ("035", "int", "35"),  # octal would be 29
        ("028", "int", "28"),  # not even valid octal
        ("09", "int", "9"),
        ("000500", "int", "500"),  # octal would be 320
        ("00000", "int", "0"),
        ("0", "int", "0"),
        ("+5", "int", "5"),
        ("-7", "int", "-7"),
        ("-000", "int", "0"),
        ("2147483647", "int", "2147483647"),
        ("ZERO", "int", "0"),
        ("ZEROS", "int", "0"),
        ("ZEROES", "int", "0"),
        # --- double ---
        ("00065000.00", "double", "65000.00"),
        ("000000.00", "double", "0.00"),
        ("1.00", "double", "1.00"),
        ("0.5", "double", "0.5"),
        (".50", "double", "0.50"),
        ("-1.25", "double", "-1.25"),
        ("-0.00", "double", "0.00"),  # no negative zero
        ("5", "double", "5.0"),
        ("0000", "double", "0.0"),
        ("ZERO", "double", "0.0"),
    ],
)
def test_translation_table(literal, java_type, expected) -> None:
    assert translate_value_literal(literal, java_type) == expected


@pytest.mark.parametrize(
    ("literal", "java_type"),
    [
        (None, "int"),
        (None, "String"),
        ("", "String"),
        ("   ", "int"),
        # literal kind does not match the field's Java type -> never guessed
        ("'X'", "int"),
        ("'X'", "double"),
        ("SPACES", "int"),
        ("SPACES", "double"),
        ("12", "String"),
        ("1.5", "String"),
        ("1.5", "int"),  # a decimal into an integer picture
        # figurative constants with no proven Java equivalent
        ("ZERO", "String"),
        ("HIGH-VALUES", "String"),
        ("LOW-VALUE", "String"),
        ("QUOTES", "String"),
        ("HIGH-VALUES", "int"),
        # int overflow would not compile
        ("2147483648", "int"),
        ("-2147483649", "int"),
        ("9999999999", "int"),
        # a Java type the backend never produces for a VALUE
        ("1", "boolean"),
        ("1", "long"),
        # unterminated / malformed
        ("'OPEN", "String"),
        ("1.2.3", "double"),
        ("ONE", "int"),
    ],
)
def test_no_initializer_when_no_provably_correct_one(literal, java_type) -> None:
    assert translate_value_literal(literal, java_type) is None


def test_int_at_the_boundary_and_negative_minimum() -> None:
    assert translate_value_literal("-2147483648", "int") == "-2147483648"


@pytest.mark.parametrize("literal", ["035", "028", "09", "000500", "010", "007"])
def test_no_int_initializer_ever_has_a_leading_zero(literal) -> None:
    out = translate_value_literal(literal, "int")
    assert out is not None
    assert not re.match(r"^-?0\d", out), out
    assert int(out) == int(literal)


# ===========================================================================
# 2. build_fields_from_symbols wiring
# ===========================================================================


def _var(name, cobol_type, value=None) -> VariableSymbol:
    return VariableSymbol(
        name=name, declared_at=_POS, level=5, cobol_type=cobol_type, value=value
    )


def test_symbol_value_becomes_the_field_initializer() -> None:
    fields = build_fields_from_symbols(
        [
            _var("WS-COUNT", NumericType(digits=2), "01"),
            _var("WS-RATE", NumericType(digits=5, decimal_places=2), "000.50"),
            _var("WS-NAME", AlphanumericType(length=10), "'ABC'"),
            _var("WS-BLANK", AlphanumericType(length=4), "SPACES"),
        ]
    )
    assert [f.initial_value for f in fields] == ["1", "0.50", '"ABC"', '""']
    assert fields[0].render() == "    private int wsCount = 1;"
    assert fields[2].render() == '    private String wsName = "ABC";'


def test_symbol_without_value_keeps_no_initializer() -> None:
    (field,) = build_fields_from_symbols([_var("WS-X", NumericType(digits=3))])
    assert field.initial_value is None
    assert field.render() == "    private int wsX;"


def test_group_item_has_no_initializer() -> None:
    (field,) = build_fields_from_symbols([_var("WS-GROUP", GroupType())])
    assert field.initial_value is None


def test_untranslatable_value_leaves_the_field_uninitialized_not_missing() -> None:
    """A field whose VALUE has no provably correct Java form must still be
    declared (as before) -- only its initializer is withheld."""
    (field,) = build_fields_from_symbols(
        [_var("WS-BIG", NumericType(digits=9), "9999999999")]
    )
    assert field.java_type == "int"
    assert field.initial_value is None


def test_a_valued_symbol_with_no_type_is_still_skipped() -> None:
    diags: list = []
    assert build_fields_from_symbols([_var("WS-U", None, "1")], diags) == []
    assert any(d.code == "BE003" for d in diags)


# ===========================================================================
# 3. Parsed program -> symbol -> field
# ===========================================================================

_PROGRAM = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. VALTEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-GROUP.
           05  WS-AGE          PIC 9(3)    VALUE 035.
           05  WS-MONTHS       PIC 9(2)    VALUE 028.
           05  WS-PERIOD       PIC 9(2)    VALUE 09.
           05  WS-BIG-ZERO     PIC 9(5)    VALUE 00500.
           05  WS-AMOUNT       PIC 9(5)V99 VALUE 00065.25.
           05  WS-NAME         PIC X(10)   VALUE 'INITIAL'.
           05  WS-BLANK        PIC X(4)    VALUE SPACES.
           05  WS-NO-VALUE     PIC 9(3).
           05  WS-FLAG         PIC X(1)    VALUE 'N'.
               88  FLAG-IS-YES VALUE 'Y'.
       PROCEDURE DIVISION.
       0000-MAIN.
           DISPLAY WS-NAME
           STOP RUN.
"""


@pytest.fixture(scope="module")
def analysed(tmp_path_factory):
    path = tmp_path_factory.mktemp("val") / "valtest.cbl"
    path.write_text(_PROGRAM, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _field_lines(java: str) -> dict[str, str]:
    return {
        m.group(2): m.group(0).strip()
        for m in re.finditer(
            r"^\s+private (String|int|double) (\w+)( = [^;\n]*)?;", java, re.M
        )
    }


def test_symbol_table_carries_the_parsed_value(analysed) -> None:
    result = analysed
    assert result.success
    # The AST always had it; the symbol now does too.
    ast_values = {}

    def walk(items):
        for item in items:
            if getattr(item, "value", None) is not None:
                ast_values[item.name] = item.value
            walk(getattr(item, "children", ()) or ())

    walk(result.ast.data_division.working_storage.items)
    assert ast_values["WS-AGE"] == "035"

    from app.parser.semantic.analyzer import SemanticAnalyzer

    ctx = SemanticAnalyzer().analyse(result.ast)
    by_name = {s.name: s for s in ctx.symbol_table.all_symbols()}
    assert by_name["WS-AGE"].value == "035"
    assert by_name["WS-NAME"].value == "'INITIAL'"
    assert by_name["WS-BLANK"].value == "SPACES"
    assert by_name["WS-NO-VALUE"].value is None
    assert by_name["WS-GROUP"].value is None  # group item
    assert by_name["FLAG-IS-YES"].value is None  # 88-level is not storage


def test_generated_java_initializes_fields_from_value_clauses(analysed) -> None:
    fields = _field_lines(analysed.java_source)
    assert fields["wsAge"] == "private int wsAge = 35;"
    assert fields["wsMonths"] == "private int wsMonths = 28;"
    assert fields["wsPeriod"] == "private int wsPeriod = 9;"
    assert fields["wsBigZero"] == "private int wsBigZero = 500;"
    assert fields["wsAmount"] == "private double wsAmount = 65.25;"
    assert fields["wsName"] == 'private String wsName = "INITIAL";'
    assert fields["wsBlank"] == 'private String wsBlank = "";'
    assert fields["wsFlag"] == 'private String wsFlag = "N";'


def test_items_without_a_value_clause_stay_uninitialized(analysed) -> None:
    fields = _field_lines(analysed.java_source)
    assert fields["wsNoValue"] == "private int wsNoValue;"
    assert fields["wsGroup"] == "private String wsGroup;"  # group: no VALUE
    # an 88-level condition-name is not storage: no field at all (Stage 23;
    # before, it was an uninitialized ``private String flagIsYes;``)
    assert "flagIsYes" not in fields


def test_no_generated_initializer_is_a_leading_zero_literal(analysed) -> None:
    for line in _field_lines(analysed.java_source).values():
        assert not re.search(r"= -?0\d", line), line


@needs_java
def test_generated_java_with_zero_padded_values_compiles_and_holds_them(
    analysed, tmp_path
) -> None:
    """``VALUE 028`` and ``VALUE 09`` are *invalid* Java octal literals: pasting
    them as written would not compile. ``VALUE 035`` would compile and be 29."""
    state = _run_and_read_fields(analysed.java_source, tmp_path)
    assert state["wsAge"] == "35"
    assert state["wsMonths"] == "28"
    assert state["wsPeriod"] == "9"
    assert state["wsBigZero"] == "500"
    assert state["wsAmount"] == "65.25"
    assert state["wsName"] == "INITIAL"
    assert state["wsBlank"] == ""
    assert state["wsFlag"] == "N"
    assert state["wsNoValue"] == "0"  # Java default: unchanged behavior


# ===========================================================================
# 4. Executed: the real corpus program the gap was found on
# ===========================================================================

_READ_HARNESS = """\
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Comparator;

public class Reader {
    public static void main(String[] args) throws Exception {
        Class<?> c = Class.forName(args[0]);
        Object o = c.getDeclaredConstructor().newInstance();
        if (args.length > 1 && args[1].equals("run")) {
            c.getMethod("run").invoke(o);
        }
        Field[] fs = c.getDeclaredFields();
        Arrays.sort(fs, Comparator.comparing(Field::getName));
        for (Field f : fs) { f.setAccessible(true); System.out.println(f.getName() + "=" + f.get(o)); }
    }
}
"""


def _run_and_read_fields(
    java: str, tmp_path: Path, run: bool = False
) -> dict[str, str]:
    """Compile the generated class, instantiate it *without seeding anything*
    (so field initializers are what is observed), optionally call ``run()``,
    and return every field's value."""
    cls = re.search(r"\bclass\s+(\w+)", java).group(1)
    d = tmp_path / "jrun"
    d.mkdir(exist_ok=True)
    (d / f"{cls}.java").write_text(java, encoding="utf-8")
    (d / "Reader.java").write_text(_READ_HARNESS, encoding="utf-8")
    comp = subprocess.run(
        ["javac", "Reader.java", f"{cls}.java"], cwd=d, capture_output=True, text=True
    )
    assert comp.returncode == 0, comp.stderr
    cmd = ["java", "Reader", cls] + (["run"] if run else [])
    out = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return dict(line.split("=", 1) for line in out.stdout.splitlines())


@pytest.fixture(scope="module")
def goto_spaghetti():
    return AnalysisService().analyze_file(SOURCES / "goto_spaghetti.cbl")


def test_goto_spaghetti_fields_carry_their_cobol_values(goto_spaghetti) -> None:
    fields = _field_lines(goto_spaghetti.java_source)
    assert fields["stepIndex"] == "private int stepIndex = 1;"
    assert fields["accumulator"] == "private int accumulator = 0;"
    assert fields["terminalState"] == 'private String terminalState = "INITIAL";'
    assert fields["retryCounter"] == "private int retryCounter = 0;"


@needs_java
def test_goto_spaghetti_unseeded_run_matches_the_cobol_program(
    goto_spaghetti, tmp_path
) -> None:
    """Stage 19 found that this program, run as generated, took the ELSE path
    and ended ``accumulator=50`` because ``STEP-INDEX`` was Java ``0`` rather
    than COBOL's ``VALUE 01``. With the initializers it follows the loop path
    the COBOL program takes (docs/MMIM_GO_TO_FIX.md §10: 2000 -> 4000 -> 2000 ->
    4000 -> 2000 -> 5000) and ends in the same state, with *nothing seeded*."""
    state = _run_and_read_fields(goto_spaghetti.java_source, tmp_path, run=True)
    assert state["accumulator"] == "30"
    assert state["stepIndex"] == "4"
    assert state["retryCounter"] == "2"
    assert state["terminalState"] == "COMPLETED"


# ===========================================================================
# 5. Real corpus: every VALUE the parser captured
# ===========================================================================


def _all_sources() -> list[Path]:
    return sorted(SOURCES.glob("*.cbl"))


def test_every_corpus_initializer_is_octal_safe_and_value_exact() -> None:
    """Across the real phase6-v2 corpus: every numeric initializer is a plain
    decimal (no leading zero) and equals the COBOL literal numerically, and
    every string initializer equals the COBOL literal's text."""
    from decimal import Decimal

    checked = 0
    for path in _all_sources():
        result = AnalysisService().analyze_file(path)
        if result.ast is None or result.ast.data_division is None:
            continue
        ws = result.ast.data_division.working_storage
        if ws is None:
            continue
        fields = _field_lines(result.java_source)

        def walk(items, fields=fields):
            nonlocal checked
            for item in items:
                literal = getattr(item, "value", None)
                pic = getattr(item, "picture", None)
                if literal is not None and pic is not None:
                    from app.backend.java.naming import to_java_field_name

                    line = fields.get(to_java_field_name(item.name))
                    if line is not None and " = " in line:
                        init = line.split(" = ", 1)[1].rstrip(";")
                        if init.startswith('"'):
                            want = (
                                '""'
                                if literal.upper().startswith("SPACE")
                                else ('"' + literal[1:-1] + '"')
                            )
                            assert init == want, (path.name, item.name, literal, init)
                        else:
                            assert not re.match(r"^-?0\d", init), (path.name, init)
                            assert Decimal(init) == Decimal(literal), (
                                path.name,
                                item.name,
                                literal,
                                init,
                            )
                        checked += 1
                walk(getattr(item, "children", ()) or ())

        walk(ws.items)
    assert checked >= 200, checked  # 270 in the current corpus
