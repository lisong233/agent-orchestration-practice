"""
Gradio Web 界面 — 部署入口
v8: 多文档并发 + 翻页浏览 + 浅色专业主题 + 访问控制
"""
import os
import gradio as gr
import asyncio
import json
import time
from collections import defaultdict

from src.agent_orchestration.graph import run_sync_quiet
from src.agent_orchestration.io import to_text

# ═══════════════════════════════════════
# 访问控制
# ═══════════════════════════════════════

_ACCESS_PASSWORD = "aiarmy2026-review"
# IP 使用计数（重启清零）
_ip_usage = defaultdict(int)
_MAX_FREE_REQUESTS = 1


def _check_access(ip: str | None, password: str) -> str:
    """检查访问权限。返回 "" 表示通过，否则返回错误信息。"""
    if not ip:
        ip = "unknown"
    if password == _ACCESS_PASSWORD:
        return ""
    count = _ip_usage[ip]
    if count >= _MAX_FREE_REQUESTS:
        return f"该 IP 已达免费使用上限（{_MAX_FREE_REQUESTS} 次）。请输入访问密码解锁。"
    return ""


def _record_usage(ip: str | None, password: str):
    """记录一次使用"""
    if not ip:
        ip = "unknown"
    if password != _ACCESS_PASSWORD:
        _ip_usage[ip] += 1

# ═══════════════════════════════════════
# 全局 CSS — 浅色专业主题
# ═══════════════════════════════════════

