"""
Negated relational operators in ``IF``/``PERFORM UNTIL`` conditions (Stage 25).

Purpose:
    COBOL's own relational-operator grammar is
    ``relational-operator ::= [NOT] { = | > | < | >= | <= | <> }`` -- a
    ``NOT`` sitting *between* the two operands negates the operator, not the
    operand (``IF WS-CODE NOT = 'AUTO'``). Neither form the grammar actually
    uses to spell "not equal" was recognised: ``<>`` was tokenized as two
    independent operator tokens (``<`` then ``>``), so ``IF X <> 'A'`` failed
    with "expected operand for IF condition"; ``NOT`` immediately before an
    operator was not consumed at all, so ``IF X NOT = 'A'`` failed with
    "expected comparison operator in IF condition" -- and with it, the whole
    ``IF`` statement was dropped by panic-mode recovery (present nowhere in
    the AST, IR, business rules, or generated Java).

    ``!=`` -- this grammar's own project-specific spelling -- already parsed
    correctly and was already fully translated by the Stage 24 backend
    (``_cobolEquals`` for text, ``!=`` for numbers). The fix is therefore
    purely about *recognizing* the two missing COBOL spellings and folding
    them (and ``NOT`` before every other operator: ``NOT >``, ``NOT <``,
    ``NOT >=``, ``NOT <=``) down to an already-supported plain spelling --
    ``NOT =`` and ``<>`` both become ``<>``, aliased to Java ``!=`` in
    ``control_flow_emitter.OPERATOR_ALIASES`` the same way ``=`` is already
    aliased to ``==``. No IR change, no new operator the backend has to
    learn.

    The *leading* ``NOT`` before an entire condition (``IF NOT WS-CODE =
    'AUTO'``, as opposed to ``IF WS-CODE NOT = 'AUTO'``) is a different,
    broader COBOL grammar rule (``condition ::= [NOT] simple-condition``).
    ``_parse_condition_term`` already handles it for a known level-88
    condition-name and its own docstring explicitly calls the general case
    "the unrelated, out-of-scope 'NOT <comparison>' gap" -- this stage does
    not touch it; it is re-pinned here as a regression guard (§5).

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.service import AnalysisService
from app.dataset.corpus import load_training_corpus
from app.parser.ast.statements import IfStatementNode
from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.token import Token
from app.parser.syntax.program_parser import ProgramParser

_HEAD = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. NEGCMP.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CODE PIC X(4) VALUE 'AUTO'.
       01  WS-N    PIC 9(3) VALUE 5.
       01  WS-R    PIC X(3) VALUE 'NO'.
"""
_TAIL = """\
       PROCEDURE DIVISION.
       MAIN-PARA.
           STOP RUN.
"""


def _program(stmt: str, procedure: str | None = None) -> str:
    body = (
        procedure
        or f"       PROCEDURE DIVISION.\n       MAIN-PARA.\n           {stmt}\n           STOP RUN.\n"
    )
    return _HEAD + body


def _tokens(source: str):
    return CobolLexer().tokenize(source, filename="s.cbl")


def _parse(source: str):
    return ProgramParser().parse(_tokens(source))


def _analyse(source: str, tmp_path: Path):
    path = tmp_path / "negcmp.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _codes(result) -> list[str]:
    return [str(getattr(d, "code", "")) for d in result.syntax_diagnostics]


def _messages(result) -> list[str]:
    return [str(getattr(d, "message", "")) for d in result.syntax_diagnostics]


def _if_stmt(program) -> IfStatementNode:
    (stmt,) = [
        s
        for s in program.procedure_division.paragraphs[0].statements
        if isinstance(s, IfStatementNode)
    ]
    return stmt


def _walk_if_statements(statements):
    """Every ``IfStatementNode`` in *statements*, including ones nested in an
    ``ELSE`` branch (``ELSE IF ...`` -- a *nested* ``IfStatementNode``, not a
    flat ``ELSE IF`` keyword, in this grammar)."""
    for s in statements:
        if isinstance(s, IfStatementNode):
            yield s
            yield from _walk_if_statements(s.then_statements)
            yield from _walk_if_statements(s.else_statements)


def _operator_index_after_if(toks) -> int:
    """Index of the comparison-operator token of the *first* ``IF``'s
    condition: two positions after the ``IF`` keyword (``IF <operand> <op>
    ...``). Robust to ``WS-N``/other operand names appearing earlier in the
    source (e.g. in the DATA DIVISION), unlike searching for the operand's
    own lexeme."""
    i = next(k for k, t in enumerate(toks) if t.lexeme.upper() == "IF")
    return i + 2


def _operator_token_after_if(toks) -> Token:
    return toks[_operator_index_after_if(toks)]


