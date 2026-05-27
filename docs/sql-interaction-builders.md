# SQL Interaction Builders

SQL edges are high-value blast-radius facts. They connect endpoint handlers,
application code, stored procedures, tables, views, and current database
metadata. They must stay regular across JavaScript, Python, .NET, SQL files,
and database introspection.

## Goal

Scanner code should not hand-build SQL interaction relationships. File and
code scanners should use the scanner-side SQL builders. Database adapters
should use the database metadata edge builders because they also own catalog
resolution, ambiguity evidence, and engine metadata.

## Scanner-Side Builders

Use `repo_graph.extraction.scanners.sql.facts` for relationships discovered
from source files:

| Builder | Edge Type | Target Type | Scope | Kind |
| --- | --- | --- | --- | --- |
| `sql_call_fact` | `CALLS_SQL` | `stored_procedure` | `runtime` | `sql_reference` |
| `sql_object_read_fact` | `READS_SQL_OBJECT` | `sql_object` | `runtime` | `sql_reference` |
| `sql_object_write_fact` | `WRITES_SQL_OBJECT` | `sql_object` | `runtime` | `sql_reference` |
| `sql_schema_reference_fact` | `REFERENCES_SQL_OBJECT` | `sql_object` | `schema` | `sql_schema_reference` |

These builders create unresolved facts. Graph construction owns cross-source
resolution to concrete SQL entities.

## Database Metadata Builders

Read-only database introspection uses `repo_graph.database` adapter helpers.
Those helpers may emit resolved or unresolved facts from current catalog
metadata and should preserve:

- database engine
- metadata source
- current database schema state
- resolution status and ambiguity candidates

Database adapters should not call scanner-side builders because scanner-side
builders describe source-file evidence, not catalog snapshots.

## Source Context

When a scanner knows the enclosing function, method, SQL object, or trigger,
pass that entity to the builder. The edge should start from the most specific
source context available:

```text
api_route -HANDLES_ROUTE-> function -CALLS_SQL-> stored_procedure -READS_SQL_OBJECT-> sql_table
```

If no enclosing context is known, the file entity remains the source.

## Evidence Rules

Every SQL interaction edge must include:

- `target_boundary=database`
- `protocol=sql`
- `dependency_scope`
- `interaction_kind`
- `raw_target`
- `normalized_target`
- `sql_operation`
- `database_object_type`

SQL file references should also preserve schema provenance such as
`schema_state`. Application snippets should preserve source context when known.

## Guardrail

`pixi run architecture-boundary-check` blocks direct imports of
`sql_interaction_properties` outside the owning SQL builder modules. If a
scanner needs a SQL interaction edge, add or use a builder in
`repo_graph.extraction.scanners.sql.facts`.
