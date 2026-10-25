from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .agents import PlannerAgent, ReviewerAgent, WriterAgent
from .api_client import OpenAICompatibleClient
from .models import WorkflowState, utc_now
from .storage import StateStore


@dataclass
class WorkflowResult:
    status: str
    run_dir: Path
    final_document_path: Path
    state: WorkflowState


class ContentWorkflow:
    """编排规划、写作、审校三个 Agent 的顺序与条件循环。"""

    def __init__(
        self,
        output_root: Path,
        max_revisions: int = 2,
        api_client: OpenAICompatibleClient | None = None,
    ):
        self.output_root = output_root
        self.max_revisions = max_revisions
        self.planner = PlannerAgent(api_client)
        self.writer = WriterAgent(api_client)
        self.reviewer = ReviewerAgent(api_client)

    def _new_run_dir(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.output_root / f"run_{stamp}_{uuid4().hex[:6]}"

    def run(
        self, topic: str, audience: str, resume_dir: Path | None = None
    ) -> WorkflowResult:
        run_dir = resume_dir or self._new_run_dir()
        store = StateStore(run_dir)
        if resume_dir:
            state = store.load()
            store.log(f"{utc_now()} RESUME step={state.current_step}")
        else:
            state = WorkflowState(uuid4().hex, topic, audience)
            store.save(state)

        try:
            if not state.plan:
                state.transition("planning")
                store.log(f"{utc_now()} START planning")
                state.plan = self.planner.execute(state)
                store.save(state)

            if not state.draft:
                state.transition("writing")
                store.log(f"{utc_now()} START writing")
                state.draft = self.writer.execute(state)
                store.save(state)

            while True:
                state.transition("reviewing")
                store.log(f"{utc_now()} START review revision={state.revision_count}")
                decision = self.reviewer.execute(state)
                state.review = decision.to_dict()
                store.save(state)

                if decision.approved:
                    break
                if state.revision_count >= self.max_revisions:
                    state.transition("failed", "failed")
                    state.errors.append("达到最大返工次数，审校仍未通过。")
                    store.save(state)
                    return self._result(state, run_dir)

                state.revision_count += 1
                state.transition("revising")
                store.log(
                    f"{utc_now()} START revision={state.revision_count} "
                    f"feedback={decision.feedback}"
                )
                state.draft = self.writer.execute(state, decision.feedback)
                store.save(state)

            state.transition("completed", "completed")
            store.log(f"{utc_now()} COMPLETED score={state.review['score']}")
            store.save(state)
            return self._result(state, run_dir)
        except Exception as exc:
            state.status = "failed"
            state.errors.append(f"{type(exc).__name__}: {exc}")
            store.log(f"{utc_now()} ERROR {type(exc).__name__}: {exc}")
            store.save(state)
            raise

    @staticmethod
    def _result(state: WorkflowState, run_dir: Path) -> WorkflowResult:
        final_path = run_dir / "final_document.md"
        final_path.write_text(state.draft, encoding="utf-8")
        return WorkflowResult(state.status, run_dir, final_path, state)

