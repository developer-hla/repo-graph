# Storage Query Reads

Repo Graph storage persists and reads an already-built graph. It should not
parse source files, build graph records, or decide report semantics.

## Goal

API routes, reports, the UI, and agents should call one small public storage
surface for graph reads:

```python
from repo_graph.storage import read_graph_scope
from repo_graph.storage import search_entities
from repo_graph.storage import search_relationships
```

Storage internals can be split by read workflow, but callers outside
`repo_graph.storage` should not import private `_neo4j_*` modules.

## Ownership

`repo_graph.storage` owns the stable public read API.

Private Neo4j read modules own these workflows:

| Module | Owns |
| --- | --- |
| `_neo4j_scope_reads.py` | graph stats, loaded scope, overview, and source activity counts |
| `_neo4j_source_reads.py` | one-source overview and source-local summaries |
| `_neo4j_entity_reads.py` | entity lookup, entity search, and entity type listing |
| `_neo4j_relationship_reads.py` | relationship search, neighbor traversal, and unresolved edge listing |
| `_neo4j_read_common.py` | small shared helpers for Neo4j read result conversion |
| `_neo4j_scope_queries.py` | graph scope and graph overview Cypher query strings |
| `_neo4j_source_queries.py` | one-source overview Cypher query strings |
| `_neo4j_relationship_queries.py` | relationship, traversal, and unresolved edge Cypher query strings |
| `_neo4j_payloads.py` | Neo4j record-to-public-payload shaping |

Storage internals should import from the focused owning module.

## Non-Ownership

Neo4j read modules do not:

- construct graph entities or edges
- parse source input
- run source sync
- format HTTP responses
- group report classifications
- render UI output

API runtime modules translate HTTP requests into public storage calls.
Report modules group and summarize storage payloads. Storage only returns
structured graph data and evidence.

## Query Rules

- Keep reusable Cypher in the focused query module that matches the owning
  read workflow.
- Keep payload shaping in `_neo4j_payloads.py`.
- Normalize inputs before running queries.
- Preserve evidence fields such as `edge_id`, source name, file path, line
  number, parser, confidence, and properties.
- Preserve unresolved targets as first-class payloads.
- Keep read results deterministic through explicit ordering and limits.

## Extension Workflow

When adding a new read:

1. Add the public function to `repo_graph.storage` only if callers outside
   storage need it.
2. Put the implementation in the focused `_neo4j_*_reads.py` module.
3. Add reusable Cypher to the focused `_neo4j_*_queries.py` module.
4. Shape records through `_neo4j_payloads.py`.
5. Add synthetic tests for the public storage/API behavior or the query string.
6. Run `pixi run audit`.

`pixi run architecture-boundary-check` blocks new imports of
`repo_graph.storage._*` from outside the storage package.
