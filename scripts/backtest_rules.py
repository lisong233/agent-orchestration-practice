"""
P2.3 - 规则回测脚本
对训练集逐个应用规则，验证通过/不通过判定准确率。
纯规则引擎版本——不需要LLM，基于关键词和正则匹配。
"""
import json, os, re, yaml
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent.parent
TXT_DIR = BASE / "训练集" / "convert_text"
LABELS_PATH = BASE / "data" / "labels_mapped.json"
RULES_DIR = BASE / "rules"

with open(LABELS_PATH, encoding="utf-8") as f:
    labels = json.load(f)

def load_rules():
    rules = []
    for yaml_file in sorted(RULES_DIR.glob("**/*.yaml")):
        with open(yaml_file, encoding="utf-8") as f:
            r = yaml.safe_load(f)
            r["_file"] = str(yaml_file.relative_to(RULES_DIR))
            rules.append(r)
    return rules

def detect_doc_type(text):
    if "科技项目计划任务书" in text[:500]:
        return "计划任务书"
    if "职工技术创新项目立项申请书" in text[:500]:
        return "立项申请书"
    return "未知"

def apply_rule(rule, text, doc_type):
    """对单文档应用单条规则，返回(通过, 证据)"""
    rid = rule["rule_id"]

    if rid == "R-01":  # 审批签章完整性
        has_dept = bool(re.search(r'申请部门.*?意见[：:]\s*\n?\s*经审核', text, re.DOTALL))
        has_tech = bool(re.search(r'(?:直属单位)?科技管理部门意见[：:]\s*\n?\s*经审核', text, re.DOTALL))
        has_date = bool(re.search(r'2026年\d{1,2}月\d{1,2}日', text))
        if has_date and (has_dept or has_tech):
            return True, "审批意见含日期"
        else:
            return False, "审批意见缺失或日期空白"

    elif rid == "R-02":  # 承诺书签署完整性
        signed = bool(re.search(r'项目负责人[：:]\s*\n?\s*\S{2,}', text, re.DOTALL))
        dated = bool(re.search(r'日期[：:]\s*2026', text))
        if signed and dated:
            return True, "承诺书已签署并注明日期"
        else:
            return False, f"承诺书{'签名缺失' if not signed else '日期缺失' if not dated else '签名和日期均缺失'}"

    elif rid == "R-03":  # 技术方案实质性
        has_tech = bool(re.search(r'(技术原理|项目采用的技术原理)', text))
        has_innovation = bool(re.search(r'(创新点|技术关键点)', text))
        # 检查技术原理是否有分点详述
        tech_details = len(re.findall(r'(?:技术原理|功能).*?(?:\d+[、.])', text, re.DOTALL))
        if has_tech and has_innovation and tech_details >= 1:
            return True, f"技术方案含{tech_details}点详述"
        elif not has_tech and not has_innovation:
            return False, "技术方案章节缺失"
        else:
            return False, f"技术方案不够具体(仅{tech_details}点)"

    elif rid == "R-04":  # 预算编制规范性
        budget_items = re.findall(r'(材料费|测试化验加工费|知识产权事务费|出版印刷).*?(\d+\.?\d*)', text)
        if len(budget_items) >= 2:
            return True, f"预算含{len(budget_items)}个明细科目"
        else:
            return False, "预算明细不足"

    elif rid == "R-05":  # 模板填写规范性
        has_template = bool(re.search(r'(填写说明|删除本提示|请在此处填写)', text))
        if not has_template:
            return True, "无模板残留"
        else:
            return False, "存在模板说明文字残留"

    elif rid == "R-06":  # 团队信息真实性
        numbered = re.findall(r'成员\d+', text)
        if numbered:
            return False, f"存在{len(numbered)}个编号占位符成员"
        return True, "无编号占位符"

    elif rid == "R-07":  # 内容匹配度与实质性
        # 检查KPI是否与项目类型匹配
        project_name = ""
        m = re.search(r'项目名称[：:]\s*(.+?)(?:\||$)', text[:500])
        if m:
            project_name = m.group(1).strip()

        # 检查是否所有KPI都是"装置准确率/响应时间/可用率"模板值
        kpi_identical = (
            bool(re.search(r'装置准确率.*85%.*88%.*90%', text)) and
            bool(re.search(r'装置响应时间.*500ms.*400ms.*350ms', text)) and
            bool(re.search(r'系统可用率.*99\.0%.*99\.5%.*99\.9%', text))
        )

        # 纯软件/算法类项目使用硬件KPI模板 → 内容不匹配
        software_keywords = ['算法', '方法研究', '优化调度', '仿真平台', '负荷预测', '需求响应',
                           '分布式', '状态感知', '智能诊断', '数字孪生', '自愈控制', '自主导航']
        is_software = any(kw in project_name for kw in software_keywords)

        if is_software and kpi_identical:
            return False, f"软件/算法类项目使用硬件KPI模板，项目名={project_name[:30]}"

        # 检查项目摘要: 如果摘要模式完全匹配模板（"针对XX关键技术问题，拟开展核心技术攻关与装置研制"）
        # 且项目名称是泛化的研究方向而非具体装置，判定为模板填充
        template_summary = bool(re.search(r'本项目针对.+?关键技术问题.*?拟开展核心技术攻关与装置研制', text))

        # 泛化项目名称关键词
        generic_keywords = ['方法研究', '技术研究', '调度方法', '仿真平台', '优化调度',
                          '状态感知', '智能诊断', '自愈控制', '预测与需求响应']
        is_generic = any(kw in project_name for kw in generic_keywords)

        if template_summary and is_generic:
            return False, f"项目摘要为模板套话且项目名称泛化: {project_name[:30]}"

        return True, "项目内容有实质描述"

    return True, "规则未实现"


