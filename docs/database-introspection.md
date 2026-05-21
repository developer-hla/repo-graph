# Database Introspection Design

RepoGraph should support optional read-only database introspection so agents can
compare code evidence with the current database shape. This is a planned source
type, not an enabled connector yet.

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

## Planned Source Contract

The config parser understands this source type so users and agents can validate
the planned contract. Build, sync, and refresh workflows still report database
sources as not implemented until a connector exists.

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

Fields:

| Field | Required | Notes |
| --- | --- | --- |
| `type` | yes | Must be `database`. |
| `name` | yes | Public-safe graph source name. |
| `engine` | yes | Start with `sqlserver`. Future engines must keep the same graph vocabulary where possible. |
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

The first adapter should inspect catalog metadata only. Useful starting points:

| Metadata | Candidate source |
| --- | --- |
| Tables | `sys.tables`, `sys.schemas`, `sys.columns` |
| Views | `sys.views`, `sys.sql_modules` |
| Stored procedures | `sys.procedures`, `sys.sql_modules` |
| Functions | `sys.objects`, `sys.sql_modules` |
| Foreign keys | `sys.foreign_keys`, `sys.foreign_key_columns` |
| Triggers | `sys.triggers`, `sys.sql_modules` |
| Module dependencies | `sys.sql_expression_dependencies` |

The connector should emit graph facts from metadata rows. It should not parse or
run user table data queries.

## Graph Facts

Introspected entities should use the existing SQL vocabulary where possible:

| Metadata object | Entity type |
| --- | --- |
| Table | `sql_table` |
| View | `sql_view` |
| Stored procedure | `stored_procedure` |
| Function | `sql_function` |
| Trigger | planned `sql_trigger` |

Every introspected SQL entity should include:

- `schema_state=current_database`
- `database_engine=sqlserver`
- `schema`
- `full_name`
- source provenance from the database source

Introspected relationships should reuse the same interaction vocabulary:

| Metadata relationship | Edge type |
| --- | --- |
| Foreign key dependency | `REFERENCES_SQL_OBJECT` |
| Module object dependency | `REFERENCES_SQL_OBJECT` unless the catalog can safely classify read/write/call behavior |
| Procedure/function execution dependency | `CALLS_SQL` when metadata proves an executable dependency |
| Trigger on table | planned `TRIGGERS_ON_SQL_OBJECT` |

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

After database sources exist, add a reconciliation report that groups drift:

| Group | Meaning |
| --- | --- |
| `code_only_reference` | Code references an object not found in current database metadata. |
| `migration_only_object` | Object is found only in historical SQL evidence. |
| `database_only_object` | Object exists in current database metadata but has no code/schema evidence in the scanned sources. |
| `schema_drift` | Source schema evidence conflicts with current database metadata. |
| `unresolved_database_reference` | Database metadata references a target outside the scanned/introspected scope. |

This should be exposed through an API report before adding UI-specific views.

## Implementation Order

1. Add a SQL Server metadata adapter behind an isolated module.
2. Add tests using synthetic metadata rows.
3. Emit `schema_state=current_database` entities and relationships.
4. Add reconciliation report APIs.
5. Add UI/report links after the API output is stable.
