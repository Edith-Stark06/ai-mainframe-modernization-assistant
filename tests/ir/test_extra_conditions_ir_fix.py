"""``IfStatementNode.extra_conditions`` in the IR layer.

The parser records ``IF WS-A > 5 OR WS-B = 2`` as the first comparison plus
``extra_conditions``; ``IRBuilder.build_if_statement`` used to lower only the
first comparison into ``IRIf``, silently losing every further term (and with
it the ``AND``/``OR`` semantics). ``IRIf`` now carries ``extra_terms`` (an
``IRConditionTerm`` per extra term, same connector/order as the AST), the
serialized IR emits them only when present (a plain IF serializes exactly as
before), the CFG decision label shows the whole condition, and the
PERFORM-UNTIL loop simulator refuses (rather than mis-evaluates) a compound IF.

The real-corpus tests run the real sources through the real pipeline.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.analysis.serializers.ir import serialize_ir
from app.analysis.service import AnalysisService
from app.behavioral.extraction.loops import _run_body
from app.ir.instructions import IRIf
from app.modernization.flow.generator import generate_flow

SOURCES = Path("data/sources/phase6-v2")

_HEADER = textwrap.dedent("""\
    IDENTIFICATION DIVISION.
    PROGRAM-ID. T.
    DATA DIVISION.
    WORKING-STORAGE SECTION.
    01 WS-A PIC 9(3) VALUE 0.
    01 WS-B PIC 9(3) VALUE 0.
    01 WS-C PIC 9(3) VALUE 0.
    01 WS-R PIC X(4) VALUE SPACE.
    01 WS-CODE PIC X VALUE SPACE.
        88 IS-OK VALUE 'A'.
    PROCEDURE DIVISION.
    MAIN.
