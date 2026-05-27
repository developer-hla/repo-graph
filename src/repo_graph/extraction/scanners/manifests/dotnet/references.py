""".NET package and project reference helpers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterable

from repo_graph.extraction.scanners.common import string_value
from repo_graph.extraction.scanners.manifests.dotnet.paths import dotnet_manifest_path_stem
from repo_graph.extraction.scanners.manifests.dotnet.xml_utils import first_child_text, xml_local_name


def dotnet_package_references(root: ET.Element) -> Iterable[dict[str, str | None]]:
    for element in root.iter():
        if xml_local_name(element.tag) != "PackageReference":
            continue
        package_name = string_value(element.attrib.get("Include")) or string_value(element.attrib.get("Update"))
        if not package_name:
            continue
        yield {
            "name": package_name,
            "version": string_value(element.attrib.get("Version")) or first_child_text(element, "Version"),
            "raw_target": package_name,
        }


def dotnet_project_references(root: ET.Element) -> Iterable[dict[str, str | None]]:
    for element in root.iter():
        if xml_local_name(element.tag) != "ProjectReference":
            continue
        raw_target = string_value(element.attrib.get("Include"))
        if not raw_target:
            continue
        name = dotnet_manifest_path_stem(raw_target)
        yield {
            "name": name,
            "raw_target": raw_target,
            "normalized_target": name,
        }


def packages_config_references(root: ET.Element) -> Iterable[dict[str, str | None]]:
    for element in root.iter():
        if xml_local_name(element.tag) != "package":
            continue
        package_name = string_value(element.attrib.get("id"))
        if not package_name:
            continue
        yield {
            "name": package_name,
            "version": string_value(element.attrib.get("version")),
            "raw_target": package_name,
        }
