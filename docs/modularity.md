# Modularity And Maintainability

Repo Graph should be easy to extend without making contributors understand a
large unrelated file first. Directory structure, package boundaries, and file
shape are part of the public architecture.

This document defines how to keep modules small, regular, and owned by one
layer.

## Goals

- Make the owning layer obvious from the path.
- Keep public package APIs small and documented.
- Let internals be detailed without leaking across layers.
- Keep report, parser, storage, API, and UI changes easy to review in isolation.
- Give agents one obvious place to add a new capability.

## File Shape Rules

Line count is a signal, not the only rule. A file should be split when it mixes
multiple responsibilities, when a small change requires reading unrelated code,
or when tests need to exercise unrelated behavior to cover one feature.

Use these soft limits:

- Under 300 lines: usually fine when the file has one clear responsibility.
- 300-600 lines: acceptable for cohesive domain logic, but watch for helper
  drift.
- Over 600 lines: should have a clear reason or a split plan.
- Over 1,000 lines: treat as architecture debt unless it is generated code.

Generated docs and generated references are exempt. Runtime source files are
not exempt.

## Package Surface Rules

Each package should expose a small public API from `__init__.py`. Code outside
the package should import that public API unless it is extending an explicitly
documented subpackage.

Private modules should use a leading underscore only when they are true
package internals. A private module should not become a new dumping ground.

Package internals may be split by:

- domain concept, such as `blast_radius`, `unresolved`, or `interactions`
- engine, such as `sqlserver` or `postgres`
- workflow step, such as `requests`, `routes`, or `responses`
- adapter boundary, such as `records`, `payloads`, or `queries`

Avoid splitting by vague buckets such as `utils`, `misc`, or `helpers` unless
the helper module is small and package-local.

## Refactor Rules

Refactors should move one boundary at a time. Do not combine a module split
with behavior changes unless the behavior change is required to preserve the
contract.

For a modularity slice:

1. State the ownership problem.
2. Add or update this spec or the owning architecture spec.
3. Move code into cohesive modules.
4. Keep the package public API stable unless the spec says otherwise.
5. Run focused tests for the moved behavior.
6. Run `pixi run audit`.

## Current Split Plan

The largest runtime files should be addressed in this order:

1. Reports: split report builders by report type. Done.
2. Database metadata: split row models, engine registry, live connectors,
   catalog queries, and fact adapters.
3. Neo4j storage: split read operations, write operations, Cypher, payload
   mapping, and record preparation.
4. API runtime: split request models, runtime settings, workflow handlers,
   query/report response builders, and route registration.
5. UI runtime: split router, API client, views, components, and formatters.

Each split should preserve generated docs and public examples unless the
owning spec explicitly changes behavior.

## Reports Package Target

Report builders are read-only projections over graph data. They should not
parse source code, mutate graph state, query Neo4j directly, or know API route
registration details.

The reports package is organized by report type:

```text
repo_graph/reports/
  __init__.py
  _common.py
  blast_radius.py
  database_reconciliation.py
  interactions.py
  unresolved.py
```

`repo_graph.reports` remains the public import surface for CLI and API code.
The focused modules own report-specific grouping, filtering, examples,
hotspots, and summary calculations.
