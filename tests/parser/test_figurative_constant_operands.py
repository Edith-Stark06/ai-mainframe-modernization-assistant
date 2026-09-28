"""
Figurative-constant operands in ``IF``/``PERFORM UNTIL`` conditions (Stage 26).

Purpose:
    ``_parse_simple_condition``'s comparison-operand check only ever accepted
    ``TokenType.IDENTIFIER``/``NUMBER``/``STRING``, so a figurative-constant
    operand (``IF WS-CODE = SPACES``) could fail with "expected operand for
    IF condition" -- but only for *some* spellings. ``app.parser.lexer
    .keywords.KEYWORDS`` reserves just two of COBOL's figurative-constant
    words, ``"ZEROS"`` and ``"SPACES"``, so only those two lex as
    ``TokenType.KEYWORD`` and hit the rejection; every other spelling
    (``ZERO``, ``SPACE``, ``ZEROES``, ``HIGH-VALUE(S)``, ``LOW-VALUE(S)``) is
    not a reserved word in this lexer, lexes as a plain
    ``TokenType.IDENTIFIER``, and already parsed. The fix widens the operand
    check to also accept a ``TokenType.KEYWORD`` token when its lexeme is one
    of those two words (``_FIGURATIVE_CONSTANT_KEYWORDS``), matching the
    ``{STRING, NUMBER, IDENTIFIER, KEYWORD}`` shape the analogous level-88
    VALUE-literal grammar (``data_parser._read_condition_literal``) already
    used for exactly this reason. No other token type is newly accepted, so
    an ordinary reserved word in the wrong place (``IF X = MOVE``) still
    fails exactly as before (§4).

    This is a pure parser-recognition fix, like task #stage22: real corpus
    impact is zero (§5) -- the one occurrence anywhere in the repository
    (the shared ``complex_acctbatch.cbl`` fixture, §6) was already
    unreachable behind an unrelated, pre-existing ``READ ... AT END``/``NOT
    AT END`` parsing gap, so its diagnostics are byte-identical before and
    after this change. A separate, pre-existing, *not* newly introduced
    defect is also pinned here rather than fixed (§7): the Java backend has
    no figurative-constant-to-Java-value translation for *any* spelling --
    ``ZERO``/``SPACE``/etc. already emitted an undeclared-identifier
    reference (``wsCode == zero``) before this stage; this fix makes
    ``SPACES``/``ZEROS`` reach that exact same, already-existing symptom
    (parses, but the Java is uncompilable) instead of failing at parse time,
    which is a strict improvement (the condition and its statements are no
    longer silently dropped from the AST/IR/business rules) without touching
    or worsening the backend gap itself.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.analysis.service import AnalysisService
from app.dataset.corpus import load_training_corpus
from app.parser.ast.statements import IfStatementNode
from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.token import Token, TokenType
from app.parser.syntax.procedure_parser import (
    _FIGURATIVE_CONSTANT_KEYWORDS,
    _is_comparison_operand_token,
)
from app.parser.syntax.program_parser import ProgramParser

_HEAD = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FIGCONST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CODE PIC X(5) VALUE 'AUTO'.
       01  WS-R    PIC X(3) VALUE 'NO'.
"""


def _program(stmt: str) -> str:
    return (
        _HEAD
        + f"       PROCEDURE DIVISION.\n       MAIN-PARA.\n           {stmt}\n           STOP RUN.\n"
    )


def _tokens(source: str):
    return CobolLexer().tokenize(source, filename="s.cbl")


def _parse(source: str):
    return ProgramParser().parse(_tokens(source))


def _analyse(source: str, tmp_path: Path):
    path = tmp_path / "figconst.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _codes(result) -> list[str]:
    return [str(getattr(d, "code", "")) for d in result.syntax_diagnostics]


def _if_stmt(program) -> IfStatementNode:
    (stmt,) = [
        s
        for s in program.procedure_division.paragraphs[0].statements
        if isinstance(s, IfStatementNode)
    ]
    return stmt


# ===========================================================================
# 1. Root cause: only SPACES/ZEROS lex as KEYWORD; every other figurative
#    constant already lexed as IDENTIFIER
# ===========================================================================

