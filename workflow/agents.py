from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .api_client import OpenAICompatibleClient, parse_json_object
from .models import WorkflowState


def _number_from(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return None
    if isinstance(value, Mapping):
        for key in ("score", "value", "points", "rating", "total"):
            if key in value:
                number = _number_from(value[key])
                if number is not None:
                    return number
        for nested in value.values():
            number = _number_from(nested)
            if number is not None:
                return number
    if isinstance(value, list):
        for nested in value:
            number = _number_from(nested)
            if number is not None:
                return number
    return None


def _boolean_from(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "approved", "通过"}:
            return True
        if normalized in {"false", "no", "rejected", "不通过"}:
            return False
    if isinstance(value, Mapping):
        for key in ("approved", "value", "result"):
            if key in value:
                result = _boolean_from(value[key])
                if result is not None:
                    return result
    return None


class BaseAgent:
    name = "base"

    def __init__(self, client: OpenAICompatibleClient | None = None):
        self.client = client

    def receive(self, state: WorkflowState, sender: str, kind: str) -> None:
        state.send(sender, self.name, kind, {"step": state.current_step})

    def reply(self, state: WorkflowState, recipient: str, kind: str, **payload: Any) -> None:
        state.send(self.name, recipient, kind, payload)


class PlannerAgent(BaseAgent):
    name = "planner"

    def execute(self, state: WorkflowState) -> dict[str, Any]:
        self.receive(state, "orchestrator", "planning_request")
        if self.client:
            result = parse_json_object(
                self.client.complete(
                    "你是内容规划 Agent。只返回 JSON 对象，字段为 title、audience、goal、sections、requirements。sections 和 requirements 必须是字符串数组。",
                    json.dumps(
                        {"topic": state.topic, "audience": state.audience},
                        ensure_ascii=False,
                    ),
                )
            )
            plan = {
                "title": str(result.get("title", state.topic)),
                "audience": str(result.get("audience", state.audience)),
                "goal": str(result.get("goal", "")),
                "sections": [str(item) for item in result.get("sections", [])],
                "requirements": [
                    str(item) for item in result.get("requirements", [])
                ],
            }
            if not plan["sections"]:
                raise RuntimeError("规划 Agent 没有返回章节列表。")
            self.reply(
                state,
                "writer",
                "plan_ready",
                title=plan["title"],
                sections=plan["sections"],
            )
            return plan

        plan = {
            "title": f"{state.topic}：从概念到可运行流程",
            "audience": state.audience,
            "goal": "用一个可运行示例解释多 Agent 的分工、通信和流程控制。",
            "sections": [
                "问题与目标",
                "Agent 分工",
                "Workflow 执行过程",
                "状态管理与消息传递",
                "运行方法",
            ],
            "requirements": ["结构清楚", "包含可执行步骤", "避免未解释的术语"],
        }
        self.reply(
            state,
            "writer",
            "plan_ready",
            title=plan["title"],
            sections=plan["sections"],
        )
        return plan


class WriterAgent(BaseAgent):
    name = "writer"

    def execute(
        self, state: WorkflowState, feedback: list[str] | None = None
    ) -> str:
        self.receive(
            state,
            "planner" if not feedback else "reviewer",
            "write_request" if not feedback else "revision_request",
        )
        plan = state.plan
        if self.client:
            prompt = {
                "topic": state.topic,
                "audience": state.audience,
                "plan": plan,
                "review_feedback": feedback or [],
                "instruction": "按照规划生成完整 Markdown 内容。直接返回 Markdown，不要使用代码围栏。",
            }
            document = self.client.complete(
                "你是写作 Agent。请使用清晰、准确的中文完成内容。严格依据输入，不编造事实。",
                json.dumps(prompt, ensure_ascii=False),
            )
            self.reply(
                state,
                "reviewer",
                "draft_ready",
                characters=len(document),
                revision=state.revision_count,
            )
            return document

        revision_note = ""
        if feedback:
            revision_note = (
                "\n\n## 审校后的改进摘要\n"
                + "\n".join(f"- 已处理：{item}" for item in feedback)
            )

        document = f"""# {plan['title']}

面向读者：{state.audience}

## 问题与目标

单个 Agent 可以完成局部任务，但复杂任务通常需要不同角色协作。本示例把内容创作拆成规划、写作和审校三个步骤，由编排器按顺序调度。目标是让每个 Agent 只负责清晰的一项工作，同时让整个流程能够追踪、恢复和扩展。

## Agent 分工

- PlannerAgent 接收主题和读者信息，生成标题、目标、章节和质量要求。
- WriterAgent 根据规划生成 Markdown 初稿，并在收到审校意见后修改内容。
- ReviewerAgent 从完整性、结构、相关性和可读性四个维度评分，决定通过或返工。

## Workflow 执行过程

编排器先创建 WorkflowState，然后调用规划 Agent。规划结果写入共享状态，并通过消息记录传给写作 Agent。写作 Agent 产出初稿后，审校 Agent 给出评分和修改意见。若得分低于阈值，编排器把意见送回写作 Agent，并再次审校，直到通过或达到最大返工次数。

这个流程包含顺序执行和条件循环两种控制方式。顺序执行保证规划先于写作，写作先于审校。条件循环让审校结果决定是否返工，因此 Agent 的输出会影响后续流程。

## 状态管理与消息传递

WorkflowState 保存主题、规划、草稿、审校结果、当前步骤、错误和历史记录。每个关键步骤都会把 state.json 写入运行目录，程序中断后可以使用 --resume 恢复。Agent 之间的消息包含发送方、接收方、消息类型、载荷和时间，完整记录在 messages.json 中。

## 运行方法

在项目根目录执行 `python main.py --topic "你的主题" --audience "目标读者"`。程序会创建独立运行目录，输出最终 Markdown 文档、共享状态、消息记录和执行日志。执行 `python -m unittest discover -s tests -v` 可验证端到端流程和条件返工逻辑。
{revision_note}
"""
        self.reply(
            state,
            "reviewer",
            "draft_ready",
            characters=len(document),
            revision=state.revision_count,
        )
        return document


@dataclass
class ReviewDecision:
    approved: bool
    score: int
    feedback: list[str]
    dimensions: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "score": self.score,
            "feedback": self.feedback,
            "dimensions": self.dimensions,
        }


