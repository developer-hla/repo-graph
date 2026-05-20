# Contributing

Repo Graph is a local-first tool for building interaction graphs from source
repositories. Contributions should keep the project generic, public-safe, and
easy to run without private infrastructure.

## Development Setup

Install Pixi, then run checks through the project tasks:

```bash
pixi run audit
```

Useful individual tasks:

```bash
pixi run check
pixi run lint
pixi run format-check
pixi run test
pixi run build-example-strict
pixi run docker-context-check
pixi run public-boundary-check
pixi run docker-smoke
```

Install pre-commit hooks after cloning:

```bash
pixi run setup
```

`pixi run docker-smoke` starts an isolated Docker Compose project, waits for
the local API to become healthy, serves the UI shell, builds and loads the
synthetic example graph into Neo4j, verifies `/stats` and `/scope`, and then
tears the project down. It uses alternate host ports by default so it does not
conflict with the normal quick start: API `18080`, Neo4j HTTP `17475`, and
Neo4j Bolt `17688`.

## Public-Safety Rules

- Do not commit private repository names, private URLs, internal database
  names, secrets, tokens, or generated private graphs.
- Use synthetic examples under `examples/` and `config/`.
- Keep real source lists in local config files outside this repository.
- Keep generated output under `.repo-graph/`.

Before opening a pull request, run `pixi run public-boundary-check` to scan
for risky public/private boundary terms. To add local company-specific terms
without committing them, put one term per line in an ignored file and run:

```bash
REPO_GRAPH_PUBLIC_BOUNDARY_TERMS=.repo-graph/public-boundary-terms.txt \
  pixi run public-boundary-check
```

## Code Standards

`AGENTS.md` is the canonical source for architecture, style, parser, graph, and
review rules. Follow it for both human-written and agent-written changes.

The short version:

- Keep side effects at the boundaries.
- Prefer small, composable functions for parser and transformation code.
- Keep graph identity deterministic.
- Preserve unresolved edges when a target cannot be resolved safely.
- Add synthetic tests for new parser behavior.

## Pull Requests

Each pull request should describe:

- Why the change is needed.
- What behavior changed.
- Which parts of the pipeline are affected.
- How the change was verified.
- Whether the public/private boundary was checked.
