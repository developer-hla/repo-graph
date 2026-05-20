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

For company-specific private terms, create an ignored local file such as
`.repo-graph/public-boundary-terms.txt` with one term per line, then set
`REPO_GRAPH_PUBLIC_BOUNDARY_TERMS` when running the public-boundary check.

## Verification

Run:

```bash
pixi run audit
pixi run docker-smoke
```

`pixi run audit` includes the Docker context check, which verifies that local
env files, generated graphs, cloned source caches, and private source configs
are ignored before the Dockerfile's `COPY . .` step can include them in an
image.

`pixi run audit` also includes the public-boundary check. It scans public
files for private markers, common credential shapes, absolute local paths, and
unexpected token-handling strings.

`pixi run audit` also checks generated reference docs under `docs/generated/`
so endpoint, graph type, and task references do not drift from code.

When the directory is initialized as a git repository, also run:

```bash
pixi run pre-commit
```

For final release verification, run the manual `docker-smoke` workflow in
GitHub Actions. It validates the Docker quick start on a clean Ubuntu runner
without slowing every push or pull request.

## Not In Scope Yet

- PyPI publishing.
- Public hosted graph services.
- Built-in credentials management.
- A central shared graph for all users.
