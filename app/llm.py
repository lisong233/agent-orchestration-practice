"""
LLM 客户端封装 — 对 Anthropic API（兼容 OpenAI SDK）。
复用 Claude Code 的 ANTHROPIC_AUTH_TOKEN 环境变量。
"""
import os, json
from openai import OpenAI


def get_client() -> OpenAI:
    """获取 LLM 客户端，优先 ANTHROPIC_AUTH_TOKEN"""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if not api_key:
        raise RuntimeError("未设置 ANTHROPIC_API_KEY 或 ANTHROPIC_AUTH_TOKEN 环境变量")

    return OpenAI(
        api_key=api_key,
        base_url="https://api.anthropic.com/v1/",  # Anthropic OpenAI-compatible endpoint
    )


def chat_json(
    system: str,
    user: str,
    model: str = "claude-sonnet-4-6",
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> dict:
    """
    发送 chat 请求并返回 JSON 解析结果。
    使用 Anthropic 的 OpenAI 兼容端点。
    """
    client = get_client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    return json.loads(content)


def chat_text(
    system: str,
    user: str,
    model: str = "claude-sonnet-4-6",
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> str:
    """发送 chat 请求并返回纯文本"""
    client = get_client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content
