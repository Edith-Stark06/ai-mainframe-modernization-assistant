"""
Java representation of level-88 condition-names (Stage 23).

Purpose:
    A level-88 entry is a *named condition on its parent data item*, not
    storage. The rest of the pipeline already says so: the AST keeps it as
    ``ConditionNameNode`` metadata (``values``), the behavioral extractor maps
    each condition-name to its parent and reads the values as opaque strings,
    the procedure parser resolves ``IF NAME`` through ``known_condition_names``,
    and the backend deliberately refuses to translate the ``IS-TRUE`` /
    ``IS-FALSE`` IR sentinel (``BE007``). But ``build_fields_from_symbols``
    still declared every 88 symbol as an uninitialized ``private String`` --
    state that does not exist, which nothing ever reads or writes.

    These tests pin the decision: no Java field for a level-88 symbol, the
    symbol itself still registered, the condition reference still reported as
    untranslatable (never guessed), and every real storage item unaffected.

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
from app.backend.java.generator import BackendDiagnostic, build_fields_from_symbols
from app.parser.lexer.position import Position
from app.parser.semantic.symbols import VariableSymbol
from app.parser.semantic.types import AlphanumericType, GroupType, NumericType

SOURCES = Path("data/sources/phase6-v2")

needs_java = pytest.mark.skipif(
    shutil.which("javac") is None or shutil.which("java") is None,
    reason="javac/java not available",
)

_POS = Position(line=1, column=1, offset=0, filename="t.cbl")


def _sym(name: str, level: int, cobol_type, value=None) -> VariableSymbol:
    return VariableSymbol(
        name=name, declared_at=_POS, level=level, cobol_type=cobol_type, value=value
    )


# ===========================================================================
# 1. build_fields_from_symbols
# ===========================================================================


def test_a_level_88_symbol_gets_no_java_field() -> None:
    diags: list[BackendDiagnostic] = []
    assert build_fields_from_symbols([_sym("IS-DEP", 88, GroupType())], diags) == []
    assert diags == []  # skipped by design, not a BE002/BE003 "could not map"


def test_the_skip_does_not_depend_on_the_symbols_type() -> None:
    """88 symbols normally carry ``GroupType``; the rule is the *level*."""
    for cobol_type in (
        GroupType(),
        AlphanumericType(length=1),
        NumericType(digits=1),
        None,
    ):
        diags: list[BackendDiagnostic] = []
        assert build_fields_from_symbols([_sym("C", 88, cobol_type)], diags) == []
        assert diags == []


def test_only_88_is_skipped_and_order_is_preserved() -> None:
    fields = build_fields_from_symbols(
        [
            _sym("WS-GROUP", 1, GroupType()),
            _sym("WS-CODE", 5, AlphanumericType(length=1), "'D'"),
            _sym("IS-DEP", 88, GroupType()),
            _sym("IS-VALID", 88, GroupType()),
            _sym("WS-N", 5, NumericType(digits=3), "07"),
            _sym("WS-77", 77, NumericType(digits=2)),
            _sym("IS-SEVEN", 88, GroupType()),
        ]
    )
    assert [(f.cobol_name, f.java_name, f.initial_value) for f in fields] == [
        ("WS-GROUP", "wsGroup", None),
        ("WS-CODE", "wsCode", '"D"'),
        ("WS-N", "wsN", "7"),
        ("WS-77", "ws77", None),
    ]


def test_every_other_level_still_becomes_a_field() -> None:
    for level in (1, 2, 5, 10, 49, 66, 77):
        (field,) = build_fields_from_symbols([_sym("X", level, GroupType())])
        assert field.java_type == "String", level


# ===========================================================================
# 2. Whole pipeline
# ===========================================================================

_DATA = [
    "01  WS-CODE PIC X(1) VALUE 'D'.",
    "    88  IS-DEP VALUE 'D'.",
    "    88  IS-VALID VALUES 'D' 'W'.",
    "01  WS-N PIC S9(3) VALUE 1.",
    "    88  NEG-ONE VALUE -1.",
    "    88  HALF VALUE .5.",
    "    88  SIGNS VALUES -1 +1 -.5.",
    "    88  ANY-ZERO VALUE ZERO.",
    "    88  BLANK VALUE IS SPACES.",
    "01  WS-OUT PIC X(5).",
]
_CONDITION_JAVA_NAMES = (
    "isDep",
    "isValid",
    "negOne",
    "half",
    "signs",
    "anyZero",
    "blank",
)


def _program(proc: list[str]) -> str:
    return (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. LEVEL88J.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        + "".join(f"       {line}\n" for line in _DATA)
        + "       PROCEDURE DIVISION.\n       MAIN-PARA.\n"
        + "".join(f"           {line}\n" for line in proc)
        + "           STOP RUN.\n"
    )


def _analyse(source: str, tmp_path: Path):
    path = tmp_path / "level88j.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _fields(java: str) -> dict[str, str]:
    return {
        m.group(2): m.group(0).strip()
        for m in re.finditer(
            r"^\s+private (String|int|double) (\w+)( = [^;\n]*)?;", java, re.M
        )
    }


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    return _analyse(_program(["DISPLAY WS-OUT"]), tmp_path_factory.mktemp("j"))


def test_all_88_forms_parse_without_a_syntax_error(result) -> None:
    assert result.success
    assert [d for d in result.syntax_diagnostics if str(d.code) != "SYN200"] == []


def test_no_java_field_for_any_condition_name(result) -> None:
    fields = _fields(result.java_source)
    for name in _CONDITION_JAVA_NAMES:
        assert name not in fields, name
    # exactly the real storage items, with their Stage 20 initializers
    assert fields == {
        "wsCode": 'private String wsCode = "D";',
        "wsN": "private int wsN = 1;",
        "wsOut": "private String wsOut;",
    }


def test_the_condition_symbols_are_still_registered(result) -> None:
    from app.parser.semantic.analyzer import SemanticAnalyzer

    table = SemanticAnalyzer().analyse(result.ast).symbol_table
    for cobol in (
        "IS-DEP",
        "IS-VALID",
        "NEG-ONE",
        "HALF",
        "SIGNS",
        "ANY-ZERO",
        "BLANK",
    ):
        sym = table.lookup(cobol)
        assert sym is not None and sym.level == 88, cobol  # type: ignore[union-attr]


def test_the_backend_reports_no_field_related_diagnostic(result) -> None:
    assert not [d for d in result.backend_diagnostics if d.code in ("BE002", "BE003")]


@pytest.mark.parametrize(
    "condition",
    ["HALF", "SIGNS", "BLANK", "IS-DEP AND HALF", "NOT BLANK"],
)
def test_a_condition_reference_is_still_untranslatable_never_guessed(
    condition, tmp_path
) -> None:
    """``IF <condition-name>`` lowers to the ``IS-TRUE``/``IS-FALSE`` sentinel.
    Since Stage 24 the backend translates it -- but only when it can do so
    provably correctly. These cannot: ``HALF`` (``.5``) and ``SIGNS`` (``-.5``)
    are not integers for the integer parent ``WS-N``, ``BLANK`` (``SPACES``) is
    not numeric, and a compound with an untranslatable term is skipped whole.
    Each is reported (``BE007``) and omitted, never turned into a comparison on
    a field that no longer (and never really) held the condition's value."""
    res = _analyse(_program([f"IF {condition} MOVE 'X' TO WS-OUT END-IF"]), tmp_path)
    assert any(d.code == "BE007" for d in res.backend_diagnostics)
    assert "// TODO: IF condition cannot be translated (BE007)" in res.java_source
    assert 'wsOut = "X"' not in res.java_source  # body never runs unguarded
    for name in _CONDITION_JAVA_NAMES:
        assert f"{name} " not in res.java_source.replace("private", "")  # no reference


