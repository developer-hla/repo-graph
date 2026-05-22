"""Code symbol relationship helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.legacy_graph_helpers import unresolved_edge
from repo_graph.extraction.scanners.sql_helpers import source_context_properties
from repo_graph.graph import Edge, Entity


@dataclass(frozen=True)
class TypeMethodIndex:
    type_methods: dict[str, frozenset[str]]

    def has_method(self, type_name: str | None, method_name: str) -> bool:
        return bool(type_name) and method_name in self.type_methods.get(type_name, frozenset())


@dataclass(frozen=True)
class SymbolCallTarget:
    name: str
    raw_target: str
    call_kind: str
    receiver: str | None = None


def symbol_call_edges(
    context: FileScanContext,
    from_entity: Entity,
    targets: Sequence[SymbolCallTarget],
    parser: str,
    line_number: int,
) -> list[Edge]:
    edges: list[Edge] = []
    seen: set[tuple[str, str]] = set()
    for target in targets:
        key = (target.name, target.raw_target)
        if key in seen or target.name == from_entity.name or target.name in from_entity.aliases:
            continue
        seen.add(key)
        properties = {
            "raw_target": target.raw_target,
            "normalized_target": target.name,
            "call_kind": target.call_kind,
            **source_context_properties(from_entity),
        }
        if target.receiver:
            properties["receiver"] = target.receiver
        edges.append(
            unresolved_edge(
                from_entity,
                target.name,
                "CALLS_SYMBOL",
                context.source.name,
                context.rel_path,
                parser,
                to_type="function",
                line_number=line_number,
                properties=properties,
            )
        )
    return edges
