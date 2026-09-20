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

_FIXTURE = Path("workspace/2e87036d-b90e-488f-b199-3162eb7c1c7e/complex_acctbatch.cbl")


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
    """``4000-PROCESS-TRANSACTIONS`` fails at its own ``READ ... AT END`` /
    ``NOT AT END`` block (line 256) -- a separate, pre-existing, unrelated
    parser gap -- well before parsing ever reaches line 263's ``IF
    WS-CURRENT-ACCOUNT NOT = SPACES``. This *stage's* (Stage 26's) fix
    therefore changes nothing observable about this fixture at lines
    256/263, confirmed directly rather than assumed -- still exactly one
    diagnostic at 256, nothing at 263 (line 263 sits inside the ``READ``'s
    ``NOT AT END`` clause, which is skipped as one unsupported statement
    whole -- task #stage28 below -- so it is never separately reached
    either).

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
    already had. The *total* stays 49 (one `SYN005` for `SYN100`, net
    zero) purely by coincidence with task #stage27's own +2 -- see
    ``tests/parser/test_perform_until_unsupported_statement_fix.py`` for the
    full accounting of this stage's own fix."""
    result = AnalysisService().analyze_file(_FIXTURE)
    assert len(result.syntax_diagnostics) == 49
    codes_at_256 = [str(d.code) for d in result.syntax_diagnostics if d.line == 256]
    assert codes_at_256 == ["SYN100"]
    codes_at_263 = [str(d.code) for d in result.syntax_diagnostics if d.line == 263]
    assert codes_at_263 == []


# ===========================================================================
# 7. Regression guard: the pre-existing, unrelated, out-of-scope Java
#    figurative-constant-translation gap is unchanged/symmetric, not fixed
#    or worsened by this stage
# ===========================================================================


def test_figurative_constant_java_translation_gap_is_symmetric_not_new() -> None:
    """Neither this stage nor any prior one taught the Java backend what a
    figurative constant *means*; every spelling -- old (``ZERO``) and newly
    parseable (``SPACES``) alike -- is still translated as a bare,
    undeclared Java identifier reference via the generic COBOL-identifier
    fallback in ``_translate_operand``. Documented, not fixed, here
    (docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md §7)."""
    from app.backend.java.condition_context import ConditionContext
    from app.backend.java.control_flow_emitter import emit_if
    from app.ir.instructions import IRIf

    ctx = ConditionContext(field_types={"wsCode": "String"})
    for word, java_ref in (("ZERO", "zero"), ("SPACES", "spaces"), ("ZEROS", "zeros")):
        cond = IRIf(left="WS-CODE", operator="=", right=word)
        diagnostics: list = []
        (line,) = emit_if(cond, 0, diagnostics, ctx)
        assert line == f"if (wsCode == {java_ref}) {{"
        assert diagnostics == []
