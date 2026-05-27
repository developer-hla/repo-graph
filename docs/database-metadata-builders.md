# Database Metadata Builders

Database metadata builders create interaction facts from read-only catalog
metadata. They are the database-introspection counterpart to the SQL scanner
builders in [sql-interaction-builders.md](sql-interaction-builders.md).

## Goal

Engine adapters should not hand-build database relationship dictionaries.
They should convert catalog rows into typed entities, resolve source and target
candidates, then call one semantic builder for the relationship being emitted.

This keeps SQL Server, PostgreSQL, and future engines on the same graph
language:

- foreign keys are schema references between tables
- executable dependencies are runtime SQL calls
- object dependencies are schema references unless metadata proves a stronger
  operation
- triggers are runtime trigger-on-table relationships

## Ownership

`repo_graph.database._metadata_edges` owns catalog-derived relationship facts.
It is private implementation code, but it is the single internal place where
database metadata edges assemble:

- `target_boundary`
- `dependency_scope`
- `interaction_kind`
- SQL protocol and operation properties
- `schema_state=current_database`
- database engine and metadata source
- unresolved and ambiguous target evidence

Engine adapters own engine-specific row conversion and source lookup. They
must not own edge vocabulary decisions or raw interaction property assembly.

## Builder APIs

Use these builders from database adapters:

| Builder | Relationship |
| --- | --- |
| `database_foreign_key_metadata_edge()` | table foreign key to referenced table |
| `database_dependency_metadata_edge()` | module, view, routine, trigger, or object dependency |
| `database_trigger_metadata_edge()` | trigger entity to table relationship |

`database_dependency_target_type()` normalizes executable dependencies whose
catalog target is only known as a generic SQL object. For example, an execute
dependency to `sql_object` becomes a `stored_procedure` target so the graph can
represent a runtime call.

The lower-level `database_metadata_edge()` and
`database_interaction_properties()` functions are local primitives for this
module only. New adapter code should use the semantic builders above.

## Evidence

Every metadata relationship must preserve:

- source database name
- engine parser ID
- database engine
- metadata source, such as `sys.foreign_keys` or `pg_depend`
- raw and normalized SQL target
- SQL operation
- current schema provenance
- relationship-specific names, such as constraint, trigger, or dependency name

Ambiguous targets must stay unresolved and include bounded candidate evidence.
Missing targets should also stay unresolved. Missing sources should become
database scan errors because the adapter cannot create a trustworthy edge
without a source entity.

## Non-Ownership

Database metadata builders do not:

- connect to databases
- read catalog rows
- create graph `Entity` or `Edge` records
- reconcile source SQL with live metadata
- infer reads or writes from metadata that cannot prove the operation

## Extension Workflow

When adding an engine or relationship type:

1. Add or update the metadata row model.
2. Convert engine-specific catalog rows in the adapter.
3. Reuse an existing semantic builder when the relationship fits.
4. Add a small builder here only when the relationship is first-class and
   cannot be represented by the existing builders.
5. Add synthetic tests for resolved, unresolved, and ambiguous targets when
   resolution behavior changes.

`pixi run architecture-boundary-check` blocks direct imports of the raw
database metadata edge/property helpers outside `_metadata_edges.py`.
