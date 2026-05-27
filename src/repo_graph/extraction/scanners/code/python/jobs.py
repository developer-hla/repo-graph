"""Python scheduled job helpers."""

from __future__ import annotations

import ast
from collections.abc import Sequence

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.facts import EntityFact, FactBatch
from repo_graph.extraction.scanners.code.python.ast_values import (
    python_attribute_name,
    python_keyword_string,
    python_string_arg,
)
from repo_graph.extraction.scanners.scheduled_jobs.facts import scheduled_job_facts


def python_job_facts(
    context: FileScanContext,
    decorators: Sequence[ast.expr],
    line_number: int,
    handler: EntityFact | None,
) -> FactBatch:
    facts = FactBatch()
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        callee = python_attribute_name(decorator.func)
        if callee not in {"cron", "periodic_task", "scheduled"}:
            continue
        schedule = (
            python_string_arg(decorator, 0)
            or python_keyword_string(decorator, "schedule")
            or python_keyword_string(decorator, "cron")
        )
        if not schedule:
            continue
        handler_name = handler.name if handler else "job"
        facts.extend(
            scheduled_job_facts(
                context,
                f"{handler_name} @ {schedule}",
                schedule,
                "python_job",
                line_number,
                handler,
            )
        )
    return facts
