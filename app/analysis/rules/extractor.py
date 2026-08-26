"""
Business Rule Extractor.

Purpose:
    Extracts BusinessRule domain models from the COBOL AST by traversing
    the semantic representation.
"""

from app.analysis.rules.models import BusinessRule
from app.parser.ast.program import ProgramNode
from app.parser.ast.procedure import ProcedureDivisionNode
from app.parser.ast.paragraphs import ParagraphNode
from app.parser.ast.statements import (
    StatementNode,
    IfStatementNode,
    MoveStatementNode,
    DisplayStatementNode,
    AddStatementNode,
    SubtractStatementNode,
    MultiplyStatementNode,
    DivideStatementNode,
)
from app.parser.ast.visitor import ASTVisitor
from app.parser.lexer.position import Position


class BusinessRuleExtractor(ASTVisitor):
    """
    Extracts BusinessRules from an AST by traversing conditionally
    executed blocks and collecting business actions.
    """

    def __init__(self) -> None:
        self.rules: list[BusinessRule] = []
        self._condition_stack: list[str] = []
        self._current_actions: list[str] = []
        self._current_rule_position: Position | None = None

    def extract(self, node: ProgramNode) -> list[BusinessRule]:
        """
        Extract rules from a parsed ProgramNode.
        """
        node.accept(self)
        self._flush_actions()
        return self.rules

    def _flush_actions(self) -> None:
        if self._current_actions and self._condition_stack:
            condition = " AND ".join(self._condition_stack)
            self.rules.append(
                BusinessRule(
                    condition=condition,
                    actions=tuple(self._current_actions),
                    source_location=self._current_rule_position,
                )
            )
        self._current_actions = []
        self._current_rule_position = None

    def _add_action(self, action_str: str, node: StatementNode) -> None:
        if not self._condition_stack:
            return
        if not self._current_actions:
            self._current_rule_position = node.start_position
        self._current_actions.append(action_str)

    def visit_program(self, node: ProgramNode) -> None:
        if node.procedure_division:
            node.procedure_division.accept(self)

    def visit_procedure_division(self, node: ProcedureDivisionNode) -> None:
        for para in node.paragraphs:
            para.accept(self)

    def visit_paragraph(self, node: ParagraphNode) -> None:
        for stmt in node.statements:
            stmt.accept(self)
        self._flush_actions()

    def visit_if_statement(self, node: IfStatementNode) -> None:
        self._flush_actions()

        cond = f"{node.condition_left} {node.condition_operator} {node.condition_right}"

        self._condition_stack.append(cond)
        for stmt in node.then_statements:
            stmt.accept(self)
        self._flush_actions()
        self._condition_stack.pop()

        if node.else_statements:
            self._condition_stack.append(f"NOT ({cond})")
            for stmt in node.else_statements:
                stmt.accept(self)
            self._flush_actions()
            self._condition_stack.pop()

    def visit_move_statement(self, node: MoveStatementNode) -> None:
        self._add_action(f"MOVE {node.source} TO {node.target}", node)

    def visit_display_statement(self, node: DisplayStatementNode) -> None:
        self._add_action(f"DISPLAY {node.operand}", node)

    def visit_add_statement(self, node: AddStatementNode) -> None:
        self._add_action(f"ADD {node.left} TO {node.right}", node)

    def visit_subtract_statement(self, node: SubtractStatementNode) -> None:
        self._add_action(f"SUBTRACT {node.right} FROM {node.left}", node)

    def visit_multiply_statement(self, node: MultiplyStatementNode) -> None:
        self._add_action(f"MULTIPLY {node.left} BY {node.right}", node)

    def visit_divide_statement(self, node: DivideStatementNode) -> None:
        self._add_action(f"DIVIDE {node.left} INTO {node.right}", node)
