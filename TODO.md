# TODO — 结项后目录归置

> 📌 结项后执行。收益：语义正确；代价：session 记忆旧路径失效。

## 目标结构

```
agent-learning/
├── AiArmy/                               ← 上层概念壳（无 .git）
│   ├── AgentOrchestrationPractice/        ← Agent 编排（当前 AiArmy/ 下沉）
│   └── SupplyDemandMatching/              ← 供需对接（移入）
└── Pricing/                               ← 造价（不动）
```

## 操作步骤

```powershell
cd D:\ClaudeWorkspace\agent-learning

# 1. 当前 AiArmy → 临时改名
Rename-Item AiArmy AiArmy_tmp

# 2. 建新壳 + 子目录
New-Item -ItemType Directory -Path AiArmy\AgentOrchestrationPractice -Force

# 3. 旧内容（含 .git）下沉一级
Get-ChildItem AiArmy_tmp -Force | Move-Item -Destination AiArmy\AgentOrchestrationPractice -Force

# 4. SupplyDemandMatching 移入
Move-Item SupplyDemandMatching AiArmy\ -Force

# 5. 清理临时目录
Remove-Item AiArmy_tmp -Force
```

## 执行后需更新

- [ ] `agent-learning/CLAUDE.md` — 架构图 + 项目表路径
- [ ] `agent-learning/ARCHIVED.md` — SupplyDemandMatching 路径
- [ ] `AiArmy/CLAUDE.md`（新建）— 两个子项目概述

## Session 记忆

改名后 CC session 记忆（`~/.claude/projects/`）会丢失。不考虑迁移：
- claude-mem 语义搜索不依赖目录路径，重要知识都在记忆里
- session 记录是过程数据，结项后价值有限
- 社区有 `claude-mv`（macOS）等方案，但 Windows 上手动改 JSONL 路径引用风险大于收益
