"""C# application interaction extraction helpers."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, unresolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.scanners.code.dotnet.csharp_syntax import csharp_unescape_string
from repo_graph.extraction.scanners.interactions.http import http_facts_for_target, http_target
from repo_graph.extraction.scanners.interactions.naming import service_name_from_url
from repo_graph.extraction.scanners.sql.helpers import source_context_properties

CS_HTTP_CALL_RE = re.compile(
    r"\.\s*(Get|Post|Put|Patch|Delete)Async\s*\(\s*(?:\$@|@\$|\$|@)?\"((?:\"\"|\\.|[^\"])*)\"",
    re.IGNORECASE,
)


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


__all__ = [
    "csharp_http_call_facts",
]
