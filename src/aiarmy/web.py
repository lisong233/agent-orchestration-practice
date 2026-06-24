"""
Gradio Web 界面 — 部署入口
提供 选类型/上传文档/输 intent/运行 四个控件，输出 JSON 结果。
"""
import gradio as gr
import asyncio

from src.aiarmy.graph import AuditPipeline


async def process_document(file, intent: str, use_llm: bool = True) -> str:
    """处理上传的文档"""
    if file is None:
        return "⚠️ 请先上传文档"

    # 读取文件内容
    if hasattr(file, "name"):
        path = file.name
    else:
        path = str(file)

    with open(path, encoding="utf-8", errors="replace") as f:
        raw_text = f.read()

    if not raw_text.strip():
        return "⚠️ 文件内容为空"

    # 运行管线
    pipeline = AuditPipeline(use_llm=use_llm)
    state = await pipeline.run(raw_text, intent)

    if state.error:
        return f"❌ 处理出错: {state.error}"

    # 格式化输出
    import json
    output = {
        "label": state.result.label,
        "title": state.fields.title if state.fields else "未知",
        "doc_type": state.fields.doc_type.value if state.fields else "未知",
        "intent": state.intent,
        "matched_rules": state.result.matched_rules,
        "reason": state.result.reason,
        "verdicts": [
            {
                "rule_id": v.rule_id,
                "rule_name": v.rule_name,
                "passed": v.passed,
                "evidence": v.evidence,
                "confidence": f"{v.confidence:.0%}",
            }
            for v in state.verdicts
        ] if state.verdicts else [],
    }

    return json.dumps(output, ensure_ascii=False, indent=2)


def build_ui():
    """构建 Gradio 界面"""
    with gr.Blocks(title="AI 军团 — 项目审核系统") as app:
        gr.Markdown("""
        # 🏛️ AI 军团 — 电力项目立项审核系统
        上传项目申报文档（.docx / .txt），输入评审意图，自动输出审核结果。
        """)

        with gr.Row():
            with gr.Column(scale=1):
                file_input = gr.File(
                    label="上传文档",
                    file_types=[".docx", ".txt"],
                )
                intent_input = gr.Textbox(
                    label="评审意图",
                    placeholder="例如：综合评审 / 判断创新程度 / 材料完整性审查",
                    value="综合评审",
                )
                llm_toggle = gr.Checkbox(
                    label="启用 LLM 深度分析",
                    value=True,
                    info="关闭后仅使用规则引擎（更快但覆盖不全）",
                )
                submit_btn = gr.Button("🚀 开始审核", variant="primary")

            with gr.Column(scale=2):
                output = gr.JSON(label="审核结果")

        submit_btn.click(
            fn=lambda f, i, llm: asyncio.run(process_document(f, i, llm)),
            inputs=[file_input, intent_input, llm_toggle],
            outputs=output,
        )

        gr.Markdown("""
        ---
        ### 支持的文档类型
        - **计划任务书**：科技项目计划任务书格式
        - **立项申请书**：职工技术创新项目立项申请书格式
        """)

    return app


if __name__ == "__main__":
    ui = build_ui()
    ui.launch(server_name="0.0.0.0", server_port=7860)
