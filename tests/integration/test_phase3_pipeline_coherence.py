"""
Phase 3 pipeline coherence regression (post-#111 review).

Confirms that the IR builder (#109), the control-flow-graph generator
(#110), and the dependency analyzer (#111) do not disagree with each
other about the same PERFORM statement: it must be represented as a
PERFORM everywhere, never silently reinterpreted as a CALL or dropped
by any one of the three layers.
"""

from __future__ import annotations

from app.analysis.dependencies.analyzer import DependencyAnalyzer
from app.analysis.dependencies.models import DependencyType
from app.analysis.models import AnalysisResult
from app.ir.builder import IRBuilder
from app.ir.instructions import IRCall
from app.modernization.flow.generator import generate_flow
from app.modernization.flow.models import EdgeType
from app.parser.lexer.lexer import CobolLexer
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.syntax.program_parser import ProgramParser

_SOURCE = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM WORKER-PARA.
       WORKER-PARA.
           DISPLAY "WORKING".
"""


def test_perform_semantics_agree_across_ir_cfg_and_dependencies() -> None:
    tokens = CobolLexer().tokenize(_SOURCE, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    ctx = SemanticAnalyzer().analyse(program)

    # --- IR layer (#109): the PERFORM lowers to an IRCall tagged PERFORM.
    ir = IRBuilder(context=ctx).build(program)
    block = ir.modules[0].functions[0].blocks[0]
    perform_calls = [
        i
        for i in block.instructions
        if isinstance(i, IRCall) and i.comment == "PERFORM"
    ]
    assert len(perform_calls) == 1
    assert perform_calls[0].target == "WORKER-PARA"

    # --- CFG layer (#110): the same PERFORM produces a PERFORMS edge,
    # never a CALLS/external edge.
    result = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=True,
        dependencies=[],
        ast=program,
        ir=ir,
    )
    flow = generate_flow(result)
    performs_edges = [e for e in flow.edges if e.edge_type == EdgeType.PERFORMS]
    assert len(performs_edges) == 1
    assert not any(e.edge_type == EdgeType.CALLS for e in flow.edges)

    # --- Dependency layer (#111): the same PERFORM produces a PERFORM
    # dependency, never a CALL dependency.
    deps = DependencyAnalyzer().analyze(program)
    perform_deps = [d for d in deps if d.type == DependencyType.PERFORM]
    call_deps = [d for d in deps if d.type == DependencyType.CALL]
    assert len(perform_deps) == 1
    assert perform_deps[0].target == "WORKER-PARA"
    assert call_deps == []
