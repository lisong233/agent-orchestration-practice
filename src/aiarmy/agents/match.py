"""
节点2 — 规则匹配 Agent
逐条规则评估文档，输出 RuleVerdict 列表。
支持纯规则引擎（快速）和 LLM 辅助（处理规则引擎无法判断的边界情况）。

方法论（v3）：正则判「结构」，LLM 判「语义」。
- 正则只检查格式硬伤（模板残留、占位符、日期是否填写）——不匹配任何具体数值/年份/项目名。
- LLM 判断需要世界知识的语义维度（内容质量、领域自洽性）。
"""
import yaml, re, glob
from collections import Counter
from pathlib import Path
from src.aiarmy.schemas import DocFields, RuleVerdict
from src.aiarmy.llm import chat_json

RULES_DIR = Path(__file__).parent.parent.parent.parent / "rules"

MATCH_SYSTEM = """你是严格的电力项目评审专家。给定一条审核规则和一份项目材料，
判断该材料是否满足这条规则。判断必须基于材料中的实际内容，
引用原文作为证据。宁可严格，不要放水——大多数申报材料是不达标的。"""

MATCH_USER = """【审核规则】
规则ID：{rule_id}
规则名称：{rule_name}
说明：{description}
通过标准：{criteria_pass}
不通过标准：{criteria_fail}

【待评审材料】
项目：{title}
关键字段：{fields}
原文片段：{raw_excerpt}

请判断该材料是否满足这条规则，输出 JSON：
{{
  "rule_id": "{rule_id}",
  "rule_name": "{rule_name}",
  "passed": true 或 false,
  "evidence": "引用材料中支持你判断的具体原文",
  "confidence": 0.0到1.0之间的数值
}}"""

# ── R-07 多维评分 prompt（v3）──
# 难例（格式合规但内容存疑）需要 LLM 从三个维度独立打分
R07_MULTIDIM_SYSTEM = """你是电力行业科技项目评审专家。你对计划任务书进行多维度的内容质量评估。
每个维度独立打分，基于文档实际内容给出具体依据。严格但不刻薄——有实质内容的给高分，
模板填充的给低分。"""

R07_MULTIDIM_USER = """【待评审材料】
项目名称：{title}
文档关键内容：
{fields}
原文片段（前2000字）：
{raw_excerpt}

请从以下三个维度独立评估，每个维度1-5分：

维度1 — 技术具体性：项目是否针对具体的技术问题，有清晰的攻关路径？
  5分=描述了具体技术方法和预期成果，有个性化内容，不可套用于其他项目
  3分=有一定技术描述但较空泛，可部分套用于同类项目
  1分=仅含模板套话（"针对XX关键技术问题，拟开展核心技术攻关与装置研制"），可完全套用于任何项目

维度2 — KPI领域自洽性：考核指标在技术领域上与项目名称是否匹配？
  5分=KPI指标与项目类型完全匹配，各指标有差异化取值，体现真实规划
  3分=KPI具备一定相关性但部分取值趋同或与项目类型不完全匹配
  1分=KPI与项目类型明显矛盾（如纯软件/算法项目却有"装置准确率/响应时间"等硬件指标），或多个KPI取值完全相同（疑似模板复制）

维度3 — 预算合理性：预算是否与项目规模匹配、有分项明细和计算依据？
  5分=预算分项到具体科目（材料费/测试费/知识产权费等），金额有计算依据，与项目规模匹配
  3分=有预算分项但金额偏整/计算依据不充分/分项过少
  1分=仅有笼统总数，无分项明细，或预算表空白

输出 JSON：
{{
  "technical_specificity": {{"score": 1-5整数, "evidence": "引用文档原文支持你的评分"}},
  "kpi_coherence": {{"score": 1-5整数, "evidence": "引用文档原文支持你的评分"}},
  "budget_reasonableness": {{"score": 1-5整数, "evidence": "引用文档原文支持你的评分"}},
  "overall_assessment": "100字以内的综合评审意见"
}}"""


