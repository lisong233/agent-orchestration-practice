"""
Gradio Web 界面 — 部署入口
提供 选类型/上传文档/输 intent/运行 四个控件，输出 JSON 结果。

v4: 类型选择由评委 UI 控制（不再靠系统猜），输出格式对齐题目 JSON 范例。
"""
import os
import gradio as gr
import asyncio

from src.aiarmy.graph import AuditPipeline
from src.aiarmy.io import to_text


async def process_document(file, dataset_type: str, intent: str, use_llm: bool = True):
    """处理上传的文档。dataset_type 来自评委 UI 选择。"""
    if file is None:
        return {"error": "请先上传文档"}

    # 获取文件路径
    if hasattr(file, "name"):
        path = file.name
    else:
        path = str(file)

    # 通过 io 层读取（自动处理 .docx/.doc/.pdf/.txt）
    try:
        raw_text = to_text(path)
    except Exception as e:
        return {"error": f"文件读取失败: {e}"}

    if not raw_text.strip():
        return {"error": "文件内容为空"}

    # 运行管线（类型由评委选择，覆盖自动检测）
    pipeline = AuditPipeline(use_llm=use_llm)
    state = await pipeline.run(raw_text, intent, doc_type_override=dataset_type)

    if state.error:
        return {"error": str(state.error)}

    # 输出格式对齐题目 JSON 范例
    file_id = os.path.splitext(os.path.basename(path))[0]
    # matched_rules 每项含 rule_id/rule_name/evidence（题目要求）
    matched_rules = [
        {
            "rule_id": v.rule_id,
            "rule_name": v.rule_name,
            "evidence": v.evidence,
        }
        for v in state.result.matched_rules
    ] if state.result else []
    # 如果 matched_rules 是 dict 列表而非 RuleVerdict，兼容两种来源
    if state.result and state.result.matched_rules and isinstance(state.result.matched_rules[0], dict):
        matched_rules = [
            {"rule_id": r.get("rule_id", ""), "rule_name": r.get("rule_name", ""), "evidence": r.get("evidence", "")}
            for r in state.result.matched_rules
        ]

    output = {
        "id": file_id,
        "dataset_type": dataset_type,
        "intent": state.intent,
        "label": state.result.label if state.result else "错误",
        "matched_rules": matched_rules,
        "reason": state.result.reason if state.result else "",
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

    # gr.JSON 期望 dict，不是 json.dumps 字符串
    return output


def build_ui():
    """构建 Gradio 界面"""
    with gr.Blocks(title="AI 军团 — 项目审核系统") as app:
        gr.Markdown("""
        # 🏛️ AI 军团 — 电力项目立项审核系统
        上传项目申报文档（.docx / .txt），选择数据集类型，输入评审意图，自动输出审核结果。
        """)

        with gr.Row():
            with gr.Column(scale=1):
                dataset_type = gr.Radio(
                    choices=["计划任务书", "立项申请书"],
                    label="数据集类型（评委选择）",
                    value="立项申请书",
                )
                file_input = gr.File(
                    label="上传文档（.docx）",
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
            fn=lambda f, dt, i, llm: asyncio.run(process_document(f, dt, i, llm)),
            inputs=[file_input, dataset_type, intent_input, llm_toggle],
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
