# Agent Usage

Repo Graph exposes a local HTTP API that agents can use after a graph has been
built and loaded into Neo4j.

Start by reading the manifest:

```bash
curl http://localhost:8000/manifest
```

The manifest lists available endpoints, graph store configuration, and planned
capabilities. Agents should prefer the documented read endpoints below instead
of trying to execute raw Cypher.

Agents should explain graph results in terms of application-boundary
dependencies. For example, say that one UI or service depends on another API
over HTTP, then cite edge evidence such as method, route, raw target, parser,
file path, and line number. Do not make the HTTP client library the main user
facing relationship.

For the generated endpoint inventory, see
[generated/api-endpoints.md](generated/api-endpoints.md). This guide stays
curated so agents know which endpoints to call for common workflows.

## Project AGENTS.md Snippet

Generate a short Markdown snippet for a repository that should point agents at
Repo Graph:

```bash
pixi run repo-graph agent-instructions \
  --api-url http://localhost:8000 \
  --config ../my-repo-graph-sources.yaml
```

Add the output to that repository's private `AGENTS.md` or equivalent agent
instructions. The snippet is intentionally Markdown, not a second JSON
discovery schema. Agents should still call `/manifest` to discover the live API
surface.

## Config And Source Status

For generated config field details, see
[generated/config-reference.md](generated/config-reference.md).

Inspect the active config without building the graph:

```bash
curl http://localhost:8000/config
```

Inspect configured sources and local readiness:

```bash
curl http://localhost:8000/sources/configured
```

Useful source status fields:

- `name`
- `type`
- `configured`
- `resolved_path`
- `exists`
- `git_repo_present`
- `current_commit`
- `ref`
- `ready`
- `problems`

Sync configured sources before building:

```bash
curl -X POST http://localhost:8000/sync \
  -H "content-type: application/json" \
  -d '{}'
```

For larger source sets, submit sync as a job:

```bash
curl -X POST http://localhost:8000/jobs/sync \
  -H "content-type: application/json" \
  -d '{}'
```

`/sources/configured` describes what the runtime can see on disk. `/sources`
describes what was loaded into Neo4j from the most recent graph load.

For private GitHub repositories in Docker, operators should put `GITHUB_TOKEN`
in local `.env`; that file is ignored and must not be committed. The token is
used for GitHub org discovery and HTTPS clone/fetch. Agents should not ask
users to place tokens in source config files. Operators can point Docker at an
ignored private config by setting `REPO_GRAPH_CONFIG` in `.env` to a container
path such as `/app/config/private-my-sources.yaml`.

## Change Preview

Preview changed sources before running an incremental refresh:

```bash
curl -X POST http://localhost:8000/snapshot/status \
  -H "content-type: application/json" \
  -d '{}'
```

Use `sync:true` to clone or update Git sources before comparing snapshots:

```bash
curl -X POST http://localhost:8000/snapshot/status \
  -H "content-type: application/json" \
  -d '{"sync":true}'
```

Useful response fields:

- `changed_count`
- `unchanged_count`
- `items[].source_name`
- `items[].status`
- `items[].reasons`
- `items[].added_files`
- `items[].modified_files`
- `items[].removed_files`

For larger source sets, submit the preview as a job:

```bash
curl -X POST http://localhost:8000/jobs/snapshot-status \
  -H "content-type: application/json" \
  -d '{}'
```

Agents should use this endpoint when they need to explain what would be
refreshed without changing graph artifacts or Neo4j.

## Build And Load

Build the active config and load the result into Neo4j:

```bash
curl -X POST http://localhost:8000/build-load \
  -H "content-type: application/json" \
  -d '{"strict":true}'
```

Useful request fields:

- `config_path`: optional config path inside the running API environment.
- `output_path`: optional graph JSON output path.
- `sync`: clone or update Git sources before scanning.
- `strict`: fail the build when scanner errors are present.
- `max_file_bytes`: skip files larger than this size.
- `clear_existing`: clear prior Repo Graph data before loading.

Build without loading:

```bash
curl -X POST http://localhost:8000/build \
  -H "content-type: application/json" \
  -d '{"strict":true}'
```

Refresh incrementally and load changed sources into Neo4j:

```bash
curl -X POST http://localhost:8000/refresh \
  -H "content-type: application/json" \
  -d '{"strict":true,"load":true}'
```

`/refresh` writes the merged graph JSON, reports changed, rebuilt, and reused
sources, and with `load:true` updates Neo4j. It full-loads when no graph is
loaded or when the loaded scope/source set differs; otherwise, it replaces only
changed sources.

For larger source sets, use the job API:

