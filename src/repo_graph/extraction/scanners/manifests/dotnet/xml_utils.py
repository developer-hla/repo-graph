""".NET XML parsing helpers."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.scanners.common import string_value


def xml_root(content: str, context: FileScanContext) -> ET.Element:
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML {context.source.name}/{context.rel_path}: {exc}") from exc


def xml_root_or_none(content: str) -> ET.Element | None:
    try:
        return ET.fromstring(content)
    except ET.ParseError:
        return None


def first_xml_text(root: ET.Element, name: str) -> str | None:
    for element in root.iter():
        if xml_local_name(element.tag) == name:
            value = string_value(element.text)
            if value:
                return value
    return None


def first_child_text(root: ET.Element, name: str) -> str | None:
    for child in root:
        if xml_local_name(child.tag) == name:
            return string_value(child.text)
    return None


def xml_local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]
