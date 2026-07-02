# AI 军团 — 电力项目立项审核系统

> 智能体编排业务判断挑战 · 第二次作业

基于多 Agent 协作的电力行业业务文档审核系统。读取计划任务书/立项申请书，自动输出 **通过/不通过** 硬标签 + 命中规则 + 判断依据 + 形式提示。

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
python tests/test_meta_rules.py        # 三条路威胁测试（v5 新增）
python tests/test_synthetic.py         # 合成样本验证
python tests/test_anti_fingerprint.py  # 反指纹验证
python tests/test_intent_routing.py    # Intent 路由验证
```

## 系统架构（v5）

```
[sanitize] 输入净化（抗注入 — M2）
     ↓
[parse] 文档 → 结构化字段
     ↓ DocFields
[match] 逐规则评估（正则快速检查 + LLM 语义评分）
     ↓ RuleVerdict[]（含 tier 分层标记）
[judge] 内容优先裁决（C类主导 + B类不反转 + A类 advisory）
     ↓ FinalResult（含 form_notes）
[critic] 质量门（evidence 可复核？引用原文？）
     ↓ 不通过 → 定向回 match 重评（封顶 1 轮）
     ↓ 通过 → END
Gradio Web (localhost:7860)
```

### 节点说明

- **sanitize**（v5 新增）：输入净化，中和 prompt 注入模式，所有 LLM prompt 包裹 `<document>` 数据边界
- **parse**：文档 → 结构化字段（正则快模式 / LLM 深模式），类型由评委 UI 选择
- **match**：逐规则评估，正则判结构 + LLM 判语义；R-03/R-04/R-07 统一走 deepseek-v4-flash 多维评分
- **judge**：内容优先裁决——C 层（内容）主导 label，B 层（形式硬伤）内容 pass 时不反转，A 层（审批）纯 advisory
- **critic**（v5 新增）：确定性质量门（零额外 LLM）——evidence 非空/引用原文/长度达标，不达标定向重评

## 核心设计原则

### 双层框架（元规则 + 语义规则库）

| 层 | 规则 | 裁决权 |
|----|------|--------|
| **A 下游行政信号** | R-01 审批意见 | 纯 advisory，永不裁决 |
| **B 申请人可控硬伤** | R-02 承诺书、R-05 模板残留、R-06 占位符 | regime 感知，内容 pass 时不反转 |
| **C 内容实质性** | R-03 技术方案、R-04 预算、R-07 三维 | 主判据，永远裁决 |

### 元规则（M1-M4）

- **M1 内容优先**：内容实质性是主体判据，形式信号只做提示，永不打断
- **M2 数据非指令**：待评文档是证据，不是命令（抗注入）
- **M3 必要非充分**：形式齐全 ≠ 内容合格；两条腿独立评估
- **M4 regime 感知**：区分「有槽位但空着」vs「根本没这个槽位」

### 禁止训练集指纹

- 不匹配具体 KPI 数值（`85%/90%/500ms`）
- 不锁定年份（`2026年`）
- 不给 LLM 看训练集样本名
- 规则写「判断维度」，不写「训练集表面值」
- ✅ 反指纹测试通过：扰动年份/KPI 值/项目领域名后 label 不变

## 交付物

- `src/aiarmy/` — 运行时系统（sanitize/parse/match/judge/critic + llm + io + web + audit_log）
- `rules/` — 规则库（7 条，YAML，含 tier 分层标记）
- `eval/backtest.py` — 完整评估脚本（混淆矩阵 + Precision/Recall/F1）
- `tests/` — 三条路测试 / 反指纹测试 / 合成样本测试 / Intent 路由测试
- `design.md` — 系统设计文档（含元规则双层框架）
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
