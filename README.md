# Repo Graph

Repo Graph builds a local graph of interactions across one or more code
repositories. It is designed to run at different scopes: a small service group,
a team domain, or every repository a developer can access.

The project is intentionally source-agnostic. Repository lists, organization
names, branch choices, and private conventions live in local config files, not
in the tool.

Repo Graph is alpha software. The current implementation can inspect source
configs, sync Git sources, scan local repositories, export a portable JSON
graph, load Neo4j, and expose a local HTTP runtime with safe read endpoints.
The scanner discovers repository, project, file, package, route, exported
symbol, Python code and manifest, HTTP call, modern C#/.NET code and manifest,
legacy VB/.NET Framework config, Kubernetes topology, and SQL relationships
from local source files.

## Goals

- Clone or update repositories into a local cache.
- Parse code, package manifests, API routes, HTTP calls, Python project and
  code metadata, C#/.NET project and code metadata, legacy VB services, SQL,
  Kubernetes manifests, and database objects without requiring users to define
  relationships up front.
- Emit an entity/edge graph with source provenance.
- Load the graph into a queryable store.
- Expose a local API that agents and developers can query.

## Quickstart

```bash
pixi run repo-graph inspect --config config/local-example.yaml
pixi run repo-graph build --config config/local-example.yaml
pixi run repo-graph build --config config/local-example.yaml --strict
pixi run repo-graph build --cached --config config/local-example.yaml --strict
pixi run repo-graph refresh --config config/local-example.yaml
pixi run repo-graph snapshot status --config config/local-example.yaml
pixi run repo-graph source-graphs write --config config/local-example.yaml
pixi run repo-graph report unresolved --graph .repo-graph/output/graph.json
```

The example config scans only synthetic repositories under `examples/`. It
includes API, shared package, inventory, Python, modern .NET, legacy VB, and
database projects so package, HTTP, project reference, Kubernetes service,
service config, and SQL relationships can resolve locally.

To scan your own repositories, create a local config outside this repository or
use an ignored local file. Sources may be local paths, explicit Git URLs, or a
GitHub organization query that expands to matching repositories through the
GitHub REST API. Keep real organization names, repository URLs, and generated
graphs out of public commits.

Use `dependency_filter` when third-party package edges would drown out the
organization graph. Repo Graph still extracts all sources first and resolves
package references globally. Resolved package/import edges are kept even when
they do not match the patterns; unresolved package references are kept only
when they look organization-owned.

```yaml
dependency_filter:
  package_include_patterns:
    - "^@example/"
    - "^example-"
    - "^Example\\."
  include_relative_imports: true
```

```bash
pixi run repo-graph inspect --config ../my-repo-graph-sources.yaml
pixi run repo-graph sync --config ../my-repo-graph-sources.yaml
pixi run repo-graph snapshot status --config ../my-repo-graph-sources.yaml
pixi run repo-graph source-graphs write --config ../my-repo-graph-sources.yaml
pixi run repo-graph build --cached --config ../my-repo-graph-sources.yaml --sync --strict
pixi run repo-graph refresh --config ../my-repo-graph-sources.yaml --sync --strict
pixi run repo-graph build --config ../my-repo-graph-sources.yaml --sync --strict
```

## Local API Runtime

Run the API directly with Pixi:

```bash
pixi run serve
```

Then open the UI at `http://localhost:8000/ui` and check:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/manifest
curl http://localhost:8000/config
curl http://localhost:8000/sources/configured
```

The runtime exposes a navigable local UI plus health, manifest, config, source
status, change preview, sync, build, refresh, load, job, unresolved report, and
read-only graph endpoints. The manifest tells agents which API capabilities are
available and which graph capabilities are still planned.

Print a Markdown snippet for another repository's `AGENTS.md`:

```bash
pixi run repo-graph agent-instructions \
  --api-url http://localhost:8000 \
  --config ../my-repo-graph-sources.yaml
```

The snippet points agents at `/manifest` as the runtime source of truth. It is
intended for private working repositories, not as a generated public artifact.

## Docker Runtime

Start Repo Graph with Neo4j:

```bash
docker compose up --build
```

Services:

- Repo Graph API: `http://localhost:8000`
- Repo Graph UI: `http://localhost:8000/ui`
- Neo4j browser: `http://localhost:7475`
- Neo4j Bolt: `bolt://localhost:7688`

The default Compose file scans only the synthetic examples in this repository.
Mount your own config and source/cache locations when scanning private
repositories. Do not bake private source configs, tokens, generated graphs, or
database volumes into a public image.

For private GitHub repositories, copy `.env.example` to `.env` and set
`GITHUB_TOKEN`. Docker Compose reads `.env` automatically. Repo Graph uses the
token for GitHub org discovery and HTTPS clone/fetch through temporary Git
environment config, without writing the token into source configs, generated
graphs, or cloned repository remotes.

To run Docker against a private config mounted from `./config`, set
`REPO_GRAPH_CONFIG` to the container path:

