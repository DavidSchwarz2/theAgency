"""Pydantic models for the GitHub API adapter."""

from pydantic import BaseModel, Field


class GitHubIssue(BaseModel):
    number: int
    title: str
    body: str | None = None
    labels: list[str] = Field(default_factory=list)
