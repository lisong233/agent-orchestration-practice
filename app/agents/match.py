"""
节点2 — 规则匹配 Agent
逐条规则评估文档，输出 RuleVerdict 列表。
支持纯规则引擎（快速）和 LLM 辅助（处理规则引擎无法判断的边界情况）。
"""
import yaml, re, glob
from pathlib import Path
from app.schemas import DocFields, RuleVerdict
from app.llm import chat_json

RULES_DIR = Path(__file__).parent.parent.parent / "rules"

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
        dated = bool(re.search(r'2026年\d{1,2}月\d{1,2}日', text))
        if dated and (dept or tech):
            return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=True,
                              evidence="审批意见含日期", confidence=0.95)
        else:
            return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=False,
                              evidence="审批意见缺失或日期空白", confidence=0.95)

    if rid == "R-02":  # 承诺书签署完整性
        signed = bool(re.search(r'项目负责人[：:]\s*\n?\s*\S{2,}', text, re.DOTALL))
        dated = bool(re.search(r'日期[：:]\s*2026', text))
        if signed and dated:
            return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=True,
                              evidence="承诺书已签署并注明日期", confidence=0.95)
        else:
            reason = "承诺书签名缺失" if not signed else "承诺书日期缺失"
            return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=False,
                              evidence=reason, confidence=0.95)

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

    if rid == "R-07":  # 内容匹配度与实质性
        project_name = ""
        m = re.search(r'\|\s*项目名称\s*\|\s*(.+?)\s*\|', text[:500])
        if not m:
            m = re.search(r'项目名称[：:]\s*(.+?)(?:\n|$)', text[:500])
        if m:
            project_name = m.group(1).strip()

        # 检查KPI是否与项目类型匹配
        kpi_identical = (
            bool(re.search(r'装置准确率.*85%.*88%.*90%', text)) and
            bool(re.search(r'装置响应时间.*500ms.*400ms.*350ms', text))
        )

        # 软件/算法类项目使用了硬件KPI模板
        software_keywords = ['算法', '方法研究', '优化调度', '仿真平台', '负荷预测', '需求响应',
                           '分布式', '状态感知', '智能诊断', '数字孪生', '自愈控制', '自主导航']
        is_software = any(kw in project_name for kw in software_keywords)

        # 泛化项目名称（排除带具体应用领域的）
        generic_keywords = ['方法研究', '调度方法', '仿真平台', '优化调度',
                          '状态感知', '智能诊断', '自愈控制', '预测与需求响应',
                          '核心技术攻关', '关键技术研究与应用']
        is_generic = any(kw in project_name for kw in generic_keywords)

        # 模板摘要
        template_summary = bool(re.search(
            r'本项目针对.+?关键技术问题.*?拟开展核心技术攻关与装置研制', text))

        if is_software and kpi_identical:
            return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=False,
                              evidence=f"软件/算法类项目使用硬件KPI模板: {project_name[:40]}",
                              confidence=0.85)
        if template_summary and is_generic:
            return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=False,
                              evidence=f"项目摘要为模板套话且名称泛化: {project_name[:40]}",
                              confidence=0.75)

        return RuleVerdict(rule_id=rid, rule_name=rule["rule_name"], passed=True,
                          evidence="项目内容有实质描述", confidence=0.6)

    # 需要 LLM 判断
    return None


async def run(fields: DocFields, intent: str = "", use_llm: bool = True) -> list[RuleVerdict]:
    """逐规则评估文档"""
    rules = load_rules(fields.doc_type.value)
    if not rules:
        return []

    # 按 intent 关键词筛选
    selected = []
    for r in rules:
        keywords = r.get("intent_keywords", [])
        if not intent or not keywords or any(kw in intent for kw in keywords):
            selected.append(r)
    if not selected:
        selected = rules  # 兜底：全量

    verdicts = []
    for rule in selected:
        # 先尝试正则快速检查
        result = quick_check(rule, fields.raw_excerpt)

        if result is None and use_llm:
            # 正则无法判断，调 LLM
            try:
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
                # LLM 失败时默认通过
                result = RuleVerdict(
                    rule_id=rule["rule_id"], rule_name=rule["rule_name"],
                    passed=True, evidence="LLM调用失败，默认通过", confidence=0.3
                )

        if result is None:
            # 未启用 LLM 且正则无法判断
            result = RuleVerdict(
                rule_id=rule["rule_id"], rule_name=rule["rule_name"],
                passed=True, evidence="需LLM判断，默认通过", confidence=0.3
            )

        verdicts.append(result)

    return verdicts
