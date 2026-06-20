# Agent Orchestration 业务判断系统 — 深度调研报告

> 调研日期：2026-06-20
> 调研范围：Agent 编排框架、规则发现与泛化、不平衡数据处理、技术栈建议、类似系统与最佳实践
> 搜索深度：多轮 advanced search + 多源交叉验证

---

## 目录

1. [Agent 编排框架/模式](#1-agent-编排框架模式)
2. [规则发现与泛化](#2-规则发现与泛化)
3. [不平衡数据处理](#3-不平衡数据处理)
4. [技术栈建议](#4-技术栈建议)
5. [类似系统/最佳实践](#5-类似系统最佳实践)
6. [推荐方案总结](#6-推荐方案总结)

---

## 1. Agent 编排框架/模式

### 1.1 主流框架对比（2026 年现状）

截至 2026 年中，Agent 编排框架已从高速演进期进入成熟收敛期。几乎所有主流框架都在 2026 上半年发布了稳定的 GA 版本。以下是核心框架的深度对比：

#### LangGraph — 生产级编排的事实标准

| 维度 | 评估 |
|------|------|
| **定位** | 有向图模型的状态机式编排框架 |
| **GitHub Stars** | 34.5M 月 PyPI 下载，超越 CrewAI 成为 GitHub 最多星的 Agent 框架 |
| **生产部署** | ~400 家企业部署，含 Klarna（处理 2/3 客服量）、Uber、LinkedIn、JPMorgan |
| **核心优势** | 持久化状态检查点、human-in-the-loop 中断/恢复、时间旅行调试、子图组合、条件路由 |
| **最新版本** | v0.4（2026-04），改进了状态持久化和 HITL 检查点 |
| **记忆系统** | 内建 checkpointing，支持 PostgreSQL/Redis/SQLite 多种后端持久化 |
| **适用场景** | 需要精确控制执行流、合规要求、长时运行工作流、复杂条件分支 |

#### CrewAI — 快速原型首选

| 维度 | 评估 |
|------|------|
| **定位** | 角色（role）驱动的多 Agent 协作框架，团队隐喻 |
| **核心优势** | 上手最快（数小时搭建 demo）、直观的角色分工概念 |
| **主要局限** | 简单任务 token 消耗约 3x 其他框架；状态管理能力有限；层级委托链不可预测 |
| **生产建议** | 适合 content generation、research、analysis 类场景；高 stakes 操作需迁移到 LangGraph |
| **最新动态** | 2026-03 推出企业版，含 observability 和 scheduling 功能 |

#### AutoGen / Microsoft Agent Framework

| 维度 | 评估 |
|------|------|
| **定位** | 对话式多 Agent 框架，GroupChat 模式 |
| **核心优势** | 事件驱动架构（v2 API）、Azure 深度集成、GroupChat 辩论模式 |
| **最新版本** | AutoGen 1.0 GA（2026-02）、Microsoft Agent Framework 1.0 GA（2026-04） |
| **适用场景** | 微软生态体系内、需要 Agent 间多轮对话辩论的场景 |
| **记忆** | 依赖消息列表和对话历史，复杂记忆架构需外部集成 |

#### Dify — 低代码 LLM 应用平台

| 维度 | 评估 |
|------|------|
| **定位** | 开源 LLM 应用开发平台，可视化工作流构建 + RAG 管线 + API 层 |
| **核心能力** | 可视化 Agent 工作流编排、RAG 知识库、模型切换、API 发布 |
| **适合场景** | 非工程团队快速搭建 LLM 应用、原型验证；不适合复杂编排需求 |
| **局限性** | 对复杂条件分支和循环支持有限，灵活度不如 LangGraph |

#### 其他值得关注的框架

| 框架 | 定位 | 特点 |
|------|------|------|
| **OpenAI Agents SDK** | OpenAI 原生 | 2026-03 达生产成熟度，仅支持 OpenAI 模型 |
| **Claude Agent SDK** | Anthropic 原生 | 2026-01 公开可用，Memory 功能 beta，企业采用增长最快 |
| **Google ADK** | Google 生态 | 层级 Agent 树、MCP/A2A 协议支持、内建调试 UI |
| **Mastra** | TypeScript 原生 | 最强 TypeScript SDK、内建 OpenTelemetry 追踪 |
| **Smolagents** | HuggingFace 生态 | 最轻量、Code-Agent 模式减少 30% LLM 调用 |

### 1.2 关键架构模式

#### 基础 Agent 循环

所有 Agent 运行在同一个核心循环上：

```
User Input → LLM 推理 → 工具调用 → 环境反馈 → LLM 推理(更新状态) → ...
```

Anthropic 的定义区分了：
- **Workflow**：编排路径是硬编码的（确定的步骤顺序）
- **Agent**：LLM 动态决定自己的流程和工具使用

对于本次作业，推荐**混合架构**——外层 Workflow 确定步骤，内层 Agent 动态决策。

#### Skill Trigger 模式（渐进式技能加载）

源自 Agent Skills 体系（SKILL.md 规范），是 2026 年最成熟的知识注入模式：

```
Level 1 [始终加载]: name + description (每技能 ~100 tokens)
Level 2 [触发加载]: SKILL.md 完整指令 (<5k tokens)
Level 3 [按需加载]: 引用文件、脚本、参考文档 (不限量)
```

**核心价值**：系统启动时只加载轻量元数据，匹配到具体任务时才注入完整指令。这避免了单次 prompt 过长导致的"注意力稀释"问题。

**对照本次作业**：判断规则可以做成 Skill 集合——每个规则对应一个 SKILL.md，只有被触发时才加载完整判断逻辑。

#### Spec-Handoff 模式（规格书传递）

这是 **"瘦 Agent / 胖平台"** 架构的核心：

```
主 Agent（协调器）
    │  读取 spec.md（任务规格书）
    │
    ├──→ Agent A（按 spec 执行子任务）
    │       输出 → 写回 artifact
    │
    ├──→ Agent B（读取 artifact，按 spec 执行下一步）
    │       输出 → 写回 artifact
    │
    └──→ 评审 Agent（对照 spec 验证最终产出）
```

**核心机制**：Agent 本身是**无状态、临时的**；状态和规格通过文件/数据库传递。这使得 Agent 可替换、可回溯、可审计。

**对照本次作业**：分析过程可用 spec-handoff——读取文档 → 规则匹配 Agent → 综合判断 Agent → 输出格式化的判断依据。

#### Compact Agent 模式

来自 Praetorian 平台的实践：
- 传统 "Monolithic Agent" 有 1200+ 行 prompt body，导致 Attention Dilution
- **解决方案**：Agent 精简为 <150 行的"瘦 Worker"，知识和规则放在外部 Skill/Hook
- 效果：减少注意力稀释，提升准确率，降低上下文消耗

#### Research Loop 模式（研究循环）

Reddit 社区总结的稳定生产架构（3-Agent 最小可行）：

```
Planner Agent → Executor Agent → Reviewer Agent → (循环或结束)
```

- **Planner**：将主问题拆解为子查询（可与 Reviewer 共享模型，不同 system prompt）
- **Executor**：执行搜索/工具调用/文档读取
- **Reviewer**：对照原始需求检查是否有 gap，决定是否循环

实践建议：
- Agent 数量应尽可能少——每多一个 Agent，失败表面就乘倍
- Supervisor 路由是最大失效点——应记录每次路由决策，监控盲区
- Reviewer/Scrutinizer Agent 是最容易发现问题的节点

#### LLM-as-Judge 模式

一个独立的 LLM 审查主 Agent 的输出，返回结构化裁决：

```json
{
  "verdict": "fail",
  "confidence": 0.91,
  "reason": "创新程度描述仅为技术特征罗列，未体现方法论的突破性",
  "suggested_action": "revise"
}
```

**适用原则**：在最可能产生不可逆后果的步骤添加 Judge 检查点。Judge 不应到处使用——没有实际成本的步骤不值得开销。

### 1.3 针对本次作业的模式推荐

综合以上分析，推荐以下架构：

```
┌─────────────────────────────────────────────────────┐
│                   Orchestrator (LangGraph)           │
│                                                      │
│  [1] 文档读取 Agent → 提取结构化字段                   │
│  [2] 规则匹配 Agent → 并行评估所有已知规则              │
│  [3] 规则发现 Agent → 对未覆盖的决策点提出新规则建议     │
│  [4] 综合判断 Agent → LLM-as-Judge 汇总裁决            │
│  [5] 格式化输出 → 硬标签 + 命中规则 + 判断依据           │
│                                                      │
│  状态: LangGraph Checkpoint (PostgreSQL持久化)         │
│  知识: SKILL.md 规则集合 + Vector DB (规则语义检索)     │
└─────────────────────────────────────────────────────┘
```

---

## 2. 规则发现与泛化

### 2.1 MoRE-LLM 方法（最相关的学术方案）

**MoRE-LLM (Mixture of Rule Experts guided by LLM)** 是 2025 年发表的规则发现框架，直接针对"从少量数据发现规则"问题：

**核心流程**：
```
迭代循环:
  1. 用当前文档和已有规则集 R 训练分类器 f_θ
  2. 对每个训练样本 x，计算预测置信度
  3. 对低置信度样本，用 LLM 生成局部规则解释
  4. 规则精炼（Rule Refinement）:
     a. 规则适应（Rule Adaptation）：LLM 对齐规则与领域知识
     b. 规则剪枝（Rule Pruning）：移除冗余/冲突规则
  5. 更新规则集 R，回到步骤 1
```

**关键创新**：
- **规则精炼步骤**：用 LLM 的外部领域知识正则化规则发现过程，防止过拟合到训练样本的表面特征
- **规则泛化**：每个规则附带一个生成它的训练样本，但规则本身推广到更广的范围
- **门控机制**：根据输入文档动态选择使用哪些规则（gating model）

### 2.2 防止过拟合的策略

#### 策略 1：带推理过程的微调（Reasoning Process Fine-tuning）

来自内容审核领域的实证研究（arXiv:2310.03400）：

- **无需在推理时显式输出推理过程**——训练时强迫模型生成推理链即可泛化
- 生成模型天然比判别模型抗过拟合：模型通过逐步演绎推导标签，不会走"输入特征→标签"的捷径
- 操作方式：用强 LLM（如 GPT-4/Claude）为训练样本自动生成分析过程，用这些数据进行微调

#### 策略 2：RL 微调 > SFT 微调

2026 年的关键研究发现（"SFT Memorizes, RL Generalizes"）：

| 训练方式 | 域内表现 | 域外泛化 |
|----------|---------|---------|
| SFT | 提升 | **下降**（最多 79.5%） |
| RL | 提升 | 提升（3.5-11.0%） |

**含义**：如果公开标注数据有限且需要泛化到隐藏集，优先考虑 RL/RLHF 而非纯 SFT。

#### 策略 3：Concept Bottleneck Model（概念瓶颈模型）

ICLR 2026 Poster —— 适用于极少量样本的规则解释框架：

- 10 个训练样本即可达到与 LLM 可比的效果
- 通过**原型-判别双层架构** + **动态概念精炼机制**，提取可解释的概念规则
- 高效、可解释、无高推理成本

#### 策略 4：Prompt Engineering 层面的泛化

- **Few-shot 示例选择**：示例应覆盖边界案例（boundary cases），不限于典型样本
- **Task-specific relevance classifier**：用少量标注（128 例/topic）训练轻量分类器做判断，优于直接 prompt LLM-as-Judge 的效果
- **Text Classification with 断言增强**（AEFL）：添加结构化断言（assertion）约束 LLM 的判断边界

### 2.3 规则发现管线设计建议

```
阶段 1: 初始规则库构建
    ↓
    暴露少量标注数据 → LLM 分析 → 提取初始规则集（带推理过程）
    ↓
阶段 2: 规则迭代精炼（MoRE-LLM 循环）
    ↓
    执行分类 → 低置信度样本→LLM 补充规则 → 规则去重/剪枝 → 验证
    ↓
阶段 3: 对抗性验证
    ↓
    构造边界测试样本 → 检查规则是否过度泛化/不足泛化 → 调整
    ↓
阶段 4: 冻结规则库
    ↓
    生成 SKILL.md 集合 → 部署到编排系统
```

---

## 3. 不平衡数据处理

### 3.1 业务审批数据的特性

审批类数据的典型分布：
- 大部分为"通过"（或"不通过"，取决于政策宽松度）
- 少数为对立类别
- 极端情况下比例可达 90:10 甚至 95:5

这给传统 ML 带来严重问题，但 LLM-based 方法有不同的优势。

### 3.2 LLM 在不平衡数据上的优势

实证研究发现：

1. **传统 ML（SVM/RF/DT）在多数类上表现更好**，但**LLM 在少数类上展现显著优势**（arXiv:2407.01551）
2. LLM 通用语言理解能力使其不依赖训练集分布，因而天然对不平衡更鲁棒
3. 生成式分类（通过推理过程得出结论）不会走"模式匹配"的捷径

### 3.3 具体处理技术

#### 3.3.1 Class-few-shot 方法（平衡少样本）

来自 ICCS 2025 论文，专门解决不平衡数据下的 few-shot prompting：

- **标准 few-shot**：示例的类分布反映数据集真实分布 → 多数类主导，少数类被淹没
- **Class-few-shot**：**从每个类平等取例**，以"从最多到最少、交替展示"的排列方式

实验规模：~10,000 次实验，4 个数据集，3 个模型。
结果：Class-few-shot 在几乎全部场景下优于标准 few-shot。

**关键发现**：
- LLM 存在位置偏差（positional bias）——倾向于 prompt 末端的标签
- 利用这一偏差：将少数类样本放在 prompt 末端可显著提升少数类识别率
- 最有效的排列模式：多数组→少数组，交替呈现

#### 3.3.2 EPIC 方法（合成数据生成）

NeurIPS 2024 Poster —— 用 LLM 生成合成少数类样本：

- 提供平衡的、分组的样本 + 一致的格式化 + 唯一的变量映射
- LLM 被引导生成真实感合成数据覆盖所有类别
- 显著提升分类性能，尤其对少数类

**启示**：如果隐藏数据集的少数类不够，可以用 LLM 生成合成样本来增强规则发现。

#### 3.3.3 Prompt 层面的平衡策略

| 策略 | 做法 | 适用场景 |
|------|------|---------|
| 均衡 Few-shot 示例 | 每类等量示例 | 所有场景 |
| 负例 + 边界案例 | 主动展示错误分类示例和模糊边界 | 规则边界模糊时 |
| 显式强调少数类 | "特别注意：样本中多数为通过，请对不通过的情况更加审慎" | 极端不平衡 |
| Assertion 约束 | 结构化断言限定判断边界 | 需要精确阈值时 |
| 位置操控 | 将少数类样本放在 prompt 末端 | LLM 有位置偏 |

#### 3.3.4 评测指标选择

对于不平衡数据，**绝不能只用 Accuracy**：

- 推荐：**Precision, Recall, F1-score**（对每个类分别计算）
- 附加：**Confusion Matrix**（检查少数类的真实分布）
- 更细粒度：**Sensitivity（少数类召回率）、Specificity（多数类召回率）**
- 排序指标：**AUC-ROC**（评估整体判别能力，不受阈值影响）

### 3.4 同代改进（Iterative Self-Training）策略

对于极端不平衡场景：

```
Rounds 1: 用平衡 few-shot → 获得初始判断（可能有偏）
Rounds 2: 取高置信度预测 + 人工修正 → 扩充标注集
Rounds 3: 用扩充集微调/更新 prompt → 再预测
Rounds 4: 重复直到收敛
```

---

## 4. 技术栈建议

### 4.1 编排框架选择

| 维度 | 推荐 | 理由 |
|------|------|------|
| **编排层** | **LangGraph** | 状态持久化、HITL、条件路由、子图组合、生产验证最充分 |
| **原型验证** | **CrewAI** | 快速搭建规则匹配 Agent 团队，之后迁移到 LangGraph |
| **备选** | **AutoGen (AG2)** | 如果看重 GroupChat 辩论模式的规则推演 |
| **低代码 UI** | **Dify** | 如果用可视化编排更高效，但复杂逻辑需自定义组件 |

### 4.2 Web 界面框架

| 框架 | 优点 | 缺点 | 适合场景 | 学习曲线 |
|------|------|------|---------|---------|
| **Gradio** | 快速部署 ML demo、内建组件丰富、HuggingFace Spaces 一键部署 | 自定义 UI 能力有限 | **原型验证、作业交付** | 低 |
| **Streamlit** | 更强大的自定义能力、数据应用生态丰富 | 对 LLM streaming 支持不如 Gradio 原生 | 数据展示+交互式仪表盘 | 中 |
| **FastAPI + Svelte/React** | 完全可控、生产级性能 | 开发量大 | **生产级部署** | 高 |
| **Open WebUI** | 自托管、内建 RAG、多用户 | 定制化复杂 | 通用 AI 接口 | 低 |

**推荐**：Gradio（快速验证）→ 后续迁移到 **FastAPI + React/Svelte**（生产级）。

Gradio 优势具体体现在：
- `gr.ChatInterface` 和 `gr.Blocks` 原生支持 LLM 流式输出
- 内建队列管理，适合多并发请求
- HuggingFace Spaces 免费部署，满足"公网可访问"的需求
- 但是自定义 UI 和权限管理需要额外开发

### 4.3 LLM 选择

| 模型 | 推理能力 | 成本 | 适合场景 |
|------|---------|------|---------|
| **Claude 4 Sonnet** | 优秀 | 中 | **主推理 Agent**——长文档理解、规则推理 |
| **GPT-4o** | 优秀 | 中高 | 备选，多模态支持 |
| **DeepSeek-V3 / Qwen3** | 良好 | 低 | **规则批量匹配**——成本敏感任务 |
| **DeepSeek-R1** | 推理型 | 中 | 复杂规则分析 |
| **本地 LLM (Qwen3-235B)** | 良好 | 硬件成本 | 私有化部署 |

**推荐策略**（分层 LLM 使用）：

```
协调层 (Orchestrator): Claude 4 Sonnet（最强推理，控制流程）
规则匹配层: DeepSeek-V3 / Qwen3（高吞吐、低成本的批量匹配）
规则精炼层: Claude 4 Sonnet / GPT-4o（需要深度分析时）
评审层 (Judge): Claude 4 Sonnet（与主 Agent 不同 provider，避免系统性偏差）
```

### 4.4 部署方案

| 方案 | 优点 | 缺点 | 成本 |
|------|------|------|------|
| **HuggingFace Spaces** | 免费公网访问、Gradio 原生支持 | GPU 资源有限 | 免费（CPU）/ 付费（GPU） |
| **Railway / Render** | 快速部署、自动 HTTPS | 冷启动延迟 | $5-20/月 |
| **阿里云/腾讯云 ECS** | 完全可控、CPU/GPU 灵活配置 | 需自行管理域名和 HTTPS | ~¥100-500/月 |
| **NAS 内网穿透** | 利用已有硬件 | 带宽限制、稳定性一般 | 几乎免费 |

**推荐**：
- **演示/原型**：HuggingFace Spaces（免费 + 公网可访问）
- **作业正式提交**：阿里云轻量应用服务器（¥68/月起 + 域名备案 + nginx/caddy HTTPS）

### 4.5 数据层

| 组件 | 推荐 | 说明 |
|------|------|------|
| **向量数据库** | ChromaDB（本地）/ Qdrant（生产） | 存储规则语义向量，用于规则检索匹配 |
| **关系数据库** | SQLite（原型）/ PostgreSQL（生产） | 存储判断记录、规则元数据、审计日志 |
| **规则存储** | YAML 文件 + SKILL.md 格式 | 规则即代码，可版本控制、可追溯 |

---

## 5. 类似系统/最佳实践

### 5.1 法律文档审查系统

#### Harvey AI（最相关的商业化系统）

Harvey 是为 AmLaw 顶级律所构建的法律 AI 平台，其 Agent 架构是：

```
Plan → Research → Work → Deliver → Review
                              ↑
                       Human-in-the-loop (律师保留最终判断)
```

核心模式：
- **Human-in-the-loop**：AI 做工作（扫描、识别、标注），人做决策（确认/修改/拒绝）
- **Cited Reasoning**：AI 输出判断时附带引用依据，不是黑箱结论
- **Privilege Review**：AI 扫描特权文档 → 生成初步判定 + 引用推理 → 律师复核 → 自动生成特权日志

**启示**：本作业可以借鉴——Agent 负责标记和依据搜索，最终判断过 Human-in-the-loop（或 Agent Judge）。

#### DISCO Cecilia Q&A

DISCO 的 e-discovery 平台集成了 Agentic AI：
- 多步推理引擎：搜索 → 关联分析 → 判定 → 引用来源
- 明确的 Tag 定义体系：给出准确的分类标记描述（比简单的"相关/不相关"更有效）
- "四角原则"：模型只读文档文本本身，不读元数据，避免元数据偏差

**启示**：规则描述要精确而非模糊。"创新程度是否足够"需要一个多维度评分卡，而非简答的 yes/no。

#### Agent-as-a-Judge 框架

来自 arXiv:2508.02994 —— 评估 Agent 行为的框架：

- 不仅仅是看最终结果，而是评估**整个推理过程**
- 多 Agent 评审比单 Agent 更鲁棒——欺骗性输出需要同时骗过多 Agent
- 但也存在**同源偏差**（同模型族的评审 Agent 会被同种方式欺骗）

**启示**：建议使用不同 provider 的 LLM 做评审（如主推理用 Claude，Judge 用 GPT-4o）

### 5.2 竞赛方案的架构启示

从 Agent 竞赛（如 SWE-bench, GAIA, Terminal-Bench）的获胜方案中提取的通用模式：

| 模式 | 说明 | 适用点 |
|------|------|--------|
| **Plan-then-Execute** | 先分解问题再逐步执行 | 文档分析先分出需要评估的维度 |
| **Self-Reflection** | Agent 对自身输出做反思修正 | 检查判断依据是否充分 |
| **Tree-of-Thought** | 同时探索多条判断路径，最后综合 | 多个规则可能导向不同结论时 |
| **Majority Voting** | 多次采样取多数结果 | 降低随机性影响 |
| **分层推理** | 先快后慢：Cheap model 先筛选，Expensive model 审关键 | 成本控制 |

### 5.3 分析竞赛的成功要素

| 要素 | 具体做法 |
|------|---------|
| **数据探索先行** | 先分析公开数据的分布、关键字段、常见模式 |
| **规则不是死的** | 规则应设计为可配置、可扩展（规则即数据） |
| **红队测试** | 主动构造对抗样本，测试规则是否有漏洞 |
| **多角度验证** | 同一文档用不同规则顺序/不同模型判断，检查一致性 |
| **错误分析循环** | 对错误案例进行归因分析，更新规则 |

### 5.4 关键学术论文索引

| 论文 | 领域 | 核心贡献 |
|------|------|---------|
| MoRE-LLM (arXiv:2503.22731) | 规则发现 | LLM 引导的规则专家混合体，迭代发现+精炼规则 |
| SFT Memorizes, RL Generalizes | 泛化 | SFT 损害域外泛化，RL 提升域外泛化 |
| EPIC (NeurIPS 2024) | 不平衡合成 | 用 LLM 生成合成少数类样本解决不平衡 |
| Adaptive Concept Discovery (ICLR 2026) | 小样本分类 | 10 样本+概念瓶颈模型达到 LLM 可比效果 |
| Class-few-shot (ICCS 2025) | 不平衡 Few-shot | 平衡类示例+位置偏差利用 |
| LLM as Content Moderator (arXiv:2310.03400) | 分类过拟合 | 推理过程微调防止过拟合 |
| Agent-as-a-Judge (arXiv:2508.02994) | Agent 评估 | 用 Agent 评估 Agent 行为轨迹 |
| MAJ-EVAL | 多 Agent 评审 | 多 Agent 多维评审框架 |

---

## 6. 推荐方案总结

### 6.1 系统架构全景图

```
┌─────────────────────────────────────────────────────────────┐
│                    Web 界面 (Gradio → FastAPI)               │
│                 上传文档 → 查看判断结果 → 审计日志             │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│              LangGraph Orchestrator (协调器)                  │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ Document │  │  Rule    │  │  Rule    │  │ Composite  │  │
│  │ Reader   │→│  Matcher │→│  Miner   │→│  Judge     │  │
│  │ Agent    │  │  Agent   │  │  Agent   │  │  Agent     │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘  │
│       │              │             │              │          │
│       ▼              ▼             ▼              ▼          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │Tavily/   │  │  Rules   │  │  LLM     │  │ 被屏蔽的     │  │
│  │doc-read  │  │  SKILL.md│  │  Proposer│  │ 人类评审     │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘  │
│                                                              │
│  持久化: LangGraph Checkpoint (PostgreSQL)                    │
│  知识库: ChromaDB (规则语义向量) + YAML 规则文件 (版本管理)      │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 分层推荐 LLM 策略

| 层级 | 角色 | 推荐模型 | 理由 |
|------|------|---------|------|
| L1 | 文档解析 + 规则匹配 | DeepSeek-V3 / Qwen3 | 高吞吐、低成本 |
| L2 | 综合判断 + 复杂推理 | Claude 4 Sonnet | 长文档理解强，推理精准 |
| L3 | 规则精炼 + 新规则发现 | Claude 4 Sonnet / GPT-4o | 需要深度分析 |
| L4 | 评审层（Judge） | GPT-4o（与 L2 不同 provider） | 避免同源偏差 |

### 6.3 关键实施要点

1. **从公开数据中挖掘规则**：用 LLM 分析公开标注样本 → 提取初始规则集 → MoRE-LLM 风格的迭代精炼
2. **规则即数据**：规则存储在 YAML/SKILL.md 文件中，可版本控制、热加载、独立测试
3. **多层次验证**：
   - 单元验证：每条规则单独测试
   - 集成验证：多条规则组合测试
   - 对抗验证：构造边界样本测试规则鲁棒性
4. **不平衡处理**：Class-few-shot + 合成数据补充 + 合适的评价指标
5. **可审计性**：每个判断记录以下信息：
   - 输入文档摘要
   - 命中的规则列表（含规则版本）
   - 每条的判断依据（引用文档原文）
   - LLM 推理过程
   - 最终判定 + 置信度

### 6.4 开发路线图（建议）

```
Phase 1 (1-2周): 数据探索 + 规则原型
  - 分析公开数据分布、常见模式
  - 用 LLM 从少量标注提取初始规则集
  - 搭建单 Agent 判断 Pipeline

Phase 2 (2-3周): 系统架构搭建
  - LangGraph 编排框架落地
  - 规则 SKILL.md 体系建立
  - Gradio Web 界面开发
  - 部署测试环境（HuggingFace Spaces）

Phase 3 (2-3周): 迭代优化
  - MoRE-LLM 规则精炼循环
  - Class-few-shot 不平衡处理
  - 对抗性测试 + 规则补充
  - 多 Agent 协作流程完善

Phase 4 (1-2周): 交付准备
  - 隐藏数据集评测
  - 性能优化（延迟/成本）
  - 审计日志 + 界面完善
  - 正式部署（ECS/云服务器）
```

---

## 参考来源

| 主题 | 来源 | URL |
|------|------|-----|
| Agent 框架对比 2026 | PE Collective | https://pecollective.com/blog/ai-agent-frameworks-compared |
| 多 Agent 框架 2026 | Towards AI | https://pub.towardsai.net/the-4-best-open-source-multi-agent-ai-frameworks-2026-9da389f9407a |
| MoRE-LLM | arXiv | https://arxiv.org/html/2503.22731v1 |
| SFT Memorizes RL Generalizes | Cameron Wolfe | https://cameronrwolfe.substack.com/p/rl-continual-learning |
| 内容审核 LLM 过拟合 | arXiv | https://arxiv.org/html/2310.03400v1 |
| Class-few-shot (ICCS 2025) | ICCS | https://www.iccs-meeting.org/archive/iccs2025/papers/159060049.pdf |
| EPIC (NeurIPS 2024) | OpenReview | https://openreview.net/forum?id=d5cKDHCrFJ |
| LLM 不平衡数据分类 | arXiv | https://arxiv.org/html/2407.01551v1 |
| Agent-as-a-Judge | arXiv | https://arxiv.org/html/2508.02994v1 |
| Adaptive Concept Discovery (ICLR 2026) | OpenReview | https://openreview.net/forum?id=UZBQ7iZzYz |
| Agent Skills 模式 | arXiv | https://arxiv.org/html/2602.12430v3 |
| Streamlit vs Gradio | Squadbase | https://www.squadbase.dev/en/blog/streamlit-vs-gradio-in-2025-a-framework-comparison-for-ai-apps |
| 法律 Agent 综述 | OAEPublish | https://www.oaepublish.com/articles/aiagent.2025.06 |
| LLM Agent 架构 2026 | Future AGI | https://futureagi.com/blog/llm-agent-architectures-core-components |
| 瘦 Agent / 胖平台架构 | Praetorian | https://www.praetorian.com/blog/deterministic-ai-orchestration-a-platform-architecture-for-autonomous-development |
| Harvey AI | Harvey | https://www.harvey.ai/blog/how-to-use-ai-for-legal-discovery |
| DISCO GenAI 文档审查 | DISCO | https://csdisco.com/blog/blog-generative-ai-for-document-review |
| 企业 LLM 运维 Lumenalta | Lumenalta | https://lumenalta.com/insights/9-llm-enterprise-applications-advancements-in-2026-for-cios-and-ctos |
| AI Agent 框架 2026 (LangChain) | LangChain | https://www.langchain.com/resources/ai-agent-frameworks |