def test_ordinary_comparisons_on_the_parent_are_unaffected(tmp_path) -> None:
    res = _analyse(_program(["IF WS-CODE = 'D' MOVE 'EQ' TO WS-OUT END-IF"]), tmp_path)
    # (Stage 24: a text comparison is COBOL's alphanumeric equality, not Java ==)
    assert 'if (_cobolEquals(wsCode, "D")) {' in res.java_source
    assert not [d for d in res.backend_diagnostics if d.code == "BE007"]


# ===========================================================================
# 3. Executed Java: only real storage exists on the generated class
# ===========================================================================

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
    cls = re.search(r"\bclass\s+(\w+)", java).group(1)  # type: ignore[union-attr]
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
def test_generated_class_has_only_storage_fields_and_compiles(result, tmp_path) -> None:
    state = _read_fields(result.java_source, tmp_path)
    assert state == {"wsCode": "D", "wsN": "1", "wsOut": "null"}


@needs_java
def test_generated_class_with_an_omitted_condition_if_still_compiles(tmp_path) -> None:
    res = _analyse(
        _program(
            [
                "DISPLAY 'START'",
                "IF NEG-ONE DISPLAY 'GUARDED' END-IF",
                "IF WS-CODE = 'D' DISPLAY 'EQ' END-IF",
            ]
        ),
        tmp_path,
    )
    assert _read_fields(res.java_source, tmp_path) == {
        "wsCode": "D",
        "wsN": "1",
        "wsOut": "null",
    }


