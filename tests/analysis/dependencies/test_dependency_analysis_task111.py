"""
Task #111 -- Dependency Analysis regression suite.

Covers requirements not already exercised by ``test_analyzer.py``:
variable read/write extraction, condition-dependency scoping,
transitive dependency queries, and -- critically -- false-positive
protection (dependency analysis must never invent a relationship that
isn't actually present in the AST).
"""

from __future__ import annotations

from pathlib import Path

from app.analysis.dependencies.analyzer import (
    DependencyAnalyzer,
    compute_transitive_dependencies,
    is_literal_operand,
)
from app.analysis.dependencies.models import Dependency, DependencyType
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.program_parser import ProgramParser

COMPLEX_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "workspace"
    / "2e87036d-b90e-488f-b199-3162eb7c1c7e"
    / "complex_acctbatch.cbl"
)


def get_dependencies(source: str) -> list[Dependency]:
    lexer = CobolLexer()
    tokens = lexer.tokenize(source, filename="test.cbl")
    parser = ProgramParser()
    program_node = parser.parse(tokens)
    return DependencyAnalyzer().analyze(program_node)


# ----------------------------------------------------------------------
# Variable read/write dependencies
# ----------------------------------------------------------------------


def test_move_extracts_read_and_write():
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE WS-SOURCE TO WS-TARGET.
    """
    deps = get_dependencies(source)
    assert len(deps) == 2

    reads = [d for d in deps if d.type == DependencyType.VARIABLE_READ]
    writes = [d for d in deps if d.type == DependencyType.VARIABLE_WRITE]
    assert {d.target for d in reads} == {"WS-SOURCE"}
    assert {d.target for d in writes} == {"WS-TARGET"}


def test_move_literal_source_is_not_a_variable_dependency():
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE "HELLO" TO WS-TARGET.
    """
    deps = get_dependencies(source)
    assert len(deps) == 1
    assert deps[0].type == DependencyType.VARIABLE_WRITE
    assert deps[0].target == "WS-TARGET"


def test_move_numeric_literal_source_is_not_a_variable_dependency():
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE 42 TO WS-COUNT.
    """
    deps = get_dependencies(source)
    assert len(deps) == 1
    assert deps[0].type == DependencyType.VARIABLE_WRITE
    assert deps[0].target == "WS-COUNT"


def test_add_extracts_read_of_both_operands_and_write_of_accumulator():
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           ADD WS-A TO WS-B.
    """
    deps = get_dependencies(source)

    reads = {d.target for d in deps if d.type == DependencyType.VARIABLE_READ}
    writes = {d.target for d in deps if d.type == DependencyType.VARIABLE_WRITE}
    assert reads == {"WS-A", "WS-B"}
    assert writes == {"WS-B"}


def test_arithmetic_with_numeric_literal_operand_does_not_fabricate_variable():
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           ADD 1 TO WS-COUNTER.
    """
    deps = get_dependencies(source)
    targets = {d.target for d in deps}
    assert "1" not in targets
    assert targets == {"WS-COUNTER"}


# ----------------------------------------------------------------------
# Condition-dependency scoping: only variables actually referenced in
# the condition are captured -- never every variable lexically nearby
# in the paragraph.
# ----------------------------------------------------------------------


def test_if_condition_dependency_does_not_leak_unrelated_paragraph_variables():
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE WS-UNRELATED-1 TO WS-UNRELATED-2
           IF WS-FLAG = 'Y'
               MOVE WS-OTHER-1 TO WS-OTHER-2
           END-IF.
    """
    deps = get_dependencies(source)
    condition_targets = {d.target for d in deps if d.type == DependencyType.CONDITION}
    assert condition_targets == {"WS-FLAG"}
    # The unrelated MOVE operands must never be reported as CONDITION
    # dependencies just because they sit in the same paragraph.
    assert "WS-UNRELATED-1" not in condition_targets
    assert "WS-UNRELATED-2" not in condition_targets
    assert "WS-OTHER-1" not in condition_targets
    assert "WS-OTHER-2" not in condition_targets


