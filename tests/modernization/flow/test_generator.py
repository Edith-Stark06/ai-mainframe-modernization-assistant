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

    n_ext = next(n for n in flow.nodes if n.id == "ext_EXT1")
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


def test_cross_module_calls() -> None:
    call_inst = IRCall(target="SUB1")
    bb1 = IRBasicBlock(label="L1", instructions=(call_inst,))
    func1 = IRFunction(name="MAIN", blocks=(bb1,))
    mod1 = IRModule(name="MOD_A", functions=(func1,))

    bb2 = IRBasicBlock(label="L2", instructions=())
    func2 = IRFunction(name="SUB1", blocks=(bb2,))
    mod2 = IRModule(name="MOD_B", functions=(func2,))

    prog = IRProgram(name="PROG1", modules=(mod1, mod2))

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

    assert len(flow.edges) == 1
    assert flow.edges[0].source_id == "fn_MOD_A_MAIN"
    assert flow.edges[0].target_id == "fn_MOD_B_SUB1"


def test_deterministic_flow_hash() -> None:
    func1 = IRFunction(name="MAIN", blocks=())
    mod1 = IRModule(name="MOD_A", functions=(func1,))
    prog1 = IRProgram(name="PROG1", modules=(mod1,))

    res1 = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=True,
        dependencies=[],
        error=None,
        ast=None,
        ir=prog1,
    )
    flow1 = generate_flow(res1)
    flow2 = generate_flow(res1)

    assert flow1.id == flow2.id

    mod2 = IRModule(name="MOD_B", functions=(func1,))
    prog2 = IRProgram(name="PROG1", modules=(mod2,))
    res2 = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=True,
        dependencies=[],
        error=None,
        ast=None,
        ir=prog2,
    )
    flow3 = generate_flow(res2)

    # Different module structure -> different flow ID
    assert flow1.id != flow3.id


def test_ambiguous_cross_module_calls() -> None:
    # MAIN in MOD_C calls SUB1
    call_inst = IRCall(target="SUB1")
    bb1 = IRBasicBlock(label="L1", instructions=(call_inst,))
    func1 = IRFunction(name="MAIN", blocks=(bb1,))
    mod_c = IRModule(name="MOD_C", functions=(func1,))

    # SUB1 in MOD_A
    func2 = IRFunction(name="SUB1", blocks=())
    mod_a = IRModule(name="MOD_A", functions=(func2,))

    # SUB1 in MOD_B
    func3 = IRFunction(name="SUB1", blocks=())
    mod_b = IRModule(name="MOD_B", functions=(func3,))

    prog = IRProgram(name="PROG1", modules=(mod_a, mod_b, mod_c))

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

    # Since SUB1 is ambiguous (no qualification), it should fallback to EXTERNAL
    assert len(flow.edges) == 1
    edge = flow.edges[0]
    assert edge.source_id == "fn_MOD_C_MAIN"
    assert edge.target_id == "ext_SUB1"

    n_ext = next((n for n in flow.nodes if n.id == "ext_SUB1"), None)
    assert n_ext is not None
    assert n_ext.node_type == NodeType.EXTERNAL


def test_qualified_ambiguous_cross_module_calls() -> None:
    # MAIN in MOD_C calls MOD_B.SUB1
    call_inst = IRCall(target="MOD_B.SUB1")
    bb1 = IRBasicBlock(label="L1", instructions=(call_inst,))
    func1 = IRFunction(name="MAIN", blocks=(bb1,))
    mod_c = IRModule(name="MOD_C", functions=(func1,))

    # SUB1 in MOD_A
    func2 = IRFunction(name="SUB1", blocks=())
    mod_a = IRModule(name="MOD_A", functions=(func2,))

    # SUB1 in MOD_B
    func3 = IRFunction(name="SUB1", blocks=())
    mod_b = IRModule(name="MOD_B", functions=(func3,))

    prog = IRProgram(name="PROG1", modules=(mod_a, mod_b, mod_c))

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

    # Since it's qualified as MOD_B.SUB1, it should resolve correctly to fn_MOD_B_SUB1
    assert len(flow.edges) == 1
    edge = flow.edges[0]
    assert edge.source_id == "fn_MOD_C_MAIN"
    assert edge.target_id == "fn_MOD_B_SUB1"

    n_resolved = next((n for n in flow.nodes if n.id == "fn_MOD_B_SUB1"), None)
    assert n_resolved is not None
    assert n_resolved.node_type == NodeType.PROCESS
