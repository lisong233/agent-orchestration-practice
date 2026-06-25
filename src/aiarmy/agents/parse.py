"""
节点1 — 文档解析 Agent
输入：原始文档文本（doc-read 输出的 Markdown）
输出：DocFields（结构化字段 + compact 摘要）
支持 LLM 模式和纯正则模式。
"""
import re
from src.aiarmy.schemas import DocFields, DocType
from src.aiarmy.llm import chat_json

PARSE_SYSTEM = """你是电力行业项目申报材料的信息抽取专家。从文档中抽取结构化字段，
只抽取文档中真实存在的内容，绝不编造。缺失的字段填 null。"""

PARSE_USER = """文档类型：{doc_type}
文档内容（Markdown，含表格）：
{raw_markdown}

请抽取以下字段，输出 JSON：
{{
  "title": "项目名称",
  "summary": "100字以内的项目核心内容摘要",
  "fields": {{
    "团队成员": "成员姓名/职称/分工的概述，注意是否有'成员10'这类占位符",
    "创新点": "技术创新点列表，注意是具体方法论还是空泛套话",
    "预算明细": "预算是否分项到具体科目和金额，还是笼统大数",
    "量化指标": "是否有可量化的KPI（准确率/响应时间等）及具体数值",
    "内容完整度": "文档是否只有封面+承诺书（空模板），还是有完整技术方案"
  }},
  "raw_excerpt": "与上述判断最相关的2-3段文档原文，供后续引用证据"
}}"""


def detect_doc_type(text: str) -> DocType:
    """检测文档类型"""
    if "科技项目计划任务书" in text[:500]:
        return DocType.计划任务书
    if "职工技术创新项目立项申请书" in text[:500]:
        return DocType.立项申请书
    return DocType.立项申请书  # 默认


def quick_extract(text: str, doc_type: DocType) -> DocFields:
    """正则快速提取（不需要LLM）"""
    title = ""
    # 计划任务书表格格式
    m = re.search(r'\|\s*项目名称\s*\|\s*(.+?)\s*\|', text[:500])
    if not m:
        m = re.search(r'项目名称[：:]\s*(.+?)(?:\n|$)', text[:500])
    if m:
        title = m.group(1).strip()

    # 团队成员
    team_info = ""
    team_section = re.search(r'(项目组人员情况|任务分工).{0,500}', text, re.DOTALL)
    if team_section:
        team_info = team_section.group(0)[:300]

    # 创新点
    innovation = ""
    innov_section = re.search(r'(技术关键点及创新点|项目采用的技术原理).{0,800}', text, re.DOTALL)
    if innov_section:
        innovation = innov_section.group(0)[:500]

    # 预算
    budget = ""
    budget_section = re.search(r'(经费|预算支出科目|总经费).{0,600}', text, re.DOTALL)
    if budget_section:
        budget = budget_section.group(0)[:400]

    # 内容完整度
    word_count = len(text)
    has_innovation = "创新点" in text or "技术原理" in text
    has_team = "项目组人员" in text or "任务分工" in text
    has_budget = "经费" in text or "预算" in text
    has_commitment = "承诺书" in text
    completeness = f"正文{word_count}字"
    completeness += f"，{'有' if has_innovation else '无'}创新章节"
    completeness += f"，{'有' if has_team else '无'}团队信息"
    completeness += f"，{'有' if has_budget else '无'}预算"
    completeness += f"，{'有' if has_commitment else '无'}承诺书"

    return DocFields(
        doc_type=doc_type,
        title=title,
        summary=text[100:300].strip() if len(text) > 100 else text[:200],
        fields={
            "团队成员": team_info,
            "创新点": innovation,
            "预算明细": budget,
            "量化指标": "",
            "内容完整度": completeness,
        },
        raw_excerpt=text,  # 保留全文供规则引擎检查
    )


async def run(raw_text: str, intent: str = "", use_llm: bool = True) -> DocFields:
    """执行文档解析"""
    doc_type = detect_doc_type(raw_text)

    # 正则模式：快速，不需要API
    if not use_llm:
        return quick_extract(raw_text, doc_type)

    # LLM 模式：深度结构化
    text = raw_text[:8000]
    for keyword in ["经费", "预算", "万元", "项目组人员"]:
        idx = raw_text.find(keyword, 8000)
        if idx > 0:
            text += "\n...\n" + raw_text[idx:idx+3000]

    try:
        result = chat_json(
            system=PARSE_SYSTEM,
            user=PARSE_USER.format(
                doc_type=doc_type.value,
                raw_markdown=text,
            ),
        )
        # raw_excerpt 必须保留全文供规则引擎检查（审批签章/承诺书在文档末尾）
        # LLM 提取的关键原文存入 fields["关键原文"]
        fields = result.get("fields", {})
        fields["关键原文"] = result.get("raw_excerpt", "")
        return DocFields(
            doc_type=doc_type,
            title=result.get("title", ""),
            summary=result.get("summary", ""),
            fields=fields,
            raw_excerpt=raw_text,  # 全文！规则引擎需要搜索审批签章
        )
    except Exception as e:
        return quick_extract(raw_text, doc_type)
