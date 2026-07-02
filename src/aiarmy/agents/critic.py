"""
节点4 — 质量门 critic（v5 新增）
对 judge 产出的 matched_rules 做确定性自检，不通过则定向回环。
三项检查全确定性、零额外 LLM 调用。
"""
import re
from src.aiarmy.schemas import PipelineState

# evidence 最低字符数。正则规则的描述性 evidence（"签名缺失"/"模板残留"）
# 通常较短，LLM evidence 会引用原文通常较长。6字以下才视为异常。
MIN_EVIDENCE_LEN = 6


async def run(state: PipelineState) -> dict:
    """
    确定性质量门检查。
    返回 {"critic_ok": bool, "critic_feedback": str}
    - critic_ok=True → 通过，走 END
    - critic_ok=False → 不通过，回 match 定向重评
    """
    if not state.result or not state.result.matched_rules:
        return {"critic_ok": True, "critic_feedback": ""}

    raw_text = state.raw_text or ""
    matched = state.result.matched_rules
    feedback_parts = []

    for i, rule in enumerate(matched):
        if not isinstance(rule, dict):
            continue
        rid = rule.get("rule_id", f"rule-{i}")
        evidence = rule.get("evidence", "")

        # 检查1：evidence 非空且长度达标
        if not evidence or len(evidence.strip()) < MIN_EVIDENCE_LEN:
            feedback_parts.append(f"{rid} evidence过短或为空（'{evidence}'），需引用原文")
            continue

        # 检查2：evidence 关键片段能在 raw_excerpt 中找到（子串匹配）
        # 跳过系统生成的 fallback evidence：
        # LLM 调用失败/无LLM回退的兜底消息不含原文引用，跳过文本匹配
        system_msgs = ["需LLM判断", "LLM调用失败", "安全侧从严", "LLM返回无法解析",
                       "LLM返回缺少有效", "规则加载异常"]
        is_system_fallback = any(msg in evidence for msg in system_msgs)
        if not is_system_fallback:
            # 取 evidence 中最长的中文片段来匹配（至少8字，跳过短描述性 evidence）
            fragments = re.findall(r'[一-鿿\d]{8,}', evidence)
            found = False
            for frag in fragments:
                if frag in raw_text:
                    found = True
                    break
            # 允许 evidence 中没有长中文片段（如纯数字/英文 evidence）
            if fragments and not found:
                feedback_parts.append(
                    f"{rid} evidence中的关键片段未在原文中找到，可能为编造"
                )

    if feedback_parts:
        feedback = "；".join(feedback_parts)
        return {
            "critic_ok": False,
            "critic_feedback": feedback,
        }

    return {"critic_ok": True, "critic_feedback": ""}
