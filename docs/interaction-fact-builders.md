# Interaction Fact Builders

Interaction facts power impact analysis. They describe dependencies across
application, deployment, messaging, storage, cache, and database boundaries.
The graph language should stay regular even when scanners use different
libraries or syntax to discover those relationships.

## Goal

Scanner authors should not hand-build interaction evidence dictionaries.
Instead, each interaction family has one owning builder API that creates the
edge type, target type, structured evidence, and unresolved target shape.

This keeps blast-radius paths consistent and gives agents one obvious place to
extend behavior.

## Required Evidence

Every edge type in `repo_graph.vocabulary.INTERACTION_EDGE_TYPES` must include:

- `target_boundary`
- `dependency_scope`
- `interaction_kind`

Builders should also preserve known evidence such as:

- `raw_target`
- `normalized_target`
- protocol or client library
- operation or method
- route, table, topic, storage object, cache key, config key, or service name
- source context when the scanner knows the enclosing function or object

## Builder Ownership

| Interaction Family | Edge Types | Owning Builder API |
| --- | --- | --- |
| HTTP and service calls | `CALLS_HTTP`, `CALLS_SERVICE` | `repo_graph.extraction.scanners.interactions.http` and `repo_graph.extraction.scanners.interactions.services` |
| Service configuration | `CONFIGURES_SERVICE` | `repo_graph.extraction.scanners.interactions.services.service_configuration_fact` |
| Deployment service routing | `ROUTES_TO_SERVICE` | `repo_graph.extraction.scanners.interactions.services.route_to_service_fact` |
| SQL calls and object references | `CALLS_SQL`, `READS_SQL_OBJECT`, `WRITES_SQL_OBJECT`, `REFERENCES_SQL_OBJECT` | `repo_graph.extraction.scanners.sql.facts`; see `docs/sql-interaction-builders.md` |
| Messaging | `PUBLISHES_MESSAGE`, `CONSUMES_MESSAGE` | `repo_graph.extraction.scanners.messaging.facts` |
| Storage | `READS_STORAGE_OBJECT`, `WRITES_STORAGE_OBJECT` | `repo_graph.extraction.scanners.storage.facts` |
| Cache | `READS_CACHE_KEY`, `WRITES_CACHE_KEY` | `repo_graph.extraction.scanners.cache.facts` |
| Database introspection | `CALLS_SQL`, `REFERENCES_SQL_OBJECT` | `repo_graph.database` adapter fact helpers |

The raw `repo_graph.extraction.interaction_properties.interaction_properties`
function is a low-level primitive. It should only be imported by these owning
builder modules.

## Scanner Rules

- Use the most specific builder that matches the relationship.
- Keep library names and syntax details as properties, not new edge types.
- Keep ambiguous targets unresolved.
- Keep scanner output fact-only. Do not create graph `Entity` or `Edge`
  records in scanner code.
- Add or update focused tests when adding a new interaction pattern.
- If no owning builder fits, update this spec before adding a new interaction
  helper.

## Guardrail

`pixi run architecture-boundary-check` blocks new direct imports of
`interaction_properties()` outside the owning builder modules. If the guardrail
fails, either use an existing builder or add a small builder in the owning
interaction family and document it here.
