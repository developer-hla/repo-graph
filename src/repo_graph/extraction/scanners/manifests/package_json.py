"""JavaScript package manifest scanners."""

from __future__ import annotations

import json
from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import (
    declares_package_facts,
    entity_fact,
    entity_reference,
    package_dependency_fact,
    package_entity_fact,
    resolved_relationship_fact,
    scan_issue,
)
from repo_graph.extraction.facts import FactBatch
from repo_graph.extraction.scanners.common import read_yaml_object, string_value
from repo_graph.extraction.scanners.package_helpers import package_dependencies


class PackageJsonExtractor:
    name = "package_json"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "package.json"

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        try:
            package = json.loads(content)
        except json.JSONDecodeError as exc:
            facts.issues.append(
                scan_issue(context, self.name, f"Invalid package.json {context.source.name}/{context.rel_path}: {exc}")
            )
            return facts
        if not isinstance(package, dict):
            facts.issues.append(
                scan_issue(
                    context,
                    self.name,
                    f"Invalid package.json {context.source.name}/{context.rel_path}: root must be object",
                )
            )
            return facts

        package_name = string_value(package.get("name"))
        package_ref = None
        if package_name:
            package_fact = package_entity_fact(
                context,
                name=package_name,
                aliases={package_name, package_name.removeprefix("@").split("/")[-1]},
                properties={
                    "version": package.get("version"),
                    "private": package.get("private"),
                    "scripts": sorted((package.get("scripts") or {}).keys())
                    if isinstance(package.get("scripts"), dict)
                    else [],
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
        for dependency in package_dependencies(package):
            facts.relationships.append(
                package_dependency_fact(
                    dependency_source_ref,
                    dependency["name"],
                    "javascript",
                    dependency["dependency_type"],
                    dependency["version"],
                    dependency["raw_target"],
                    context,
                    self.name,
                )
            )

        return facts


class PnpmWorkspaceExtractor:
    name = "pnpm_workspace"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "pnpm-workspace.yaml"

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        data = read_yaml_object(content)
        package_patterns = data.get("packages") if data else None
        workspace_fact = entity_fact(
            context,
            entity_type="workspace",
            name=f"{context.source.name} workspace",
            aliases={context.source.name},
            properties={
                "ecosystem": "javascript",
                "path": context.rel_path,
                "package_patterns": package_patterns if isinstance(package_patterns, list) else [],
            },
        )
        facts.entities.append(workspace_fact)
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                workspace_fact.reference,
                "DECLARES_WORKSPACE",
                context,
                self.name,
            )
        )
        return facts
