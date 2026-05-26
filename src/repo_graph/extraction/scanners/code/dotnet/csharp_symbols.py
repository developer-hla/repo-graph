"""C# symbol extraction helpers."""

from __future__ import annotations

import re

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_fact, entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, FactBatch, RelationshipFact
from repo_graph.extraction.scanners.code.dotnet.csharp_syntax import csharp_scope_code
from repo_graph.extraction.scanners.symbol_helpers import SymbolCallTarget, TypeMethodIndex, symbol_call_facts

CS_TYPE_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|internal|static|sealed|abstract|partial)\s+)*"
    r"(class|record|interface|struct)\s+([A-Za-z_]\w*)"
)
CS_METHOD_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|internal|static|virtual|override|async|sealed|new|partial|extern|unsafe)"
    r"\s+)+(?:[\w<>\[\],.?]+\s+)+([A-Za-z_]\w*)\s*(?:<[^>]+>)?\s*\("
)
CS_NEW_METHOD_CALL_RE = re.compile(r"\bnew\s+(?P<class>[A-Za-z_]\w*)\s*\([^)]*\)\s*\.\s*(?P<method>[A-Za-z_]\w*)\s*\(")
CS_QUALIFIED_METHOD_CALL_RE = re.compile(r"\b(?P<receiver>this|[A-Za-z_]\w*)\s*\.\s*(?P<method>[A-Za-z_]\w*)\s*\(")
CS_DIRECT_METHOD_CALL_RE = re.compile(r"(?<![\.\w])(?P<method>[A-Za-z_]\w*)\s*\(")


def csharp_method_index(content: str) -> TypeMethodIndex:
    current_type: str | None = None
    type_methods: dict[str, set[str]] = {}
    for line in content.splitlines():
        type_match = CS_TYPE_RE.match(line)
        if type_match:
            current_type = type_match.group(2)
            continue
        method_match = CS_METHOD_RE.match(line)
        if current_type and method_match:
            type_methods.setdefault(current_type, set()).add(method_match.group(1))
    return TypeMethodIndex(type_methods={type_name: frozenset(methods) for type_name, methods in type_methods.items()})


def csharp_symbol_facts(
    context: FileScanContext,
    symbol_kind: str,
    name: str,
    namespace: str | None,
    line_number: int,
    parent_name: str | None = None,
) -> FactBatch:
    facts = FactBatch()
    entity_type = csharp_entity_type(symbol_kind)
    full_name = ".".join(part for part in (namespace, parent_name, name) if part)
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
            "namespace": namespace,
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
            "dotnet_symbol",
            line_number,
        )
    )
    return facts


def csharp_entity_type(symbol_kind: str) -> str:
    if symbol_kind == "interface":
        return "interface"
    if symbol_kind == "method":
        return "function"
    return "class"


def csharp_symbol_call_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact,
    current_type: str | None,
    method_index: TypeMethodIndex,
) -> list[RelationshipFact]:
    code = csharp_scope_code(line)
    targets = [
        *csharp_new_method_call_targets(code, method_index),
        *csharp_qualified_method_call_targets(code, current_type, method_index),
        *csharp_direct_method_call_targets(code, current_type, method_index),
    ]
    return symbol_call_facts(context, from_entity, targets, "dotnet_call", line_number)


def csharp_new_method_call_targets(code: str, method_index: TypeMethodIndex) -> list[SymbolCallTarget]:
    return [
        SymbolCallTarget(
            f"{match.group('class')}.{match.group('method')}",
            f"new {match.group('class')}().{match.group('method')}",
            "class_method",
            receiver=match.group("class"),
        )
        for match in CS_NEW_METHOD_CALL_RE.finditer(code)
        if method_index.has_method(match.group("class"), match.group("method"))
    ]


def csharp_qualified_method_call_targets(
    code: str,
    current_type: str | None,
    method_index: TypeMethodIndex,
) -> list[SymbolCallTarget]:
    targets: list[SymbolCallTarget] = []
    for match in CS_QUALIFIED_METHOD_CALL_RE.finditer(code):
        receiver = match.group("receiver")
        method_name = match.group("method")
        if receiver == "this" and method_index.has_method(current_type, method_name):
            targets.append(
                SymbolCallTarget(f"{current_type}.{method_name}", f"this.{method_name}", "instance_method", receiver)
            )
        elif method_index.has_method(receiver, method_name):
            targets.append(
                SymbolCallTarget(f"{receiver}.{method_name}", f"{receiver}.{method_name}", "class_method", receiver)
            )
    return targets


def csharp_direct_method_call_targets(
    code: str,
    current_type: str | None,
    method_index: TypeMethodIndex,
) -> list[SymbolCallTarget]:
    return [
        SymbolCallTarget(f"{current_type}.{method_name}", method_name, "direct")
        for match in CS_DIRECT_METHOD_CALL_RE.finditer(code)
        if (method_name := match.group("method")) and method_index.has_method(current_type, method_name)
    ]


__all__ = [
    "csharp_direct_method_call_targets",
    "csharp_entity_type",
    "csharp_method_index",
    "csharp_new_method_call_targets",
    "csharp_qualified_method_call_targets",
    "csharp_symbol_call_facts",
    "csharp_symbol_facts",
]
