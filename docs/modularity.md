# Modularity And Maintainability

Repo Graph should be easy to extend without making contributors understand a
large unrelated file first. Directory structure, package boundaries, and file
shape are part of the public architecture.

This document defines how to keep modules small, regular, and owned by one
layer.

## Goals

- Make the owning layer obvious from the path.
- Keep public package APIs small and documented.
- Let internals be detailed without leaking across layers.
- Keep report, parser, storage, API, and UI changes easy to review in isolation.
- Give agents one obvious place to add a new capability.

## File Shape Rules

Line count is a signal, not the only rule. A file should be split when it mixes
multiple responsibilities, when a small change requires reading unrelated code,
or when tests need to exercise unrelated behavior to cover one feature.

Use these soft limits:

- Under 300 lines: usually fine when the file has one clear responsibility.
- 300-600 lines: acceptable for cohesive domain logic, but watch for helper
  drift.
- Over 600 lines: should have a clear reason or a split plan.
- Over 1,000 lines: treat as architecture debt unless it is generated code.

Generated docs and generated references are exempt. Runtime source files are
not exempt.

## Package Surface Rules

Each package should expose a small public API from `__init__.py`. Code outside
the package should import that public API unless it is extending an explicitly
documented subpackage.

Private modules should use a leading underscore only when they are true
package internals. A private module should not become a new dumping ground.

Package internals may be split by:

- domain concept, such as `blast_radius`, `unresolved`, or `interactions`
- engine, such as `sqlserver` or `postgres`
- workflow step, such as `requests`, `routes`, or `responses`
- adapter boundary, such as `records`, `payloads`, or `queries`

Avoid splitting by vague buckets such as `utils`, `misc`, or `helpers` unless
the helper module is small and package-local.

## Refactor Rules

Refactors should move one boundary at a time. Do not combine a module split
with behavior changes unless the behavior change is required to preserve the
contract.

For a modularity slice:

1. State the ownership problem.
2. Add or update this spec or the owning architecture spec.
3. Move code into cohesive modules.
4. Keep the package public API stable unless the spec says otherwise.
5. Run focused tests for the moved behavior.
6. Run `pixi run audit`.

## Current Split Plan

The largest runtime files should be addressed in this order:

1. Reports: split report builders by report type. Done.
2. Database metadata: split row models, engine registry, live connectors,
   catalog queries, and fact adapters. Done.
3. Neo4j storage: split read operations, write operations, Cypher, payload
   mapping, and record preparation. Done.
4. API runtime: split request models, runtime settings, workflow handlers,
   query/report response builders, and route registration. Done.
5. UI runtime: split router, API client, views, components, and formatters.
   Done.

Each split should preserve generated docs and public examples unless the
owning spec explicitly changes behavior.

## Reports Package Target

Report builders are read-only projections over graph data. They should not
parse source code, mutate graph state, query Neo4j directly, or know API route
registration details.

The reports package is organized by report type:

```text
repo_graph/reports/
  __init__.py
  _common.py
  blast_radius.py
  database_reconciliation.py
  interactions.py
  unresolved.py
```

`repo_graph.reports` remains the public import surface for CLI and API code.
The focused modules own report-specific grouping, filtering, examples,
hotspots, and summary calculations.

## Database Package Target

Database metadata code is split by contract and engine:

```text
repo_graph/database/
  __init__.py
  _constants.py
  _models.py
  _naming.py
  _adapters.py
  _adapter_common.py
  _sqlserver_adapter.py
  _postgres_adapter.py
  _connectors.py
  _readers.py
  _reader_common.py
  _sqlserver_reader.py
  _postgres_reader.py
  _metadata.py
```

`repo_graph.database` remains the public import surface. `_metadata.py` is a
compatibility facade for older internal imports; new code should import through
the package root or the focused module that owns the behavior.

Responsibilities:

- `_models.py`: typed metadata rows, source requests, scan results, and graph
  adapter result types.
- `_adapters.py`: engine registry and generic dispatch.
- `_sqlserver_adapter.py` and `_postgres_adapter.py`: pure metadata-row to
  fact conversion for each engine.