""")


def _analyze(tmp_path, source: str):
    path = tmp_path / "t.cbl"
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(path)


def _analyze_if(tmp_path, condition: str):
    body = f"    IF {condition}\n        MOVE 'Y' TO WS-R\n    END-IF.\n    STOP RUN.\n"
    return _analyze(tmp_path, _HEADER + body)


def _ifs(result) -> list[IRIf]:
    return [
        i
        for module in result.ir.modules
        for fn in module.functions
        for block in fn.blocks
        for i in block.instructions
        if isinstance(i, IRIf)
    ]


def _terms(node: IRIf) -> list[tuple[str, str, str, str]]:
    return [(t.connector, t.left, t.operator, t.right) for t in node.extra_terms]


# --- 1. simple IF unchanged ---------------------------------------------


def test_simple_if_is_unchanged(tmp_path):
    (node,) = _ifs(_analyze_if(tmp_path, "WS-A > 5"))
    assert (node.left, node.operator, node.right) == ("WS-A", ">", "5")
    assert node.extra_terms == ()
    assert node.condition_text() == "WS-A > 5"


def test_simple_if_serializes_exactly_as_before(tmp_path):
    result = _analyze_if(tmp_path, "WS-A > 5")
    (dumped,) = [
        i
        for i in serialize_ir(result.ir)["modules"][0]["functions"][0]["blocks"][0][
            "instructions"
        ]
        if i["type"] == "IRIf"
    ]
    assert "extra_terms" not in dumped
    assert set(dumped) == {
        "type",
        "kind",
        "name",
        "result",
        "comment",
        "source_position",
        "paragraph",
        "left",
        "operator",
        "right",
    }


# --- 2-4. AND / OR / ordering -------------------------------------------


def test_and_extra_condition_survives_into_ir(tmp_path):
    (node,) = _ifs(_analyze_if(tmp_path, "WS-A > 5 AND WS-B = 2"))
    assert _terms(node) == [("AND", "WS-B", "=", "2")]
    assert node.condition_text() == "WS-A > 5 AND WS-B = 2"


def test_or_extra_condition_survives_into_ir(tmp_path):
    (node,) = _ifs(_analyze_if(tmp_path, "WS-A > 5 OR WS-B = 2"))
    assert _terms(node) == [("OR", "WS-B", "=", "2")]
    assert node.condition_text() == "WS-A > 5 OR WS-B = 2"


def test_multiple_extra_conditions_keep_connectors_and_order(tmp_path):
    (node,) = _ifs(_analyze_if(tmp_path, "WS-A > 5 AND WS-B = 2 OR WS-C < 3"))
    assert (node.left, node.operator, node.right) == ("WS-A", ">", "5")
    assert _terms(node) == [("AND", "WS-B", "=", "2"), ("OR", "WS-C", "<", "3")]
    assert node.condition_text() == "WS-A > 5 AND WS-B = 2 OR WS-C < 3"


def test_variable_and_decimal_operands_are_lowered_per_term(tmp_path):
    (node,) = _ifs(_analyze_if(tmp_path, "WS-A > WS-B OR WS-C < 0.25"))
    assert (node.left, node.operator, node.right) == ("WS-A", ">", "WS-B")
    assert _terms(node) == [("OR", "WS-C", "<", "0.25")]


def test_condition_name_terms_keep_is_true_is_false(tmp_path):
    (node,) = _ifs(_analyze_if(tmp_path, "IS-OK AND NOT IS-OK OR WS-A > 5"))
    assert (node.left, node.operator, node.right) == ("IS-OK", "IS-TRUE", "IS-OK")
    assert _terms(node) == [
        ("AND", "IS-OK", "IS-FALSE", "IS-OK"),
        ("OR", "WS-A", ">", "5"),
    ]


def test_nested_ifs_each_keep_their_own_terms(tmp_path):
    body = (
        "    IF WS-A > 5 OR WS-B = 2\n"
        "        IF WS-C = 1 AND WS-A < 9\n"
        "            MOVE 'Y' TO WS-R\n"
        "        END-IF\n"
        "    END-IF.\n    STOP RUN.\n"
    )
    outer, inner = _ifs(_analyze(tmp_path, _HEADER + body))
    assert _terms(outer) == [("OR", "WS-B", "=", "2")]
    assert _terms(inner) == [("AND", "WS-A", "<", "9")]


# --- serialization --------------------------------------------------------


def test_compound_if_serializes_its_extra_terms(tmp_path):
    result = _analyze_if(tmp_path, "WS-A > 5 OR WS-B = 2")
    (dumped,) = [
        i
        for i in serialize_ir(result.ir)["modules"][0]["functions"][0]["blocks"][0][
            "instructions"
        ]
        if i["type"] == "IRIf"
    ]
    assert dumped["extra_terms"] == [
        {
            "type": "IRConditionTerm",
            "connector": "OR",
            "left": "WS-B",
            "operator": "=",
            "right": "2",
        }
    ]


# --- CFG ------------------------------------------------------------------


def test_cfg_decision_label_shows_the_whole_condition(tmp_path):
    flow = generate_flow(_analyze_if(tmp_path, "WS-A > 5 OR WS-B = 2"))
    labels = [n.name for n in flow.nodes if n.name.startswith("IF ")]
    assert labels == ["IF WS-A > 5 OR WS-B = 2"]


def test_cfg_label_of_a_plain_if_is_unchanged(tmp_path):
    flow = generate_flow(_analyze_if(tmp_path, "WS-A > 5"))
    assert [n.name for n in flow.nodes if n.name.startswith("IF ")] == ["IF WS-A > 5"]


# --- PERFORM UNTIL loop simulator: fail safe --------------------------------

_MOVE = {"type": "IRMove", "source": "1", "result": "Y"}
_END = {"type": "IREndIf"}


def test_loop_simulator_still_interprets_a_plain_if():
    body = [{"type": "IRIf", "left": "X", "operator": ">", "right": "0"}, _MOVE, _END]
    assert _run_body(body, {"X": 5})["Y"] == 1


def test_loop_simulator_refuses_a_compound_if_instead_of_guessing():
    """Evaluating only the first term of ``X > 0 OR Z = 1`` would be wrong."""
    body = [
        {
            "type": "IRIf",
            "left": "X",
            "operator": ">",
            "right": "0",
            "extra_terms": [
                {
                    "type": "IRConditionTerm",
                    "connector": "OR",
                    "left": "Z",
                    "operator": "==",
                    "right": "1",
                }
            ],
        },
        _MOVE,
        _END,
    ]
    assert _run_body(body, {"X": 5, "Z": 1}) is None


# --- real corpus, real pipeline ---------------------------------------------

REAL_OR = [
    (
        "credit_approval.cbl",
        ("BANKRUPTCY-FLAG", "=", "Y"),
        ("OR", "CREDIT-SCORE", "<", "580"),
    ),
    (
        "daily_trans_report.cbl",
        ("FD-TX-VAL", ">", "10000.00"),
        ("OR", "FD-TX-SUSPICIOUS", "=", "Y"),
    ),
    ("insurance_claim.cbl", ("DRIVER-AGE", "<", "21"), ("OR", "DRIVER-AGE", ">", "75")),
    (
        "payment_gateway.cbl",
        ("AUTH-OUT-RESP-CODE", "=", " "),
        ("OR", "AUTH-OUT-RESP-CODE", "=", "000"),
    ),
    (
        "pricing_tier.cbl",
        ("PAYMENT-METHOD", "=", "ACH"),
        ("OR", "PAYMENT-METHOD", "=", "WIRE"),
    ),
]


def _bare(value: str) -> str:
    return value.strip("'\"")


@pytest.fixture(scope="module")
def real_results():
    cache: dict[str, object] = {}

    def load(filename: str):
        if filename not in cache:
            cache[filename] = AnalysisService().analyze_file(SOURCES / filename)
        return cache[filename]

    return load


@pytest.mark.parametrize(("filename", "first", "extra"), REAL_OR)
def test_real_or_condition_survives_into_ir(real_results, filename, first, extra):
    matches = []
    for node in _ifs(real_results(filename)):
        if (
            node.extra_terms
            and (
                node.left,
                node.operator,
                _bare(node.right),
            )
            == first
        ):
            matches.append(node)
    assert len(matches) == 1, f"{filename}: expected exactly one IRIf for {first}"
    (term,) = matches[0].extra_terms
    assert (term.connector, term.left, term.operator, _bare(term.right)) == extra


def test_real_condition_names_88_and_term_survives_into_ir(real_results):
    """``IF PHYSICAL-BRANCH AND TX-WITHDRAWAL`` (line 54)."""
    (node,) = [n for n in _ifs(real_results("condition_names_88.cbl")) if n.extra_terms]
    assert (node.left, node.operator, node.right) == (
        "PHYSICAL-BRANCH",
        "IS-TRUE",
        "PHYSICAL-BRANCH",
    )
    assert _terms(node) == [("AND", "TX-WITHDRAWAL", "IS-TRUE", "TX-WITHDRAWAL")]


def test_real_ir_extra_terms_match_the_ast_one_for_one(real_results):
    """AST-driven, no hand-written expectation: for the 8 audited sources every
    ``extra_conditions`` term of every IF appears, in order, on some IRIf."""
    sources = [
        "account_eligibility.cbl",
        "condition_names_88.cbl",
        "credit_approval.cbl",
        "daily_trans_report.cbl",
        "insurance_claim.cbl",
        "mortgage_service.cbl",
        "payment_gateway.cbl",
        "pricing_tier.cbl",
    ]
    total = 0
    for filename in sources:
        result = real_results(filename)
        ast_terms: list[list[tuple[str, str, str, str]]] = []

        def walk(stmts):
            for s in stmts:
                if s.__class__.__name__ == "IfStatementNode":
                    if s.extra_conditions:
                        ast_terms.append(
                            [
                                (t.connector, t.left, t.operator, _bare(t.right))
                                for t in s.extra_conditions
                            ]
                        )
                    walk(s.then_statements)
                    walk(s.else_statements)

        for para in result.ast.procedure_division.paragraphs:
            walk(para.statements)
        ir_terms = [
            [(t.connector, t.left, t.operator, _bare(t.right)) for t in n.extra_terms]
            for n in _ifs(result)
            if n.extra_terms
        ]
        assert ir_terms == ast_terms, filename
        total += len(ast_terms)
    # 11 -> 12 (task #stage25): account_eligibility.cbl's compound
    # ``IF CITIZENSHIP-STATUS NOT = 'CITIZEN' AND CITIZENSHIP-STATUS NOT =
    # 'RESIDENT'`` used to fail to parse at all (dropped by recovery, so
    # neither term existed on the AST or the IR); now it does, and the
    # ``ir_terms == ast_terms`` check above already proves the new term is
    # represented identically on both sides.
    assert total == 12
