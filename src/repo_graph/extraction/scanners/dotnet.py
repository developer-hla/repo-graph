"""C# and legacy .NET scanners."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext, ScanResult
from repo_graph.extraction.legacy_graph_helpers import resolved_edge
from repo_graph.extraction.scanners.common import first_entity
from repo_graph.extraction.scanners.dotnet_helpers import (
    CS_METHOD_RE,
    CS_NAMESPACE_RE,
    CS_TYPE_RE,
    VB_ATTRIBUTE_RE,
    VB_END_METHOD_RE,
    VB_METHOD_RE,
    VB_NAMESPACE_RE,
    VB_TYPE_RE,
    CSharpAttribute,
    csharp_attributes,
    csharp_controller_route_result,
    csharp_function_scope_state,
    csharp_http_call_edges,
    csharp_method_index,
    csharp_minimal_route_result,
    csharp_route_prefix,
    csharp_should_clear_attributes,
    csharp_symbol_call_edges,
    csharp_symbol_result,
    vb_contract_route_result,
    vb_method_index,
    vb_service_call_edges,
    vb_sql_command_edges,
    vb_symbol_call_edges,
    vb_symbol_result,
)
from repo_graph.extraction.scanners.interaction_helpers import route_entity
from repo_graph.extraction.scanners.sql_helpers import sql_reference_edges_for_line
from repo_graph.graph import Entity


class LegacyDotnetEndpointExtractor:
    name = "legacy_dotnet_endpoint"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".asmx", ".svc"}

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        suffix = Path(context.rel_path).suffix.lower()
        framework = "asmx" if suffix == ".asmx" else "wcf"
        path = "/" + context.rel_path.replace("\\", "/")
        route = route_entity(context, "POST", path, 1, framework, operation_name=None)
        result.entities.append(route)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                route,
                "DECLARES_ROUTE",
                context.source.name,
                context.rel_path,
                self.name,
                1,
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
                    self.name,
                    1,
                )
            )
        return result


class CSharpCodeExtractor:
    name = "csharp_code"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".cs"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        method_index = csharp_method_index(content)
        namespace: str | None = None
        current_type: str | None = None
        current_route_prefix: str | None = None
        current_function: Entity | None = None
        current_function_brace_depth = 0
        current_function_seen_body = False
        pending_attributes: list[CSharpAttribute] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            result.extend(csharp_minimal_route_result(context, line, line_number))
            result.edges.extend(csharp_http_call_edges(context, line, line_number))
            if current_function:
                result.edges.extend(csharp_http_call_edges(context, line, line_number, from_entity=current_function))
                result.edges.extend(
                    sql_reference_edges_for_line(context, line, line_number, from_entity=current_function)
                )
                result.edges.extend(
                    csharp_symbol_call_edges(
                        context,
                        line,
                        line_number,
                        from_entity=current_function,
                        current_type=current_type,
                        method_index=method_index,
                    )
                )

            attributes = csharp_attributes(line, line_number)
            if attributes:
                pending_attributes.extend(attributes)
                current_function_brace_depth, current_function_seen_body = csharp_function_scope_state(
                    line,
                    current_function_brace_depth,
                    current_function_seen_body,
                )
                continue

            namespace_match = CS_NAMESPACE_RE.match(line)
            if namespace_match:
                namespace = namespace_match.group(1)

            type_match = CS_TYPE_RE.match(line)
            if type_match:
                current_function = None
                current_function_brace_depth = 0
                current_function_seen_body = False
                current_type = type_match.group(2)
                current_route_prefix = csharp_route_prefix(pending_attributes, current_type, None)
                result.extend(
                    csharp_symbol_result(
                        context,
                        type_match.group(1).lower(),
                        current_type,
                        namespace,
                        line_number,
                    )
                )
                pending_attributes = []
                continue

            method_match = CS_METHOD_RE.match(line)
            if method_match:
                method_name = method_match.group(1)
                symbol_result = csharp_symbol_result(
                    context,
                    "method",
                    method_name,
                    namespace,
                    line_number,
                    parent_name=current_type,
                )
                current_function = first_entity(symbol_result)
                result.extend(symbol_result)
                result.extend(
                    csharp_controller_route_result(
                        context,
                        method_name,
                        pending_attributes,
                        current_route_prefix,
                        current_type,
                        line_number,
                        current_function,
                    )
                )
                current_function_brace_depth, current_function_seen_body = csharp_function_scope_state(line, 0, False)
                pending_attributes = []
                continue

            if csharp_should_clear_attributes(line):
                pending_attributes = []
            if current_function:
                current_function_brace_depth, current_function_seen_body = csharp_function_scope_state(
                    line,
                    current_function_brace_depth,
                    current_function_seen_body,
                )
                if current_function_seen_body and current_function_brace_depth <= 0 and "}" in line:
                    current_function = None
                    current_function_brace_depth = 0
                    current_function_seen_body = False

        return result


class VbCodeExtractor:
    name = "vb_code"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".vb"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        method_index = vb_method_index(content)
        namespace: str | None = None
        current_type: str | None = None
        current_function: Entity | None = None
        pending_attributes: list[str] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            attribute_match = VB_ATTRIBUTE_RE.match(line)
            if attribute_match:
                pending_attributes.append(attribute_match.group(1).lower())
                continue

            namespace_match = VB_NAMESPACE_RE.match(line)
            if namespace_match:
                namespace = namespace_match.group(1)

            type_match = VB_TYPE_RE.match(line)
            if type_match:
                current_type = type_match.group(2)
                current_function = None
                result.extend(
                    vb_symbol_result(context, type_match.group(1).lower(), current_type, namespace, line_number)
                )
                pending_attributes = []
                continue

            method_match = VB_METHOD_RE.match(line)
            if method_match:
                method_name = method_match.group(2)
                symbol_result = vb_symbol_result(
                    context,
                    method_match.group(1).lower(),
                    method_name,
                    namespace,
                    line_number,
                    parent_name=current_type,
                )
                current_function = first_entity(symbol_result)
                result.extend(symbol_result)
                result.extend(
                    vb_contract_route_result(context, method_name, pending_attributes, line_number, current_function)
                )
                pending_attributes = []

            result.edges.extend(vb_service_call_edges(context, line, line_number))
            result.edges.extend(vb_sql_command_edges(context, line, line_number))
            if current_function:
                result.edges.extend(vb_service_call_edges(context, line, line_number, from_entity=current_function))
                result.edges.extend(vb_sql_command_edges(context, line, line_number, from_entity=current_function))
                if not method_match:
                    result.edges.extend(
                        vb_symbol_call_edges(
                            context,
                            line,
                            line_number,
                            from_entity=current_function,
                            current_type=current_type,
                            method_index=method_index,
                        )
                    )

            if not attribute_match and line.strip():
                pending_attributes = []
            if VB_END_METHOD_RE.match(line):
                current_function = None
        return result
