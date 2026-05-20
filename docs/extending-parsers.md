# Extending Parsers

RepoGraph parser work should follow one repeatable path. A parser slice is not
complete until code, examples, tests, and generated references all agree.

## Add A Parser Slice

1. Add or update a synthetic fixture under `examples/`.
   Use public-safe names such as `example`, `api-service`, and
   `database-project`.

2. Add the file type to `DEFAULT_FILE_EXTENSIONS` in
   `repo_graph.config` when RepoGraph does not already scan it.

3. Add project discovery only when the parser needs a new project boundary.
   Project discovery belongs near `project_info_for_manifest` in
   `repo_graph.scanner`.

4. Add a `FileExtractor` implementation in `repo_graph.scanner`.
   Each extractor should define a stable `name`, a narrow `can_process`
   predicate, and an `extract` method that returns a `ScanResult`.

5. Emit graph facts through `Entity`, `Edge`, `resolved_edge`, and
   `unresolved_edge`. Every emitted fact needs source provenance. File-derived
   facts should include `file_path`, `line_number` when available, parser name,
   and confidence.

6. Keep the graph vocabulary semantic. If a parser discovers an HTTP call,
   emit `CALLS_SERVICE` or `CALLS_HTTP` and record library-specific evidence
   such as `fetch`, `axios`, `requests`, `httpx`, or `HttpClient` in edge
   properties. Do not add one edge type or parser ID per client library.

7. Register the extractor in `default_extractors`.
   The registry order should stay deterministic.

8. Add focused tests in `tests/test_scanner.py`.
   Tests should cover at least one positive extraction and any important
   unresolved or ambiguous reference behavior.

9. Regenerate docs with `pixi run generate-docs`.
   Confirm `docs/generated/parser-coverage.md` includes the new parser when
   the examples exercise it.

10. Run `pixi run audit`.

## Parser Rules

- Prefer structured parsers when practical.
- Keep regex parsing bounded and covered by synthetic fixtures.
- Preserve unresolved edges when a target cannot be resolved safely.
- Do not require users to predefine relationships that RepoGraph can discover
  from source evidence.
- Optimize parser output for app-boundary dependencies. Parser names and
  library names are evidence; edge types should remain useful for impact
  analysis and agent summaries.
- Keep extractor failures local by returning `ScanResult.errors` instead of
  stopping the whole graph build.

## Expected Outputs

A parser slice should leave a reviewer able to answer:

- Which files does it scan?
- Which entity and edge types does it emit?
- Which examples exercise it?
- Which unresolved references are expected?
- Which generated docs changed?
