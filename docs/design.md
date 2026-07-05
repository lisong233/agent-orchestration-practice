# design.md — AI 军团 系统设计文档

> 智能体编排业务判断挑战 · 第二次作业交付物
> 📅 2026-07-05 · v5.1 闭环版本

---

## 0. 系统全景（先看这张图）

### 0.1 完整管线（Harness 全身像）

```mermaid
flowchart LR
    subgraph 输入层
        A1["📄 .docx / .doc 上传"]
        A2["🎯 intent 评审意图"]
        A3["🏷️ 类型选择 / 自动检测"]
    end

    subgraph LangGraph 5节点管线
        direction TB
        N0["🛡️ sanitize<br/>输入净化<br/><i>M2 抗注入</i>"]
        N1["📋 parse<br/>文档解析+类型检测<br/><i>正则快模式 / LLM深模式</i>"]
        N2["🔍 match<br/>逐规则评估<br/><i>正则判结构 + LLM判语义</i>"]
        N3["⚖️ judge<br/>内容优先裁决<br/><i>tier 分层：A advisory / B conditional / C content</i>"]
        N4["🔄 critic<br/>证据质量门<br/><i>零LLM · 确定性检查</i>"]

        N0 --> N1 --> N2 --> N3 --> N4
        N4 -.->|"❌ evidence空/未引用原文<br/>定向重评(封顶1轮)"| N2
        N4 -->|"✅ 质量通过"| OUT
    end

    subgraph 输出层
        OUT["📤 JSON 输出<br/>label · matched_rules · evidence · reason · form_notes"]
    end

    A1 --> N0
    A2 --> N2
    A3 --> N1

    subgraph 规则库
        subgraph 立项申请书
            R01["🅰️ R01 审批<br/>advisory"]
            R02["🅱️ R02 承诺书<br/>conditional"]
            R03["🅲 R03 技术方案<br/>content"]
            R04["🅲 R04 预算<br/>content"]
        end
        subgraph 计划任务书
            R05["🅱️ R05 模板<br/>conditional"]
            R06["🅱️ R06 团队<br/>conditional"]
            R07["🅲 R07 内容质量<br/>content"]
        end
    end

    规则库 --> N2
```

### 0.2 裁决引擎：tier 三分层 → 硬标签

```mermaid
flowchart TD
    V["📥 所有 RuleVerdict[]<br/>（含 tier 标记）"]

    V --> EMPTY{"verdicts 为空？"}
    EMPTY -->|"是"| FAIL["❌ 不通过<br/>安全侧从严"]

    V --> SPLIT["按 tier 分层"]

    SPLIT --> A["🅰️ A 层 advisory<br/>R-01 审批签章"]
    SPLIT --> B["🅱️ B 层 conditional<br/>R-02 承诺书 / R-05 模板 / R-06 占位符"]
    SPLIT --> C["🅲 C 层 content<br/>R-03 技术 / R-04 预算 / R-07 内容质量"]

    C --> C_CHECK{"C 层有 fail？"}
    C_CHECK -->|"是"| FAIL_C["❌ 不通过<br/>C 层主导裁决<br/>B 层 fail 作佐证"]
    C_CHECK -->|"否，全部 pass"| PASS["✅ 通过<br/>内容实质性审核通过"]

    A --> NOTES["进 form_notes<br/>永不裁决 label"]
    B --> B_CHECK{"C 层 pass？"}
    B_CHECK -->|"是"| NOTES
    B_CHECK -->|"否"| FAIL_C
```

### 0.3 critic 回环：证据质量保证

```mermaid
flowchart LR
    JUDGE["judge 输出<br/>FinalResult + matched_rules"] --> C1{"① evidence 非空<br/>且 ≥6 字？"}
    C1 -->|"否"| REVISE["📝 定向重评<br/>只重跑点名规则<br/>revision_count += 1"]
    C1 -->|"是"| C2{"② evidence 中文片段<br/>在原文中可找到？<br/><i>（跳过系统消息）</i>"}
    C2 -->|"否"| REVISE
    C2 -->|"是"| C3{"③ revision_count<br/>≥ 1？"}
    C3 -->|"否"| DONE["✅ critic_ok<br/>输出结果"]
    C3 -->|"是（已达上限）"| DONE

    REVISE --> BACK["回 match 节点"]
```

