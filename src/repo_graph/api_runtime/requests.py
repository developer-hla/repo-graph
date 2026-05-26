"""API request models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from repo_graph.extraction import MAX_FILE_BYTES


class LoadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph_path: str | None = None
    clear_existing: bool = True


class BuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_path: str | None = None
    output_path: str | None = None
    sync: bool = False
    strict: bool = False
    max_file_bytes: int = MAX_FILE_BYTES


class BuildLoadRequest(BuildRequest):
    clear_existing: bool = True


class RefreshRequest(BuildRequest):
    load: bool = False


class RefreshChangedRequest(BuildRequest):
    pass


class SnapshotStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_path: str | None = None
    sync: bool = False
    max_file_bytes: int = MAX_FILE_BYTES


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_path: str | None = None


__all__ = [
    "BuildLoadRequest",
    "BuildRequest",
    "LoadRequest",
    "RefreshChangedRequest",
    "RefreshRequest",
    "SnapshotStatusRequest",
    "SyncRequest",
]
