"""
Gradio Web 界面 — 部署入口
工业控制台风格：暗色主题 + 电蓝色数据展示 + 琥珀色警告。

v7: 前端重设计 — Industrial Command Center 美学
"""
import os
import gradio as gr
import asyncio
import json
import time

from src.aiarmy.graph import AuditPipeline
from src.aiarmy.io import to_text

# ═══════════════════════════════════════
# 全局 CSS — 暗色工业控制台
# ═══════════════════════════════════════

GLOBAL_CSS = """
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&family=Noto+Sans+SC:wght@300;500;700&display=swap');

:root {
  --bg-deep: #080c12;
  --bg-panel: #0f1822;
  --bg-card: #141e2b;
  --border: #1e3048;
  --text-primary: #dce6f0;
  --text-secondary: #7b8ea8;
  --text-muted: #4a5f78;
  --accent-blue: #00c8f0;
  --accent-amber: #f0a800;
  --accent-green: #00d878;
  --accent-red: #f0444c;
  --glow-blue: 0 0 18px rgba(0,200,240,0.3);
  --glow-green: 0 0 18px rgba(0,216,120,0.3);
  --glow-red: 0 0 20px rgba(240,68,76,0.4);
  --font-mono: 'JetBrains Mono', 'Cascadia Code', monospace;
  --font-sans: 'Noto Sans SC', system-ui, sans-serif;
}

* { box-sizing: border-box; }

body, .gradio-container {
  background: var(--bg-deep) !important;
  font-family: var(--font-sans) !important;
  color: var(--text-primary) !important;
}

.gradio-container {
  max-width: 1200px !important;
  margin: 0 auto !important;
  padding: 20px 24px !important;
}

/* 输入面板 */
.panel-input {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 24px;
}

.panel-input label, .panel-input .label-text {
  color: var(--text-secondary) !important;
  font-size: 12px !important;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 600 !important;
}

/* Radio buttons */
.gradio-container input[type="radio"] { accent-color: var(--accent-blue); }
.gradio-container .radio-group {
  background: var(--bg-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  padding: 8px 12px !important;
}

/* File upload */
.gradio-container .file-preview {
  background: var(--bg-card) !important;
  border: 2px dashed var(--border) !important;
  border-radius: 8px !important;
}

/* Text input */
.gradio-container textarea, .gradio-container input[type="text"] {
  background: var(--bg-card) !important;
  border: 1px solid var(--border) !important;
  color: var(--text-primary) !important;
  border-radius: 6px !important;
  font-family: var(--font-mono) !important;
  font-size: 13px !important;
}

.gradio-container textarea:focus, .gradio-container input[type="text"]:focus {
  border-color: var(--accent-blue) !important;
  box-shadow: 0 0 0 2px rgba(0,200,240,0.15) !important;
}

/* Primary button */
.gradio-container button.primary, .gradio-container .lg.primary {
  background: linear-gradient(135deg, #0068a0, #0098d0) !important;
  border: 1px solid rgba(0,200,240,0.4) !important;
  color: #fff !important;
  font-weight: 700 !important;
  font-size: 15px !important;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  border-radius: 8px !important;
  padding: 14px 28px !important;
  transition: all 0.2s !important;
  box-shadow: 0 0 24px rgba(0,180,220,0.25) !important;
}

.gradio-container button.primary:hover {
  background: linear-gradient(135deg, #0078b8, #00a8e8) !important;
  box-shadow: 0 0 36px rgba(0,200,240,0.45) !important;
  transform: translateY(-1px);
}

/* Accordion */
.gradio-container .accordion {
  background: var(--bg-panel) !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  margin-top: 12px !important;
}

.gradio-container .accordion > .label-wrap {
  color: var(--text-secondary) !important;
  font-size: 13px !important;
  letter-spacing: 0.04em;
}

/* Code block (JSON) */
.gradio-container .codemirror-wrapper, .gradio-container .code-container {
  background: var(--bg-deep) !important;
  border: 1px solid var(--border) !important;
  border-radius: 6px !important;
  font-family: var(--font-mono) !important;
  font-size: 12px !important;
}

/* Hide footer */
footer { display: none !important; }
"""


