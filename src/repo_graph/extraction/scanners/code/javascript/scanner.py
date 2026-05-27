"""JavaScript and TypeScript source scanners."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.facts import EntityFact, FactBatch
from repo_graph.extraction.scanners.cache.facts import cache_facts_for_line
from repo_graph.extraction.scanners.code.javascript.helpers import (
    javascript_function_scope_state,
    javascript_symbol_call_facts,
    javascript_symbol_facts,
    javascript_symbol_index,
)
from repo_graph.extraction.scanners.interactions.http import http_call_facts
from repo_graph.extraction.scanners.interactions.imports import import_facts
from repo_graph.extraction.scanners.interactions.routes import route_facts
from repo_graph.extraction.scanners.messaging.facts import message_facts_for_line
from repo_graph.extraction.scanners.scheduled_job_helpers import javascript_scheduled_job_facts
from repo_graph.extraction.scanners.sql.references import sql_reference_facts_for_line
from repo_graph.extraction.scanners.storage.facts import storage_facts_for_line


class JavaScriptExtractor:
    name = "javascript"
    target_patterns = ("*.js", "*.jsx", "*.ts", "*.tsx")
    parser_ids = (
        "javascript_call",
        "javascript_cache",
        "javascript_export",
        "javascript_http",
        "javascript_import",
        "javascript_message",
        "javascript_route",
        "javascript_job",
        "javascript_storage",
        "javascript_symbol",
        "sql_reference",
    )

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".js", ".jsx", ".ts", ".tsx"}

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        symbol_index = javascript_symbol_index(context, content)
        current_function: EntityFact | None = None
        current_function_brace_depth = 0
        current_function_seen_body = False
        for line_number, line in enumerate(content.splitlines(), start=1):
            facts.relationships.extend(import_facts(context, line, line_number))
            facts.extend(route_facts(context, line, line_number, symbol_index.functions_by_name))
            facts.extend(javascript_scheduled_job_facts(context, line, line_number, symbol_index.functions_by_name))
            for declaration in symbol_index.declarations_by_line.get(line_number, ()):
                facts.extend(javascript_symbol_facts(context, declaration))
            function_at_line = symbol_index.function_by_line.get(line_number)
            if function_at_line:
                current_function = function_at_line
                current_function_brace_depth = 0
                current_function_seen_body = False
            facts.relationships.extend(http_call_facts(context, line, line_number))
            facts.relationships.extend(cache_facts_for_line(context, line, line_number, "javascript_cache"))
            facts.relationships.extend(message_facts_for_line(context, line, line_number, "javascript_message"))
            facts.relationships.extend(storage_facts_for_line(context, line, line_number, "javascript_storage"))
            if current_function:
                facts.relationships.extend(http_call_facts(context, line, line_number, from_entity=current_function))
                facts.relationships.extend(
                    cache_facts_for_line(
                        context,
                        line,
                        line_number,
                        "javascript_cache",
                        from_entity=current_function,
                    )
                )
                facts.relationships.extend(
                    message_facts_for_line(
                        context,
                        line,
                        line_number,
                        "javascript_message",
                        from_entity=current_function,
                    )
                )
                facts.relationships.extend(
                    storage_facts_for_line(
                        context,
                        line,
                        line_number,
                        "javascript_storage",
                        from_entity=current_function,
                    )
                )
                facts.relationships.extend(sql_reference_facts_for_line(context, line, line_number, current_function))
                facts.relationships.extend(
                    javascript_symbol_call_facts(context, line, line_number, current_function, symbol_index)
                )
                current_function_brace_depth, current_function_seen_body = javascript_function_scope_state(
                    line,
                    current_function_brace_depth,
                    current_function_seen_body,
                )
                if current_function_seen_body:
                    if current_function_brace_depth <= 0:
                        current_function = None
                else:
                    current_function = None
        return facts
