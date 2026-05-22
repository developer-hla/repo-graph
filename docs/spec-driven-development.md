# Spec-Driven Development

RepoGraph should use written specs for meaningful architecture, parser, graph,
storage, API, and UI changes. Specs are not ceremony. They are how agents and
humans keep extension work regular, reviewable, and aligned with the public
tool boundary.

## When A Spec Is Required

Write or update a spec before implementation when a change:

- creates or changes a public contract
- adds a scanner, source type, graph fact, storage behavior, report, API route,
  or UI workflow
- changes module boundaries or import direction
- changes graph resolution, identity, schema, or incremental refresh behavior
- introduces a new extension pattern other contributors are expected to follow

Small bug fixes may not need a new spec, but they should still cite the
existing contract they preserve.

## Spec Shape

A spec should answer these questions in plain language:

- What problem does this solve?
- Who uses it?
- Which layer owns the behavior?
- Which layers are explicitly not responsible for it?
- What are the input and output contracts?
- What deterministic IDs, names, or keys are required?
- What evidence is preserved for agents and developers?
- What errors or unresolved states are expected?
- What examples prove the behavior without private data?
- What tests and generated docs must change?
- What migration path keeps existing behavior working?

## Separation Of Concerns Checklist

Before implementation, confirm:

- Config parses intent; it does not execute source sync, parsing, or graph
  resolution.
- Sources resolve repository/database inputs; they do not parse code.
- Scanners extract typed facts with evidence; they do not build, mutate, or
  persist graphs.
- The graph constructor turns facts into entities, edges, stable IDs,
  unresolved targets, and summaries.
- Storage persists an already-built graph; it does not parse source input.
- Reports read graph data; they do not create graph facts.
- API, UI, and CLI orchestrate workflows; they do not hide parser or
  resolution policy.

## Implementation Rules

- Implement the smallest slice that moves code toward the spec.
- Keep current behavior unless the spec explicitly changes it.
- Avoid broad rewrites that mix architecture cleanup with feature changes.
- Keep examples synthetic and public-safe.
- Add or update tests at the boundary being changed.
- Regenerate docs when generated references change.
- Run `pixi run audit` before committing.

## Review Rules

Reviewers should ask:

- Does the implementation follow the spec?
- Did the spec need to be updated based on what was learned?
- Are ownership boundaries clearer after the change?
- Did any layer gain a responsibility it should not own?
- Can a future agent find the expected extension path without reading the whole
  codebase?

If the answer is no, improve the spec or reduce the implementation scope before
adding more behavior.
