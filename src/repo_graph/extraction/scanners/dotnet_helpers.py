"""C#, VB, and .NET scanner helpers."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from repo_graph.extraction.contracts import FileScanContext, ScanResult
from repo_graph.extraction.legacy_graph_helpers import interaction_properties, resolved_edge, unresolved_edge
from repo_graph.extraction.scanners.common import string_value
from repo_graph.extraction.scanners.interaction_helpers import (
    add_route,
    http_edges_for_target,
    http_target,
    route_entity,
    route_handler_edge,
    service_name_from_identifier,
    service_name_from_url,
    url_value,
)
from repo_graph.extraction.scanners.sql_helpers import (
    source_context_properties,
    sql_interaction_properties,
    stored_procedure_target,
)
from repo_graph.extraction.scanners.symbol_helpers import SymbolCallTarget, TypeMethodIndex, symbol_call_edges
from repo_graph.graph import Edge, Entity

DOTNET_PROJECT_SUFFIXES = {".csproj", ".fsproj", ".vbproj"}


DOTNET_BUILD_SUFFIXES = {".props", ".targets"}


SLN_PROJECT_RE = re.compile(r'^Project\("[^"]+"\)\s*=\s*"([^"]+)",\s*"([^"]+)"')


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


def dotnet_project_metadata(content: str) -> dict[str, str | None]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return dotnet_metadata_defaults()
    return dotnet_project_metadata_from_root(root)


def dotnet_project_metadata_from_root(root: ET.Element, default_name: str | None = None) -> dict[str, str | None]:
    package_id = first_xml_text(root, "PackageId")
    assembly_name = first_xml_text(root, "AssemblyName") or default_name
    root_namespace = first_xml_text(root, "RootNamespace")
    version = first_xml_text(root, "Version")
    return {
        "package_id": package_id,
        "assembly_name": assembly_name,
        "root_namespace": root_namespace,
        "version": version,
        "target_framework": first_xml_text(root, "TargetFramework"),
        "target_frameworks": first_xml_text(root, "TargetFrameworks"),
        "output_type": first_xml_text(root, "OutputType"),
    }


def dotnet_metadata_defaults() -> dict[str, str | None]:
    return {
        "package_id": None,
        "assembly_name": None,
        "root_namespace": None,
        "version": None,
        "target_framework": None,
        "target_frameworks": None,
        "output_type": None,
    }


def dotnet_package_entity(context: FileScanContext, metadata: dict[str, str | None]) -> Entity | None:
    package_name = metadata["package_id"] or metadata["assembly_name"]
    if not package_name:
        return None
    aliases = {package_name}
    if metadata["assembly_name"]:
        aliases.add(metadata["assembly_name"])
    return Entity(
        entity_type="package",
        name=package_name,
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases=aliases,
        properties={
            "ecosystem": "dotnet",
            "version": metadata["version"],
            "target_framework": metadata["target_framework"],
            "target_frameworks": metadata["target_frameworks"],
            "output_type": metadata["output_type"],
            "project": context.project.name if context.project else None,
        },
    )


def dotnet_package_references(root: ET.Element) -> Iterable[dict[str, str | None]]:
    for element in root.iter():
        if xml_local_name(element.tag) != "PackageReference":
            continue
        package_name = string_value(element.attrib.get("Include")) or string_value(element.attrib.get("Update"))
        if not package_name:
            continue
        yield {
            "name": package_name,
            "version": string_value(element.attrib.get("Version")) or first_child_text(element, "Version"),
            "raw_target": package_name,
        }


def dotnet_project_references(root: ET.Element) -> Iterable[dict[str, str | None]]:
    for element in root.iter():
        if xml_local_name(element.tag) != "ProjectReference":
            continue
        raw_target = string_value(element.attrib.get("Include"))
        if not raw_target:
            continue
        yield {
            "name": Path(raw_target).stem,
            "raw_target": raw_target,
            "normalized_target": Path(raw_target).stem,
        }


def packages_config_references(root: ET.Element) -> Iterable[dict[str, str | None]]:
    for element in root.iter():
        if xml_local_name(element.tag) != "package":
            continue
        package_name = string_value(element.attrib.get("id"))
        if not package_name:
            continue
        yield {
            "name": package_name,
            "version": string_value(element.attrib.get("version")),
            "raw_target": package_name,
        }


def solution_project_reference(line: str) -> dict[str, str | None] | None:
    match = SLN_PROJECT_RE.match(line)
    if not match:
        return None
    raw_path = match.group(2)
    if Path(raw_path).suffix.lower() not in DOTNET_PROJECT_SUFFIXES:
        return None
    return {
        "name": Path(raw_path).stem,
        "display_name": match.group(1),
        "raw_target": raw_path,
        "normalized_target": Path(raw_path).stem,
    }


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


def csharp_symbol_result(
    context: FileScanContext,
    symbol_kind: str,
    name: str,
    namespace: str | None,
    line_number: int,
    parent_name: str | None = None,
) -> ScanResult:
    result = ScanResult()
    entity_type = csharp_entity_type(symbol_kind)
    full_name = ".".join(part for part in (namespace, parent_name, name) if part)
    aliases = {name, full_name or name}
    if parent_name:
        aliases.add(f"{parent_name}.{name}")
    symbol = Entity(
        entity_type=entity_type,
        name=full_name or name,
        source_name=context.source.name,
        file_path=context.rel_path,
        line_number=line_number,
        aliases=aliases,
        properties={
            "symbol_kind": symbol_kind,
            "namespace": namespace,
            "parent": parent_name,
            "project": context.project.name if context.project else None,
        },
    )
    result.entities.append(symbol)
    result.edges.append(
        resolved_edge(
            context.file_entity,
            symbol,
            "DECLARES_SYMBOL",
            context.source.name,
            context.rel_path,
            "dotnet_symbol",
            line_number,
        )
    )
    return result


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


def csharp_controller_route_result(
    context: FileScanContext,
    method_name: str,
    attributes: Sequence[CSharpAttribute],
    route_prefix: str | None,
    type_name: str | None,
    line_number: int,
    handler: Entity | None = None,
) -> ScanResult:
    result = ScanResult()
    route_path = csharp_route_prefix(attributes, type_name, method_name)
    for attribute in attributes:
        method = csharp_http_attribute_method(attribute)
        if not method:
            continue
        attribute_path = csharp_first_string(attribute.args) or route_path or ""
        path = csharp_join_route_paths(
            route_prefix, csharp_replace_route_tokens(attribute_path, type_name, method_name)
        )
        route = route_entity(context, method, path, line_number, "dotnet_controller_route", method_name)
        result.entities.append(route)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                route,
                "DECLARES_ROUTE",
                context.source.name,
                context.rel_path,
                "dotnet_controller_route",
                line_number,
            )
        )
        if context.project:
            result.edges.append(
                resolved_edge(
                    context.project.entity,
                    route,
                    "EXPOSES_ROUTE",
                    context.source.name,
                    context.rel_path,
                    "dotnet_controller_route",
                    line_number,
                )
            )
        if handler:
            result.edges.append(route_handler_edge(context, route, handler, "dotnet_controller_route", line_number))
    return result


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


def csharp_minimal_route_result(context: FileScanContext, line: str, line_number: int) -> ScanResult:
    result = ScanResult()
    for match in CS_MINIMAL_ROUTE_RE.finditer(line):
        result.extend(
            add_route(
                context,
                match.group(1).upper(),
                csharp_unescape_string(match.group(2)),
                line_number,
                "dotnet_minimal_route",
            )
        )
    return result


def csharp_symbol_call_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity,
    current_type: str | None,
    method_index: TypeMethodIndex,
) -> list[Edge]:
    code = csharp_scope_code(line)
    targets = [
        *csharp_new_method_call_targets(code, method_index),
        *csharp_qualified_method_call_targets(code, current_type, method_index),
        *csharp_direct_method_call_targets(code, current_type, method_index),
    ]
    return symbol_call_edges(context, from_entity, targets, "dotnet_call", line_number)


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


def csharp_http_call_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
) -> list[Edge]:
    edges: list[Edge] = []
    source_entity = from_entity or context.file_entity
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
            edges.append(
                unresolved_edge(
                    source_entity,
                    target["service_name"],
                    "CALLS_SERVICE",
                    context.source.name,
                    context.rel_path,
                    "dotnet_http",
                    to_type="service",
                    line_number=line_number,
                    properties=target,
                )
            )
        else:
            edges.extend(
                http_edges_for_target(
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
    return edges


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


def config_file_entity(context: FileScanContext, config_kind: str) -> Entity:
    name = Path(context.rel_path).name
    return Entity(
        entity_type="config_file",
        name=name,
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases={name, context.rel_path},
        properties={
            "config_kind": config_kind,
            "ecosystem": "dotnet",
            "path": context.rel_path,
            "project": context.project.name if context.project else None,
        },
    )


def framework_config_values(context: FileScanContext, root: ET.Element) -> Iterable[Entity]:
    for section in root.iter():
        section_name = xml_local_name(section.tag)
        if section_name == "appSettings":
            for child in section:
                if xml_local_name(child.tag) == "add":
                    key = string_value(child.attrib.get("key"))
                    if key:
                        yield config_value_entity(
                            context,
                            key,
                            "app_setting",
                            {
                                "key": key,
                                "has_value": string_value(child.attrib.get("value")) is not None,
                                "target_url": url_value(child.attrib.get("value")),
                            },
                        )
        elif section_name == "connectionStrings":
            for child in section:
                if xml_local_name(child.tag) == "add":
                    name = string_value(child.attrib.get("name"))
                    if name:
                        yield config_value_entity(
                            context,
                            name,
                            "connection_string",
                            {
                                "key": name,
                                "provider_name": string_value(child.attrib.get("providerName")),
                                "has_value": string_value(child.attrib.get("connectionString")) is not None,
                            },
                        )
        elif section_name == "client":
            for child in section:
                if xml_local_name(child.tag) == "endpoint":
                    name = string_value(child.attrib.get("name")) or string_value(child.attrib.get("contract"))
                    address = url_value(child.attrib.get("address"))
                    if name or address:
                        yield config_value_entity(
                            context,
                            name or address or "endpoint",
                            "wcf_endpoint",
                            {
                                "key": name,
                                "contract": string_value(child.attrib.get("contract")),
                                "binding": string_value(child.attrib.get("binding")),
                                "target_url": address,
                            },
                        )


def config_value_entity(
    context: FileScanContext,
    name: str,
    value_kind: str,
    properties: dict[str, Any],
) -> Entity:
    entity_name = f"{value_kind}:{name}"
    return Entity(
        entity_type="config_value",
        name=entity_name,
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases={name, entity_name},
        properties={
            "display_name": name,
            "value_kind": value_kind,
            "project": context.project.name if context.project else None,
            **{key: value for key, value in properties.items() if value is not None},
        },
    )


def config_service_edge(config_value: Entity, context: FileScanContext, parser: str) -> Edge | None:
    raw_target = config_value.properties.get("target_url")
    if not isinstance(raw_target, str):
        return None
    key = config_value.properties.get("key")
    contract = config_value.properties.get("contract")
    service_name = service_name_from_identifier(key or contract or service_name_from_url(raw_target))
    target = http_target(raw_target, "GET")
    target["dependency_scope"] = "configuration"
    target["interaction_kind"] = "service_configuration"
    target["service_name"] = service_name
    return unresolved_edge(
        config_value,
        service_name,
        "CONFIGURES_SERVICE",
        context.source.name,
        context.rel_path,
        parser,
        to_type="service",
        properties=target,
    )


def vb_symbol_result(
    context: FileScanContext,
    symbol_kind: str,
    name: str,
    namespace: str | None,
    line_number: int,
    parent_name: str | None = None,
) -> ScanResult:
    result = ScanResult()
    entity_type = "function" if symbol_kind in {"function", "sub"} else symbol_kind
    full_name = ".".join(part for part in (namespace, parent_name, name) if part)
    aliases = {name, full_name or name}
    if parent_name:
        aliases.add(f"{parent_name}.{name}")
    symbol = Entity(
        entity_type=entity_type,
        name=full_name or name,
        source_name=context.source.name,
        file_path=context.rel_path,
        line_number=line_number,
        aliases=aliases,
        properties={
            "symbol_kind": symbol_kind,
            "namespace": namespace,
            "parent": parent_name,
            "project": context.project.name if context.project else None,
        },
    )
    result.entities.append(symbol)
    result.edges.append(
        resolved_edge(
            context.file_entity,
            symbol,
            "DECLARES_SYMBOL",
            context.source.name,
            context.rel_path,
            "vb_symbol",
            line_number,
        )
    )
    return result


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


def vb_contract_route_result(
    context: FileScanContext,
    method_name: str,
    attributes: Sequence[str],
    line_number: int,
    handler: Entity | None = None,
) -> ScanResult:
    result = ScanResult()
    framework = legacy_contract_framework(attributes)
    if not framework:
        return result
    service_path = legacy_dotnet_service_path(context.rel_path, framework)
    route = route_entity(
        context,
        "POST",
        f"{service_path}/{method_name}",
        line_number,
        "vb_contract_route",
        operation_name=method_name,
    )
    result.entities.append(route)
    result.edges.append(
        resolved_edge(
            context.file_entity,
            route,
            "DECLARES_ROUTE",
            context.source.name,
            context.rel_path,
            "vb_contract_route",
            line_number,
        )
    )
    if context.project:
        result.edges.append(
            resolved_edge(
                context.project.entity,
                route,
                "EXPOSES_ROUTE",
                context.source.name,
                context.rel_path,
                "vb_contract_route",
                line_number,
            )
        )
    if handler:
        result.edges.append(route_handler_edge(context, route, handler, "vb_contract_route", line_number))
    return result


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


def vb_symbol_call_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity,
    current_type: str | None,
    method_index: TypeMethodIndex,
) -> list[Edge]:
    code = vb_scope_code(line)
    targets = [
        *vb_new_method_call_targets(code, method_index),
        *vb_qualified_method_call_targets(code, current_type, method_index),
        *vb_direct_method_call_targets(code, current_type, method_index),
    ]
    return symbol_call_edges(context, from_entity, targets, "vb_call", line_number)


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


def vb_service_call_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
) -> list[Edge]:
    edges: list[Edge] = []
    source_entity = from_entity or context.file_entity
    extra_properties = source_context_properties(from_entity)
    for match in VB_HTTP_LITERAL_RE.finditer(line):
        edges.extend(
            legacy_http_edges_for_target(
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
        edges.append(
            unresolved_edge(
                source_entity,
                service_name,
                "CALLS_SERVICE",
                context.source.name,
                context.rel_path,
                "vb_config_service",
                to_type="service",
                line_number=line_number,
                properties=properties,
            )
        )
    return edges


def legacy_http_edges_for_target(
    context: FileScanContext,
    raw_target: str,
    line_number: int,
    parser: str,
    client: str,
    from_entity: Entity | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[Edge]:
    source_entity = from_entity or context.file_entity
    parsed = urlparse(raw_target)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        target = http_target(raw_target, "GET")
        target["service_name"] = service_name_from_url(raw_target)
        target["client"] = client
        if extra_properties:
            target.update(extra_properties)
        return [
            unresolved_edge(
                source_entity,
                target["service_name"],
                "CALLS_SERVICE",
                context.source.name,
                context.rel_path,
                parser,
                to_type="service",
                line_number=line_number,
                properties=target,
            )
        ]
    return http_edges_for_target(
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


def vb_sql_command_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
) -> list[Edge]:
    targets = [match.group(1) for match in VB_COMMAND_TEXT_RE.finditer(line)]
    targets.extend(match.group(1) for match in VB_SQL_COMMAND_RE.finditer(line))
    edges: list[Edge] = []
    source_entity = from_entity or context.file_entity
    extra_properties = source_context_properties(from_entity)
    for target in targets:
        normalized = stored_procedure_target(target)
        if not normalized:
            continue
        edges.append(
            unresolved_edge(
                source_entity,
                normalized,
                "CALLS_SQL",
                context.source.name,
                context.rel_path,
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
    return edges


def xml_root(content: str, context: FileScanContext) -> ET.Element:
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML {context.source.name}/{context.rel_path}: {exc}") from exc


def first_xml_text(root: ET.Element, name: str) -> str | None:
    for element in root.iter():
        if xml_local_name(element.tag) == name:
            value = string_value(element.text)
            if value:
                return value
    return None


def first_child_text(root: ET.Element, name: str) -> str | None:
    for child in root:
        if xml_local_name(child.tag) == name:
            return string_value(child.text)
    return None


def xml_local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]