_ALL_FIGURATIVE_CONSTANTS = (
    "ZERO",
    "ZEROS",
    "ZEROES",
    "SPACE",
    "SPACES",
    "HIGH-VALUE",
    "HIGH-VALUES",
    "LOW-VALUE",
    "LOW-VALUES",
)


def test_figurative_constant_keyword_set_is_exactly_zeros_and_spaces() -> None:
    assert _FIGURATIVE_CONSTANT_KEYWORDS == {"ZEROS", "SPACES"}


@pytest.mark.parametrize("word", _ALL_FIGURATIVE_CONSTANTS)
def test_figurative_constant_lexer_classification(word: str) -> None:
    toks = _tokens(_program(f"IF WS-CODE = {word} MOVE 'Y' TO WS-R END-IF"))
    (tok,) = [t for t in toks if t.lexeme == word]
    expected = (
        TokenType.KEYWORD
        if word in _FIGURATIVE_CONSTANT_KEYWORDS
        else TokenType.IDENTIFIER
    )
    assert tok.type is expected, word


# ===========================================================================
# 2. _is_comparison_operand_token: the exact widened acceptance, and its
#    boundary (an ordinary reserved word is still rejected)
# ===========================================================================


def _kw_token(lexeme: str) -> Token:
    (tok,) = [
        t
        for t in _tokens(_program(f"IF WS-CODE = {lexeme} MOVE 'Y' TO WS-R END-IF"))
        if t.lexeme == lexeme
    ]
    return tok


@pytest.mark.parametrize("word", ["SPACES", "ZEROS"])
def test_operand_token_accepts_the_two_figurative_constant_keywords(word: str) -> None:
    assert _is_comparison_operand_token(_kw_token(word))


def test_operand_token_still_rejects_an_ordinary_reserved_word() -> None:
    """An unrelated keyword (``MOVE``) in operand position must still be
    rejected -- the widened check is scoped to exactly the two figurative
    constants, not every ``TokenType.KEYWORD``."""
    toks = _tokens(_program("IF WS-CODE = 5 MOVE 'Y' TO WS-R END-IF"))
    (move_tok,) = [t for t in toks if t.lexeme == "MOVE"][:1]
    assert not _is_comparison_operand_token(move_tok)


# ===========================================================================
# 3. Parser: every figurative-constant spelling parses as an IF-condition
#    operand, in both operand positions, with zero syntax diagnostics
# ===========================================================================


@pytest.mark.parametrize("word", _ALL_FIGURATIVE_CONSTANTS)
def test_figurative_constant_as_right_operand(word: str, tmp_path: Path) -> None:
    result = _analyse(
        _program(
            f"IF WS-CODE = {word}\n               MOVE 'Y' TO WS-R\n           END-IF"
        ),
        tmp_path,
    )
    assert _codes(result) == []
    stmt = _if_stmt(result.ast)
    assert (stmt.condition_left, stmt.condition_operator, stmt.condition_right) == (
        "WS-CODE",
        "=",
        word,
    )


@pytest.mark.parametrize("word", _ALL_FIGURATIVE_CONSTANTS)
def test_figurative_constant_as_left_operand(word: str, tmp_path: Path) -> None:
    result = _analyse(
        _program(
            f"IF {word} = WS-CODE\n               MOVE 'Y' TO WS-R\n           END-IF"
        ),
        tmp_path,
    )
    assert _codes(result) == []
    stmt = _if_stmt(result.ast)
    assert (stmt.condition_left, stmt.condition_operator, stmt.condition_right) == (
        word,
        "=",
        "WS-CODE",
    )


# ===========================================================================
# 4. Composes with Stage 25's NOT-negation and <> forms
# ===========================================================================


def test_not_equal_figurative_constant(tmp_path: Path) -> None:
    result = _analyse(
        _program(
            "IF WS-CODE NOT = SPACES\n               MOVE 'Y' TO WS-R\n           END-IF"
        ),
        tmp_path,
    )
    assert _codes(result) == []
    stmt = _if_stmt(result.ast)
    assert (stmt.condition_left, stmt.condition_operator, stmt.condition_right) == (
        "WS-CODE",
        "<>",
        "SPACES",
    )


