# AI 军团 — 电力项目立项审核系统

> 智能体编排业务判断挑战 · 第二次作业

基于多 Agent 协作的电力行业业务文档审核系统。读取计划任务书/立项申请书，自动输出 **通过/不通过** 硬标签 + 命中规则 + 判断依据。

## 快速开始

### 环境准备

```bash
cd D:/ClaudeWorkspace/agent-learning/AiArmy

# 安装依赖
pip install -r requirements.txt

# 配置 API Key
cp .env.example .env
# 编辑 .env 填入真实 DEEPSEEK_API_KEY
```

### 启动 Web 界面

```bash
python -m src.aiarmy.web
# 浏览器打开 http://localhost:7860
```

**评委操作流程**：选数据集类型 → 上传 .docx → 输评审意图 → 点"开始审核" → 查看 JSON 结果

### 命令行回测

```bash
# 纯规则引擎（不需要 API key）
python eval/backtest.py -v

# LLM 增强模式（需要 DEEPSEEK_API_KEY）
python eval/backtest.py --llm -v
```

### 运行测试

```bash
python tests/test_synthetic.py        # 合成样本验证
python tests/test_anti_fingerprint.py # 反指纹验证
python tests/test_intent_routing.py   # Intent 路由验证
```

## 系统架构

```
[上传 .docx] → io.py (doc-read CLI / python-docx)
     ↓
[parse] 文档 → 结构化字段
     ↓ DocFields
[match] 逐规则评估（正则快速检查 + LLM 语义评分）
     ↓ RuleVerdict[]
[judge] 汇总裁决（确定性铁律 + LLM 综合）
     ↓ FinalResult
Gradio Web (localhost:7860)
```

- **parse**：文档 → 结构化字段（正则快模式 / LLM 深模式），类型由评委 UI 选择
- **match**：逐规则评估，正则判结构 + LLM 判语义，R-07 难例走 deepseek-v4-pro
- **judge**：汇总 verdicts，确定性裁决 + LLM 综合，matched_rules 确定性取自 verdicts

## 评估结果（v4）

| 模式 | 综合准确率 | 立项申请书 | 计划任务书 |
|------|:---:|:---:|:---:|
| 纯规则引擎 | 89.5% | 100% (9/9) | 80% (8/10) |

- **立项申请书 100%**：R-01/R-02 纯正则，零 API 调用
- **计划任务书 80%**：2 篇"通过"被判不通过——数据报告中已证明此 2 篇与不通过文档在文本层面无法区分
- **通过 Recall 50%**（v4 fallback 从严后）：少数类"通过"在不可学习文档上无法召回，这是诚实的代价
- `logs/runs.jsonl` 记录每次判断的完整中间过程（部署后唯一观测窗口）

## 核心设计原则

### 正则判结构，LLM 判语义

```
正则（通用，换文档也成立）         LLM（需要世界知识）
├─ 模板说明文字残留              ├─ 摘要是否具体攻关路径
├─ 编号占位符成员                ├─ KPI 与项目类型是否自洽
├─ 审批/签名「在场性」            ├─ 预算是否合理匹配
└─ KPI 自我重复（模板复制）       └─ 创新点是否有实质方法论
```

### 禁止训练集指纹

- 不匹配具体 KPI 数值（`85%/90%/500ms`）
- 不锁定年份（`2026年`）
- 不给 LLM 看训练集样本名
- 规则写「判断维度」，不写「训练集表面值」
- ✅ 反指纹测试通过：扰动年份/KPI 值/项目领域名后 label 不变

## 交付物

- `src/aiarmy/` — 运行时系统（parse/match/judge + llm + io + web + audit_log）
- `rules/` — 规则库（7 条，YAML）
- `eval/backtest.py` — 完整评估脚本（混淆矩阵 + Precision/Recall/F1）
- `tests/` — 反指纹测试 / 合成样本测试 / Intent 路由测试
- `design.md` — 系统设计文档
- `README.md` — 本文件

## 部署

### 格式边界

- **Docker 环境仅支持 .docx**（python-docx 兜底）
- 开发环境支持 .docx/.doc/.pdf/.txt（doc-read CLI）

### Docker

```bash
# 构建 & 启动
docker compose up -d --build

# 访问
http://localhost:7860
```

### NAS 远端部署

```bash
ssh nas-wan "cd /volume1/docker/aiarmy && git pull && docker compose up -d --build"
# 访问: http://100.66.1.1:7860
```

## 许可

作业项目，内部使用。