- `_connectors.py`: live connector entry points and safe connection handling.
- `_sqlserver_reader.py` and `_postgres_reader.py`: bounded catalog queries
  for each engine.
- `_adapter_common.py`, `_reader_common.py`, `_constants.py`, and
  `_naming.py`: small package-local shared contracts.

## Storage Package Target

Storage adapters persist and query already-built graph records. They should not
parse files, construct graph IDs, resolve references, or own API response
workflow.

The Neo4j storage adapter is organized by responsibility:

```text
repo_graph/storage/
  __init__.py
  _neo4j.py
  _neo4j_common.py
  _neo4j_loader.py
  _neo4j_models.py
  _neo4j_payloads.py
  _neo4j_queries.py
  _neo4j_reads.py
  _neo4j_records.py
  _neo4j_settings.py
  _neo4j_writes.py
```

`repo_graph.storage` remains the public import surface for CLI, API, and
refresh code. `_neo4j.py` is a compatibility facade for older internal imports;
new code should import through the package root or the focused module that owns
the behavior.

Responsibilities:

- `_neo4j_settings.py`: environment-backed connection settings.
- `_neo4j_models.py`: typed storage return values and prepared record groups.
- `_neo4j_loader.py`: load orchestration from graph JSON into Neo4j.
- `_neo4j_records.py`: conversion from graph export dictionaries to write
  records.
- `_neo4j_writes.py`: schema setup and write transactions.
- `_neo4j_reads.py`: read workflows and result shaping.
- `_neo4j_queries.py`: Cypher query text builders.
- `_neo4j_payloads.py`: Neo4j records mapped into API/report payloads.
- `_neo4j_common.py`: small adapter-local normalization helpers.

## API Runtime Target

`repo_graph.api` is the public facade used by the CLI, docs generator, tests,
and external callers. Runtime implementation should live in focused
`repo_graph.api_runtime` modules so adding a route or response builder does
not require editing a monolithic API file.

The API runtime package is organized by workflow boundary:

```text
repo_graph/
  api.py
  api_runtime/
    __init__.py
    config_workflows.py
    constants.py
    coverage.py
    errors.py
    manifest.py
    query_responses.py
    relationships.py
    report_responses.py
    requests.py
    routes.py
    settings.py
    source_files.py
```

Responsibilities:

- `api.py`: stable public import surface and default `app`.
- `requests.py`: Pydantic request models.
- `settings.py`: runtime settings, environment parsing, and path resolution.
- `manifest.py`: health, manifest, and UI shell helpers.
- `config_workflows.py`: config, sync, build, load, refresh, and job
  workflows.
- `query_responses.py`: Neo4j-backed graph query response builders.
- `report_responses.py`: report endpoint response builders.
- `source_files.py`: source root lookup and safe snippet reads.
- `coverage.py` and `relationships.py`: shared response grouping and warning
  helpers.
- `routes.py`: FastAPI route registration only.
- `errors.py`: HTTP exception mapping.

Tests should patch the owning implementation module, not `repo_graph.api`, when
they need to replace storage, config, refresh, or build dependencies.

## UI Runtime Target

The browser UI is served as static assets. It should remain build-tool-free for
now, but the runtime should still be split by responsibility so UI changes are
easy to review and syntax-check.

```text
repo_graph/ui/
  index.html
  styles.css
  actions.js
  api-client.js
  app.js
  components.js
  events.js
  formatters.js
  markup.js
  operations-markup.js
  relationship-markup.js
  report-markup.js
  routing.js
  views.js
```

Responsibilities:

- `app.js`: state initialization, route table, DOM bindings, and boot.
- `api-client.js`: HTTP helpers and API error shaping.
- `views.js`: top-level view renderers.
- `actions.js`: async workflow actions that update result panels.
- `events.js`: document click and submit delegation.
- `routing.js`: hash route writing and route parameter serialization.
- `components.js`: generic HTML controls and containers.
- `formatters.js`: escaping, dates, values, status labels, and small row
  formatters.
- `markup.js`, `relationship-markup.js`, `operations-markup.js`, and
  `report-markup.js`: domain-specific HTML projections.

All UI JavaScript files must pass `pixi run ui-check`; do not add a new UI
script without making it part of the static shell and syntax check.
