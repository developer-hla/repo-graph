"""Python scanner helpers."""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import (
    entity_fact,
    entity_reference,
    resolved_relationship_fact,
    unresolved_relationship_fact,
)
from repo_graph.extraction.facts import EntityFact, FactBatch, RelationshipFact
from repo_graph.extraction.scanners.interaction_helpers import (
    HTTP_METHODS,
    http_facts_for_target,
    http_target,
    route_entity_fact,
    route_handler_fact,
    service_name_from_url,
)
from repo_graph.extraction.scanners.messaging_helpers import (
    MessageTarget,
    message_operation,
    message_relationship_fact,
    message_target,
)
from repo_graph.extraction.scanners.package_helpers import normalize_python_package_name
from repo_graph.extraction.scanners.sql.helpers import (
    source_context_properties,
    sql_call_facts,
    sql_object_read_facts,
    sql_object_schema_reference_facts,
    sql_object_write_facts,
)
from repo_graph.extraction.scanners.storage_helpers import (
    StorageOperation,
    StorageTarget,
    storage_operation,
    storage_relationship_fact,
    storage_target,
    storage_target_from_parts,
)
from repo_graph.extraction.scanners.symbol_helpers import SymbolCallTarget, symbol_call_facts


@dataclass(frozen=True)
class PythonCallableIndex:
    functions: frozenset[str]
    class_methods: dict[str, frozenset[str]]

    def has_function(self, name: str) -> bool:
        return name in self.functions

    def has_method(self, class_name: str, method_name: str) -> bool:
        return method_name in self.class_methods.get(class_name, frozenset())


def python_import_fact(context: FileScanContext, raw_target: str, level: int, line_number: int) -> RelationshipFact:
    is_relative = level > 0 or raw_target.startswith(".")
    target_name = raw_target if is_relative else normalize_python_package_name(raw_target.split(".", 1)[0])
    return unresolved_relationship_fact(
        entity_reference(context.file_entity),
        target_name,
        "IMPORTS",
        context,
        "python_import",
        to_type="module" if is_relative else "package",
        line_number=line_number,
        properties={
            "raw_target": raw_target,
            "normalized_target": target_name,
            "import_kind": "relative" if is_relative else "package",
        },
    )


def python_symbol_facts(
    context: FileScanContext,
    symbol_kind: str,
    name: str,
    line_number: int,
    class_stack: Sequence[str],
) -> FactBatch:
    facts = FactBatch()
    module_name = python_module_name(context.rel_path)
    parent_name = ".".join(class_stack) or None
    full_name = ".".join(part for part in (module_name, parent_name, name) if part)
    entity_type = "function" if symbol_kind in {"function", "async_function"} else symbol_kind
    aliases = {name, full_name or name}
    if parent_name:
        aliases.add(f"{parent_name}.{name}")
    symbol = entity_fact(
        context,
        entity_type=entity_type,
        name=full_name or name,
        line_number=line_number,
        aliases=aliases,
        properties={
            "symbol_kind": symbol_kind,
            "module": module_name or None,
            "parent": parent_name,
            "project": context.project.name if context.project else None,
        },
    )
    facts.entities.append(symbol)
    facts.relationships.append(
        resolved_relationship_fact(
            entity_reference(context.file_entity),
            symbol.reference,
            "DECLARES_SYMBOL",
            context,
            "python_symbol",
            line_number,
        )
    )
    return facts


