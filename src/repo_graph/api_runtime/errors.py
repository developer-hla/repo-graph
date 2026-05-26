"""HTTP error mapping helpers."""

from __future__ import annotations

from fastapi import HTTPException


def neo4j_http_exception(operation: str, exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=f"Entity not found: {exc.args[0]}")
    return HTTPException(status_code=503, detail=f"Neo4j {operation} failed: {exc}")


__all__ = [
    "neo4j_http_exception",
]
