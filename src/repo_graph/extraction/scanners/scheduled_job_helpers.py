"""Shared scheduled job helpers."""

from __future__ import annotations

import re

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_fact, entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, FactBatch

CRON_SCHEDULE_RE = re.compile(
    r"\bcron\s*\.\s*schedule\s*\(\s*(?P<quote>[\"'])(?P<schedule>[^\"']+)(?P=quote)\s*,\s*"
    r"(?P<handler>[A-Za-z_$][\w$]*)",
    re.IGNORECASE,
)


def javascript_scheduled_job_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    handler_by_name: dict[str, EntityFact],
) -> FactBatch:
    facts = FactBatch()
    for match in CRON_SCHEDULE_RE.finditer(line):
        handler_name = match.group("handler")
        facts.extend(
            scheduled_job_facts(
                context,
                job_name=f"{handler_name} @ {match.group('schedule')}",
                schedule=match.group("schedule"),
                parser="javascript_job",
                line_number=line_number,
                handler=handler_by_name.get(handler_name),
            )
        )
    return facts


def scheduled_job_facts(
    context: FileScanContext,
    job_name: str,
    schedule: str,
    parser: str,
    line_number: int,
    handler: EntityFact | None = None,
) -> FactBatch:
    facts = FactBatch()
    job = entity_fact(
        context,
        entity_type="scheduled_job",
        name=job_name,
        line_number=line_number,
        aliases={job_name, schedule},
        properties={
            "schedule": schedule,
            "project": context.project.name if context.project else None,
        },
    )
    facts.entities.append(job)
    facts.relationships.append(
        resolved_relationship_fact(
            entity_reference(context.file_entity),
            job.reference,
            "DECLARES_JOB",
            context,
            parser,
            line_number,
            properties={"schedule": schedule},
        )
    )
    if context.project:
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.project.entity),
                job.reference,
                "SCHEDULES_JOB",
                context,
                parser,
                line_number,
                properties={"schedule": schedule},
            )
        )
    if handler:
        facts.relationships.append(
            resolved_relationship_fact(
                job.reference,
                handler.reference,
                "RUNS_JOB",
                context,
                parser,
                line_number,
                properties={
                    "schedule": schedule,
                    "handler_name": handler.name,
                    "handler_type": handler.entity_type,
                },
            )
        )
    return facts