class ReviewerAgent(BaseAgent):
    name = "reviewer"

    def execute(self, state: WorkflowState) -> ReviewDecision:
        self.receive(state, "writer", "review_request")
        draft = state.draft
        if self.client:
            review = parse_json_object(
                self.client.complete(
                    "你是严格但公平的审校 Agent。只返回 JSON 对象，包含 approved(boolean)、score(0到100数字)、feedback(字符串数组)、dimensions(数字对象)。approved 只表示是否达标；feedback 可包含非阻塞建议，不要因为存在建议就把 approved 设为 false。只有未满足要求或 score < 85 时才不通过。",
                    json.dumps(
                        {
                            "topic": state.topic,
                            "audience": state.audience,
                            "requirements": state.plan.get("requirements", []),
                            "required_sections": state.plan.get("sections", []),
                            "draft": draft,
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            try:
                score_value = _number_from(review.get("score"))
                if score_value is None:
                    raise ValueError("score 中没有数字")
                score = max(0, min(100, score_value))
                dimensions = {
                    str(key): number
                    for key, value in review.get("dimensions", {}).items()
                    if (number := _number_from(value)) is not None
                }
                raw_feedback = review.get("feedback", [])
                if isinstance(raw_feedback, str):
                    feedback = [raw_feedback] if raw_feedback.strip() else []
                elif isinstance(raw_feedback, list):
                    feedback = [
                        str(item.get("message", item.get("comment", item)))
                        if isinstance(item, Mapping)
                        else str(item)
                        for item in raw_feedback
                    ]
                else:
                    feedback = [str(raw_feedback)]
                model_approved = _boolean_from(review.get("approved"))
                if model_approved is None:
                    raise ValueError("approved 不是布尔值")
                approved = model_approved and score >= 85
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                raise RuntimeError("审校 Agent 返回的字段不符合要求。") from exc
            decision = ReviewDecision(approved, score, feedback, dimensions)
            self.reply(
                state,
                "orchestrator" if approved else "writer",
                "review_approved" if approved else "revision_required",
                score=score,
                feedback=feedback,
            )
            return decision

        required_headings = [f"## {name}" for name in state.plan["sections"]]
        missing = [heading for heading in required_headings if heading not in draft]

        completeness = 40 if not missing else max(0, 40 - 8 * len(missing))
        structure = 25 if draft.count("## ") >= 5 else 15
        relevance = 20 if state.topic.split()[0].lower() in draft.lower() else 12
        readability = 15 if len(draft) >= 650 else 8

        feedback: list[str] = []
        if missing:
            feedback.append("补充缺失章节：" + "、".join(missing))
        if "审校后的改进摘要" not in draft:
            feedback.append("增加改进摘要，说明如何响应审校意见")
        if len(draft) < 650:
            feedback.append("补充关键实现细节")

        process_score = 10 if "审校后的改进摘要" in draft else 0
        score = completeness + structure + relevance + readability - 10 + process_score
        approved = score >= 85 and not feedback
        decision = ReviewDecision(
            approved=approved,
            score=score,
            feedback=feedback,
            dimensions={
                "completeness": completeness,
                "structure": structure,
                "relevance": relevance,
                "readability": readability,
                "feedback_response": process_score,
            },
        )
        self.reply(
            state,
            "orchestrator" if approved else "writer",
            "review_approved" if approved else "revision_required",
            score=score,
            feedback=feedback,
        )
        return decision

