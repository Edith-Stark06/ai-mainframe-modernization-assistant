from typing import Dict, List, Optional
import hashlib

from app.analysis.models import AnalysisResult
from app.modernization.flow.models import Flow, FlowNode, FlowEdge, NodeType, EdgeType
from app.ir.program import IRFunction
from app.ir.instructions import IRCall
from app.ir.visitors import IRVisitor, traverse_ir


class FlowGenerationVisitor(IRVisitor):
    def __init__(self) -> None:
        self.nodes: Dict[str, FlowNode] = {}
        self.edges: List[FlowEdge] = []
        self.current_function: Optional[str] = None
        self._edge_counter = 0

    def visit_function(self, node: IRFunction) -> None:
        node_id = f"fn_{node.name}"
        # Always set to PROCESS when we encounter the actual definition
        self.nodes[node_id] = FlowNode(
            id=node_id, node_type=NodeType.PROCESS, name=node.name
        )
        self.current_function = node_id

    def visit_call(self, node: IRCall) -> None:
        if self.current_function:
            target_id = f"fn_{node.target}"
            if target_id not in self.nodes:
                self.nodes[target_id] = FlowNode(
                    id=target_id, node_type=NodeType.EXTERNAL, name=node.target
                )

            # Create a deterministic edge ID
            edge_id = f"e_{self.current_function}_{target_id}_{self._edge_counter}"
            self._edge_counter += 1

            self.edges.append(
                FlowEdge(
                    id=edge_id,
                    source_id=self.current_function,
                    target_id=target_id,
                    edge_type=EdgeType.CALLS,
                )
            )


def generate_flow(analysis: AnalysisResult) -> Flow:
    """
    Generate a deterministic Flow graph from an AnalysisResult.
    """
    visitor = FlowGenerationVisitor()
    if analysis.ir:
        traverse_ir(analysis.ir, visitor)

    nodes = list(visitor.nodes.values())

    # Sort nodes and edges for deterministic output, as required by the spec
    nodes.sort(key=lambda n: n.id)
    visitor.edges.sort(key=lambda e: e.id)

    # Fallback name if IR is missing or program name is not available
    flow_name = analysis.ir.name if analysis.ir else "Unknown Program"

    return Flow(
        id=f"flow_{hashlib.md5(flow_name.encode()).hexdigest()[:8]}",
        name=flow_name,
        nodes=nodes,
        edges=visitor.edges,
    )
