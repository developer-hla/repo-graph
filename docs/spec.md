# Repo Graph MVP Spec

## Problem

Teams often need to understand how code in multiple repositories connects:
API calls, imports, package dependencies, SQL tables, stored procedures,
database schemas, and other cross-boundary references. That understanding is
usually spread across code search, tribal knowledge, and outdated diagrams.

Repo Graph should turn local or remote repository sets into a queryable graph
that developers and agents can use.

## Users

- A developer scans a few repositories in their daily working area.
- A tech lead scans one product or domain.
- An architect scans many repositories across an organization.
- An agent queries the graph before answering architecture questions.

## Non-Goals For The Public Tool

- It should not ship private repository names or company-specific profiles.
- It should not require code to be copied into this repo.
- It should not assume a single Git provider.
- It should not require one central graph for all users.

## Source Model

Sources are declared in a config file. A source may be a local path, a specific
Git repository, a GitHub organization query that expands to Git repositories,
or an optional `database` source that adds read-only metadata introspection for
current database state; see
[database-introspection.md](database-introspection.md).

Each graph build records:

- source name
- source type
- repository URL when available
- branch or ref
- commit SHA
- scan time
- file path and line provenance for entities and edges

Example:

```yaml
name: example-domain
cache_dir: .repo-graph/cache/repos

sources:
  - type: git
    name: api-service
    url: https://github.com/example/api-service.git
    ref: default

  - type: github_org
    name: example-org
    org: example
    visibility: all
    ref: default
    limit: 50
    include:
      archived: false
      forks: false
      name_patterns:
        - "-service$"

  - type: local_path
    name: local-library
    path: ../local-library
```

The database source shape is defined in
[database-introspection.md](database-introspection.md). This source type is
parsed and validated for supported engines. Build and refresh workflows read
live SQL Server and PostgreSQL metadata when the optional driver and configured
environment variable are available. A database source error should not prevent
repository sources in the same config from being scanned.

The implementation architecture is defined separately in
[architecture.md](architecture.md). Meaningful changes to scanner contracts,
graph construction, storage, API, reports, UI, or incremental refresh should
follow [spec-driven-development.md](spec-driven-development.md).

## Graph Model

The graph has two primary concepts:

- Entity: a thing found in source code, such as a repository, project, file,
  package, API endpoint, SQL table, SQL view, stored procedure, function, class,
  or config value.
- Edge: a relationship between entities or between an entity and an unresolved
  target string.

Every edge should include:

- edge type
- source entity
- target entity or unresolved target name
- source repository
- file path
- line number when available
- confidence level
- parser name

Edge types should be semantic. For dependency and interaction edges, the graph
should say that a UI calls an API, an API calls another service, a service uses
a SQL object, or a project depends on another project or package. The parser
should not make users think in terms of a specific syntax shape or HTTP client
library.

Interaction evidence belongs on the edge. When known, HTTP and service-call
edges should carry protocol, method, route or target path, raw target,
normalized target, config key, client library, parser, file path, and line
number. Agents should summarize these as app-boundary dependencies and use the
evidence for proof and drill-down.

When a parser can identify the handler for an endpoint, the graph should link
the route to that function with `HANDLES_ROUTE`. Runtime and database calls
inside that function should use the function as the edge source while keeping
file and line evidence. This lets blast-radius queries follow paths such as:

```text
endpoint -> handler function -> database table or stored procedure
endpoint -> handler function -> service-layer function -> database table
```

Internal code delegation should use `CALLS_SYMBOL` when a parser can identify
that one function calls another discovered function or method. Parser-specific
syntax such as `self.method()`, `Worker().load()`, or a direct local function
call is evidence for the same semantic edge.

Scanners should not construct the final graph directly. The target architecture
has scanners emit typed facts with source evidence, then a graph constructor
turns those facts into entities, edges, IDs, resolved references, unresolved
targets, summaries, and JSON/storage output.

Unresolved edges are expected. They mean a reference was found but the scanner
could not map it to a known entity in the current graph scope.

## Storage

MVP storage should support:

- JSON export for portability
- Neo4j load for relationship queries
- HTTP API for agent queries

Neo4j is a good first graph database because it is easy to run in Docker and
agents can express useful questions in Cypher.

The initial Neo4j runtime stores `RepoGraphEntity` nodes, `RepoGraphTarget`
nodes for unresolved references, a `RepoGraphGraph` metadata node, and typed
relationships derived from graph edge types.

## API MVP

