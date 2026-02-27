"""Filesystem browser — exposes a simple directory listing for the UI directory picker."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

router = APIRouter(prefix="/fs", tags=["filesystem"])


class FsEntry(BaseModel):
    name: str
    path: str
    is_dir: bool


class FsBrowseResponse(BaseModel):
    path: str
    parent: str | None
    entries: list[FsEntry]


@router.get("/browse", response_model=FsBrowseResponse)
async def browse(
    path: str = Query(default="", description="Absolute path to browse. Defaults to home directory."),
    dirs_only: bool = Query(default=False, description="Return only directories."),
) -> FsBrowseResponse:
    target = Path(path).expanduser() if path else Path.home()

    if not target.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Path not found: {target}")
    if not target.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Not a directory: {target}")

    parent = str(target.parent) if target != target.parent else None

    raw = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))

    entries: list[FsEntry] = []
    for child in raw:
        if child.name.startswith("."):
            continue
        if dirs_only and not child.is_dir():
            continue
        entries.append(FsEntry(name=child.name, path=str(child), is_dir=child.is_dir()))

    return FsBrowseResponse(path=str(target), parent=parent, entries=entries)