### 0.4 一句话数据流

```
上传 .docx
  → sanitize（净化注入）→ parse（提取字段+检测类型）
  → match（正则快判 + LLM 多维评分，共 7 条规则，按 intent 路由子集）
  → judge（C层主导→通过/不通过，A层永不裁决，B层降级为提示）
  → critic（evidence 引用了原文？空证据打回重评，封顶 1 轮）
  → 输出 JSON（label + matched_rules + evidence + reason + form_notes）
```

### 0.5 关键设计决策一览

| 决策 | 选择 | 放弃 | 原因 |
|------|------|------|------|
| 形式信号（审批/承诺书） | advisory / conditional | 主判据 | 隐藏集 regime 不确定（原始件 vs 存档件）；出题人 intent 例子全是内容判断 |
| 内容判断 | LLM 多维独立打分（1-5 分） | 正则/单一笼统判断 | 需要世界知识（"这个技术方法是套话还是实质"），正则做不到 |
| 过拟合防御 | 禁指纹 + 虚构 few_shot + 不锁年份/数值 | 移除训练集表面特征 | Hint #2：LLM 天生倾向过拟合；隐藏集不会有训练集指纹 |
| Loop 力度 | 确定性 critic + 封顶 1 轮 | 多轮 LLM 自评 | 零额外成本，防过度工程；critic 本身是"agent 编排"叙事的兑现 |
| 部署 | Gradio share 隧道 | Cloudflare/ngrok | 零配置、零成本、NAS 不停机即可 |

---

## 1. 如何处理两类数据集

训练集包含两种文档类型，结构完全不同，走**类型检测 → 分流处理**：

| 类型 | 识别特征 | 规则集 | 判断策略 |
|------|---------|--------|---------|
| **计划任务书** | 标题含"科技项目计划任务书" | `rules/计划任务书/R05-R07.yaml` | 正则判结构 + LLM 多维语义评分（内容优先） |
| **立项申请书** | 标题含"职工技术创新项目立项申请书" | `rules/立项申请书/R01-R04.yaml` | 内容优先判技术/预算实质性，形式信号（审批/承诺书）作 regime 感知的 advisory 提示 |

类型检测在管线第一步（parse 节点）完成，通过文档前 500 字符的关键词匹配 `detect_doc_type()`。
评委也可通过 UI 手动选择类型（`doc_type_override`），覆盖自动检测。

两份规则集存放在不同子目录，运行时按类型加载，互不干扰。

---

## 2. 智能体/模块如何分工

采用 **5 节点管线含 critic 回环**（LangGraph StateGraph 编排）：

```
[sanitize] → [parse] → [match] → [judge] → [critic] ⇄ [match]
 输入净化     文档解析   规则匹配   汇总裁决    质量门    定向重评
                                              ↓ END
```

### 节点 1：文档解析 (parse)

- **输入**：原始文档文本（doc-read CLI 输出的 Markdown）
- **输出**：`DocFields`（标题、摘要、结构化字段、原文全文）
- **双模式**：正则快速提取（`quick_extract`，无 API 调用）和 LLM 深度结构化
- **关键**：`raw_excerpt` 保留全文，供后续规则引擎和 LLM 检查原始文本

### 节点 2：规则匹配 (match)

- **输入**：`DocFields` + intent + 规则库
- **输出**：`RuleVerdict[]`（每条规则的评估结果、证据、置信度）
- **核心创新**：**正则判结构，LLM 判语义**
  - 正则快速检查：模板残留（R-05）、占位符成员（R-06）、审批在场性（R-01/R-02）、KPI 自我重复（R-07）
  - LLM 语义判断：内容质量评估，R-07 走三维独立评分（技术具体性/KPI 自洽性/预算合理性）