def load_rules(doc_type: str) -> list[dict]:
    """加载指定文档类型的所有规则"""
    rules = []
    type_dir = RULES_DIR / doc_type
    if not type_dir.exists():
        return rules
    for yaml_file in sorted(type_dir.glob("*.yaml")):
        with open(yaml_file, encoding="utf-8") as f:
            r = yaml.safe_load(f)
            r["_file"] = str(yaml_file.name)
            rules.append(r)
    return rules


def quick_check(rule: dict, text: str) -> RuleVerdict | None:
    """
    正则快速检查——对于格式类规则，不需要调 LLM。
    返回 None 表示需要 LLM 判断。
    """
    rid = rule["rule_id"]

    if rid == "R-01":  # 审批签章完整性
        dept = bool(re.search(r'申请部门.*?意见[：:]\s*\n?\s*经审核', text, re.DOTALL))
        tech = bool(re.search(r'(?:直属单位)?科技管理部门意见[：:]\s*\n?\s*经审核', text, re.DOTALL))
        # 判「日期栏是否填写」，不判「填的是哪年」
        dated = bool(re.search(r'\d{4}年\d{1,2}月\d{1,2}日', text))
        if dated and (dept or tech):
            return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=True,
                              evidence="审批意见含日期", confidence=0.95)
        else:
            return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=False,
                              evidence="审批意见缺失或日期空白", confidence=0.95)

    if rid == "R-02":  # 承诺书签署完整性
        m = re.search(r'项目负责人[：:]\s*\n?\s*(\S{2,})', text, re.DOTALL)
        # 排除占位符词，防止「项目负责人：（签字）」判为已签（v4 spec 任务7）
        placeholder = {"（签字）", "(签字)", "签字", "（盖章）", "(盖章)", "盖章", "姓名", "/"}
        signed = bool(m) and m.group(1).strip() not in placeholder
        # 判「日期栏是否填写」，不判具体年份
        dated = bool(re.search(r'日期[：:]\s*\d{4}', text))
        if signed and dated:
            return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=True,
                              evidence="承诺书已签署并注明日期", confidence=0.95)
        else:
            reason = "承诺书签名缺失" if not signed else "承诺书日期缺失"
            return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=False,
                              evidence=reason, confidence=0.95)

    if rid in ("R-03", "R-04"):
        # 立项申请书 R-03/R-04：补充性规则，核心判断由 R-01/R-02 完成
        # 正则无法判断内容质量→默认通过。LLM 容易过度严格（预算末节），不在此调用。
        return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=True,
                          evidence="格式层面无异常（内容质量由核心规则 R-01/R-02 裁决）",
                          confidence=0.45)

    if rid == "R-05":  # 模板填写规范性
        has_template = bool(re.search(r'(填写说明|删除本提示|请在此处填写)', text))
        if not has_template:
            return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=True,
                              evidence="无模板残留", confidence=0.9)
        else:
            return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=False,
                              evidence="存在模板说明文字残留", confidence=0.95)

    if rid == "R-06":  # 团队信息真实性
        numbered = re.findall(r'成员\d+', text)
        if numbered:
            return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=False,
                              evidence=f"存在{len(numbered)}个编号占位符成员", confidence=0.95)
        return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=True,
                          evidence="无编号占位符", confidence=0.8)

    if rid == "R-07":  # 内容匹配度与实质性 — 正则只判结构异常，其余交LLM
        # 检查1：KPI 自我重复（多个不同指标取值完全相同 → 模板复制粘贴）
        kpi_values = re.findall(r'(?:[≥≥>]?\s*)?(\d+(?:\.\d+)?)\s*%', text)
        if len(kpi_values) >= 3:
            val_counts = Counter(kpi_values)
            repeated = [(v, c) for v, c in val_counts.items() if c >= 3]
            if repeated:
                return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=False,
                    evidence=f"多个考核指标取值完全相同({repeated[0][0]}%)，"
                             f"共{repeated[0][1]}处，疑似模板复制填充",
                    confidence=0.85)

        # 检查2：KPI 数值异常雷同（不同指标但数值都在同一窄区间 → 模板批量生成）
        numeric_kpis = re.findall(r'(?:[≥≥>]?\s*)?(\d+(?:\.\d+)?)\s*%', text)
        if len(numeric_kpis) >= 6:
            # 将所有数值做分布检查：如果超过一半的 KPI 数值完全相同 → 模板填充
            val_counts = Counter(numeric_kpis)
            max_dup = max(val_counts.values())
            if max_dup >= len(numeric_kpis) * 0.5:
                return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=False,
                    evidence=f"{len(numeric_kpis)}个KPI指标中{max_dup}个取值相同，分布异常，疑似模板批量填充",
                    confidence=0.8)

        # 其余内容质量判断需LLM的世界知识，正则无法覆盖
        return None

    # R-03, R-04 不在此处理——quick_check 在上方已返回默认通过
    # 需要 LLM 判断（仅 R-07 计划任务书）
    return None


