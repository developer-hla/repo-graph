"""Neo4j entity lookup and search read operations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from neo4j import GraphDatabase

from repo_graph.storage._neo4j_common import lower_filter, normalize_limit, optional_filter
from repo_graph.storage._neo4j_payloads import entity_payload
from repo_graph.storage._neo4j_settings import Neo4jSettings


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


def list_entities_by_types(
    settings: Neo4jSettings,
    entity_types: Iterable[str],
    source_name: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    normalized_types = sorted({entity_type for entity_type in entity_types if entity_type})
    if not normalized_types:
        return []
    params = {
        "entity_types": normalized_types,
        "source_name": optional_filter(source_name),
        "limit": normalize_limit(limit, maximum=1000),
    }
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            records = session.run(
                """
                MATCH (entity:RepoGraphEntity)
                WHERE entity.entity_type IN $entity_types
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
