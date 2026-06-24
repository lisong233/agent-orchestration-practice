# 强模型指导弱模型做编码：社区实践调研

> 📅 2026-06-23 · 糯米调研（主 agent 直接多轮 Tavily 搜索 + 交叉验证，未 spawn 子 agent）
> 🎯 回答：用 Opus 规划 + DeepSeek 实施，社区有哪些成熟模式？交接方式怎么选？
> 📌 一句话结论：**「文档交接 vs 新 session」是伪命题——社区主流是「文档交接 + 干净 session」两者结合。**

---

## 0. TL;DR（先看这个）

| 你的纠结 | 社区答案 |
|---------|---------|
| 文档交接 还是 新开 session？ | **都要**。强模型把规划写成结构化文档 → 弱模型在**干净 session**里读文档执行。两者是组合，不是二选一 |
| 共享上下文行不行？ | **不行**。弱模型会被强模型的长篇推理"淹没"。社区原话："Clean trajectory beats arguing with polluted context" |
| spec 要写多详细？ | **越低抽象层越好**（精确到单个文件/函数级），但**要 terse**（高密度，不啰嗦）。Martin Fowler 实测：抽象层越低，LLM 解释步骤越少，出错越少 |
| 弱模型为什么开放决策会垮？ | 社区共识："strong execution amplifies weak direction"——弱模型高保真执行 spec，spec 错了它也照错执行。所以**决策必须强模型做完、写死在 spec 里** |

这套模式有四个等价的社区命名，本质都是**「分离推理与执行」**：
- **architect / editor**（Aider）
- **manager / builder** 或 **draft / editor**（社区俗称）
- **Orchestrator / Boomerang**（Roo Code）
- **Plan / Act**（Cline）

---

## 1. Aider architect/editor 模式（最直接相关，2024-09 首创）

### 工作原理
Aider 把一个编码任务拆成**两次 LLM 请求**：
1. **Architect 模型**：描述"怎么解决这个问题"，用自然语言随便说，不管格式
2. **Editor 模型**：拿 Architect 的方案，转成**具体的文件编辑指令**（diff 格式）

官方原话（aider.chat/docs）：
> "Certain LLMs aren't able to propose coding solutions and specify detailed file edits all in one go. For these models, architect mode can produce better results than code mode by pairing them with an editor model."

### 核心洞察（为什么要分离）
> "前沿模型推理brilliantly，但有时会搞砸结构化 diff 输出；便宜模型对 diff 很精准，但规划能力弱。"（deployhq.com/guides/aider, 2026）

**= 推理和"产出格式正确的代码"是两种不同能力，分给不同模型各司其职。**

### 实测数据（关键）
- **SOTA 85%**：o1-preview 当 architect + DeepSeek 或 o1-mini 当 editor（aider 官方 benchmark）
- architect/editor 配对**显著提升**了许多模型的单独基线分
- 2026 推荐配对：
  ```bash
  aider --architect --model opus --editor-model sonnet      # Claude 系
  aider --architect --model gpt-5 --editor-model gpt-5-mini  # OpenAI 系
  aider --model deepseek/deepseek-reasoner                    # DeepSeek（便宜 20 倍）
  ```
- `--reasoning-effort medium` 给 architect，editor 关掉或调 low

### 代价
两次请求 → 更慢、更贵（但质量换来了）。`--auto-accept-architect` 可跳过人工确认，让 plan 直接喂给 editor。

### 对本场景的启示
**Opus 当 architect（写 spec/plan）+ DeepSeek 当 editor（写代码）完全是这个模式的标准用法。** 你已经在做对的事。Aider 的经验说明这套不是理论，是 benchmark 验证过的 SOTA。

---

## 2. Roo Code Orchestrator / Boomerang Tasks（2025，正面回答"新 session"问题）

### 工作原理
- **Orchestrator 模式**接到复杂任务 → 拆成子任务 → 用 `new_task` 工具委派给专门模式（Code / Architect / Debug）
- **每个子任务跑在自己独立的 context 里**（关键！）
- 子任务完成 → 返回摘要给 Orchestrator，继续下一个

官方原话（roocodeinc.github.io）：
> "Each subtask runs in its own context, often using a different Roo Code mode tailored for that specific job."

### 两个关键设计（直接回答你的疑问）
1. **委派时传"comprehensive instructions"**（note.com 实测指南）：
   > "For each subtask, use the `new_task` tool to delegate... provide comprehensive instructions in the `message` parameter."
   → **= 子任务的指令必须自包含、完整。这就是"文档交接"，只不过通过 message 参数传。**

2. **每模式可配不同模型**（DataCamp 教程）：
   > "Assign different AI models to specific modes, like using o3 for architecture planning and Claude Sonnet 4 for code execution."
   → **= 强模型规划、弱模型执行，工具原生支持。**

3. **Orchestrator 自己不读写文件**——只协调。强制了"规划与执行分离"。

