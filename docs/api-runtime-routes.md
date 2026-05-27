# API Runtime Routes

The API runtime exposes Repo Graph to local tools, agents, and the UI. Route
registration should stay small and regular so new workflows have one obvious
place to live.

## Goal

Agents and developers should be able to discover the API from `/manifest`,
call documented endpoints, and map a route path back to the owning runtime
module without reading one large route file.

## Ownership

`repo_graph.api_runtime.routes.create_app()` owns FastAPI app construction and
the order of route registration.

Focused route modules own endpoint declarations:

| Module | Owns |
| --- | --- |
| `_ui_routes.py` | UI shell and static assets |
| `_system_routes.py` | health, manifest, and config inspection |
| `_source_routes.py` | configured sources, source sync, snapshot status, and source-related jobs |
| `_build_routes.py` | build, load, refresh, refresh-changed jobs, and job lookup |
| `_query_routes.py` | graph stats, scope, search, relationships, source files, neighbors, impact, and unresolved edge queries |
| `_report_routes.py` | unresolved, interactions, and database reconciliation reports |

The public API remains:

```python
from repo_graph.api import create_app
```

## Non-Ownership

Route modules should not:

- parse source configs directly
- run Git operations directly
- build or mutate graph objects directly
- run Neo4j Cypher directly
- format UI markup
- hide parser or graph-resolution policy

Routes translate HTTP input into calls to workflow, query, report, and storage
APIs. Those underlying modules own the behavior.

## Error Handling

Routes should convert expected workflow errors into HTTP responses:

- `ValueError` -> `400`
- `FileNotFoundError` or missing resource `KeyError` -> `404`
- external runtime failures such as build, refresh, or Neo4j failures -> `503`

Graph-query routes should use `repo_graph.api_runtime.errors.neo4j_http_exception`
when the failure is a Neo4j-backed query.

## Extension Workflow

When adding an endpoint:

1. Pick the owning route module by workflow.
2. Add the route there, not to `routes.py`.
3. Put behavior in an owning workflow/query/report module first.
4. Update `/manifest` endpoint docs when the public API changes.
5. Add synthetic API tests for the route or generated endpoint docs.
6. Run `pixi run audit`.

`routes.py` should remain a small coordinator. If it starts accumulating
endpoint functions again, split the endpoint into the owning route module.
