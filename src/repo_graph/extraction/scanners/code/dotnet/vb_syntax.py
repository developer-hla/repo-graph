"""Visual Basic syntax helpers for the .NET scanner."""

from __future__ import annotations

import re

VB_ATTRIBUTE_RE = re.compile(r"^\s*<\s*([A-Za-z_][\w.]*)", re.IGNORECASE)
VB_NAMESPACE_RE = re.compile(r"^\s*Namespace\s+([A-Za-z_][\w.]*)", re.IGNORECASE)
VB_TYPE_RE = re.compile(
    r"^\s*(?:(?:Public|Private|Friend|Protected|Partial|MustInherit|NotInheritable)\s+)*"
    r"(Class|Module|Interface)\s+([A-Za-z_]\w*)",
    re.IGNORECASE,
)
VB_METHOD_RE = re.compile(
    r"^\s*(?:(?:Public|Private|Protected|Friend|Shared|Overrides|Overridable|Async|Static)\s+)*"
    r"(Function|Sub)\s+([A-Za-z_]\w*)",
    re.IGNORECASE,
)
VB_END_METHOD_RE = re.compile(r"^\s*End\s+(Function|Sub)\b", re.IGNORECASE)


def vb_scope_code(line: str) -> str:
    return re.sub(r'"(?:[^"]|"")*"', '""', line)


__all__ = [
    "vb_scope_code",
]