def evaluate_document(text, doc_type, rules):
    """对单文档应用所有适用规则"""
    applicable = [r for r in rules if r["applies_to"] == doc_type]
    verdicts = []
    for rule in applicable:
        passed, evidence = apply_rule(rule, text, doc_type)
        verdicts.append({
            "rule_id": rule["rule_id"],
            "rule_name": rule["rule_name"],
            "passed": passed,
            "evidence": evidence,
            "weight": rule.get("weight", "high")
        })

    # 裁决逻辑
    critical_fails = [v for v in verdicts if not v["passed"] and v["weight"] == "critical"]
    high_fails = [v for v in verdicts if not v["passed"] and v["weight"] == "high"]

    if critical_fails:
        final = "不通过"
        reason = "; ".join(f"{v['rule_id']}: {v['evidence']}" for v in critical_fails)
    elif len(high_fails) >= 2:
        final = "不通过"
        reason = "; ".join(f"{v['rule_id']}: {v['evidence']}" for v in high_fails)
    elif high_fails:
        final = "不通过"
        reason = "; ".join(f"{v['rule_id']}: {v['evidence']}" for v in high_fails)
    else:
        final = "通过"
        reason = "所有规则通过"

    return final, reason, verdicts


# 加载规则
rules = load_rules()
print(f"加载 {len(rules)} 条规则:")
for r in rules:
    print(f"  {r['rule_id']} [{r['applies_to']}] {r['rule_name']} (weight={r.get('weight','high')})")
print()

# 回测
results = []
for txt_file in sorted(TXT_DIR.glob("*.txt")):
    with open(txt_file, encoding="utf-8") as f:
        text = f.read()

    label = labels.get(txt_file.name, "???")
    doc_type = detect_doc_type(text)
    final, reason, verdicts = evaluate_document(text, doc_type, rules)

    correct = "✓" if final == label else "✗"
    results.append({
        "file": txt_file.name,
        "label": label,
        "predicted": final,
        "correct": final == label,
        "doc_type": doc_type,
        "reason": reason,
        "verdicts": verdicts
    })

    failed_rules = [v for v in verdicts if not v["passed"]]
    print(f'{correct} {label:4s} → {final:4s} | {doc_type:6s} | {txt_file.name[:50]:50s} | '
          f'{" / ".join(f["rule_id"] for f in failed_rules) if failed_rules else "全部通过"}')

# 统计
total = len(results)
acc = sum(1 for r in results if r["correct"])
pass_correct = sum(1 for r in results if r["label"] == "通过" and r["correct"])
fail_correct = sum(1 for r in results if r["label"] == "不通过" and r["correct"])
pass_total = sum(1 for r in results if r["label"] == "通过")
fail_total = sum(1 for r in results if r["label"] == "不通过")
false_pos = sum(1 for r in results if r["predicted"] == "通过" and r["label"] == "不通过")
false_neg = sum(1 for r in results if r["predicted"] == "不通过" and r["label"] == "通过")

print(f"\n{'='*60}")
print(f"准确率: {acc}/{total} = {acc/total:.1%}")
print(f"通过召回: {pass_correct}/{pass_total} = {pass_correct/pass_total:.1%}" if pass_total else "通过召回: N/A")
print(f"不通过召回: {fail_correct}/{fail_total} = {fail_correct/fail_total:.1%}" if fail_total else "不通过召回: N/A")
print(f"假阳性(误判通过): {false_pos} | 假阴性(漏判不通过): {false_neg}")

# 按文档类型统计
for dtype in ["立项申请书", "计划任务书"]:
    d_results = [r for r in results if r["doc_type"] == dtype]
    d_acc = sum(1 for r in d_results if r["correct"])
    print(f"\n【{dtype}】准确率: {d_acc}/{len(d_results)} = {d_acc/len(d_results):.1%}")

# 打印错误详情
errors = [r for r in results if not r["correct"]]
if errors:
    print(f"\n=== 预测错误 ({len(errors)}个) ===")
    for r in errors:
        print(f"  {r['label']} → {r['predicted']} | {r['doc_type']} | {r['file'][:50]}")
        print(f"    原因: {r['reason']}")