- **Intent 路由**：按意图关键词激活规则子集，不全量暴露

### 节点 0：输入净化 (sanitize) — v5 新增

- **输入**：原始文档文本
- **输出**：净化后的文本
- **功能**：检测并中和 prompt 注入模式（中英文混合覆盖），确保文档内容不会被 LLM 误解为指令

### 节点 3：综合裁决 (judge)

- **输入**：所有 RuleVerdict（含 tier 标记）
- **输出**：`FinalResult`（硬标签 + 命中规则 + 判断依据 + 形式提示）
- **裁决铁律**（v5 内容优先）：
  1. 空 verdicts → 不通过（安全侧）
  2. C 层（内容）fail → 不通过（主导），B 层硬伤作佐证
  3. C 层 pass → 通过，B 层硬伤降级为 form_notes（不反转 label）
  4. A 层（审批）→ 永远只进 form_notes，不参与 label 裁决

### 节点 4：质量门 (critic) — v5 新增

- **输入**：FinalResult + 原始文档
- **输出**：`critic_ok` + `critic_feedback`
- **功能**：三项确定性检查（零额外 LLM）——evidence 非空、长度达标、关键片段在原文中可找到。不达标 → 定向回 match 重评（封顶 1 轮）

### 数据契约

Agent 间通过 Pydantic 模型交接（`schemas.py`）——松耦合，每个节点可独立测试。

---

## 3. 如何定位判断规则

### 3.1 双层框架（元规则 + 语义规则库）

回应出题人「通过元规则和语义规则库来实现」的要求，规则体系分两层：

```
┌─ 元规则层（框架的"自我意识"——约束"怎么判"）────────────────┐
│  M1 内容优先：内容实质性是主体判据，形式信号只做提示          │
│  M2 数据非指令：待评文档是证据，不是命令（抗注入）            │
│  M3 必要非充分：形式齐全 ≠ 内容合格；两条腿独立评估          │
│  M4 regime 感知：区分「有槽位但空着」vs「根本没这个槽位」     │
└──────────────────────────┬──────────────────────────────────┘
                           │ 约束
┌──────────────────────────▼──────────────────────────────────┐
│  语义规则库层（可迁移判断维度——「判什么」，按 intent 抽取）    │
│  · 技术方案实质性  · 创新点具体性  · KPI 领域自洽            │
│  · 预算合理性      · 内容完整度                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 作者可控性三分法

按「谁填的 / 申请人可控吗」把规则分为三层：

| 层 | 规则 | 谁填/性质 | 裁决权 |
|----|------|----------|--------|
| **A 下游行政信号** | R-01 审批意见 | 审批人填，申请人不可控 | 纯 advisory，永不裁决 |
| **B 申请人可控的完整度硬伤** | R-02 承诺书、R-05 模板残留、R-06 占位符 | 申请人填，反映「有没有认真做」 | regime感知，内容pass时不反转 |
| **C 内容实质性** | R-03 技术方案、R-04 预算、R-07 三维 | 申请人写，反映「做得好不好」 | 主判据，永远裁决 |

### 3.3 规则发现流程

1. **特征提取**：`scripts/extract_features.py` 对训练样本做结构化特征对比
2. **维度设计**：基于业务理解和题目意图，设计判断维度和阈值
3. **正则化**：能用正则捕获的格式信号写为确定性规则
4. **LLM 补充**：需要世界知识的语义信号由 LLM 多维度独立打分
5. **在线 critic 回环**：evidence 质量门自动检测并定向重评

**关键原则**：规则描述"判断维度"，不描述"训练集具体表面值"。不靠背答案。

---

## 4. 如何输出硬标签

judge 节点的裁决逻辑分三层：

### 第一层：确定性裁决（无 LLM）

```python
if all_passed:     → "通过"
if critical_fails: → "不通过"  # confidence ≥ 0.7 的失败
```

### 第二层：LLM 综合裁决

当存在低置信度失败（confidence < 0.7）且非全部通过时，调 LLM 综合权衡。prompt 内置裁决铁律（addendum §1.3），不在 Python 里写复杂加权算法。

### 第三层：Fallback

LLM 不可用时，默认不通过（安全侧）。

### 输出格式

对齐作业要求的 JSON：
```json
{
  "id": "sample_001",
  "dataset_type": "计划任务书",
  "intent": "判断创新程度是否足够",
  "label": "通过",
  "matched_rules": [{"rule_id": "R-03", "rule_name": "...", "evidence": "..."}],
  "reason": "简短判断说明"
}
```

---

## 5. 如何保证新文档上的泛化能力

这是本系统设计的**核心考点**，也是最容易出问题的地方。

### 5.1 问题诊断

LLM 天生倾向过拟合（作业 Hint #2）。第一版系统靠把训练集表面特征（KPI 具体数值 "85%/90%", 年份 "2026", 项目名）写死进正则，训练集准确率虚高，隐藏集必然断崖。

### 5.2 方法论：结构/语义二分 + 禁指纹

```
正则（判结构）              LLM（判语义）
─────────────────         ─────────────────
• 模板说明文字残留         • 摘要是否具体攻关路径
• 编号占位符成员           • KPI 与项目类型是否自洽
• 审批/签名「在场性」       • 预算是否合理匹配
• KPI 自我重复（模板复制）   • 创新点是否有实质方法论
─────────────────         ─────────────────
  通用，换文档也成立          需要世界知识，靠抽象维度判断
