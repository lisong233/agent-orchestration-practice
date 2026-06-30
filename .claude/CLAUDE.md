# AI 军团 — Agent 编排作业

> 基于训练数据，构建多 Agent 编排系统：读取业务文档 → 发现隐含判断规则 → 输出审核结果 + 命中规则 + 判断依据

## 核心任务

1. **规则发现**：从 19 个训练样本（通过 4 / 不通过 15）中自动发现审核规则
2. **Agent 编排**：用 3 节点管线（parse→match→judge）编排审核流程
3. **泛化能力**：正则判结构 + LLM 判语义，禁止训练集指纹

## 训练集（2026-06-24 最终）

```
训练集/
├── raw/                        ← 源文件（只读，不可动）
│   ├── *.docx                  ← 13 原生 + 5 转换产物
│   ├── *.doc                   ← 7 原始 .doc（WPS 格式）
│   ├── *.zip                   ← 1 个作业附件
│   └── 训练集_审核结果.xlsx     ← ground truth 标签
├── 可用/                       ← 20 个 doc-read 解析入口
│   ├── *.docx (19)             ← 全部通过 doc-read 验证
│   └── 训练集_审核结果.xlsx     ← 标签文件
└── convert_text/               ← P1 产物：19 个 txt + 1 个 xlsx
    ├── *.txt (19)              ← doc-read 解析后的纯文本
    └── 训练集_审核结果.xlsx     ← 标签（复制）
```

> `训练集/` 整个目录已 gitignore，不进仓库。

### 标签分布

| 标签 | 数量 |
|------|------|
| 通过 | 4 |
| 不通过 | 15 |
| **合计** | **19** |

> 26 太阳能板斜拉线已与出题方确认删除。11 开关小车由主人重新导出为完整 docx（替换 rescue 文本）。

### 已知限制

- **SF6（14）**：重新保存后仅含封面页，正文缺失——出题方原始文件 document.xml 结构异常，无法修复。
- **计划任务书 doc 13/14**：文本层面与不通过文档无法区分（共用同一模板），纯规则引擎无法召回。

## 当前状态（2026-06-30 23:00）

P1 ✅ → P2 ✅ → P3 ✅ → v3 ✅ → **v4 harness 收尾 ✅**

### v4 完成项（handoff-2026-06-30-harness-finalize.md）

**P0 安全**：
1. ✅ `.env.example` 占位符化 + `.env` gitignore + `logs/` gitignore

**P1 Harness 修正**：
2. ✅ 文档类型由评委 UI 选择（Radio → doc_type_override 全链路）
3. ✅ Web 输出 JSON 对齐题目格式（id/dataset_type/matched_rules）
4. ✅ R-07 难例显式走 deepseek-v4-pro
5. ✅ LLM 不可靠路径 fallback 统一 = 不通过
6. ✅ matched_rules 确定性取自 verdicts（不靠 LLM 现编）
7. ✅ 审计日志落盘（audit_log.py + graph.py 集成）

**P2 鲁棒性**：
8. ✅ R-02 签名正则防占位符欺骗
9. ✅ R-07 看得到预算段落（追加定位逻辑）

**P3 验证**：
10. ✅ 反指纹测试：扰动年份/KPI/项目名后 label 不变
11. ✅ 合成样本测试：4/4 规则正反触发正确
12. ✅ Intent 路由测试：7/7 路由正确

**P4 部署**：
13. ✅ Dockerfile + docker-compose.yml（python:3.12-slim，python-docx 兜底）
14. ⏸ LangGraph 迁移（langgraph 包不可用，当前顺序 await 已正确，spec 确认"3 节点不需要状态机"）
15. ⏸ NAS 部署拿公网 URL（需主人操作 NAS）

### 诚实基线（v4）

| 模式 | 综合 | 立项申请书 | 计划任务书 |
|------|:---:|:---:|:---:|
| 纯规则 | 89.5% (17/19) | 100% (9/9) | 80% (8/10) |

通过 Recall 50%（2/4）—— v4 fallback 从严后，不可学习的 2 篇计划任务书"通过"无法召回。

### 待做

- [ ] NAS 部署拿公网 URL（题目硬要求）
- [ ] LLM 增强模式全量回测（需要 API key）
- [ ] LangGraph 迁移（langgraph 包可安装时）
