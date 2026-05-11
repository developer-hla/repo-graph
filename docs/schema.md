# RepoGraph JSON Schema Notes

The MVP export is a single JSON document. It is intentionally simple so it can
be loaded into different stores.

## Top-Level Fields

- `metadata`: tool name, schema version, scope name, and generation time.
- `sources`: resolved source list with local path, ref, URL, and commit when
  available.
- `summary`: file, entity, edge, resolution, and error counts.
- `entity_counts`: counts grouped by `entity_type`.
- `edge_counts`: counts grouped by `edge_type`.
- `entities`: graph nodes.
- `edges`: graph relationships.
- `errors`: scanner errors that did not stop the build.

## Entity

```json
{
  "entity_id": "stable-id",
  "entity_type": "repository | project | file | package | api_route | function | class | sql_table | sql_view | sql_function | stored_procedure",
  "name": "display name",
  "source_name": "source from config",
  "file_path": "relative/path when known",
  "line_number": 12,
  "aliases": ["optional alternate names"],
  "properties": {}
}
```

## Edge

```json
{
  "edge_id": "stable-id",
  "from_entity_id": "stable-id",
  "from_name": "source entity display name",
  "from_type": "file",
  "to_name": "target display name or unresolved reference",
  "to_type": "target type when known",
  "to_entity_id": "stable-id when resolved",
  "edge_type": "CONTAINS_PROJECT | CONTAINS_FILE | DECLARES_PACKAGE | DEPENDS_ON_PACKAGE | IMPORTS | DECLARES_ROUTE | EXPOSES_ROUTE | DECLARES_SYMBOL | CALLS_HTTP | CALLS_SERVICE | DEFINES | CALLS_SQL | READS_SQL_OBJECT",
  "resolved": true,
  "source_name": "source from config",
  "file_path": "relative/path when known",
  "line_number": 12,
  "confidence": "high | medium | low",
  "parser": "filesystem | package_json | javascript | sql | sql_reference",
  "properties": {}
}
```

## Core Entity Types

- `repository`: one configured source.
- `project`: a package or workspace discovered inside a repository.
- `file`: a scanned source file.
- `package`: a package manifest declaration, such as `package.json` `name`.
- `api_route`: an HTTP route declared in source code.
- `function` and `class`: exported JavaScript or TypeScript symbols.
- `sql_table`, `sql_view`, `sql_function`, `stored_procedure`: SQL objects
  declared in SQL files.

## Core Edge Types

- `CONTAINS_PROJECT`: repository to discovered project.
- `CONTAINS_FILE`: repository or project to file.
- `DECLARES_PACKAGE`: file or project to package.
- `DEPENDS_ON_PACKAGE`: package or manifest file to package target.
- `IMPORTS`: file to imported package or relative module target.
- `DECLARES_ROUTE`: file to route.
- `EXPOSES_ROUTE`: project to route.
- `DECLARES_SYMBOL`: file to exported function or class.
- `CALLS_HTTP`: file to route target inferred from `fetch` or `axios`.
- `CALLS_SERVICE`: file to a service-like target inferred from environment
  URL names.
- `DEFINES`: SQL file to SQL object declaration.
- `CALLS_SQL`: file to stored procedure target.
- `READS_SQL_OBJECT`: file to table, view, function, or procedure target.

Scanner-derived reference edges include evidence in `properties`, such as
`raw_target`, `normalized_target`, dependency type, HTTP method, target path,
target environment variable, or SQL object name.

## Unresolved Edges

An unresolved edge is a discovered reference that could not be mapped to an
entity in the current graph scope. This often means the target lives outside
the selected sources, the parser does not understand the declaration format
yet, or the reference is dynamic.

If a target matches multiple possible entities, the edge remains unresolved and
includes `properties.resolution_status = "ambiguous"` plus a bounded
`resolution_candidates` list. This avoids silently linking a reference to the
wrong repository or database object.

Service-like targets are resolved in priority order: explicit `service`
entities first, then `project`, then `repository`. This lets an environment URL
such as `INVENTORY_SERVICE_URL` resolve to a discovered project named or
aliased `inventory-service` without being treated as an ambiguous match with
its parent repository.

## Neo4j Mapping

The Neo4j loader stores graph exports with a small public-safe model:

- `RepoGraphGraph`: one metadata node for the loaded graph.
- `RepoGraphSource`: one node per configured source recorded in the graph
  export.
- `RepoGraphEntity`: one node per exported entity.
- `RepoGraphTarget`: one node per unresolved target string.
- `(:RepoGraphGraph)-[:INCLUDES_SOURCE]->(:RepoGraphSource)` records the
  source set used by the loaded graph.
- Relationships use sanitized edge types such as `IMPORTS`, `CALLS_SQL`, and
  `READS_SQL_OBJECT`.

Each loaded node and relationship keeps the original graph fields as
properties. Nested `properties` maps are preserved as `properties_json` and
flattened into `property_*` fields where practical.

Resolved edges point from a `RepoGraphEntity` to another `RepoGraphEntity`.
Unresolved edges point from a `RepoGraphEntity` to a `RepoGraphTarget`.
