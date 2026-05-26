# RepoGraph Architecture

RepoGraph turns a selected set of repositories and optional read-only database
metadata into a queryable dependency graph. The system should be easy to extend
without making every contributor understand every parser, storage adapter, and
API endpoint.

This document defines the target architecture. Some current code predates this
shape and should be refactored toward it in small slices.

## Core Principle

Extraction and graph construction are separate concerns.

Scanners parse inputs and emit typed facts with evidence. They do not build the
graph, assign graph IDs, resolve references, dedupe graph nodes, or write to
storage.

The graph constructor consumes extracted facts and owns entity creation, edge
creation, stable IDs, resolution, summaries, schema versioning, and export
shape.

```text
config
  -> source resolver
  -> extraction orchestrator
  -> scanners
  -> extracted facts
  -> graph constructor
  -> graph model
  -> storage, reports, API, UI
```

## Layers

| Layer | Owns | Must Not Own |
| --- | --- | --- |
| Config | Public-safe source profiles, scan limits, dependency filters, runtime settings | Git operations, parsing source code, graph resolution |
| Source resolver | Local path validation, Git/GitHub sync, commit metadata | File parsing, database introspection, graph construction |
| Extraction orchestrator | Walking files, selecting scanners, invoking database scanners, collecting scanner outputs, source snapshots, source-level graph artifacts | Language semantics, graph ID assignment, storage writes |
| Scanners | Parsing one input domain and emitting typed facts with evidence | Stable graph IDs, cross-source resolution, graph mutation, storage writes |
| Fact model | Typed extraction outputs, references, evidence, confidence, provenance | Parser-specific syntax, storage schema, UI shape |
| Graph constructor | Entity/edge creation, stable IDs, dedupe, resolution, unresolved target handling, summaries | Source sync, parsing files, database queries, API responses |
| Storage | Persisting and querying an already-built graph | Parsing, graph construction policy, source sync |
| Reports | Read-only projections from graph data | Building or mutating graph state |
| API/UI/CLI | User workflows and orchestration | Parser internals, graph resolution policy |

## Package Boundaries And Public Surfaces

Directory and file structure are part of the architecture. A package should
make ownership obvious before a contributor reads implementation details.

Each layer may have complex internals, but it should expose a small, regular
public surface. For example, a Python scanner package can contain AST visitors,
normalizers, framework adapters, and test helpers, but code outside that package
should only need its public scanner contract or registration function.

This rule applies to every application layer, not just scanners:

- `config` exposes validated configuration types and loading helpers; parsing
  internals stay private.
- `sources` exposes source resolution and sync operations; provider-specific
  Git or GitHub details stay behind that boundary.
- `extraction` exposes the orchestrator, scanner contracts, fact model, and
  registry; scanner-family internals stay under their scanner package.
- `graph` exposes graph construction and the graph model; resolution, ID, and
  adapter internals stay behind that surface.
- `storage` exposes load/query operations; database-driver details stay private.
- `reports` exposes read-only report builders; formatting helpers stay private.
- `api`, `ui`, and `cli` expose user workflows; they should call layer APIs
  rather than reaching into private implementation modules.

Public module names should be stable, documented, and easy for agents to learn.
Private modules may be split as deeply as needed, but cross-layer imports
should target the documented package surface.

## Scanner Families

Scanners share one public contract but can use different implementation
strategies. Python can use AST, C# and VB can start with bounded regexes, SQL
can use SQL-specific parsing, and database scanners can read catalogs.

All scanner families emit extracted facts, not graph objects.

### Code Scanner

Examples: Python, C#, VB, JavaScript, TypeScript.

Input:

- source identity
- relative file path
- file text
- project context when known

Output:

- symbol declarations
- route declarations
- call references
- imports
- SQL snippets found in code
- evidence: parser ID, file path, line number, raw target, normalized target,
  syntax-specific details

Code scanners should be conservative with internal call facts. Emit a function
call fact only when the target can reasonably map to a discovered symbol.

### Manifest Scanner

Examples: `package.json`, `pyproject.toml`, `.csproj`, `.sln`,
`packages.config`, Kubernetes YAML, framework config.

Input:

- source identity
- relative manifest path
- manifest text or parsed document
- project context when known

Output:

- package declarations
- dependency references
- project references
- config declarations
- deployment and service declarations
- route-to-service facts from deployment manifests

Manifest scanners should preserve config key names and shape, but should not
require private secret values for useful graph facts.

### SQL File Scanner

Examples: schema files, procedure files, migration files.

Input:

- source identity
- relative SQL file path
- SQL text
- source provenance hints

Output:

- SQL object declarations
- SQL-to-SQL reads, writes, execution, schema references, trigger declarations
- schema provenance such as `current_schema`, `historical`, or `unknown`

SQL file scanners must preserve migration/history provenance. Historical SQL
facts are useful evidence, but they are not proof of current database state.

### Database Scanner

