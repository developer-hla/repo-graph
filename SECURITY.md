# Security

Repo Graph scans source code and can clone configured repositories into a local
cache. Treat source configs, generated graphs, and graph database snapshots as
sensitive when they reference private code.

## Supported Versions

Repo Graph is pre-1.0. Security fixes are handled on the latest mainline code
until stable releases exist.

## Reporting A Vulnerability

Use GitHub private vulnerability reporting if it is enabled for the repository.
If it is not enabled, open a minimal public issue asking for a secure contact
path. Do not include exploit details, private repository names, tokens, graph
exports, or other sensitive data in public issues.

## Handling Sensitive Data

- Keep private source lists outside this repository.
- Do not commit generated graphs from private repositories.
- Do not publish graph database volumes created from private code.
- Do not put credentials in Repo Graph config files.
- Keep local `.env` files uncommitted. Use `.env.example` only for empty
  placeholders.
- Prefer read-only credentials for Git providers when scanning private sources.
