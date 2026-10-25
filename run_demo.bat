@echo off
cd /d "%~dp0"
chcp 65001 >nul
python main.py --topic "多 Agent Workflow 入门" --audience "软件工程课程学生" --output-dir runs
pause
