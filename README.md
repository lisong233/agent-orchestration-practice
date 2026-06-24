# AI 军团 — 电力项目立项审核系统

> 智能体编排业务判断挑战 · 第二次作业

基于多 Agent 协作的电力行业业务文档审核系统。读取计划任务书/立项申请书，自动输出 **通过/不通过** 硬标签 + 命中规则 + 判断依据。

## 快速开始

### 环境准备

```bash
# 1. 克隆仓库
cd D:/ClaudeWorkspace/agent-learning/AiArmy

# 2. 创建虚拟环境（uv）
uv venv
uv pip install -r requirements.txt

# 3. 配置 API Key（二选一）
# 方案 A：Claude（推荐，复用 Claude Code 的 key，无需额外配置）
#   已在 Claude Code 中登录即可，自动读取 ANTHROPIC_AUTH_TOKEN

# 方案 B：DeepSeek（更便宜）
export DEEPSEEK_API_KEY=your_key
```

### 启动 Web 界面

```bash
uv run python -m src.aiarmy.web
# 浏览器打开 http://localhost:7860
```

### 命令行回测

```bash
# 纯规则引擎（不需要 API key）
uv run python eval/backtest.py -v

# LLM 增强模式（需要 API key）
uv run python eval/backtest.py --llm -v
```

### 单文档测试

```bash
uv run python -c "
import asyncio
from src.aiarmy.graph import AuditPipeline
from src.aiarmy.io import to_text

text = to_text('训练集/可用/某种变电站设备红外测温辅助定位装置.docx')
pipeline = AuditPipeline(use_llm=False)
state = asyncio.run(pipeline.run(text, '综合评审'))
print(f'结果: {state.result.label}')
print(f'理由: {state.result.reason}')
"
```

## 系统架构

```
[上传 .docx] → doc-read CLI → [parse] → [match] → [judge] → JSON 结果
                                 文档解析   规则匹配   汇总裁决
```

- **parse**：文档 → 结构化字段（正则快模式 / LLM 深模式）
- **match**：逐规则评估，正则判结构 + LLM 判语义
- **judge**：汇总 verdicts，确定性裁决 + LLM 综合

## 评估结果

| 模式 | 综合准确率 | 立项申请书 | 计划任务书 |
|------|:---:|:---:|:---:|
| 纯规则引擎 | 68.4% | 100% (9/9) | 40% (4/10) |
| LLM 增强 | 待评测 | — | — |

- **通过 Recall（少数类）**：100%（4/4 通过样本不误判）
- 计划任务书 40% 是**诚实基线**——6 篇格式合规的难例需要 LLM 语义判断，不在正则中背答案
- 详见 `eval/backtest.py` 输出（混淆矩阵 + Precision/Recall/F1）

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

## 交付物

- `src/aiarmy/` — 运行时系统
- `rules/` — 规则库（7 条，YAML）
- `eval/backtest.py` — 完整评估脚本
- `design.md` — 系统设计文档
- `README.md` — 本文件

## 部署

### Docker → NAS

```bash
# 构建 & 启动
docker compose up -d --build

# 访问
http://localhost:7860
```

### NAS 远端部署

```bash
ssh nas-wan "cd /volume1/docker/aiarmy && git pull && docker compose up -d --build"
# 访问: http://100.66.1.1:7860 或 http://192.168.50.246:7860
```

## 许可

作业项目，内部使用。
