"""Scheduled job fact construction."""

from __future__ import annotations

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_fact, entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, FactBatch


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
