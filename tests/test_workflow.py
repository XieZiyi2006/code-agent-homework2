from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from workflow.api_client import OpenAICompatibleClient, parse_json_object
from workflow.orchestrator import ContentWorkflow


class FakeApiClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        if "规划 Agent" in system_prompt:
            return json.dumps(
                {
                    "title": "API 测试主题",
                    "audience": "学生",
                    "goal": "测试 API 模式",
                    "sections": ["背景", "实现", "总结"],
                    "requirements": ["内容完整"],
                },
                ensure_ascii=False,
            )
        if "审校 Agent" in system_prompt:
            return json.dumps(
                {
                    "approved": {"value": True},
                    "score": {"overall": 90},
                    "feedback": ["内容达标，可考虑补充一个例子。"],
                    "dimensions": {"clarity": {"score": 90}},
                },
                ensure_ascii=False,
            )
        return "# API 生成的 Markdown\n\n## 背景\n内容。\n\n## 实现\n内容。\n\n## 总结\n内容。"


class ContentWorkflowTests(unittest.TestCase):
    def test_json_parser_accepts_fenced_json_with_surrounding_text(self) -> None:
        response = (
            "审校结果如下：\n```json\n"
            '{"approved": true, "score": 90, "feedback": []}\n'
            "```\n以上为审校结论。"
        )
        parsed = parse_json_object(response)
        self.assertTrue(parsed["approved"])
        self.assertEqual(90, parsed["score"])

    def test_json_parser_reports_non_json_response(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "响应片段"):
            parse_json_object("模型暂时无法完成审校。")

    def test_api_mode_uses_client_for_all_agents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = FakeApiClient()
            result = ContentWorkflow(
                Path(temp_dir), max_revisions=0, api_client=client
            ).run("API 测试主题", "学生")
            self.assertEqual("completed", result.status)
            self.assertTrue(result.state.review["approved"])
            self.assertEqual(90, result.state.review["score"])
            self.assertEqual(90, result.state.review["dimensions"]["clarity"])
            self.assertEqual(1, len(result.state.review["feedback"]))
            self.assertEqual(3, client.calls)

    def test_end_to_end_workflow_completes_after_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = ContentWorkflow(Path(temp_dir), max_revisions=2).run(
                topic="多 Agent Workflow", audience="软件工程学生"
            )
            self.assertEqual("completed", result.status)
            self.assertEqual(1, result.state.revision_count)
            self.assertTrue(result.state.review["approved"])
            self.assertGreaterEqual(result.state.review["score"], 85)
            self.assertTrue(result.final_document_path.exists())

    def test_agents_exchange_messages_and_state_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = ContentWorkflow(Path(temp_dir)).run("测试流程", "开发者")
            message_kinds = [message.kind for message in result.state.messages]
            self.assertIn("planning_request", message_kinds)
            self.assertIn("plan_ready", message_kinds)
            self.assertIn("revision_required", message_kinds)
            self.assertIn("review_approved", message_kinds)

            state_data = json.loads(
                (result.run_dir / "state.json").read_text(encoding="utf-8")
            )
            self.assertEqual("completed", state_data["status"])
            self.assertGreater(len(state_data["history"]), 3)

    def test_max_revision_limit_can_fail_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = ContentWorkflow(Path(temp_dir), max_revisions=0).run(
                "失败分支测试", "测试人员"
            )
            self.assertEqual("failed", result.status)
            self.assertTrue(result.state.errors)
            self.assertTrue((result.run_dir / "state.json").exists())

    def test_api_client_builds_compatible_request(self) -> None:
        from unittest.mock import patch
        from io import BytesIO

        response_body = json.dumps(
            {"choices": [{"message": {"content": "response text"}}]}
        ).encode("utf-8")

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return response_body

        with patch("workflow.api_client.urlopen", return_value=FakeResponse()) as send:
            client = OpenAICompatibleClient(
                "test-key", "https://api.example/v1/", "test-model"
            )
            self.assertEqual("response text", client.complete("system", "user"))
            request = send.call_args.args[0]
            self.assertEqual(
                "https://api.example/v1/chat/completions", request.full_url
            )
            self.assertEqual("Bearer test-key", request.get_header("Authorization"))

    def test_api_timeout_has_actionable_error(self) -> None:
        from unittest.mock import patch

        with patch("workflow.api_client.urlopen", side_effect=TimeoutError):
            client = OpenAICompatibleClient(
                "test-key", "https://api.example/v1", "test-model", timeout=3
            )
            with self.assertRaisesRegex(RuntimeError, "超过 3 秒"):
                client.complete("system", "user")


if __name__ == "__main__":
    unittest.main()

