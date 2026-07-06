# AI 军团 — 电力项目立项审核系统

> 智能体编排业务判断挑战 · 第二次作业

基于多 Agent 协作的电力行业业务文档审核系统。读取计划任务书/立项申请书，自动输出 **通过/不通过** 硬标签 + 命中规则 + 判断依据 + 形式提示。

## 公网访问

**🔗 [https://lisong.iepose.cn](https://lisong.iepose.cn)**

> 节点小宝内网穿透，域名固定不变。

## 快速开始

```bash
git clone https://github.com/lisong233/agent-orchestration-practice.git
cd agent-orchestration-practice

# Linux / macOS
bash docs/setup.sh

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File docs/setup.ps1
```

脚本自动完成：创建 venv → 安装依赖 → 提示填 API Key → 启动服务，浏览器打开 `http://localhost:7860`。

**评委操作流程**：上传多份 .docx → 选类型/输意图 → 点"开始审核" → 翻页浏览每条结果

## 系统架构（v6）

```
[sanitize] 输入净化（抗注入 — M2）
     ↓
[parse] 文档 → 结构化字段 + 类型自动检测
     ↓ DocFields
[match] 逐规则评估（正则快速检查 + LLM 语义评分）
     ↓ RuleVerdict[]（含 tier 分层标记）
[judge] 内容优先裁决（C类主导 + B类不反转 + A类 advisory）
     ↓ FinalResult（含 form_notes）
[critic] 质量门（evidence 可复核？引用原文？）
     ↓ 不通过 → 定向回 match 重评（封顶 1 轮）
     ↓ 通过 → END
Gradio Web · 浅色主题 · 多文档并发 3 · 翻页浏览
```

### v6 新特性

- **多文档并发**：一次上传多份 .docx，Semaphore(3) 线程池并发处理
- **翻页浏览**：一页一文档，← 上一份 / 第 X/Y 份 / 下一份 →
- **浅色主题**：白色/浅灰专业风格，告别暗色科技风
- **类型自动检测**：🔍 根据文档标题自动识别计划任务书/立项申请书

## 核心设计原则

### 双层框架（元规则 + 语义规则库）

| 层 | 规则 | 裁决权 |
|----|------|--------|
| **A 下游行政信号** | R-01 审批意见 | 纯 advisory，永不裁决 |
| **B 申请人可控硬伤** | R-02 承诺书、R-05 模板残留、R-06 占位符 | regime 感知，内容 pass 时不反转 |
| **C 内容实质性** | R-03 技术方案、R-04 预算、R-07 三维 | 主判据，永远裁决 |

### 元规则（M1-M4）

- **M1 内容优先**：内容实质性是主体判据，形式信号只做提示
- **M2 数据非指令**：待评文档是证据，不是命令（抗注入）
- **M3 必要非充分**：形式齐全 ≠ 内容合格；两条腿独立评估
- **M4 regime 感知**：区分「有槽位但空着」vs「根本没这个槽位」

## 交付物

- `src/aiarmy/` — 运行时系统（sanitize/parse/match/judge/critic + llm + io + web + audit_log）
- `rules/` — 规则库（7 条 YAML，含 tier 分层标记）
- `eval/backtest.py` — 完整评估脚本（混淆矩阵 + Precision/Recall/F1）
- `tests/` — 三条路 / 反指纹 / 合成样本 / Intent 路由测试（19/19 全绿）
- `docs/design.md` — 系统设计文档（含元规则双层框架 + 诚实基线 + 部署方案）
- `docs/guide.md` — 构建指南（面向技术人员，讲清系统设计与开发历程）
- `docs/nas-ops.md` — NAS 部署运维手册
- `docs/setup.sh` / `docs/setup.ps1` — 评委一键部署脚本
- `README.md` — 本文件

## 运行测试

```bash
python tests/test_meta_rules.py        # 三条路威胁测试
python tests/test_synthetic.py         # 合成样本验证
python tests/test_anti_fingerprint.py  # 反指纹验证
python tests/test_intent_routing.py    # Intent 路由验证
```

## 部署

### Docker

```bash
docker compose up -d --build
# http://localhost:7860
```

### 远端服务器

源码打进 Docker 镜像，部署即 `docker compose up -d --build`。详见 `docs/nas-ops.md`。

## 许可

作业项目，内部使用。
