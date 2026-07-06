"""
LLM 客户端封装 — 统一使用 Anthropic Messages API。

后端选择（优先级）：
  1. DEEPSEEK_API_KEY 已设 → deepseek + deepseek-v4-flash（最便宜）
  2. 否则 → claude + claude-haiku-4-5（Claude Code 自带 key）

所有 agent 直接调 chat_json/chat_text，不自己判断后端——统一由此模块决定。

运行时覆写：set_override() 可临时替换 API key / base_url / model，供 Web UI
评委自定义 key 场景使用。clear_override() 恢复 .env 默认。
"""
import os, json, re, threading
from pathlib import Path
from anthropic import Anthropic

# ── 自动加载 .env（优先）或 .env.example ──
def _load_dotenv():
    """简易 .env 加载，不依赖 python-dotenv"""
    for name in [".env", ".env.example"]:
        env_file = Path(__file__).parent.parent.parent.parent / name
        if not env_file.exists():
            env_file = Path.cwd() / name
        if env_file.exists():
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k not in os.environ:
                            os.environ[k] = v
            break  # 只加载找到的第一个

_load_dotenv()

# ── 模块级配置：后端 + 模型自动检测 ──
_BACKEND = "claude"
_MODEL = "claude-haiku-4-5"

if os.environ.get("DEEPSEEK_API_KEY"):
    _BACKEND = "deepseek"
    _MODEL = "deepseek-v4-flash"

# ── 运行时覆写（线程安全，供 Web UI 评委自定义 key）──
_override = threading.local()
_override.api_key = None
_override.base_url = None
_override.model = None


def set_override(api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None):
    """设置当前线程的 LLM 配置覆写。下一次管线调用生效。"""
    _override.api_key = api_key
    _override.base_url = base_url
    _override.model = model


def clear_override():
    """清除当前线程的覆写，恢复 .env 默认配置"""
    _override.api_key = None
    _override.base_url = None
    _override.model = None


def get_client(backend: str | None = None) -> Anthropic:
    """
    获取 LLM 客户端。优先级：运行时覆写 > .env 默认。
    """
    # 检查运行时覆写
    if _override.api_key:
        return Anthropic(
            api_key=_override.api_key,
            base_url=_override.base_url or "https://api.deepseek.com/anthropic",
        )

    backend = backend or _BACKEND
    if backend == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("未设置 DEEPSEEK_API_KEY 环境变量")
        return Anthropic(api_key=api_key, base_url="https://api.deepseek.com/anthropic")

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


def _effective_model(model: str | None = None) -> str:
    """返回实际使用的模型名：运行时覆写 > 显式传参 > 模块默认"""
    return _override.model or model or _MODEL


def chat_json(
    system: str,
    user: str,
    model: str | None = None,
    backend: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> dict:
    """发送 chat 请求并返回 JSON 解析结果。model 优先级：覆写 > 传参 > 默认。"""
    client = get_client(backend)
    resp = client.messages.create(
        model=_effective_model(model),
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
    model: str | None = None,
    backend: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> str:
    """发送 chat 请求并返回纯文本"""
    client = get_client(backend)
    resp = client.messages.create(
        model=_effective_model(model),
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return _get_text(resp)