GLOBAL_CSS = """
:root {
  color-scheme: light;
}
  --bg-page: #f5f5f5;
  --bg-surface: #ffffff;
  --bg-card: #f9fafb;
  --border: #e5e7eb;
  --border-light: #f0f0f0;
  --text-primary: #1a1a2e;
  --text-secondary: #6b7280;
  --text-muted: #9ca3af;
  --accent: #2563eb;
  --accent-hover: #1d4ed8;
  --accent-light: rgba(37, 99, 235, 0.08);
  --pass: #059669;
  --pass-bg: rgba(5, 150, 105, 0.06);
  --fail: #dc2626;
  --fail-bg: rgba(220, 38, 38, 0.05);
  --warn: #d97706;
  --warn-bg: rgba(217, 119, 6, 0.06);
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.06), 0 2px 4px rgba(0,0,0,0.04);
  --radius: 8px;
  --radius-sm: 6px;
  --font-mono: 'Cascadia Code', 'Consolas', 'JetBrains Mono', monospace;
  --font-sans: 'Noto Sans SC', system-ui, -apple-system, sans-serif;
}

* { box-sizing: border-box; }

body, .gradio-container {
  background: var(--bg-page) !important;
  font-family: var(--font-sans) !important;
  color: var(--text-primary) !important;
}

.gradio-container {
  max-width: 1100px !important;
  margin: 0 auto !important;
  padding: 24px 20px !important;
}

/* ── 表单控件 ── */

.gradio-container label, .gradio-container .label-text {
  color: var(--text-primary) !important;
  font-size: 13px !important;
  font-weight: 600 !important;
  margin-bottom: 4px !important;
}

.gradio-container .label-text span {
  color: var(--text-muted) !important;
  font-weight: 400 !important;
  font-size: 11px !important;
}

.gradio-container input[type="radio"] {
  accent-color: var(--accent);
}

.gradio-container .radio-group {
  background: var(--bg-surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important;
  padding: 6px 10px !important;
}

.gradio-container textarea, .gradio-container input[type="text"] {
  background: var(--bg-surface) !important;
  border: 1px solid var(--border) !important;
  color: var(--text-primary) !important;
  border-radius: var(--radius-sm) !important;
  font-family: var(--font-mono) !important;
  font-size: 13px !important;
}

.gradio-container textarea:focus, .gradio-container input[type="text"]:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px var(--accent-light) !important;
  outline: none !important;
}

/* ── 文件上传 ── */
.gradio-container .file-preview {
  background: var(--bg-surface) !important;
  border: 2px dashed var(--border) !important;
  border-radius: var(--radius) !important;
}

.gradio-container .file-preview button {
  background: var(--bg-surface) !important;
  border: 1px solid var(--border) !important;
  color: var(--text-secondary) !important;
}

/* ── 主按钮 ── */
.gradio-container button.primary, .gradio-container .lg.primary {
  background: var(--accent) !important;
  border: none !important;
  color: #fff !important;
  font-weight: 600 !important;
  font-size: 15px !important;
  letter-spacing: 0.02em;
  border-radius: var(--radius) !important;
  padding: 12px 32px !important;
  transition: background 0.15s, box-shadow 0.15s !important;
  box-shadow: var(--shadow) !important;
}

.gradio-container button.primary:hover {
  background: var(--accent-hover) !important;
  box-shadow: var(--shadow-md) !important;
}

/* ── 次要按钮 ── */
.gradio-container button:not(.primary):not(.lg) {
  background: var(--bg-surface) !important;
  border: 1px solid var(--border) !important;
  color: var(--text-primary) !important;
  border-radius: var(--radius-sm) !important;
  font-weight: 500 !important;
  transition: background 0.15s !important;
}

.gradio-container button:not(.primary):not(.lg):hover {
  background: var(--bg-card) !important;
}

/* ── Accordion ── */
.gradio-container .accordion {
  background: var(--bg-surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  margin-top: 12px !important;
  box-shadow: var(--shadow-sm) !important;
}

.gradio-container .accordion > .label-wrap {
  color: var(--text-secondary) !important;
  font-size: 13px !important;
  letter-spacing: 0.02em;
  font-weight: 600 !important;
}

/* ── Code block ── */
.gradio-container .codemirror-wrapper, .gradio-container .code-container {
  background: var(--bg-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important;
  font-family: var(--font-mono) !important;
  font-size: 12px !important;
}

/* ── Checkbox ── */
.gradio-container input[type="checkbox"] {
  accent-color: var(--accent);
}

/* ── 隐藏 footer ── */
footer { display: none !important; }

/* ── 进度动画 ── */
@keyframes pulse-dot {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}
.pulse-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: var(--accent); animation: pulse-dot 1.2s ease-in-out infinite;
  margin: 0 2px;
}
.pulse-dot:nth-child(2) { animation-delay: 0.2s; }
.pulse-dot:nth-child(3) { animation-delay: 0.4s; }

/* ── 强制浅色：无视系统暗色主题（Gradio Svelte wrapper 在 dark 下注 #1f2937）── */
@media (prefers-color-scheme: dark) {
  html, body, .gradio-container, .gradio-container .block,
  .gradio-container .panel, .gradio-container .group,
  .gradio-container .form, .gradio-container .wrap,
  .gradio-container .center, .gradio-container .full,
  .gradio-container main, .gradio-container [class*="svelte"] {
    background: var(--bg-page) !important;
    color: var(--text-primary) !important;
  }
  .gradio-container input, .gradio-container textarea, .gradio-container select {
    background: var(--bg-surface) !important;
    color: var(--text-primary) !important;
    border-color: var(--border) !important;
  }
}
"""


# ═══════════════════════════════════════
# HTML 模板
# ═══════════════════════════════════════

