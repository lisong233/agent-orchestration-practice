"""
LangGraph 编排 — 5 节点管线含 critic 回环（v5）
[sanitize] → [parse] → [match] → [judge] → [critic] ⇄ [match]
                                              ↓ END

StateGraph 节点连边，state 用 schemas.PipelineState (Pydantic)。
节点函数为 agent run() 的薄包装——业务逻辑零改动。
"""
import asyncio
from typing import Optional

from langgraph.graph import StateGraph, END

from src.aiarmy.schemas import PipelineState, DocFields, RuleVerdict, FinalResult


# ── 节点函数：agent run() 的薄包装 ──

async def _sanitize_node(state: PipelineState) -> dict:
    """节点0：输入净化 — M2 抗注入（v5 新增）"""
    from src.aiarmy.sanitize import sanitize
    clean = sanitize(state.raw_text)
    if state.verbose and clean != state.raw_text:
        print(f"  [sanitize] ⚠️ 检测到疑似注入模式，已标记")
    return {"raw_text": clean}


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
    """节点2：规则匹配 → RuleVerdict[]
    v5: 若 critic_feedback 非空 → 定向重评点名规则，其余复用上轮结果。
    """
    from src.aiarmy.agents.match import run, load_rules, quick_check, _eval_content_quality, _eval_r07_multidim
    from src.aiarmy.llm import chat_json
    from src.aiarmy.schemas import RuleVerdict

    feedback = state.critic_feedback
    if feedback and state.verdicts:
        # 定向重评：只重跑 critic 反馈中点名的规则
        if state.verbose:
            print(f"  [match] 🔄 critic 反馈：{feedback}，定向重评...")
        # 解析反馈中提到的 rule_id
        import re
        mentioned = set(re.findall(r'(R-\d{2})', feedback))
        new_verdicts = []
        for v in state.verdicts:
            if v.rule_id in mentioned:
                # 定向重评这条规则
                rules = load_rules(state.fields.doc_type.value)
                rule = next((r for r in rules if r["rule_id"] == v.rule_id), None)
                if rule:
                    result = quick_check(rule, state.fields.raw_excerpt)
                    if result is None and state.use_llm:
                        try:
                            if rule["rule_id"] == "R-07":
                                result = _eval_r07_multidim(state.fields, rule)
                            elif rule["rule_id"] == "R-03":
                                result = _eval_content_quality(
                                    "R-03", rule, state.fields,
                                    dim1_name="技术方法具体性",
                                    dim1_desc="是否描述了具体的技术方法/原理/实验设计？有无个性化内容不可套用于其他项目？",
                                    dim2_name="创新点深度",
                                    dim2_desc="创新点是实质性方法论还是空泛概念罗列？",
                                )
                            elif rule["rule_id"] == "R-04":
                                result = _eval_content_quality(
                                    "R-04", rule, state.fields,
                                    dim1_name="预算分项完整性",
                                    dim1_desc="是否分项到具体科目（材料费/测试费/差旅费/知识产权等）？",
                                    dim2_name="金额合理性",
                                    dim2_desc="各分项金额是否与项目规模匹配？有无计算依据？",
                                )
                        except Exception:
                            pass
                    if result is not None:
                        new_verdicts.append(result)
                        continue
                # 无法重评 → 保留原 verdict
                new_verdicts.append(v)
            else:
                new_verdicts.append(v)
        revision = state.revision_count + 1
        verdicts = new_verdicts
    else:
        # 首次 match：全量评估
        verdicts = await run(state.fields, state.intent, use_llm=state.use_llm)
        revision = state.revision_count

    passed = sum(1 for v in verdicts if v.passed)
    if state.verbose:
        tag = " (重评)" if feedback else ""
        log = f"  [match{tag}] {passed}/{len(verdicts)} 规则通过"
        if passed < len(verdicts):
            log += f" | 失败: {', '.join(v.rule_id for v in verdicts if not v.passed)}"
        else:
            log += " ✅"
        print(log)
    return {"verdicts": verdicts, "revision_count": revision}


async def _judge_node(state: PipelineState) -> dict:
    """节点3：汇总裁决 → FinalResult"""
    from src.aiarmy.agents.judge import run
    result = await run(state.verdicts, state.fields.title, state.intent,
                       use_llm=state.use_llm)
    if state.verbose:
        print(f"  [judge] → {result.label} | {result.reason[:60]}...")
    return {"result": result}


async def _critic_node(state: PipelineState) -> dict:
    """节点4：质量门 — 确定性 evidence 检查（v5 新增）"""
    from src.aiarmy.agents.critic import run
    result = await run(state)
    if state.verbose:
        ok = result.get("critic_ok", True)
        fb = result.get("critic_feedback", "")
        if ok:
            print(f"  [critic] ✅ 质量门通过")
        else:
            print(f"  [critic] ⚠️ 需重评：{fb[:80]}...")
    return result


# ── 条件路由 ──

def _need_revision(state: PipelineState) -> str:
    """critic 后路由：ok→END，不ok+未超上限→revise match"""
    if state.critic_ok or state.revision_count >= 1:
        return "end"
    return "revise"


# ── 构建 StateGraph ──

def _build_graph() -> StateGraph:
    """构建 5 节点管线含 critic 回环（单例，所有 AuditPipeline 实例共用）"""
    builder = StateGraph(PipelineState)
    builder.add_node("sanitize", _sanitize_node)
    builder.add_node("parse", _parse_node)
    builder.add_node("match", _match_node)
    builder.add_node("judge", _judge_node)
    builder.add_node("critic", _critic_node)
    builder.set_entry_point("sanitize")
    builder.add_edge("sanitize", "parse")
    builder.add_edge("parse", "match")
    builder.add_edge("match", "judge")
    builder.add_edge("judge", "critic")
    builder.add_conditional_edges(
        "critic", _need_revision,
        {"revise": "match", "end": END}
    )
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
            print(f"  [sanitize] 净化输入...")

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
                "form_notes": final.result.form_notes if final.result else "",
                "use_llm": self.use_llm,
                "revision_count": final.revision_count,
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
