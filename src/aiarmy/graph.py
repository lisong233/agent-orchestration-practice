"""
LangGraph 编排 — 3 节点管线（v4 迁移）
[parse] → DocFields → [match] → Verdict[] → [judge] → FinalResult

StateGraph 节点连边，state 用 schemas.PipelineState (Pydantic)。
节点函数为 agent run() 的薄包装——业务逻辑零改动。
"""
import asyncio
from typing import Optional

from langgraph.graph import StateGraph

from src.aiarmy.schemas import PipelineState, DocFields, RuleVerdict, FinalResult


# ── 节点函数：agent run() 的薄包装 ──

async def _parse_node(state: PipelineState) -> dict:
    """节点1：文档解析 → DocFields"""
    from src.aiarmy.agents.parse import run
    fields = await run(
        state.raw_text, state.intent,
        use_llm=state.use_llm,
        doc_type_override=state.doc_type_override,
    )
    if state.verbose:
        print(f"  [parse] → {fields.doc_type.value} | {fields.title[:40] if fields.title else '?'}")
    return {"fields": fields, "doc_type": fields.doc_type}


async def _match_node(state: PipelineState) -> dict:
    """节点2：规则匹配 → RuleVerdict[]"""
    from src.aiarmy.agents.match import run
    verdicts = await run(state.fields, state.intent, use_llm=state.use_llm)
    passed = sum(1 for v in verdicts if v.passed)
    if state.verbose:
        log = f"  [match] {passed}/{len(verdicts)} 规则通过"
        if passed < len(verdicts):
            log += f" | 失败: {', '.join(v.rule_id for v in verdicts if not v.passed)}"
        else:
            log += " ✅"
        print(log)
    return {"verdicts": verdicts}


async def _judge_node(state: PipelineState) -> dict:
    """节点3：汇总裁决 → FinalResult"""
    from src.aiarmy.agents.judge import run
    result = await run(state.verdicts, state.fields.title, state.intent,
                       use_llm=state.use_llm)
    if state.verbose:
        print(f"  [judge] → {result.label} | {result.reason[:60]}...")
    return {"result": result}


# ── 构建 StateGraph ──

def _build_graph() -> StateGraph:
    """构建 3 节点线性管线（单例，所有 AuditPipeline 实例共用）"""
    builder = StateGraph(PipelineState)
    builder.add_node("parse", _parse_node)
    builder.add_node("match", _match_node)
    builder.add_node("judge", _judge_node)
    builder.set_entry_point("parse")
    builder.add_edge("parse", "match")
    builder.add_edge("match", "judge")
    return builder.compile()

# 模块级单例 —— 图结构在编译时确定，不需要每次 build
_GRAPH = _build_graph()


class AuditPipeline:
    """审核管线 — 对外接口与迁移前完全兼容。"""

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm

    async def run(self, raw_text: str, intent: str = "综合评审",
                  verbose: bool = True,
                  doc_type_override: str | None = None) -> PipelineState:
        """执行完整审核管线。返回 final PipelineState。"""
        state = PipelineState(
            raw_text=raw_text,
            intent=intent,
            use_llm=self.use_llm,
            verbose=verbose,
            doc_type_override=doc_type_override,
        )

        if verbose:
            print(f"  [parse] 解析文档 ({len(raw_text)}字符)...")

        try:
            result = await _GRAPH.ainvoke(state)
            # ainvoke 返回 dict，需转为 PipelineState
            if isinstance(result, dict):
                final = PipelineState(**result)
            else:
                final = result
        except Exception as e:
            final = PipelineState(
                raw_text=raw_text, intent=intent,
                error=str(e), use_llm=self.use_llm,
            )
            if verbose:
                print(f"  ❌ ERROR: {e}")

        # 审计日志落盘（部署后唯一观测窗口）
        try:
            from src.aiarmy.audit_log import log_run
            log_run({
                "doc_type": final.doc_type.value if final.doc_type else "未知",
                "title": final.fields.title if final.fields else "",
                "intent": final.intent,
                "verdicts": [
                    {"rule_id": v.rule_id, "passed": v.passed, "confidence": v.confidence}
                    for v in final.verdicts
                ],
                "label": final.result.label if final.result else "错误",
                "reason": final.result.reason if final.result else "",
                "use_llm": self.use_llm,
                "error": final.error,
            })
        except Exception:
            pass

        return final


def run_sync(raw_text: str, intent: str = "综合评审", use_llm: bool = True,
             doc_type_override: str | None = None) -> PipelineState:
    """同步入口 — 方便调试和 Gradio 调用"""
    pipeline = AuditPipeline(use_llm=use_llm)
    return asyncio.run(pipeline.run(raw_text, intent,
                                    doc_type_override=doc_type_override))