### 对本场景的启示
Roo Code 用工程实践证明了：**子任务在干净独立 context 里跑 + 完整指令交接，是处理复杂工作流的标准架构。** 这正是"新 session + 文档交接"的组合，不是二选一。

---

## 3. Cline Plan/Act + Memory Bank（交接的工程细节最丰富）

### Plan/Act 分离
- **Plan 模式**：只读不写、讨论方案、出 implementation_plan.md
- **Act 模式**：执行实现
- 切换前 plan 阶段的所有讨论都会帮助 Act 阶段做对

### 交接的具体机制（社区踩坑总结，含金量最高）
来自 Cline 官方 + LinkedIn 实践帖：

1. **70-80% context 容量就该开新 task**，别等爆满（会"amnesia"健忘）
2. **`/newtask` 只携带 essentials**：plan、decisions、relevant files、next steps —— 不是全量历史
3. **Memory Bank 模式**：跨 session 的持久化文档
   - `projectbrief.md`（项目目标）
   - `activeContext.md`（当前状态，每次 session 后更新）
   - `progress.md`（里程碑）
4. **金句**（LinkedIn @clinebot）：
   > "Thread goes sideways? Don't course-correct. Edit the message that missed the requirement. **Clean trajectory beats arguing with polluted context.**"
   → **上下文污染了，别在里面硬掰。重开干净的，比跟脏上下文较劲强。**
5. **金句2**：
   > "Bigger windows help, but **the harness matters more**. Keep only what matters in view."
   → **大 context 窗口不是答案，脚手架（怎么组织交接）才是。**

### Memory Bank vs Spec 的区别（Martin Fowler 厘清）
| | 作用域 | 例子 |
|---|-------|------|
| **Memory Bank** | 跨所有 session 都相关 | AGENTS.md、architecture.md、项目总览 |
| **Spec** | 只跟当前这个任务相关 | story-324.md、feature-x/plan.md |

→ **对本作业**：v2 蓝图 = Memory Bank（项目级常驻），执行附录的某个 Phase 工单 = Spec（任务级）。

---

## 4. Spec-Driven Development（spec 该怎么写）

### 核心理念
Spec 是 source of truth，先写规格再让 AI 执行。工具：GitHub Spec Kit、Kiro、Tessl。

### 最关键的实践结论（Martin Fowler, martinfowler.com）
> "把 spec 放在**很低的抽象层**（per code file），能减少 LLM 的步骤和解释，因此减少出错几率。"

但同时——
> 即使在这么低的抽象层，我还是看到了非确定性：同一个 spec 生成多次，结果不同。要不断迭代 spec 让它更具体来提高可复现性。

### spec 要 terse（HN 高赞）
> "保持 guide 简短。太长会白白吃 context。LLM 给人写东西时很啰嗦。生成 guide 时我总加一句'be succinct and terse, don't be verbose'，把它变成高密度上下文文档。"

### 最重要的失败模式（augmentcode.com）
> "AI coding agents build exactly what specs tell them to, **even when specs are wrong**. **Strong execution amplifies weak direction.**"
> 在 spec 执行前 review 它，永远比事后拆解一个"自信地写错了、散落在几十个文件里"的实现便宜。

→ **这是整个调研对你最重要的一句话**：弱模型会高保真地执行你的 spec，所以**错误的决策不会被弱模型纠正，只会被放大**。这就是为什么"决策必须由强模型在 spec 阶段做完"。

### 什么时候不该用 SDD（arXiv:2602.00180）
throwaway 原型、solo 短命项目、探索性编码、简单 CRUD —— spec 投入 > 收益。

---

## 5. 弱模型为什么"开放决策垮、填空式行"（社区共识）

把各家观点汇总成因果链：

```
弱模型擅长：模式识别、高保真执行明确指令、产出格式正确的代码（diff）
弱模型不擅长：消歧、架构权衡、在 spec 留白处自主决策

→ 所以：
  ✅ 给它「填空式」任务（spec 写死了做什么、怎么做，它填实现）→ 表现好
  ❌ 给它「开放式」任务（让它自己决定架构/选型/裁决逻辑）→ 容易垮
  且垮的方式很隐蔽：它会自信地写出语法正确但方向错的代码（strong execution + weak direction）
```

TechChannel 原话：
> "AI agents are literal-minded; they excel at pattern recognition but struggle with ambiguity. A bloated or unclear context can lead to misinterpretation."

→ **对应你给 V4 Pro 的执行附录**：你把 prompt 模板写死、judge 裁决逻辑写死（消除了开放决策），把"照骨架填函数体"留给它（填空式）—— **完全符合社区共识，方向对了。**

---

## 6. 成本与效果权衡

