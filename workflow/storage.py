from __future__ import annotations

import json
from pathlib import Path

from .models import WorkflowState


class StateStore:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)

    @property
    def state_path(self) -> Path:
        return self.run_dir / "state.json"

    def save(self, state: WorkflowState) -> None:
        self.state_path.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.run_dir / "messages.json").write_text(
            json.dumps(
                [message.__dict__ for message in state.messages],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def load(self) -> WorkflowState:
        return WorkflowState.from_dict(
            json.loads(self.state_path.read_text(encoding="utf-8"))
        )

    def log(self, line: str) -> None:
        with (self.run_dir / "workflow.log").open("a", encoding="utf-8") as file:
            file.write(line + "\n")

