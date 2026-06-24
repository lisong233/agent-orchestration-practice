"""
LLM 客户端封装 — 统一使用 Anthropic Messages API。
支持双后端：
  - claude: 默认，复用 ANTHROPIC_AUTH_TOKEN（Claude Code 的 key）
  - deepseek: DeepSeek Anthropic 兼容端点（api.deepseek.com/anthropic）

运行时判断量大 → 走便宜的 deepseek flash/claude-haiku
离线规则发现/难例分析 → 走强的 claude sonnet/opus

全程只用一个 SDK（anthropic），不引入 openai 冗余依赖。
"""
import os, json, re
from anthropic import Anthropic


def get_client(backend: str = "claude") -> Anthropic:
    """
    获取 LLM 客户端。
    backend="claude" → Anthropic 原生端点（ANTHROPIC_AUTH_TOKEN）
    backend="deepseek" → DeepSeek Anthropic 兼容端点（DEEPSEEK_API_KEY）
    """
    if backend == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("未设置 DEEPSEEK_API_KEY 环境变量")
        return Anthropic(api_key=api_key, base_url="https://api.deepseek.com/anthropic")

    # 默认 Claude
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
    backend: str = "claude",
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> dict:
    """发送 chat 请求并返回 JSON 解析结果"""
    client = get_client(backend)
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
    backend: str = "claude",
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> str:
    """发送 chat 请求并返回纯文本"""
    client = get_client(backend)
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return _get_text(resp)
