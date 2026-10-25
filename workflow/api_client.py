from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OpenAICompatibleClient:
    """Minimal standard-library client for OpenAI-compatible Chat Completions."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: int = 180,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
            }
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"API 返回 HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"无法连接模型 API: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError(
                f"等待模型 API 响应超过 {self.timeout} 秒。可检查网络或使用 --timeout 延长等待时间。"
            ) from exc
        except (IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("模型 API 返回了无法识别的响应格式。") from exc

        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("模型 API 响应缺少 message.content。") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("模型 API 返回了空内容。")
        return content.strip()


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    decoder = json.JSONDecoder()

    try:
        value, _ = decoder.raw_decode(cleaned)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    for index, character in enumerate(cleaned):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value

    preview = " ".join(cleaned.split())[:240]
    raise RuntimeError(
        "模型响应中没有找到有效 JSON 对象。响应片段: "
        + (preview or "<empty>")
    )