def test_perform_until_condition_literal_operand_excluded():
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM UNTIL WS-DONE = 'Y'
               DISPLAY "LOOPING"
           END-PERFORM.
    """
    deps = get_dependencies(source)
    condition_targets = {d.target for d in deps if d.type == DependencyType.CONDITION}
    assert condition_targets == {"WS-DONE"}
    assert "Y" not in condition_targets
    assert "'Y'" not in condition_targets


# ----------------------------------------------------------------------
# False-positive protection (task #111: "this is critical")
# ----------------------------------------------------------------------


def test_unrelated_variables_in_different_paragraphs_are_not_connected():
    """
    Two paragraphs that each touch their own, differently-named
    variables must never produce a dependency crossing between them --
    dependency extraction is not supposed to relate variables that
    merely coexist in the same program.
    """
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       FIRST-PARA.
           MOVE WS-ALPHA TO WS-BETA.
       SECOND-PARA.
           MOVE WS-GAMMA TO WS-DELTA.
    """
    deps = get_dependencies(source)

    first_targets = {d.target for d in deps if d.source == "FIRST-PARA"}
    second_targets = {d.target for d in deps if d.source == "SECOND-PARA"}

    assert first_targets == {"WS-ALPHA", "WS-BETA"}
    assert second_targets == {"WS-GAMMA", "WS-DELTA"}
    # No dependency should ever claim FIRST-PARA relates to WS-GAMMA/
    # WS-DELTA or SECOND-PARA relates to WS-ALPHA/WS-BETA.
    assert not (first_targets & {"WS-GAMMA", "WS-DELTA"})
    assert not (second_targets & {"WS-ALPHA", "WS-BETA"})


def test_unrelated_paragraphs_are_not_connected_without_perform_or_call():
    """
    Two sequential paragraphs with no PERFORM/CALL between them must
    not produce any PERFORM/CALL dependency linking them -- physical
    (lexical) adjacency in the source is not a dependency.
    """
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       FIRST-PARA.
           DISPLAY "FIRST".
       SECOND-PARA.
           DISPLAY "SECOND".
    """
    deps = get_dependencies(source)
    assert len(deps) == 0


def test_arbitrary_literals_never_become_variable_dependencies():
    assert is_literal_operand('"A STRING"') is True
    assert is_literal_operand("'ANOTHER'") is True
    assert is_literal_operand("123") is True
    assert is_literal_operand("-123") is True
    assert is_literal_operand("+12.5") is True
    assert is_literal_operand("0") is True
    # Real identifiers are never misclassified as literals.
    assert is_literal_operand("WS-FIELD") is False
    assert is_literal_operand("WS-FIELD-1") is False


def test_string_resembling_program_name_only_becomes_call_dependency_via_real_call_statement():
    """
    A quoted literal that merely *looks like* a program name must not
    be turned into a fabricated CALL dependency unless it genuinely
    appears as the target of a real CALL statement. Here it appears
    only inside a DISPLAY, which the analyzer does not treat as a call.
    """
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY "SUBPROG".
    """
    deps = get_dependencies(source)
    assert len(deps) == 0
    assert not any(d.type == DependencyType.CALL for d in deps)


def test_lexical_proximity_does_not_create_dependency():
    """
    A MOVE immediately followed by an unrelated CALL must not cause the
    MOVE's operands to be conflated with the CALL's target -- each
    statement's dependencies are derived strictly from its own operands.
    """
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE WS-X TO WS-Y
           CALL SUBPROG.
    """
    deps = get_dependencies(source)
    call_deps = [d for d in deps if d.type == DependencyType.CALL]
    assert len(call_deps) == 1
    assert call_deps[0].target == "SUBPROG"
    # WS-X/WS-Y must never appear as CALL dependencies, and SUBPROG
    # must never appear as a VARIABLE_READ/VARIABLE_WRITE dependency.
    assert not any(
        d.target == "SUBPROG"
        and d.type in (DependencyType.VARIABLE_READ, DependencyType.VARIABLE_WRITE)
        for d in deps
    )
    assert not any(
        d.type == DependencyType.CALL and d.target in ("WS-X", "WS-Y") for d in deps
    )


def test_unsupported_display_statement_produces_no_fabricated_dependency():
    """
    DISPLAY has no dedicated dependency-extraction visitor method (it
    carries no meaningful dependency information); it must be silently
    skipped rather than producing a guessed dependency of any kind.
    """
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY WS-SOMETHING.
    """
    deps = get_dependencies(source)
    assert len(deps) == 0