def _build_result_html(file_id: str, dataset_type: str, intent: str,
                       label: str, reason: str, form_notes: str,
                       matched: list[dict], verdicts, elapsed: float,
                       status_icon: str = "") -> str:
    """构建裁决结果卡片（浅色主题）"""

    # ── 裁决牌 ──
    if label == "通过":
        badge_color, badge_bg, badge_icon, badge_text = (
            "var(--pass)", "var(--pass-bg)", "#", "审核通过"
        )
    else:
        badge_color, badge_bg, badge_icon, badge_text = (
            "var(--fail)", "var(--fail-bg)", "#", "审核不通过"
        )

    status_bar = f"""
    <div class="verdict-bar" style="border-left-color:{badge_color};background:{badge_bg};">
      <div class="verdict-icon" style="color:{badge_color};">{badge_icon} {status_icon}</div>
      <div class="verdict-main">
        <div class="verdict-label" style="color:{badge_color};">{badge_text}</div>
        <div class="verdict-meta">
          <span class="meta-tag">{file_id}</span>
          <span class="meta-sep">·</span>
          <span class="meta-tag">{dataset_type}</span>
          <span class="meta-sep">·</span>
          <span class="meta-tag">{intent}</span>
          <span class="meta-sep">·</span>
          <span class="meta-time">{(elapsed * 1000):.0f}ms</span>
        </div>
      </div>
    </div>"""

    # ── 裁决理由 ──
    reason_block = ""
    if reason:
        reason_block = f"""
        <div class="section-card">
          <div class="section-head">
            <span class="section-dot" style="background:var(--accent);"></span>
            裁决理由
          </div>
          <div class="reason-text">{reason}</div>
        </div>"""

    # ── 形式提示 ──
    notes_block = ""
    if form_notes:
        notes_block = f"""
        <div class="section-card" style="border-left:3px solid var(--warn);">
          <div class="section-head">
            <span class="section-dot" style="background:var(--warn);"></span>
            形式提示
          </div>
          <div class="notes-text">{form_notes}</div>
        </div>"""

    # ── 命中规则 ──
    rules_cards = ""
    for r in matched:
        rid = r.get("rule_id", "?")
        rname = r.get("rule_name", "")
        ev = r.get("evidence", "")
        rules_cards += f"""
        <div class="rule-card">
          <div class="rule-card-head">
            <span class="rule-badge">{rid}</span>
            <span class="rule-name">{rname}</span>
          </div>
          <div class="rule-evidence">{ev}</div>
        </div>"""

    matched_block = ""
    if rules_cards:
        matched_block = f"""
        <div class="section-card">
          <div class="section-head">
            <span class="section-dot" style="background:var(--text-muted);"></span>
            命中规则
          </div>
          {rules_cards}
        </div>"""

    # ── 全规则明细表 ──
    rows = ""
    for v in verdicts:
        v_passed = getattr(v, "passed", False)
        v_icon = "✓" if v_passed else "✗"
        v_color = "var(--pass)" if v_passed else "var(--fail)"
        tier = getattr(v, "tier", "content")
        tier_label = {"advisory": "提示", "conditional": "条件", "content": "核心"}.get(tier, "")
        tier_color = {"advisory": "var(--text-muted)", "conditional": "var(--warn)", "content": "var(--accent)"}.get(tier, "#6b7280")
        rows += f"""
        <tr class="verdict-row">
          <td class="td-icon"><span style="color:{v_color};font-weight:700;">{v_icon}</span></td>
          <td class="td-rid"><code>{v.rule_id}</code></td>
          <td class="td-name">{v.rule_name}</td>
          <td class="td-tier"><span style="color:{tier_color};font-size:10px;font-weight:600;">{tier_label}</span></td>
          <td class="td-evidence">{v.evidence[:120]}{'…' if len(v.evidence) > 120 else ''}</td>
          <td class="td-conf">{v.confidence:.0%}</td>
        </tr>"""

    table_block = f"""
    <details class="verdict-details">
      <summary class="details-summary">
        <span class="section-dot" style="background:var(--text-muted);"></span>
        全部评审明细 <span style="color:var(--text-muted);font-weight:400;">（{len(verdicts)} 条规则）</span>
      </summary>
      <table class="verdict-table">
        <thead>
          <tr>
            <th class="th-icon"></th>
            <th class="th-rid">规则</th>
            <th class="th-name">名称</th>
            <th class="th-tier">层级</th>
            <th class="th-evidence">证据</th>
            <th class="th-conf">置信度</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </details>"""

    return f"""
    <style>
      .verdict-bar {{
        display: flex; align-items: center; gap: 16px;
        padding: 20px 24px; border-left: 4px solid;
        border-radius: var(--radius); margin-bottom: 16px;
        background: var(--bg-surface); box-shadow: var(--shadow);
      }}
      .verdict-icon {{ font-size: 28px; line-height: 1; font-weight: 700; }}
      .verdict-label {{ font-size: 20px; font-weight: 700; margin-bottom: 4px; }}
      .verdict-meta {{
        display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
        font-size: 11px; color: var(--text-muted);
      }}
      .meta-tag {{
        background: var(--bg-card); padding: 2px 8px; border-radius: 4px;
        font-family: var(--font-mono); font-size: 11px;
      }}
      .meta-sep {{ color: var(--border); }}
      .meta-time {{ font-family: var(--font-mono); color: var(--text-muted); }}
      .section-card {{
        background: var(--bg-surface); border: 1px solid var(--border);
        border-radius: var(--radius); padding: 18px 22px; margin-bottom: 12px;
        box-shadow: var(--shadow-sm);
      }}
      .section-head {{
        font-size: 12px; font-weight: 700; letter-spacing: 0.04em;
        color: var(--text-secondary); margin-bottom: 12px;
        display: flex; align-items: center; gap: 8px;
      }}
      .section-dot {{ width: 7px; height: 7px; border-radius: 50%; display: inline-block; flex-shrink: 0; }}
      .reason-text {{ font-size: 14px; color: var(--text-primary); line-height: 1.75; }}
      .notes-text {{ font-size: 13px; color: #92400e; line-height: 1.65; }}
      .rule-card {{
        background: var(--bg-card); border: 1px solid var(--border);
        border-radius: var(--radius-sm); padding: 12px 16px; margin-bottom: 8px;
      }}
      .rule-card-head {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
      .rule-badge {{
        background: var(--accent-light); color: var(--accent);
        font-family: var(--font-mono); font-size: 11px; font-weight: 700;
        padding: 3px 8px; border-radius: 4px; letter-spacing: 0.04em;
      }}
      .rule-name {{ font-size: 14px; font-weight: 600; color: var(--text-primary); }}
      .rule-evidence {{ font-size: 13px; color: var(--text-secondary); line-height: 1.65; }}
      .rule-evidence::before {{ content: "📎 "; font-size: 11px; }}
      .verdict-details {{ margin-top: 12px; }}
      .details-summary {{
        cursor: pointer; font-size: 12px; font-weight: 600;
        letter-spacing: 0.04em; color: var(--text-secondary);
        padding: 12px 0; display: flex; align-items: center; gap: 8px;
      }}
      .verdict-table {{
        width: 100%; border-collapse: collapse; font-size: 12px;
        font-family: var(--font-mono);
      }}
      .verdict-table th {{
        text-align: left; padding: 8px 10px; background: var(--bg-card);
        color: var(--text-muted); font-size: 10px; letter-spacing: 0.06em;
        font-weight: 600;
      }}
      .verdict-table td {{
        padding: 7px 10px; border-bottom: 1px solid var(--border-light);
      }}
      .verdict-row:hover {{ background: var(--accent-light); }}
      .td-icon {{ width: 28px; text-align: center; }}
      .td-rid {{ width: 52px; }}
      .td-rid code {{
        background: var(--accent-light); color: var(--accent);
        padding: 2px 6px; border-radius: 3px; font-size: 11px;
      }}
      .td-name {{ color: var(--text-primary); font-weight: 500; }}
      .td-tier {{ width: 50px; }}
      .td-evidence {{ color: var(--text-secondary); max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
      .td-conf {{ width: 55px; text-align: center; color: var(--text-muted); }}
      .th-icon {{ width: 28px; }} .th-rid {{ width: 52px; }} .th-tier {{ width: 50px; }}
      .th-conf {{ width: 55px; text-align: center; }}
    </style>
    {status_bar}
    {reason_block}
    {notes_block}
    {matched_block}
    {table_block}
    """


