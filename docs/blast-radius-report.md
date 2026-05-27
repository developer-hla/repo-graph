# Blast-Radius Report

The blast-radius report explains which graph entities are connected to a
selected root through dependency or structural paths. It is the main local
workflow for refactor planning, legacy rebuilds, and impact analysis.

## Goal

Agents and developers should be able to ask:

- what depends on this entity
- what this entity depends on
- which sources are affected
- which edge types explain the paths
- what evidence supports each step

The report should return structured paths, not prose. Agents can then inspect
the result and decide how to explain or act on it.

## Ownership

`repo_graph.reports.blast_radius` owns blast-radius report construction.

It owns:

- request normalization for direction, depth, profile, edge type, and limit
- graph traversal around one root entity
- unresolved target payloads for outbound paths
- path, node, edge, source, and summary payload shaping
- impact profile filtering through `repo_graph.vocabulary.IMPACT_PROFILES`

It does not own:

- graph construction or entity/edge resolution
- Neo4j query execution
- API route registration
- UI rendering
- parser-specific evidence extraction

## Package Shape

The public package surface is intentionally small:

```python
from repo_graph.reports import blast_radius_report_from_graph
from repo_graph.reports import blast_radius_report_from_items
```

Internals are split by responsibility:

```text
repo_graph/reports/blast_radius/
  __init__.py      public report API
  _builder.py      report assembly
  _profiles.py     profiles, defaults, and request validation
  _traversal.py    graph traversal and edge filtering
  _payloads.py     node, edge, path, and unresolved target payloads
  _summaries.py    affected-source groups, path groups, and summary counts
```

New blast-radius behavior should be added to the owning internal module rather
than expanding `_builder.py` with unrelated helper logic.

## Inputs

`blast_radius_report_from_graph()` accepts exported graph JSON and a root
`entity_id`. It reads `metadata`, `entities`, and `edges`.

`blast_radius_report_from_items()` accepts an already-shaped root entity and
path items. API adapters can use it when Neo4j has already returned path-like
payloads.

Supported request fields:

| Field | Meaning |
| --- | --- |
| `direction` | `in`, `out`, or `both` |
| `depth` | traversal depth, currently 1 through 3 |
| `edge_type` | optional exact edge-type filter |
| `profile` | `impact`, `structural`, or `all` |
| `limit` | maximum returned path items |

## Output

The report returns:

- root entity metadata
- path items with `neighbor`, `edge`, and ordered `path.steps`
- affected source groups
- path groups by source and edge type
- summary counts for paths, sources, edge types, neighbor types, and max depth

Unresolved outbound targets are included as synthetic target payloads when the
edge has enough target evidence. This keeps missing-source blast radius visible
instead of dropping the edge.

## Rules

- Keep traversal deterministic for the same graph inputs.
- Keep ambiguous or unresolved evidence visible.
- Do not infer new dependencies in the report layer.
- Do not add parser-specific semantics here. Parser details belong on edge
  evidence and vocabulary profiles decide whether the edge participates.
- Preserve the public report output shape unless a spec update documents the
  contract change.

## Tests

Changes should keep or add synthetic coverage for:

- inbound and outbound traversal
- multi-step paths
- profile filtering
- path grouping and affected-source grouping
- unresolved outbound target payloads when behavior changes
