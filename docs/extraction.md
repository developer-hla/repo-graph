# Extraction Architecture

Extraction turns resolved sources and optional read-only database metadata into
graph-ready scanner output. This layer is where most parser growth will happen,
so its public surface must stay small even when scanner internals become
detailed.

## Public Surface

Code outside `repo_graph.extraction` should import from the package root:

```python
from repo_graph.extraction import build_graph, build_cached_graph, snapshot_status
```

The package root exposes workflow functions and scanner contracts. API, CLI,
storage, reports, config, and source resolver code should not import scanner
family internals directly.

## Ownership

The extraction package owns:

- graph build orchestration
- source-level graph artifact builds
- source snapshots used by incremental builds
- scanner contracts
- scanner registry order
- scanner invocation and local scanner errors

The extraction package does not own:

- source checkout and GitHub expansion
- final graph identity and cross-source resolution
- storage writes or query behavior
- API response shape
- CLI argument parsing
- report grouping

## Module Boundaries

Target module responsibilities:

- `orchestrator.py`: build flow, database-source handoff, dependency filtering,
  source-level graph build orchestration.
- `contracts.py`: public file-scanner protocol and scan context types.
- `facts.py`: typed scanner fact contracts, evidence, entity references, and
  local scan issues.
- `fact_helpers.py`: small helper functions for common typed fact patterns,
  such as package declarations and package dependency relationships.
- `interaction_properties.py`: common structured evidence for application and
  database interaction relationships.
- `source_scanner.py`: source file walking, scanner invocation, local scanner
  error collection, and `SourceScanResult` creation.
- `registry.py`: deterministic default scanner registration.
- `project_discovery.py`: repository/project boundary discovery from manifests.
- `scanners/`: scanner family implementations. Current families include
  `manifests.py`, `python.py`, `javascript.py`, `sql.py`, `deployment.py`, and
  `code/dotnet`.
- `scanners/*_helpers.py`: domain-specific scanner helpers. Shared helpers
  should be split by domain instead of collected in one large module.

New parser work should add or update the relevant scanner family module, emit
typed facts, and register through `registry.py`. Do not add new scanner
behavior to orchestration, source walking, API, CLI, reports, storage, or graph
resolution modules.

## Scanner Registry

The registry owns scanner order. Scanner modules should expose scanner classes
or small factory functions; callers should ask the registry for default
scanners instead of constructing scanner families directly.

Registry order must stay deterministic because parser fingerprints, snapshot
status, and generated parser coverage depend on it.

## Scanner Output

Scanners return `FactBatch` with typed facts and local issues. Scanner modules
must not emit graph `Entity` or `Edge` records directly. The graph constructor
owns conversion from facts into graph records, stable IDs, resolution, summary
counts, and export shape.

Source discovery uses the same contract for repository, project, and file
scaffolding. `FileScanContext` carries `EntityFact` values, so scanner code can
reference the current repository, project, or file without importing the graph
model. Source scanning returns `SourceScanResult` with a `FactBatch` and
`files_scanned`; orchestration applies those facts to the graph constructor.
Database introspection returns `DatabaseScanResult` with the same `FactBatch`
shape. Database adapters may resolve relationships within their metadata
snapshot, but they still emit fact records instead of graph records.

Use `repo_graph.extraction.fact_helpers` for common fact patterns and
`repo_graph.extraction.interaction_properties` for structured interaction
evidence. Scanner helper modules may create `EntityFact`, `RelationshipFact`,
and `FactBatch` values when a shared helper does not fit.

## Refactor Path

1. Keep scanner-family modules behind the registry and keep domain helper
   modules small enough that ownership stays obvious.
2. Keep scanner output fact-only and make graph construction the only place
   that creates graph records.
3. Move shared scanner contracts and helpers into small modules when a scanner
   family becomes hard to follow.

Each slice should preserve generated graph output unless the spec explicitly
changes behavior.