def test_angle_bracket_not_equal_figurative_constant(tmp_path: Path) -> None:
    result = _analyse(
        _program(
            "IF WS-CODE <> ZEROS\n               MOVE 'Y' TO WS-R\n           END-IF"
        ),
        tmp_path,
    )
    assert _codes(result) == []
    stmt = _if_stmt(result.ast)
    assert (stmt.condition_left, stmt.condition_operator, stmt.condition_right) == (
        "WS-CODE",
        "<>",
        "ZEROS",
    )


# ===========================================================================
# 5. Real corpus: zero occurrences anywhere in the 45-source training corpus
# ===========================================================================

_FIGURATIVE_CONSTANT_PATTERN = re.compile(
    r"(?:=|<>|<=|>=|<|>)\s*(SPACES?|ZEROS?|ZEROES|HIGH-VALUES?|LOW-VALUES?)\b",
    re.IGNORECASE,
)


def test_no_corpus_source_uses_a_figurative_constant_as_a_comparison_operand() -> None:
    """Confirms the corpus-impact claim directly, the same way every prior
    stage's survey did: search raw source text (code columns, comments
    excluded) for a figurative constant immediately after a comparison
    operator. This stage's fix has zero corpus impact -- no version bump,
    no dataset regeneration."""
    hits: dict[str, int] = {}
    for rec in load_training_corpus():
        n = 0
        for line in rec.source.splitlines():
            if len(line) > 6 and line[6] in "*/":
                continue
            code = line[7:] if len(line) > 7 else ""
            n += len(_FIGURATIVE_CONSTANT_PATTERN.findall(code))
        if n:
            hits[rec.source_id] = n
    assert hits == {}


# ===========================================================================
# 6. Shared workspace fixture: the one real occurrence is already
#    unreachable behind an unrelated, pre-existing gap -- byte-identical
#    diagnostics before and after this fix
# ===========================================================================

_FIXTURE = Path("tests/fixtures/complex_acctbatch.cbl")


@pytest.mark.skipif(
    not _FIXTURE.exists(), reason="shared workspace fixture not present"
)
def test_fixture_still_has_the_one_spaces_occurrence_line() -> None:
    text = _FIXTURE.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert "NOT = SPACES" in lines[262]  # line 263, 1-indexed


