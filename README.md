# Simple Workflow MVP

这是一个可直接运行的三 Agent 内容创作 Workflow，用于完成 Homework 2 的核心要求。默认本地模式只使用 Python 标准库；可选 API 模式也通过标准库调用 OpenAI-compatible Chat Completions，无需安装 SDK。

## 功能

- 3 个 Agent 顺序协作：规划 Agent、写作 Agent、审校 Agent
- 通过 `WorkflowState` 共享规划、草稿、审校结果和运行状态
- 通过消息记录实现 Agent 间通信，可查看发送方、接收方和载荷
- 审校不通过时自动返回写作 Agent 修改，形成条件循环
- 每一步保存检查点，支持 `--resume` 恢复
- 输出日志、状态、消息和最终 Markdown 文档
- 包含端到端、通信和失败分支测试
- 可选接入 OpenAI-compatible API，让三个 Agent 调用模型完成规划、写作和审校

## 环境

- Python 3.10 或更高版本
- Windows、macOS、Linux 均可运行

## 快速运行

```powershell
python main.py --topic "多 Agent Workflow 入门" --audience "软件工程课程学生"
```

## API 模式

API 模式会把主题、读者信息、规划、草稿和审校上下文发送给配置的模型服务。需要有效密钥和可访问的兼容接口，API 请求可能产生费用。密钥只从环境变量读取，不要提交到 Git。

PowerShell 当前终端设置密钥并运行：

```powershell
$env:OPENAI_API_KEY = "你的 API 密钥"
$env:OPENAI_BASE_URL = "https://api.openai.com/v1"
$env:OPENAI_MODEL = "gpt-4o-mini"
python main.py --provider api
```

若服务响应较慢，可延长单次请求等待时间，例如：

```powershell
python main.py --provider api --timeout 300
```

兼容服务也可以通过参数指定地址和模型：

```powershell
python main.py --provider api --base-url "https://你的服务/v1" --model "你的模型名"
```

接口需要支持 `POST /chat/completions`，并返回标准 `choices[0].message.content`。若不指定 `--provider api`，程序仍使用离线本地模式。

清除当前 PowerShell 会话中的密钥：

```powershell
Remove-Item Env:OPENAI_API_KEY
```

自定义输出目录：

```powershell
python main.py --output-dir runs --max-revisions 2
```

从中断点恢复：

```powershell
python main.py --resume runs\run_YYYYMMDD_HHMMSS_xxxxxx
```

## 运行测试

```powershell
python -m unittest discover -s tests -v
```

## 输出说明

每次执行会生成独立目录：

```text
runs/run_时间_随机编号/
├── final_document.md  最终内容
├── state.json         Workflow 共享状态和历史
├── messages.json      Agent 消息记录
└── workflow.log       执行日志
```

## 演示建议

1. 运行主程序，展示控制台中的完成状态和最终评分。
2. 打开 `workflow.log`，说明规划、写作、审校、返工、复审的顺序。
3. 打开 `messages.json`，展示 Agent 间消息传递。
4. 打开 `state.json`，展示共享状态和步骤历史。
5. 运行测试，展示成功流程与最大返工次数失败分支。

详细架构见 [DESIGN.md](DESIGN.md)。

