"""Java translation of COBOL single-quoted string literals.

``_translate_operand`` recognised only Java's own ``"..."`` delimiter as a
string literal. A COBOL literal written with COBOL's own delimiter, ``'...'``
(the overwhelmingly common form in the corpus -- ``MOVE 'Y' TO WS-FLAG``,
``IF PAYMENT-METHOD = 'ACH'``), fell through to the "COBOL identifier" rule
and was silently turned into an undeclared Java variable reference
(``'Y'`` -> ``y``) -- the direct cause of every remaining ``cannot find
symbol`` ``javac`` failure in the corpus. It is now re-emitted as a Java
``"..."`` string literal with the same content.

Root-cause trace (verified, not assumed): the lexer keeps a COBOL string
token's delimiting quotes in its lexeme (``_read_string``, either ``'`` or
``"``). ``IRBuilder.build_operand`` recognises only the ``"``-delimited form
as a literal (``app/ir/builder.py:1001``); a ``'``-delimited operand falls
through to ``build_variable_reference``, whose only transformation is
``.upper()`` on the *whole* token (quotes included) -- a no-op for every real
corpus literal, all of which are already upper-case (verified: no corpus
single-quoted literal contains a lower-case letter). So the exact original
quoted text reaches ``_translate_operand`` unchanged, and a backend-only fix
there is sufficient. (The upstream `.upper()` call *would* corrupt a future
mixed-case single-quoted literal's content -- see "new independent gaps" in
``docs/MMIM_JAVA_LITERAL_EMISSION_FIX.md``; not fixed here, since it lives in
the IR builder, not the backend, and the current 45-source corpus never
triggers it.)

Not in scope, deliberately unchanged: ``==`` on the resulting Java `String`
is reference equality, not value equality (`docs/MMIM_JAVA_IF_EMISSION_FIX.md`
§7 already named this a separate issue requiring type information the IR does
not carry); this file asserts the literal's *text*, never its `==` semantics.
COBOL's doubled-quote escape (``'IT''S'``) is not lexed as one token to begin
with (a separate, pre-existing lexer gap: the scanner stops at the first
matching quote), so it cannot reach this function and is out of scope
(parser tokenization is explicitly untouched).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from app.analysis.service import AnalysisService
from app.backend.java.statement_emitter import (
    _escape_java_string_content,
    _translate_operand,
)

SOURCES = Path("data/sources/phase6-v2")


# --- 1. the fix itself ------------------------------------------------------


@pytest.mark.parametrize(
    ("cobol", "java"),
    [
        ("'Y'", '"Y"'),
        ("'N'", '"N"'),
        ("'ACH'", '"ACH"'),
        ("'AUTO'", '"AUTO"'),
        ("'LIFE'", '"LIFE"'),
        (
            "'SKIPPED-ALPHA'",
            '"SKIPPED-ALPHA"',
        ),  # hyphen: not a valid Java identifier char
        ("' '", '" "'),  # a single space
        ("''", '""'),  # empty literal
        ("'55 WALL STREET'", '"55 WALL STREET"'),  # embedded spaces and digits
        ("'A.HAMILTON@TREASURY.GOV'", '"A.HAMILTON@TREASURY.GOV"'),  # punctuation
        (
            "'999-12-3456'",
            '"999-12-3456"',
        ),  # digits that look numeric but are not IR numerics
    ],
)
def test_single_quoted_literal_becomes_a_java_string_literal(cobol, java):
    assert _translate_operand(cobol) == java


def test_double_quoted_literal_behavior_is_unchanged():
    assert _translate_operand('"HELLO"') == '"HELLO"'
    assert _translate_operand('""') == '""'
    assert _translate_operand("\"HAS 'APOSTROPHE'\"") == "\"HAS 'APOSTROPHE'\""


@pytest.mark.parametrize(
    ("operand", "expected"),
    [
        ("42", "42"),
        ("-1", "-1"),
        ("0.25", "0.25"),
        ("+5", "+5"),
    ],
)
def test_numeric_literal_behavior_is_unchanged(operand, expected):
    assert _translate_operand(operand) == expected


@pytest.mark.parametrize(
    ("cobol_name", "java_identifier"),
    [
        ("WS-GREETING", "wsGreeting"),
        ("WS-COUNT", "wsCount"),
        ("CUSTOMER-NAME", "customerName"),
    ],
)
def test_unquoted_identifier_behavior_is_unchanged(cobol_name, java_identifier):
    assert _translate_operand(cobol_name) == java_identifier


def test_ambiguous_single_char_operand_is_not_misread_as_an_apostrophe():
    """A bare ``'`` is not a valid COBOL operand the lexer/AST ever produce
    (an unterminated string is a LexerError), but the length guard must not
    treat a 1-character operand as a matched pair of delimiters."""
    assert _translate_operand("'") == to_identifier_or_literal("'")


def to_identifier_or_literal(operand: str) -> str:
    from app.backend.java.naming import to_java_field_name

    return to_java_field_name(operand)


# --- escaping ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "escaped"),
    [
        ("PLAIN", "PLAIN"),
        ('HAS "QUOTES"', 'HAS \\"QUOTES\\"'),
        ("BACK\\SLASH", "BACK\\\\SLASH"),
        ('BOTH \\ AND "', 'BOTH \\\\ AND \\"'),
    ],
)
def test_escape_java_string_content(content, escaped):
    assert _escape_java_string_content(content) == escaped


def test_literal_with_a_double_quote_inside_compiles():
    """A COBOL literal delimited by single quotes may itself contain a
    double quote (Java's delimiter) -- it must be escaped, not left to break
    the generated Java's own string literal."""
    assert _translate_operand("'SAY \"HI\"'") == '"SAY \\"HI\\""'


def test_literal_with_a_backslash_compiles():
    assert _translate_operand("'C:\\PATH'") == '"C:\\\\PATH"'


# --- pipeline: COBOL -> AST -> IR -> Java -----------------------------------

_HEADER = textwrap.dedent("""\
    IDENTIFICATION DIVISION.
    PROGRAM-ID. T.
    DATA DIVISION.
    WORKING-STORAGE SECTION.
    01 WS-R PIC X(20) VALUE SPACE.
    01 WS-CODE PIC X(4) VALUE SPACE.
    PROCEDURE DIVISION.
    MAIN.
""")


def _java(tmp_path, body: str):
    path = tmp_path / "t.cbl"
    path.write_text(_HEADER + body, encoding="utf-8")
    result = AnalysisService().analyze_file(path)
    return result.java_source, result.backend_diagnostics


def test_pipeline_move_of_single_quoted_literal(tmp_path):
    java, diags = _java(tmp_path, "    MOVE 'Y' TO WS-R.\n    STOP RUN.\n")
    assert 'wsR = "Y";' in java
    assert not [d for d in diags if d.code in ("BE005", "BE007")]


def test_pipeline_display_of_single_quoted_literal(tmp_path):
    java, _ = _java(tmp_path, "    DISPLAY 'HELLO WORLD'.\n    STOP RUN.\n")
    assert 'System.out.println("HELLO WORLD");' in java


def test_pipeline_if_condition_with_single_quoted_literal(tmp_path):
    java, diags = _java(
        tmp_path,
        "    IF WS-CODE = 'ACH'\n        DISPLAY 'YES'\n    END-IF.\n    STOP RUN.\n",
    )
    # Stage 24: a text comparison is COBOL's alphanumeric equality, not Java ``==``
    assert 'if (_cobolEquals(wsCode, "ACH")) {' in java
    assert 'System.out.println("YES");' in java
    assert not [d for d in diags if d.code == "BE007"]


def test_pipeline_compound_condition_with_two_single_quoted_literals(tmp_path):
    java, _ = _java(
        tmp_path,
        "    IF WS-CODE = 'ACH' OR WS-CODE = 'WIRE'\n"
        "        DISPLAY 'MATCH'\n    END-IF.\n    STOP RUN.\n",
    )
    assert 'if (_cobolEquals(wsCode, "ACH") || _cobolEquals(wsCode, "WIRE")) {' in java


@pytest.mark.skipif(shutil.which("javac") is None, reason="javac not installed")
def test_pipeline_output_compiles_with_javac(tmp_path):
    java, _ = _java(
        tmp_path,
        "    MOVE 'Y' TO WS-R.\n"
        "    IF WS-CODE = 'ACH'\n        DISPLAY 'MATCHED'\n    END-IF.\n    STOP RUN.\n",
    )
    (tmp_path / "T.java").write_text(java, encoding="utf-8")
    done = subprocess.run(
        ["javac", str(tmp_path / "T.java")], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr


# --- real corpus --------------------------------------------------------------


@pytest.fixture(scope="module")
def real_java():
    cache: dict[str, tuple[str, list]] = {}

    def load(filename: str):
        if filename not in cache:
            r = AnalysisService().analyze_file(SOURCES / filename)
            cache[filename] = (r.java_source, r.backend_diagnostics)
        return cache[filename]

    return load


# Every real form found in the corpus that reaches the emitted (entry)
# paragraph: single letter, multi-letter code, hyphenated code, phrase with
# spaces, a value containing punctuation.
REAL_LITERALS = [
    ("batch_acct_update.cbl", '"Y"'),  # MOVE 'Y' TO WS-EOF-FLAG
    (
        "fallthrough_flow.cbl",
        '"COMPLETED"',
    ),  # MOVE 'COMPLETED' TO PASS-THRU-STATUS (0000-MAIN-CONTROL). Originally
    # pinned to 'SKIPPED-ALPHA' (2000-STAGE-BETA's IF), which mmim-gen-v16
    # (docs/MMIM_PERFORM_THRU_FIX.md) legitimately removed from this
    # source's generated Java: recovering 0000-MAIN-CONTROL's previously
    # silently-dropped MOVE/GOBACK statements means GOBACK now correctly
    # terminates this backend's flat statement concatenation before it
    # ever reaches 2000-STAGE-BETA.
    ("daily_trans_report.cbl", '"HIGH RISK TRANSACTION FLAGGED"'),
    ("daily_trans_report.cbl", '"Y"'),  # the FD-TX-SUSPICIOUS = 'Y' OR term
    ("policy_redefines.cbl", '"AUTO"'),
    ("policy_redefines.cbl", '"LIFE"'),
    ("goto_spaghetti.cbl", '"STARTED"'),
]


@pytest.mark.parametrize(("filename", "expected"), REAL_LITERALS)
def test_real_single_quoted_literal_is_translated(real_java, filename, expected):
    java, _ = real_java(filename)
    assert expected in java, f"{filename}: {expected} not found"


def test_real_five_previously_unbalanced_sources_compile_further(real_java):
    """These 5 no longer fail with a structural (`illegal start of type` /
    `statements not expected` / `<identifier> expected`) javac error -- only
    `cannot find symbol` for the two separately-tracked, unrelated gaps
    (FILE SECTION fields never declared; == is reference equality)."""
    import tempfile

    for filename in (
        "batch_acct_update.cbl",
        "daily_trans_report.cbl",
        "fallthrough_flow.cbl",
        "goto_spaghetti.cbl",
        "policy_redefines.cbl",
    ):
        java, _ = real_java(filename)
        assert java.count("{") == java.count("}"), filename
        cls = re.search(r"\bclass\s+(\w+)", java).group(1)
        d = Path(tempfile.mkdtemp())
        (d / f"{cls}.java").write_text(java, encoding="utf-8")
        result = subprocess.run(
            ["javac", str(d / f"{cls}.java")], capture_output=True, text=True
        )
        structural = [
            ln
            for ln in result.stderr.splitlines()
            if "error:" in ln
            and "cannot find symbol" not in ln
            and "error: reported" not in ln.lower()
        ]
        assert structural == [], (filename, structural)
