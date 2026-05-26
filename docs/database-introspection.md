# Database Introspection Design

RepoGraph supports optional read-only database introspection through a database
source contract and engine adapter registry. SQL Server and PostgreSQL have
live metadata connectors plus pure metadata-row adapters.

## Why This Exists

SQL files in repositories are useful evidence, but they are not always the
current schema. Migration and revision files can describe tables, procedures,
or constraints that existed in the past and were later changed or removed.

Database introspection gives RepoGraph a second evidence source:

- code and SQL files show what repositories declare or reference
- migration files show historical database changes
- live metadata shows what exists in the selected database now

The goal is better blast-radius analysis and drift detection, not database data
access.

## Non-Goals

- Do not read table data.
- Do not execute application SQL.
- Do not mutate schema or data.
- Do not make production database access the default workflow.
- Do not commit connection strings, server names, database names, or private
  environment variable names.

## Source Contract

The config parser understands this source type so users and agents can validate
the contract. Build and refresh workflows read live database metadata when the
engine's optional driver and the configured connection environment variable are
available in the runtime. SQL Server uses `pyodbc` plus a SQL Server ODBC
driver. PostgreSQL uses `psycopg`. Engines without a live connector still
report a source error without blocking repository sources in the same config.

```yaml
sources:
  - type: database
    name: example-current-db
    engine: sqlserver
    connection_env: REPO_GRAPH_EXAMPLE_SQLSERVER_URL
    schemas:
      - dbo
    include_object_types:
      - table
      - view
      - stored_procedure
      - function
      - trigger
      - foreign_key
      - dependency
    query_timeout_seconds: 10
    max_metadata_rows: 50000
```

For PostgreSQL, the shape is the same:

```yaml
sources:
  - type: database
    name: example-current-pg
    engine: postgres
    connection_env: REPO_GRAPH_EXAMPLE_POSTGRES_URL
    schemas:
      - public
    include_object_types:
      - table
      - view
      - stored_procedure
      - function
      - foreign_key
      - dependency
```

Fields:

| Field | Required | Notes |
| --- | --- | --- |
| `type` | yes | Must be `database`. |
| `name` | yes | Public-safe graph source name. |
| `engine` | yes | Supported values include `sqlserver` and `postgres`; all engines must keep the same graph vocabulary where possible. |
| `connection_env` | yes | Environment variable containing the connection string. The value must not be written to graph output. |
| `schemas` | no | Optional allow-list. If omitted, use engine-safe defaults such as user schemas only. |
| `include_object_types` | no | Optional object-type allow-list. |
| `query_timeout_seconds` | no | Required implementation default should be conservative. |
| `max_metadata_rows` | no | Hard cap to prevent runaway metadata reads. |

## Safety Rules

- Database sources must be opt-in.
- Credentials must come from environment variables or ignored private config.
- The connector must use read-only metadata queries.
- The connector must not log connection strings.
- Timeouts and row limits must be enforced.
- Connection failures should become source errors, not crash unrelated source
  scans unless strict mode requires failure.
- Public tests must use fake metadata rows or a synthetic local test double,
  not a real database.

## SQL Server Metadata

The SQL Server connector consumes catalog-shaped metadata rows only. It uses
`pyodbc` when available, reads the connection string from `connection_env`, and
sets a query timeout. The package and ODBC driver are optional runtime
dependencies so public tests and normal repository scanning do not require a
database driver.

The connector reads these catalog sources:

| Metadata | Candidate source |
| --- | --- |
| Tables | `sys.objects`, `sys.schemas` |
| Views | `sys.objects`, `sys.schemas` |
| Stored procedures | `sys.objects`, `sys.schemas` |
| Functions | `sys.objects`, `sys.schemas` |
| Foreign keys | `sys.foreign_keys`, `sys.tables`, `sys.schemas` |
| Triggers | `sys.triggers`, `sys.trigger_events`, `sys.tables`, `sys.schemas` |
| Module dependencies | `sys.sql_expression_dependencies` |

It does not read table data or execute application SQL. It emits graph facts
from metadata rows and adds a source error if the connection fails, the driver
is missing, the connection environment variable is absent, or
`max_metadata_rows` is reached.

## PostgreSQL Metadata

The PostgreSQL connector consumes catalog-shaped metadata rows only. It uses
`psycopg` when available, reads the connection string from `connection_env`,
and sets `statement_timeout` for the session before reading metadata. The
package is an optional runtime dependency so public tests and normal repository
scanning do not require a database driver.

The connector reads these catalog sources:

