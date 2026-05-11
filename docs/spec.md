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
Git repository, or a GitHub organization query.

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

  - type: local_path
    name: local-library
    path: ../local-library
```

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
- `POST /jobs/sync`
- `POST /jobs/build`
- `POST /jobs/build-load`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /load`
- `POST /query`
- `GET /stats`
- `GET /scope`
- `GET /sources`
- `GET /entities/search`
- `GET /entities/neighbors`
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
- `POST /load`

For large source sets, an in-memory local job API should support:

- `POST /jobs/sync`
- `POST /jobs/build`
- `POST /jobs/build-load`
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

- `GET /entities/search`
- `GET /entities/{entity_id}`
- `GET /entities/{entity_id}/neighbors`
- `GET /edges/unresolved`

Raw Cypher should stay unavailable until there is an explicit read-only mode
and clear result limits.

## CLI MVP

```bash
repo-graph sync --config path/to/sources.yaml
repo-graph build --config path/to/sources.yaml --output graph.json
repo-graph build --config path/to/sources.yaml --strict
repo-graph load --graph graph.json
repo-graph serve --config path/to/sources.yaml
repo-graph agent-instructions --api-url http://localhost:8000 --config path/to/sources.yaml
```

## Parser MVP

Start with parsers that are useful across many codebases:

- Git metadata
- package manifests
- TypeScript and JavaScript imports
- HTTP route declarations
- SQL tables, views, functions, and stored procedures
- SQL references from application code
- configurable regex patterns

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
3. JSON graph builder with repository and file entities.
4. Package, import, route, and SQL parsers.
5. Neo4j loader.
6. FastAPI query service.
7. Docker Compose runtime.
8. Agent manifest and usage docs.