Examples: SQL Server metadata, PostgreSQL metadata.

Input:

- configured database source
- read-only connection settings supplied through ignored private environment
  variables
- schema/object filters and row limits

Output:

- current database object declarations
- current database-to-database dependencies
- trigger facts
- metadata source evidence

Database scanners must be read-only, timeout-limited, row-limited, and must not
read table data. They emit facts for current database state; they do not repair
or reconcile source code.

## Extracted Fact Contract

The target scanner output should be a small set of typed fact drafts. Exact
Python classes can evolve, but the contract should preserve these concepts:

```text
ExtractedFact
  fact_type: stable semantic type
  subject: declared entity ref or source-local ref
  object: declared entity ref, unresolved target ref, or value
  evidence: parser, source, path, line, raw target, normalized target
  confidence: high | medium | low
  properties: structured fact-specific evidence
```

The current public fact model lives in `repo_graph.extraction.facts`:

- `Evidence`
- `EntityReference`
- `EntityFact`
- `RelationshipFact`
- `ScanIssue`
- `FactBatch`

Those generic records are the migration surface. More specific domain fact
helpers can be added when they reduce parser complexity without hiding the
underlying evidence.

The graph constructor decides whether those facts become entities, edges,
unresolved targets, warnings, or report inputs. `FactBatch` contains typed
facts and local scanner issues; scanners and source discovery must not emit
graph records directly. Repository, project, and file scaffolding should use
the same fact path as language scanner output. Source scans should return facts
and counts; orchestration owns applying those facts to the graph model.

## Graph Constructor Contract

The graph constructor owns the stable graph language:

- entity and edge creation
- deterministic IDs
- aliases and lookup keys
- resolution and ambiguity policy
- unresolved target nodes
- dependency filtering
- graph schema version
- summary counts
- JSON export shape
- load-ready graph records for storage

Graph construction must remain deterministic for the same facts and config.
`repo_graph.graph.builder` adapts typed facts into the current graph model while
the external JSON schema stays stable.

## Import Direction Rules

Import direction should keep parser code isolated:

```text
config/sources -> extraction orchestrator -> scanners -> fact model
fact model -> graph constructor -> graph model -> storage/reports/API
```

Rules:

- Scanners may import scanner contracts, fact model types, vocabulary constants,
  and parser-local helpers.
- Scanners must not import storage, API, UI, report builders, or Neo4j code.
- Scanners and source discovery should not import `repo_graph.graph.Entity` or
  `repo_graph.graph.Edge`; they should emit fact drafts instead.
- The graph constructor may import the fact model and graph model.
- Storage adapters may import graph records, but not scanner modules.
- API and CLI may orchestrate build/load workflows, but should not contain
  parser or resolution logic.

## Package Layout Target

The codebase should move toward this shape:

```text
repo_graph/
  __init__.py
  config/
    __init__.py
    _loader.py
  sources/
    __init__.py
    _resolver.py
  extraction/
    __init__.py
    orchestrator.py
    contracts.py
    cached_builds.py
    fact_helpers.py
    facts.py
    interaction_properties.py
    project_discovery.py
    registry.py
    snapshots.py
    source_scanner.py
    source_graphs.py
    scanners/
      __init__.py
      common.py
      interaction_helpers.py
      manifest_helpers.py
      package_helpers.py
      sql_helpers.py
      symbol_helpers.py
      code/
        python/
          __init__.py
          scanner.py
          ast_parse.py
          symbols.py
        dotnet/
          __init__.py
          scanner.py
          csharp.py
          vb.py
        javascript/
          __init__.py
          scanner.py
      manifests/
        package_json.py
        pyproject.py
        dotnet_project.py
        kubernetes.py
      sql/
        files.py
      database/
        sqlserver.py
        postgres.py
  graph/
    __init__.py
    builder.py
    model.py
    resolution.py
    vocabulary.py
  storage/
    __init__.py
    _neo4j.py
  reports/
    __init__.py
    _builders.py
  api.py
  cli.py
```

This is a direction, not a requirement to move everything in one change.
Refactors should preserve behavior and keep public APIs stable.

Package `__init__.py` files should be intentional. They should re-export only
the small public contract for that package and should not become dumping grounds
for implementation details.

## Refactor Path

1. Specify contracts before moving code.
2. Add fact draft types and a graph-construction adapter while preserving the
   current JSON output.
3. Move shared scanner contracts and helpers out of the large scanner module.
4. Move one scanner family at a time behind the same registry.
5. Convert scanners from direct `Entity`/`Edge` emission to fact emission, one
   scanner family at a time.
6. Move graph construction, resolution, and filtering behind a dedicated graph
   builder.
7. Keep generated docs and synthetic examples updated after each slice.

## Done Criteria For Architecture Slices

Each architecture slice must:

- state which contract or boundary it changes
- keep behavior covered by synthetic tests
- avoid private examples or generated internal graphs
- preserve generated docs when the public surface changes
- run `pixi run audit`
