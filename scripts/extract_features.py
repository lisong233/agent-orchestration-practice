"""
P2 - 全量文档特征提取脚本
从 convert_text/ 中读取全部解析后的txt，提取结构化特征，输出特征矩阵。
用于发现通过/不通过的关键区分维度。
"""
import json, os, re
from pathlib import Path

BASE = Path(__file__).parent.parent
TXT_DIR = BASE / "训练集" / "convert_text"
LABELS_PATH = BASE / "data" / "labels.json"
OUT_PATH = BASE / "data" / "features.json"

with open(LABELS_PATH, encoding="utf-8") as f:
    raw_labels = json.load(f)

# 识别文档类型
def detect_doc_type(text: str) -> str:
    if "科技项目计划任务书" in text[:500]:
        return "计划任务书"
    if "职工技术创新项目立项申请书" in text[:500]:
        return "立项申请书"
    return "未知"

# 提取特征
def extract_features(text: str, filename: str):
    f = {"file": filename, "length": len(text)}

    # 文档类型
    f["doc_type"] = detect_doc_type(text)

    # 团队人数
    team_matches = re.findall(r'\|\s*\d+\s*\|\s*(\S+?)\s*\|', text)
    # 更精确：找"任务分工"附近的表格
    f["team_lines"] = len(re.findall(r'\|\s*\d+\s*\|.*\|.*\|.*\|.*\|.*\|', text))

    # 占位符检测
    placeholder_patterns = [
        r'成员\d+',           # 成员10, 成员11
        r'[刘王李赵孙周吴郑]工', # 刘工, 王工...
        r'[张陈黄林]\w{0,2}工', # 张工...
    ]
    placeholders = []
    for pat in placeholder_patterns:
        matches = re.findall(pat, text)
        placeholders.extend(matches)
    f["placeholder_count"] = len(placeholders)
    f["has_numbered_placeholders"] = bool(re.findall(r'成员\d+', text))
    f["has_surname_placeholders"] = bool(re.findall(r'[刘王李赵孙周吴郑张陈黄林][工]', text))

    # 预算相关
    budget_match = re.search(r'(?:总经费|申请经费总额|总计).*?(\d+\.?\d*)', text)
    f["budget_amount"] = float(budget_match.group(1)) if budget_match else None
    f["budget_has_detail"] = bool(re.search(r'(材料费|测试费|加工费|知识产权)', text))
    f["budget_line_count"] = len(re.findall(r'^\|.*\|.*万元.*\|', text, re.MULTILINE))

    # KPI/量化指标
    f["has_kpi_table"] = bool(re.search(r'考核指标', text))
    kpi_values = re.findall(r'(\d{2,3}\.?\d*)%', text)  # 百分比指标
    f["kpi_percentage_count"] = len(kpi_values)

    # 创新点
    f["innovation_point_count"] = len(re.findall(r'(?:创新点|技术关键点|技术原理)[：:\s]*\d+[、.]', text))
    f["has_innovation_section"] = bool(re.search(r'(技术关键点及创新点|项目采用的技术原理)', text))

    # 审批签章
    f["has_approval_opinion"] = bool(re.search(r'(申请部门.*意见|科技管理部门.*意见).*:', text))
    f["approval_has_date"] = bool(re.search(r'\d{4}.*年.*月.*日', text))
    f["approval_date_count"] = len(re.findall(r'\d{4}年\d{1,2}月\d{1,2}日', text))

    # 承诺书
    f["has_commitment"] = bool(re.search(r'廉洁及科研诚信承诺书', text))
    commitment_signed = re.search(r'项目负责人[：:]\s*(\S+)', text)
    f["commitment_signed"] = bool(commitment_signed and commitment_signed.group(1) not in ['', '：', ':'])
    f["commitment_has_date"] = bool(re.search(r'日期[：:]\s*\d{4}', text))

    # 项目编号
    f["has_project_number"] = bool(re.search(r'项目编号.*\d{4,}', text))

    # 进度安排
    f["has_schedule"] = bool(re.search(r'(工作.*安排.*进度|项目执行期限)', text))

    # 交付成果
    f["has_deliverables"] = bool(re.search(r'(交付成果|预期成果|项目形成的专利)', text))

    # 段落/表格密度
    f["table_row_count"] = len(re.findall(r'^\|.*\|$', text, re.MULTILINE))

    return f


