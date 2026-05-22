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

The package root exposes workflow functions and scanner contracts. Implementation
modules such as `_scanner_impl.py` are private migration modules and should not
be imported by API, CLI, storage, reports, config, or source resolver code.

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
  source-level scanning orchestration.
- `contracts.py`: public scanner protocol and scan result types.
- `registry.py`: deterministic default scanner registration.
- `legacy_graph_helpers.py`: temporary helpers for legacy scanners that still
  emit `Entity` and `Edge` objects.
- `project_discovery.py`: repository/project boundary discovery from manifests.
- scanner family packages: language, manifest, SQL, and database extraction
  details.

The current `_scanner_impl.py` is a private migration module. New parser work
should not add new public imports from it. Refactors should move one scanner
family at a time out of this module.

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

1. Move orchestration, registry, and legacy graph helpers out of the scanner
   implementation module.
2. Move project discovery into its own module once shared manifest parsing
   helpers are separated.
3. Move scanner families one at a time behind the registry.
4. Add typed extracted facts and adapt legacy graph output through the graph
   constructor.
5. Remove direct scanner emission of `Entity` and `Edge`.

Each slice should preserve generated graph output unless the spec explicitly
changes behavior.