# ===========================================================================
# 1. The lexer: ``<>`` is one token, only when directly adjacent
# ===========================================================================


def test_adjacent_angle_brackets_are_one_neq_token() -> None:
    toks = _tokens(_program("IF WS-N <> 5 MOVE 'Y' TO WS-R END-IF"))
    op = _operator_token_after_if(toks)
    assert (op.type.name, op.lexeme) == ("OPERATOR_NEQ", "<>")


def test_space_separated_angle_brackets_stay_two_tokens() -> None:
    """The lexer's ``<=``/``>=``/``==``/``!=`` combination has always required
    strict adjacency (``scanner.peek()``, no whitespace skip); ``<>`` follows
    the identical rule, so a detached ``< >`` is unaffected."""
    toks = _tokens(_program("IF WS-N < > 5 MOVE 'Y' TO WS-R END-IF"))
    i = _operator_index_after_if(toks)
    assert (toks[i].type.name, toks[i].lexeme) == ("OPERATOR_LT", "<")
    assert (toks[i + 1].type.name, toks[i + 1].lexeme) == ("OPERATOR_GT", ">")


def test_other_two_char_operators_are_unchanged() -> None:
    """Regression: ``<=``/``>=``/``==``/``!=`` combination logic, sitting right
    beside the new ``<>`` branch, is untouched."""
    for clause, expected in (
        ("<=", ("OPERATOR_LE", "<=")),
        (">=", ("OPERATOR_GE", ">=")),
        ("==", ("OPERATOR_EQ", "==")),
        ("!=", ("OPERATOR_NEQ", "!=")),
    ):
        toks = _tokens(_program(f"IF WS-N {clause} 5 MOVE 'Y' TO WS-R END-IF"))
        op = _operator_token_after_if(toks)
        assert (op.type.name, op.lexeme) == expected, clause


def test_a_lone_less_than_or_greater_than_is_still_unaffected() -> None:
    for clause, expected in ((">", ("OPERATOR_GT", ">")), ("<", ("OPERATOR_LT", "<"))):
        toks = _tokens(_program(f"IF WS-N {clause} 5 MOVE 'Y' TO WS-R END-IF"))
        op = _operator_token_after_if(toks)
        assert (op.type.name, op.lexeme) == expected, clause


# ===========================================================================
# 2. The parser: ``NOT <op>`` and ``<>`` both parse, to the same operator
# ===========================================================================


@pytest.mark.parametrize(
    ("stmt", "operator"),
    [
        ("IF WS-CODE NOT = 'AUTO' MOVE 'Y' TO WS-R END-IF", "<>"),
        ("IF WS-CODE <> 'AUTO' MOVE 'Y' TO WS-R END-IF", "<>"),
        ("IF WS-CODE != 'AUTO' MOVE 'Y' TO WS-R END-IF", "!="),  # regression: unchanged
        ("IF WS-CODE = 'AUTO' MOVE 'Y' TO WS-R END-IF", "="),  # regression: unchanged
        ("IF WS-N NOT > 5 MOVE 'Y' TO WS-R END-IF", "<="),
        ("IF WS-N NOT < 5 MOVE 'Y' TO WS-R END-IF", ">="),
        ("IF WS-N NOT >= 5 MOVE 'Y' TO WS-R END-IF", "<"),
        ("IF WS-N NOT <= 5 MOVE 'Y' TO WS-R END-IF", ">"),
    ],
)
def test_negated_and_plain_operators_produce_the_expected_ast_operator(
    stmt, operator
) -> None:
    program = _parse(_program(stmt))
    assert _if_stmt(program).condition_operator == operator


def test_not_equal_forms_produce_identical_ast_shapes() -> None:
    """``NOT =``, ``<>`` and ``!=`` all mean the same comparison; only the
    *operator string* may legitimately differ (``!=`` keeps its own already-
    supported spelling, ``NOT =``/``<>`` both collapse to ``<>``)."""
    not_eq = _if_stmt(
        _parse(_program("IF WS-CODE NOT = 'AUTO' MOVE 'Y' TO WS-R END-IF"))
    )
    angle = _if_stmt(_parse(_program("IF WS-CODE <> 'AUTO' MOVE 'Y' TO WS-R END-IF")))
    assert not_eq.condition_operator == angle.condition_operator == "<>"
    assert not_eq.condition_left == angle.condition_left == "WS-CODE"
    assert not_eq.condition_right == angle.condition_right == "'AUTO'"


def test_negation_round_trips_back_to_the_original_operator() -> None:
    """``NOT`` of ``NOT <op>`` is ``<op>`` again, for every operator this
    grammar accepts -- exercises :data:`app.parser.syntax.procedure_parser
    ._NEGATED_OPERATOR` as an involution."""
    table = {
        "=": "<>",
        "==": "!=",
        "<>": "=",
        "!=": "==",
        ">": "<=",
        "<": ">=",
        ">=": "<",
        "<=": ">",
    }
    for op, negated in table.items():
        assert table[negated] == op, op