def python_module_name(rel_path: str) -> str:
    path = Path(rel_path).with_suffix("")
    parts = list(path.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def python_route_facts(
    context: FileScanContext,
    operation_name: str,
    decorators: Sequence[ast.expr],
    line_number: int,
    handler: EntityFact | None = None,
) -> FactBatch:
    facts = FactBatch()
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        path = python_string_arg(decorator, 0) or python_keyword_string(decorator, "path")
        if not path:
            continue
        for method in python_route_methods(decorator):
            facts.extend(python_add_route_facts(context, method, path, line_number, operation_name, handler))
    return facts


def python_route_methods(decorator: ast.Call) -> list[str]:
    callee = python_attribute_name(decorator.func)
    if callee in HTTP_METHODS:
        return [callee.upper()]
    if callee not in {"route", "api_route"}:
        return []
    methods = python_keyword_strings(decorator, "methods")
    return [method.upper() for method in methods] if methods else ["GET"]


def python_add_route_facts(
    context: FileScanContext,
    method: str,
    path: str,
    line_number: int,
    operation_name: str,
    handler: EntityFact | None = None,
) -> FactBatch:
    facts = FactBatch()
    route = route_entity_fact(context, method, path, line_number, "python_route", operation_name)
    facts.entities.append(route)
    facts.relationships.append(
        resolved_relationship_fact(
            entity_reference(context.file_entity),
            route.reference,
            "DECLARES_ROUTE",
            context,
            "python_route",
            line_number,
        )
    )
    if context.project:
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.project.entity),
                route.reference,
                "EXPOSES_ROUTE",
                context,
                "python_route",
                line_number,
            )
        )
    if handler:
        facts.relationships.append(route_handler_fact(context, route, handler, "python_route", line_number))
    return facts


