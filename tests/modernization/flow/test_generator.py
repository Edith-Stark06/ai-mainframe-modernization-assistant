from app.analysis.models import AnalysisResult
from app.modernization.flow.generator import generate_flow
from app.modernization.flow.models import NodeType, EdgeType
from app.ir.program import IRProgram, IRModule, IRFunction
from app.ir.blocks import IRBasicBlock
from app.ir.instructions import IRCall


def test_generate_flow_empty() -> None:
    result = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=False,
        dependencies=[],
        error=None,
        ast=None,
        ir=None,
    )
    flow = generate_flow(result)
    assert flow.name == "Unknown Program"
    assert len(flow.nodes) == 0
    assert len(flow.edges) == 0


def test_generate_flow_with_functions_and_calls() -> None:
    call_inst = IRCall(target="SUB1")
    bb1 = IRBasicBlock(label="L1", instructions=(call_inst,))
    func1 = IRFunction(name="MAIN", blocks=(bb1,))

    bb2 = IRBasicBlock(label="L2", instructions=())
    func2 = IRFunction(name="SUB1", blocks=(bb2,))

    mod = IRModule(name="MOD1", functions=(func1, func2))
    prog = IRProgram(name="PROG1", modules=(mod,))

    result = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=True,
        dependencies=[],
        error=None,
        ast=None,
        ir=prog,
    )

    flow = generate_flow(result)
    assert flow.name == "PROG1"

    # Expected 2 nodes: MAIN, SUB1
    assert len(flow.nodes) == 2
    # They should be sorted by id (fn_MOD1_MAIN, fn_MOD1_SUB1)
    assert flow.nodes[0].id == "fn_MOD1_MAIN"
    assert flow.nodes[0].node_type == NodeType.PROCESS

    assert flow.nodes[1].id == "fn_MOD1_SUB1"
    assert flow.nodes[1].node_type == NodeType.PROCESS

    assert len(flow.edges) == 1
    edge = flow.edges[0]
    assert edge.source_id == "fn_MOD1_MAIN"
    assert edge.target_id == "fn_MOD1_SUB1"
    assert edge.edge_type == EdgeType.CALLS


def test_generate_flow_with_external_call() -> None:
    call_inst = IRCall(target="EXT1")
    bb1 = IRBasicBlock(label="L1", instructions=(call_inst,))
    func1 = IRFunction(name="MAIN", blocks=(bb1,))

    mod = IRModule(name="MOD1", functions=(func1,))
    prog = IRProgram(name="PROG1", modules=(mod,))

    result = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=True,
        dependencies=[],
        error=None,
        ast=None,
        ir=prog,
    )

    flow = generate_flow(result)

    # Expected 2 nodes: MAIN (PROCESS), EXT1 (EXTERNAL)
    assert len(flow.nodes) == 2

    n_ext = next(n for n in flow.nodes if n.id == "fn_MOD1_EXT1")
    assert n_ext.node_type == NodeType.EXTERNAL

    n_main = next(n for n in flow.nodes if n.id == "fn_MOD1_MAIN")
    assert n_main.node_type == NodeType.PROCESS


def test_duplicate_calls_prevented() -> None:
    # 3 identical calls to SUB1
    call_inst1 = IRCall(target="SUB1")
    call_inst2 = IRCall(target="SUB1")
    call_inst3 = IRCall(target="SUB1")
    bb1 = IRBasicBlock(label="L1", instructions=(call_inst1, call_inst2, call_inst3))
    func1 = IRFunction(name="MAIN", blocks=(bb1,))

    bb2 = IRBasicBlock(label="L2", instructions=())
    func2 = IRFunction(name="SUB1", blocks=(bb2,))

    mod = IRModule(name="MOD1", functions=(func1, func2))
    prog = IRProgram(name="PROG1", modules=(mod,))

    result = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=True,
        dependencies=[],
        error=None,
        ast=None,
        ir=prog,
    )

    flow = generate_flow(result)

    # We should only have 1 CALLS edge representing the relationship
    assert len(flow.edges) == 1
    assert flow.edges[0].source_id == "fn_MOD1_MAIN"
    assert flow.edges[0].target_id == "fn_MOD1_SUB1"