```bash
curl -X POST http://localhost:8000/jobs/build-load \
  -H "content-type: application/json" \
  -d '{"strict":true}'

curl -X POST http://localhost:8000/jobs/refresh \
  -H "content-type: application/json" \
  -d '{"strict":true,"load":true}'
```

To keep Neo4j current without rebuilding when nothing changed, use the
refresh-changed job:

```bash
curl -X POST http://localhost:8000/jobs/refresh-changed \
  -H "content-type: application/json" \
  -d '{"strict":true}'
```

`/jobs/refresh-changed` checks snapshot status first. If no sources changed,
the job result has `status:"skipped"` and no graph artifacts or Neo4j data are
updated. If sources changed, it runs refresh with loading enabled and reports
changed sources, rebuilt and reused source graph counts, and the Neo4j load
mode (`full_load`, `replace_sources`, or `skipped`).

Poll the returned `job_id`:

```bash
curl http://localhost:8000/jobs/<job_id>
```

List recent jobs:

```bash
curl http://localhost:8000/jobs
curl "http://localhost:8000/jobs?status=running"
curl "http://localhost:8000/jobs?kind=build-load"
```

Job statuses are:

- `queued`
- `running`
- `succeeded`
- `failed`

Jobs are in-memory and local to the running API process. If the API container
restarts, job history is lost. Agents should use jobs for long-running local
work, not as durable audit history.

## Load Status

Check graph counts:

```bash
curl http://localhost:8000/stats
```

Useful fields:

- `entity_count`
- `edge_count`
- `resolved_edge_count`
- `unresolved_edge_count`
- `unresolved_target_count`

## Scope And Sources

Inspect the loaded graph scope:

```bash
curl http://localhost:8000/scope
```

The scope response includes graph metadata, summary counts, and the loaded
source list. Use it before answering architecture questions so you can name the
actual graph scope and avoid implying that repositories outside the loaded
source set were scanned.

List only loaded sources:

```bash
curl http://localhost:8000/sources
```

Useful source fields:

- `name`
- `type`
- `path`
- `url`
- `ref`
- `commit`

## Explore The Graph

Use Explore before starting broad architecture work:

```bash
curl "http://localhost:8000/explore"
```

The response gives bounded aggregate views that are easier to scan than raw
graph paths:

- `entity_types`: entity type counts with common starting points such as
  routes, SQL objects, files, services, and packages.
- `edge_types`: relationship type counts, including resolved and unresolved
  counts.
- `sources`: per-source entity, edge, and unresolved edge counts.
- `cross_source_edges`: resolved relationships where the source and target
  entity live in different loaded sources.

Use this endpoint to choose a source, entity type, edge type, or unresolved
hotspot before drilling into Search, Impact, or Unresolved.

## Inspect One Source

Use source overview when a question starts from one repository or source:

```bash
curl "http://localhost:8000/sources/<source_name>/overview"
```

The response shows:

- source metadata and summary counts
- entity and relationship type counts scoped to that source
- owned surface examples, such as routes, packages, services, and SQL objects
- dependency/use targets discovered in that source
- outgoing and incoming cross-source relationships
- unresolved hotspots for that source

Use this before answering what a repository owns, what it depends on, what
depends on it, or where its missing graph coverage is concentrated.

## Inspect Source Snippets

Use source snippets when relationship evidence includes a source name, file
path, and line number:

```bash
curl "http://localhost:8000/sources/<source_name>/files/snippet?path=src/app.py&line=42&context=3"
```

The snippet endpoint reads local files only. The path must stay inside the
configured or loaded source root, context is capped, and large files are
rejected. Use this to quote or inspect the local code around an edge before
making a refactor claim.

## Search Entities

Find entities by name, file path, ID, alias, or full name:

```bash
curl "http://localhost:8000/entities/search?q=accounts&limit=10"
```

Filter by entity type:

```bash
curl "http://localhost:8000/entities/search?type=api_route"
curl "http://localhost:8000/entities/search?type=stored_procedure"
curl "http://localhost:8000/entities/search?type=sql_table"
```

Filter by source:

```bash
curl "http://localhost:8000/entities/search?source=api-service"
```

## Search Relationship Evidence

Use relationship search when you need proof for why one source depends on
another source or why one kind of entity points at another:

```bash
curl "http://localhost:8000/relationships/search?from_source=api-service&to_source=database"
```

Useful filters:

```bash
curl "http://localhost:8000/relationships/search?type=CALLS_SQL"
curl "http://localhost:8000/relationships/search?from_type=api_route&to_type=stored_procedure"
curl "http://localhost:8000/relationships/search?from_source=api-service&to_source=database&type=CALLS_SQL"
curl "http://localhost:8000/relationships/search?resolved=false"
```

