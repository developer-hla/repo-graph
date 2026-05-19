# Public Release Checklist

Use this checklist before making Repo Graph public.

## Repository

- `LICENSE` is present.
- `README.md` describes the alpha status, quickstart, and privacy model.
- `CONTRIBUTING.md` explains setup, checks, and public-safety rules.
- `SECURITY.md` explains vulnerability reporting and sensitive data handling.
- `docs/agent-usage.md` explains the local agent query contract.
- CI runs on pull requests and pushes to `main`.
- Generated files are ignored and not committed.

## Privacy

- No private repository names.
- No internal organization names.
- No internal database names.
- No secrets or tokens.
- No generated private graphs.
- Examples use only synthetic repositories, schemas, and APIs.

Suggested local check:

```bash
rg -n "PRIVATE_TERM|ORG_NAME|INTERNAL_DB" . -g '!pixi.lock' -g '!.pixi/**' -g '!.repo-graph/**'
```

Replace the example terms with the private names relevant to your environment.

## Verification

Run:

```bash
pixi run audit
pixi run docker-smoke
```

When the directory is initialized as a git repository, also run:

```bash
pixi run pre-commit
```

## Not In Scope Yet

- PyPI publishing.
- Public hosted graph services.
- Built-in credentials management.
- A central shared graph for all users.
