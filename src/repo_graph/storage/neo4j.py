"""Neo4j storage for Repo Graph exports."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from repo_graph.graph import stable_id

DEFAULT_NEO4J_URI = "bolt://neo4j:7687"
DEFAULT_NEO4J_USER = "neo4j"
DEFAULT_NEO4J_PASSWORD = "repo-graph-password"
DEFAULT_RELATIONSHIP_TYPE = "RELATED_TO"
RELATIONSHIP_TYPE_RE = re.compile(r"[^A-Z0-9_]")
PROPERTY_KEY_RE = re.compile(r"[^A-Za-z0-9_]")


@dataclass(frozen=True)
class Neo4jSettings:
    uri: str = DEFAULT_NEO4J_URI
    user: str = DEFAULT_NEO4J_USER
    password: str = DEFAULT_NEO4J_PASSWORD
    database: str | None = None

    @classmethod
    def from_env(cls) -> Neo4jSettings:
        return cls(
            uri=env_value("REPO_GRAPH_NEO4J_URI", DEFAULT_NEO4J_URI),
            user=env_value("REPO_GRAPH_NEO4J_USER", DEFAULT_NEO4J_USER),
            password=env_value("REPO_GRAPH_NEO4J_PASSWORD", DEFAULT_NEO4J_PASSWORD),
            database=env_optional_value("REPO_GRAPH_NEO4J_DATABASE"),
        )


@dataclass(frozen=True)
class LoadSummary:
    scope_name: str | None
    schema_version: str | None
    source_count: int
    entity_count: int
    edge_count: int
    resolved_edge_count: int
    unresolved_edge_count: int
    unresolved_target_count: int
    clear_existing: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreparedGraphRecords:
    source_records: list[dict[str, Any]]
    entity_records: list[dict[str, Any]]
    edge_records: list[dict[str, Any]]
    target_records: list[dict[str, Any]]


def env_value(name: str, default: str | None) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return "" if default is None else default
    return value.strip()


def env_optional_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def load_graph_path(
    path: Path,
    settings: Neo4jSettings,
    clear_existing: bool = True,
    replace_sources: Iterable[str] | None = None,
) -> LoadSummary:
    graph_data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(graph_data, dict):
        raise ValueError("Graph JSON root must be an object.")
    return load_graph_data(graph_data, settings, clear_existing=clear_existing, replace_sources=replace_sources)


def load_graph_data(
    graph_data: Mapping[str, Any],
    settings: Neo4jSettings,
    clear_existing: bool = True,
    replace_sources: Iterable[str] | None = None,
) -> LoadSummary:
    source_names = normalize_source_names(replace_sources)
    if clear_existing and source_names:
        raise ValueError("Source replacement cannot also clear the whole graph.")
    validate_replace_sources(graph_data, source_names)
    records = prepare_graph_records(graph_data)

    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            initialize_schema(session)
            if clear_existing:
                session.execute_write(clear_graph_tx)
            elif source_names:
                session.execute_write(delete_current_edges_tx, records.edge_records)
                session.execute_write(delete_source_data_tx, source_names)
            session.execute_write(write_graph_tx, graph_record(graph_data))
            if records.source_records:
                session.execute_write(write_sources_tx, records.source_records)
            if records.entity_records:
                session.execute_write(write_entities_tx, records.entity_records)
            if records.target_records:
                session.execute_write(write_targets_tx, records.target_records)
            for relationship_type, edge_records in grouped_relationships(records.edge_records).items():
                session.execute_write(write_resolved_edges_tx, relationship_type, resolved_edges(edge_records))
                session.execute_write(write_unresolved_edges_tx, relationship_type, unresolved_edges(edge_records))
            session.execute_write(delete_orphan_targets_tx)

    return load_summary(
        graph_data,
        records.source_records,
        records.edge_records,
        records.target_records,
        clear_existing=clear_existing,
    )


def read_graph_stats(settings: Neo4jSettings) -> dict[str, Any]:
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            record = session.run(
                """
                CALL () {
                  MATCH (entity:RepoGraphEntity)
                  RETURN count(entity) AS entity_count
                }
                CALL () {
                  MATCH (target:RepoGraphTarget)
                  RETURN count(target) AS unresolved_target_count
                }
                CALL () {
                  MATCH ()-[edge]->()
                  WHERE edge.edge_id IS NOT NULL
                  RETURN count(edge) AS edge_count
                }
                CALL () {
                  MATCH ()-[edge]->()
                  WHERE edge.edge_id IS NOT NULL AND coalesce(edge.resolved, false) = true
                  RETURN count(edge) AS resolved_edge_count
                }
                CALL () {
                  MATCH ()-[edge]->()
                  WHERE edge.edge_id IS NOT NULL AND coalesce(edge.resolved, false) = false
                  RETURN count(edge) AS unresolved_edge_count
                }
                OPTIONAL MATCH (graph:RepoGraphGraph {graph_id: "current"})
                RETURN
                  graph.scope_name AS scope_name,
                  graph.schema_version AS schema_version,
                  graph.generated_at AS generated_at,
                  entity_count,
                  edge_count,
                  resolved_edge_count,
                  unresolved_edge_count,
                  unresolved_target_count
                """
            ).single()
    if record is None:
        return {}
    return dict(record)


def read_graph_scope(settings: Neo4jSettings) -> dict[str, Any]:
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            record = session.run(
                """
                OPTIONAL MATCH (graph:RepoGraphGraph {graph_id: "current"})
                OPTIONAL MATCH (graph)-[:INCLUDES_SOURCE]->(source:RepoGraphSource)
                WITH graph, source
                ORDER BY source.index, source.name
                RETURN graph, [item IN collect(source) WHERE item IS NOT NULL] AS sources
                """
            ).single()
    if record is None or record["graph"] is None:
        return unloaded_scope_payload()
    return scope_payload(record["graph"], record["sources"])


def search_entities(
    settings: Neo4jSettings,
    query: str | None = None,
    entity_type: str | None = None,
    source_name: str | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    params = {
        "search_text": lower_filter(query),
        "entity_type": optional_filter(entity_type),
        "source_name": optional_filter(source_name),
        "limit": normalize_limit(limit, maximum=100),
    }
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            records = session.run(
                """
                MATCH (entity:RepoGraphEntity)
                WHERE
                  ($search_text IS NULL
                    OR toLower(coalesce(entity.name, "")) CONTAINS $search_text
                    OR toLower(coalesce(entity.entity_id, "")) = $search_text
                    OR toLower(coalesce(entity.file_path, "")) CONTAINS $search_text
                    OR toLower(coalesce(entity.property_full_name, "")) CONTAINS $search_text
                    OR any(alias IN coalesce(entity.aliases, [])
                      WHERE toLower(toString(alias)) CONTAINS $search_text))
                  AND ($entity_type IS NULL OR entity.entity_type = $entity_type)
                  AND ($source_name IS NULL OR entity.source_name = $source_name)
                RETURN entity
                ORDER BY entity.entity_type, entity.source_name, entity.name
                LIMIT $limit
                """,
                **params,
            )
            return [entity_payload(record["entity"]) for record in records]


def get_entity(settings: Neo4jSettings, entity_id: str) -> dict[str, Any] | None:
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            record = session.run(
                """
                MATCH (entity:RepoGraphEntity {entity_id: $entity_id})
                RETURN entity
                LIMIT 1
                """,
                entity_id=entity_id,
            ).single()
    if record is None:
        return None
    return entity_payload(record["entity"])


def get_entity_neighbors(
    settings: Neo4jSettings,
    entity_id: str,
    direction: str = "both",
    edge_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    normalized_direction = normalize_direction(direction)
    normalized_limit = normalize_limit(limit, maximum=200)
    params = {
        "entity_id": entity_id,
        "edge_type": optional_filter(edge_type),
        "limit": normalized_limit,
    }
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            records: list[Any] = []
            if normalized_direction in {"out", "both"}:
                records.extend(session.run(outgoing_neighbors_query(), **params))
            if normalized_direction in {"in", "both"}:
                records.extend(session.run(incoming_neighbors_query(), **params))

    return [neighbor_payload(record) for record in records[:normalized_limit]]


def list_unresolved_edges(
    settings: Neo4jSettings,
    source_name: str | None = None,
    edge_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    params = {
        "source_name": optional_filter(source_name),
        "edge_type": optional_filter(edge_type),
        "limit": normalize_limit(limit, maximum=1000),
    }
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            records = session.run(
                """
                MATCH (source:RepoGraphEntity)-[edge]->(target:RepoGraphTarget)
                WHERE edge.edge_id IS NOT NULL
                  AND ($source_name IS NULL OR edge.source_name = $source_name)
                  AND ($edge_type IS NULL OR edge.edge_type = $edge_type)
                RETURN source, edge, target
                ORDER BY edge.source_name, edge.edge_type, edge.to_name
                LIMIT $limit
                """,
                **params,
            )
            return [unresolved_edge_payload(record) for record in records]


def outgoing_neighbors_query() -> str:
    return """
        MATCH (:RepoGraphEntity {entity_id: $entity_id})-[edge]->(neighbor)
        WHERE edge.edge_id IS NOT NULL
          AND ($edge_type IS NULL OR edge.edge_type = $edge_type)
        RETURN edge, neighbor, labels(neighbor) AS labels, "out" AS direction
        ORDER BY edge.edge_type, edge.to_name
        LIMIT $limit
    """


def incoming_neighbors_query() -> str:
    return """
        MATCH (neighbor)-[edge]->(:RepoGraphEntity {entity_id: $entity_id})
        WHERE edge.edge_id IS NOT NULL
          AND ($edge_type IS NULL OR edge.edge_type = $edge_type)
        RETURN edge, neighbor, labels(neighbor) AS labels, "in" AS direction
        ORDER BY edge.edge_type, edge.from_name
        LIMIT $limit
    """


def entity_payload(entity: Mapping[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "entity_id": entity.get("entity_id"),
            "entity_type": entity.get("entity_type"),
            "name": entity.get("name"),
            "source_name": entity.get("source_name"),
            "file_path": entity.get("file_path"),
            "line_number": entity.get("line_number"),
            "aliases": entity.get("aliases", []),
            "properties": json_object(entity.get("properties_json")),
        }
    )


def target_payload(target: Mapping[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "target_id": target.get("target_id"),
            "name": target.get("name"),
            "target_type": target.get("target_type"),
            "source_name": target.get("source_name"),
            "resolved": target.get("resolved", False),
        }
    )


def edge_payload(edge: Mapping[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "edge_id": edge.get("edge_id"),
            "edge_type": edge.get("edge_type"),
            "from_entity_id": edge.get("from_entity_id"),
            "from_name": edge.get("from_name"),
            "from_type": edge.get("from_type"),
            "to_entity_id": edge.get("to_entity_id"),
            "to_name": edge.get("to_name"),
            "to_type": edge.get("to_type"),
            "resolved": edge.get("resolved", False),
            "source_name": edge.get("source_name"),
            "file_path": edge.get("file_path"),
            "line_number": edge.get("line_number"),
            "confidence": edge.get("confidence"),
            "parser": edge.get("parser"),
            "properties": json_object(edge.get("properties_json")),
        }
    )


def neighbor_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "direction": record["direction"],
        "edge": edge_payload(record["edge"]),
        "neighbor": graph_node_payload(record["neighbor"], record.get("labels", [])),
    }


def unresolved_edge_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source": entity_payload(record["source"]),
        "edge": edge_payload(record["edge"]),
        "target": target_payload(record["target"]),
    }


def graph_node_payload(node: Mapping[str, Any], labels: Iterable[str]) -> dict[str, Any]:
    if "RepoGraphTarget" in labels:
        return target_payload(node)
    return entity_payload(node)


def source_payload(source: Mapping[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "source_id": source.get("source_id"),
            "index": source.get("index"),
            "name": source.get("name"),
            "type": source.get("type"),
            "path": source.get("path"),
            "url": source.get("url"),
            "ref": source.get("ref"),
            "commit": source.get("commit"),
        }
    )


def scope_payload(graph: Mapping[str, Any], sources: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    source_items = [source_payload(source) for source in sources]
    return {
        "loaded": True,
        "scope_name": graph.get("scope_name"),
        "schema_version": graph.get("schema_version"),
        "generated_at": graph.get("generated_at"),
        "tool": graph.get("tool"),
        "summary": json_object(graph.get("summary_json")),
        "source_count": len(source_items),
        "sources": source_items,
    }


def unloaded_scope_payload() -> dict[str, Any]:
    return {
        "loaded": False,
        "source_count": 0,
        "sources": [],
    }


def json_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def compact_dict(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def optional_filter(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()


def lower_filter(value: str | None) -> str | None:
    normalized = optional_filter(value)
    if normalized is None:
        return None
    return normalized.lower()


def normalize_limit(value: int, maximum: int) -> int:
    if value < 1:
        raise ValueError("Limit must be at least 1.")
    if value > maximum:
        raise ValueError(f"Limit must be at most {maximum}.")
    return value


def normalize_direction(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"in", "out", "both"}:
        raise ValueError("Direction must be one of: in, out, both.")
    return normalized


def graph_items(graph_data: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    raw_items = graph_data.get(key, [])
    if not isinstance(raw_items, list):
        raise ValueError(f"Graph field '{key}' must be a list.")
    return [item for item in raw_items if isinstance(item, dict)]


def prepare_graph_records(graph_data: Mapping[str, Any]) -> PreparedGraphRecords:
    source_records = [
        source_record(source, graph_data, index) for index, source in enumerate(graph_items(graph_data, "sources"))
    ]
    entity_records = [entity_record(entity) for entity in graph_items(graph_data, "entities")]
    edge_records = [edge_record(edge) for edge in graph_items(graph_data, "edges")]
    target_records = unresolved_target_records(edge_records)
    return PreparedGraphRecords(
        source_records=source_records,
        entity_records=entity_records,
        edge_records=edge_records,
        target_records=target_records,
    )


def normalize_source_names(source_names: Iterable[str] | None) -> tuple[str, ...]:
    if source_names is None:
        return ()
    return tuple(sorted({source_name.strip() for source_name in source_names if source_name.strip()}))


def validate_replace_sources(graph_data: Mapping[str, Any], source_names: tuple[str, ...]) -> None:
    if not source_names:
        return
    graph_sources = {source.get("name") for source in graph_items(graph_data, "sources")}
    missing = [source_name for source_name in source_names if source_name not in graph_sources]
    if missing:
        raise ValueError(f"Replace source is not present in graph: {', '.join(missing)}")


def graph_record(graph_data: Mapping[str, Any]) -> dict[str, Any]:
    metadata = mapping_value(graph_data.get("metadata"))
    summary = mapping_value(graph_data.get("summary"))
    sources = graph_items(graph_data, "sources")
    record = {
        "graph_id": "current",
        "tool": metadata.get("tool"),
        "schema_version": metadata.get("schema_version"),
        "scope_name": metadata.get("scope_name"),
        "generated_at": metadata.get("generated_at"),
        "source_count": len(sources),
        "summary_json": json.dumps(summary, sort_keys=True),
        "sources_json": json.dumps(sources, sort_keys=True),
    }
    for key, value in summary.items():
        record[f"summary_{safe_property_key(key)}"] = value
    return neo4j_properties(record)


def source_record(source: Mapping[str, Any], graph_data: Mapping[str, Any], index: int) -> dict[str, Any]:
    metadata = mapping_value(graph_data.get("metadata"))
    name = required_string(source, "name")
    source_id = stable_id("source", str(metadata.get("scope_name") or ""), name)
    properties = neo4j_properties(
        {
            "source_id": source_id,
            "index": index,
            "name": name,
            "type": source.get("type"),
            "path": source.get("path"),
            "url": source.get("url"),
            "ref": source.get("ref"),
            "commit": source.get("commit"),
        }
    )
    return {
        "source_id": source_id,
        "properties": properties,
    }


def entity_record(entity: Mapping[str, Any]) -> dict[str, Any]:
    properties = neo4j_properties(
        {
            "entity_id": required_string(entity, "entity_id"),
            "entity_type": entity.get("entity_type"),
            "name": entity.get("name"),
            "source_name": entity.get("source_name"),
            "file_path": entity.get("file_path"),
            "line_number": entity.get("line_number"),
            "aliases": entity.get("aliases", []),
            "properties": mapping_value(entity.get("properties")),
        }
    )
    return {
        "entity_id": properties["entity_id"],
        "properties": properties,
    }


def edge_record(edge: Mapping[str, Any]) -> dict[str, Any]:
    properties = neo4j_properties(
        {
            "edge_id": required_string(edge, "edge_id"),
            "from_entity_id": edge.get("from_entity_id"),
            "from_name": edge.get("from_name"),
            "from_type": edge.get("from_type"),
            "to_name": edge.get("to_name"),
            "to_type": edge.get("to_type"),
            "to_entity_id": edge.get("to_entity_id"),
            "edge_type": edge.get("edge_type"),
            "resolved": edge.get("resolved", False),
            "source_name": edge.get("source_name"),
            "file_path": edge.get("file_path"),
            "line_number": edge.get("line_number"),
            "confidence": edge.get("confidence"),
            "parser": edge.get("parser"),
            "properties": mapping_value(edge.get("properties")),
        }
    )
    return {
        "edge_id": properties["edge_id"],
        "from_entity_id": properties.get("from_entity_id"),
        "to_entity_id": properties.get("to_entity_id"),
        "target_id": unresolved_target_id(edge),
        "relationship_type": sanitize_relationship_type(str(edge.get("edge_type") or "")),
        "resolved": bool(edge.get("resolved") and edge.get("to_entity_id")),
        "properties": properties,
    }


def unresolved_target_records(edge_records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    targets: dict[str, dict[str, Any]] = {}
    for edge in unresolved_edges(edge_records):
        properties = edge["properties"]
        target_id = edge["target_id"]
        targets[target_id] = neo4j_properties(
            {
                "target_id": target_id,
                "name": properties.get("to_name"),
                "target_type": properties.get("to_type"),
                "source_name": properties.get("source_name"),
                "resolved": False,
            }
        )
    return [{"target_id": target_id, "properties": properties} for target_id, properties in sorted(targets.items())]


def unresolved_target_id(edge: Mapping[str, Any]) -> str:
    return stable_id(
        "unresolved",
        str(edge.get("source_name") or ""),
        str(edge.get("to_type") or ""),
        str(edge.get("to_name") or ""),
    )


def load_summary(
    graph_data: Mapping[str, Any],
    source_records: list[dict[str, Any]],
    edge_records: list[dict[str, Any]],
    target_records: list[dict[str, Any]],
    clear_existing: bool,
) -> LoadSummary:
    metadata = mapping_value(graph_data.get("metadata"))
    resolved_count = len(resolved_edges(edge_records))
    unresolved_count = len(edge_records) - resolved_count
    return LoadSummary(
        scope_name=string_or_none(metadata.get("scope_name")),
        schema_version=string_or_none(metadata.get("schema_version")),
        source_count=len(source_records),
        entity_count=len(graph_items(graph_data, "entities")),
        edge_count=len(edge_records),
        resolved_edge_count=resolved_count,
        unresolved_edge_count=unresolved_count,
        unresolved_target_count=len(target_records),
        clear_existing=clear_existing,
    )


def grouped_relationships(edge_records: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in edge_records:
        groups.setdefault(record["relationship_type"], []).append(record)
    return groups


def resolved_edges(edge_records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in edge_records if record["resolved"]]


def unresolved_edges(edge_records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in edge_records if not record["resolved"]]


def initialize_schema(session: Any) -> None:
    for query in (
        "CREATE CONSTRAINT repo_graph_entity_id IF NOT EXISTS "
        "FOR (entity:RepoGraphEntity) REQUIRE entity.entity_id IS UNIQUE",
        "CREATE CONSTRAINT repo_graph_target_id IF NOT EXISTS "
        "FOR (target:RepoGraphTarget) REQUIRE target.target_id IS UNIQUE",
        "CREATE CONSTRAINT repo_graph_source_id IF NOT EXISTS "
        "FOR (source:RepoGraphSource) REQUIRE source.source_id IS UNIQUE",
        "CREATE CONSTRAINT repo_graph_graph_id IF NOT EXISTS "
        "FOR (graph:RepoGraphGraph) REQUIRE graph.graph_id IS UNIQUE",
    ):
        session.run(query).consume()


def clear_graph_tx(tx: Any) -> None:
    tx.run(
        """
        MATCH (node)
        WHERE
          node:RepoGraphEntity
          OR node:RepoGraphTarget
          OR node:RepoGraphSource
          OR node:RepoGraphGraph
        DETACH DELETE node
        """
    ).consume()


def delete_current_edges_tx(tx: Any, edges: list[dict[str, Any]]) -> None:
    edge_ids = [edge["edge_id"] for edge in edges]
    if not edge_ids:
        return
    tx.run(
        """
        MATCH ()-[edge]->()
        WHERE edge.edge_id IN $edge_ids
        DELETE edge
        """,
        edge_ids=edge_ids,
    ).consume()


def delete_source_data_tx(tx: Any, source_names: Iterable[str]) -> None:
    names = list(source_names)
    if not names:
        return
    tx.run(
        """
        MATCH ()-[edge]->()
        WHERE edge.edge_id IS NOT NULL
          AND edge.source_name IN $source_names
        DELETE edge
        """,
        source_names=names,
    ).consume()
    tx.run(
        """
        MATCH (entity:RepoGraphEntity)
        WHERE entity.source_name IN $source_names
        DETACH DELETE entity
        """,
        source_names=names,
    ).consume()
    tx.run(
        """
        MATCH (target:RepoGraphTarget)
        WHERE target.source_name IN $source_names
        DETACH DELETE target
        """,
        source_names=names,
    ).consume()
    tx.run(
        """
        MATCH (source:RepoGraphSource)
        WHERE source.name IN $source_names
        DETACH DELETE source
        """,
        source_names=names,
    ).consume()


def write_graph_tx(tx: Any, graph: dict[str, Any]) -> None:
    tx.run(
        """
        MERGE (graph:RepoGraphGraph {graph_id: $graph_id})
        SET graph += $properties
        """,
        graph_id=graph["graph_id"],
        properties=graph,
    ).consume()


def write_sources_tx(tx: Any, sources: list[dict[str, Any]]) -> None:
    tx.run(
        """
        UNWIND $sources AS source
        MERGE (node:RepoGraphSource {source_id: source.source_id})
        SET node += source.properties
        WITH node, source
        MATCH (graph:RepoGraphGraph {graph_id: "current"})
        MERGE (graph)-[relationship:INCLUDES_SOURCE {source_id: source.source_id}]->(node)
        SET relationship.source_id = source.source_id
        """,
        sources=sources,
    ).consume()


def write_entities_tx(tx: Any, entities: list[dict[str, Any]]) -> None:
    tx.run(
        """
        UNWIND $entities AS entity
        MERGE (node:RepoGraphEntity {entity_id: entity.entity_id})
        SET node += entity.properties
        """,
        entities=entities,
    ).consume()


def write_targets_tx(tx: Any, targets: list[dict[str, Any]]) -> None:
    tx.run(
        """
        UNWIND $targets AS target
        MERGE (node:RepoGraphTarget {target_id: target.target_id})
        SET node += target.properties
        """,
        targets=targets,
    ).consume()


def write_resolved_edges_tx(tx: Any, relationship_type: str, edges: list[dict[str, Any]]) -> None:
    if not edges:
        return
    tx.run(
        f"""
        UNWIND $edges AS edge
        MATCH (source:RepoGraphEntity {{entity_id: edge.from_entity_id}})
        MATCH (target:RepoGraphEntity {{entity_id: edge.to_entity_id}})
        MERGE (source)-[relationship:{relationship_type} {{edge_id: edge.edge_id}}]->(target)
        SET relationship += edge.properties
        """,
        edges=edges,
    ).consume()


def write_unresolved_edges_tx(tx: Any, relationship_type: str, edges: list[dict[str, Any]]) -> None:
    if not edges:
        return
    tx.run(
        f"""
        UNWIND $edges AS edge
        MATCH (source:RepoGraphEntity {{entity_id: edge.from_entity_id}})
        MATCH (target:RepoGraphTarget {{target_id: edge.target_id}})
        MERGE (source)-[relationship:{relationship_type} {{edge_id: edge.edge_id}}]->(target)
        SET relationship += edge.properties
        """,
        edges=edges,
    ).consume()


def delete_orphan_targets_tx(tx: Any) -> None:
    tx.run(
        """
        MATCH (target:RepoGraphTarget)
        WHERE NOT (target)<-[]-()
        DELETE target
        """
    ).consume()


def neo4j_properties(raw: Mapping[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    nested = mapping_value(raw.get("properties"))
    for key, value in raw.items():
        if key == "properties":
            continue
        normalized = neo4j_property_value(value)
        if normalized is not None:
            properties[safe_property_key(key)] = normalized

    if nested:
        properties["properties_json"] = json.dumps(nested, sort_keys=True)
        for key, value in nested.items():
            normalized = neo4j_property_value(value)
            if normalized is not None:
                properties[f"property_{safe_property_key(key)}"] = normalized
    return properties


def neo4j_property_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list | tuple | set) and all(isinstance(item, bool | int | float | str) for item in value):
        return sorted(value) if isinstance(value, set) else list(value)
    return json.dumps(value, sort_keys=True)


def sanitize_relationship_type(value: str) -> str:
    normalized = RELATIONSHIP_TYPE_RE.sub("_", value.strip().upper()).strip("_")
    if not normalized:
        return DEFAULT_RELATIONSHIP_TYPE
    if normalized[0].isdigit():
        return f"EDGE_{normalized}"
    return normalized


def safe_property_key(value: Any) -> str:
    normalized = PROPERTY_KEY_RE.sub("_", str(value).strip()).strip("_")
    if not normalized:
        return "value"
    if normalized[0].isdigit():
        return f"property_{normalized}"
    return normalized


def mapping_value(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def required_string(value: Mapping[str, Any], key: str) -> str:
    raw_value = value.get(key)
    if not isinstance(raw_value, str) or not raw_value:
        raise ValueError(f"Graph item must define non-empty '{key}'.")
    return raw_value


def string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None