def _route_by_intent(intent: str, rules: list[dict]) -> list[dict]:
    """
    Intent → 规则子集路由（v3）。
    - 空/泛化意图 → 全部规则
    - 定向意图 → keyword 优先（零成本），无匹配时全部规则兜底
    不硬编码关键词表，靠规则的 intent_keywords 字段自描述。
    """
    if not intent or not intent.strip():
        return rules

    # 泛化意图关键词
    generic_intents = ["综合评审", "全面评审", "全部", "完整审核", "总体"]
    if any(g in intent for g in generic_intents):
        return rules

    # 关键词匹配
    selected = []
    for r in rules:
        keywords = r.get("intent_keywords", [])
        if not keywords:
            selected.append(r)  # 无关键词的规则总是激活
        elif any(kw in intent for kw in keywords):
            selected.append(r)

    # 兜底：如果关键词匹配为零（intent 完全陌生），全量加载
    return selected if selected else rules


async def run(fields: DocFields, intent: str = "", use_llm: bool = True) -> list[RuleVerdict]:
    """逐规则评估文档"""
    rules = load_rules(fields.doc_type.value)
    if not rules:
        return []

    # Intent 路由：只激活相关规则子集
    selected = _route_by_intent(intent, rules)

    verdicts = []
    for rule in selected:
        # 先尝试正则快速检查
        result = quick_check(rule, fields.raw_excerpt)

        if result is None and use_llm:
            try:
                if rule["rule_id"] == "R-07":
                    # R-07: 多维评分（v3）——难例用 Sonnet 做三维独立判断
                    result = _eval_r07_multidim(fields, rule)
                else:
                    # 其他规则：标准单一判断
                    criteria_pass = "; ".join(rule.get("criteria", {}).get("pass", []))
                    criteria_fail = "; ".join(rule.get("criteria", {}).get("fail", []))
                    resp = chat_json(
                        system=MATCH_SYSTEM,
                        user=MATCH_USER.format(
                            rule_id=rule["rule_id"],
                            rule_name=rule["rule_name"],
                            description=rule.get("description", ""),
                            criteria_pass=criteria_pass,
                            criteria_fail=criteria_fail,
                            title=fields.title,
                            fields=fields.fields,
                            raw_excerpt=fields.raw_excerpt[:2000],
                        ),
                    )
                    result = RuleVerdict(
                        rule_id=resp.get("rule_id", rule["rule_id"]),
                        rule_name=resp.get("rule_name", rule["rule_name"]),
                        passed=resp.get("passed", True),
                        evidence=resp.get("evidence", ""),
                        confidence=resp.get("confidence", 0.5),
                    )
            except Exception:
                # LLM 失败时从严判不通过（v4 spec 任务4：少数类是通过，安全侧是不通过）
                result = RuleVerdict(
                    rule_id=rule["rule_id"], rule_name=rule["rule_name"],
                    passed=False, evidence="LLM调用失败，安全侧从严判不通过", confidence=0.5,
                )

        if result is None:
            # 未启用 LLM 且正则无法判断 → 从严
            result = RuleVerdict(
                rule_id=rule["rule_id"], rule_name=rule["rule_name"],
                passed=False, evidence="需LLM判断，安全侧从严判不通过", confidence=0.5,
            )

        verdicts.append(result)

    return verdicts


