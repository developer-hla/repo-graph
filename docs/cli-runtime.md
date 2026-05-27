# CLI Runtime Contract

The CLI is a thin command entrypoint. It should be easy to find one command,
change it, test it, and update generated command docs without reading unrelated
runtime behavior.

## Public Surface

The stable public surface is:

- `repo_graph.cli.main`
- `repo_graph.cli.build_parser`
- `repo_graph.cli.agent_instructions_markdown`

Generated CLI docs and tests may import `repo_graph.cli.build_parser`. Other
runtime code should not depend on command implementation modules unless it is
extending the CLI itself.

## Package Shape

```text
repo_graph/
  cli.py
  cli_runtime/
    __init__.py
    build.py
    common.py
    parser.py
    reports.py
    runtime.py
    sources.py
```

`cli.py` owns only process entrypoint behavior: build the parser, parse
arguments, and dispatch to the selected command.

`cli_runtime.parser` owns argparse command registration. It wires command names,
arguments, help text, and default handlers. It should not run scans, read Neo4j,
or build reports directly.

`cli_runtime.build` owns graph build, refresh, and load commands.

`cli_runtime.sources` owns source inspection, sync, snapshots, and source graph
artifact commands.

`cli_runtime.reports` owns commands that read graph JSON and print report
payloads.

`cli_runtime.runtime` owns local API runtime commands and generated agent
instructions.

`cli_runtime.common` owns small CLI-only helpers for JSON output, graph JSON
loading, output path resolution, and argparse value validation.

## Extension Rules

Add a new command by:

1. Putting the command handler in the module that owns the workflow.
2. Registering the command and arguments in `cli_runtime.parser`.
3. Keeping command output structured and scriptable.
4. Updating generated CLI docs when command shape changes.
5. Adding focused CLI tests for parsing, validation, and output payloads.

Do not add domain logic to the CLI layer. Command handlers should call the
owning package APIs and print the result.
