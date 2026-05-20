# RepoGraph JSON Schema Notes

The MVP export is a single JSON document. It is intentionally simple so it can
be loaded into different stores.

For generated type counts from the synthetic example graph, see
[generated/graph-types.md](generated/graph-types.md). For generated parser
coverage from the same examples, see
[generated/parser-coverage.md](generated/parser-coverage.md). For canonical
vocabulary values and policy metadata, see
[generated/vocabulary.md](generated/vocabulary.md). This document defines the
intended shape and meaning of the graph.

## Top-Level Fields

- `metadata`: tool name, schema version, scope name, and generation time.
- `sources`: resolved source list with local path, ref, URL, and commit when
  available.
- `summary`: file, entity, edge, resolution, and error counts.
- `entity_counts`: counts grouped by `entity_type`.
- `edge_counts`: counts grouped by `edge_type`.
- `entities`: graph nodes.
- `edges`: graph relationships.
- `errors`: scanner errors that did not stop the build.

## Entity

```json
{
  "entity_id": "stable-id",
  "entity_type": "repository | project | workspace | solution | build_config | config_file | config_value | file | package | service | deployment | container | ingress | api_route | function | class | module | interface | sql_table | sql_view | sql_function | stored_procedure",
  "name": "display name",
  "source_name": "source from config",
  "file_path": "relative/path when known",
  "line_number": 12,
  "aliases": ["optional alternate names"],
  "properties": {}
}
```

## Edge

```json
{
  "edge_id": "stable-id",
  "from_entity_id": "stable-id",
  "from_name": "source entity display name",
  "from_type": "file",
  "to_name": "target display name or unresolved reference",
  "to_type": "target type when known",
  "to_entity_id": "stable-id when resolved",
  "edge_type": "CONTAINS_PROJECT | CONTAINS_FILE | DECLARES_WORKSPACE | DECLARES_SOLUTION | DECLARES_BUILD_CONFIG | DECLARES_CONFIG_FILE | DECLARES_CONFIG | DECLARES_PACKAGE | DECLARES_SERVICE | DECLARES_DEPLOYMENT | DECLARES_INGRESS | DEPENDS_ON_PACKAGE | DEPENDS_ON_PROJECT | IMPORTS | DECLARES_ROUTE | EXPOSES_ROUTE | DECLARES_SYMBOL | RUNS_CONTAINER | SELECTS_DEPLOYMENT | ROUTES_TO_SERVICE | CALLS_HTTP | CALLS_SERVICE | CONFIGURES_SERVICE | DEFINES | CALLS_SQL | READS_SQL_OBJECT",
  "resolved": true,
  "source_name": "source from config",
  "file_path": "relative/path when known",
  "line_number": 12,
  "confidence": "high | medium | low",
  "parser": "stable parser id such as filesystem, package_json, or python_import",
  "properties": {}
}
```

## Core Entity Types

- `repository`: one configured source.
- `project`: a package, workspace project, Python project, .NET project, or
  solution-level project discovered inside a repository.
- `workspace`: a workspace manifest such as `pnpm-workspace.yaml`.
- `solution`: a .NET solution manifest.
- `build_config`: a shared build manifest such as `Directory.Build.props`.
- `config_file`: a configuration manifest such as `Web.config`,
  `App.config`, or `packages.config`.
- `config_value`: a config key discovered from app settings, connection
  strings, or WCF client endpoints. Sensitive values are not required for the
  public schema, but generated graphs should still be treated as sensitive.
- `file`: a scanned source file.
- `package`: a package manifest declaration, such as `package.json` `name`,
  Python project name, or .NET package ID.
- `service`, `deployment`, `container`, and `ingress`: Kubernetes runtime
  topology discovered from manifests.
- `api_route`: an HTTP route declared in source code.
- `function`, `class`, `module`, and `interface`: exported JavaScript,
  TypeScript, Python, C#, or legacy VB symbols.
- `sql_table`, `sql_view`, `sql_function`, `stored_procedure`: SQL objects
  declared in SQL files.

## Core Edge Types

- `CONTAINS_PROJECT`: repository to discovered project.
- `CONTAINS_FILE`: repository or project to file.
- `DECLARES_WORKSPACE`: file to workspace manifest.
- `DECLARES_SOLUTION`: file to solution manifest.
- `DECLARES_BUILD_CONFIG`: file to build config manifest.
- `DECLARES_CONFIG_FILE`: file to config manifest.
- `DECLARES_CONFIG`: config file to config value.
- `DECLARES_PACKAGE`: file or project to package.
- `DECLARES_SERVICE`: file to Kubernetes service.
- `DECLARES_DEPLOYMENT`: file to Kubernetes deployment.
- `DECLARES_INGRESS`: file to Kubernetes ingress.
- `DEPENDS_ON_PACKAGE`: package, project, build config, or manifest file to
  package target.
- `DEPENDS_ON_PROJECT`: project to project target, such as a .NET
  `ProjectReference`.
- `IMPORTS`: file to imported package or relative module target.
- `DECLARES_ROUTE`: file to route.
- `EXPOSES_ROUTE`: project to route.
- `DECLARES_SYMBOL`: file to exported function or class.
- `RUNS_CONTAINER`: Kubernetes deployment to container.
- `SELECTS_DEPLOYMENT`: Kubernetes service to deployment selected by labels.
- `ROUTES_TO_SERVICE`: Kubernetes ingress route to backend service.
- `CALLS_HTTP`: file to route target inferred from `fetch`, `axios`,
  `requests`, `httpx`, or .NET HTTP client calls.
