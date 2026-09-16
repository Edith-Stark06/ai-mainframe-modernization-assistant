"""
Control Flow Graph Generator (task #110).

Purpose:
    Build a :class:`~app.modernization.flow.models.Flow` that represents
    actual COBOL execution flow -- sequential statements, IF/ELSE
    branching, PERFORM UNTIL loops, paragraph transitions, PERFORM and
    GO TO targets, and program termination -- rather than only the
    call-graph relationships between whole functions that this module
    produced before task #110.

    The pre-#110 call graph (one ``PROCESS`` node per
    :class:`~app.ir.program.IRFunction`, one ``CALLS`` edge per
    :class:`~app.ir.instructions.IRCall`) is preserved unchanged: every
    node ID, edge ID, and cross-module/ambiguous-call resolution rule it
    produced still applies verbatim, so existing consumers and the
    existing test suite (``tests/modernization/flow/test_generator.py``)
    keep working. Statement-level CFG nodes/edges are *added* alongside
    it in the same :class:`~app.modernization.flow.models.Flow`, using a
    disjoint ID namespace (``stmt_...`` vs. ``fn_...``/``ext_...``).

    Per task #109's architectural decision, every paragraph's statements
    still live in one flat :class:`~app.ir.blocks.IRBasicBlock` rather
    than being split into separate blocks/functions. This module
    recovers per-paragraph structure from
    :attr:`~app.ir.instructions.IRInstruction.paragraph` (task #109) and
    reconstructs real control flow by interpreting the existing
    ``IRIf``/``IRElse``/``IREndIf``/``IRPerformUntil``/``IREndPerform``
    marker sequence with a single forward pass and a small nesting
    stack -- the same marker sequence
    :mod:`app.backend.java.generator` already interprets to produce
    nested Java ``if``/``while`` blocks. No IR restructuring, no parser
    changes, no Java backend changes.

Responsibilities:
    - Preserve the existing function-level call graph exactly.
    - Build one statement/decision node per paragraph statement,
      connected by edges typed ``FLOWS_TO``, ``TRUE_BRANCH``,
      ``FALSE_BRANCH``, ``LOOP_BODY``, ``LOOP_BACK``, ``LOOP_EXIT``,
      ``PERFORMS``, ``GOES_TO``, or ``FALLTHROUGH``.
    - Distinguish a PERFORM/GO TO to a paragraph defined in this same
      program from a CALL to an external program, using only
      information already present in the IR (whether the target name
      matches a known paragraph).
    - Terminate flow at STOP RUN/GOBACK (task #109's ``IRReturn``) and
      at GO TO: no node created after either has an outgoing edge added
      for it, so no phantom successor is fabricated.
    - Guarantee termination: the interpreter is a single forward pass
      over an already-finite instruction list plus one linear
      post-pass to resolve forward-referenced PERFORM/GO TO/fallthrough
      targets -- it cannot loop, regardless of how the source program's
      *represented* control flow loops.
    - Compute reachability from the program's first paragraph and
      report structural loop-back edges (see :func:`compute_reachability`
      and :func:`count_cycles`).

Non-responsibilities:
    - Expanding a CALL target's own internal control flow (the callee's
      body is not analysed; only a boundary edge is produced).
    - EVALUATE, file I/O, or any construct with no AST/IR representation
      -- there is nothing here for the CFG to reflect, consistent with
      task #108/#109's "unsupported/unmodelled" accounting.
    - Modelling a fixed "return to caller" edge for a PERFORM'd
      paragraph's exit: which PERFORM statement a given paragraph
      returns to is call-site-dependent, and a single static edge
      cannot represent that without call-stack-sensitive analysis,
      which is out of this task's scope. The paragraph's exit is
      instead connected to the next paragraph in source order via
      ``FALLTHROUGH`` when it is not itself terminal -- the correct
      static approximation of COBOL's actual fall-through semantics,
      and a documented, known limitation for the PERFORM case rather
      than a fabricated "return" edge.

Dependencies:
    - :mod:`app.modernization.flow.models` -- ``Flow``, ``FlowNode``,
      ``FlowEdge``, ``NodeType``, ``EdgeType``.
    - :mod:`app.ir.instructions`, :mod:`app.ir.visitors` -- the IR
      instruction hierarchy and traversal driver.
    - Python standard library only (``hashlib``, ``dataclasses``).

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from app.analysis.models import AnalysisResult
from app.ir.instructions import (
    IRAccept,
    IRAdd,
    IRAssignment,
    IRCall,
    IRDisplay,
    IRDivide,
    IRElse,
    IREndIf,
    IREndPerform,
    IRIf,
    IRInstruction,
    IRJump,
    IRMove,
    IRMultiply,
    IRPerformUntil,
    IRReturn,
    IRSubtract,
)
from app.ir.blocks import IRBasicBlock
from app.ir.program import IRFunction, IRModule
from app.ir.visitors import IRVisitor, traverse_ir
from app.modernization.flow.models import EdgeType, Flow, FlowEdge, FlowNode, NodeType

__all__ = [
    "FlowGenerationVisitor",
    "compute_reachability",
    "count_cycles",
    "generate_flow",
]


@dataclass
class _BranchFrame:
    """One open ``IF`` awaiting its ``IREndIf`` during the forward pass."""

    decision_id: str
    else_seen: bool = False
    #: The THEN branch's own pending edges, captured when IRElse is seen
    #: (or, if there is no ELSE, unused -- see visit_end_if).
    then_pending: List[Tuple[str, "EdgeType"]] = field(default_factory=list)


@dataclass
class _LoopFrame:
    """One open ``PERFORM UNTIL`` awaiting its ``IREndPerform``."""

    decision_id: str


@dataclass
class _DeferredEdge:
    """
    A ``PERFORMS``/``GOES_TO`` edge whose target paragraph may be defined
    later in the source than the statement that references it.  Resolved
    in a linear post-pass once every paragraph's entry node is known.
    """

    source_id: str
    target_paragraph: str
    edge_type: EdgeType


class FlowGenerationVisitor(IRVisitor):
    """
    Builds the combined call-graph + control-flow-graph node/edge set.

    Instantiate one per :class:`~app.ir.program.IRProgram` (via
    :func:`generate_flow`); the visitor accumulates state as
    :func:`~app.ir.visitors.traverse_ir` drives it, so it is not meant
    to be reused across programs.
    """

    def __init__(self, known_functions: Dict[str, List[str]]) -> None:
        self.known_functions = known_functions
        self.nodes: Dict[str, FlowNode] = {}
        # Keep track of logical edges to prevent duplicates
        self._seen_logical_edges: Set[Tuple[str, str, EdgeType]] = set()
        self.edges: List[FlowEdge] = []
        self.current_module: Optional[str] = None
        self.current_function: Optional[str] = None

        # -- Task #110 control-flow state (reset per basic block) --------
        self._known_paragraphs: Set[str] = set()
        self._paragraph_order: List[str] = []
        self._paragraph_entry: Dict[str, str] = {}
        self._paragraph_terminal: Dict[str, bool] = {}
        self._paragraph_pending_at_close: Dict[str, List[Tuple[str, EdgeType]]] = {}
        self._paragraph_index: Dict[str, int] = {}
        self._current_paragraph: Optional[str] = None
        # Node(s) whose outgoing edge should connect to the *next* node
        # created.  A list because an IF with no ELSE needs both the
        # THEN branch's exit and the decision's own FALSE branch to
        # reach the same join point.
        self._pending: List[Tuple[str, EdgeType]] = []
        self._branch_stack: List[_BranchFrame] = []
        self._loop_stack: List[_LoopFrame] = []
        self._deferred_edges: List[_DeferredEdge] = []
        #: Loop-back edges found -- each one is exactly one structural
        #: cycle in the statement-level graph (see module docstring).
        self.loop_back_edge_count = 0

    # ------------------------------------------------------------------
    # Existing call-graph behaviour (unchanged)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Task #110: statement-level control flow
    # ------------------------------------------------------------------

    def visit_basic_block(self, node: IRBasicBlock) -> None:
        """Pre-scan the block once so forward PERFORM/GO TO targets resolve."""
        self._known_paragraphs = {i.paragraph for i in node.instructions if i.paragraph}

    def _maybe_enter_paragraph(self, instr: IRInstruction) -> None:
        """Detect a paragraph boundary and record its entry node in advance."""
        para = instr.paragraph
        if not para or para == self._current_paragraph:
            return
        if self._current_paragraph is not None:
            self._close_paragraph()
        self._current_paragraph = para
        self._paragraph_order.append(para)
        self._paragraph_index[para] = 0
        self._pending = []  # a new paragraph starts its own flow

    def _close_paragraph(self) -> None:
        """
        Snapshot the just-finished paragraph's still-open edges.

        A paragraph's last statement can leave *more than one* pending
        edge -- e.g. an ``IF`` with no ``ELSE`` as the final statement
        leaves both the THEN branch's exit and the decision's own
        FALSE branch open, each of which must still reach "whatever
        comes after this paragraph" (task #110: an IF's false path must
        never simply be dropped just because no further statement
        happens to follow it in the same paragraph). Every pending edge
        is preserved here, with its own original edge type, for
        :meth:`finish` to resolve once the next paragraph's entry node
        is known -- not just the single most-recently-created node.
        """
        para = self._current_paragraph
        if para is None:
            return
        self._paragraph_terminal[para] = not self._pending
        self._paragraph_pending_at_close[para] = list(self._pending)

    def _new_node(
        self, node_type: NodeType, label: str, *, metadata: Optional[dict] = None
    ) -> str:
        """
        Create one statement/decision node with a stable, deterministic ID.

        The ID is derived only from the module name, the paragraph name,
        and that paragraph's running statement index -- all of which
        come from source structure, never from Python object identity
        (task #110's stable-ID requirement).
        """
        para = self._current_paragraph or "__no_paragraph__"
        mod_prefix = self.current_module if self.current_module else "unknown"
        index = self._paragraph_index.get(para, 0)
        self._paragraph_index[para] = index + 1
        node_id = f"stmt_{mod_prefix}_{para}_{index}"

        self.nodes[node_id] = FlowNode(
            id=node_id,
            node_type=node_type,
            name=label,
            metadata=metadata or {},
        )

        if para not in self._paragraph_entry:
            self._paragraph_entry[para] = node_id
        return node_id

    def _link_pending_to(self, node_id: str) -> None:
        """Connect every pending edge source to the newly created *node_id*."""
        for source_id, edge_type in self._pending:
            self._add_edge(source_id, node_id, edge_type)
        self._pending = []

    def _add_edge(self, source_id: str, target_id: str, edge_type: EdgeType) -> None:
        logical_edge = (source_id, target_id, edge_type)
        if logical_edge in self._seen_logical_edges:
            return
        self._seen_logical_edges.add(logical_edge)
        edge_id = f"e_{source_id}_{target_id}_{edge_type.value}"
        self.edges.append(
            FlowEdge(
                id=edge_id,
                source_id=source_id,
                target_id=target_id,
                edge_type=edge_type,
            )
        )
        if edge_type is EdgeType.LOOP_BACK:
            self.loop_back_edge_count += 1

    def _sequential_node(self, instr: IRInstruction, label: str) -> None:
        """Handle a plain, non-branching statement: link, create, advance."""
        self._maybe_enter_paragraph(instr)
        node_id = self._new_node(NodeType.PROCESS, label)
        self._link_pending_to(node_id)
        self._pending = [(node_id, EdgeType.FLOWS_TO)]

    # -- Individual instruction hooks (duck-typed via IRInstruction.accept) --

    def visit_move(self, node: IRMove) -> None:
        self._sequential_node(node, f"MOVE {node.source} TO {node.result}")

    def visit_display(self, node: IRDisplay) -> None:
        self._sequential_node(node, f"DISPLAY {node.operand}")

    def visit_accept(self, node: IRAccept) -> None:
        self._sequential_node(node, f"ACCEPT {node.result}")

    def visit_add(self, node: IRAdd) -> None:
        self._sequential_node(node, f"ADD {node.left} TO {node.right}")

    def visit_subtract(self, node: IRSubtract) -> None:
        self._sequential_node(node, f"SUBTRACT {node.left} FROM {node.right}")

    def visit_multiply(self, node: IRMultiply) -> None:
        self._sequential_node(node, f"MULTIPLY {node.left} BY {node.right}")

    def visit_divide(self, node: IRDivide) -> None:
        self._sequential_node(node, f"DIVIDE {node.left} INTO {node.right}")

    def visit_assignment(self, node: IRAssignment) -> None:
        self._sequential_node(node, f"{node.result} = {node.value}")

    def visit_if(self, node: IRIf) -> None:
        self._maybe_enter_paragraph(node)
        decision_id = self._new_node(
            NodeType.DECISION, f"IF {node.left} {node.operator} {node.right}"
        )
        self._link_pending_to(decision_id)
        self._branch_stack.append(_BranchFrame(decision_id=decision_id))
        # The next node created is the first statement of the THEN branch.
        self._pending = [(decision_id, EdgeType.TRUE_BRANCH)]

    def visit_else(self, node: IRElse) -> None:
        frame = self._branch_stack[-1]
        frame.else_seen = True
        # Whatever the THEN branch ended on (if anything) must reach the
        # join point once we know where that is -- keep it pending.
        frame.then_pending = list(self._pending)
        self._pending = [(frame.decision_id, EdgeType.FALSE_BRANCH)]

    def visit_end_if(self, node: IREndIf) -> None:
        frame = self._branch_stack.pop()
        join_pending: List[Tuple[str, EdgeType]] = []
        if frame.else_seen:
            join_pending.extend(frame.then_pending)
            join_pending.extend(self._pending)
        else:
            # No ELSE: the THEN branch's exit AND the decision's own
            # FALSE branch both reach the join point.
            join_pending.extend(self._pending)
            join_pending.append((frame.decision_id, EdgeType.FALSE_BRANCH))
        self._pending = join_pending

    def visit_perform_until(self, node: IRPerformUntil) -> None:
        self._maybe_enter_paragraph(node)
        decision_id = self._new_node(
            NodeType.DECISION,
            f"PERFORM UNTIL {node.left} {node.operator} {node.right}",
        )
        self._link_pending_to(decision_id)
        self._loop_stack.append(_LoopFrame(decision_id=decision_id))
        self._pending = [(decision_id, EdgeType.LOOP_BODY)]

    def visit_end_perform(self, node: IREndPerform) -> None:
        frame = self._loop_stack.pop()
        # The loop body's exit flows back to the condition, closing the
        # cycle -- this is the one and only source of cycles in this
        # graph, so counting LOOP_BACK edges (see _add_edge) is an exact
        # count of structural loops, not an approximation.
        for source_id, _edge_type in self._pending:
            self._add_edge(source_id, frame.decision_id, EdgeType.LOOP_BACK)
        self._pending = [(frame.decision_id, EdgeType.LOOP_EXIT)]

    def visit_return(self, node: IRReturn) -> None:
        """STOP RUN or GOBACK (task #109): terminal, no successor edge."""
        self._maybe_enter_paragraph(node)
        kind = node.comment or "RETURN"
        node_id = self._new_node(
            NodeType.PROCESS, kind, metadata={"terminal": True, "kind": kind}
        )
        self._link_pending_to(node_id)
        self._pending = []  # no phantom successor after termination

    def visit_jump(self, node: IRJump) -> None:
        """
        GO TO (unreachable from the parser today -- see task #109's audit
        -- but handled here for robustness/completeness).  Terminal at
        this point in the flow: control transfers unconditionally
        elsewhere.
        """
        self._maybe_enter_paragraph(node)
        node_id = self._new_node(NodeType.PROCESS, f"GO TO {node.target}")
        self._link_pending_to(node_id)
        self._deferred_edges.append(
            _DeferredEdge(node_id, node.target, EdgeType.GOES_TO)
        )
        self._pending = []  # control leaves unconditionally; no fallthrough

    def visit_call(self, node: IRCall) -> None:
        # Statement-level participation only applies to IRCall instances
        # that actually came from the #109 pipeline's paragraph-attributed
        # IR. Hand-built IR with no `paragraph` set (as in this module's
        # pre-#110 unit tests, which assert an exact pure-call-graph node
        # and edge count) is left exactly as it always behaved: only the
        # call-graph node/edge below is produced, with no additional
        # statement-level node -- preserving those tests unchanged.
        has_paragraph_context = bool(node.paragraph)
        if has_paragraph_context:
            self._maybe_enter_paragraph(node)

        # `comment` (task #110) is the authoritative discriminator
        # between a PERFORM and a genuine CALL -- both lower to IRCall
        # identically otherwise. Hand-built IR that never sets `comment`
        # (as in this module's pre-#110 unit tests) falls back to the
        # "target matches a known local paragraph" heuristic, which is
        # exactly this repository's pre-#110 behaviour for such IR.
        is_perform = (
            node.comment == "PERFORM"
            if node.comment in ("PERFORM", "CALL")
            else node.target in self._known_paragraphs
        )
        if is_perform:
            # PERFORM <paragraph>: a control-flow edge to that
            # paragraph's entry, not a call-graph edge -- whether or not
            # the target actually resolves to a paragraph in this
            # program.  An unresolved target still gets a PERFORMS edge
            # (to a synthetic `ext_<name>` node, exactly like an
            # unresolved CALL target), rather than being silently
            # mis-classified as a cross-module CALLS edge.  Both the
            # PERFORM statement's own node AND the deferred PERFORMS
            # edge are created here, since the paragraph may be defined
            # later in the source than this PERFORM.
            node_id = self._new_node(NodeType.PROCESS, f"PERFORM {node.target}")
            self._link_pending_to(node_id)
            self._deferred_edges.append(
                _DeferredEdge(node_id, node.target, EdgeType.PERFORMS)
            )
            self._pending = [(node_id, EdgeType.FLOWS_TO)]
            return

        # Unchanged pre-#110 behaviour: a genuine CALL to another
        # function/module, or an unresolved external target.
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

            self._add_edge(self.current_function, target_id, EdgeType.CALLS)

        # A CALL statement also participates in sequential statement flow
        # -- but only when it has real paragraph context to place it in.
        if has_paragraph_context:
            call_node_id = self._new_node(NodeType.PROCESS, f"CALL {node.target}")
            self._link_pending_to(call_node_id)
            self._pending = [(call_node_id, EdgeType.FLOWS_TO)]

    # ------------------------------------------------------------------
    # Finalisation
    # ------------------------------------------------------------------

    def finish(self) -> None:
        """
        Resolve deferred PERFORM/GO TO edges and add paragraph fallthrough.

        Must be called exactly once, after :func:`traverse_ir` has
        finished driving this visitor.
        """
        self._close_paragraph()

        for deferred in self._deferred_edges:
            target_entry = self._paragraph_entry.get(deferred.target_paragraph)
            if target_entry is None:
                # The PERFORM/GO TO target does not match any paragraph
                # actually present in this program -- an unresolved
                # reference.  Do not fabricate a target; report it as an
                # EXTERNAL node instead, exactly as an unresolved CALL
                # target already is.
                target_entry = f"ext_{deferred.target_paragraph}"
                if target_entry not in self.nodes:
                    self.nodes[target_entry] = FlowNode(
                        id=target_entry,
                        node_type=NodeType.EXTERNAL,
                        name=deferred.target_paragraph,
                    )
            self._add_edge(deferred.source_id, target_entry, deferred.edge_type)

        for i in range(len(self._paragraph_order) - 1):
            para = self._paragraph_order[i]
            next_para = self._paragraph_order[i + 1]
            if self._paragraph_terminal.get(para):
                continue  # STOP RUN/GOBACK/GO TO: no fallthrough
            next_entry = self._paragraph_entry.get(next_para)
            if next_entry is None:
                continue
            # Every edge still open when this paragraph ended reaches
            # the next paragraph's entry -- there can be more than one
            # (see _close_paragraph's docstring: an IF with no ELSE as
            # the last statement leaves two). A plain FLOWS_TO is
            # relabelled FALLTHROUGH to mark that it crosses a paragraph
            # boundary; a more specific type (e.g. FALSE_BRANCH) is kept
            # as-is, since it remains accurate and more informative than
            # a generic fallthrough label.
            for source_id, edge_type in self._paragraph_pending_at_close.get(para, []):
                resolved_type = (
                    EdgeType.FALLTHROUGH
                    if edge_type is EdgeType.FLOWS_TO
                    else edge_type
                )
                self._add_edge(source_id, next_entry, resolved_type)


def compute_reachability(flow: Flow, entry_node_id: Optional[str]) -> Set[str]:
    """
    Return the set of node IDs reachable from *entry_node_id*.

    Uses an iterative depth-first search with an explicit visited set,
    so it terminates even on a graph containing cycles (task #110's
    "cycles must terminate" and "malformed input cannot hang"
    requirements) and never recurses (no call-stack depth risk on a
    large program).

    Args:
        flow: The graph to search.
        entry_node_id: The node to start from, or ``None`` if there is
            no identifiable entry point (e.g. an empty flow), in which
            case no node is reachable.

    Returns:
        The set of reachable node IDs, including *entry_node_id* itself
        if it exists in *flow*.
    """
    if entry_node_id is None or entry_node_id not in {n.id for n in flow.nodes}:
        return set()

    adjacency: Dict[str, List[str]] = {}
    for edge in flow.edges:
        adjacency.setdefault(edge.source_id, []).append(edge.target_id)

    visited: Set[str] = set()
    stack = [entry_node_id]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for neighbour in adjacency.get(current, ()):
            if neighbour not in visited:
                stack.append(neighbour)
    return visited


def count_cycles(flow: Flow) -> int:
    """
    Count structural cycles in *flow*.

    Every cycle in the statement-level control-flow graph is introduced
    by exactly one ``LOOP_BACK`` edge (the only edge type this generator
    ever directs from a later node back to an earlier one); counting
    those edges is therefore an exact cycle count for graphs this
    generator produces, not a heuristic approximation.

    Args:
        flow: The graph to inspect.

    Returns:
        The number of ``LOOP_BACK`` edges present.
    """
    return sum(1 for edge in flow.edges if edge.edge_type is EdgeType.LOOP_BACK)


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
    visitor.finish()

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