The response includes grouped counts plus exact edge evidence: from entity,
target entity or unresolved target, source names, file path, line number,
parser, confidence, and edge properties. Use this before making a refactor
claim that needs file-level evidence.

## Get Entity Details

Fetch one entity by ID:

```bash
curl "http://localhost:8000/entities/<entity_id>"
```

Use this after search when you need stable identity, source provenance, file
path, line number, aliases, or parser-specific properties.

## Inspect One Entity

Use entity overview when a question starts from one route, package, symbol,
SQL object, service, or file:

```bash
curl "http://localhost:8000/entities/<entity_id>/overview"
```

The response bundles:

- entity metadata
- `coverage`: unresolved-reference warnings for the entity's source, including
  sample truncation metadata
- direct incoming relationships and grouped counts
- direct outgoing relationships and grouped counts
- example relationship records for each direction

Use this before jumping to impact when you need local context around one graph
entity, such as who directly calls it, what it directly uses, or which source
owns the neighboring entities. If `coverage.status` is `warning`, mention that
direct relationship context may be incomplete and link the warning back to
`/reports/unresolved?source=<source_name>`.

## Get Neighbors

Show incoming and outgoing relationships for an entity:

```bash
curl "http://localhost:8000/entities/<entity_id>/neighbors"
```

Directional examples:

```bash
curl "http://localhost:8000/entities/<entity_id>/neighbors?direction=out"
curl "http://localhost:8000/entities/<entity_id>/neighbors?direction=in"
```

Filter by edge type:

```bash
curl "http://localhost:8000/entities/<entity_id>/neighbors?edge_type=CALLS_SQL"
curl "http://localhost:8000/entities/<entity_id>/neighbors?edge_type=IMPORTS"
```

Use bounded depth for local traversal:

```bash
curl "http://localhost:8000/entities/<entity_id>/neighbors?direction=both&depth=2"
```

The neighbor endpoint supports depth `1` through `3`. When `edge_type` is set
on a multi-hop request, every edge in the returned path must match that type.

## Get Impact

Use impact when you need a blast-radius view for a refactor, API change, SQL
object change, or service boundary question:

```bash
curl "http://localhost:8000/entities/<entity_id>/impact"
```

Impact defaults to incoming relationships at depth `2`, which answers "what
appears to depend on this entity?" Use `direction=out` to ask what the entity
touches. The default `profile=impact` follows dependency and usage edges such
as imports, package/project dependencies, service calls, HTTP calls, and SQL
references. It excludes structural graph edges like `CONTAINS_FILE` and
`DEFINES` so blast-radius results do not get padded with repository/file
containment paths.

Use `type` to restrict the traversal to one edge type:

```bash
curl "http://localhost:8000/entities/<entity_id>/impact?direction=in&depth=3"
curl "http://localhost:8000/entities/<entity_id>/impact?direction=out&type=CALLS_SQL"
curl "http://localhost:8000/entities/<entity_id>/impact?direction=in&type=CALLS_HTTP"
```

Use profiles when you need a different view of the same entity:

```bash
curl "http://localhost:8000/entities/<entity_id>/impact?profile=all"
curl "http://localhost:8000/entities/<entity_id>/impact?profile=structural"
```

Profiles:

- `impact`: dependency and usage edges; this is the default for blast radius.
- `all`: all graph paths, including containment and declaration edges.
- `structural`: containment and declaration edges only.

When `type` is provided, it is treated as an explicit edge request and is not
limited by the selected profile.

Useful response fields:

- `entity`: the root entity being investigated
- `profile`: selected impact profile
- `allowed_edge_types`: edge types used by the selected profile, or null when
  `profile=all` or `type` is provided
- `items`: bounded neighbor/path examples
- `items[].path.steps`: ordered edge-by-edge proof chain for each returned path
- `coverage`: unresolved-reference warnings for the start entity's source,
  including sample truncation metadata
- `affected_sources`: groups by source name with count, minimum depth, entity
  types, edge types, and examples
- `affected_source_count`: number of source groups in the result
- `path_groups`: counts grouped by affected source and edge type

Each path step includes `from`, `edge`, and `to`. The edge carries file path,
line number, parser, confidence, and source metadata when the parser found it.
Use source snippets for any step with file and line evidence.

Agents should treat this as evidence for likely blast radius, not a proof that
all runtime dependencies were discovered. If `coverage.warnings` is non-empty,
state that the known impact paths may be incomplete and inspect
`/reports/unresolved` for the same source before making a high-confidence
refactor claim.

The same core blast-radius shape is available from graph JSON when Neo4j is not
running:

