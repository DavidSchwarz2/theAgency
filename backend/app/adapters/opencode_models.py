from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    """Shared config: silently ignore unknown fields from the OpenCode API."""

    model_config = ConfigDict(extra="ignore")


class SessionInfo(_Base):
    id: str
    title: str | None = None


class MessageInfo(_Base):
    id: str
    sessionID: str
    role: Literal["user", "assistant", "system"]


class Part(_Base):
    type: str
    # `content` is optional; some part types (e.g. tool calls) carry no text content.
    content: str | None = None


class MessageResponse(_Base):
    info: MessageInfo
    parts: list[Part]


class TodoItem(_Base):
    content: str
    status: Literal["pending", "in_progress", "completed", "cancelled"]
    priority: Literal["high", "medium", "low", ""] = ""
