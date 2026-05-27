"""Python AST value extraction helpers."""

from __future__ import annotations

import ast


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