def _build_empty_html() -> str:
    """首页空白状态"""
    return """
    <div class="empty-state">
      <div class="empty-icon">📋</div>
      <div class="empty-text">上传文档开始审核</div>
      <div class="empty-sub">支持 .docx / .doc / .txt，多文件批量处理</div>
    </div>
    """


def _build_progress_html(done: int, total: int, filenames: list[str]) -> str:
    """处理中进度 HTML"""
    items = ""
    for i, name in enumerate(filenames):
        if i < done:
            icon = '<span style="color:var(--pass);">✓</span>'
            cls = 'progress-item done'
        elif i == done:
            icon = '<span class="pulse-dot"></span><span class="pulse-dot"></span><span class="pulse-dot"></span>'
            cls = 'progress-item active'
        else:
            icon = '<span style="color:var(--border);">○</span>'
            cls = 'progress-item pending'
        items += f'<div class="{cls}">{icon} <span>{name}</span></div>'

    return f"""
    <style>
      .progress-container {{
        background: var(--bg-surface); border: 1px solid var(--border);
        border-radius: var(--radius); padding: 24px;
        box-shadow: var(--shadow);
      }}
      .progress-title {{
        font-size: 15px; font-weight: 600; color: var(--text-primary);
        margin-bottom: 16px; display: flex; align-items: center; gap: 8px;
      }}
      .progress-item {{
        display: flex; align-items: center; gap: 10px;
        padding: 10px 14px; font-size: 13px; font-family: var(--font-mono);
        border-radius: var(--radius-sm);
      }}
      .progress-item.done {{ color: var(--text-secondary); }}
      .progress-item.active {{ color: var(--accent); font-weight: 600; background: var(--accent-light); }}
      .progress-item.pending {{ color: var(--text-muted); }}
    </style>
    <div class="progress-container">
      <div class="progress-title">⏳ 处理中（{done}/{total}）</div>
      {items}
    </div>
    """


