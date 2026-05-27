# Config Package Contract

The config package turns a source profile into validated model objects for the
rest of Repo Graph. It should keep one obvious path for adding source types,
scan rules, and defaults.

## Public Surface

Code outside the config package should import from `repo_graph.config`.

Stable public values include:

- `load_config`
- `load_raw_config`
- `RepoGraphConfig`
- `Source`
- `IncludeRules`
- `ExcludeRules`
- `DependencyFilter`
- default and enum constants used by generated config docs

## Package Shape

```text
repo_graph/config/
  __init__.py
  _database.py
  _defaults.py
  _github.py
  _loader.py
  _models.py
  _rules.py
  _sources.py
  _values.py
```

`_loader.py` owns YAML loading and top-level `RepoGraphConfig` assembly.

`_models.py` owns config dataclasses.

`_defaults.py` owns default paths, file extensions, excluded directories, and
supported enum sets.

`_sources.py` owns source list parsing and dispatch by source type.

`_github.py` owns GitHub organization source parsing.

`_database.py` owns database source parsing.

`_rules.py` owns include, exclude, and dependency filter parsing.

`_values.py` owns scalar value validation helpers.

## Extension Rules

Add a new source type by:

1. Adding parser logic in a focused source-type module.
2. Registering dispatch in `_sources.py`.
3. Adding fields to `Source` only when the value is needed outside config
   parsing.
4. Updating generated config docs when the public shape changes.
5. Adding focused config tests for valid and invalid examples.

Do not read environment variables, clone repositories, open database
connections, or scan files in the config package. Config parsing should only
validate and normalize declared configuration.
