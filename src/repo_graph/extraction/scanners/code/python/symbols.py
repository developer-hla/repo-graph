"""Python symbol declaration and call helpers."""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_fact, entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, FactBatch, RelationshipFact
from repo_graph.extraction.scanners.code.python.ast_values import (
    python_call_raw_target,
    python_call_receiver_name,
    python_receiver_class_name,
)
from repo_graph.extraction.scanners.symbol_helpers import SymbolCallTarget, symbol_call_facts


@dataclass(frozen=True)
class PythonCallableIndex:
    functions: frozenset[str]
    class_methods: dict[str, frozenset[str]]

    def has_function(self, name: str) -> bool:
        return name in self.functions

    def has_method(self, class_name: str, method_name: str) -> bool:
        return method_name in self.class_methods.get(class_name, frozenset())


def python_symbol_facts(
    context: FileScanContext,
    symbol_kind: str,
    name: str,
    line_number: int,
    class_stack: Sequence[str],
) -> FactBatch:
    facts = FactBatch()
    module_name = python_module_name(context.rel_path)
    parent_name = ".".join(class_stack) or None
    full_name = ".".join(part for part in (module_name, parent_name, name) if part)
    entity_type = "function" if symbol_kind in {"function", "async_function"} else symbol_kind
    aliases = {name, full_name or name}
    if parent_name:
        aliases.add(f"{parent_name}.{name}")
    symbol = entity_fact(
        context,
        entity_type=entity_type,
        name=full_name or name,
        line_number=line_number,
        aliases=aliases,
        properties={
            "symbol_kind": symbol_kind,
            "module": module_name or None,
            "parent": parent_name,
            "project": context.project.name if context.project else None,
        },
    )
    facts.entities.append(symbol)
    facts.relationships.append(
        resolved_relationship_fact(
            entity_reference(context.file_entity),
            symbol.reference,
            "DECLARES_SYMBOL",
            context,
            "python_symbol",
            line_number,
        )
    )
    return facts


def python_module_name(rel_path: str) -> str:
    path = Path(rel_path).with_suffix("")
    parts = list(path.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def python_symbol_call_facts(
    context: FileScanContext,
    call: ast.Call,
    from_entity: EntityFact,
    class_stack: Sequence[str],
    callable_index: PythonCallableIndex,
) -> list[RelationshipFact]:
    target = python_symbol_call_target(call.func, class_stack, callable_index)
    if not target:
        return []
    return symbol_call_facts(context, from_entity, [target], "python_call", call.lineno)


def python_symbol_call_target(
    func: ast.expr,
    class_stack: Sequence[str],
    callable_index: PythonCallableIndex,
) -> SymbolCallTarget | None:
    if isinstance(func, ast.Name) and callable_index.has_function(func.id):
        return SymbolCallTarget(func.id, func.id, "direct")
    if not isinstance(func, ast.Attribute):
        return None

    receiver = python_call_receiver_name(func.value)
    class_name = python_receiver_class_name(func.value)
    if class_name and callable_index.has_method(class_name, func.attr):
        return SymbolCallTarget(f"{class_name}.{func.attr}", python_call_raw_target(func), "class_method", receiver)
    if receiver in {"self", "cls"} and class_stack:
        current_class = ".".join(class_stack)
        if callable_index.has_method(current_class, func.attr):
            return SymbolCallTarget(
                f"{current_class}.{func.attr}", python_call_raw_target(func), "instance_method", receiver
            )
    return None