# 构建文件名→标签的映射
label_map = {}
for old_name, label in raw_labels.items():
    # 去掉扩展名，用于模糊匹配
    base = os.path.splitext(old_name)[0]
    label_map[base] = label

# 遍历所有txt文件
features = []
for txt_file in sorted(TXT_DIR.glob("*.txt")):
    with open(txt_file, encoding="utf-8") as f:
        text = f.read()

    base = txt_file.stem
    # 匹配标签
    label = None
    for key, val in label_map.items():
        # 用文件名开头的数字或关键词匹配
        if base.startswith(key.split()[0]) if key[0].isdigit() else (key[:4] in base or base[:4] in key):
            label = val
            break
    if label is None:
        # 更宽松的匹配
        for key, val in label_map.items():
            if any(word in base for word in key.split() if len(word) >= 3):
                label = val
                break

    feat = extract_features(text, txt_file.name)
    feat["label"] = label
    features.append(feat)

# 保存
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(features, f, ensure_ascii=False, indent=2)

# 分组统计
pass_docs = [d for d in features if d["label"] == "通过"]
fail_docs = [d for d in features if d["label"] == "不通过"]

print(f"总计: {len(features)} 篇 (通过 {len(pass_docs)} / 不通过 {len(fail_docs)} / 未知 {len(features)-len(pass_docs)-len(fail_docs)})")
print()

# 数值特征对比
numeric_keys = ["length", "placeholder_count", "budget_amount", "budget_line_count",
                "kpi_percentage_count", "innovation_point_count", "table_row_count",
                "approval_date_count", "team_lines"]
print("=== 数值特征对比 (均值) ===")
print(f"{'特征':<30} {'通过':>10} {'不通过':>10} {'差异':>10}")
for k in numeric_keys:
    p_vals = [d[k] for d in pass_docs if d[k] is not None]
    f_vals = [d[k] for d in fail_docs if d[k] is not None]
    p_avg = sum(p_vals)/len(p_vals) if p_vals else 0
    f_avg = sum(f_vals)/len(f_vals) if f_vals else 0
    diff = p_avg - f_avg
    print(f"{k:<30} {p_avg:>10.1f} {f_avg:>10.1f} {diff:>+10.1f}")

print()
# 布尔特征对比
bool_keys = ["has_numbered_placeholders", "has_surname_placeholders",
             "has_kpi_table", "has_innovation_section", "has_approval_opinion",
             "approval_has_date", "has_commitment", "commitment_signed",
             "commitment_has_date", "has_project_number", "has_schedule",
             "has_deliverables", "budget_has_detail"]
print("=== 布尔特征对比 (占比) ===")
print(f"{'特征':<35} {'通过':>8} {'不通过':>8}")
for k in bool_keys:
    p_ratio = sum(1 for d in pass_docs if d[k]) / len(pass_docs) if pass_docs else 0
    f_ratio = sum(1 for d in fail_docs if d[k]) / len(fail_docs) if fail_docs else 0
    print(f"{k:<35} {p_ratio:>7.1%} {f_ratio:>7.1%}")

print(f"\n✅ 特征提取完成 → {OUT_PATH}")
print(f"\n=== 标签不匹配的文件 ===")
for d in features:
    if d["label"] is None:
        print(f"  ⚠️ {d['file']}")

# 逐文件打印关键特征
print(f"\n=== 逐文件摘要 ===")
for d in sorted(features, key=lambda x: (x["label"] or "未知", x["file"])):
    print(f"{d['label']:4s} | {d['doc_type']:6s} | {d['file'][:50]:50s} | "
          f"size={d['length']:>6d} | placeholder={d['placeholder_count']:>3d} | "
          f"budget={str(d['budget_amount']):>8s} | "
          f"approval={'✓' if d['has_approval_opinion'] else '✗'} | "
          f"commit_signed={'✓' if d['commitment_signed'] else '✗'}")