| 任务类型 | 给谁 | 依据 |
|---------|------|------|
| 架构设计、技术选型、spec 撰写、裁决逻辑 | **强模型（Opus）** | 开放决策，错了会被放大 |
| 写 prompt 模板 | **强模型** | 质量命脉，弱模型自创易垮 |
| 照骨架填函数、机械重构、格式化、写 diff | **弱模型（DeepSeek）** | 填空式，便宜 20 倍 |
| review 弱模型的产出 | **强模型** | 形成 plan→execute→review 闭环 |

- Aider 实测：DeepSeek reasoner 在 polyglot benchmark 74.2%，约 $1.30/run，比前沿模型**便宜 20 倍**
- architect/editor 配对比单模型贵（两次请求），但质量提升值得

---

## 7. 针对「Opus 规划 + DeepSeek 实施」的具体推荐

结合本作业（AiArmy）现状，落地建议：

### 7.1 交接架构（采用「文档交接 + 干净 session」）
```
Opus（architect）            DeepSeek V4 Pro（editor/builder）
  │                                  │
  ├─ 写 v2 蓝图（Memory Bank 级）──────┤ 开干净 session
  ├─ 写执行附录（含死 prompt）─────────┤ 读这两份文档
  ├─ 按 Phase 写任务工单（Spec 级）────┤ 照工单执行单个 Phase
  │                                  │ 完成 → 提交 + 写 progress
  └─ review 产出 → 修正工单 ←──────────┘ 返回
       （plan → execute → review 闭环）
```

### 7.2 五条铁律（从社区提炼，直接执行）
1. **干净 session 执行**：DeepSeek 不要继承 Opus 的长篇规划对话，只读文档。对应"clean trajectory beats polluted context"
2. **spec 低抽象 + terse**：工单精确到文件级（如"实现 app/agents/parse.py 的 run()"），但高密度不啰嗦
3. **决策全在 Opus 这边做完**：留白处弱模型会乱填。prompt、裁决逻辑、选型必须写死（你已做对）
4. **execute 前 review spec，不是 execute 后**：spec 错了便宜地改 spec，别等弱模型写错一堆文件
5. **一个 Phase 一个 session**：context 到 70% 就开新的，用 progress.md 交接。别让单个 session 拖太长

### 7.3 工具选择（可选）
- 想要工具原生支持这套模式 → **Aider**（`--architect --model opus --editor-model deepseek`）或 **Roo Code**（Orchestrator + 配 profile）
- 想纯手工控制 → 就用现在的方式：Opus 写文档 → 手动开 DeepSeek session 喂文档。**对作业这种规模，手工足够，不必引入新工具**

### 7.4 对照检查：你已经做对的
- ✅ 写了分层文档（蓝图=Memory Bank，附录=execution spec）
- ✅ prompt 模板写死（消除弱模型最易垮的开放创作）
- ✅ judge 裁决逻辑写死在 prompt 铁律里
- ✅ 给了每步验收命令（让弱模型知道"算不算做完"）

### 7.5 还可以补强的
- ⬜ 把执行附录的 Phase 拆成**独立工单**（一个 Phase 一个 .md），让 DeepSeek 一次只读一个，context 更干净
- ⬜ 每个工单顶部写死"开干净 session 读我，别继承之前对话"
- ⬜ 约定 progress 文件（如 `docs/progress.md`），DeepSeek 每完成一个 Phase 更新，Opus review 时读它

---

## 参考来源

| 主题 | 来源 |
|------|------|
| Aider architect/editor 原理 + SOTA | aider.chat/2024/09/26/architect.html · aider.chat/docs/usage/modes.html |
| Aider 2026 模型配对 | deployhq.com/guides/aider |
| architect-editor 模式综述（含 Devin/Cursor/Claude Code 对比） | github.com/pydantic/pydantic-ai-harness/issues/92 |
| Roo Code Boomerang/Orchestrator | roocodeinc.github.io/Roo-Code/features/boomerang-tasks · note.com/singlecores |
| Roo vs Cline 对比 + 多模型配置 | datacamp.com/tutorial/roo-code |
| Cline Memory Bank | docs.cline.bot/best-practices/memory-bank |
| Cline 上下文管理（newtask/deep-planning） | LinkedIn @clinebot |
| Cline new_task 交接协议 | modelmesh.gitbook.io/cline-zhong-wen-ban-docs |
| SDD 三工具对比（Kiro/spec-kit/Tessl）+ Memory Bank vs Spec | martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html |
| SDD 失败模式（strong execution amplifies weak direction） | augmentcode.com/tools/best-ai-spec-review-tools |
| SDD 学术综述 | arXiv:2602.00180 |
| spec 要 terse | news.ycombinator.com/item?id=45935763 |
| 上下文工程 | techchannel.com/sdd-and-context-engineering · thoughtworks.medium.com/spec-driven-development |

---

> *糯米 2026-06-23 · 社区的话总结成一句：分离推理与执行，干净上下文喂高密度 spec，决策强模型做完别留白给弱模型喵~*