def test_no_syntax_diagnostic_for_any_supported_form(tmp_path) -> None:
    for stmt in (
        "IF WS-CODE NOT = 'AUTO' MOVE 'Y' TO WS-R END-IF",
        "IF WS-CODE <> 'AUTO' MOVE 'Y' TO WS-R END-IF",
        "IF WS-N NOT > 5 MOVE 'Y' TO WS-R END-IF",
        "IF WS-N NOT <= 5 MOVE 'Y' TO WS-R END-IF",
    ):
        result = _analyse(_program(stmt), tmp_path)
        assert result.syntax_diagnostics == [], stmt


# ===========================================================================
# 3. Compound conditions: NOT= / <> in AND/OR-joined terms
# ===========================================================================


def test_not_equal_inside_a_compound_and_condition() -> None:
    program = _parse(
        _program("IF WS-CODE NOT = 'AUTO' AND WS-N NOT = 5 MOVE 'Y' TO WS-R END-IF")
    )
    stmt = _if_stmt(program)
    assert stmt.condition_operator == "<>"
    assert len(stmt.extra_conditions) == 1
    term = stmt.extra_conditions[0]
    assert term.connector == "AND"
    assert term.left == "WS-N"
    assert term.operator == "<>"
    assert term.right == "5"


def test_not_equal_mixed_with_an_ordinary_or_term() -> None:
    program = _parse(
        _program("IF WS-CODE <> 'AUTO' OR WS-N > 3 MOVE 'Y' TO WS-R END-IF")
    )
    stmt = _if_stmt(program)
    assert stmt.condition_operator == "<>"
    assert stmt.extra_conditions[0].connector == "OR"
    assert stmt.extra_conditions[0].operator == ">"


def test_a_run_of_if_statements_is_not_disturbed_by_recovery(tmp_path) -> None:
    """Multiple consecutive data declarations / statements: the fix must not
    make parser recovery swallow a neighbouring, unrelated statement."""
    source = _program(
        "",
        procedure=(
            "       PROCEDURE DIVISION.\n"
            "       MAIN-PARA.\n"
            "           MOVE 'X' TO WS-R\n"
            "           IF WS-CODE NOT = 'AUTO'\n"
            "               MOVE 'Y' TO WS-R\n"
            "           END-IF\n"
            "           MOVE 'Z' TO WS-R\n"
            "           STOP RUN.\n"
        ),
    )
    result = _analyse(source, tmp_path)
    assert result.syntax_diagnostics == []
    kinds = [
        type(s).__name__ for s in result.ast.procedure_division.paragraphs[0].statements
    ]
    assert kinds == [
        "MoveStatementNode",
        "IfStatementNode",
        "MoveStatementNode",
        "StopRunStatementNode",
    ]


# ===========================================================================
# 4. Existing string/numeric/figurative literal forms are unaffected
# ===========================================================================


@pytest.mark.parametrize(
    ("stmt", "expected_operator"),
    [
        ("IF WS-CODE = 'AUTO' MOVE 'Y' TO WS-R END-IF", "="),
        ("IF WS-CODE != 'AUTO' MOVE 'Y' TO WS-R END-IF", "!="),
        ("IF WS-N > 3 MOVE 'Y' TO WS-R END-IF", ">"),
        ("IF WS-N >= 3 MOVE 'Y' TO WS-R END-IF", ">="),
        ("IF WS-N <= 3 MOVE 'Y' TO WS-R END-IF", "<="),
        ("IF WS-N < 3 MOVE 'Y' TO WS-R END-IF", "<"),
    ],
)
def test_ordinary_unnegated_comparisons_are_byte_for_byte_unchanged(
    stmt, expected_operator
) -> None:
    """Every form this grammar already accepted keeps the exact same
    condition_operator string it always produced (no aliasing, no negation)."""
    program = _parse(_program(stmt))
    assert _if_stmt(program).condition_operator == expected_operator


# ===========================================================================
# 5. The out-of-scope leading-NOT gap is untouched (regression guard)
# ===========================================================================


def test_leading_not_before_an_ordinary_condition_still_fails_the_same_way(
    tmp_path,
) -> None:
    """``IF NOT WS-N = 5`` (NOT before the *entire* condition, not between
    operand and operator) is a different, broader grammar rule
    (``condition ::= [NOT] simple-condition``) that ``_parse_condition_term``
    already -- and still -- deliberately leaves unconsumed for a non-condition
    -name operand. This stage must not touch it."""
    result = _analyse(_program("IF NOT WS-N = 5 MOVE 'Y' TO WS-R END-IF"), tmp_path)
    assert "SYN005" in _codes(result)
    assert any(
        "expected comparison operator in IF condition" in m for m in _messages(result)
    )


