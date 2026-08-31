from typing import Dict, List, Optional, Set, Tuple
import hashlib

from app.analysis.models import AnalysisResult
from app.modernization.flow.models import Flow, FlowNode, FlowEdge, NodeType, EdgeType
from app.ir.program import IRFunction, IRModule
from app.ir.instructions import IRCall
from app.ir.visitors import IRVisitor, traverse_ir


class FlowGenerationVisitor(IRVisitor):
    def __init__(self, known_functions: Dict[str, List[str]]) -> None:
        self.known_functions = known_functions
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
            # Check if target is explicitly qualified (e.g. MODULE_B.SUB1)
            parts = node.target.split(".", 1)
            if len(parts) == 2:
                req_mod, raw_target = parts
            else:
                req_mod = None
                raw_target = node.target

            candidates = self.known_functions.get(raw_target, [])

            if req_mod:
                if req_mod in candidates:
                    target_id = f"fn_{req_mod}_{raw_target}"
                    node_type = NodeType.PROCESS
                else:
                    target_id = f"ext_{raw_target}"
                    node_type = NodeType.EXTERNAL
            else:
                if len(candidates) == 1:
                    target_mod = candidates[0]
                    target_id = f"fn_{target_mod}_{raw_target}"
                    node_type = NodeType.PROCESS
                else:
                    target_id = f"ext_{raw_target}"
                    node_type = NodeType.EXTERNAL

            # Create external/resolved node if it doesn't exist
            if target_id not in self.nodes:
                self.nodes[target_id] = FlowNode(
                    id=target_id, node_type=node_type, name=raw_target
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

    The resulting Flow.id represents the deterministic identity of the logical
    program flow structure, NOT the global identity of the source workspace or file.
    Identical programs in different workspaces will correctly receive the same Flow ID.
    """
    if not analysis.ir:
        # Return a deterministic empty flow if IR is missing
        return Flow(
            id="flow_empty_analysis",
            name="Unknown Program",
            nodes=[],
            edges=[],
        )

    # Pre-compute all known functions to resolve cross-module targets
    known_functions: Dict[str, List[str]] = {}
    for mod in analysis.ir.modules:
        for fn in mod.functions:
            if fn.name not in known_functions:
                known_functions[fn.name] = []
            known_functions[fn.name].append(mod.name)

    visitor = FlowGenerationVisitor(known_functions)
    traverse_ir(analysis.ir, visitor)

    nodes = list(visitor.nodes.values())

    # Sort nodes and edges for deterministic output
    nodes.sort(key=lambda n: n.id)
    visitor.edges.sort(key=lambda e: e.id)

    flow_name = analysis.ir.name if analysis.ir.name else "Unknown Program"

    # Stable deterministic flow ID derived from canonical structure
    # This identifies the logical analyzed program structure.
    nodes_sig = ",".join(n.id for n in nodes)
    edges_sig = ",".join(e.id for e in visitor.edges)
    canonical_str = f"{flow_name}|nodes:{nodes_sig}|edges:{edges_sig}"

    flow_id = f"flow_{hashlib.sha256(canonical_str.encode()).hexdigest()[:16]}"

    return Flow(
        id=flow_id,
        name=flow_name,
        nodes=nodes,
        edges=visitor.edges,
    )
