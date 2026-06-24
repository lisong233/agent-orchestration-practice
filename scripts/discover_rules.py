"""
P2 - 规则发现研究循环 (Research Loop)
========================================
对计划任务书类型文档进行语义级内容质量分析，
利用 DeepSeek V4 Flash 的世界知识评估项目实质性。

设计原则：
- 只用于格式规则无法判别的边界案例（计划任务书）
- 立项申请书已被 R01-R04 完美覆盖，不需要 LLM
- 输出结构化 JSON，包含判断依据供人工复核

用法：
  python scripts/discover_rules.py                    # 分析全部计划任务书
  python scripts/discover_rules.py --dry-run           # 仅打印prompt，不调API
  python scripts/discover_rules.py --output rules/     # 分析并生成规则建议
"""
import json, os, sys, argparse
from pathlib import Path
from openai import OpenAI

BASE = Path(__file__).parent.parent
TXT_DIR = BASE / "训练集" / "convert_text"
LABELS_PATH = BASE / "data" / "labels_mapped.json"

SYSTEM_PROMPT = """你是电力行业科技项目评审专家。你的任务是评估一份项目计划任务书的实质质量。

评审维度：
1. 项目是否针对具体的技术问题（而非泛化的研究方向）
2. 技术方案是否有清晰的攻关路径（而非模板套话）
3. KPI指标是否与项目名称在技术领域上自洽（如纯算法项目不应有"装置准确率"指标）
4. 预算是否与项目规模合理匹配

注意：所有计划任务书使用同一模板，所以格式层面的差异（有无缺失章节）不作为判断依据。
你要做的是基于项目名称和摘要，利用你的电力行业知识，判断这个项目是否像一个"真实可立项的工程项目"。

输出格式（严格JSON）：
{
  "project_name": "项目名称",
  "quality_score": 1-5的整数（5=非常实质，1=明显模板填充）,
  "assessment": "150字以内的评审意见",
  "red_flags": ["红旗1", "红旗2"],
  "recommendation": "通过" 或 "不通过"
}"""

USER_PROMPT_TEMPLATE = """请评审以下项目计划任务书：

【项目信息】
项目名称：{project_name}
项目摘要：{summary}

【考核指标（KPI）】
{kpi_text}

【预算】
{budget_text}

请输出JSON格式的评审结果。"""


def extract_project_info(text: str) -> dict:
    """从计划任务书文本中提取关键信息"""
    import re

    info = {"project_name": "", "summary": "", "kpi_text": "", "budget_text": ""}

    # 项目名称 (计划任务书用表格格式: | 项目名称 | xxx |)
    m = re.search(r'\|\s*项目名称\s*\|\s*(.+?)\s*\|', text[:500])
    if not m:
        # fallback: 立项申请书格式
        m = re.search(r'项目名称[：:]\s*(.+?)(?:\||\n|$)', text[:500])
    if m:
        info["project_name"] = m.group(1).strip()

    # 项目摘要
    # 计划任务书: "本项目针对...关键技术问题，拟开展..."
    m = re.search(r'本项目针对(.+?)(?:。|\n)', text)
    if m:
        info["summary"] = "本项目针对" + m.group(1).strip()[:500]
    # fallback: 项目摘要标记
    if not info["summary"]:
        m = re.search(r'[（(]项目摘要[）)]\s*\n(.*?)(?:\n\||\n\|)', text, re.DOTALL)
        if m:
            info["summary"] = m.group(1).strip()[:500]

    # KPI表格
    kpi_start = text.find("考核指标名称")
    if kpi_start >= 0:
        kpi_end = text.find("交付成果", kpi_start)
        if kpi_end < 0:
            kpi_end = text.find("序号", kpi_start + 100)
        info["kpi_text"] = text[kpi_start:kpi_end if kpi_end > 0 else kpi_start+500].strip()

    # 预算
    budget_start = text.find("经费类型")
    if budget_start < 0:
        budget_start = text.find("预算支出科目")
    if budget_start >= 0:
        budget_end = text.find("监理费", budget_start)
        if budget_end < 0:
            budget_end = text.find("承诺书", budget_start)
        if budget_end < 0:
            budget_end = budget_start + 800
        info["budget_text"] = text[budget_start:budget_end].strip()

    return info


def analyze_document(text: str, client: OpenAI = None, dry_run: bool = False) -> dict:
    """对单篇计划任务书做语义分析"""
    info = extract_project_info(text)

    prompt = USER_PROMPT_TEMPLATE.format(
        project_name=info["project_name"] or "（未提取到）",
        summary=info["summary"] or "（未提取到）",
        kpi_text=info["kpi_text"] or "（无KPI表）",
        budget_text=info["budget_text"] or "（无预算表）",
    )

    if dry_run:
        print(f"\n{'='*60}")
        print(f"项目: {info['project_name']}")
        print(f"摘要: {info['summary'][:100]}...")
        print(f"--- PROMPT ---")
        print(prompt[:500])
        return {"project_name": info["project_name"], "quality_score": 0,
                "assessment": "DRY RUN", "red_flags": [], "recommendation": "通过"}

    if client is None:
        return {"project_name": info["project_name"], "quality_score": 3,
                "assessment": "未配置LLM，默认通过", "red_flags": [], "recommendation": "通过"}

    try:
        resp = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=1000,
        )
        result = json.loads(resp.choices[0].message.content)
        return result
    except Exception as e:
        print(f"  ⚠️ LLM调用失败: {e}")
        return {"project_name": info["project_name"], "quality_score": 0,
                "assessment": f"LLM调用失败: {e}", "red_flags": ["API_ERROR"],
                "recommendation": "通过"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="仅打印prompt不调API")
    parser.add_argument("--output", type=str, help="输出规则建议目录")
    args = parser.parse_args()

    # 加载标签
    with open(LABELS_PATH, encoding="utf-8") as f:
        labels = json.load(f)

    # 只分析计划任务书
    taskbook_files = []
    for txt_file in sorted(TXT_DIR.glob("*.txt")):
        with open(txt_file, encoding="utf-8") as f:
            text = f.read()
        if "科技项目计划任务书" in text[:500]:
            taskbook_files.append((txt_file, text))

    print(f"找到 {len(taskbook_files)} 篇计划任务书")

    # 初始化 DeepSeek
    client = None
    if not args.dry_run:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if api_key:
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        else:
            print("⚠️ 未设置 DEEPSEEK_API_KEY 环境变量，将跳过LLM分析")
            print("   export DEEPSEEK_API_KEY=your_key")

    results = []
    for txt_file, text in taskbook_files:
        filename = txt_file.name
        label = labels.get(filename, "???")
        print(f"\n分析: {filename[:50]}... (标签: {label})")

        result = analyze_document(text, client, args.dry_run)
        result["file"] = filename
        result["ground_truth"] = label
        result["predicted"] = result.get("recommendation", "通过")
        result["correct"] = result["predicted"] == label
        results.append(result)

        status = "✓" if result["correct"] else "✗"
        print(f"  {status} 评分={result.get('quality_score','?')}/5 预测={result['predicted']} "
              f"实际={label} | {result.get('assessment','')[:80]}")

    # 统计
    if not args.dry_run:
        correct = sum(1 for r in results if r.get("correct"))
        total = len(results)
        print(f"\n{'='*60}")
        print(f"LLM分析准确率: {correct}/{total} = {correct/total:.1%}" if total else "N/A")

        # 保存详细结果
        out_file = BASE / "data" / "llm_analysis.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"详细结果 → {out_file}")

    print("\n✅ 分析完成")


if __name__ == "__main__":
    main()