@pytest.mark.skipif(
    not _FIXTURE.exists(), reason="shared workspace fixture not present"
)
def test_fixture_diagnostic_total_is_unchanged_by_this_fix() -> None:
    """``4000-PROCESS-TRANSACTIONS`` failed at its own ``READ ... AT END`` /
    ``NOT AT END`` block (line 256) -- a separate, pre-existing, unrelated
    parser gap at the time this test was written -- well before parsing
    ever reached line 263's ``IF WS-CURRENT-ACCOUNT NOT = SPACES``. This
    *stage's* (Stage 26's) fix therefore changed nothing observable about
    this fixture at lines 256/263 at the time -- back then, still exactly
    one diagnostic at 256 (``READ``, whole statement skipped), nothing at
    263 (inside the skipped ``NOT AT END`` clause, never separately
    reached).

    That premise no longer holds as of task #stage40 (below): ``READ`` now
    has a real parser/AST node, so line 256 produces zero diagnostics, and
    line 263's ``IF`` is reached and captured on the AST as one of the
    ``READ``'s ``not_at_end_statements`` -- still never lowered to IR
    (unreachable under this backend's always-end-of-file model), but no
    longer hidden behind a skip either. Confirmed directly: neither line
    appears in ``result.syntax_diagnostics`` any more.

    The total moved 47 -> 49 for a wholly unrelated reason: task #stage27
    (FILE SECTION support) reaches this fixture's own 3-``FD`` FILE SECTION
    (lines 24-63, no relation to comparison operands), replacing its one
    ``SYN101 "unsupported DATA DIVISION section 'FILE'"`` with 3
    previously-latent ``SYN200 "'COMP-3' clause ... not represented"``
    warnings on 3 of its fields -- see
    ``tests/parser/test_unsupported_syntax_reporting.py
    ::test_complex_fixture_surfaces_49_syntax_diagnostics`` for the full
    accounting. Pinned here as 49, not re-derived, so this test keeps
    proving *this* stage's own claim (lines 256/263 unchanged) rather than
    silently drifting if a later stage touches the total again.

    Line 256's own *code* moved `SYN005` -> `SYN100` for a third, also
    unrelated reason: task #stage28
    (docs/MMIM_PERFORM_UNTIL_UNSUPPORTED_STATEMENT_FIX.md) teaches the
    ``PERFORM UNTIL`` body loop to skip an unsupported verb (``READ`` here)
    gracefully instead of raising a hard parser error -- the vague "expected
    statement in PERFORM block" becomes the precise "unsupported statement
    'READ'", the same upgrade every other unsupported-statement location
    already had. The *total* stayed 49 (one `SYN005` for `SYN100`, net
    zero) purely by coincidence with task #stage27's own +2 -- see
    ``tests/parser/test_perform_until_unsupported_statement_fix.py`` for the
    full accounting of this stage's own fix.

    49 -> 48 (task #stage32) is a fourth, again unrelated, reason: this
    fixture's ``4100-FIND-ACCOUNT``/``5000-CALCULATE-EXPOSURE`` paragraphs
    (subscripted table lookups over ``WS-ACCOUNT-ENTRY OCCURS 50 TIMES``,
    lines 126-140-ish) contain ``IF`` conditions on a subscripted operand
    (``WA-ACCOUNT-ID(WS-IDX)``, ``WA-STATUS(WS-IDX)``) -- this grammar's
    comparison-operand check had never accepted one, so each produced its
    own latent ``SYN005 "expected comparison operator"``, and the whole
    enclosing ``IF``/``END-IF`` (with its ``THEN``/``ELSE`` bodies) was
    dropped. Task #stage32 (docs/...) teaches the condition parser to
    recognise a single-dimension, literal- or identifier-subscripted
    reference as one structured operand instead, so those ``IF``s now
    parse -- one fewer ``SYN005``, net -1. Confirmed directly, not assumed:
    ``statements_parsed`` (not asserted by this test, but checked directly
    against the fixture while diagnosing this change) rose from 60 to 68 --
    the same "walking past a fixed gate reveals previously-unreachable
    code" pattern this fixture's own history above already shows for the
    ``NOT =`` fix, not new instability. Lines 256/263 (this test's own
    subject) are untouched by this change -- confirmed directly, not
    assumed -- since they sit in an unrelated paragraph reached (and still
    gated by the separate ``READ ... AT END`` gap) regardless of this fix.

    48 -> 47 (task #stage34) is a fifth, again unrelated, reason:
    ``PERFORM VARYING`` (this fixture has four occurrences, none at lines
    256/263) previously misparsed entirely -- the token right after
    ``PERFORM`` being ``VARYING`` (not ``UNTIL``) fell into the inline
    single-target PERFORM branch, producing ``PerformStatementNode(
    target="VARYING")`` and leaving the loop variable
    (``WS-IDX``/``WS-IDX2``) stranded on the stream as an unexpected
    token -- 4 latent ``SYN001 "unexpected token"`` diagnostics, one per
    occurrence. Task #stage34 adds a real ``PerformVaryingStatementNode``/
    parser, removing all 4 (net -4); it also newly reaches two
    ``EXIT PERFORM`` statements nested inside those loops' bodies (task
    #stage34's real corpus/fixture-shape discovery, previously
    unreachable for the same reason) and correctly reports each as its
    own ``SYN100 "unsupported statement 'EXIT PERFORM'"`` (net +2) instead
    of letting the stray ``PERFORM`` token that used to follow a
    mis-skipped bare ``EXIT`` corrupt the surrounding parse -- see
    ``tests/parser/test_stage34_perform_varying.py`` for the parser-level
    tests. Net -2 (48 -> 47). Confirmed directly, not assumed. Lines
    256/263 remain untouched.

    47 -> 44 (task #stage35) is a sixth, again unrelated, reason: COMPUTE
    is now implemented (for the grammar the 45-source corpus evidences).
    4 of this fixture's 6 real COMPUTE statements now parse into a
    ``ComputeStatementNode`` instead of a ``SYN100`` skip (net -4); the
    other 2 use syntax Stage 35 does not implement (an intrinsic
    ``FUNCTION`` operand, the ``ROUNDED`` clause) and are unaffected --
    see ``tests/parser/test_unsupported_syntax_reporting.py
    ::test_complex_fixture_surfaces_49_syntax_diagnostics`` for the full
    accounting. None of the 6 are at lines 256/263. Pinned here as 44,
    not re-derived, for the same reason 49 was pinned above.

    44 -> 41 (task #stage40) is the ``READ`` implementation, and this is
    the one delta in this fixture's history that *does* touch line 256
    directly: line 256's own ``SYN100 "unsupported statement 'READ'"``
    (and the two sibling ``READ`` occurrences at lines 191/229) are gone
    -- all three now parse into a real ``ReadStatementNode`` (net -3).
    See ``tests/parser/test_perform_until_unsupported_statement_fix.py
    ::test_fixture_diagnostic_total_and_statements_parsed_move_by_the_read_fix``
    for the full accounting. Line 263 still produces no diagnostic of its
    own (unchanged from before -- see the updated class docstring above).

    41 -> 24 (task #stage41) is a seventh, again unrelated, reason: this
    fixture's 17 real ``COMP-3`` occurrences (none at lines 256/263) each
    previously produced their own ``SYN200 "'COMP-3' clause ... not
    represented"``; all 17 now attach a real ``UsageType.COMP_3`` via
    ``ElementaryItemNode.usage`` with zero diagnostics (net -17) -- see
    ``tests/parser/test_unsupported_syntax_reporting.py
    ::test_complex_fixture_surfaces_49_syntax_diagnostics`` for the full
    accounting. Lines 256/263 remain untouched."""
    result = AnalysisService().analyze_file(_FIXTURE)
    assert len(result.syntax_diagnostics) == 24
    codes_by_line = {d.line: str(d.code) for d in result.syntax_diagnostics}
    assert 256 not in codes_by_line
    assert 263 not in codes_by_line


