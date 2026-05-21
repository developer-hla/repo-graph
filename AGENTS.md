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
- App-boundary semantics first: graph facts should describe meaningful
  relationships between applications, services, projects, data objects, and
  deployment resources. Parser names, HTTP client libraries, and syntax details
  are evidence, not the primary graph language.
- First-class coverage discipline: when a parser discovers a new kind of
  application, data, deployment, or integration boundary, evaluate it against
  `docs/first-class-coverage.md` before hiding it in generic properties or
  creating parser-specific vocabulary.

## Graph Rules

- Every entity and edge must include source provenance.
- Every file-derived entity or edge should include relative file path and line
  number when available.
- Edge types should describe semantic relationships such as runtime service
  calls, SQL usage, package dependencies, project references, deployment
  topology, declarations, and ownership. Do not create graph vocabulary around
  low-level implementation details such as a specific HTTP client library.
- When a parser can identify an endpoint handler, emit `HANDLES_ROUTE` from
  the `api_route` to the handler `function`. Runtime or database calls inside
  that function should use the function as the edge source and keep file and
  line evidence.
- When a parser can identify app-internal delegation between discovered
  functions or methods, emit `CALLS_SYMBOL` from caller to callee. Be
  conservative to avoid turning standard-library or third-party helper calls
  into false-positive blast-radius paths.
- Important integration boundaries should become first-class graph facts when
  they are stable, discoverable, and useful for impact analysis. Examples
  include SQL reads and writes, SQL schema dependencies, message publish/consume
  boundaries, storage reads and writes, cache usage, and scheduled/background
  work.
- SQL migration or revision files are historical evidence, not proof of current
  database state. Preserve schema provenance and do not use historical SQL
  objects as normal resolution candidates for current application dependencies.
- Interaction edges should preserve evidence on the edge, including protocol,
  method, route or target path, raw target, normalized target, config key,
  client library, parser, file path, and line number when those values are
  known.
- Edge types listed in `repo_graph.vocabulary.INTERACTION_EDGE_TYPES` must
  include `target_boundary`, `dependency_scope`, and `interaction_kind` in
  edge `properties`. Do not add those fields to structural, declaration, or
  ownership edges unless the edge is actually modeling an interaction.
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
- Prefer semantic parser IDs such as `javascript_http`, `python_http`, and
  `dotnet_http`. Store library-specific evidence such as `fetch`, `axios`,
  `requests`, `httpx`, or `HttpClient` in edge properties instead of creating
  one parser ID or edge type per library.
- Do not add language-specific parser behavior without synthetic tests.
- Follow `docs/extending-parsers.md` when adding or changing parser behavior.

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
