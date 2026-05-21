# First-Class Coverage Audit

RepoGraph should make important dependency boundaries easy for agents and
developers to query. Parser details belong in evidence fields, but stable
application, data, deployment, and integration relationships should be graph
facts.

## First-Class Criteria

A relationship is a good candidate for first-class graph vocabulary when it
meets most of these criteria:

- It crosses a meaningful application, data, deployment, or integration
  boundary.
- A change to the target can create blast radius in another source, service,
  database object, job, or endpoint.
- The relationship can be discovered from source, manifests, or config without
  requiring users to predefine the dependency.
- The target has a stable name that can be resolved or reported as unresolved.
- The same concept appears across multiple languages, frameworks, or legacy
  stacks.

Do not add first-class graph vocabulary for one library, one syntax form, or
one parser implementation. Those details belong in edge `properties` as
evidence.

## Current Coverage

| Area | Current first-class facts | Status |
| --- | --- | --- |
| Application HTTP calls | `CALLS_HTTP`, `CALLS_SERVICE` | Covered for common JavaScript, Python, .NET, and VB forms. |
| Service configuration | `CONFIGURES_SERVICE` | Covered for environment values, Web.config/App.config, and WCF-style endpoints. |
| Deployment routing | `DECLARES_SERVICE`, `DECLARES_DEPLOYMENT`, `DECLARES_INGRESS`, `ROUTES_TO_SERVICE`, `RUNS_CONTAINER`, `SELECTS_DEPLOYMENT` | Covered for Kubernetes manifests. |
| API routes | `DECLARES_ROUTE`, `EXPOSES_ROUTE` | Covered for common JavaScript, Python, .NET, and legacy VB route forms. |
| Packages and project structure | `DEPENDS_ON_PACKAGE`, `DEPENDS_ON_PROJECT`, `IMPORTS`, containment/declaration edges | Covered for supported package and project manifests. |
| Application-to-database calls | `CALLS_SQL` | Covered for application stored procedure calls in supported languages. |
| Database object reads | `READS_SQL_OBJECT` | Covered for SQL object reads from SQL definitions and application SQL snippets. |
| Database object writes | `WRITES_SQL_OBJECT` | Covered for inserts, updates, deletes, merges, truncates, and same-line `SELECT INTO` statements in SQL definitions and application SQL snippets. |
| SQL schema dependencies | `REFERENCES_SQL_OBJECT` | Covered for `REFERENCES` clauses with provenance that distinguishes current schema files from migration history. |
| SQL-to-SQL execution | `CALLS_SQL` from SQL objects | Covered for stored procedure execution discovered inside SQL definitions. |

## Gaps To Promote

These should be treated as first-class candidates before adding parser-specific
shortcuts.

| Priority | Area | Why it matters | Candidate vocabulary |
| --- | --- | --- | --- |
| High | Current database introspection | Revision and migration files can describe objects that no longer exist. Read-only introspection can provide the current database shape and reconcile code evidence against reality. | Source type: `database`; schema state: `current_database`; SQL Server metadata from `sys.*` catalogs. |
| High | Route/function/query context | A table or stored procedure impact path is more useful when it reaches a handler or endpoint, not only a file. | `HANDLES_ROUTE`, `CALLS_SYMBOL`, or narrower call-context edges after design review. |
| High | Messaging and event streams | Services often depend through queues, topics, and event contracts instead of HTTP. Refactors need publisher and consumer impact. | Entities: `message_topic`, `message_queue`, `message_contract`; edges: `PUBLISHES_MESSAGE`, `CONSUMES_MESSAGE`. |
| Medium | Deeper SQL schema dependencies | Schema-bound views, computed columns, constraints, and SQL module dependencies create blast radius beyond simple `REFERENCES` clauses. | Continue using `REFERENCES_SQL_OBJECT` with `sql_operation` evidence such as `SCHEMA_BOUND_VIEW` or catalog-derived dependency type. |
| Medium | File, blob, and transfer storage | Legacy and integration systems often couple through shared paths, buckets, FTP/SFTP drops, or blob containers. | Entities: `storage_location`; edges: `READS_STORAGE_OBJECT`, `WRITES_STORAGE_OBJECT`. |
| Medium | Cache and distributed state | Redis or similar caches can couple services through key names and invalidation behavior. | Entities: `cache_store`, `cache_key`; edges: `READS_CACHE_KEY`, `WRITES_CACHE_KEY`. |
| Medium | Scheduled and background work | Jobs create runtime entry points and dependencies that do not appear as HTTP routes. | Entities: `scheduled_job`, `worker`; edges: `DECLARES_JOB`, `RUNS_JOB`, `SCHEDULES_JOB`. |
| Medium | Database triggers | A table mutation can execute trigger logic that calls procedures or changes other tables. | Entity: `sql_trigger`; edges: `TRIGGERS_ON_SQL_OBJECT`, plus normal SQL call/read/write edges from the trigger. |
| Lower | Auth, identity, and policy boundaries | Auth changes can have wide blast radius, but many references are configuration-only and need careful false-positive control. | Prefer evidence-backed `USES_IDENTITY_PROVIDER` only when stable targets are available. |

## Recommended Slice Order

1. Add read-only database introspection as an optional source type.
   Start with SQL Server metadata for tables, views, procedures, functions,
   foreign keys, triggers, and module dependencies. Do not read table data.
2. Add reconciliation reports for code-vs-database drift.
   Flag objects found only in migration history, references missing from the
   current database, and current database objects with no code evidence.
3. Improve execution context.
   Attach SQL and service calls to functions or route handlers where parsers
   can do this safely, then expose route-to-query impact paths.
4. Add messaging boundaries.
   Keep Kafka, RabbitMQ, Azure Service Bus, SQS, and similar client libraries as
   evidence for generic publish/consume graph facts.
5. Add storage and transfer boundaries.
   Model shared storage as a dependency target, not as one edge type per SDK.
6. Add cache and scheduled-job slices when examples and stable naming rules are
   clear.

## Database State Provenance

SQL files are useful but not equally authoritative:

- `schema_state=current_schema`: source file appears to define the current
  schema, such as `schema.sql`.
- `schema_state=historical`: source file appears to be migration or revision
  history. Keep the evidence, but do not treat its objects as proof of current
  database state.
- `schema_state=unknown`: source file could not be classified.
- `schema_state=current_database`: future read-only database introspection found
  the object in a live database metadata catalog.

Database introspection should be opt-in, read-only, timeout-limited, and driven
by ignored private config. The public project should contain only the generic
adapter and synthetic examples; connection strings, server names, and database
names belong outside the repo. The planned source contract lives in
[database-introspection.md](database-introspection.md).

## Review Questions For New Parsers

Before adding or changing a parser, answer these questions:

- Does this discover a relationship that crosses an application, data,
  deployment, or integration boundary?
- Should the relationship become a graph edge type, or is it evidence for an
  existing edge type?
- What is the stable target name, and can unresolved targets be useful?
- Which source, file, line, parser, protocol, raw target, and normalized target
  evidence should be preserved?
- Which synthetic example proves this behavior without private data?
