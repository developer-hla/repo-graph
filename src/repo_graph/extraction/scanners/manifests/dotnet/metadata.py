""".NET project metadata helpers."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from repo_graph.extraction.scanners.manifests.dotnet.xml_utils import first_xml_text, xml_root_or_none


def dotnet_project_metadata(content: str) -> dict[str, str | None]:
    root = xml_root_or_none(content)
    if root is None:
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
