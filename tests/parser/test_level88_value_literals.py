"""
Level-88 ``VALUE`` / ``VALUES`` literals (Stage 23).

Purpose:
    A level-88 condition-name accepted only a string, a plain number or a
    figurative-constant word. The lexer splits a signed number into
    ``UNKNOWN('-')`` + ``NUMBER`` and a leading-decimal number into
    ``PERIOD`` + ``NUMBER``, so ``88 X VALUE -1.`` / ``VALUE .5.`` /
    ``VALUES -1 -2.`` were dropped with a ``SYN005`` (and the leftover of
    ``.5`` produced a *second*, spurious level-number ``SYN005``). Worse,
    ``VALUES IS 1 2`` silently captured the noise word ``IS`` as a *value*.

    The 88 parser now joins a sign / leading point to the digits it sits
    directly against (as the elementary-item ``VALUE`` clause does, but with
    its own code -- that clause is untouched), and skips the optional
    ``IS`` (``VALUE IS``) / ``IS``/``ARE`` (``VALUES IS|ARE``). Forms the
    parser has always rejected on purpose (``THRU`` ranges, comma
    separators, a detached sign) are still rejected.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.service import AnalysisService
from app.behavioral.extraction.conditions import (
    _generate_condition_name_boundary_values,
)
from app.behavioral.extraction.extractor import (
    _collect_condition_name_parents,
    _collect_condition_name_values,
)
from app.dataset.analysis_bundle import build_analysis_bundle
from app.dataset.corpus import load_training_corpus
from app.parser.ast.data_items import ConditionNameNode
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.program_parser import ProgramParser

_HEAD = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LEVEL88.
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


def _conditions(source: str) -> dict[str, tuple[str | None, tuple[str, ...]]]:
    """``{condition-name: (value, values)}`` for every 88 entry that parsed."""
    program = ProgramParser().parse(_tokens(source))
    out: dict[str, tuple[str | None, tuple[str, ...]]] = {}
    for item in program.data_division.working_storage.items:
        if isinstance(item, ConditionNameNode):
            out[item.name] = (item.value, item.values)
    return out


def _one(clause: str) -> tuple[str | None, tuple[str, ...]] | None:
    """Parse ``88 C <clause>.`` under a parent item; ``None`` if it was dropped."""
    found = _conditions(_program("01  P PIC S9V99 VALUE 1.", f"    88  C {clause}."))
    return found.get("C")


def _analyse(source: str, tmp_path: Path):
    path = tmp_path / "level88.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _codes(result) -> list[str]:
    return [str(getattr(d, "code", "")) for d in result.syntax_diagnostics]


def _messages(result) -> list[str]:
    return [str(getattr(d, "message", "")) for d in result.syntax_diagnostics]


# ===========================================================================
# 1. The lexer contract is unchanged (the fix is parser-only)
# ===========================================================================


@pytest.mark.parametrize(
    ("clause", "expected"),
    [
        ("VALUE -1", [("UNKNOWN", "-"), ("NUMBER", "1"), ("PERIOD", ".")]),
        (
            "VALUE -.5",
            [("UNKNOWN", "-"), ("PERIOD", "."), ("NUMBER", "5"), ("PERIOD", ".")],
        ),
        ("VALUE .5", [("PERIOD", "."), ("NUMBER", "5"), ("PERIOD", ".")]),
        ("VALUE 0.5", [("NUMBER", "0.5"), ("PERIOD", ".")]),
    ],
)
def test_lexer_token_streams_are_unchanged(clause, expected) -> None:
    toks = _tokens(_program("01  P PIC S9V99 VALUE 1.", f"    88  C {clause}."))
    i = next(
        k
        for k, t in enumerate(toks)
        if t.lexeme == "VALUE" and toks[k - 1].lexeme == "C"
    )
    end = next(k for k in range(i, len(toks)) if toks[k].lexeme == "PROCEDURE")
    assert [(t.type.name, t.lexeme) for t in toks[i + 1 : end]] == expected


# ===========================================================================
# 2. Singular VALUE: every supported literal form
# ===========================================================================


@pytest.mark.parametrize(
    ("clause", "literal"),
    [
        # ordinary
        ("VALUE 'D'", "'D'"),
        ('VALUE "D"', '"D"'),
        ("VALUE 'HAS .5 AND -1 IN IT'", "'HAS .5 AND -1 IN IT'"),
        ("VALUE 1", "1"),
        ("VALUE 01", "01"),
        ("VALUE 0.5", "0.5"),
        ("VALUE 000450000.00", "000450000.00"),
        # signed numeric
        ("VALUE -1", "-1"),
        ("VALUE +1", "+1"),
        ("VALUE -0.5", "-0.5"),
        ("VALUE +0.5", "+0.5"),
        ("VALUE -000450000.00", "-000450000.00"),
        # leading decimal
        ("VALUE .5", ".5"),
        ("VALUE .05", ".05"),
        ("VALUE -.5", "-.5"),
        ("VALUE +.5", "+.5"),
        # optional IS
        ("VALUE IS 1", "1"),
        ("VALUE IS -1", "-1"),
        ("VALUE IS .5", ".5"),
        ("VALUE IS -.5", "-.5"),
        ("VALUE IS 'Y'", "'Y'"),
        # figurative constants
        ("VALUE ZERO", "ZERO"),
        ("VALUE ZEROS", "ZEROS"),
        ("VALUE ZEROES", "ZEROES"),
        ("VALUE SPACE", "SPACE"),
        ("VALUE SPACES", "SPACES"),
        ("VALUE HIGH-VALUES", "HIGH-VALUES"),
        ("VALUE LOW-VALUE", "LOW-VALUE"),
        ("VALUE QUOTES", "QUOTES"),
    ],
)
def test_singular_value_forms(clause, literal) -> None:
    assert _one(clause) == (literal, (literal,))


# ===========================================================================
# 3. Plural VALUES: multiple values, mixed forms
# ===========================================================================


@pytest.mark.parametrize(
    ("clause", "values"),
    [
        ("VALUES 'A' 'B'", ("'A'", "'B'")),
        ("VALUES 1 2 3", ("1", "2", "3")),
        ("VALUES -1 -2", ("-1", "-2")),
        ("VALUES +1 +2", ("+1", "+2")),
        ("VALUES -1 2 -3", ("-1", "2", "-3")),
        ("VALUES .5 -.5", (".5", "-.5")),
        ("VALUES 1 .5", ("1", ".5")),  # the point of .5 is not the terminator
        ("VALUES .5 1", (".5", "1")),
        ("VALUES 1 -.5 0.25 +.75", ("1", "-.5", "0.25", "+.75")),
        ("VALUES ZERO 1", ("ZERO", "1")),
        ("VALUES SPACES 'X'", ("SPACES", "'X'")),
        ("VALUES 'A'", ("'A'",)),
        # optional IS / ARE noise words
        ("VALUES IS 1 2", ("1", "2")),
        ("VALUES ARE 1 2", ("1", "2")),
        ("VALUES ARE -1 -2", ("-1", "-2")),
        ("VALUES ARE 'A' 'B'", ("'A'", "'B'")),
    ],
)
def test_plural_values_forms(clause, values) -> None:
    # a multi-value condition-name has no single canonical ``value``
    assert _one(clause) == (None, values)


def test_the_noise_word_is_never_captured_as_a_value() -> None:
    """``VALUES IS 1 2`` used to yield ``('IS', '1', '2')``."""
    assert "IS" not in _one("VALUES IS 1 2")[1]  # type: ignore[index]
    assert "ARE" not in _one("VALUES ARE 1 2")[1]  # type: ignore[index]


# ===========================================================================
# 4. Item boundaries: a leading-decimal point is not a terminator, and a
#    terminator is never mistaken for a decimal point
# ===========================================================================


def test_a_run_of_88_entries_with_every_form_parses_and_keeps_order(tmp_path) -> None:
    source = _program(
        "01  P PIC S9V99 VALUE 1.",
        "    88  A VALUE 'D'.",
        "    88  B VALUE -1.",
        "    88  C VALUES -1 .5.",
        "    88  D VALUE -.5.",
        "    88  E VALUES ARE 1 2.",
        "    88  F VALUE ZERO.",
        "01  Q PIC X(3) VALUE 'ABC'.",
        "    88  G VALUE IS 'ABC'.",
    )
    found = _conditions(source)
    assert list(found) == list("ABCDEFG")
    assert found["C"] == (None, ("-1", ".5"))
    assert found["D"] == ("-.5", ("-.5",))
    assert found["G"] == ("'ABC'", ("'ABC'",))
    result = _analyse(source, tmp_path)
    assert "SYN005" not in _codes(result) and "SYN001" not in _codes(result)
    # the elementary items around them are untouched
    walk = [
        (i.name, i.value)
        for i in result.ast.data_division.working_storage.items
        if not isinstance(i, ConditionNameNode)
    ]
    assert walk == [("P", "1"), ("Q", "'ABC'")]


def test_a_terminating_period_is_not_a_decimal_point() -> None:
    """``VALUES 1 2.`` then the next entry on the following line, and a period
    followed by whitespace then another entry on the same line."""
    assert _conditions(
        _program("01  P PIC 9.", "    88  A VALUES 1 2.", "    88  B VALUE 3.")
    ) == {"A": (None, ("1", "2")), "B": ("3", ("3",))}
    assert _conditions(
        _program("01  P PIC 9.", "    88  A VALUES 1 2. 88  B VALUE 3.")
    ) == {"A": (None, ("1", "2")), "B": ("3", ("3",))}


# ===========================================================================
# 5. Rejected forms stay rejected (deliberately), and never poison neighbours
# ===========================================================================


@pytest.mark.parametrize(
    "clause",
    [
        "VALUE - 1",  # detached sign
        "VALUE + 1",
        "VALUE + .5",
        "VALUE . 5",  # detached point
        "VALUE IS - 1",
        "VALUES 1 - 2",
        "VALUE 1 THRU 5",  # ranges are a separate, unsupported form
        "VALUES 1 THRU 5",
        "VALUES 1 THROUGH 5",
        "VALUES 1, 2, 3",  # comma separators are not supported
        "VALUES 'A', 'B'",
        "VALUE",  # no literal
        "VALUES",
    ],
)
def test_unsupported_forms_are_dropped_with_a_diagnostic(clause, tmp_path) -> None:
    source = _program(
        "01  P PIC S9V99 VALUE 1.", f"    88  BAD {clause}.", "    88  GOOD VALUE 'G'."
    )
    found = _conditions(source)
    assert "BAD" not in found
    assert found.get("GOOD") == ("'G'", ("'G'",))  # the next entry still parses
    assert "SYN005" in _codes(_analyse(source, tmp_path))


def test_a_detached_point_after_a_value_is_a_terminator_not_a_decimal(tmp_path) -> None:
    """``VALUES 1 . 5`` is ``VALUES 1.`` followed by a stray ``5.``: the detached
    period ends the entry (it is *not* joined into ``.5``), and the stray tokens
    are what get reported -- the same as before this stage."""
    source = _program(
        "01  P PIC 9V9 VALUE 1.", "    88  A VALUES 1 . 5.", "    88  GOOD VALUE 'G'."
    )
    found = _conditions(source)
    assert found["A"] == (None, ("1",))  # never ('1', '.5')
    assert found["GOOD"] == ("'G'", ("'G'",))
    assert "SYN005" in _codes(_analyse(source, tmp_path))


def test_the_thru_message_and_the_detached_sign_message_are_unchanged(tmp_path) -> None:
    thru = _analyse(_program("01  P PIC 9.", "    88  R VALUES 1 THRU 5."), tmp_path)
    assert any("THRU range form is not supported" in m for m in _messages(thru))
    sign = _analyse(_program("01  P PIC 9.", "    88  N VALUE - 1."), tmp_path)
    assert any(
        "expected literal after VALUE for condition 'N', got '-'" in m
        for m in _messages(sign)
    )
    plural = _analyse(_program("01  P PIC 9.", "    88  N VALUES 1 - 2."), tmp_path)
    assert any(
        "expected literal after VALUES for condition 'N', got '-'" in m
        for m in _messages(plural)
    )


# ===========================================================================
# 6. Elementary-item VALUE behavior is untouched (Stages 21 and 22)
# ===========================================================================


def _elementary(clause: str) -> dict[str, str | None]:
    program = ProgramParser().parse(_tokens(_program(f"01  A PIC S9(3)V99 {clause}.")))
    return {i.name: i.value for i in program.data_division.working_storage.items}


@pytest.mark.parametrize(
    ("clause", "expected"),
    [
        ("VALUE +000450000.00", "+000450000.00"),
        ("VALUE -5", "-5"),
        ("VALUE .50", ".50"),
        ("VALUE -.50", "-.50"),
        ("VALUE +.50", "+.50"),
        ("VALUE IS .50", ".50"),
        ("VALUE 0.50", "0.50"),
        ("VALUE 'TEXT'", "'TEXT'"),
        ("VALUE SPACES", "SPACES"),
    ],
)
def test_elementary_item_values_are_unchanged(clause, expected) -> None:
    assert _elementary(clause) == {"A": expected}


def test_elementary_detached_forms_keep_their_diagnostics(tmp_path) -> None:
    detached = _analyse(_program("01  A PIC S9(3) VALUE + 5."), tmp_path)
    assert any("expected '.' to terminate data item" in m for m in _messages(detached))
    point = _analyse(_program("01  A PIC S9V99 VALUE + .50."), tmp_path)
    assert any("numeric literal directly after the sign" in m for m in _messages(point))


# ===========================================================================
# 7. Propagation: AST -> symbol table -> behavioral-extraction consumers
# ===========================================================================

_PROPAGATION = _program(
    "01  WS-N PIC S9(3) VALUE 1.",
    "    88  NEG-ONE VALUE -1.",
    "    88  HALF VALUE .5.",
    "    88  SIGNS VALUES -1 +1 -.5.",
    "01  WS-C PIC X(1) VALUE 'D'.",
    "    88  IS-DEP VALUE 'D'.",
)


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    return build_analysis_bundle(
        "level88", _PROPAGATION, str(tmp_path_factory.mktemp("bundle"))
    )


def test_symbols_are_registered_for_the_new_forms(tmp_path) -> None:
    from app.parser.semantic.analyzer import SemanticAnalyzer

    result = _analyse(_PROPAGATION, tmp_path)
    table = SemanticAnalyzer().analyse(result.ast).symbol_table
    for name in ("NEG-ONE", "HALF", "SIGNS", "IS-DEP"):
        sym = table.lookup(name)
        assert sym is not None and sym.level == 88, name  # type: ignore[union-attr]


def test_behavioral_consumers_receive_the_declared_values(bundle) -> None:
    values = _collect_condition_name_values(bundle.ast)
    assert values["NEG-ONE"] == ("-1",)
    assert values["HALF"] == (".5",)
    assert values["SIGNS"] == ("-1", "+1", "-.5")
    assert values["IS-DEP"] == ("D",)  # string literals are unquoted, as before
    parents = _collect_condition_name_parents(bundle.ast)
    assert parents == {
        "NEG-ONE": "WS-N",
        "HALF": "WS-N",
        "SIGNS": "WS-N",
        "IS-DEP": "WS-C",
    }


def test_boundary_values_cover_the_whole_declared_domain(bundle) -> None:
    values = _collect_condition_name_values(bundle.ast)["SIGNS"]
    assert _generate_condition_name_boundary_values("IS-TRUE", values) == [
        ("-1", True),
        ("+1", True),
        ("-.5", True),
        ("OTHER", False),
    ]
    assert _generate_condition_name_boundary_values("IS-FALSE", values)[-1] == (
        "OTHER",
        True,
    )


# ===========================================================================
# 8. Corpus: the 11 real level-88 entries are unchanged
# ===========================================================================


def test_corpus_level_88_entries_parse_exactly_as_before(tmp_path) -> None:
    rec = next(
        r for r in load_training_corpus() if r.source_id == "t_condition_names_88"
    )
    found = _conditions(rec.source)
    assert found == {
        "TX-DEPOSIT": ("'D'", ("'D'",)),
        "TX-WITHDRAWAL": ("'W'", ("'W'",)),
        "TX-TRANSFER": ("'T'", ("'T'",)),
        "TX-FEE": ("'F'", ("'F'",)),
        "TX-VALID-KIND": (None, ("'D'", "'W'", "'T'", "'F'")),
        "TX-PENDING": ("'P'", ("'P'",)),
        "TX-APPROVED": ("'A'", ("'A'",)),
        "TX-REJECTED": ("'R'", ("'R'",)),
        "TX-SETTLED": ("'S'", ("'S'",)),
        "ONLINE-CHANNEL": (None, ("'WEB'", "'MOB'", "'API'")),
        "PHYSICAL-BRANCH": (None, ("'BRN'", "'ATM'")),
    }
    # and no other corpus source declares a level-88 entry at all
    others = [
        r.source_id
        for r in load_training_corpus()
        if r.source_id != "t_condition_names_88"
        and any(
            len(line) > 7 and line[6] != "*" and " 88 " in f" {line[7:72].split()[0]} "
            for line in r.source.splitlines()
            if len(line) > 7 and line[7:72].split()
        )
    ]
    assert others == []
