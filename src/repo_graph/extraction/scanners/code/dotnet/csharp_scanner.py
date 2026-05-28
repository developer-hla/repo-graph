"""C# code scanner."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext, ScannerMetadataMixin, ScannerSpec
from repo_graph.extraction.facts import EntityFact, FactBatch
from repo_graph.extraction.scanners.cache.facts import cache_facts_for_line
from repo_graph.extraction.scanners.code.dotnet.csharp_interactions import csharp_http_call_facts
from repo_graph.extraction.scanners.code.dotnet.csharp_routes import (
    csharp_controller_route_facts,
    csharp_minimal_route_facts,
    csharp_route_prefix,
)
from repo_graph.extraction.scanners.code.dotnet.csharp_symbols import (
    CS_METHOD_RE,
    CS_TYPE_RE,
    csharp_method_index,
    csharp_symbol_call_facts,
    csharp_symbol_facts,
)
from repo_graph.extraction.scanners.code.dotnet.csharp_syntax import (
    CS_NAMESPACE_RE,
    CSharpAttribute,
    csharp_attributes,
    csharp_function_scope_state,
    csharp_should_clear_attributes,
)
from repo_graph.extraction.scanners.messaging.facts import message_facts_for_line
from repo_graph.extraction.scanners.sql.references import sql_reference_facts_for_line
from repo_graph.extraction.scanners.storage.facts import storage_facts_for_line


class CSharpCodeExtractor(ScannerMetadataMixin):
    spec = ScannerSpec(
        name="csharp_code",
        family="code",
        target_patterns=("*.cs",),
        parser_ids=(
            "dotnet_call",
            "dotnet_cache",
            "dotnet_controller_route",
            "dotnet_http",
            "dotnet_minimal_route",
            "dotnet_message",
            "dotnet_symbol",
            "dotnet_storage",
            "sql_reference",
        ),
        description="C# symbols, routes, calls, and application interactions.",
    )

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".cs"

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        method_index = csharp_method_index(content)
        namespace: str | None = None
        current_type: str | None = None
        current_route_prefix: str | None = None
        current_function: EntityFact | None = None
        current_function_brace_depth = 0
        current_function_seen_body = False
        pending_attributes: list[CSharpAttribute] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            facts.extend(csharp_minimal_route_facts(context, line, line_number))
            facts.relationships.extend(cache_facts_for_line(context, line, line_number, "dotnet_cache"))
            facts.relationships.extend(csharp_http_call_facts(context, line, line_number))
            facts.relationships.extend(message_facts_for_line(context, line, line_number, "dotnet_message"))
            facts.relationships.extend(storage_facts_for_line(context, line, line_number, "dotnet_storage"))
            if current_function:
                facts.relationships.extend(
                    cache_facts_for_line(context, line, line_number, "dotnet_cache", from_entity=current_function)
                )
                facts.relationships.extend(
                    csharp_http_call_facts(context, line, line_number, from_entity=current_function)
                )
                facts.relationships.extend(
                    message_facts_for_line(context, line, line_number, "dotnet_message", from_entity=current_function)
                )
                facts.relationships.extend(
                    storage_facts_for_line(context, line, line_number, "dotnet_storage", from_entity=current_function)
                )
                facts.relationships.extend(
                    sql_reference_facts_for_line(context, line, line_number, from_entity=current_function)
                )
                facts.relationships.extend(
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
                facts.extend(
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
                facts.extend(symbol_facts)
                facts.extend(
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

        return facts
