# Extension Author Guide

Repo Graph extensions should be easy for agents and developers to add without
learning the whole codebase. The rule is simple: choose the graph language
first, then add the smallest scanner, graph, report, API, or UI change that
supports that language.

Parser names, SDK names, framework names, and syntax details are evidence.
The graph should describe useful dependency facts such as "this route calls
this function", "this function reads this table", or "this service publishes to
this topic".

## Before You Code

Answer these questions first:

- What user question will this extension answer?
- Which graph entity or edge should represent the answer?
- Is the relationship already covered by the vocabulary in
  [generated/graph-types.md](generated/graph-types.md)?
- Does this need a new first-class fact? If yes, apply
  [first-class-coverage.md](first-class-coverage.md).
- Which layer owns the behavior?
- Which synthetic example can prove it without private data?

Meaningful extensions need a spec update before implementation. Use
[spec-driven-development.md](spec-driven-development.md) for the expected spec
shape.

## Choose The Owning Layer

| Extension | Owning Layer | Use This Path |
| --- | --- | --- |
| New config field or dependency filter | `repo_graph.config` | Parse and validate intent only. Do not sync sources or build graphs here. |
| New local, Git, GitHub, or database source behavior | `repo_graph.sources` or `repo_graph.database` | Resolve inputs and metadata. Emit or return source information for extraction. |
| New file parser or language support | `repo_graph.extraction.scanners` | Implement a scanner that returns `FactBatch` values. Register it in the default scanner registry. |
| New semantic entity or edge type | `repo_graph.vocabulary`, graph builder specs | Add vocabulary only when the relationship is stable, queryable, and useful for impact analysis. |
| New graph resolution or canonical resource behavior | `repo_graph.graph` | Convert existing facts into deterministic entities, edges, unresolved targets, or canonical resources. |
| New Neo4j load/query behavior | `repo_graph.storage` | Persist or query an already-built graph. Do not parse source input here. |
| New report | `repo_graph.reports` | Build read-only projections from graph data. |
| New API, CLI, or UI workflow | `repo_graph.api`, `repo_graph.cli`, `repo_graph.ui` | Orchestrate existing layer APIs. Do not hide parser or resolution logic in workflow code. |

## One Extension Path

1. Update the relevant spec.
   For parser work, start with [extraction.md](extraction.md) and
   [extending-parsers.md](extending-parsers.md). For architecture or workflow
   changes, update the owning spec first.

2. Add a synthetic example.
   Keep names public-safe, such as `api-service`, `shared-library`, or
   `database-project`.

3. Implement behind the owning package surface.
   Complex internals are fine, but other layers should import the package API,
   not private helper modules.

4. Emit typed facts.
   Scanners return `FactBatch` with `EntityFact`, `RelationshipFact`, and
   `ScanIssue` values. Scanners must not create graph `Entity` or `Edge`
   records.

5. Use semantic graph vocabulary.
   Prefer existing graph facts before adding new ones. Store library and syntax
   details in relationship properties.

6. Preserve evidence.
   Include source name, parser ID, file path, line number, confidence, raw
   target, normalized target, and context when known.

7. Keep unresolved references.
   If a target cannot be resolved safely, emit an unresolved relationship.
   Unresolved facts are useful graph output, not parser failures.

8. Add focused tests.
   Cover at least one positive case and any important unresolved or ambiguous
   behavior.

9. Regenerate generated docs.
   Run `pixi run generate-docs` when scanner coverage, vocabulary, config,
   runtime, API, or CLI references can change.

10. Run the full audit.
    Use `pixi run audit` before committing.

## Scanner Contract

File scanners implement the public `FileExtractor` protocol from
`repo_graph.extraction.contracts`:

- `name`
- `target_patterns`
- `parser_ids`
- `can_process(rel_path)`
- `extract(context, content) -> FactBatch`

Scanner families may have detailed internals under directories such as
`repo_graph.extraction.scanners.code.python`, but registration should stay in
`repo_graph.extraction.registry`.

Use these public extraction APIs before hand-building facts:

| Need | Preferred API |
| --- | --- |
| Entity declarations | `repo_graph.extraction.fact_helpers.entity_fact` |
| Resolved relationships | `resolved_relationship_fact` |
| Unresolved target relationships | `unresolved_relationship_fact` |
| Source evidence and local scanner issues | `source_evidence`, `scan_issue` |
| Interaction edge evidence | `repo_graph.extraction.interaction_properties.interaction_properties` |
| Messaging facts | `repo_graph.extraction.scanners.messaging_helpers` |
| Storage facts | `repo_graph.extraction.scanners.storage_helpers` |
| Cache facts | `repo_graph.extraction.scanners.cache_helpers` |
| Scheduled job facts | `repo_graph.extraction.scanners.scheduled_job_helpers` |
| Symbol facts and conservative internal calls | `repo_graph.extraction.scanners.symbol_helpers` |

## Graph Fact Rules

Use the most meaningful source entity that the parser can identify:

- If a route maps to a handler, emit `HANDLES_ROUTE` from `api_route` to
  `function`.
- If HTTP, messaging, storage, cache, or SQL work happens inside a function,
  use that function as the source and keep file/line evidence on the edge.
- If a discovered function calls another discovered function, emit
  `CALLS_SYMBOL` only when the target is clear.
- If a parser finds a boundary target but cannot resolve it, preserve an
  unresolved edge to the generic target type.

Interaction edges listed in
`repo_graph.vocabulary.INTERACTION_EDGE_TYPES` must include structured
interaction properties:

- `target_boundary`
- `dependency_scope`
- `interaction_kind`

Do not add those fields to containment, ownership, or declaration edges.

## External Resources

Some unresolved boundary targets represent shared external resources. For
example, message topics, queues, storage locations, and cache keys may be used
by multiple repositories before a concrete owner is known.

Scanners should emit unresolved relationships to generic target types such as
`message_topic`, `storage_location`, or `cache_key`. The graph constructor owns
canonical external resource nodes, stable IDs, dedupe, and cleanup during
refresh.

## Database Extensions

SQL file scanners and database scanners both emit graph facts, but they do not
have the same authority.

- Migration or revision files are historical evidence.
- Current schema files may describe the intended current source state.
- Read-only database introspection describes current database state.

Preserve `schema_state` evidence such as `historical`, `current_schema`,
`unknown`, or `current_database` when the extension can tell the difference.
Database scanners must be read-only, timeout-limited, and metadata-only.

## Done Checklist

A complete extension should leave these answers obvious:

- What layer owns it?
- What public API did it add or use?
- Which entity and edge types can it emit?
- Which evidence fields does it preserve?
- Which unresolved references are expected?
- Which examples prove it?
- Which tests cover it?
- Which generated docs changed?

If a reviewer needs to read the whole codebase to answer those questions, the
extension path is not regular enough yet.
