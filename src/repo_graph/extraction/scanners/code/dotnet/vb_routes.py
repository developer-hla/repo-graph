"""Visual Basic legacy endpoint route extraction helpers."""

from __future__ import annotations

from collections.abc import Sequence

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, FactBatch
from repo_graph.extraction.scanners.interactions.routes import route_entity_fact, route_handler_fact


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


__all__ = [
    "legacy_contract_framework",
    "legacy_dotnet_service_path",
    "vb_contract_route_facts",
]
