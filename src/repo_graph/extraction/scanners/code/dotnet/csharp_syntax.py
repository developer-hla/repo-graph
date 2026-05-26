"""C# syntax helpers for the .NET scanner."""

from __future__ import annotations

import re
from dataclasses import dataclass

CS_ATTRIBUTE_LINE_RE = re.compile(r"^\s*\[(?P<body>.+)\]\s*$")
CS_ATTRIBUTE_ITEM_RE = re.compile(r"(?P<name>[A-Za-z_][\w.]*)(?:Attribute)?\s*(?:\((?P<args>[^)]*)\))?")
CS_NAMESPACE_RE = re.compile(r"^\s*namespace\s+([A-Za-z_][\w.]*)(?:\s*;|\s*\{)?")


@dataclass(frozen=True)
class CSharpAttribute:
    name: str
    args: str | None
    line_number: int


def csharp_attributes(line: str, line_number: int) -> list[CSharpAttribute]:
    match = CS_ATTRIBUTE_LINE_RE.match(line)
    if not match:
        return []
    return [
        CSharpAttribute(
            name=csharp_attribute_name(attribute_match.group("name")),
            args=attribute_match.group("args"),
            line_number=line_number,
        )
        for attribute_match in CS_ATTRIBUTE_ITEM_RE.finditer(match.group("body"))
    ]


def csharp_attribute_name(name: str) -> str:
    return name.rsplit(".", 1)[-1].removesuffix("Attribute").lower()


def csharp_first_string(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(?:\$@|@\$|\$|@)?\"((?:\"\"|\\.|[^\"])*)\"", value)
    if not match:
        return None
    return csharp_unescape_string(match.group(1))


def csharp_unescape_string(value: str) -> str:
    return value.replace('""', '"').replace(r"\"", '"').replace(r"\\", "\\")


def csharp_replace_route_tokens(value: str, type_name: str | None, method_name: str | None) -> str:
    controller_name = type_name.removesuffix("Controller") if type_name else ""
    route = re.sub(r"\[controller\]", controller_name, value, flags=re.IGNORECASE)
    return re.sub(r"\[action\]", method_name or "", route, flags=re.IGNORECASE)


def csharp_join_route_paths(prefix: str | None, path: str) -> str:
    if path.startswith("/"):
        return path
    parts = [part.strip("/") for part in (prefix, path) if part and part.strip("/")]
    return "/" + "/".join(parts) if parts else "/"


def csharp_should_clear_attributes(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped and not stripped.startswith("//"))


def csharp_function_scope_state(line: str, brace_depth: int, seen_body: bool) -> tuple[int, bool]:
    code = csharp_scope_code(line)
    seen_body = seen_body or "{" in code
    brace_depth += code.count("{") - code.count("}")
    return brace_depth, seen_body


def csharp_scope_code(line: str) -> str:
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', line)


__all__ = [
    "CSharpAttribute",
    "csharp_attribute_name",
    "csharp_attributes",
    "csharp_first_string",
    "csharp_function_scope_state",
    "csharp_join_route_paths",
    "csharp_replace_route_tokens",
    "csharp_scope_code",
    "csharp_should_clear_attributes",
    "csharp_unescape_string",
]
