# Extending Parsers

RepoGraph parser work should follow one repeatable path. A parser slice is not
complete until code, examples, tests, and generated references all agree.

Parser work must also follow the architecture boundary in
[architecture.md](architecture.md): scanners extract typed facts with evidence;
graph construction converts those facts into graph entities, edges, IDs,
resolution, and export shape. Current code still has legacy direct
`Entity`/`Edge` emission in places, so refactors should move toward the
architecture spec rather than expanding that coupling.

## Add A Parser Slice

1. Write or update the relevant spec.
   For scanner contracts and boundaries, update [architecture.md](architecture.md)
   or a scanner-family spec. For broad workflow changes, follow
   [spec-driven-development.md](spec-driven-development.md).

2. Add or update a synthetic fixture under `examples/`.
   Use public-safe names such as `example`, `api-service`, and
   `database-project`.

3. Add the file type to `DEFAULT_FILE_EXTENSIONS` in
   `repo_graph.config` when RepoGraph does not already scan it.

4. Add project discovery only when the parser needs a new project boundary.
   Project discovery belongs to the extraction layer near project manifest
   discovery.

5. Add or register a scanner implementation.
   Each extractor should define a stable `name`, a narrow `can_process`
   predicate, and an extraction method that returns scanner output. Long-term,
   scanner output should be typed extracted facts, not graph objects.

6. Emit semantic facts with source provenance.
   While legacy code still emits `Entity` and `Edge` directly, use shared
   helpers consistently. File-derived facts should include `file_path`,
   `line_number` when available, parser name, and confidence. New refactors
   should prefer typed fact drafts that the graph constructor converts into
   graph objects.

7. Keep the graph vocabulary semantic. If a parser discovers an HTTP call,
   emit `CALLS_SERVICE` or `CALLS_HTTP` and record library-specific evidence
   such as `fetch`, `axios`, `requests`, `httpx`, or `HttpClient` in edge
   properties. Do not add one edge type or parser ID per client library.
   If a parser can identify that an API route is handled by a specific
   function, emit `HANDLES_ROUTE` from the route to that function. When HTTP
   or database calls are inside a known function, use that function as the
   source entity and keep the file path and line number as evidence.
   If a parser can identify one discovered function calling another discovered
   function or method, emit `CALLS_SYMBOL` from caller to callee. Keep this
   conservative; do not emit symbol-call edges for obvious standard-library or
   third-party calls unless the target can resolve to a scanned symbol.
   If the parser discovers a new boundary type, evaluate it against
   [first-class coverage](first-class-coverage.md) before deciding whether to
   add graph vocabulary or reuse an existing edge type.
   For interaction edge types listed in `repo_graph.vocabulary.INTERACTION_EDGE_TYPES`,
   use the scanner `interaction_properties` helper or an equivalent wrapper so
   `target_boundary`, `dependency_scope`, and `interaction_kind` are present.

8. Register the extractor in the scanner registry.
   The registry order should stay deterministic.

9. Add focused tests in `tests/test_extraction.py`.
   Tests should cover at least one positive extraction and any important
   unresolved or ambiguous reference behavior.

10. Regenerate docs with `pixi run generate-docs`.
   Confirm `docs/generated/parser-coverage.md` includes the new parser when
   the examples exercise it.

11. Run `pixi run audit`.

## Parser Rules

- Prefer structured parsers when practical.
- Keep regex parsing bounded and covered by synthetic fixtures.
- Preserve unresolved edges when a target cannot be resolved safely.
- Do not require users to predefine relationships that RepoGraph can discover
  from source evidence.
- Keep extraction separate from graph construction. Scanners should not own
  stable IDs, graph resolution, summary counts, dependency filtering, storage
  writes, or API/report shapes.
- Optimize parser output for app-boundary dependencies. Parser names and
  library names are evidence; edge types should remain useful for impact
  analysis and agent summaries.
- Promote important integration boundaries to first-class graph facts when
  they are stable, discoverable, and useful for blast-radius analysis. Use
  `docs/first-class-coverage.md` as the checklist.
- Use interaction evidence for app-to-app and app-to-database relationships:
  `CALLS_HTTP`, `CALLS_SERVICE`, `CONFIGURES_SERVICE`, `ROUTES_TO_SERVICE`,
  `CALLS_SQL`, `READS_SQL_OBJECT`, `WRITES_SQL_OBJECT`, and
  `REFERENCES_SQL_OBJECT`. Do not use interaction evidence for containment,
  declaration, or ownership edges such as `CONTAINS_FILE`, `DECLARES_SYMBOL`,
  or `DEFINES`.
- SQL parsers should preserve schema provenance. Migration or revision files are
  historical evidence, not proof of current database state. Prefer
  `schema_state=current_schema`, `historical`, `unknown`, or
  `current_database` when that distinction is known.
- Keep extractor failures local by returning `ScanResult.errors` instead of
  stopping the whole graph build.

## Expected Outputs

A parser slice should leave a reviewer able to answer:

- Which files does it scan?
- Which entity and edge types does it emit?
- Which examples exercise it?
- Which unresolved references are expected?
- Which generated docs changed?
