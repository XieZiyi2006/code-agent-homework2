from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from workflow.api_client import OpenAICompatibleClient
from workflow.orchestrator import ContentWorkflow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="三 Agent 内容创作 Workflow：规划、写作、审校。"
    )
    parser.add_argument("--topic", default="多 Agent Workflow 入门")
    parser.add_argument("--audience", default="软件工程课程学生")
    parser.add_argument("--output-dir", default="runs")
    parser.add_argument("--max-revisions", type=int, default=2)
    parser.add_argument("--provider", choices=("local", "api"), default="local")
    parser.add_argument(
        "--base-url",
        default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.getenv("OPENAI_TIMEOUT", "180")),
        help="每次模型 API 请求的超时秒数（默认 180）。",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        help="从已有 run 目录中的 state.json 恢复执行。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_client = None
    if args.provider == "api":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise SystemExit("API 模式需要先设置 OPENAI_API_KEY 环境变量。")
        api_client = OpenAICompatibleClient(
            api_key=api_key,
            base_url=args.base_url,
            model=args.model,
            timeout=args.timeout,
        )
    workflow = ContentWorkflow(
        output_root=Path(args.output_dir),
        max_revisions=args.max_revisions,
        api_client=api_client,
    )
    result = workflow.run(
        topic=args.topic,
        audience=args.audience,
        resume_dir=args.resume,
    )

    print("\nWorkflow 执行完成")
    print(f"状态: {result.status}")
    print(f"运行目录: {result.run_dir}")
    print(f"最终文档: {result.final_document_path}")
    print(f"审校轮次: {result.state.revision_count + 1}")
    print("Agent 消息数:", len(result.state.messages))
    print("\n最终审校结果:")
    print(json.dumps(result.state.review, ensure_ascii=False, indent=2))
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

