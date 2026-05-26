"""JavaScript and TypeScript scanner helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_fact, entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, FactBatch, RelationshipFact
from repo_graph.extraction.scanners.symbol_helpers import SymbolCallTarget, symbol_call_facts

JS_IDENTIFIER = r"[A-Za-z_$][\w$]*"
JS_FUNCTION_DECL_RE = re.compile(
    rf"\b(?P<export>export\s+(?:default\s+)?)?(?:async\s+)?function\s+(?P<name>{JS_IDENTIFIER})\s*\("
)
JS_CLASS_DECL_RE = re.compile(rf"\b(?P<export>export\s+(?:default\s+)?)?class\s+(?P<name>{JS_IDENTIFIER})\b")
JS_CONST_FUNCTION_RE = re.compile(
    rf"\b(?P<export>export\s+)?(?:const|let|var)\s+(?P<name>{JS_IDENTIFIER})\s*=\s*"
    rf"(?:async\s*)?(?:\([^)]*\)|{JS_IDENTIFIER})?\s*=>"
)
JS_CALL_RE = re.compile(rf"\b(?P<name>{JS_IDENTIFIER})\s*\(")
JS_CALL_SKIP_NAMES = frozenset(
    {
        "catch",
        "describe",
        "fetch",
        "for",
        "function",
        "if",
        "it",
        "require",
        "return",
        "switch",
        "while",
    }
)


@dataclass(frozen=True)
class JavaScriptSymbolDeclaration:
    name: str
    entity_type: str
    line_number: int
    exported: bool
    entity: EntityFact

    @property
    def parser(self) -> str:
        if self.exported:
            return "javascript_export"
        return "javascript_symbol"


@dataclass(frozen=True)
class JavaScriptSymbolIndex:
    declarations_by_line: dict[int, tuple[JavaScriptSymbolDeclaration, ...]]
    functions_by_name: dict[str, EntityFact]
    function_by_line: dict[int, EntityFact]


def javascript_symbol_index(context: FileScanContext, content: str) -> JavaScriptSymbolIndex:
    declarations_by_line: dict[int, list[JavaScriptSymbolDeclaration]] = {}
    functions_by_name: dict[str, EntityFact] = {}
    function_by_line: dict[int, EntityFact] = {}
    for line_number, line in enumerate(content.splitlines(), start=1):
        for entity_type, name, exported in javascript_symbol_matches(line):
            declaration = javascript_symbol_declaration(context, entity_type, name, line_number, exported)
            declarations_by_line.setdefault(line_number, []).append(declaration)
            if entity_type == "function":
                functions_by_name[name] = declaration.entity
                function_by_line[line_number] = declaration.entity
    return JavaScriptSymbolIndex(
        declarations_by_line={
            line_number: tuple(declarations) for line_number, declarations in declarations_by_line.items()
        },
        functions_by_name=functions_by_name,
        function_by_line=function_by_line,
    )


def javascript_symbol_matches(line: str) -> list[tuple[str, str, bool]]:
    matches: list[tuple[str, str, bool]] = []
    for pattern, entity_type in (
        (JS_FUNCTION_DECL_RE, "function"),
        (JS_CONST_FUNCTION_RE, "function"),
        (JS_CLASS_DECL_RE, "class"),
    ):
        for match in pattern.finditer(line):
            matches.append((entity_type, match.group("name"), bool(match.group("export"))))
    return matches


def javascript_symbol_declaration(
    context: FileScanContext,
    entity_type: str,
    name: str,
    line_number: int,
    exported: bool,
) -> JavaScriptSymbolDeclaration:
    entity = entity_fact(
        context,
        entity_type=entity_type,
        name=name,
        line_number=line_number,
        aliases={name},
        properties={
            "project": context.project.name if context.project else None,
            "exported": exported,
        },
    )
    return JavaScriptSymbolDeclaration(
        name=name,
        entity_type=entity_type,
        line_number=line_number,
        exported=exported,
        entity=entity,
    )


def javascript_symbol_facts(context: FileScanContext, declaration: JavaScriptSymbolDeclaration) -> FactBatch:
    facts = FactBatch()
    facts.entities.append(declaration.entity)
    facts.relationships.append(
        resolved_relationship_fact(
            entity_reference(context.file_entity),
            declaration.entity.reference,
            "DECLARES_SYMBOL",
            context,
            declaration.parser,
            declaration.line_number,
            properties={
                "symbol_kind": declaration.entity_type,
                "exported": declaration.exported,
            },
        )
    )
    return facts


def javascript_symbol_call_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact,
    symbol_index: JavaScriptSymbolIndex,
) -> list[RelationshipFact]:
    return symbol_call_facts(
        context,
        from_entity,
        javascript_symbol_call_targets(line, symbol_index),
        "javascript_call",
        line_number,
    )


def javascript_symbol_call_targets(
    line: str,
    symbol_index: JavaScriptSymbolIndex,
) -> list[SymbolCallTarget]:
    targets: list[SymbolCallTarget] = []
    for match in JS_CALL_RE.finditer(line):
        name = match.group("name")
        if name in JS_CALL_SKIP_NAMES or name not in symbol_index.functions_by_name:
            continue
        targets.append(SymbolCallTarget(name=name, raw_target=name, call_kind="function"))
    return targets


def javascript_function_scope_state(line: str, brace_depth: int, seen_body: bool) -> tuple[int, bool]:
    opens = line.count("{")
    closes = line.count("}")
    next_seen_body = seen_body or opens > 0
    return brace_depth + opens - closes, next_seen_body
