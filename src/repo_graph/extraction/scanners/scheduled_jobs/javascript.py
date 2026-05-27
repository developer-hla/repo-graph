"""JavaScript scheduled job extraction."""

from __future__ import annotations

import re

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.facts import EntityFact, FactBatch
from repo_graph.extraction.scanners.scheduled_jobs.facts import scheduled_job_facts

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
