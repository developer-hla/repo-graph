"""C# and legacy .NET scanners."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext, ScanResult
from repo_graph.extraction.fact_helpers import entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import EntityFact
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
    csharp_controller_route_facts,
    csharp_function_scope_state,
    csharp_http_call_facts,
    csharp_method_index,
    csharp_minimal_route_facts,
    csharp_route_prefix,
    csharp_should_clear_attributes,
    csharp_symbol_call_facts,
    csharp_symbol_facts,
    vb_contract_route_facts,
    vb_method_index,
    vb_service_call_facts,
    vb_sql_command_facts,
    vb_symbol_call_facts,
    vb_symbol_facts,
)
from repo_graph.extraction.scanners.interaction_helpers import route_entity_fact
from repo_graph.extraction.scanners.sql_helpers import sql_reference_facts_for_line


class LegacyDotnetEndpointExtractor:
    name = "legacy_dotnet_endpoint"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".asmx", ".svc"}

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        suffix = Path(context.rel_path).suffix.lower()
        framework = "asmx" if suffix == ".asmx" else "wcf"
        path = "/" + context.rel_path.replace("\\", "/")
        route = route_entity_fact(context, "POST", path, 1, framework, operation_name=None)
        result.facts.entities.append(route)
        result.facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                route.reference,
                "DECLARES_ROUTE",
                context,
                self.name,
                1,
            )
        )
        if context.project:
            result.facts.relationships.append(
                resolved_relationship_fact(
                    entity_reference(context.project.entity),
                    route.reference,
                    "EXPOSES_ROUTE",
                    context,
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
        current_function: EntityFact | None = None
        current_function_brace_depth = 0
        current_function_seen_body = False
        pending_attributes: list[CSharpAttribute] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            result.facts.extend(csharp_minimal_route_facts(context, line, line_number))
            result.facts.relationships.extend(csharp_http_call_facts(context, line, line_number))
            if current_function:
                result.facts.relationships.extend(
                    csharp_http_call_facts(context, line, line_number, from_entity=current_function)
                )
                result.facts.relationships.extend(
                    sql_reference_facts_for_line(context, line, line_number, from_entity=current_function)
                )
                result.facts.relationships.extend(
                    csharp_symbol_call_facts(
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
                result.facts.extend(
                    csharp_symbol_facts(
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
                symbol_facts = csharp_symbol_facts(
                    context,
                    "method",
                    method_name,
                    namespace,
                    line_number,
                    parent_name=current_type,
                )
                current_function = symbol_facts.entities[0] if symbol_facts.entities else None
                result.facts.extend(symbol_facts)
                result.facts.extend(
                    csharp_controller_route_facts(
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
        current_function: EntityFact | None = None
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
                result.facts.extend(
                    vb_symbol_facts(context, type_match.group(1).lower(), current_type, namespace, line_number)
                )
                pending_attributes = []
                continue

            method_match = VB_METHOD_RE.match(line)
            if method_match:
                method_name = method_match.group(2)
                symbol_facts = vb_symbol_facts(
                    context,
                    method_match.group(1).lower(),
                    method_name,
                    namespace,
                    line_number,
                    parent_name=current_type,
                )
                current_function = symbol_facts.entities[0] if symbol_facts.entities else None
                result.facts.extend(symbol_facts)
                result.facts.extend(
                    vb_contract_route_facts(context, method_name, pending_attributes, line_number, current_function)
                )
                pending_attributes = []

            result.facts.relationships.extend(vb_service_call_facts(context, line, line_number))
            result.facts.relationships.extend(vb_sql_command_facts(context, line, line_number))
            if current_function:
                result.facts.relationships.extend(
                    vb_service_call_facts(context, line, line_number, from_entity=current_function)
                )
                result.facts.relationships.extend(
                    vb_sql_command_facts(context, line, line_number, from_entity=current_function)
                )
                if not method_match:
                    result.facts.relationships.extend(
                        vb_symbol_call_facts(
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
