"""
Unit tests for the Dependency Analyzer.
"""

from app.analysis.dependencies.models import DependencyType
from app.analysis.dependencies.analyzer import DependencyAnalyzer
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.program_parser import ProgramParser


def get_dependencies(source: str):
    """Helper to lex, parse, and analyze source."""
    lexer = CobolLexer()
    tokens = lexer.tokenize(source, filename="test.cbl")
    parser = ProgramParser()
    program_node = parser.parse(tokens)

    analyzer = DependencyAnalyzer()
    return analyzer.analyze(program_node)


def test_call_dependency():
    """
    Test extraction of CALL statements.
    Note that the AST preserves quotes around literal targets,
    and the DependencyAnalyzer intentionally preserves this representation
    as per repository conventions.
    """
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL 'BONUSMOD'
           CALL BONUSMOD2.
    """
    deps = get_dependencies(source)
    assert len(deps) == 2

    assert deps[0].type == DependencyType.CALL
    assert deps[0].target == "'BONUSMOD'"

    assert deps[1].type == DependencyType.CALL
    assert deps[1].target == "BONUSMOD2"


def test_perform_dependency():
    """
    Test extraction of PERFORM statements, including nested
    statements inside a PERFORM UNTIL block supported by the AST.
    """
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM CALCULATE-BONUS
           PERFORM UNTIL WS-DONE = 'Y'
               PERFORM DO-WORK
           END-PERFORM.
    """
    deps = get_dependencies(source)

    assert len(deps) == 2

    assert deps[0].type == DependencyType.PERFORM
    assert deps[0].target == "CALCULATE-BONUS"

    assert deps[1].type == DependencyType.PERFORM
    assert deps[1].target == "DO-WORK"


def test_duplicate_dependency_handling():
    """
    Test that duplicate dependencies are deterministically deduplicated,
    preserving the source location of the first occurrence.
    """
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL BONUSMOD
           CALL BONUSMOD
           PERFORM WORK
           PERFORM WORK.
    """
    deps = get_dependencies(source)
    assert len(deps) == 2

    assert deps[0].type == DependencyType.CALL
    assert deps[0].target == "BONUSMOD"
    assert deps[0].source_location.line == 6

    assert deps[1].type == DependencyType.PERFORM
    assert deps[1].target == "WORK"
    assert deps[1].source_location.line == 8


def test_no_dependencies():
    """Test a program with no dependencies."""
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY "HELLO"
           STOP RUN.
    """
    deps = get_dependencies(source)
    assert len(deps) == 0


def test_multiple_dependencies():
    """Test multiple different dependencies in multiple paragraphs."""
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM INIT-RTN
           CALL SUBPROG.
       INIT-RTN.
           DISPLAY "INIT".
    """
    deps = get_dependencies(source)
    assert len(deps) == 2

    assert deps[0].type == DependencyType.PERFORM
    assert deps[0].target == "INIT-RTN"

    assert deps[1].type == DependencyType.CALL
    assert deps[1].target == "SUBPROG"


def test_source_location_preserved():
    """Test that source locations are correctly preserved."""
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL BONUSMOD.
    """
    deps = get_dependencies(source)
    assert len(deps) == 1
    dep = deps[0]
    assert dep.source_location is not None
    assert dep.source_location.line == 6
    assert dep.source_location.column == 12


def test_if_statement_nested():
    """Test dependency extraction from inside an IF statement's THEN and ELSE branches."""
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF X = Y
               CALL SUB1
           ELSE
               PERFORM PARA1
           END-IF.
    """
    deps = get_dependencies(source)

    assert len(deps) == 2

    assert deps[0].type == DependencyType.CALL
    assert deps[0].target == "SUB1"

    assert deps[1].type == DependencyType.PERFORM
    assert deps[1].target == "PARA1"


def test_copy_dependency_not_extractable_from_current_ast():
    """
    COPY is currently not represented as an extractable dependency in the AST.

    DependencyAnalyzer must not fabricate a DependencyType.COPY dependency.
    The current source therefore produces no extracted dependencies.
    """
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           COPY EMPFILE.
    """

    lexer = CobolLexer()
    tokens = lexer.tokenize(source, filename="test.cbl")
    parser = ProgramParser()
    program_node = parser.parse(tokens)

    analyzer = DependencyAnalyzer()
    deps = analyzer.analyze(program_node)

    assert len(deps) == 0


def test_analyzer_reuse():
    """Test that DependencyAnalyzer can be reused and its internal state resets."""
    analyzer = DependencyAnalyzer()

    source1 = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST1.
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL 'PROG1'.
    """
    lexer1 = CobolLexer()
    tokens1 = lexer1.tokenize(source1, filename="test1.cbl")
    parser1 = ProgramParser()
    program1 = parser1.parse(tokens1)

    deps1 = analyzer.analyze(program1)
    assert len(deps1) == 1
    assert deps1[0].target == "'PROG1'"

    source2 = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST2.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM INIT-RTN.
    """
    lexer2 = CobolLexer()
    tokens2 = lexer2.tokenize(source2, filename="test2.cbl")
    parser2 = ProgramParser()
    program2 = parser2.parse(tokens2)

    deps2 = analyzer.analyze(program2)
    assert len(deps2) == 1
    assert deps2[0].target == "INIT-RTN"
