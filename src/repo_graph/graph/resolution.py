"""Graph reference resolution policy."""

from __future__ import annotations

from collections import defaultdict

from repo_graph.graph.model import Entity, Graph


def resolve_graph_edges(graph: Graph) -> None:
    lookup: dict[tuple[str | None, str], list[Entity]] = defaultdict(list)
    for entity in graph.entities.values():
        if not is_resolution_candidate(entity):
            continue
        keys = {entity.name, *entity.aliases}
        full_name = entity.properties.get("full_name")
        if isinstance(full_name, str):
            keys.add(full_name)
        schema = entity.properties.get("schema")
        if isinstance(schema, str) and schema:
            keys.add(f"{schema}.{entity.name}")
        for key in keys:
            normalized = normalize_key(key)
            lookup[(entity.entity_type, normalized)].append(entity)
            lookup[(None, normalized)].append(entity)

    for edge in graph.edges.values():
        if edge.to_entity_id:
            edge.resolved = edge.to_entity_id in graph.entities
            continue
        candidates = resolution_candidates(lookup, edge.to_type, normalize_key(edge.to_name))
        entity = choose_resolution(candidates, edge.source_name)
        if entity:
            edge.to_entity_id = entity.entity_id
            edge.to_type = entity.entity_type
            edge.resolved = True
        elif candidates:
            edge.properties["resolution_status"] = "ambiguous"
            edge.properties["resolution_candidates"] = [
                {
                    "entity_id": candidate.entity_id,
                    "entity_type": candidate.entity_type,
                    "name": candidate.name,
                    "source_name": candidate.source_name,
                }
                for candidate in candidates[:25]
            ]


def normalize_key(value: str) -> str:
    return value.strip().strip("[]`\"'").lower()


def resolution_candidates(
    lookup: dict[tuple[str | None, str], list[Entity]],
    target_type: str | None,
    target_name: str,
) -> list[Entity]:
    if target_type == "service":
        for entity_types in (["service"], ["project"], ["repository"]):
            candidates = [
                candidate for entity_type in entity_types for candidate in lookup.get((entity_type, target_name), [])
            ]
            if candidates:
                return dedupe_entities(candidates)

    candidates: list[Entity] = []
    for entity_type in resolution_entity_types(target_type):
        candidates.extend(lookup.get((entity_type, target_name), []))
    if not candidates:
        candidates.extend(lookup.get((None, target_name), []))
    return dedupe_entities(candidates)


def resolution_entity_types(target_type: str | None) -> list[str | None]:
    if target_type == "sql_object":
        return ["sql_table", "sql_view", "sql_function", "sql_trigger", "stored_procedure"]
    if target_type == "service":
        return ["service", "project", "repository"]
    if target_type:
        return [target_type]
    return [None]


def choose_resolution(candidates: list[Entity], source_name: str) -> Entity | None:
    if not candidates:
        return None

    same_source = [candidate for candidate in candidates if candidate.source_name == source_name]
    if len(same_source) == 1:
        return same_source[0]
    if len(same_source) > 1:
        return None

    if len(candidates) == 1:
        return candidates[0]
    return None


def is_resolution_candidate(entity: Entity) -> bool:
    if entity.entity_type.startswith("sql_") or entity.entity_type == "stored_procedure":
        return entity.properties.get("schema_state") != "historical"
    return True


def dedupe_entities(candidates: list[Entity]) -> list[Entity]:
    entities: dict[str, Entity] = {}
    for candidate in candidates:
        entities[candidate.entity_id] = candidate
    return list(entities.values())
