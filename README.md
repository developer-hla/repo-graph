# Repo Graph

[![repo-graph-ci](https://github.com/developer-hla/repo-graph/actions/workflows/repo-graph-ci.yaml/badge.svg)](https://github.com/developer-hla/repo-graph/actions/workflows/repo-graph-ci.yaml)

Repo Graph builds a local interaction graph from one or more source
repositories. It helps developers and agents answer questions about API calls,
imports, package dependencies, project references, SQL objects, Kubernetes
topology, and unresolved references without relying on stale diagrams or
tribal knowledge.

It is designed to run at different scopes: a few repositories for one
developer, a product area for a team, or a larger source set for architecture
work. Private repository lists, organization names, tokens, generated graphs,
and company-specific conventions stay in local ignored config files.

Repo Graph is alpha software. The current runtime can inspect source configs,
sync Git sources, scan local repositories, export JSON, load Neo4j, and expose
a local HTTP API plus a navigable UI.

## What It Does

- Clones or updates configured Git repositories into a local cache.
- Scans local paths, explicit Git URLs, or GitHub organization source sets.
- Extracts repository, project, file, package, route, symbol, service, SQL,
  Kubernetes, Python, JavaScript/TypeScript, modern .NET, and legacy VB/.NET
  relationships.
- Emits deterministic entity and edge records with source, file, line, parser,
  and confidence metadata.
- Keeps unresolved references as first-class graph evidence instead of hiding
  them.
- Loads Neo4j for graph queries and exposes safe read endpoints for agents and
  local tools.
- Provides a local UI for search, impact analysis, unresolved triage, evidence
  snippets, and refresh jobs.

## Graph Model

Repo Graph treats application boundaries as the main language of the graph. A
UI that calls an API over HTTP, an API that calls another service, and a
service that reads a SQL object are dependency facts. The edge records the
interaction details that support that fact.

Parser and library details stay as evidence. For example, `fetch`, `axios`,
`requests`, `httpx`, and `HttpClient` should all produce semantic HTTP
dependency edges such as `CALLS_SERVICE` or `CALLS_HTTP`; the specific client,
raw URL, normalized route, config key, file path, and line number belong on the
edge as evidence.

## Example Questions

Repo Graph is useful for questions like:

- What depends on this route, stored procedure, package, or source file?
- Which repositories call this service or SQL object?
- What is the known blast radius of changing this entity?
- Which references did the graph fail to resolve, and why?
- Which missing repositories, parser gaps, or ambiguous targets should we fix
  before trusting a refactor plan?
- Which sources changed since the last graph build?

## Five-Minute Docker Quick Start

Start the local API, UI, and Neo4j with the synthetic example sources:

```bash
docker compose up --build
```

Open:

- Repo Graph UI: `http://localhost:8000/ui`
- Repo Graph API: `http://localhost:8000`
- Neo4j Browser: `http://localhost:7475`

Build and load the example graph:

```bash
curl -X POST http://localhost:8000/build-load \
  -H "content-type: application/json" \
  -d '{"strict":true}'
```

Check that the graph is loaded:

```bash
curl http://localhost:8000/scope
curl http://localhost:8000/stats
```

Then use the UI:

1. Open `http://localhost:8000/ui#search?type=api_route`.
2. Open an entity from the search results.
3. Click `Impact` to inspect known blast radius.
4. Review `Coverage Warnings` before trusting the result.
5. Open `Unresolved` to see missing-source, parser-gap, and ambiguous-target
   triage.

UI state is encoded in hash routes, so links can be refreshed or shared:

```text
/ui#search?q=orders&type=api_route
/ui#impact?entityId=<entity_id>&direction=in&depth=2
/ui#unresolved?source=api-service&type=CALLS_SQL
/ui#relationships?fromSource=api-service&type=CALLS_SQL&resolved=false
```

For generated Docker service, port, and environment details, see
[docs/generated/runtime-docker.md](docs/generated/runtime-docker.md).

## Local Pixi Quick Start

Install Pixi, then run the scanner against the built-in examples:

```bash
pixi run repo-graph inspect --config config/local-example.yaml
pixi run repo-graph build --config config/local-example.yaml --strict
pixi run repo-graph report unresolved --graph .repo-graph/output/graph.json
pixi run repo-graph report blast-radius --graph .repo-graph/output/graph.json --entity-id <entity_id>
```

For the generated CLI command reference, see
[docs/generated/cli-reference.md](docs/generated/cli-reference.md).

Run the local API without Docker:

```bash
pixi run serve
```

Run the full local verification suite:

```bash
pixi run audit
```

The example config scans only synthetic repositories under `examples/`. It
includes API, shared package, inventory, Python, modern .NET, legacy VB, and
database projects so package, HTTP, project reference, Kubernetes service,
service config, and SQL relationships can resolve locally. For generated
coverage from those examples, see
[docs/generated/parser-coverage.md](docs/generated/parser-coverage.md).
For scanner registration order, target patterns, and parser IDs, see
[docs/generated/scanner-catalog.md](docs/generated/scanner-catalog.md).
For the extension workflow, see
[docs/extension-author-guide.md](docs/extension-author-guide.md).

## Scanning Your Own Repositories

Create a local config outside this repository or use an ignored file such as
`config/private-my-sources.yaml`. Sources may be local paths, explicit Git
URLs, or a GitHub organization query that expands to matching repositories
through the GitHub REST API.

For field-level config details, see
[docs/generated/config-reference.md](docs/generated/config-reference.md).

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

Use `dependency_filter` when third-party package references would drown out
organization-owned dependencies:

```yaml
dependency_filter:
  package_include_patterns:
    - "^@example/"
    - "^example-"
    - "^Example\\."
  include_relative_imports: true
```

Typical private-source workflow:

```bash
pixi run repo-graph inspect --config ../my-repo-graph-sources.yaml
pixi run repo-graph sync --config ../my-repo-graph-sources.yaml
pixi run repo-graph snapshot status --config ../my-repo-graph-sources.yaml
pixi run repo-graph build --cached --config ../my-repo-graph-sources.yaml --sync --strict
pixi run repo-graph refresh --config ../my-repo-graph-sources.yaml --sync --strict
```

For private GitHub repositories in Docker, copy `.env.example` to `.env` and
set `GITHUB_TOKEN`. Docker Compose reads `.env` automatically. Repo Graph uses
the token for GitHub org discovery and HTTPS clone/fetch through temporary Git
environment config, without writing the token into source configs, generated
graphs, or cloned repository remotes.

To run Docker against a private config mounted from `./config`, set
`REPO_GRAPH_CONFIG` to the container path:

```bash
REPO_GRAPH_CONFIG=/app/config/private-my-sources.yaml
```

## Runtime API

The runtime exposes health, config, source status, sync, build, refresh, load,
job, scope, stats, graph query, unresolved report, and UI endpoints.

For the generated API endpoint reference, see
[docs/generated/api-endpoints.md](docs/generated/api-endpoints.md).

Useful setup endpoints:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/manifest
curl http://localhost:8000/config
curl http://localhost:8000/sources/configured
```

Build, load, and refresh:

```bash
curl -X POST http://localhost:8000/sync \
  -H "content-type: application/json" \
  -d '{}'

curl -X POST http://localhost:8000/build-load \
  -H "content-type: application/json" \
  -d '{"strict":true}'

curl -X POST http://localhost:8000/snapshot/status \
  -H "content-type: application/json" \
  -d '{}'

curl -X POST http://localhost:8000/refresh \
  -H "content-type: application/json" \
  -d '{"strict":true,"load":true}'
```

For larger source sets, submit long-running operations as local in-memory jobs:

```bash
curl -X POST http://localhost:8000/jobs/build-load \
  -H "content-type: application/json" \
  -d '{"strict":true}'

curl -X POST http://localhost:8000/jobs/refresh-changed \
  -H "content-type: application/json" \
  -d '{"strict":true}'

curl http://localhost:8000/jobs/<job_id>
```

Job history is local to the running API process. If the container restarts,
jobs disappear.

Read-only query endpoints for agents and local tools:

```bash
curl "http://localhost:8000/scope"
curl "http://localhost:8000/sources"
curl "http://localhost:8000/explore"
curl "http://localhost:8000/entities/search?type=api_route"
curl "http://localhost:8000/entities/<entity_id>/overview"
curl "http://localhost:8000/entities/<entity_id>/impact?direction=in&depth=2"
curl "http://localhost:8000/relationships/search?from_source=api-service&to_source=database"
curl "http://localhost:8000/sources/<source_name>/overview"
curl "http://localhost:8000/sources/<source_name>/files/snippet?path=src/app.py&line=42"
curl "http://localhost:8000/reports/unresolved"
```

See [docs/agent-usage.md](docs/agent-usage.md) for endpoint examples and agent
guidance. Raw Cypher is intentionally not exposed yet.

## Agent Integration

Generate a short Markdown snippet for another repository's private
`AGENTS.md`:

```bash
pixi run repo-graph agent-instructions \
  --api-url http://localhost:8000 \
  --config ../my-repo-graph-sources.yaml
```

The snippet points agents at `/manifest` as the runtime source of truth. It is
intended for private working repositories, not as a generated public artifact.

## Repository Layout

```text
AGENTS.md               Canonical agent and review standards
CONTRIBUTING.md         Contributor setup and pull request expectations
Dockerfile              Repo Graph API container image
SECURITY.md             Vulnerability reporting and sensitive data handling
config/                 Example source profiles
docker-compose.yaml     Local API plus Neo4j runtime
docs/spec.md            MVP planning spec
docs/architecture.md    Target architecture and layer boundaries
docs/spec-driven-development.md Spec-first workflow for meaningful changes
docs/modularity.md     File-shape and package-boundary rules
docs/extraction.md      Extraction layer contract and refactor path
docs/interaction-fact-builders.md Canonical interaction fact builder APIs
docs/sql-interaction-builders.md SQL-specific interaction builder contract
docs/database-metadata-builders.md Database metadata relationship builder contract
docs/schema.md          Current JSON graph shape
docs/agent-usage.md     Agent query API examples
docs/blast-radius-report.md Blast-radius report contract
docs/extension-author-guide.md One obvious extension path for contributors
docs/extending-parsers.md Parser extension workflow
docs/database-introspection.md Planned read-only database source design
docs/first-class-coverage.md First-class graph coverage audit
docs/generated/         Generated API, scanner, config, runtime, and vocabulary docs
docs/public-release.md  Public release checklist
examples/               Offline demo sources
scripts/                Local verification and docs generation scripts
src/repo_graph/         Tool implementation
tests/                  Unit tests
```

## Standards And Checks

`AGENTS.md` is the source of truth for coding standards and review rules.
`CLAUDE.md` and `.github/codex/pr_review_instructions.md` point back to it so
agents and reviewers apply the same rules.

Run the full local check before opening a PR:

```bash
pixi run audit
```

GitHub Actions runs `pixi run audit` on pushes and pull requests.

## Public And Private Boundary

This repository is meant to be public-safe. Keep private repository lists,
generated graph output, tokens, internal database names, and company-specific
examples outside this repository.

Generated graphs can reveal private architecture even when source code is not
included. Treat generated output, graph database volumes, and local source
configs as sensitive when scanning private repositories.

Ignored local files include `.env`, `.env.*`, `.repo-graph/`, `.pixi/`, and
`config/private*.yaml`.

Neo4j credentials are read from environment variables:

- `REPO_GRAPH_NEO4J_URI`
- `REPO_GRAPH_NEO4J_USER`
- `REPO_GRAPH_NEO4J_PASSWORD`
- `REPO_GRAPH_NEO4J_DATABASE`

Do not commit `.env` files with private credentials.

## License

Repo Graph is released under the MIT License.
