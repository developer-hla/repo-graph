""".NET framework config fact helpers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_fact, unresolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.scanners.common import string_value
from repo_graph.extraction.scanners.interactions.http import http_target
from repo_graph.extraction.scanners.interactions.naming import (
    service_name_from_identifier,
    service_name_from_url,
    url_value,
)
from repo_graph.extraction.scanners.manifests.dotnet.xml_utils import xml_local_name


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
            yield from app_setting_facts(context, section)
        elif section_name == "connectionStrings":
            yield from connection_string_facts(context, section)
        elif section_name == "client":
            yield from wcf_endpoint_facts(context, section)


def app_setting_facts(context: FileScanContext, section: ET.Element) -> Iterable[EntityFact]:
    for child in section:
        if xml_local_name(child.tag) != "add":
            continue
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


def connection_string_facts(context: FileScanContext, section: ET.Element) -> Iterable[EntityFact]:
    for child in section:
        if xml_local_name(child.tag) != "add":
            continue
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


def wcf_endpoint_facts(context: FileScanContext, section: ET.Element) -> Iterable[EntityFact]:
    for child in section:
        if xml_local_name(child.tag) != "endpoint":
            continue
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
