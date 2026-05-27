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
6. .NET scanner helpers: split C# syntax, C# symbols, C# routes, C#
   interactions, VB syntax, VB symbols, VB routes, and VB interactions. Done.
7. Database reconciliation report: split collection, grouping, summaries,
   constants, and SQL item normalization. Done.
8. Source resolver: split models, path resolution, GitHub expansion, Git
   checkout, sync workflows, resolution workflows, and status payloads. Done.
9. Scanner helper architecture: define the package-local helper split target
   for Python, shared interactions, SQL, and deployment scanners. Done.
10. Python scanner helpers: split AST values, symbols, imports, routes, HTTP,
    SQL, messaging, cache, scheduled jobs, and storage. Done.
11. Shared interaction helpers: split import, export, route, HTTP, and
    service/URL naming helpers. Done.
12. SQL scanner helpers: split definitions, references, naming, provenance,
    and interaction properties. Done.
13. Deployment helpers: split Kubernetes resources, environment/config links,
    ingress, selectors, and value normalization. Done.
14. .NET scanner facade cleanup: remove the package-level helper facade and
    import focused .NET scanner modules directly. Done.
15. Messaging helpers: split models, operation detection, target extraction,
    regex/method constants, and fact construction. Done.
16. Storage helpers: split models, operation detection, target extraction,
    regex/method constants, and fact construction. Done.
17. Cache helpers: split models, operation detection, target extraction,
    regex/method constants, and fact construction. Done.
18. Scheduled job helpers: split shared job fact construction from JavaScript
    cron extraction. Done.
19. .NET manifest helpers: split constants, XML parsing, project metadata,
    references, solution parsing, and framework config facts. Done.
20. .NET manifest scanner entrypoints: split project, packages config,
    framework config, build config, and solution scanners. Done.

Each split should preserve generated docs and public examples unless the
owning spec explicitly changes behavior.

## Next Split Candidates

After the report, database, storage, API, UI, and scanner helper splits, the
remaining runtime hotspots are narrower. The next candidates should come from a
fresh size and boundary report.

Large test files and generated documentation scripts can be split later, but
runtime package boundaries should stay the priority.

## Scanner Helper Package Target

Scanner helper modules should make extension points obvious. A scanner package
can have detailed internals, but the package surface should be small and the
owning scanner entry point should not need to import unrelated behavior.

Rules:

- Keep scanner entry points focused on file eligibility, parse orchestration,
  and visitor/state wiring.
- Put syntax or AST value extraction in one module per language or input
  family.
- Put symbol declaration and symbol call logic together.
- Put route declaration and route handler linking together.
- Put application interaction extraction in focused modules by domain when the
  language scanner owns domain-specific parsing: HTTP, SQL, messaging, cache,
  scheduled jobs, and storage.
- Keep shared helpers semantic, not library-specific. For example, HTTP helper
  modules can preserve `requests`, `fetch`, or `HttpClient` evidence, but the
  emitted relationship should still express application-to-application
  dependency facts.
- Use `helpers.py` facades only when there is an explicit migration reason.
  New scanner internals should import from the focused module that owns the
  behavior.

Target implementation slices:

```text
repo_graph/extraction/scanners/
  cache/
    __init__.py
    facts.py
    models.py
    operations.py
    patterns.py
    targets.py
  interactions/
    __init__.py
    imports.py
    exports.py
    routes.py
    http.py
    naming.py
  sql/
    __init__.py
    files.py
    definitions.py
    references.py
    properties.py
    provenance.py
    naming.py
  deployment/
    __init__.py
    kubernetes.py
    kubernetes_resources.py
    kubernetes_env.py
    kubernetes_ingress.py
    kubernetes_selectors.py
    kubernetes_values.py
  messaging/
    __init__.py
    facts.py
    models.py
    operations.py
    patterns.py
    targets.py
  storage/
    __init__.py
    facts.py
    models.py
    operations.py
    patterns.py
    targets.py
  scheduled_jobs/
    __init__.py
    facts.py
    javascript.py
  manifests/
    dotnet/
      __init__.py
      build_config.py
      config.py
      constants.py
      framework_config.py
      metadata.py
      packages_config.py
      paths.py
      project.py
      references.py
      solution.py
      solutions.py
      xml_utils.py
  code/
    python/
      __init__.py
      scanner.py
      ast_values.py
      symbols.py
      imports.py
      routes.py
      http.py
      sql.py
      messaging.py
      cache.py
      jobs.py
      storage.py
```

Shared helper facades may remain only when an existing public surface needs a
temporary bridge. The target is not fewer files; the target is one obvious
place to add a behavior without reading unrelated scanner domains.

## Sources Package Target

Source resolution owns where code and database metadata come from. It should
not parse source files, introspect database catalogs, construct graph IDs, or
serve API response shapes.

```text
repo_graph/sources/
  __init__.py
  _models.py
  _paths.py
  _github.py
  _git.py
  _expansion.py
  _resolution.py
  _sync.py
  _status.py
  _resolver.py
```

`repo_graph.sources` remains the public import surface for CLI, API,
extraction, snapshots, and docs code. `_resolver.py` is a compatibility facade
for older internal imports; new code should import through the package root or
the focused module that owns the behavior.

Responsibilities:

- `_models.py`: resolved source data models.
- `_paths.py`: local and cache path naming.
- `_github.py`: GitHub organization expansion, pagination, filtering, and
  token/header creation.
- `_git.py`: Git checkout, fetch, branch selection, commit, origin, and command
  execution helpers.
- `_expansion.py`: configured source expansion and duplicate-name checks.
- `_resolution.py`: converting configured sources into `ResolvedSource`
  records.
- `_sync.py`: source sync orchestration.
- `_status.py`: inspect/sync status payloads and database connector readiness.

## .NET Scanner Package Target

The .NET scanner package supports both modern C# and legacy VB. `scanner.py`
owns the scan loop and scanner registration. Language-specific parsing details
live in focused helpers so a route change does not require reading symbol
resolution, SQL extraction, and legacy HTTP logic.

```text
repo_graph/extraction/scanners/code/dotnet/
  __init__.py
  scanner.py
  csharp_syntax.py
  csharp_symbols.py
  csharp_routes.py
  csharp_interactions.py
  vb_syntax.py
  vb_symbols.py
  vb_routes.py
  vb_interactions.py
```

Responsibilities:

- `scanner.py`: line iteration, project context, scope state, and scanner
  registration.
- `csharp_syntax.py` and `vb_syntax.py`: language syntax regexes, scope text,
  attributes, and string normalization.
- `csharp_symbols.py` and `vb_symbols.py`: symbol declarations and local call
  relationships.
- `csharp_routes.py` and `vb_routes.py`: endpoint declarations and route
  handler links.
- `csharp_interactions.py` and `vb_interactions.py`: application-to-application
  and application-to-database interaction facts found in code.

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
  database_reconciliation/
    __init__.py
    _builder.py
    _constants.py
    _groups.py
    _normalization.py
    _summaries.py
  interactions.py
  unresolved.py
```

`repo_graph.reports` remains the public import surface for CLI and API code.
The focused modules own report-specific grouping, filtering, examples,
hotspots, and summary calculations.

The database reconciliation report is a package because it combines multiple
classification workflows. `_builder.py` owns the public report shape,
`_groups.py` owns classification accumulation, `_summaries.py` owns totals and
hotspots, `_normalization.py` owns SQL entity and edge normalization, and
`_constants.py` owns classification vocabulary.

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