```bash
repo-graph report blast-radius --graph .repo-graph/output/graph.json --entity-id <entity_id>
```

## Interaction Report

Use the grouped interaction report when the user wants the application or
database dependency map rather than individual file-level edges:

```bash
curl "http://localhost:8000/reports/interactions"
```

Filter by source, target source, or edge type:

```bash
curl "http://localhost:8000/reports/interactions?source=api-service"
curl "http://localhost:8000/reports/interactions?target_source=database-project"
curl "http://localhost:8000/reports/interactions?type=READS_SQL_OBJECT"
curl "http://localhost:8000/reports/interactions?type=WRITES_SQL_OBJECT"
curl "http://localhost:8000/reports/interactions?type=REFERENCES_SQL_OBJECT"
```

Report groups include `from_source`, `target_source`, `target_boundary`,
`dependency_scope`, `interaction_kind`, counts, and bounded evidence examples.
Use this report to summarize chains such as a UI calling an API, an API calling
another service, an application querying SQL, or a stored procedure/view reading
or writing a table. SQL schema references include provenance such as
`schema_state=current_schema`, `historical`, or `unknown`; do not treat
historical migration evidence as proof of the current database shape.

## Database Reconciliation Report

Use the database reconciliation report when current database metadata is loaded
and the user asks about schema drift, stale SQL references, or database objects
with no code evidence:

```bash
curl "http://localhost:8000/reports/database-reconciliation"
```

Filter by code/schema source or current database metadata source:

```bash
curl "http://localhost:8000/reports/database-reconciliation?source=api-service"
curl "http://localhost:8000/reports/database-reconciliation?database_source=current-db"
```

Report classifications include `code_only_reference`,
`unresolved_database_reference`, `schema_drift`, `migration_only_object`, and
`database_only_object`. Treat them as drift triage, not proof that an object is
unused.

The same report is available in the local UI at `/ui#database`. Use hash query
parameters such as `/ui#database?source=api-service` or
`/ui#database?databaseSource=current-db` when linking a user to a filtered
view.

## List Unresolved Edges

Unresolved edges show references that were found but not safely linked to an
entity in the current graph scope.

```bash
curl "http://localhost:8000/edges/unresolved"
```

Filter by source or edge type:

```bash
curl "http://localhost:8000/edges/unresolved?source=api-service"
curl "http://localhost:8000/edges/unresolved?type=CALLS_SQL"
```

Agents should mention unresolved edges as missing scope or unresolved parser
coverage, not automatically as unused code.

## Unresolved Report

Use the grouped unresolved report before deciding which repositories or parser
slices are missing:

```bash
curl "http://localhost:8000/reports/unresolved"
```

Filter by source or edge type:

```bash
curl "http://localhost:8000/reports/unresolved?source=api-service"
curl "http://localhost:8000/reports/unresolved?type=CALLS_SQL"
```

Report groups include:

- `classification`: a hint such as `likely_missing_source`,
  `ambiguous_target`, `likely_parser_gap`, or `needs_review`
- `recommended_action`: the next triage step suggested by the classification
- `count`: how many unresolved edges matched the same target
- `source_names`: which sources reference that target
- `examples`: bounded file and line evidence

The response also includes `classification_groups`, `source_hotspots`, and
`target_hotspots` so agents can summarize the highest-value follow-up work
before inspecting individual evidence examples.

Treat classifications as triage hints. They are not proof that code is unused
or that a repository is definitely missing.

## Common Agent Workflows

Find API routes:

```bash
curl "http://localhost:8000/entities/search?type=api_route&limit=50"
```

Find SQL objects:

```bash
curl "http://localhost:8000/entities/search?type=sql_table&limit=50"
curl "http://localhost:8000/entities/search?type=sql_view&limit=50"
curl "http://localhost:8000/entities/search?type=stored_procedure&limit=50"
```

Explain what a file touches:

1. Search for the file entity by path.
2. Fetch its neighbors.
3. Group outgoing edges by `edge_type`.

Estimate refactor blast radius:

1. Search for the API route, symbol, SQL object, service, file, or package.
2. Call `/entities/<entity_id>/impact?direction=in&depth=2`.
3. Review `affected_sources` before drilling into individual `items`.
4. Repeat with a narrower `type` filter when one relationship kind matters.

Find missing graph scope:

1. Call `/reports/unresolved`.
2. Review high-count `likely_missing_source` groups first.
3. Check `ambiguous_target` groups before trusting cross-source answers.
4. Treat `likely_parser_gap` groups as candidates for deeper extraction.

## Raw Cypher

`POST /query` is intentionally unavailable. Raw Cypher may be added later
behind an explicit read-only configuration flag or replaced by more
purpose-built endpoints.
