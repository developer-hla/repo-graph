# Vocabulary Package Contract

The vocabulary package is the canonical source for graph entity names, edge
names, parser IDs, interaction evidence values, report policy, and coverage
warning rules.

## Public Surface

Code should import vocabulary values from `repo_graph.vocabulary` unless it is
working on the vocabulary package itself.

The package initializer re-exports the stable contract used by scanners,
reports, storage, API responses, generated docs, and tests.

## Package Shape

```text
repo_graph/vocabulary/
  __init__.py
  coverage.py
  edges.py
  entities.py
  impact.py
  interactions.py
  parsers.py
  unresolved.py
```

`entities.py` owns graph entity type names and entity-type groups.

`edges.py` owns graph edge type names and edge-type groups.

`interactions.py` owns structured interaction evidence values, such as target
boundary, dependency scope, and interaction kind.

`parsers.py` owns parser identifiers emitted in graph facts.

`impact.py` owns blast-radius traversal profile policy.

`unresolved.py` owns unresolved edge classification policy.

`coverage.py` owns coverage warning rule models and rule data.

## Extension Rules

Add vocabulary only when the value is semantic, stable, queryable, and useful
outside one parser implementation.

For new values:

1. Put the value in the owning module.
2. Re-export it from `repo_graph.vocabulary` only when other packages need it.
3. Update generated docs when public values change.
4. Add or update tests that prove generated graphs and reports use known
   vocabulary.

Do not put parser-specific syntax, client-library names, or one-off framework
details in graph vocabulary. Those belong in scanner evidence properties.