def _eval_r07_multidim(fields: DocFields, rule: dict) -> RuleVerdict:
    """
    R-07 多维评分（v3）。
    三个维度独立打分：技术具体性 / KPI领域自洽性 / 预算合理性。
    模型由 llm 模块自动选择（DEEPSEEK_API_KEY→V4 Flash，否则→Haiku）。
    """
    field_text = ""
    if isinstance(fields.fields, dict):
        for k, v in fields.fields.items():
            val = str(v)[:300] if v else "（无）"
            field_text += f"【{k}】{val}\n"

    # 构造 R-07 输入：前 2000 字 + 预算段落（若在后部）
    excerpt = fields.raw_excerpt[:2000]
    budget_idx = fields.raw_excerpt.find("经费")
    if budget_idx < 0:
        budget_idx = fields.raw_excerpt.find("预算")
    if budget_idx > 2000:
        excerpt += "\n...\n" + fields.raw_excerpt[budget_idx:budget_idx + 800]

    resp = chat_json(
        system=R07_MULTIDIM_SYSTEM,
        user=R07_MULTIDIM_USER.format(
            title=fields.title,
            fields=field_text,
            raw_excerpt=excerpt,
        ),
        model="deepseek-v4-pro",   # 难例升级强模型（v4 spec 任务3）
        max_tokens=1500,
    )

    # LLM 返回垃圾 JSON → 从严判不通过（v4 spec 任务4）
    if resp.get("_parse_error"):
        return RuleVerdict(
            rule_id="R-07", rule_name=rule["rule_name"], passed=False,
            evidence="LLM返回无法解析，安全侧从严判不通过", confidence=0.5,
        )

    # 解析三维评分
    tech = resp.get("technical_specificity", {})
    kpi = resp.get("kpi_coherence", {})
    budget = resp.get("budget_reasonableness", {})

    s1 = int(tech.get("score", 3))
    s2 = int(kpi.get("score", 3))
    s3 = int(budget.get("score", 3))

    # 综合裁决（v3.1 校准：所有计划任务书共用模板→技术具体性普遍偏低）
    scores = [s1, s2, s3]
    avg_score = sum(scores) / 3
    dim_names = ["技术具体性", "KPI领域自洽性", "预算合理性"]
    low_dims = sum(1 for s in scores if s <= 2)
    very_low = sum(1 for s in scores if s == 1)

    # 裁决：≥2 维得 1 分 或 三维全部 ≤2 → 不通过
    if very_low >= 2:
        bad_dims = [dim_names[i] for i, s in enumerate(scores) if s == 1]
        return RuleVerdict(
            rule_id="R-07", rule_name=rule["rule_name"], passed=False,
            evidence=f"多维严重不达标：{'、'.join(bad_dims)}均仅1/5 | "
                     f"评分 {s1}/{s2}/{s3}",
            confidence=0.85,
        )

    if low_dims == 3:
        return RuleVerdict(
            rule_id="R-07", rule_name=rule["rule_name"], passed=False,
            evidence=f"三维全面偏低（{s1}/{s2}/{s3}），内容质量不足",
            confidence=0.7,
        )

    # 其余 → 通过
    return RuleVerdict(
        rule_id="R-07", rule_name=rule["rule_name"], passed=True,
        evidence=f"评分 {s1}/{s2}/{s3}（均分{avg_score:.1f}/5），无明确不达标信号",
        confidence=0.55,
    )
