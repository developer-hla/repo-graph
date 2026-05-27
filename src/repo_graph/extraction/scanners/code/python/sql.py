"""Python SQL interaction helpers."""

from __future__ import annotations

import ast

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.scanners.code.python.ast_values import python_attribute_name, python_string_arg
from repo_graph.extraction.scanners.sql.properties import source_context_properties
from repo_graph.extraction.scanners.sql.references import (
    sql_call_facts,
    sql_object_read_facts,
    sql_object_schema_reference_facts,
    sql_object_write_facts,
)


def python_sql_call_facts(
    context: FileScanContext,
    call: ast.Call,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    callee = python_attribute_name(call.func)
    if callee not in {"execute", "executemany", "exec_driver_sql", "text"}:
        return []
    raw_sql = python_string_arg(call, 0)
    if not raw_sql:
        return []
    extra_properties = source_context_properties(from_entity)
    return [
        *sql_call_facts(context, raw_sql, call.lineno, from_entity=from_entity, extra_properties=extra_properties),
        *sql_object_read_facts(
            context, raw_sql, call.lineno, from_entity=from_entity, extra_properties=extra_properties
        ),
        *sql_object_write_facts(
            context, raw_sql, call.lineno, from_entity=from_entity, extra_properties=extra_properties
        ),
        *sql_object_schema_reference_facts(
            context,
            raw_sql,
            call.lineno,
            from_entity=from_entity,
            extra_properties=extra_properties,
        ),
    ]