def test_file_dependencies_are_not_fabricated():
    """
    OPEN/CLOSE/READ/WRITE file operations have no AST representation
    (per the #105/#108 parser audit); the analyzer must not invent a
    file dependency out of thin air just because such statements are
    common in real COBOL. Since these statements cannot even be parsed
    into the AST today, using ordinary COBOL statements confirms no
    file-shaped dependency leaks out of unrelated constructs either.
    """
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE WS-A TO WS-B
           PERFORM WRITE-RECORD.
       WRITE-RECORD.
           DISPLAY "WRITING".
    """
    deps = get_dependencies(source)
    assert not any(d.target in ("FILE", "RECORD") for d in deps)
    # No DependencyType value for file dependencies exists at all --
    # confirming the type enum itself carries no fabricated category.
    assert not hasattr(DependencyType, "FILE")


def test_business_rule_dependencies_are_not_emitted():
    """
    Business-rule dependency extraction is task #112's concern. #111's
    analyzer must never emit a DependencyType outside its own
    documented set, regardless of how "rule-like" the source looks.
    """
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       VALIDATE-ELIGIBILITY.
           IF WS-AGE = 18
               MOVE 'Y' TO WS-ELIGIBLE
           END-IF.
    """
    deps = get_dependencies(source)
    allowed_types = {
        DependencyType.COPY,
        DependencyType.CALL,
        DependencyType.PERFORM,
        DependencyType.VARIABLE_READ,
        DependencyType.VARIABLE_WRITE,
        DependencyType.CONDITION,
    }
    assert all(d.type in allowed_types for d in deps)


# ----------------------------------------------------------------------
# Transitive dependency queries
# ----------------------------------------------------------------------


def test_transitive_perform_chain_is_discovered():
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM SECOND-PARA.
       SECOND-PARA.
           PERFORM THIRD-PARA.
       THIRD-PARA.
           DISPLAY "DONE".
    """
    deps = get_dependencies(source)

    direct = {d.target for d in deps if d.source == "MAIN-PARA"}
    assert direct == {"SECOND-PARA"}

    transitive = compute_transitive_dependencies(deps, "MAIN-PARA")
    assert transitive == {"SECOND-PARA", "THIRD-PARA"}


def test_transitive_query_does_not_mutate_direct_dependency_list():
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM SECOND-PARA.
       SECOND-PARA.
           PERFORM THIRD-PARA.
       THIRD-PARA.
           DISPLAY "DONE".
    """
    deps = get_dependencies(source)
    before = list(deps)

    compute_transitive_dependencies(deps, "MAIN-PARA")

    assert deps == before
    assert len(deps) == len(before)


