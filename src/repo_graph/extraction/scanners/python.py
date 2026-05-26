"""Python source scanner."""

from __future__ import annotations

import ast
from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import scan_issue
from repo_graph.extraction.facts import EntityFact, FactBatch
from repo_graph.extraction.scanners.python_helpers import (
    PythonCallableIndex,
    python_http_call_facts,
    python_import_fact,
    python_route_facts,
    python_sql_call_facts,
    python_symbol_call_facts,
    python_symbol_facts,
)


class PythonCodeExtractor:
    name = "python"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".py"

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            facts.issues.append(
                scan_issue(context, self.name, f"Invalid Python {context.source.name}/{context.rel_path}: {exc}")
            )
            return facts

        visitor = PythonAstVisitor(context, python_callable_index(tree))
        visitor.visit(tree)
        return visitor.facts


class PythonAstVisitor(ast.NodeVisitor):
    def __init__(self, context: FileScanContext, callable_index: PythonCallableIndex) -> None:
        self.context = context
        self.callable_index = callable_index
        self.facts = FactBatch()
        self.class_stack: list[str] = []
        self.function_stack: list[EntityFact] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.facts.relationships.append(python_import_fact(self.context, alias.name, 0, node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        raw_target = "." * node.level + (node.module or "")
        self.facts.relationships.append(python_import_fact(self.context, raw_target, node.level, node.lineno))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.facts.extend(python_symbol_facts(self.context, "class", node.name, node.lineno, self.class_stack))
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.visit_python_function(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_python_function(node, "async_function")

    def visit_python_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, symbol_kind: str) -> None:
        symbol_facts = python_symbol_facts(self.context, symbol_kind, node.name, node.lineno, self.class_stack)
        function_entity = symbol_facts.entities[0] if symbol_facts.entities else None
        self.facts.extend(symbol_facts)
        self.facts.extend(
            python_route_facts(self.context, node.name, node.decorator_list, node.lineno, function_entity)
        )
        if function_entity:
            self.function_stack.append(function_entity)
        self.generic_visit(node)
        if function_entity:
            self.function_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        self.facts.relationships.extend(python_http_call_facts(self.context, node))
        self.facts.relationships.extend(python_sql_call_facts(self.context, node))
        if self.function_stack:
            function_entity = self.function_stack[-1]
            self.facts.relationships.extend(python_http_call_facts(self.context, node, from_entity=function_entity))
            self.facts.relationships.extend(python_sql_call_facts(self.context, node, from_entity=function_entity))
            self.facts.relationships.extend(
                python_symbol_call_facts(
                    self.context,
                    node,
                    from_entity=function_entity,
                    class_stack=self.class_stack,
                    callable_index=self.callable_index,
                )
            )
        self.generic_visit(node)


class PythonCallableCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.functions: set[str] = set()
        self.class_methods: dict[str, set[str]] = {}
        self.class_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.visit_python_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_python_function(node)

    def visit_python_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if self.class_stack:
            class_name = ".".join(self.class_stack)
            self.class_methods.setdefault(class_name, set()).add(node.name)
            self.generic_visit(node)
            return
        self.functions.add(node.name)
        self.generic_visit(node)


def python_callable_index(tree: ast.AST) -> PythonCallableIndex:
    collector = PythonCallableCollector()
    collector.visit(tree)
    return PythonCallableIndex(
        functions=frozenset(collector.functions),
        class_methods={class_name: frozenset(methods) for class_name, methods in collector.class_methods.items()},
    )