- `CALLS_SERVICE`: file to a service-like target inferred from environment
  URL names, config keys, or legacy HTTP clients.
- `CONFIGURES_SERVICE`: config value to a service-like target inferred from
  URL settings or WCF endpoints.
- `DEFINES`: SQL file to SQL object declaration.
- `CALLS_SQL`: file to stored procedure target.
- `READS_SQL_OBJECT`: file to table, view, function, or procedure target.

Scanner-derived reference edges include evidence in `properties`, such as
`raw_target`, `normalized_target`, dependency type, ecosystem, package version,
HTTP method, target path, target environment variable, or SQL object name.

## Dependency Filtering

Configs may define `dependency_filter` to reduce third-party package noise in
final graph exports:

```yaml
dependency_filter:
  package_include_patterns:
    - "^@example/"
    - "^example-"
  package_exclude_patterns:
    - "-test$"
  include_relative_imports: true
```

The filter applies after global edge resolution. Resolved `DEPENDS_ON_PACKAGE`
and package `IMPORTS` edges are retained because they point to packages found
inside the scanned source set. Unresolved package references are retained only
when they match `package_include_patterns`, unless no include patterns are
configured. `package_exclude_patterns` removes matching package references.
Relative import edges are controlled by `include_relative_imports`.

## Unresolved Edges

An unresolved edge is a discovered reference that could not be mapped to an
entity in the current graph scope. This often means the target lives outside
the selected sources, the parser does not understand the declaration format
yet, or the reference is dynamic.

If a target matches multiple possible entities, the edge remains unresolved and
includes `properties.resolution_status = "ambiguous"` plus a bounded
`resolution_candidates` list. This avoids silently linking a reference to the
wrong repository or database object.

Service-like targets are resolved in priority order: explicit `service`
entities first, then `project`, then `repository`. This lets an environment URL
such as `INVENTORY_SERVICE_URL` resolve to a discovered project named or
aliased `inventory-service` without being treated as an ambiguous match with
its parent repository.

## Unresolved Report

The unresolved report groups unresolved edges by `edge_type`, `to_type`, target
name, and classification hint. It is available from graph JSON through the CLI
and from the loaded graph through the API.

```json
{
  "summary": {
    "unresolved_edge_count": 12,
    "group_count": 3,
    "returned_group_count": 3,
    "classification_edge_counts": {
      "likely_missing_source": 2,
      "likely_parser_gap": 1
    },
    "classification_group_counts": {
      "likely_missing_source": 2,
      "likely_parser_gap": 1
    }
  },
  "classification_groups": [
    {
      "classification": "likely_missing_source",
      "recommended_action": "Add or sync the repository, package, service, or database project that owns this target.",
      "count": 2,
      "group_count": 1,
      "source_names": ["api-service"],
      "edge_types": ["CALLS_SQL"]
    }
  ],
  "source_hotspots": [
    {
      "source_name": "api-service",
      "count": 4,
      "group_count": 2,
      "classifications": ["likely_missing_source"],
      "edge_types": ["CALLS_SQL"]
    }
  ],
  "target_hotspots": [
    {
      "to_type": "stored_procedure",
      "to_name": "dbo.load",
      "count": 4,
      "group_count": 1,
      "classifications": ["likely_missing_source"],
      "edge_types": ["CALLS_SQL"],
      "source_names": ["api-service"]
    }
  ],
  "items": [
    {
      "edge_type": "CALLS_SQL",
      "to_type": "stored_procedure",
      "to_name": "dbo.load",
      "classification": "likely_missing_source",
      "recommended_action": "Add or sync the repository, package, service, or database project that owns this target.",
      "count": 4,
      "source_names": ["api-service"],
      "parsers": ["sql_reference"],
      "examples": [
        {
          "source_name": "api-service",
          "file_path": "src/app.py",
          "line_number": 42
        }
      ]
    }
  ]
}
```

Classification values are triage hints:

- `likely_missing_source`: usually means the referenced package, service,
  project, or database object lives outside the current graph scope.
- `ambiguous_target`: multiple graph entities matched, so RepoGraph did not
  guess.
- `likely_parser_gap`: source scope may be correct, but extraction likely needs
  deeper parser support.
- `needs_review`: no heuristic matched.

## Neo4j Mapping

The Neo4j loader stores graph exports with a small public-safe model:

- `RepoGraphGraph`: one metadata node for the loaded graph.
- `RepoGraphSource`: one node per configured source recorded in the graph
  export.
- `RepoGraphEntity`: one node per exported entity.
- `RepoGraphTarget`: one node per unresolved target string.
- `(:RepoGraphGraph)-[:INCLUDES_SOURCE]->(:RepoGraphSource)` records the
  source set used by the loaded graph.
- Relationships use sanitized edge types such as `IMPORTS`, `CALLS_SQL`, and
  `READS_SQL_OBJECT`.

Each loaded node and relationship keeps the original graph fields as
properties. Nested `properties` maps are preserved as `properties_json` and
flattened into `property_*` fields where practical.

Resolved edges point from a `RepoGraphEntity` to another `RepoGraphEntity`.
Unresolved edges point from a `RepoGraphEntity` to a `RepoGraphTarget`.
