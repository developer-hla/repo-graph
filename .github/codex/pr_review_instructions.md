# Codex PR Review Instructions

## Foundation

Before reviewing any PR, read the repository root `AGENTS.md`. It contains the
coding standards, graph rules, architecture boundaries, and public-safety
requirements. Use it as the primary review framework.

This file defines review process and output format only.

## Scope

- Review only the changes introduced by the PR.
- Do not propose broad refactors outside the PR scope unless they fix a real
  issue caused by the PR.
- Do not invent private context. If something is unclear, ask a question.
- Treat public-safety leaks as blocking issues.

## What To Look For

### Correctness

- Incorrect graph entity or edge identity.
- False-positive edge resolution, especially ambiguous cross-source matches.
- Source metadata that can misrepresent repository URL, ref, commit, or path.
- Strict mode that fails to report scanner errors correctly.

### Architecture

- Config, source sync, scanner, graph, CLI/API/storage responsibilities mixed
  across layers.
- Parser logic added without tests.
- Storage or API code changing graph-resolution policy directly.

### Public Safety

- Private repo names, internal org names, internal database names, tokens,
  generated private graphs, or company-specific examples committed to the repo.
- Example configs that point to real private systems.

### Tests

- New parser behavior without synthetic fixtures.
- Git behavior tests that require network access.
- Tests that depend on private credentials or local machine paths.
- Missing regression tests for source sync, graph resolution, and strict mode.

### Dependencies

- Runtime dependencies added for behavior that the standard library can handle.
- `pixi.toml` changed without `pixi.lock`.
- Pre-commit or CI changes that weaken checks.

## Output Format

Write reviews in GitHub-flavored Markdown:

```markdown
## Summary
- One to three bullets.

## Must-fix
- `path:line` - Blocking correctness, safety, or contract issue.

## Suggestions
- `path:line` - Non-blocking improvement or question.

## Public-Safety Check
- State whether the PR preserves the public/private boundary.
```

Do not suggest generic commands as a substitute for findings. CI already runs
mechanical checks.