# ===========================================================================
# 7. Regression guard: at the time of this stage (Stage 26), the pre-existing,
#    unrelated, out-of-scope Java figurative-constant-translation gap was
#    unchanged/symmetric across every spelling, not fixed or worsened here.
#    Task #stage31 (docs/FIGURATIVE_CONSTANT_JAVA_EMISSION.md) later fixed
#    the *type-compatible* cases (SPACES/SPACE against text, ZERO family
#    against a number) -- see
#    tests/backend/test_figurative_constant_java_emission.py for that. This
#    test now pins what Stage 31 deliberately leaves exactly as broken as it
#    was here: a figurative constant compared against a field of the *wrong*
#    type, which no stage has proof enough to translate.
# ===========================================================================


def test_figurative_constant_java_translation_gap_remains_for_type_mismatches() -> None:
    """``ZERO``/``ZEROS`` compared against a ``String`` field is a genuine
    type mismatch (a numeric figurative constant on a text item): task
    #stage31 requires proof of the *other* operand's type before
    translating a figurative constant, and correctly finds none here, so
    this stays the same undeclared Java identifier reference it always was.
    ``SPACES`` against this same ``String`` field, by contrast, is exactly
    the case Stage 31 now translates -- no longer symmetric with ``ZERO``/
    ``ZEROS``, by design; asserted directly rather than assumed."""
    from app.backend.java.condition_context import ConditionContext
    from app.backend.java.control_flow_emitter import emit_if
    from app.ir.instructions import IRIf

    ctx = ConditionContext(field_types={"wsCode": "String"})
    for word, java_ref in (("ZERO", "zero"), ("ZEROS", "zeros")):
        cond = IRIf(left="WS-CODE", operator="=", right=word)
        diagnostics: list = []
        (line,) = emit_if(cond, 0, diagnostics, ctx)
        assert line == f"if (wsCode == {java_ref}) {{"
        assert diagnostics == []

    cond = IRIf(left="WS-CODE", operator="=", right="SPACES")
    (line,) = emit_if(cond, 0, [], ctx)
    assert line == 'if (_cobolEquals(wsCode, "")) {'