def _build_error_html(filename: str, error: str) -> str:
    """单文档处理错误"""
    return f"""
    <div class="error-banner">
      <span class="error-icon">!</span>
      <div>
        <div class="error-title">{filename}</div>
        <div class="error-detail">{error}</div>
      </div>
    </div>
    """


# ═══════════════════════════════════════
# 处理函数
# ═══════════════════════════════════════

def _state_to_result(state, filename: str, file_id: str, dataset_type: str,
                     intent: str, elapsed: float, status_icon: str = "") -> dict:
    """将 PipelineState 转为前端可用的 dict"""
    if state.error:
        return {
            "filename": filename, "file_id": file_id,
            "error": state.error, "label": "错误",
        }
    actual_type = state.doc_type.value if state.doc_type else (dataset_type or "未知")

    # 类型展示
    if dataset_type == "自动检测":
        type_display = f"🔍 {actual_type}"
    else:
        type_display = actual_type
        if actual_type != dataset_type and actual_type != "未知":
            type_display += f"（⚠️ 文档标题指示为「{actual_type}」）"

    label = state.result.label if state.result else "错误"
    reason = state.result.reason if state.result else ""
    form_notes = state.result.form_notes if state.result else ""

    # 匹配规则
    if state.result and state.result.matched_rules:
        if isinstance(state.result.matched_rules[0], dict):
            matched = state.result.matched_rules
        else:
            matched = [{"rule_id": v.rule_id, "rule_name": v.rule_name, "evidence": v.evidence}
                        for v in state.result.matched_rules]
    else:
        matched = []

    # 完整 JSON
    verdicts_data = [
        {"rule_id": v.rule_id, "rule_name": v.rule_name, "passed": v.passed,
         "evidence": v.evidence, "confidence": f"{v.confidence:.0%}"}
        for v in state.verdicts
    ]
    detail_json = json.dumps({
        "id": file_id, "dataset_type": actual_type, "intent": intent,
        "label": label, "matched_rules": matched, "reason": reason,
        "form_notes": form_notes, "verdicts": verdicts_data,
        "elapsed_ms": round(elapsed * 1000),
    }, ensure_ascii=False, indent=2)

    # Markdown 摘要
    md_parts = [f"## {label}", "",
                f"*{file_id} · {type_display} · {intent} · {elapsed * 1000:.0f}ms*",
                "", "---", ""]
    if reason:
        md_parts.append(f"### 裁决理由\n\n{reason}\n")
    if form_notes:
        md_parts.append(f"### 形式提示\n\n{form_notes}\n")
    if matched:
        md_parts.append("### 命中规则\n")
        for r in matched:
            md_parts.append(f"- **{r.get('rule_id')} {r.get('rule_name')}**\n  {r.get('evidence')}\n")

    return {
        "filename": filename, "file_id": file_id,
        "type_display": type_display, "actual_type": actual_type,
        "label": label, "reason": reason, "form_notes": form_notes,
        "matched": matched, "verdicts_raw": state.verdicts,
        "verdicts_data": verdicts_data,
        "elapsed": elapsed, "html": "", "reason_md": "\n".join(md_parts),
        "json_raw": detail_json, "status_icon": status_icon,
    }


