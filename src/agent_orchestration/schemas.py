"""
数据契约 — Agent 间 spec-handoff 的结构化接口。
所有 Agent 输入/输出均遵循此契约，确保节点间松耦合。
"""
from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import Enum


class DocType(str, Enum):
    计划任务书 = "计划任务书"
    立项申请书 = "立项申请书"


class DocFields(BaseModel):
    """节点1 parse 输出：解析+compact 后的结构化文档"""
    doc_type: DocType
    title: str
    summary: str = Field(description="100字以内的项目核心内容摘要")
    fields: dict = Field(description="关键字段：团队成员/创新点/预算明细/量化指标/内容完整度")
    raw_excerpt: str = Field(description="保留原文片段供证据引用")


class RuleVerdict(BaseModel):
    """节点2 match 输出：单条规则的评估结果"""
    rule_id: str
    rule_name: str
    passed: bool
    evidence: str = Field(description="引用文档原文")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    tier: Literal["advisory", "conditional", "content"] = "content"
    """规则层级：advisory（A类-永不裁决）/ conditional（B类-regime感知）/ content（C类-主判据）"""


class FinalResult(BaseModel):
    """节点3 judge 输出：最终交付格式"""
    label: Literal["通过", "不通过"]
    matched_rules: list[dict] = Field(description="命中的规则列表")
    reason: str = Field(description="150字以内的最终判断说明")
    form_notes: str = ""
    """形式提示（A/B类规则的附注，与内容判据分离，便于Web分区展示）"""


class PipelineState(BaseModel):
    """LangGraph 管线状态 — Pydantic 模型，StateGraph 节点间流转"""
    raw_text: str = ""
    doc_type: Optional[DocType] = None
    intent: str = "综合评审"
    fields: Optional[DocFields] = None
    verdicts: list[RuleVerdict] = Field(default_factory=list)
    result: Optional[FinalResult] = None
    error: Optional[str] = None
    # 管线控制（非业务字段，节点函数需要访问）
    use_llm: bool = True
    verbose: bool = True
    doc_type_override: Optional[str] = None
    # loop 控制（v5 新增）
    critic_ok: bool = False
    revision_count: int = 0
    critic_feedback: str = ""
