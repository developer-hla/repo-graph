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
- temporary legacy conversion from scanner results into graph objects

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
- `contracts.py`: public scanner protocol and scan result types.
- `facts.py`: typed scanner fact contracts, evidence, entity references, and
  local scan issues.
- `fact_helpers.py`: small helper functions for common typed fact patterns,
  such as package declarations and package dependency relationships.
- `source_scanner.py`: source file walking, scanner invocation, and local
  scanner error collection.
- `registry.py`: deterministic default scanner registration.
- `legacy_graph_helpers.py`: temporary helpers for legacy scanners that still
  emit `Entity` and `Edge` objects.
- `project_discovery.py`: repository/project boundary discovery from manifests.
- `scanners/`: scanner family implementations. Current families are
  `manifests.py`, `python.py`, `dotnet.py`, `javascript.py`, `sql.py`, and
  `deployment.py`.
- `scanners/*_helpers.py`: domain-specific legacy scanner helpers while
  scanner families still emit graph objects directly. Shared helpers should be
  split by domain instead of collected in one large module.

New parser work should add or update the relevant scanner family module, emit
typed facts when practical, and register through `registry.py`. Do not add new
scanner behavior to orchestration, source walking, API, CLI, reports, storage,
or graph resolution modules.

## Scanner Registry

The registry owns scanner order. Scanner modules should expose scanner classes
or small factory functions; callers should ask the registry for default
scanners instead of constructing scanner families directly.

Registry order must stay deterministic because parser fingerprints, snapshot
status, and generated parser coverage depend on it.

## Legacy Graph Helpers

Until scanners emit typed facts, legacy scanners may use shared helpers to
create graph objects. This is temporary compatibility inside extraction only.

Allowed legacy helpers:

- `resolved_edge`
- `unresolved_edge`
- `interaction_properties`

New code should prefer typed facts when the fact model exists. Do not add new
graph-construction policy to scanner family modules.

## Refactor Path

1. Keep scanner-family modules behind the registry and keep domain helper
   modules small enough that ownership stays obvious.
2. Migrate scanner families from direct `Entity` and `Edge` emission to typed
   facts, one family at a time.
3. Remove direct scanner emission of `Entity` and `Edge`.

Each slice should preserve generated graph output unless the spec explicitly
changes behavior.
