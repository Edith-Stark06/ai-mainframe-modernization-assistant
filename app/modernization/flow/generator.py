from typing import Dict, List, Optional, Set, Tuple
import hashlib

from app.analysis.models import AnalysisResult
from app.modernization.flow.models import Flow, FlowNode, FlowEdge, NodeType, EdgeType
from app.ir.program import IRFunction, IRModule
from app.ir.instructions import IRCall
from app.ir.visitors import IRVisitor, traverse_ir


class FlowGenerationVisitor(IRVisitor):
    def __init__(self) -> None:
        self.nodes: Dict[str, FlowNode] = {}
        # Keep track of logical edges to prevent duplicates
        self._seen_logical_edges: Set[Tuple[str, str, EdgeType]] = set()
        self.edges: List[FlowEdge] = []
        self.current_module: Optional[str] = None
        self.current_function: Optional[str] = None

    def visit_module(self, node: IRModule) -> None:
        # Use module name to qualify function IDs, avoiding collisions
        self.current_module = node.name

    def visit_function(self, node: IRFunction) -> None:
        # Stable qualified identity: fn_<module>_<function>
        mod_prefix = self.current_module if self.current_module else "unknown"
        node_id = f"fn_{mod_prefix}_{node.name}"

        # If an external node was previously created for this name, it will be upgraded
        # because the final pass of nodes dict uses node_id.
        self.nodes[node_id] = FlowNode(
            id=node_id, node_type=NodeType.PROCESS, name=node.name
        )
        self.current_function = node_id

    def visit_call(self, node: IRCall) -> None:
        if self.current_function:
            mod_prefix = self.current_module if self.current_module else "unknown"
            target_id = f"fn_{mod_prefix}_{node.target}"

            # Create external node if it doesn't exist
            if target_id not in self.nodes:
                self.nodes[target_id] = FlowNode(
                    id=target_id, node_type=NodeType.EXTERNAL, name=node.target
                )

            logical_edge = (self.current_function, target_id, EdgeType.CALLS)
            if logical_edge not in self._seen_logical_edges:
                self._seen_logical_edges.add(logical_edge)

                # Create a deterministic edge ID using the relationship signature
                edge_id = (
                    f"e_{self.current_function}_{target_id}_{EdgeType.CALLS.value}"
                )

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
    Handles empty IR gracefully.
    """
    if not analysis.ir:
        # Return a deterministic empty flow if IR is missing
        return Flow(
            id="flow_empty_analysis",
            name="Unknown Program",
            nodes=[],
            edges=[],
        )

    visitor = FlowGenerationVisitor()
    traverse_ir(analysis.ir, visitor)

    nodes = list(visitor.nodes.values())

    # Sort nodes and edges for deterministic output
    nodes.sort(key=lambda n: n.id)
    visitor.edges.sort(key=lambda e: e.id)

    flow_name = analysis.ir.name if analysis.ir.name else "Unknown Program"

    # Stable deterministic flow ID derived from workspace/program identity
    # Instead of just the program name, we incorporate the module names
    modules_sig = "_".join(m.name for m in analysis.ir.modules)
    sig_str = f"{flow_name}_{modules_sig}"

    return Flow(
        id=f"flow_{hashlib.md5(sig_str.encode()).hexdigest()[:8]}",
        name=flow_name,
        nodes=nodes,
        edges=visitor.edges,
    )