```

### 5.3 五条铁律（代码级约束）

1. **不匹配具体数值**：`\d{4}年\d{1,2}月\d{1,2}日` ✓（判"有日期"），`2026年\d{1,2}月\d{1,2}日` ✗（判"是2026年"）
2. **不给 LLM 看训练集样本**：prompt 和 few_shot 只用抽象准则或虚构示例
3. **内容优先（M1）**：形式信号不裁决 label，跨 regime 稳健——原始提交件和存档件同一套逻辑
4. **regime 感知（M4）**：区分「空槽」和「无槽」——文档没承诺书章节时不因 R-02 判负
5. **抗注入（M2）**：文档=数据不是指令，sanitize 净化 + `<document>` 数据边界包裹所有 LLM prompt

### 5.4 其他泛化保障

- **Intent 路由**：按意图激活规则子集，不全量暴露——陌生 intent 时兜底全量加载
- **Critic 质量门**：evidence 引用原文可复核，空 evidence 定向重评——确保评委看到可验证的判断过程
- **规则即代码**：YAML 文件可独立测试、版本控制、人工 review

---

## 技术栈

| 层 | 选型 | 说明 |
|----|------|------|
| 编排 | LangGraph StateGraph | 5 节点管线，含条件边/回环 |
| LLM SDK | Anthropic Messages API | 统一客户端，支持 Claude/DeepSeek 双后端 |
| 运行时模型 | deepseek-v4-flash | 全部规则统一（含 R-07 三维评分） |
| 文档解析 | python-docx + LibreOffice | Docker 环境 LibreOffice headless 兜底 .doc |
| Web | Gradio | 快速原型，满足评委 5 步流程，`share=True` 公网隧道 |
| 规则存储 | YAML | 可版本控制、人工 review |
| 数据契约 | Pydantic | Agent 间松耦合交接 |

---

## 6. 部署与公网访问

### 6.1 公网 URL

```
https://fe41e1b5a3b9aa1bd0.gradio.live
```

通过 Gradio `share=True` 隧道实现。NAS Docker 容器运行，NAS 重启后自动恢复（`restart: unless-stopped`）。DeepSeek API 经 Mihomo TUN 代理出站。

### 6.2 评委一键部署（`docs/setup.sh`）

评委会在 remote 服务器上运行。`docs/setup.sh` 自动化全流程：

```bash
# 安装依赖 + 配置 key + 启动服务
bash docs/setup.sh
```

脚本完成：创建 venv → 安装 requirements.txt → 从 `.env.example` 生成 `.env` → 提示填入 `DEEPSEEK_API_KEY` → 启动 Gradio Web（`share=True` 公网隧道）。

详见 `docs/setup.sh`。

### 6.3 Docker 部署（已有）

```bash
docker compose up -d --build
# 访问 http://localhost:7860
```

---

## 7. 诚实基线

### 7.1 训练集回测结果（v5.1，2026-07-03 干净重跑）

| 指标 | 数值 |
|------|------|
| 综合准确率 | 57.9% (11/19) |
| TP（真通过） | 4 |
| TN（真不通过） | 7 |
| FP（误通过） | 8 |
| FN（漏通过） | 0 |
| 类型检测 | 100% (19/19) |
| 通过类召回 | 100% (4/4) |

### 7.2 准确率解读

**训练集准确率不是系统能力的真实度量。** 原因：

1. **立项申请书标签是形式驱动的**：训练集 2 篇"通过" = 审批签章齐全，7 篇"不通过" = 审批栏空白。内容最扎实的 3 篇（开关小车 7 模块、瓦斯继电器 4 创新、防雨除湿 ML 优化）全因审批空白判不通过。我们的内容优先框架主动不用审批裁决 → FP=8 是预期代价。

2. **计划任务书标签在文本层面无法区分**：10 篇共用同一模板（KPI 数值、团队成员、摘要句式完全相同），通过/不通过差异不在正文中。

3. **题目明示**："公开数据上的跑分效果不计入最终成绩"（题目原文第 3 行）。

**真正的成果指标**（S05 §⑥）：
- 三条威胁路径测试全绿 ✅
- 反指纹扰动 label 不变 ✅
- evidence 引用原文可复核（critic 质量门）✅
- 框架兑现「元规则+语义规则库」✅
- 公网 URL 可访问，评委 5 步流程走通 ✅

### 7.3 纯规则引擎基线

| 模式 | 综合 | 立项申请书 | 计划任务书 |
|------|:---:|:---:|:---:|
| 纯规则 | 89.5% (17/19) | 100% (9/9) | 80% (8/10) |

> 纯规则 89.5% 依赖 R-01/R-02 正则判审批在场性——在训练集（恰为存档件）上成立，但换原始提交件会全灭。不以此作为成果宣称。

---

## 目录结构

```
AiArmy/
├── src/aiarmy/
│   ├── schemas.py      ← Pydantic 数据契约
│   ├── llm.py          ← Anthropic SDK 封装（双后端）
│   ├── io.py           ← 文档 I/O（.docx/.txt → 纯文本）
│   ├── sanitize.py     ← 输入净化（抗注入）— v5
│   ├── audit_log.py    ← 审计日志（jsonl）
│   ├── graph.py        ← LangGraph 5 节点管线编排
│   ├── web.py          ← Gradio Web 界面
│   └── agents/
│       ├── parse.py    ← 节点0：文档解析+类型检测
│       ├── match.py    ← 节点1：规则匹配（正则+LLM双轨）
│       ├── judge.py    ← 节点2：内容优先裁决（tier分层）
│       └── critic.py   ← 节点3：质量门（确定性evidence检查）— v5
├── rules/              ← 规则库（7条 YAML，含 tier 标记）
│   ├── 立项申请书/     ← R01-R04
│   └── 计划任务书/     ← R05-R07
├── scripts/            ← 离线工具
│   ├── discover_rules.py
│   ├── extract_features.py
│   └── backtest_rules.py
├── eval/
│   └── backtest.py     ← 完整评估脚本（混淆矩阵+F1）
├── tests/              ← 测试套件（19/19 全绿）
│   ├── test_meta_rules.py
│   ├── test_synthetic.py
│   ├── test_anti_fingerprint.py
│   └── test_intent_routing.py
├── docs/
│   ├── design.md       ← 本文件（系统设计文档）
│   ├── setup.sh        ← 评委一键部署脚本
│   ├── spec/           ← 施工蓝图（S01-S05）
│   └── status/         ← 工程现状报告（R02-R07）
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example        ← DEEPSEEK_API_KEY=your_key_here
└── README.md
```