# ═══════════════════════════════════════
# HTML 模板 — 裁决结果展示
# ═══════════════════════════════════════

def _build_result_html(file_id: str, dataset_type: str, intent: str,
                       label: str, reason: str, form_notes: str,
                       matched: list[dict], verdicts, elapsed: float) -> str:
    """构建裁决结果的工业控制台 HTML"""

    # ── 裁决牌 ──
    if label == "通过":
        badge_color, badge_bg, badge_glow, badge_icon, badge_text = (
            "#00d878", "rgba(0,216,120,0.08)", "var(--glow-green)", "◆", "审核通过"
        )
        status_bar = f"""
        <div class="verdict-bar" style="border-color:{badge_color};background:{badge_bg};box-shadow:{badge_glow};">
          <div class="verdict-icon" style="color:{badge_color};">{badge_icon}</div>
          <div class="verdict-main">
            <div class="verdict-label" style="color:{badge_color};">{badge_text}</div>
            <div class="verdict-meta">{file_id} &nbsp;·&nbsp; {dataset_type} &nbsp;·&nbsp; {intent} &nbsp;·&nbsp; {(elapsed*1000):.0f}ms</div>
          </div>
        </div>"""
    else:
        badge_color, badge_bg, badge_glow, badge_icon, badge_text = (
            "#f0444c", "rgba(240,68,76,0.08)", "var(--glow-red)", "⬢", "审核不通过"
        )
        status_bar = f"""
        <div class="verdict-bar" style="border-color:{badge_color};background:{badge_bg};box-shadow:{badge_glow};">
          <div class="verdict-icon" style="color:{badge_color};">{badge_icon}</div>
          <div class="verdict-main">
            <div class="verdict-label" style="color:{badge_color};">{badge_text}</div>
            <div class="verdict-meta">{file_id} &nbsp;·&nbsp; {dataset_type} &nbsp;·&nbsp; {intent} &nbsp;·&nbsp; {(elapsed*1000):.0f}ms</div>
          </div>
        </div>"""

    # ── 裁决理由 ──
    reason_block = ""
    if reason:
        reason_block = f"""
        <div class="reason-section">
          <div class="section-head">
            <span class="section-dot" style="background:var(--accent-blue);box-shadow:0 0 8px var(--accent-blue);"></span>
            裁决理由
          </div>
          <div class="reason-text">{reason}</div>
        </div>"""

    # ── 形式提示 ──
    notes_block = ""
    if form_notes:
        notes_block = f"""
        <div class="notes-section">
          <div class="section-head">
            <span class="section-dot" style="background:var(--accent-amber);box-shadow:0 0 8px var(--accent-amber);"></span>
            形式提示
          </div>
          <div class="notes-text">{form_notes}</div>
        </div>"""

    # ── 命中规则卡片 ──
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
        <div class="rules-section">
          <div class="section-head">
            <span class="section-dot" style="background:var(--accent-red);box-shadow:0 0 8px var(--accent-red);"></span>
            命中规则
          </div>
          {rules_cards}
        </div>"""

    # ── 全规则明细表 ──
    rows = ""
    for v in verdicts:
        v_passed = getattr(v, "passed", False)
        v_icon = "◆" if v_passed else "⬢"
        v_color = "var(--accent-green)" if v_passed else "var(--accent-red)"
        tier = getattr(v, "tier", "content")
        tier_badge = {"advisory": "INFO", "conditional": "WARN", "content": "CORE"}.get(tier, "")
        tier_color = {"advisory": "#7b8ea8", "conditional": "#f0a800", "content": "#00c8f0"}.get(tier, "#7b8ea8")
        rows += f"""
        <tr class="verdict-row">
          <td class="td-icon"><span style="color:{v_color};">{v_icon}</span></td>
          <td class="td-rid"><code>{v.rule_id}</code></td>
          <td class="td-name">{v.rule_name}</td>
          <td class="td-tier"><span style="color:{tier_color};font-size:10px;letter-spacing:0.08em;">{tier_badge}</span></td>
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
        display: flex; align-items: center; gap: 18px;
        padding: 22px 28px; border-left: 5px solid;
        border-radius: 8px; margin-bottom: 16px;
        font-family: var(--font-mono);
      }}
      .verdict-icon {{ font-size: 36px; line-height: 1; }}
      .verdict-label {{ font-size: 22px; font-weight: 800; letter-spacing: 0.04em; margin-bottom: 4px; }}
      .verdict-meta {{ font-size: 11px; color: var(--text-muted); letter-spacing: 0.03em; }}
      .section-head {{
        font-size: 12px; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.1em; color: var(--text-secondary);
        margin-bottom: 12px; display: flex; align-items: center; gap: 10px;
      }}
      .section-dot {{ width: 7px; height: 7px; border-radius: 50%; display: inline-block; }}
      .reason-section, .notes-section, .rules-section {{
        background: var(--bg-card); border: 1px solid var(--border);
        border-radius: 8px; padding: 18px 22px; margin-bottom: 12px;
      }}
      .reason-text {{ font-size: 14px; color: #c0d0e0; line-height: 1.75; }}
      .notes-text {{ font-size: 13px; color: #c8a850; line-height: 1.65; }}
      .rule-card {{
        background: var(--bg-panel); border: 1px solid var(--border);
        border-radius: 6px; padding: 14px 18px; margin-bottom: 8px;
      }}
      .rule-card-head {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
      .rule-badge {{
        background: #1a3048; color: var(--accent-blue); font-family: var(--font-mono);
        font-size: 11px; font-weight: 700; padding: 3px 9px; border-radius: 4px;
        letter-spacing: 0.05em; border: 1px solid rgba(0,200,240,0.25);
      }}
      .rule-name {{ font-size: 14px; font-weight: 600; color: var(--text-primary); }}
      .rule-evidence {{ font-size: 13px; color: var(--text-secondary); line-height: 1.65; }}
      .rule-evidence::before {{ content: "📎 "; font-size: 11px; }}
      .verdict-details {{ margin-top: 12px; }}
      .details-summary {{
        cursor: pointer; font-size: 12px; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.1em; color: var(--text-secondary);
        padding: 12px 0; display: flex; align-items: center; gap: 10px;
      }}
      .verdict-table {{
        width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px;
        font-family: var(--font-mono);
      }}
      .verdict-table th {{
        text-align: left; padding: 8px 10px; background: rgba(0,0,0,0.3);
        color: var(--text-muted); font-size: 10px; text-transform: uppercase;
        letter-spacing: 0.08em; font-weight: 600;
      }}
      .verdict-table td {{ padding: 7px 10px; border-bottom: 1px solid rgba(30,48,72,0.5); }}
      .verdict-row:hover {{ background: rgba(0,200,240,0.03); }}
      .td-icon {{ width: 28px; text-align: center; font-size: 14px; }}
      .td-rid {{ width: 52px; }}
      .td-rid code {{
        background: rgba(0,0,0,0.3); color: var(--accent-blue);
        padding: 2px 6px; border-radius: 3px; font-size: 11px;
      }}
      .td-name {{ color: var(--text-primary); font-weight: 500; }}
      .td-tier {{ width: 50px; }}
      .td-evidence {{ color: var(--text-secondary); max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
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


# ═══════════════════════════════════════
# 处理函数
# ═══════════════════════════════════════

async def process_document(file, dataset_type: str, intent: str, use_llm: bool = True):
    """处理上传文档，返回 (html, markdown_summary, json_raw)"""
    t0 = time.time()

    if file is None:
        return (
            '<div class="empty-state"><div class="empty-icon">⬆</div><div>上传文档开始审核</div><div class="empty-sub">支持 .docx / .txt</div></div>',
            "", "{}"
        )

    if hasattr(file, "name"):
        path = file.name
    else:
        path = str(file)

    try:
        raw_text = to_text(path)
    except Exception as e:
        return (
            f'<div class="error-banner"><span class="error-icon">!</span><div><div class="error-title">文件读取失败</div><div class="error-detail">{e}</div></div></div>',
            "", "{}"
        )

    if not raw_text.strip():
        return (
            '<div class="error-banner"><span class="error-icon">!</span><div><div class="error-title">文件内容为空</div><div class="error-detail">请检查文件是否损坏</div></div></div>',
            "", "{}"
        )

    # 类型：自动检测时不传 override，让 parse 自己判定
    override = None if dataset_type == "自动检测" else dataset_type

    pipeline = AuditPipeline(use_llm=use_llm)
    state = await pipeline.run(raw_text, intent, doc_type_override=override)
    elapsed = time.time() - t0

    # 实际使用的类型（自动检测结果）
    actual_type = state.doc_type.value if state.doc_type else (override or "未知")

    if state.error:
        return (
            f'<div class="error-banner"><span class="error-icon">!</span><div><div class="error-title">管线错误</div><div class="error-detail">{state.error}</div></div></div>',
            "", "{}"
        )

    file_id = os.path.splitext(os.path.basename(path))[0]
    label = state.result.label if state.result else "错误"
    reason = state.result.reason if state.result else ""
    form_notes = state.result.form_notes if state.result else ""

    # 类型提示：自动检测 vs 手动选择
    if dataset_type == "自动检测":
        type_display = f"🔍 {actual_type}"
    else:
        type_display = actual_type
        if actual_type != dataset_type:
            type_display += f"（⚠️ 文档标题指示为「{actual_type}」，评委手动选择「{dataset_type}」）"

    # 匹配规则
    if state.result and state.result.matched_rules:
        if isinstance(state.result.matched_rules[0], dict):
            matched = state.result.matched_rules
        else:
            matched = [{"rule_id": v.rule_id, "rule_name": v.rule_name, "evidence": v.evidence}
                        for v in state.result.matched_rules]
    else:
        matched = []

    # HTML 展示
    html = _build_result_html(file_id, type_display, intent, label, reason, form_notes,
                               matched, state.verdicts, elapsed)

    # Markdown 摘要
    md_parts = [f"## {label}", "", f"*{file_id} · {dataset_type} · {intent} · {elapsed*1000:.0f}ms*", "", "---", ""]
    if reason:
        md_parts.append(f"### 裁决理由\n\n{reason}\n")
    if form_notes:
        md_parts.append(f"### 形式提示\n\n{form_notes}\n")
    if matched:
        md_parts.append("### 命中规则\n")
        for r in matched:
            md_parts.append(f"- **{r.get('rule_id')} {r.get('rule_name')}**\n  {r.get('evidence')}\n")
    reason_md = "\n".join(md_parts)

    # 完整 JSON
    verdicts_data = [
        {"rule_id": v.rule_id, "rule_name": v.rule_name, "passed": v.passed,
         "evidence": v.evidence, "confidence": f"{v.confidence:.0%}"}
        for v in state.verdicts
    ]
    detail = {
        "id": file_id, "dataset_type": actual_type, "intent": intent,
        "label": label, "matched_rules": matched, "reason": reason,
        "form_notes": form_notes, "verdicts": verdicts_data,
        "elapsed_ms": round(elapsed * 1000),
    }

    return html, reason_md, json.dumps(detail, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════
# UI 构建
# ═══════════════════════════════════════

def build_ui():
    with gr.Blocks(title="AI 军团 — 电力项目立项审核") as app:

        # ── 标题 ──
        gr.HTML("""
        <div style="padding:8px 0 24px 0;">
          <div style="display:flex;align-items:center;gap:14px;">
            <div style="width:3px;height:36px;background:var(--accent-blue);box-shadow:0 0 12px var(--accent-blue);border-radius:2px;"></div>
            <div>
              <div style="font-family:var(--font-mono);font-size:22px;font-weight:800;color:var(--text-primary);letter-spacing:0.02em;">
                AI 军团
                <span style="color:var(--accent-blue);">·</span>
                <span style="font-weight:400;color:var(--text-secondary);">电力项目立项审核系统</span>
              </div>
              <div style="font-family:var(--font-mono);font-size:10px;color:var(--text-muted);letter-spacing:0.12em;margin-top:2px;">
                INDUSTRIAL COMMAND CENTER &nbsp;v5 — META-RULE FRAMEWORK
              </div>
            </div>
          </div>
        </div>
        """)

        # ── 主布局 ──
        with gr.Row(equal_height=True):
            # 左栏：输入
            with gr.Column(scale=4, min_width=300):
                with gr.Group():
                    dataset_type = gr.Radio(
                        choices=["自动检测", "计划任务书", "立项申请书"],
                        label="数据集类型",
                        value="自动检测",
                        info="「自动检测」由系统根据文档标题判定；评委也可手动指定",
                    )
                    file_input = gr.File(
                        label="上传文档",
                        file_types=[".docx", ".txt"],
                    )
                    intent_input = gr.Textbox(
                        label="评审意图",
                        placeholder="综合评审 / 判断创新程度 / 材料完整性审查",
                        value="综合评审",
                    )
                    llm_toggle = gr.Checkbox(
                        label="LLM 深度分析",
                        value=True,
                        info="关闭后仅使用规则引擎",
                    )
                    submit_btn = gr.Button("▶ 开始审核", variant="primary", size="lg")

            # 右栏：结果
            with gr.Column(scale=7, min_width=480):
                html_output = gr.HTML(
                    value='<div class="empty-state"><div class="empty-icon">⬢</div><div>等待审核</div><div class="empty-sub">上传文档并点击「开始审核」</div></div>'
                )
                with gr.Accordion("裁决摘要", open=True):
                    reason_output = gr.Markdown("*等待提交...*")
                with gr.Accordion("完整 JSON", open=False):
                    json_output = gr.Code(language="json", label="")

        submit_btn.click(
            fn=lambda f, dt, i, llm: asyncio.run(process_document(f, dt, i, llm)),
            inputs=[file_input, dataset_type, intent_input, llm_toggle],
            outputs=[html_output, reason_output, json_output],
        )

        # ── 底部状态栏 ──
        gr.HTML("""
        <div style="margin-top:28px;padding-top:14px;border-top:1px solid var(--border);
                    font-family:var(--font-mono);font-size:10px;color:var(--text-muted);
                    display:flex;justify-content:space-between;letter-spacing:0.04em;">
          <span>sanitize → parse → match → judge → critic ⇄ match</span>
          <span>M1 内容优先 &nbsp; M2 数据非指令 &nbsp; M3 必要非充分 &nbsp; M4 regime 感知</span>
        </div>
        """)

        # 空状态和错误样式
        gr.HTML("""
        <style>
          .empty-state {
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            height: 280px; color: var(--text-muted); gap: 10px;
            background: var(--bg-panel); border: 2px dashed var(--border); border-radius: 10px;
          }
          .empty-icon { font-size: 48px; opacity: 0.3; }
          .empty-sub { font-size: 12px; opacity: 0.5; }
          .error-banner {
            display: flex; align-items: flex-start; gap: 16px;
            padding: 20px 24px; background: rgba(240,68,76,0.08);
            border-left: 4px solid var(--accent-red); border-radius: 6px;
            box-shadow: 0 0 20px rgba(240,68,76,0.15);
          }
          .error-icon {
            width: 32px; height: 32px; background: var(--accent-red); color: #fff;
            border-radius: 50%; display: flex; align-items: center; justify-content: center;
            font-weight: 800; font-size: 18px; flex-shrink: 0;
          }
          .error-title { font-weight: 700; font-size: 15px; color: var(--accent-red); margin-bottom: 4px; }
          .error-detail { font-size: 13px; color: var(--text-secondary); font-family: var(--font-mono); }
        </style>
        """)

    return app


if __name__ == "__main__":
    ui = build_ui()
    ui.launch(server_name="0.0.0.0", server_port=7860, css=GLOBAL_CSS)