| Metadata | Candidate source |
| --- | --- |
| Tables | `pg_class`, `pg_namespace` |
| Views and materialized views | `pg_class`, `pg_namespace` |
| Functions and procedures | `pg_proc`, `pg_namespace` |
| Foreign keys | `pg_constraint` |
| Triggers | `pg_trigger`, `pg_class`, `pg_namespace`, `pg_proc` |
| View and routine dependencies | `pg_depend`, `pg_rewrite` |

It does not read table data or execute application SQL. It emits graph facts
from metadata rows and adds a source error if the connection fails, the driver
is missing, the connection environment variable is absent, or
`max_metadata_rows` is reached. PostgreSQL-specific details such as
materialized view status are preserved in properties while agents and users
still see generic database entities and dependency edges.

## Database Facts

Introspected entities should use the existing SQL vocabulary where possible:

| Metadata object | Entity type |
| --- | --- |
| Table | `sql_table` |
| View | `sql_view` |
| Stored procedure | `stored_procedure` |
| Function | `sql_function` |
| Trigger | `sql_trigger` |

Every introspected SQL entity should include:

- `schema_state=current_database`
- `database_engine`, such as `sqlserver` or `postgres`
- `schema`
- `full_name`
- source provenance from the database source

The current adapters live in `repo_graph.database` and expose typed
metadata rows such as `SqlServerObjectRow`, `SqlServerForeignKeyRow`,
`SqlServerTriggerRow`, `SqlServerDependencyRow`, `PostgresObjectRow`,
`PostgresForeignKeyRow`, `PostgresTriggerRow`, and `PostgresDependencyRow`.
`scan_database_metadata()` dispatches through the engine registry, while
`scan_sqlserver_metadata()` and
`scan_postgres_metadata()` remain direct pure adapter entry points.
`scan_database_source()` is the live source entry point. These functions
return `DatabaseScanResult` with a `FactBatch` of `EntityFact` and
`RelationshipFact` records. Orchestration passes those facts through the graph
builder; database adapters do not create graph `Entity` or `Edge` records.

Introspected relationships should reuse the same interaction vocabulary:

| Metadata relationship | Edge type |
| --- | --- |
| Foreign key dependency | `REFERENCES_SQL_OBJECT` |
| Module object dependency | `REFERENCES_SQL_OBJECT` unless the catalog can safely classify read/write/call behavior |
| Procedure/function execution dependency | `CALLS_SQL` when metadata proves an executable dependency |
| Trigger on table | `TRIGGERS_ON_SQL_OBJECT` |

PostgreSQL trigger metadata also emits `CALLS_SQL` from the `sql_trigger` entity
to the trigger function when `pg_trigger.tgfoid` resolves to a function in the
introspected scope. SQL Server trigger body dependencies are read through
`sys.sql_expression_dependencies` when the catalog exposes them.

Do not infer `READS_SQL_OBJECT` or `WRITES_SQL_OBJECT` from metadata unless the
metadata source can distinguish reads from writes safely. If not, use
`REFERENCES_SQL_OBJECT` with evidence fields that describe the catalog source.

## Provenance

Use `schema_state` to explain how authoritative an object is:

| Value | Meaning |
| --- | --- |
| `current_database` | Found through live read-only database metadata. |
| `current_schema` | Found in a source file that appears to define current schema. |
| `historical` | Found in migration or revision history. |
| `unknown` | Found in SQL source that RepoGraph could not classify. |

Resolution should prefer non-historical evidence. Historical SQL objects should
remain visible but should not prove that a current application reference is
safe.

## Reconciliation Reports

The database reconciliation report groups drift between source evidence and
current database metadata:

| Group | Meaning |
| --- | --- |
| `code_only_reference` | Code references an object not found in current database metadata. |
| `migration_only_object` | Object is found only in historical SQL evidence. |
| `database_only_object` | Object exists in current database metadata but has no code/schema evidence in the scanned sources. |
| `schema_drift` | Source schema evidence conflicts with current database metadata. |
| `unresolved_database_reference` | Database metadata references a target outside the scanned/introspected scope. |

This is exposed through `GET /reports/database-reconciliation` and
`repo-graph report database-reconciliation`. It is a report over graph facts,
not a live database query.

## Implementation Order

1. SQL Server metadata adapter behind an isolated module. Done for synthetic
   rows.
2. Tests using synthetic metadata rows. Done.
3. Emit `schema_state=current_database` entities and relationships. Done.
4. Add reconciliation report APIs. Done.
5. Add UI/report links after the API output is stable. Done.
6. Add a shared adapter registry and PostgreSQL pure metadata adapter. Done.
7. Add SQL Server live metadata connector behind the database source contract.
   Done.
8. Add PostgreSQL live connector behind the same `database` source contract.
   Done.
9. Add first-class SQL trigger entities and trigger-on-table edges. Done.