def test_transitive_query_handles_cycles_without_infinite_traversal():
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM SECOND-PARA.
       SECOND-PARA.
           PERFORM MAIN-PARA.
    """
    deps = get_dependencies(source)

    transitive = compute_transitive_dependencies(deps, "MAIN-PARA")
    # Must terminate and correctly discover the cycle without hanging.
    assert transitive == {"SECOND-PARA", "MAIN-PARA"}


def test_transitive_query_from_unknown_start_returns_empty_set():
    deps = [
        Dependency(
            type=DependencyType.PERFORM,
            target="B",
            source="A",
        )
    ]
    assert compute_transitive_dependencies(deps, "NOT-A-REAL-PARAGRAPH") == set()


def test_transitive_query_excludes_variable_and_condition_edges_by_default():
    """
    Transitive reachability follows PERFORM/CALL control-transfer edges
    only; a paragraph merely reading/writing a variable that another
    paragraph also happens to read/write must not be treated as a
    transitive dependency chain.
    """
    deps = [
        Dependency(type=DependencyType.PERFORM, target="B", source="A"),
        Dependency(type=DependencyType.VARIABLE_WRITE, target="WS-X", source="B"),
        Dependency(type=DependencyType.VARIABLE_READ, target="WS-X", source="C"),
        Dependency(type=DependencyType.PERFORM, target="C", source="WS-X"),
    ]
    transitive = compute_transitive_dependencies(deps, "A")
    assert transitive == {"B"}
    assert "C" not in transitive
    assert "WS-X" not in transitive


def test_transitive_query_can_include_call_edges():
    deps = [
        Dependency(type=DependencyType.PERFORM, target="B", source="A"),
        Dependency(type=DependencyType.CALL, target="EXTPROG", source="B"),
    ]
    transitive = compute_transitive_dependencies(deps, "A")
    assert transitive == {"B", "EXTPROG"}


# ----------------------------------------------------------------------
# Complex fixture validation
# ----------------------------------------------------------------------


def test_complex_fixture_dependency_metrics():
    """
    Drives the real ~500-line complex fixture through the full
    lexer -> parser -> DependencyAnalyzer pipeline and reports the
    metrics required by task #111. This is a smoke/regression test:
    it asserts internal consistency (every bucket only contains its
    own DependencyType, edges are all attributable to a real
    paragraph) rather than fixed magic counts, so it stays valid as
    the fixture or parser coverage evolves.
    """
    source = COMPLEX_FIXTURE.read_text(encoding="utf-8")
    deps = get_dependencies(source)

    by_type: dict[DependencyType, list[Dependency]] = {}
    for dep in deps:
        by_type.setdefault(dep.type, []).append(dep)

    total = len(deps)
    variable_deps = len(by_type.get(DependencyType.VARIABLE_READ, [])) + len(
        by_type.get(DependencyType.VARIABLE_WRITE, [])
    )
    read_deps = len(by_type.get(DependencyType.VARIABLE_READ, []))
    write_deps = len(by_type.get(DependencyType.VARIABLE_WRITE, []))
    perform_deps = len(by_type.get(DependencyType.PERFORM, []))
    call_deps = len(by_type.get(DependencyType.CALL, []))
    condition_deps = len(by_type.get(DependencyType.CONDITION, []))
    copy_deps = len(by_type.get(DependencyType.COPY, []))

    # Sanity: every extracted dependency belongs to a real paragraph
    # that the analyzer actually visited (never "" / unattributed).
    assert all(d.source for d in deps)

    # Every dependency's target must be a non-empty string -- no
    # fabricated blank/placeholder targets.
    assert all(d.target.strip() for d in deps)

    # Report (visible in -s / captured output for manual inspection).
    print("\n--- Task #111 complex fixture dependency metrics ---")
    print(f"Total dependency edges:        {total}")
    print(f"Variable dependencies:         {variable_deps}")
    print(f"  read:                        {read_deps}")
    print(f"  write:                       {write_deps}")
    print(f"Paragraph (PERFORM) deps:      {perform_deps}")
    print(f"External program (CALL) deps:  {call_deps}")
    print("File dependencies:             0 (no AST representation)")
    print(f"Condition dependencies:        {condition_deps}")
    print(f"COPY dependencies:             {copy_deps} (no AST representation -> 0)")
    print("Business-rule dependencies:    0 (by design, task #112)")

    # This fixture is known (from tasks #109/#110) to contain real
    # PERFORM and IF/PERFORM-UNTIL condition usage, so these buckets
    # must be non-trivially populated -- guards against a silent
    # extraction regression.
    assert perform_deps > 0
    assert condition_deps > 0
    assert variable_deps > 0

    # COPY has no AST representation; must never be fabricated.
    assert copy_deps == 0

    # Transitive reachability from the fixture's entry paragraph must
    # terminate and be a superset of its direct PERFORM targets.
    lexer = CobolLexer()
    tokens = lexer.tokenize(source, filename="complex_acctbatch.cbl")
    parser = ProgramParser()
    program_node = parser.parse(tokens)
    first_paragraph = program_node.procedure_division.paragraphs[0].name

    direct_performs = {
        d.target
        for d in deps
        if d.source == first_paragraph and d.type == DependencyType.PERFORM
    }
    transitive = compute_transitive_dependencies(deps, first_paragraph)
    assert direct_performs <= transitive
    print(f"Transitive relationships from entry paragraph: {len(transitive)}")

    suspicious = [d for d in deps if is_literal_operand(d.target)]
    print(
        f"Suspicious/unresolved references (literal-looking targets): {len(suspicious)}"
    )
    assert suspicious == []