async def process_batch(files, dataset_type: str, intent: str, use_llm: bool,
                       api_key: str = "", base_url: str = "", model: str = "",
                       password: str = "", request: gr.Request | None = None):
    """多文档并发处理 → (state_dict, html, page_info, reason_md, json_str, progress_html)
    api_key 可选：评委自定义 LLM 配置（key + url + model 三件套），留空使用 .env 默认。"""
    # 访问控制
    client_ip = request.client.host if request else None
    access_error = _check_access(client_ip, password)
    if access_error:
        error_html = f"""
        <div class="error-banner">
          <span class="error-icon">!</span>
          <div>
            <div class="error-title">访问受限</div>
            <div class="error-detail">{access_error}</div>
          </div>
        </div>"""
        return (
            {"results": [], "page": 0, "dataset_type": "", "intent": ""},
            error_html, "", "", "{}", ""
        )

    if files is None:
        return (
            {"results": [], "page": 0, "dataset_type": "", "intent": ""},
            _build_empty_html(), "", "", "{}", ""
        )

    if not isinstance(files, list):
        files = [files]

    t0 = time.time()
    override = None if dataset_type == "自动检测" else dataset_type
    sem = asyncio.Semaphore(3)

    async def process_one(idx: int, file):
        async with sem:
            try:
                if hasattr(file, 'name'):
                    path = file.name
                else:
                    path = str(file)

                filename = os.path.basename(path)
                file_id = os.path.splitext(filename)[0]

                raw_text = to_text(path)
                if not raw_text.strip():
                    return (idx, {
                        "filename": filename, "file_id": file_id,
                        "error": "文件内容为空", "label": "错误",
                    })

                loop = asyncio.get_running_loop()
                key = api_key.strip() if api_key else None
                url = base_url.strip() if api_key else None
                mdl = model.strip() if api_key else None
                state = await loop.run_in_executor(
                    None, run_sync_quiet, raw_text, intent, use_llm, override, key, url, mdl
                )
                elapsed = time.time() - t0
                result = _state_to_result(
                    state, filename, file_id, dataset_type, intent, elapsed,
                    status_icon=f"#{idx+1}"
                )
                return (idx, result)

            except Exception as e:
                filename = os.path.basename(file.name) if hasattr(file, 'name') else str(file)
                file_id = os.path.splitext(filename)[0]
                return (idx, {
                    "filename": filename, "file_id": file_id,
                    "error": str(e), "label": "错误",
                })

    # 启动所有任务
    tasks = [process_one(i, f) for i, f in enumerate(files)]

    # 逐个收集结果
    results = [None] * len(files)
    for coro in asyncio.as_completed(tasks):
        idx, result = await coro
        results[idx] = result

    # 构建 HTML
    for r in results:
        if r and not r.get("error"):
            r["html"] = _build_result_html(
                r["file_id"], r["type_display"], intent,
                r["label"], r.get("reason", ""), r.get("form_notes", ""),
                r.get("matched", []), r.get("verdicts_raw", []),
                r.get("elapsed", 0), r.get("status_icon", "")
            )
        elif r and r.get("error"):
            r["html"] = _build_error_html(r["filename"], r["error"])
            r["reason_md"] = f"## 错误\n\n{r['error']}"
            r["json_raw"] = json.dumps({"error": r["error"], "file": r["filename"]},
                                       ensure_ascii=False, indent=2)

    # 记录访问
    _record_usage(client_ip, password)

    state = {
        "results": results,
        "page": 0,
        "dataset_type": dataset_type,
        "intent": intent,
        "total_elapsed": time.time() - t0,
    }

    # 渲染第一页
    first = results[0] if results else None
    if first:
        return (
            state,
            first.get("html", _build_empty_html()),
            f"第 1 / {len(results)} 份 · **{first.get('filename', '')}**",
            first.get("reason_md", ""),
            first.get("json_raw", "{}"),
            ""
        )
    else:
        return (
            state,
            '<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-text">没有文件被处理</div></div>',
            "", "", "{}", ""
        )


def render_page(state: dict, direction: int):
    """翻页渲染。direction: -1 prev, +1 next, 0 当前页"""
    if not state or not state.get("results"):
        return state, _build_empty_html(), "", "", "{}"

    results = state["results"]
    if not results:
        return state, _build_empty_html(), "", "", "{}"

    new_page = state.get("page", 0) + direction
    new_page = max(0, min(new_page, len(results) - 1))
    state["page"] = new_page

    r = results[new_page]
    return (
        state,
        r.get("html", _build_empty_html()),
        f"第 {new_page + 1} / {len(results)} 份 · **{r.get('filename', '')}**",
        r.get("reason_md", ""),
        r.get("json_raw", "{}"),
    )