- `GET /health`
- `GET /config`
- `GET /sources/configured`
- `POST /sync`
- `POST /build`
- `POST /build-load`
- `POST /snapshot/status`
- `POST /refresh`
- `POST /jobs/sync`
- `POST /jobs/build`
- `POST /jobs/build-load`
- `POST /jobs/snapshot-status`
- `POST /jobs/refresh`
- `POST /jobs/refresh-changed`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /load`
- `POST /query`
- `GET /stats`
- `GET /scope`
- `GET /sources`
- `GET /sources/{source_name}/overview`
- `GET /sources/{source_name}/files/snippet`
- `GET /explore`
- `GET /entities/search`
- `GET /relationships/search`
- `GET /entities/neighbors`
- `GET /entities/{entity_id}/overview`
- `GET /reports/interactions`
- `GET /reports/database-reconciliation`
- `GET /manifest`

The manifest tells agents how to use the running graph and what scope was
loaded.

The first public runtime surface should support synchronous local build and
load orchestration:

- `GET /config`
- `GET /sources/configured`
- `POST /sync`
- `POST /build`
- `POST /build-load`
- `POST /snapshot/status`
- `POST /refresh`
- `POST /load`

For large source sets, an in-memory local job API should support:

- `POST /jobs/sync`
- `POST /jobs/build`
- `POST /jobs/build-load`
- `POST /jobs/snapshot-status`
- `POST /jobs/refresh`
- `POST /jobs/refresh-changed`
- `GET /jobs`
- `GET /jobs/{job_id}`

Jobs are not durable. If the API process restarts, job history is lost.

The API should expose graph scope metadata so agents can state which sources,
refs, and commits were loaded:

- `GET /scope`
- `GET /sources`

The configured source API should expose source readiness before graph load:

- source name and type
- configured path, URL, and ref
- resolved local path
- exists/missing status
- Git repository presence
- current commit when known
- sync outcome and per-source errors when `/sync` or `/jobs/sync` is used

The first public query surface should use purpose-built read endpoints:

- `GET /explore`
- `GET /entities/search`
- `GET /relationships/search`
- `GET /entities/{entity_id}`
- `GET /entities/{entity_id}/overview`
- `GET /entities/{entity_id}/neighbors`
- `GET /entities/{entity_id}/impact`
- `GET /sources/{source_name}/overview`
- `GET /sources/{source_name}/files/snippet`
- `GET /edges/unresolved`
- `GET /reports/interactions`
- `GET /reports/database-reconciliation`
- `GET /reports/unresolved`
- `GET /ui`

Raw Cypher should stay unavailable until there is an explicit read-only mode
and clear result limits.

The first UI should be a navigable local control plane over these endpoints.
It should start with workflow pages for graph overview, entity search, impact
analysis, unresolved-reference review, database drift review, and refresh jobs.
Source, entity, relationship, and snippet evidence views should remain
available as contextual drilldowns rather than primary navigation items.
Advanced filters should stay available, but the default surface should
emphasize the question a user is trying to answer rather than every query
parameter.
UI routes should be shareable through hash query parameters so developers and
agents can link directly to a search, entity overview, impact query,
unresolved triage filter, database drift filter, or relationship evidence view.

Impact queries should default to dependency and usage edges so refactor
blast-radius results are not dominated by containment or declaration paths.
Agents can request `profile=all` for raw graph traversal or
`profile=structural` for containment and declaration paths.
The impact UI should let users find a start entity from the same workflow
instead of requiring a copied entity ID from another page. Start-entity search,
trace controls, affected-source summaries, and path evidence should be shown as
one shareable hash route.
Impact responses should include ordered path steps with edge evidence so users
can see the proof chain for each affected entity.
Impact and entity overview responses should also include source coverage
warnings derived from unresolved references. This keeps blast-radius answers
honest when missing source scope, parser gaps, or ambiguous targets may hide
additional relationships.

## CLI MVP

```bash
repo-graph sync --config path/to/sources.yaml
repo-graph build --config path/to/sources.yaml --output graph.json
repo-graph build --config path/to/sources.yaml --strict
repo-graph build --cached --config path/to/sources.yaml --strict
repo-graph refresh --config path/to/sources.yaml --load
repo-graph load --graph graph.json
repo-graph load --graph graph.json --replace-source api-service
repo-graph snapshot status --config path/to/sources.yaml
repo-graph snapshot write --config path/to/sources.yaml
repo-graph source-graphs write --config path/to/sources.yaml
repo-graph serve --config path/to/sources.yaml
repo-graph agent-instructions --api-url http://localhost:8000 --config path/to/sources.yaml
```

## Incremental Build Direction

RepoGraph should move from full rebuilds toward source-level incremental
updates. The first foundation is a source snapshot:

- source name, type, path, URL, ref, and commit
- tool, graph schema, and parser fingerprint
- scannable file paths, sizes, and content hashes

Snapshots are stored under `.repo-graph/sources/<source>/snapshot.json`.
Changed-source detection compares the current snapshot to the saved one and
reports added, modified, removed, or metadata-changed sources.

The API exposes that same comparison through `POST /snapshot/status` and
`POST /jobs/snapshot-status` so agents and the UI can preview changed sources
without writing graph artifacts or loading Neo4j.

Source-level graph artifacts are stored beside snapshots under
`.repo-graph/sources/<source>/graph.json`. These artifacts scan one source at a
time and intentionally defer global resolution. The `build --cached` path
reuses unchanged source graph artifacts, rebuilds changed source graphs, merges
the source artifacts, and then recomputes cross-source resolution once before
loading. That preserves correctness while reducing scanner work.

The `refresh` command wraps the cached build path into the first end-to-end
incremental workflow. Without `--load`, it refreshes source graph artifacts,
writes the merged graph JSON, and reports changed, rebuilt, and reused sources.
With `--load`, it loads the full graph when Neo4j has no current graph or a
different scope loaded; otherwise, it replaces only the sources that changed.

The `POST /jobs/refresh-changed` API job is the agent-friendly keep-current
path. It checks source snapshot status first, skips when no sources changed,
and otherwise runs refresh with Neo4j loading enabled. This gives agents a
single endpoint for updating local graph data without doing work when the
source set is already current.

The later Neo4j incremental path should use the same source identity and
snapshot metadata to replace one changed source at a time. Source replacement
loads a globally resolved graph, deletes selected source-owned data, removes
current graph edge IDs before replaying relationships, and cleans orphan
unresolved targets. That lets changed sources be refreshed without clearing the
whole database while still letting inbound cross-source references move between
resolved and unresolved states.

## Parser MVP

Start with parsers that are useful across many codebases:

- Git metadata
- project discovery from package manifests and workspaces
- JavaScript, Python, and .NET package manifests and dependency declarations
- .NET solution, project reference, and shared build config manifests
- legacy .NET Framework `Web.config`, `App.config`, `packages.config`,
  ASMX/WCF endpoints, VB symbols, conservative VB internal calls,
  config-driven service URLs, and SQL command stored procedure references
- modern C#/.NET controller routes, minimal API routes, symbols, and HTTP
  service calls, plus conservative same-class or explicit class method calls
- Python imports, FastAPI or Flask routes, HTTP calls, and exported
  application symbols, plus conservative local function and method calls
- Kubernetes services, deployments, containers, ingress routes, and
  service-selection topology
- TypeScript and JavaScript imports, exports, route declarations, named route
  handlers, and conservative same-file function calls
- HTTP calls from `fetch` and common client libraries
- messaging publish and consume calls for topics, queues, and event contracts
- shared storage reads and writes for paths, buckets, blobs, and file drops
- cache key reads and writes
- scheduled job declarations with handler links when available
- SQL tables, views, functions, and stored procedures
- SQL references from application code

The default extractor pass should do useful discovery without asking users to
predefine relationships. Configurable dependency filters should run after
global graph resolution so they can reduce third-party package noise without
discarding relationships discovered from the scanned sources.

Future parser slices should add:

- deeper database metadata such as computed dependencies and richer trigger body impact
- route/function/query context so endpoint impact paths do not stop at file
  ownership
- deeper MSBuild metadata
- optional LLM-assisted documentation discovery that emits evidence-backed
  candidate entities and edges

## Database Introspection Direction

SQL revision and migration files are historical evidence. They can describe
objects that no longer exist, so they should not be treated as authoritative
current database state by default.

RepoGraph supports an optional `database` source type contract, an engine
metadata adapter registry, and live SQL Server and PostgreSQL metadata
connectors. The SQL Server connector reads catalog metadata through optional
`pyodbc` and a SQL Server ODBC driver. The PostgreSQL connector reads catalog
metadata through optional `psycopg`. Other database engines should use
engine-specific catalogs while emitting the same normalized graph vocabulary.
Connectors must not read table data.

Generated facts from source files should include provenance such as
`schema_state=current_schema`, `schema_state=historical`, or
`schema_state=unknown`. Introspected facts should use
`schema_state=current_database`. Agents should prefer current-database facts
when answering current-state schema questions, while still using code and
history evidence to explain drift, stale references, and migration-only
objects.

Database connections must be opt-in, read-only, timeout-limited, and configured
through ignored private config or environment variables. Public examples should
stay synthetic and must not include real server names, database names, or
connection strings.

## Public/Private Boundary

Public repo:

- tool code
- generic examples
- schema docs
- tests with synthetic fixtures

Private local config:

- real organization names
- real repository lists
- real generated graphs
- internal database names
- internal API examples

## MVP Milestones

1. Config loader and source model.
2. Git sync into a local cache.
3. JSON graph builder with repository, project, package, and file entities.
4. JavaScript, Python, .NET, HTTP, route, and SQL parser slices.
5. Neo4j loader.
6. FastAPI query service.
7. Docker Compose runtime.
8. Agent manifest and usage docs.
