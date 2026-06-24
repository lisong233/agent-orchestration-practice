"""
LangGraph 编排 — 3 节点管线
[parse] → DocFields → [match] → Verdict[] → [judge] → FinalResult
"""
import asyncio
from dataclasses import dataclass, field
from typing import Optional

from app.schemas import DocFields, RuleVerdict, FinalResult, DocType


@dataclass
class PipelineState:
    """管线状态（用 dataclass 而非 TypedDict，Pydantic 兼容更好）"""
    raw_text: str = ""
    doc_type: Optional[DocType] = None
    intent: str = "综合评审"
    fields: Optional[DocFields] = None
    verdicts: list = field(default_factory=list)
    result: Optional[FinalResult] = None
    error: Optional[str] = None


class AuditPipeline:
    """审核管线 — 不使用 LangGraph StateGraph，直接用简单的顺序调用。
    对于 3 节点的线性流程，这个复杂度级别不需要引入 StateGraph 的状态机开销。
    如果需要条件路由（按 doc_type 分流），在 match 节点中处理。
    """

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm

    async def run(self, raw_text: str, intent: str = "综合评审",
                  verbose: bool = True) -> PipelineState:
        """执行完整审核管线"""
        state = PipelineState(raw_text=raw_text, intent=intent)

        def log(msg):
            if verbose:
                print(f"  {msg}")

        try:
            # 节点1：解析
            log(f"[parse] 解析文档 ({len(raw_text)}字符)...")
            state.fields = await self._parse(raw_text, intent)
            state.doc_type = state.fields.doc_type
            log(f"[parse] → {state.doc_type.value} | {state.fields.title[:40] if state.fields.title else '?'}")

            # 节点2：规则匹配
            log(f"[match] 加载规则 ({state.doc_type.value})...")
            state.verdicts = await self._match(state.fields, intent)
            passed = sum(1 for v in state.verdicts if v.passed)
            log(f"[match] {passed}/{len(state.verdicts)} 规则通过" +
                (f" | 失败: {', '.join(v.rule_id for v in state.verdicts if not v.passed)}"
                 if passed < len(state.verdicts) else " ✅"))

            # 节点3：裁决
            log(f"[judge] 汇总裁决...")
            state.result = await self._judge(state.verdicts, state.fields.title, intent)
            log(f"[judge] → {state.result.label} | {state.result.reason[:60]}...")

        except Exception as e:
            state.error = str(e)
            log(f"❌ ERROR: {e}")

        return state

    async def _parse(self, raw_text: str, intent: str) -> DocFields:
        from app.agents.parse import run
        return await run(raw_text, intent, use_llm=self.use_llm)

    async def _match(self, fields: DocFields, intent: str) -> list[RuleVerdict]:
        from app.agents.match import run
        return await run(fields, intent, use_llm=self.use_llm)

    async def _judge(self, verdicts: list[RuleVerdict], title: str,
                     intent: str) -> FinalResult:
        from app.agents.judge import run
        return await run(verdicts, title, intent, use_llm=self.use_llm)


def run_sync(raw_text: str, intent: str = "综合评审", use_llm: bool = True) -> PipelineState:
    """同步入口 — 方便调试和 Gradio 调用"""
    pipeline = AuditPipeline(use_llm=use_llm)
    return asyncio.run(pipeline.run(raw_text, intent))
