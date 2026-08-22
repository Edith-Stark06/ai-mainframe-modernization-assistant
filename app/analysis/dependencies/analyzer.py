"""
Dependency Analyzer.

Extracts COBOL dependencies (COPY, CALL, PERFORM) from the AST.
"""

from typing import Any

from app.analysis.dependencies.models import Dependency, DependencyType
from app.parser.ast.visitor import ASTVisitor
from app.parser.ast.node import ASTNode
from app.parser.ast.program import ProgramNode
from app.parser.ast.procedure import ProcedureDivisionNode
from app.parser.ast.paragraphs import ParagraphNode
from app.parser.ast.statements import (
    CallStatementNode,
    PerformStatementNode,
    PerformUntilStatementNode,
    IfStatementNode,
)


class DependencyAnalyzer(ASTVisitor):
    """
    Traverses the AST to extract dependencies.

    Extracts CALL and PERFORM dependencies.
    NOTE: COPY statements are not currently represented in the parsed AST
    and thus cannot be extracted by this analyzer.
    """

    def __init__(self) -> None:
        self._dependencies: list[Dependency] = []
        self._seen: set[tuple[DependencyType, str]] = set()

    def analyze(self, node: ASTNode) -> list[Dependency]:
        """
        Analyze a node and its children, returning a list of extracted dependencies.
        """
        self._dependencies = []
        self._seen = set()
        node.accept(self)
        return self._dependencies

    def _add_dependency(self, dep: Dependency) -> None:
        """
        Add a dependency if it hasn't been seen before (deduplication).
        Preserves the first occurrence's source location.
        """
        key = (dep.type, dep.target)
        if key not in self._seen:
            self._seen.add(key)
            self._dependencies.append(dep)

    def visit_program(self, node: ProgramNode) -> Any:
        if node.procedure_division:
            node.procedure_division.accept(self)
        # Note: COPY statements might appear in other divisions if supported in the future.
        return None

    def visit_procedure_division(self, node: ProcedureDivisionNode) -> Any:
        for paragraph in node.paragraphs:
            paragraph.accept(self)
        return None

    def visit_paragraph(self, node: ParagraphNode) -> Any:
        for statement in node.statements:
            statement.accept(self)
        return None

    def visit_call_statement(self, node: CallStatementNode) -> Any:
        self._add_dependency(
            Dependency(
                type=DependencyType.CALL,
                target=node.target,
                source_location=node.start_position,
            )
        )
        return None

    def visit_perform_statement(self, node: PerformStatementNode) -> Any:
        self._add_dependency(
            Dependency(
                type=DependencyType.PERFORM,
                target=node.target,
                source_location=node.start_position,
            )
        )
        return None

    def visit_perform_until_statement(self, node: PerformUntilStatementNode) -> Any:
        for statement in node.statements:
            statement.accept(self)
        return None

    def visit_if_statement(self, node: IfStatementNode) -> Any:
        for statement in node.then_statements:
            statement.accept(self)
        for statement in node.else_statements:
            statement.accept(self)
        return None
