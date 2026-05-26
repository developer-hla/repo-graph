"""C# and VB code scanner helpers."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import (
    entity_fact,
    entity_reference,
    resolved_relationship_fact,
    unresolved_relationship_fact,
)
from repo_graph.extraction.facts import EntityFact, FactBatch, RelationshipFact
from repo_graph.extraction.interaction_properties import interaction_properties
from repo_graph.extraction.scanners.interaction_helpers import (
    add_route_facts,
    http_facts_for_target,
    http_target,
    route_entity_fact,
    route_handler_fact,
    service_name_from_identifier,
    service_name_from_url,
)
from repo_graph.extraction.scanners.sql_helpers import (
    source_context_properties,
    sql_interaction_properties,
    stored_procedure_target,
)
from repo_graph.extraction.scanners.symbol_helpers import (
    SymbolCallTarget,
    TypeMethodIndex,
    symbol_call_facts,
)

CS_ATTRIBUTE_LINE_RE = re.compile(r"^\s*\[(?P<body>.+)\]\s*$")


CS_ATTRIBUTE_ITEM_RE = re.compile(r"(?P<name>[A-Za-z_][\w.]*)(?:Attribute)?\s*(?:\((?P<args>[^)]*)\))?")


CS_NAMESPACE_RE = re.compile(r"^\s*namespace\s+([A-Za-z_][\w.]*)(?:\s*;|\s*\{)?")


CS_TYPE_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|internal|static|sealed|abstract|partial)\s+)*"
    r"(class|record|interface|struct)\s+([A-Za-z_]\w*)"
)


CS_METHOD_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|internal|static|virtual|override|async|sealed|new|partial|extern|unsafe)"
    r"\s+)+(?:[\w<>\[\],.?]+\s+)+([A-Za-z_]\w*)\s*(?:<[^>]+>)?\s*\("
)


CS_MINIMAL_ROUTE_RE = re.compile(
    r"\b[A-Za-z_]\w*\s*\.\s*Map(Get|Post|Put|Patch|Delete|Head|Options)\s*\(\s*"
    r"(?:\$@|@\$|\$|@)?\"((?:\"\"|\\.|[^\"])*)\"",
    re.IGNORECASE,
)


CS_HTTP_CALL_RE = re.compile(
    r"\.\s*(Get|Post|Put|Patch|Delete)Async\s*\(\s*(?:\$@|@\$|\$|@)?\"((?:\"\"|\\.|[^\"])*)\"",
    re.IGNORECASE,
)


CS_NEW_METHOD_CALL_RE = re.compile(r"\bnew\s+(?P<class>[A-Za-z_]\w*)\s*\([^)]*\)\s*\.\s*(?P<method>[A-Za-z_]\w*)\s*\(")


CS_QUALIFIED_METHOD_CALL_RE = re.compile(r"\b(?P<receiver>this|[A-Za-z_]\w*)\s*\.\s*(?P<method>[A-Za-z_]\w*)\s*\(")


CS_DIRECT_METHOD_CALL_RE = re.compile(r"(?<![\.\w])(?P<method>[A-Za-z_]\w*)\s*\(")


VB_ATTRIBUTE_RE = re.compile(r"^\s*<\s*([A-Za-z_][\w.]*)", re.IGNORECASE)


VB_NAMESPACE_RE = re.compile(r"^\s*Namespace\s+([A-Za-z_][\w.]*)", re.IGNORECASE)


VB_TYPE_RE = re.compile(
    r"^\s*(?:(?:Public|Private|Friend|Protected|Partial|MustInherit|NotInheritable)\s+)*"
    r"(Class|Module|Interface)\s+([A-Za-z_]\w*)",
    re.IGNORECASE,
)


VB_METHOD_RE = re.compile(
    r"^\s*(?:(?:Public|Private|Protected|Friend|Shared|Overrides|Overridable|Async|Static)\s+)*"
    r"(Function|Sub)\s+([A-Za-z_]\w*)",
    re.IGNORECASE,
)


VB_END_METHOD_RE = re.compile(r"^\s*End\s+(Function|Sub)\b", re.IGNORECASE)


VB_CONFIG_SETTING_RE = re.compile(r"ConfigurationManager\.AppSettings\s*\(\s*\"([^\"]+)\"\s*\)", re.IGNORECASE)


VB_COMMAND_TEXT_RE = re.compile(r"\.CommandText\s*=\s*\"([^\"]+)\"", re.IGNORECASE)


VB_SQL_COMMAND_RE = re.compile(r"New\s+SqlCommand\s*\(\s*\"([^\"]+)\"", re.IGNORECASE)


VB_HTTP_LITERAL_RE = re.compile(
    r"(?:WebRequest\.Create|WebClient\(\)\.(?:DownloadString|OpenRead|UploadString)|\.DownloadString|\.OpenRead)"
    r"\s*\(\s*\"([^\"]+)\"",
    re.IGNORECASE,
)


VB_NEW_METHOD_CALL_RE = re.compile(
    r"\bNew\s+(?P<class>[A-Za-z_]\w*)\s*\([^)]*\)\s*\.\s*(?P<method>[A-Za-z_]\w*)\s*\(",
    re.IGNORECASE,
)


VB_QUALIFIED_METHOD_CALL_RE = re.compile(
    r"\b(?P<receiver>Me|[A-Za-z_]\w*)\s*\.\s*(?P<method>[A-Za-z_]\w*)\s*\(",
    re.IGNORECASE,
)


VB_DIRECT_METHOD_CALL_RE = re.compile(r"(?<![\.\w])(?P<method>[A-Za-z_]\w*)\s*\(", re.IGNORECASE)


@dataclass(frozen=True)
class CSharpAttribute:
    name: str
    args: str | None
    line_number: int


def csharp_attributes(line: str, line_number: int) -> list[CSharpAttribute]:
    match = CS_ATTRIBUTE_LINE_RE.match(line)
    if not match:
        return []
    return [
        CSharpAttribute(
            name=csharp_attribute_name(attribute_match.group("name")),
            args=attribute_match.group("args"),
            line_number=line_number,
        )
        for attribute_match in CS_ATTRIBUTE_ITEM_RE.finditer(match.group("body"))
    ]


def csharp_attribute_name(name: str) -> str:
    return name.rsplit(".", 1)[-1].removesuffix("Attribute").lower()


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


def csharp_route_prefix(
    attributes: Sequence[CSharpAttribute],
    type_name: str | None,
    method_name: str | None,
) -> str | None:
    route_attribute = next((attribute for attribute in attributes if attribute.name == "route"), None)
    if not route_attribute:
        return None
    route = csharp_first_string(route_attribute.args)
    if route is None:
        return None
    return csharp_replace_route_tokens(route, type_name, method_name)


def csharp_controller_route_facts(
    context: FileScanContext,
    method_name: str,
    attributes: Sequence[CSharpAttribute],
    route_prefix: str | None,
    type_name: str | None,
    line_number: int,
    handler: EntityFact | None = None,
) -> FactBatch:
    facts = FactBatch()
    route_path = csharp_route_prefix(attributes, type_name, method_name)
    for attribute in attributes:
        method = csharp_http_attribute_method(attribute)
        if not method:
            continue
        attribute_path = csharp_first_string(attribute.args) or route_path or ""
        path = csharp_join_route_paths(
            route_prefix, csharp_replace_route_tokens(attribute_path, type_name, method_name)
        )
        route = route_entity_fact(context, method, path, line_number, "dotnet_controller_route", method_name)
        facts.entities.append(route)
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                route.reference,
                "DECLARES_ROUTE",
                context,
                "dotnet_controller_route",
                line_number,
            )
        )
        if context.project:
            facts.relationships.append(
                resolved_relationship_fact(
                    entity_reference(context.project.entity),
                    route.reference,
                    "EXPOSES_ROUTE",
                    context,
                    "dotnet_controller_route",
                    line_number,
                )
            )
        if handler:
            facts.relationships.append(
                route_handler_fact(context, route, handler, "dotnet_controller_route", line_number)
            )
    return facts


def csharp_http_attribute_method(attribute: CSharpAttribute) -> str | None:
    methods = {
        "httpget": "GET",
        "httppost": "POST",
        "httpput": "PUT",
        "httppatch": "PATCH",
        "httpdelete": "DELETE",
        "httphead": "HEAD",
        "httpoptions": "OPTIONS",
    }
    return methods.get(attribute.name)


def csharp_minimal_route_facts(context: FileScanContext, line: str, line_number: int) -> FactBatch:
    facts = FactBatch()
    for match in CS_MINIMAL_ROUTE_RE.finditer(line):
        facts.extend(
            add_route_facts(
                context,
                match.group(1).upper(),
                csharp_unescape_string(match.group(2)),
                line_number,
                "dotnet_minimal_route",
            )
        )
    return facts


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


def csharp_http_call_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    facts: list[RelationshipFact] = []
    source_ref = entity_reference(from_entity or context.file_entity)
    extra_properties = source_context_properties(from_entity)
    for match in CS_HTTP_CALL_RE.finditer(line):
        method = match.group(1).upper()
        raw_target = csharp_unescape_string(match.group(2))
        parsed = urlparse(raw_target)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            target = http_target(raw_target, method)
            target["service_name"] = service_name_from_url(raw_target)
            target["client"] = "HttpClient"
            target.update(extra_properties)
            facts.append(
                unresolved_relationship_fact(
                    source_ref,
                    target["service_name"],
                    "CALLS_SERVICE",
                    context,
                    "dotnet_http",
                    to_type="service",
                    line_number=line_number,
                    properties=target,
                )
            )
        else:
            facts.extend(
                http_facts_for_target(
                    context,
                    method,
                    raw_target,
                    line_number,
                    "dotnet_http",
                    client="HttpClient",
                    from_entity=from_entity,
                    extra_properties=extra_properties,
                )
            )
    return facts


def csharp_first_string(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(?:\$@|@\$|\$|@)?\"((?:\"\"|\\.|[^\"])*)\"", value)
    if not match:
        return None
    return csharp_unescape_string(match.group(1))


def csharp_unescape_string(value: str) -> str:
    return value.replace('""', '"').replace(r"\"", '"').replace(r"\\", "\\")


def csharp_replace_route_tokens(value: str, type_name: str | None, method_name: str | None) -> str:
    controller_name = type_name.removesuffix("Controller") if type_name else ""
    route = re.sub(r"\[controller\]", controller_name, value, flags=re.IGNORECASE)
    return re.sub(r"\[action\]", method_name or "", route, flags=re.IGNORECASE)


def csharp_join_route_paths(prefix: str | None, path: str) -> str:
    if path.startswith("/"):
        return path
    parts = [part.strip("/") for part in (prefix, path) if part and part.strip("/")]
    return "/" + "/".join(parts) if parts else "/"


def csharp_should_clear_attributes(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped and not stripped.startswith("//"))


def csharp_function_scope_state(line: str, brace_depth: int, seen_body: bool) -> tuple[int, bool]:
    code = csharp_scope_code(line)
    seen_body = seen_body or "{" in code
    brace_depth += code.count("{") - code.count("}")
    return brace_depth, seen_body


def csharp_scope_code(line: str) -> str:
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', line)


def vb_symbol_facts(
    context: FileScanContext,
    symbol_kind: str,
    name: str,
    namespace: str | None,
    line_number: int,
    parent_name: str | None = None,
) -> FactBatch:
    facts = FactBatch()
    entity_type = "function" if symbol_kind in {"function", "sub"} else symbol_kind
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
            "vb_symbol",
            line_number,
        )
    )
    return facts


def vb_method_index(content: str) -> TypeMethodIndex:
    current_type: str | None = None
    type_methods: dict[str, set[str]] = {}
    for line in content.splitlines():
        type_match = VB_TYPE_RE.match(line)
        if type_match:
            current_type = type_match.group(2)
            continue
        method_match = VB_METHOD_RE.match(line)
        if current_type and method_match:
            type_methods.setdefault(current_type, set()).add(method_match.group(2))
    return TypeMethodIndex(type_methods={type_name: frozenset(methods) for type_name, methods in type_methods.items()})


def vb_contract_route_facts(
    context: FileScanContext,
    method_name: str,
    attributes: Sequence[str],
    line_number: int,
    handler: EntityFact | None = None,
) -> FactBatch:
    facts = FactBatch()
    framework = legacy_contract_framework(attributes)
    if not framework:
        return facts
    service_path = legacy_dotnet_service_path(context.rel_path, framework)
    route = route_entity_fact(
        context,
        "POST",
        f"{service_path}/{method_name}",
        line_number,
        "vb_contract_route",
        operation_name=method_name,
    )
    facts.entities.append(route)
    facts.relationships.append(
        resolved_relationship_fact(
            entity_reference(context.file_entity),
            route.reference,
            "DECLARES_ROUTE",
            context,
            "vb_contract_route",
            line_number,
        )
    )
    if context.project:
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.project.entity),
                route.reference,
                "EXPOSES_ROUTE",
                context,
                "vb_contract_route",
                line_number,
            )
        )
    if handler:
        facts.relationships.append(route_handler_fact(context, route, handler, "vb_contract_route", line_number))
    return facts


def legacy_contract_framework(attributes: Sequence[str]) -> str | None:
    names = {attribute.rsplit(".", 1)[-1].lower() for attribute in attributes}
    if "webmethod" in names:
        return "asmx"
    if "operationcontract" in names:
        return "wcf"
    return None


def legacy_dotnet_service_path(rel_path: str, framework: str) -> str:
    path = rel_path.replace("\\", "/")
    lower_path = path.lower()
    if (framework == "asmx" and lower_path.endswith(".asmx.vb")) or (
        framework == "wcf" and lower_path.endswith(".svc.vb")
    ):
        path = path[:-3]
    elif lower_path.endswith(".vb"):
        suffix = ".asmx" if framework == "asmx" else ".svc"
        path = f"{path[:-3]}{suffix}"
    return "/" + path


def vb_symbol_call_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact,
    current_type: str | None,
    method_index: TypeMethodIndex,
) -> list[RelationshipFact]:
    code = vb_scope_code(line)
    targets = [
        *vb_new_method_call_targets(code, method_index),
        *vb_qualified_method_call_targets(code, current_type, method_index),
        *vb_direct_method_call_targets(code, current_type, method_index),
    ]
    return symbol_call_facts(context, from_entity, targets, "vb_call", line_number)


def vb_new_method_call_targets(code: str, method_index: TypeMethodIndex) -> list[SymbolCallTarget]:
    return [
        SymbolCallTarget(
            f"{match.group('class')}.{match.group('method')}",
            f"New {match.group('class')}().{match.group('method')}",
            "class_method",
            receiver=match.group("class"),
        )
        for match in VB_NEW_METHOD_CALL_RE.finditer(code)
        if method_index.has_method(match.group("class"), match.group("method"))
    ]


def vb_qualified_method_call_targets(
    code: str,
    current_type: str | None,
    method_index: TypeMethodIndex,
) -> list[SymbolCallTarget]:
    targets: list[SymbolCallTarget] = []
    for match in VB_QUALIFIED_METHOD_CALL_RE.finditer(code):
        receiver = match.group("receiver")
        method_name = match.group("method")
        if receiver.lower() == "me" and method_index.has_method(current_type, method_name):
            targets.append(
                SymbolCallTarget(f"{current_type}.{method_name}", f"Me.{method_name}", "instance_method", receiver)
            )
        elif method_index.has_method(receiver, method_name):
            targets.append(
                SymbolCallTarget(f"{receiver}.{method_name}", f"{receiver}.{method_name}", "class_method", receiver)
            )
    return targets


def vb_direct_method_call_targets(
    code: str,
    current_type: str | None,
    method_index: TypeMethodIndex,
) -> list[SymbolCallTarget]:
    return [
        SymbolCallTarget(f"{current_type}.{method_name}", method_name, "direct")
        for match in VB_DIRECT_METHOD_CALL_RE.finditer(code)
        if (method_name := match.group("method")) and method_index.has_method(current_type, method_name)
    ]


def vb_scope_code(line: str) -> str:
    return re.sub(r'"(?:[^"]|"")*"', '""', line)


def vb_service_call_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    facts: list[RelationshipFact] = []
    source_ref = entity_reference(from_entity or context.file_entity)
    extra_properties = source_context_properties(from_entity)
    for match in VB_HTTP_LITERAL_RE.finditer(line):
        facts.extend(
            legacy_http_facts_for_target(
                context,
                match.group(1),
                line_number,
                "vb_http",
                client=legacy_http_client(match.group(0)),
                from_entity=from_entity,
                extra_properties=extra_properties,
            )
        )
    for match in VB_CONFIG_SETTING_RE.finditer(line):
        key = match.group(1)
        service_name = service_name_from_identifier(key)
        properties = interaction_properties(
            "application",
            "runtime",
            "service_call",
            raw_target=key,
            normalized_target=service_name,
            config_key=key,
            service_name=service_name,
        )
        properties.update(extra_properties)
        facts.append(
            unresolved_relationship_fact(
                source_ref,
                service_name,
                "CALLS_SERVICE",
                context,
                "vb_config_service",
                to_type="service",
                line_number=line_number,
                properties=properties,
            )
        )
    return facts


def legacy_http_facts_for_target(
    context: FileScanContext,
    raw_target: str,
    line_number: int,
    parser: str,
    client: str,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[RelationshipFact]:
    source_ref = entity_reference(from_entity or context.file_entity)
    parsed = urlparse(raw_target)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        target = http_target(raw_target, "GET")
        target["service_name"] = service_name_from_url(raw_target)
        target["client"] = client
        if extra_properties:
            target.update(extra_properties)
        return [
            unresolved_relationship_fact(
                source_ref,
                target["service_name"],
                "CALLS_SERVICE",
                context,
                parser,
                to_type="service",
                line_number=line_number,
                properties=target,
            )
        ]
    return http_facts_for_target(
        context,
        "GET",
        raw_target,
        line_number,
        parser,
        client=client,
        from_entity=from_entity,
        extra_properties=extra_properties,
    )


def legacy_http_client(evidence: str) -> str:
    if "WebRequest" in evidence:
        return "WebRequest"
    if "WebClient" in evidence:
        return "WebClient"
    return "legacy_http_client"


def vb_sql_command_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    targets = [match.group(1) for match in VB_COMMAND_TEXT_RE.finditer(line)]
    targets.extend(match.group(1) for match in VB_SQL_COMMAND_RE.finditer(line))
    facts: list[RelationshipFact] = []
    source_ref = entity_reference(from_entity or context.file_entity)
    extra_properties = source_context_properties(from_entity)
    for target in targets:
        normalized = stored_procedure_target(target)
        if not normalized:
            continue
        facts.append(
            unresolved_relationship_fact(
                source_ref,
                normalized,
                "CALLS_SQL",
                context,
                "vb_sql_command",
                to_type="stored_procedure",
                line_number=line_number,
                properties=sql_interaction_properties(
                    target,
                    "EXECUTE",
                    "stored_procedure",
                    extra_properties=extra_properties,
                ),
            )
        )
    return facts
