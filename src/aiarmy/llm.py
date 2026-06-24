"""
LLM 客户端封装 — Anthropic Messages API。
复用 Claude Code 的 ANTHROPIC_AUTH_TOKEN 环境变量。
"""
import os, json, re
from anthropic import Anthropic


def get_client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if not api_key:
        raise RuntimeError("未设置 ANTHROPIC_API_KEY 或 ANTHROPIC_AUTH_TOKEN")
    return Anthropic(api_key=api_key)


def _extract_json(text: str) -> dict:
    """从文本中提取 JSON 对象（处理 markdown code block 包裹）"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试提取 ```json ... ``` 块
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 尝试提取 { ... } 块
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # 返回空字典
    return {"_parse_error": True, "_raw": text[:200]}


def _get_text(resp) -> str:
    """从 Anthropic 响应中提取文本（跳过 thinking blocks）"""
    for block in resp.content:
        if hasattr(block, "text"):
            return block.text
    return ""


def chat_json(
    system: str,
    user: str,
    model: str = "claude-haiku-4-5",
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> dict:
    """发送 chat 请求并返回 JSON 解析结果"""
    client = get_client()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user + "\n\n请只输出JSON，不要包含其他文字。"}],
    )
    content = _get_text(resp)
    return _extract_json(content)


def chat_text(
    system: str,
    user: str,
    model: str = "claude-haiku-4-5",
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> str:
    """发送 chat 请求并返回纯文本"""
    client = get_client()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return _get_text(resp)