def go_home():
    """返回首页"""
    return (
        {"results": [], "page": 0, "dataset_type": "", "intent": ""},
        _build_empty_html(), "", "", "{}",
        gr.update(visible=True),   # input_col
        gr.update(visible=False),  # result_col
    )


# ═══════════════════════════════════════
# UI 构建
# ═══════════════════════════════════════

def build_ui():
    with gr.Blocks(title="AI 军团 — 电力项目立项审核") as app:
        batch_state = gr.State({"results": [], "page": 0})

        # ── 标题 ──
        gr.HTML("""
        <div style="padding:4px 0 20px 0;display:flex;align-items:center;gap:12px;">
          <div style="width:3px;height:28px;background:var(--accent);border-radius:2px;"></div>
          <div>
            <div style="font-family:var(--font-mono);font-size:20px;font-weight:700;color:var(--text-primary);">
              AI 军团
              <span style="color:var(--accent);font-weight:600;">·</span>
              <span style="font-weight:500;color:var(--text-secondary);">电力项目立项审核系统</span>
            </div>
            <div style="font-family:var(--font-mono);font-size:10px;color:var(--text-muted);letter-spacing:0.06em;margin-top:2px;">
              MULTI-DOCUMENT REVIEW · META-RULE FRAMEWORK v6
            </div>
          </div>
        </div>
        """)

        # ── 输入区域 ──
        with gr.Column(visible=True) as input_col:
            with gr.Group():
                dataset_type = gr.Radio(
                    choices=["自动检测", "计划任务书", "立项申请书"],
                    label="数据集类型",
                    value="自动检测",
                    info="「自动检测」由系统根据文档标题判定；评委也可手动指定",
                )
                file_input = gr.File(
                    label="上传文档",
                    file_count="multiple",
                    file_types=[".docx", ".doc", ".txt"],
                )
                intent_input = gr.Textbox(
                    label="评审意图",
                    placeholder="综合评审 / 判断创新程度 / 材料完整性审查",
                    value="综合评审",
                )
                access_pwd = gr.Textbox(
                    label="🔑 访问密码",
                    placeholder="输入密码以解锁无限制使用",
                    type="password",
                    info="⚠️ 不输入密码：每 IP 仅限使用 1 次。输入正确密码后无限制。",
                )
                with gr.Accordion("⚙️ API 设置（可选）", open=False):
                    api_key_input = gr.Textbox(
                        label="API Key",
                        placeholder="sk-...（留空使用默认）",
                        type="password",
                    )
                    api_url_input = gr.Textbox(
                        label="Base URL",
                        placeholder="https://api.deepseek.com/anthropic",
                        value="https://api.deepseek.com/anthropic",
                    )
                    with gr.Row():
                        model_preset = gr.Dropdown(
                            label="模型",
                            choices=["deepseek-v4-flash", "deepseek-v4-pro", "自定义..."],
                            value="deepseek-v4-flash",
                            scale=2,
                        )
                        model_custom = gr.Textbox(
                            label="自定义模型名",
                            placeholder="输入模型 ID",
                            visible=False,
                            scale=3,
                        )
                    gr.Markdown("*填入 API Key 后须同时填写 Base URL 和模型；留空则使用服务端默认 DeepSeek 配置*")
                llm_toggle = gr.Checkbox(
                    label="LLM 深度分析",
                    value=True,
                    info="关闭后仅使用规则引擎",
                )
                submit_btn = gr.Button("▶ 开始审核", variant="primary", size="lg")

        # ── 结果区域 ──
        with gr.Column(visible=False) as result_col:
            # 进度/状态
            progress_html = gr.HTML("")

            # 导航
            with gr.Row():
                prev_btn = gr.Button("← 上一份", scale=1)
                page_info = gr.Markdown("", elem_classes=["page-info"], visible=True)
                next_btn = gr.Button("下一份 →", scale=1)

            # 裁决结果卡片
            html_output = gr.HTML()

            with gr.Accordion("裁决摘要", open=True):
                reason_output = gr.Markdown("*等待提交...*")
            with gr.Accordion("完整 JSON", open=False):
                json_output = gr.Code(language="json", label="")

            # 返回按钮
            back_btn = gr.Button("← 返回首页", variant="secondary", size="sm")

        # ── 底部 ──
        gr.HTML("""
        <div style="margin-top:24px;padding-top:12px;border-top:1px solid var(--border);
                    font-family:var(--font-mono);font-size:10px;color:var(--text-muted);
                    display:flex;justify-content:space-between;letter-spacing:0.03em;">
          <span>sanitize → parse → match → judge → critic ⇄ match &nbsp;|&nbsp; 并发 3 · 翻页浏览</span>
          <span>M1 内容优先 &nbsp; M2 数据非指令 &nbsp; M3 必要非充分 &nbsp; M4 regime 感知</span>
        </div>
        """)

        # 空状态和错误样式
        gr.HTML("""
        <style>
          .empty-state {
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            height: 200px; color: var(--text-muted); gap: 8px;
            background: var(--bg-surface); border: 2px dashed var(--border); border-radius: var(--radius);
          }
          .empty-icon { font-size: 36px; opacity: 0.5; }
          .empty-text { font-size: 15px; font-weight: 500; color: var(--text-secondary); }
          .empty-sub { font-size: 12px; opacity: 0.6; }
          .error-banner {
            display: flex; align-items: flex-start; gap: 16px;
            padding: 20px 24px; background: var(--fail-bg);
            border-left: 4px solid var(--fail); border-radius: var(--radius);
            box-shadow: var(--shadow-sm);
          }
          .error-icon {
            width: 32px; height: 32px; background: var(--fail); color: #fff;
            border-radius: 50%; display: flex; align-items: center; justify-content: center;
            font-weight: 800; font-size: 18px; flex-shrink: 0;
          }
          .error-title { font-weight: 700; font-size: 15px; color: var(--fail); margin-bottom: 4px; }
          .error-detail { font-size: 13px; color: var(--text-secondary); font-family: var(--font-mono); }
        </style>
        """)

        # ══ 事件绑定 ══

        # 模型预设切换 → 显示/隐藏自定义输入
        model_preset.change(
            fn=lambda v: gr.update(visible=(v == "自定义...")),
            inputs=[model_preset],
            outputs=[model_custom],
        )

        # 提交（包装函数以支持 gr.Request）
        def submit_handler(f, dt, i, llm, key, url, preset, custom, pwd, request: gr.Request):
            model = custom if preset == "自定义..." else preset
            return asyncio.run(process_batch(f, dt, i, llm, key, url, model, pwd, request))

        submit_btn.click(
            fn=submit_handler,
            inputs=[file_input, dataset_type, intent_input, llm_toggle,
                    api_key_input, api_url_input, model_preset, model_custom,
                    access_pwd],
            outputs=[batch_state, html_output, page_info, reason_output, json_output, progress_html],
        ).then(
            fn=lambda: (gr.update(visible=False), gr.update(visible=True)),
            outputs=[input_col, result_col],
        )

        # 翻页
        prev_btn.click(
            fn=lambda s: render_page(s, -1),
            inputs=[batch_state],
            outputs=[batch_state, html_output, page_info, reason_output, json_output],
        )

        next_btn.click(
            fn=lambda s: render_page(s, +1),
            inputs=[batch_state],
            outputs=[batch_state, html_output, page_info, reason_output, json_output],
        )

        # 返回首页
        back_btn.click(
            fn=go_home,
            outputs=[batch_state, html_output, page_info, reason_output, json_output,
                     input_col, result_col],
        )

    return app


if __name__ == "__main__":
    ui = build_ui()
    ui.launch(
        server_name="0.0.0.0", server_port=7860,
        theme=gr.themes.Soft(),
        css=GLOBAL_CSS,
        head="""
        <script>
        (function() {
            var params = new URLSearchParams(window.location.search);
            if (!params.has('__theme')) {
                params.set('__theme', 'light');
                window.location.search = params.toString();
            }
        })();
        </script>
        """,
    )
