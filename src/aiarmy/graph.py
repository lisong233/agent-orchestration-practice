"""
LangGraph 编排 — 3 节点管线
[parse] → DocFields → [match] → Verdict[] → [judge] → FinalResult

v4: 支持 doc_type_override（评委 UI 选择类型，覆盖自动检测）；审计日志落盘。
"""
import asyncio
from dataclasses import dataclass, field
from typing import Optional

from src.aiarmy.schemas import DocFields, RuleVerdict, FinalResult, DocType


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
    """审核管线 — 3 节点顺序调用。"""

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm

    async def run(self, raw_text: str, intent: str = "综合评审",
                  verbose: bool = True, doc_type_override: str | None = None) -> PipelineState:
        """执行完整审核管线。
        doc_type_override: 评委 UI 选择的类型，覆盖自动检测（None=自动检测，用于 backtest/CLI）。
        """
        state = PipelineState(raw_text=raw_text, intent=intent)

        def log(msg):
            if verbose:
                print(f"  {msg}")

        try:
            # 节点1：解析
            log(f"[parse] 解析文档 ({len(raw_text)}字符)...")
            state.fields = await self._parse(raw_text, intent, doc_type_override=doc_type_override)
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

        # 审计日志落盘（v4：部署后唯一观测窗口）
        try:
            from src.aiarmy.audit_log import log_run
            log_run({
                "doc_type": state.doc_type.value if state.doc_type else "未知",
                "title": state.fields.title if state.fields else "",
                "intent": state.intent,
                "verdicts": [
                    {"rule_id": v.rule_id, "passed": v.passed, "confidence": v.confidence}
                    for v in state.verdicts
                ],
                "label": state.result.label if state.result else "错误",
                "reason": state.result.reason if state.result else "",
                "use_llm": self.use_llm,
                "error": state.error,
            })
        except Exception:
            pass  # 日志写入失败不影响主流程

        return state

    async def _parse(self, raw_text: str, intent: str,
                     doc_type_override: str | None = None) -> DocFields:
        from src.aiarmy.agents.parse import run
        return await run(raw_text, intent, use_llm=self.use_llm,
                         doc_type_override=doc_type_override)

    async def _match(self, fields: DocFields, intent: str) -> list[RuleVerdict]:
        from src.aiarmy.agents.match import run
        return await run(fields, intent, use_llm=self.use_llm)

    async def _judge(self, verdicts: list[RuleVerdict], title: str,
                     intent: str) -> FinalResult:
        from src.aiarmy.agents.judge import run
        return await run(verdicts, title, intent, use_llm=self.use_llm)


def run_sync(raw_text: str, intent: str = "综合评审", use_llm: bool = True,
             doc_type_override: str | None = None) -> PipelineState:
    """同步入口 — 方便调试和 Gradio 调用"""
    pipeline = AuditPipeline(use_llm=use_llm)
    return asyncio.run(pipeline.run(raw_text, intent, doc_type_override=doc_type_override))
