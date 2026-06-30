"""
节点3 — 综合裁决 Agent
汇总所有规则结果，输出最终硬标签 + 依据。
裁决逻辑用 prompt 铁律实现，不在 Python 里写复杂算法。
"""
from src.aiarmy.schemas import RuleVerdict, FinalResult
from src.aiarmy.llm import chat_json

JUDGE_SYSTEM = """你是电力项目立项的终审专家。给定一份材料在多条规则上的评审结果，
做出最终"通过/不通过"裁决。

裁决铁律（必须遵守）：
1. 任何一条 confidence≥0.7 的 critical 规则不通过 → 最终"不通过"
2. 若所有规则都通过 → "通过"
3. 存在低置信度（confidence<0.7）的不通过 → 综合权衡，但倾向从严
4. 记住：本领域大多数材料是"不通过"的，通过的是少数高质量材料"""

JUDGE_USER = """项目：{title}
意图：{intent}
各规则评审结果：
{verdicts_json}

请输出最终裁决 JSON：
{{
  "label": "通过" 或 "不通过",
  "matched_rules": [
    {{"rule_id": "...", "rule_name": "...", "evidence": "..."}}
  ],
  "reason": "150字以内的最终判断说明，说清楚为什么通过/不通过"
}}"""


async def run(verdicts: list[RuleVerdict], title: str = "", intent: str = "",
              use_llm: bool = True) -> FinalResult:
    """汇总裁决"""

    # 先做确定性裁决：critical 规则失败 → 直接不通过
    critical_fails = [v for v in verdicts if not v.passed and v.confidence >= 0.7]
    all_passed = all(v.passed for v in verdicts)

    if all_passed:
        # 全部通过
        return FinalResult(
            label="通过",
            matched_rules=[v.model_dump() for v in verdicts],
            reason="所有审核规则均通过",
        )

    if critical_fails:
        # 有高置信度失败 → 不通過，不需要 LLM
        return FinalResult(
            label="不通过",
            matched_rules=[v.model_dump() for v in critical_fails],
            reason="; ".join(f"{v.rule_id} {v.evidence}" for v in critical_fails),
        )

    # 模糊情况 → LLM 综合裁决
    if use_llm:
        try:
            verdicts_json = "\n".join(
                f"- {v.rule_id} {v.rule_name}: {'通过' if v.passed else '不通过'} "
                f"(置信度{v.confidence:.0%}) 证据:{v.evidence}"
                for v in verdicts
            )
            resp = chat_json(
                system=JUDGE_SYSTEM,
                user=JUDGE_USER.format(
                    title=title,
                    intent=intent,
                    verdicts_json=verdicts_json,
                ),
            )
            label = resp.get("label", "不通过")
            # matched_rules 确定性取自 verdicts，不靠 LLM 现编（v4 spec 任务5）
            source = [v for v in verdicts if not v.passed] if label == "不通过" else verdicts
            return FinalResult(
                label=label,
                matched_rules=[
                    {"rule_id": v.rule_id, "rule_name": v.rule_name, "evidence": v.evidence}
                    for v in source
                ],
                reason=resp.get("reason", ""),
            )
        except Exception:
            pass

    # fallback：默认不通过
    return FinalResult(
        label="不通过",
        matched_rules=[v.model_dump() for v in verdicts if not v.passed],
        reason="存在未通过的审核规则，综合判定为不通过",
    )