def test_leading_not_before_a_known_condition_name_is_still_handled_separately(
    tmp_path,
) -> None:
    """``IF NOT <condition-name>`` (Stage 24) is unaffected: it is a
    different sentinel path (``IS-FALSE``), not this stage's operator
    negation."""
    source = (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. NEGCMP.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        "       01  WS-CODE PIC X(1) VALUE 'D'.\n"
        "           88  IS-DEP VALUE 'D'.\n"
        "       01  WS-R PIC X(3) VALUE 'NO'.\n"
        "       PROCEDURE DIVISION.\n       MAIN-PARA.\n"
        "           IF NOT IS-DEP MOVE 'Y' TO WS-R END-IF\n"
        "           STOP RUN.\n"
    )
    result = _analyse(source, tmp_path)
    assert result.syntax_diagnostics == []
    java = result.java_source
    assert "!_cobolEquals" in java  # Stage 24's IS-FALSE translation, untouched


# ===========================================================================
# 6. Real corpus: every source that used ``NOT =`` now parses cleanly
# ===========================================================================

_AFFECTED_SOURCES = (
    "t_account_eligibility",
    "t_batch_acct_update",
    "t_insurance_claim",
    "t_payment_gateway",
)


def test_every_not_equal_occurrence_in_the_corpus_is_in_the_four_known_sources() -> (
    None
):
    """Confirms the corpus-impact claim directly, the same way every prior
    stage's survey did: search raw source text (code columns, comments
    excluded) for ``NOT =`` and ``<>``."""
    import re

    hits: dict[str, int] = {}
    for rec in load_training_corpus():
        n = 0
        for line in rec.source.splitlines():
            # Comment indicator column (7, i.e. index 6); the code itself is
            # free-format here and not truncated to column 72 -- account_
            # eligibility.cbl:33 alone runs to 92 characters.
            if len(line) > 6 and line[6] in "*/":
                continue
            code = line[7:] if len(line) > 7 else ""
            n += len(re.findall(r"\bNOT\s*=", code, re.I))
            n += code.count("<>")
        if n:
            hits[rec.source_id] = n
    assert set(hits) == set(_AFFECTED_SOURCES)
    assert hits["t_account_eligibility"] == 2  # a compound AND of two NOT= terms
    assert hits["t_batch_acct_update"] == 1
    assert hits["t_insurance_claim"] == 1
    assert hits["t_payment_gateway"] == 1


@pytest.mark.parametrize("source_id", _AFFECTED_SOURCES)
def test_real_affected_sources_no_longer_report_syn005(source_id) -> None:
    p = Path(f"data/sources/phase6-v2/{source_id.removeprefix('t_')}.cbl")
    result = AnalysisService().analyze_file(p)
    assert "SYN005" not in [str(d.code) for d in result.syntax_diagnostics], (
        source_id,
        [str(d.code) for d in result.syntax_diagnostics],
    )


def test_real_source_account_eligibility_produces_the_expected_ast() -> None:
    """``IF CITIZENSHIP-STATUS NOT = 'CITIZEN' AND CITIZENSHIP-STATUS NOT =
    'RESIDENT'`` (account_eligibility.cbl:33) -- the compound case, nested
    inside the ``ELSE`` of the paragraph's outer ``IF AGE < 18``."""
    p = Path("data/sources/phase6-v2/account_eligibility.cbl")
    result = AnalysisService().analyze_file(p)
    assert result.ast is not None and result.ast.procedure_division is not None
    ifs = [
        s
        for para in result.ast.procedure_division.paragraphs
        for s in _walk_if_statements(para.statements)
        if s.condition_left == "CITIZENSHIP-STATUS"
    ]
    (stmt,) = ifs
    assert stmt.condition_operator == "<>"
    assert stmt.condition_right == "'CITIZEN'"
    assert len(stmt.extra_conditions) == 1
    assert stmt.extra_conditions[0].operator == "<>"
    assert stmt.extra_conditions[0].right == "'RESIDENT'"


def test_sources_unaffected_by_this_stage_are_untouched() -> None:
    """A source with no ``NOT =``/``<>`` gets an identical AST-item count and
    zero new syntax diagnostics from this change (spot check; the full
    per-source fingerprint comparison is done outside pytest, see
    docs/MMIM_NEGATED_COMPARISON_FIX.md)."""
    p = Path("data/sources/phase6-v2/goto_spaghetti.cbl")
    result = AnalysisService().analyze_file(p)
    assert "SYN005" not in [str(d.code) for d in result.syntax_diagnostics]
