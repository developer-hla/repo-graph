# Repo Graph

Repo Graph builds a local graph of interactions across one or more code
repositories. It is designed to run at different scopes: a small service group,
a team domain, or every repository a developer can access.

The project is intentionally source-agnostic. Repository lists, organization
names, branch choices, and private conventions live in local config files, not
in the tool.

Repo Graph is alpha software. The current implementation can inspect source
configs, sync Git sources, scan local repositories, and export a portable JSON
graph. Graph database loading, the HTTP API, and Docker runtime are planned
next.

## Goals

- Clone or update repositories into a local cache.
- Parse code, package manifests, API routes, SQL, database objects, and
  configurable patterns.
- Emit an entity/edge graph with source provenance.
- Load the graph into a queryable store.
- Expose a local API that agents and developers can query.

## Quickstart

```bash
pixi run repo-graph inspect --config config/local-example.yaml
pixi run repo-graph build --config config/local-example.yaml
pixi run repo-graph build --config config/local-example.yaml --strict
```

The example config scans only synthetic repositories under `examples/`.

To scan your own repositories, create a local config outside this repository or
use an ignored local file. Keep real organization names, repository URLs, and
generated graphs out of public commits.

```bash
pixi run repo-graph inspect --config ../my-repo-graph-sources.yaml
pixi run repo-graph sync --config ../my-repo-graph-sources.yaml
pixi run repo-graph build --config ../my-repo-graph-sources.yaml --sync --strict
```

## Repository Layout

```text
AGENTS.md               Canonical agent and review standards
CONTRIBUTING.md         Contributor setup and pull request expectations
SECURITY.md             Vulnerability reporting and sensitive data handling
config/                 Example source profiles
docs/spec.md            MVP planning spec
docs/schema.md          Current JSON graph shape
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

## License

Repo Graph is released under the MIT License.
