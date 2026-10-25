from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Message:
    sender: str
    recipient: str
    kind: str
    payload: dict[str, Any]
    created_at: str = field(default_factory=utc_now)


@dataclass
class WorkflowState:
    workflow_id: str
    topic: str
    audience: str
    status: str = "created"
    current_step: str = "created"
    plan: dict[str, Any] = field(default_factory=dict)
    draft: str = ""
    review: dict[str, Any] = field(default_factory=dict)
    revision_count: int = 0
    messages: list[Message] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    history: list[dict[str, str]] = field(default_factory=list)

    def transition(self, step: str, status: str = "running") -> None:
        self.current_step = step
        self.status = status
        self.history.append({"step": step, "status": status, "at": utc_now()})

    def send(
        self, sender: str, recipient: str, kind: str, payload: dict[str, Any]
    ) -> None:
        self.messages.append(Message(sender, recipient, kind, payload))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowState":
        data = dict(data)
        data["messages"] = [Message(**message) for message in data.get("messages", [])]
        return cls(**data)

