"""Shared .NET manifest and config scanner helpers."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_fact, unresolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.scanners.common import string_value
from repo_graph.extraction.scanners.interaction_helpers import (
    http_target,
    service_name_from_identifier,
    service_name_from_url,
    url_value,
)

DOTNET_PROJECT_SUFFIXES = {".csproj", ".fsproj", ".vbproj"}


DOTNET_BUILD_SUFFIXES = {".props", ".targets"}


SLN_PROJECT_RE = re.compile(r'^Project\("[^"]+"\)\s*=\s*"([^"]+)",\s*"([^"]+)"')


def dotnet_project_metadata(content: str) -> dict[str, str | None]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return dotnet_metadata_defaults()
    return dotnet_project_metadata_from_root(root)


def dotnet_project_metadata_from_root(root: ET.Element, default_name: str | None = None) -> dict[str, str | None]:
    package_id = first_xml_text(root, "PackageId")
    assembly_name = first_xml_text(root, "AssemblyName") or default_name
    root_namespace = first_xml_text(root, "RootNamespace")
    version = first_xml_text(root, "Version")
    return {
        "package_id": package_id,
        "assembly_name": assembly_name,
        "root_namespace": root_namespace,
        "version": version,
        "target_framework": first_xml_text(root, "TargetFramework"),
        "target_frameworks": first_xml_text(root, "TargetFrameworks"),
        "output_type": first_xml_text(root, "OutputType"),
    }


def dotnet_metadata_defaults() -> dict[str, str | None]:
    return {
        "package_id": None,
        "assembly_name": None,
        "root_namespace": None,
        "version": None,
        "target_framework": None,
        "target_frameworks": None,
        "output_type": None,
    }


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
        yield {
            "name": Path(raw_target).stem,
            "raw_target": raw_target,
            "normalized_target": Path(raw_target).stem,
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


def solution_project_reference(line: str) -> dict[str, str | None] | None:
    match = SLN_PROJECT_RE.match(line)
    if not match:
        return None
    raw_path = match.group(2)
    if Path(raw_path).suffix.lower() not in DOTNET_PROJECT_SUFFIXES:
        return None
    return {
        "name": Path(raw_path).stem,
        "display_name": match.group(1),
        "raw_target": raw_path,
        "normalized_target": Path(raw_path).stem,
    }


def config_file_fact(context: FileScanContext, config_kind: str) -> EntityFact:
    name = Path(context.rel_path).name
    return entity_fact(
        context,
        entity_type="config_file",
        name=name,
        aliases={name, context.rel_path},
        properties={
            "config_kind": config_kind,
            "ecosystem": "dotnet",
            "path": context.rel_path,
            "project": context.project.name if context.project else None,
        },
    )


def framework_config_value_facts(context: FileScanContext, root: ET.Element) -> Iterable[EntityFact]:
    for section in root.iter():
        section_name = xml_local_name(section.tag)
        if section_name == "appSettings":
            for child in section:
                if xml_local_name(child.tag) == "add":
                    key = string_value(child.attrib.get("key"))
                    if key:
                        yield config_value_fact(
                            context,
                            key,
                            "app_setting",
                            {
                                "key": key,
                                "has_value": string_value(child.attrib.get("value")) is not None,
                                "target_url": url_value(child.attrib.get("value")),
                            },
                        )
        elif section_name == "connectionStrings":
            for child in section:
                if xml_local_name(child.tag) == "add":
                    name = string_value(child.attrib.get("name"))
                    if name:
                        yield config_value_fact(
                            context,
                            name,
                            "connection_string",
                            {
                                "key": name,
                                "provider_name": string_value(child.attrib.get("providerName")),
                                "has_value": string_value(child.attrib.get("connectionString")) is not None,
                            },
                        )
        elif section_name == "client":
            for child in section:
                if xml_local_name(child.tag) == "endpoint":
                    name = string_value(child.attrib.get("name")) or string_value(child.attrib.get("contract"))
                    address = url_value(child.attrib.get("address"))
                    if name or address:
                        yield config_value_fact(
                            context,
                            name or address or "endpoint",
                            "wcf_endpoint",
                            {
                                "key": name,
                                "contract": string_value(child.attrib.get("contract")),
                                "binding": string_value(child.attrib.get("binding")),
                                "target_url": address,
                            },
                        )


def config_value_fact(
    context: FileScanContext,
    name: str,
    value_kind: str,
    properties: dict[str, Any],
) -> EntityFact:
    entity_name = f"{value_kind}:{name}"
    return entity_fact(
        context,
        entity_type="config_value",
        name=entity_name,
        aliases={name, entity_name},
        properties={
            "display_name": name,
            "value_kind": value_kind,
            "project": context.project.name if context.project else None,
            **{key: value for key, value in properties.items() if value is not None},
        },
    )


def config_service_fact(
    config_value: EntityFact,
    context: FileScanContext,
    parser: str,
) -> RelationshipFact | None:
    raw_target = config_value.properties.get("target_url")
    if not isinstance(raw_target, str):
        return None
    key = config_value.properties.get("key")
    contract = config_value.properties.get("contract")
    service_name = service_name_from_identifier(key or contract or service_name_from_url(raw_target))
    target = http_target(raw_target, "GET")
    target["dependency_scope"] = "configuration"
    target["interaction_kind"] = "service_configuration"
    target["service_name"] = service_name
    return unresolved_relationship_fact(
        config_value.reference,
        service_name,
        "CONFIGURES_SERVICE",
        context,
        parser,
        to_type="service",
        properties=target,
    )


def xml_root(content: str, context: FileScanContext) -> ET.Element:
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML {context.source.name}/{context.rel_path}: {exc}") from exc


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