# ===========================================================================
# 4. The real corpus source
# ===========================================================================

_REAL_CONDITIONS = (
    "txDeposit",
    "txWithdrawal",
    "txTransfer",
    "txFee",
    "txValidKind",
    "txPending",
    "txApproved",
    "txRejected",
    "txSettled",
    "onlineChannel",
    "physicalBranch",
)
_REAL_STORAGE = (
    "transactionStatusRecord",
    "txTypeCode",
    "txStatusFlag",
    "channelOrigin",
    "txAmount",
    "processingOutcome",
    "outcomeAction",
    "feesLevied",
)


@pytest.fixture(scope="module")
def condition_names_88():
    return AnalysisService().analyze_file(SOURCES / "condition_names_88.cbl")


def test_real_source_declares_only_its_storage_items(condition_names_88) -> None:
    fields = _fields(condition_names_88.java_source)
    assert tuple(fields) == _REAL_STORAGE  # declaration order, no condition-names
    for name in _REAL_CONDITIONS:
        assert name not in fields


def test_real_source_keeps_its_initializers_and_diagnostics(condition_names_88) -> None:
    fields = _fields(condition_names_88.java_source)
    assert fields["txTypeCode"] == 'private String txTypeCode = "D";'
    assert fields["txStatusFlag"] == 'private String txStatusFlag = "P";'
    assert fields["channelOrigin"] == 'private String channelOrigin = "ATM";'
    assert fields["txAmount"] == "private double txAmount = 2500.00;"
    assert fields["outcomeAction"] == 'private String outcomeAction = "";'
    assert fields["feesLevied"] == "private double feesLevied = 0.00;"
    # the real compound-88 IF stays skipped (pinned elsewhere) -- unchanged
    # It used to keep one SYN003 for the column-7 '*' comment line; task
    # #stage30 (docs/FIXED_FORMAT_NORMALIZATION.md) blanks comment lines before
    # lexing, so the source now parses with no syntax diagnostic at all.
    assert condition_names_88.syntax_diagnostics == []


@needs_java
def test_real_source_compiles_and_runs_with_only_storage(
    condition_names_88, tmp_path
) -> None:
    state = _read_fields(condition_names_88.java_source, tmp_path)
    assert set(state) == set(_REAL_STORAGE)
    assert state["txTypeCode"] == "D"
    assert state["txAmount"] == "2500.0"
