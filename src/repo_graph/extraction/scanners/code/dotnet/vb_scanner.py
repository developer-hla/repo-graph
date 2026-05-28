"""Legacy VB.NET code scanner."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext, ScannerMetadataMixin, ScannerSpec
from repo_graph.extraction.facts import EntityFact, FactBatch
from repo_graph.extraction.scanners.cache.facts import cache_facts_for_line
from repo_graph.extraction.scanners.code.dotnet.vb_interactions import (
    vb_service_call_facts,
    vb_sql_command_facts,
)
from repo_graph.extraction.scanners.code.dotnet.vb_routes import vb_contract_route_facts
from repo_graph.extraction.scanners.code.dotnet.vb_symbols import (
    vb_method_index,
    vb_symbol_call_facts,
    vb_symbol_facts,
)
from repo_graph.extraction.scanners.code.dotnet.vb_syntax import (
    VB_ATTRIBUTE_RE,
    VB_END_METHOD_RE,
    VB_METHOD_RE,
    VB_NAMESPACE_RE,
    VB_TYPE_RE,
)
from repo_graph.extraction.scanners.messaging.facts import message_facts_for_line
from repo_graph.extraction.scanners.storage.facts import storage_facts_for_line


class VbCodeExtractor(ScannerMetadataMixin):
    spec = ScannerSpec(
        name="vb_code",
        family="code",
        target_patterns=("*.vb",),
        parser_ids=(
            "vb_call",
            "vb_cache",
            "vb_config_service",
            "vb_contract_route",
            "vb_http",
            "vb_message",
            "vb_sql_command",
            "vb_storage",
            "vb_symbol",
        ),
        description="Legacy VB.NET symbols, contract routes, calls, and application interactions.",
    )

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".vb"

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
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
                facts.extend(
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
                facts.extend(symbol_facts)
                facts.extend(
                    vb_contract_route_facts(context, method_name, pending_attributes, line_number, current_function)
                )
                pending_attributes = []

            facts.relationships.extend(cache_facts_for_line(context, line, line_number, "vb_cache"))
            facts.relationships.extend(vb_service_call_facts(context, line, line_number))
            facts.relationships.extend(message_facts_for_line(context, line, line_number, "vb_message"))
            facts.relationships.extend(storage_facts_for_line(context, line, line_number, "vb_storage"))
            facts.relationships.extend(vb_sql_command_facts(context, line, line_number))
            if current_function:
                facts.relationships.extend(
                    cache_facts_for_line(context, line, line_number, "vb_cache", from_entity=current_function)
                )
                facts.relationships.extend(
                    vb_service_call_facts(context, line, line_number, from_entity=current_function)
                )
                facts.relationships.extend(
                    message_facts_for_line(context, line, line_number, "vb_message", from_entity=current_function)
                )
                facts.relationships.extend(
                    storage_facts_for_line(context, line, line_number, "vb_storage", from_entity=current_function)
                )
                facts.relationships.extend(
                    vb_sql_command_facts(context, line, line_number, from_entity=current_function)
                )
                if not method_match:
                    facts.relationships.extend(
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
        return facts
