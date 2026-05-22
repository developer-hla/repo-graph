"""Python source scanner."""

from __future__ import annotations

import ast
from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext, ScanResult
from repo_graph.extraction.scanners.shared import (
    PythonCallableIndex,
    first_entity,
    python_http_call_edges,
    python_import_edge,
    python_route_result,
    python_sql_call_edges,
    python_symbol_call_edges,
    python_symbol_result,
)
from repo_graph.graph import Entity


class PythonCodeExtractor:
    name = "python"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".py"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            result.errors.append(f"Invalid Python {context.source.name}/{context.rel_path}: {exc}")
            return result

        visitor = PythonAstVisitor(context, python_callable_index(tree))
        visitor.visit(tree)
        return visitor.result


class PythonAstVisitor(ast.NodeVisitor):
    def __init__(self, context: FileScanContext, callable_index: PythonCallableIndex) -> None:
        self.context = context
        self.callable_index = callable_index
        self.result = ScanResult()
        self.class_stack: list[str] = []
        self.function_stack: list[Entity] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.result.edges.append(python_import_edge(self.context, alias.name, 0, node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        raw_target = "." * node.level + (node.module or "")
        self.result.edges.append(python_import_edge(self.context, raw_target, node.level, node.lineno))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.result.extend(python_symbol_result(self.context, "class", node.name, node.lineno, self.class_stack))
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.visit_python_function(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_python_function(node, "async_function")

    def visit_python_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, symbol_kind: str) -> None:
        symbol_result = python_symbol_result(self.context, symbol_kind, node.name, node.lineno, self.class_stack)
        function_entity = first_entity(symbol_result)
        self.result.extend(symbol_result)
        self.result.extend(
            python_route_result(self.context, node.name, node.decorator_list, node.lineno, function_entity)
        )
        if function_entity:
            self.function_stack.append(function_entity)
        self.generic_visit(node)
        if function_entity:
            self.function_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        self.result.edges.extend(python_http_call_edges(self.context, node))
        self.result.edges.extend(python_sql_call_edges(self.context, node))
        if self.function_stack:
            function_entity = self.function_stack[-1]
            self.result.edges.extend(python_http_call_edges(self.context, node, from_entity=function_entity))
            self.result.edges.extend(python_sql_call_edges(self.context, node, from_entity=function_entity))
            self.result.edges.extend(
                python_symbol_call_edges(
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
