# RepoGraph Agent Standards

This file is the single source of truth for coding standards, architecture
rules, and review expectations in RepoGraph. All AI agents, local audits, and
automated reviewers should read this file before making or reviewing changes.

## Project Boundary

RepoGraph is a public-safe, generic tool for building local interaction graphs
from source repositories. It must not assume any private company, internal
GitHub organization, database schema, repository name, or generated internal
graph.

Keep private usage in private config files outside this repository.

## Public-Safety Rules

- Do not commit private repository names, private URLs, internal database names,
  company-specific examples, tokens, secrets, or generated internal graphs.
- Examples must use synthetic names such as `example`, `api-service`, and
  `database-project`.
- Tests must use synthetic fixtures created in temporary directories or under
  `examples/`.
- Generated output belongs under `.repo-graph/` and must stay ignored.

## Architecture

RepoGraph is organized as a pipeline:

1. **Config** (`repo_graph.config`) parses source profiles and scan rules.
2. **Sources** (`repo_graph.sources`) resolves local paths and syncs Git repos
   into a local cache.
3. **Scanner** (`repo_graph.scanner`) reads source files and emits entities and
   edges.
4. **Graph** (`repo_graph.graph`) owns graph identity, resolution, summaries,
   and JSON export.
5. **CLI/API/storage** layers call the pipeline; they should not contain parser
   or graph-resolution logic.

Keep those boundaries intact. Do not put Git sync logic in scanners, parser
logic in the CLI, or graph-resolution policy in storage code.

## Architecture Principles

- Agent-first learnability: agents and developers should be able to learn the
  tool from examples, generated references, runtime manifests, and structured
  feedback without reverse-engineering internals.
- One obvious extension path: common changes such as adding a parser, source
  type, graph fact, report, or API surface should follow one documented
  workflow with expected tests and generated docs.
- Standard-library depth: shared graph vocabulary, parser helpers, runtime
  operations, diagnostics, and storage/query behavior should live in coherent
  project APIs rather than scattered literals or one-off scripts.
- Deterministic tooling: diagnostics, graph facts, refresh plans, coverage
  reports, and repair hints should be structured and stable enough for agents
  to inspect and act on.
- Direct developer experience: checking, running, formatting, inspecting, and
  repairing RepoGraph should be fast, copyable, and scriptable through Pixi
  tasks, CLI commands, and documented local workflows.
- Regularity over cleverness: prefer explicit, repeatable patterns over local
  shortcuts when the code defines public behavior, extension behavior, or agent
  contracts.

## Graph Rules

- Every entity and edge must include source provenance.
- Every file-derived entity or edge should include relative file path and line
  number when available.
- Ambiguous references must remain unresolved. Never silently link a reference
  to an arbitrary entity when more than one candidate matches.
- Unresolved edges are valid output. They mean the target was not found in the
  current graph scope or the parser could not resolve it safely.
- IDs must be deterministic for the same source inputs.
- Scanner errors should be collected and reported. Strict mode may fail the
  build when errors are present.

## Source Sync Rules

- Git cache paths must not allow two different URLs to share the same source
  directory.
- Existing cached Git repos must have an `origin` URL matching the configured
  source URL.
- `ref: default` means the remote default branch head.
- Local-path sources must not require Git metadata.

## Parser Rules

- Parsers must be deterministic and side-effect free.
- Parsers should tolerate partial failures and record errors rather than
  stopping the whole scan, unless strict mode is enabled.
- Prefer structured parsing when practical. Regex-based parsing is acceptable
  for MVP scanners, but keep patterns bounded and tested.
- Do not add language-specific parser behavior without synthetic tests.

## Code Style

- Prefer functional composition for transformation-heavy code. Use small pure
  functions and explicit data structures where practical. Isolate side effects
  at boundaries such as Git sync, filesystem reads/writes, CLI, API, and
  database storage.
- Use classes when they model durable state, resources, or domain objects. Do
  not force either functional or object-oriented style when the other is
  clearer for the job.
- Use Python 3.11 syntax: `list[str]`, `dict[str, str]`, `str | None`.
- Keep imports at the top of files.
- Prefer small functions with one responsibility.
- Use early returns to avoid deep nesting.
- Avoid broad `Any` unless parsing untyped external data.
- Avoid inline comments unless they explain non-obvious behavior.
- Use `pathlib.Path` for filesystem paths.
- Do not swallow exceptions silently.

## Dependency Management

- Dependencies are managed with Pixi in `pixi.toml`.
- If `pixi.toml` changes, update and include `pixi.lock`.
- Keep runtime dependencies minimal.
- Development-only tools belong in Pixi dependencies only if they are used by
  tasks, pre-commit hooks, or CI.

## Tests

- Default tests must not require network access or private credentials.
- Git behavior tests should use local temporary Git repositories.
- New parser behavior needs focused synthetic fixtures.
- Regression tests are required for graph resolution, source sync, and strict
  mode behavior.

## Commands

Use these before considering work complete:

```bash
pixi run audit
```

Individual checks:

```bash
pixi run check
pixi run lint
pixi run format-check
pixi run test
pixi run build-example-strict
```

## Review Checklist

Reviewers and audit agents should verify:

- Public-safety boundary is preserved.
- New behavior has synthetic tests.
- Graph resolution cannot create false-positive links.
- Source sync records accurate provenance.
- CLI behavior matches docs.
- Generated files remain ignored.
- `pixi.lock` is updated when dependencies change.
