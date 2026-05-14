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

For larger source sets, use the job API:

```bash
curl -X POST http://localhost:8000/jobs/build-load \
  -H "content-type: application/json" \
  -d '{"strict":true}'
```

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

## Get Entity Details

Fetch one entity by ID:

```bash
curl "http://localhost:8000/entities/<entity_id>"
```

Use this after search when you need stable identity, source provenance, file
path, line number, aliases, or parser-specific properties.

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

The current neighbor endpoint supports `depth=1`. Multi-hop traversal should
wait until the API has clearer safeguards and result shaping.

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
- `count`: how many unresolved edges matched the same target
- `source_names`: which sources reference that target
- `examples`: bounded file and line evidence

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

Find missing graph scope:

1. Call `/reports/unresolved`.
2. Review high-count `likely_missing_source` groups first.
3. Check `ambiguous_target` groups before trusting cross-source answers.
4. Treat `likely_parser_gap` groups as candidates for deeper extraction.

## Raw Cypher

`POST /query` is intentionally unavailable. Raw Cypher may be added later
behind an explicit read-only configuration flag or replaced by more
purpose-built endpoints.
