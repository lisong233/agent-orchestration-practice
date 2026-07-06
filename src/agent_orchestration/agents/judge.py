"""
节点3 — 综合裁决 Agent
汇总所有规则结果，输出最终硬标签 + 依据。
v5: 内容优先裁决（M1）—— C类（内容）主导label，A类（advisory）永不裁决，
     B类（conditional）内容pass时降级为form_notes。
注：judge 是纯确定性 tier 分层裁决，不调用 LLM（裁决逻辑在代码里，不在 prompt 里）。
"""
from src.agent_orchestration.schemas import RuleVerdict, FinalResult


def _tier(v: RuleVerdict) -> str:
    """读取规则的 tier 层级，默认 content"""
    return getattr(v, 'tier', 'content') or 'content'


async def run(verdicts: list[RuleVerdict], title: str = "", intent: str = "",
              use_llm: bool = True) -> FinalResult:
    """汇总裁决 — v5 内容优先"""

    # 0. 空 verdicts 防护（R04 未落地的修复）
    if not verdicts:
        return FinalResult(
            label="不通过", matched_rules=[],
            reason="规则加载异常/无有效判据，安全侧从严判不通过",
        )

    # 1. 按 tier 分层
    content = [v for v in verdicts if _tier(v) == "content"]
    conditional = [v for v in verdicts if _tier(v) == "conditional"]
    advisory = [v for v in verdicts if _tier(v) == "advisory"]

    # 2. 内容优先裁决（M1）
    content_fail = [v for v in content if not v.passed]
    cond_fail = [v for v in conditional if not v.passed]

    if content_fail:
        # 内容不达标 → 不通过（主导），B类硬伤作佐证
        label = "不通过"
        matched = [
            {"rule_id": v.rule_id, "rule_name": v.rule_name, "evidence": v.evidence}
            for v in (content_fail + cond_fail)
        ]
        reason_parts = [f"{v.rule_id} {v.evidence}" for v in content_fail]
        if cond_fail:
            reason_parts.append(f"另有{len(cond_fail)}项形式硬伤")
        reason = "；".join(reason_parts)
    else:
        # 内容达标 → 通过（M1：B类不反转）
        label = "通过"
        matched = [
            {"rule_id": v.rule_id, "rule_name": v.rule_name, "evidence": v.evidence}
            for v in content
        ]
        reason = "内容实质性审核通过"

    # 3. A类（R-01 审批）+ B类硬伤（内容pass时）→ form_notes
    notes_parts = []
    for v in advisory:
        if not v.passed:
            notes_parts.append(f"审批提示：{v.evidence}")
    if label == "通过":
        for v in cond_fail:
            notes_parts.append(f"形式提示：{v.rule_id} {v.evidence}")
    form_notes = "；".join(notes_parts) if notes_parts else ""

    # 附加 reason 中
    if form_notes:
        reason = reason + "。" + form_notes if reason else form_notes

    return FinalResult(
        label=label,
        matched_rules=matched,
        reason=reason[:200],
        form_notes=form_notes,
    )