def python_http_call_facts(
    context: FileScanContext,
    call: ast.Call,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    callee = python_attribute_name(call.func)
    root_name = python_call_root_name(call.func)
    if root_name not in {"httpx", "requests"}:
        return []
    if callee in HTTP_METHODS:
        raw_target = python_string_arg(call, 0) or python_keyword_string(call, "url")
        return python_http_facts_for_target(context, callee.upper(), raw_target, call.lineno, root_name, from_entity)
    if callee == "request":
        method = python_string_arg(call, 0) or python_keyword_string(call, "method") or "GET"
        raw_target = python_string_arg(call, 1) or python_keyword_string(call, "url")
        return python_http_facts_for_target(context, method.upper(), raw_target, call.lineno, root_name, from_entity)
    return []


def python_http_facts_for_target(
    context: FileScanContext,
    method: str,
    raw_target: str | None,
    line_number: int,
    client: str,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    if not raw_target:
        return []
    source_ref = entity_reference(from_entity or context.file_entity)
    extra_properties = source_context_properties(from_entity)
    parsed = urlparse(raw_target)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        target = http_target(raw_target, method)
        target["service_name"] = service_name_from_url(raw_target)
        target["client"] = client
        target.update(extra_properties)
        return [
            unresolved_relationship_fact(
                source_ref,
                target["service_name"],
                "CALLS_SERVICE",
                context,
                "python_http",
                to_type="service",
                line_number=line_number,
                properties=target,
            )
        ]
    return http_facts_for_target(
        context,
        method,
        raw_target,
        line_number,
        "python_http",
        client=client,
        from_entity=from_entity,
        extra_properties=extra_properties,
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


def python_message_facts(
    context: FileScanContext,
    call: ast.Call,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    callee = python_attribute_name(call.func)
    operation = message_operation(
        callee,
        receiver=python_call_root_name(call.func) or python_call_receiver_name(call.func),
    )
    if not operation:
        return []
    return [
        message_relationship_fact(context, operation, target, call.lineno, "python_message", from_entity)
        for target in python_message_targets(call, operation.method)
    ]


def python_message_targets(call: ast.Call, method: str) -> list[MessageTarget]:
    targets: list[MessageTarget] = []
    for key in ("topic", "topics", "queue", "queue_name", "QueueName", "QueueUrl", "routing_key"):
        values = python_keyword_strings(call, key)
        targets.extend(message_target(value, python_message_destination_kind(key), key) for value in values)
    if not targets:
        targets.extend(
            message_target(value, python_message_destination_kind_for_method(method), "first_arg")
            for value in python_string_values_from_arg(call, 0)
        )
    return targets


def python_message_destination_kind(key: str) -> str:
    normalized = key.lower()
    if "queue" in normalized or "routing" in normalized:
        return "queue"
    return "topic"


def python_message_destination_kind_for_method(method: str) -> str:
    if method in {"basic_consume", "receive_message", "send_message"}:
        return "queue"
    return "topic"


def python_storage_facts(
    context: FileScanContext,
    call: ast.Call,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    operation = python_storage_operation(call)
    if not operation:
        return []
    target = python_storage_target(call)
    if not target:
        return []
    return [storage_relationship_fact(context, operation, target, call.lineno, "python_storage", from_entity)]


def python_storage_operation(call: ast.Call) -> StorageOperation | None:
    callee = python_attribute_name(call.func)
    if callee == "open":
        return StorageOperation(python_open_mode_action(call), "open")
    return storage_operation(callee, receiver=python_call_root_name(call.func) or python_call_receiver_name(call.func))


def python_open_mode_action(call: ast.Call) -> str:
    mode = python_string_arg(call, 1) or python_keyword_string(call, "mode") or "r"
    if any(token in mode for token in ("w", "a", "x", "+")):
        return "write"
    return "read"


def python_storage_target(call: ast.Call) -> StorageTarget | None:
    values: dict[str, str] = {}
    for key in ("Bucket", "bucket", "bucket_name", "Container", "container", "Key", "key", "path", "file_path"):
        value = python_keyword_string(call, key)
        if value:
            values[key.lower()] = value
    if values:
        return storage_target_from_parts(values)
    raw_target = python_string_arg(call, 0)
    if raw_target:
        return storage_target(raw_target, "path", target_key="first_arg")
    return None


def python_symbol_call_facts(
    context: FileScanContext,
    call: ast.Call,
    from_entity: EntityFact,
    class_stack: Sequence[str],
    callable_index: PythonCallableIndex,
) -> list[RelationshipFact]:
    target = python_symbol_call_target(call.func, class_stack, callable_index)
    if not target:
        return []
    return symbol_call_facts(context, from_entity, [target], "python_call", call.lineno)


def python_symbol_call_target(
    func: ast.expr,
    class_stack: Sequence[str],
    callable_index: PythonCallableIndex,
) -> SymbolCallTarget | None:
    if isinstance(func, ast.Name) and callable_index.has_function(func.id):
        return SymbolCallTarget(func.id, func.id, "direct")
    if not isinstance(func, ast.Attribute):
        return None

    receiver = python_call_receiver_name(func.value)
    class_name = python_receiver_class_name(func.value)
    if class_name and callable_index.has_method(class_name, func.attr):
        return SymbolCallTarget(f"{class_name}.{func.attr}", python_call_raw_target(func), "class_method", receiver)
    if receiver in {"self", "cls"} and class_stack:
        current_class = ".".join(class_stack)
        if callable_index.has_method(current_class, func.attr):
            return SymbolCallTarget(
                f"{current_class}.{func.attr}", python_call_raw_target(func), "instance_method", receiver
            )
    return None


def python_attribute_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr.lower()
    if isinstance(node, ast.Name):
        return node.id.lower()
    return None


def python_call_root_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return python_call_root_name(node.value)
    if isinstance(node, ast.Call):
        return python_call_root_name(node.func)
    return None


def python_call_receiver_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return python_call_receiver_name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def python_receiver_class_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        return python_call_receiver_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    return None


def python_call_raw_target(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except ValueError:
        return "unknown"


def python_string_arg(call: ast.Call, index: int) -> str | None:
    if index >= len(call.args):
        return None
    return python_string_value(call.args[index])


def python_string_values_from_arg(call: ast.Call, index: int) -> list[str]:
    if index >= len(call.args):
        return []
    return python_string_values(call.args[index])


def python_keyword_string(call: ast.Call, keyword_name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == keyword_name:
            return python_string_value(keyword.value)
    return None


def python_keyword_strings(call: ast.Call, keyword_name: str) -> list[str]:
    for keyword in call.keywords:
        if keyword.arg == keyword_name:
            return python_string_values(keyword.value)
    return []


def python_string_values(node: ast.AST) -> list[str]:
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return [value for item in node.elts if (value := python_string_value(item))]
    value = python_string_value(node)
    return [value] if value else []


def python_string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(python_joined_string_part(value) for value in node.values)
    return None


def python_joined_string_part(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.FormattedValue):
        try:
            return "${" + ast.unparse(node.value).strip() + "}"
        except ValueError:
            return "${expr}"
    return ""
