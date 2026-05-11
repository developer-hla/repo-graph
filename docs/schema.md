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
  "entity_type": "repository | file | package | api_route | sql_table | sql_view | sql_function | stored_procedure",
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
  "edge_type": "CONTAINS_FILE | DECLARES_PACKAGE | DEPENDS_ON_PACKAGE | IMPORTS | DECLARES_ROUTE | DEFINES | CALLS_SQL | READS_SQL_OBJECT",
  "resolved": true,
  "source_name": "source from config",
  "file_path": "relative/path when known",
  "line_number": 12,
  "confidence": "high | medium | low",
  "parser": "filesystem | package_json | javascript | sql | sql_reference",
  "properties": {}
}
```

## Unresolved Edges

An unresolved edge is a discovered reference that could not be mapped to an
entity in the current graph scope. This often means the target lives outside
the selected sources, the parser does not understand the declaration format
yet, or the reference is dynamic.

If a target matches multiple possible entities, the edge remains unresolved and
includes `properties.resolution_status = "ambiguous"` plus a bounded
`resolution_candidates` list. This avoids silently linking a reference to the
wrong repository or database object.