```bash
REPO_GRAPH_CONFIG=/app/config/private-my-sources.yaml
```

Override the Neo4j host ports with `REPO_GRAPH_NEO4J_HTTP_PORT` and
`REPO_GRAPH_NEO4J_BOLT_PORT` if those ports are already in use.

Build and load the example graph into Neo4j:

```bash
curl http://localhost:8000/config
curl http://localhost:8000/sources/configured

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

curl http://localhost:8000/stats
```

For larger source sets, use the in-memory job API and poll until the job
finishes:

```bash
curl -X POST http://localhost:8000/jobs/sync \
  -H "content-type: application/json" \
  -d '{}'

curl -X POST http://localhost:8000/jobs/build-load \
  -H "content-type: application/json" \
  -d '{"strict":true}'

curl -X POST http://localhost:8000/jobs/snapshot-status \
  -H "content-type: application/json" \
  -d '{}'

curl -X POST http://localhost:8000/jobs/refresh \
  -H "content-type: application/json" \
  -d '{"strict":true,"load":true}'

curl -X POST http://localhost:8000/jobs/refresh-changed \
  -H "content-type: application/json" \
  -d '{"strict":true}'

curl http://localhost:8000/jobs/<job_id>
```

Job history is local to the running API process. If the container restarts,
jobs disappear.

Build without loading:

```bash
curl -X POST http://localhost:8000/build \
  -H "content-type: application/json" \
  -d '{"strict":true,"output_path":".repo-graph/output/graph.json"}'
```

Load an existing graph:

```bash
curl -X POST http://localhost:8000/load \
  -H "content-type: application/json" \
  -d '{}'
```

The API loads `.repo-graph/output/graph.json` by default based on the active
config file. Pass `graph_path` in the request body to load a different graph
inside the running container:

```bash
curl -X POST http://localhost:8000/load \
  -H "content-type: application/json" \
  -d '{"graph_path":"/app/.repo-graph/output/graph.json"}'
```

For local CLI loading against the Compose Neo4j service:

```bash
REPO_GRAPH_NEO4J_URI=bolt://localhost:7688 \
REPO_GRAPH_NEO4J_PASSWORD=repo-graph-password \
pixi run repo-graph load --graph .repo-graph/output/graph.json

REPO_GRAPH_NEO4J_URI=bolt://localhost:7688 \
REPO_GRAPH_NEO4J_PASSWORD=repo-graph-password \
pixi run repo-graph load --graph .repo-graph/output/graph.json \
  --replace-source api-service

REPO_GRAPH_NEO4J_URI=bolt://localhost:7688 \
REPO_GRAPH_NEO4J_PASSWORD=repo-graph-password \
pixi run repo-graph refresh --config config/local-example.yaml --load

REPO_GRAPH_NEO4J_URI=bolt://localhost:7688 \
REPO_GRAPH_NEO4J_PASSWORD=repo-graph-password \
pixi run repo-graph stats
```

Read-only query endpoints are available for agents and local tools:

```bash
curl "http://localhost:8000/scope"
curl "http://localhost:8000/sources"
curl "http://localhost:8000/sources/<source_name>/overview"
curl "http://localhost:8000/explore"
curl "http://localhost:8000/entities/search?type=api_route"
curl "http://localhost:8000/entities/<entity_id>/neighbors"
curl "http://localhost:8000/entities/<entity_id>/impact?direction=in&depth=2"
curl "http://localhost:8000/edges/unresolved"
curl "http://localhost:8000/reports/unresolved"
```

See [docs/agent-usage.md](docs/agent-usage.md) for endpoint examples and agent
guidance. Raw Cypher is intentionally not exposed yet.

## Repository Layout

```text
AGENTS.md               Canonical agent and review standards
CONTRIBUTING.md         Contributor setup and pull request expectations
Dockerfile              Repo Graph API container image
SECURITY.md             Vulnerability reporting and sensitive data handling
config/                 Example source profiles
docker-compose.yaml     Local API plus Neo4j runtime
docs/spec.md            MVP planning spec
docs/schema.md          Current JSON graph shape
docs/agent-usage.md     Agent query API examples
docs/public-release.md  Public release checklist
examples/               Offline demo sources
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

## Privacy Model

This repo should be safe to publish publicly. Keep private repository lists,
generated graph output, tokens, internal database names, and company-specific
examples outside this repository.

Generated graphs can reveal private architecture even when the source code is
not included. Treat generated output, graph database volumes, and local source
configs as sensitive when scanning private repositories.

Neo4j credentials are read from environment variables:

- `REPO_GRAPH_NEO4J_URI`
- `REPO_GRAPH_NEO4J_USER`
- `REPO_GRAPH_NEO4J_PASSWORD`
- `REPO_GRAPH_NEO4J_DATABASE`

Do not commit `.env` files with private credentials.

## License

Repo Graph is released under the MIT License.
