"""Python package manifest scanners."""

from __future__ import annotations

import tomllib
from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import (
    declares_package_facts,
    entity_reference,
    package_dependency_fact,
    package_entity_fact,
    scan_issue,
)
from repo_graph.extraction.facts import FactBatch
from repo_graph.extraction.scanners.manifest_helpers import is_requirements_file
from repo_graph.extraction.scanners.package_helpers import (
    normalize_python_package_name,
    pyproject_dependencies,
    pyproject_metadata,
    python_import_name,
    requirement_dependency,
)


class PythonProjectExtractor:
    name = "pyproject"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "pyproject.toml"

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        try:
            pyproject = tomllib.loads(content)
        except tomllib.TOMLDecodeError as exc:
            facts.issues.append(
                scan_issue(
                    context,
                    self.name,
                    f"Invalid pyproject.toml {context.source.name}/{context.rel_path}: {exc}",
                )
            )
            return facts
        if not isinstance(pyproject, dict):
            facts.issues.append(
                scan_issue(
                    context,
                    self.name,
                    f"Invalid pyproject.toml {context.source.name}/{context.rel_path}: root must be object",
                )
            )
            return facts

        metadata = pyproject_metadata(pyproject)
        package_ref = None
        if metadata["name"]:
            package_name = metadata["name"]
            package_fact = package_entity_fact(
                context,
                name=package_name,
                aliases={package_name, normalize_python_package_name(package_name), python_import_name(package_name)},
                properties={
                    "ecosystem": "python",
                    "version": metadata["version"],
                    "project": context.project.name if context.project else None,
                },
            )
            facts.entities.append(package_fact)
            package_ref = package_fact.reference
            facts.relationships.extend(declares_package_facts(context, package_ref, self.name))

        dependency_source_ref = (
            package_ref
            if package_ref
            else entity_reference(context.project.entity if context.project else context.file_entity)
        )
        for dependency in pyproject_dependencies(pyproject):
            facts.relationships.append(
                package_dependency_fact(
                    dependency_source_ref,
                    dependency["name"],
                    "python",
                    dependency["dependency_type"],
                    dependency["version"],
                    dependency["raw_target"],
                    context,
                    self.name,
                )
            )
        return facts


class PythonRequirementsExtractor:
    name = "requirements"

    def can_process(self, rel_path: str) -> bool:
        return is_requirements_file(Path(rel_path))

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        dependency_source = context.project.entity if context.project else context.file_entity
        for line_number, line in enumerate(content.splitlines(), start=1):
            dependency = requirement_dependency(line)
            if not dependency:
                continue
            facts.relationships.append(
                package_dependency_fact(
                    entity_reference(dependency_source),
                    dependency["name"],
                    "python",
                    "requirements",
                    dependency["version"],
                    dependency["raw_target"],
                    context,
                    self.name,
                    line_number=line_number,
                )
            )
        return facts
