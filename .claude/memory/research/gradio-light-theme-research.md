# Gradio 6.x Light Theme — 防止系统深色模式覆盖

> 调研日期：2026-07-06 | 工具：Tavily MCP 多轮搜索 + 提取

---

## 核心结论

**Gradio 没有内置的 "force light mode" 参数。** 它的默认行为是跟随系统 `prefers-color-scheme` 媒体查询。要锁定 light mode，必须通过 JS 或 CSS 注入变通实现。以下列出已验证的方案，按推荐优先级排列。

---

## 具体问答

### Q1: 在 Gradio 6.x 中如何设置 light theme 并忽略 `prefers-color-scheme: dark`？

**最佳方案**：通过 `launch()` 的 `js=` 参数注入 JS，在页面加载时设置 URL 参数 `?__theme=light`。

原理：Gradio 前端的 `handle_darkmode()` 函数（`Blocks.svelte` L375-394）优先检查 URL 参数 `__theme`：
- `__theme=dark` → 调用 `darkmode()`
- `__theme=system` → 调用 `use_system_theme()`
- 无参数 / `__theme=light` → 保持 light（不调用任何切换函数）
- 若 `__theme` 参数不存在 → 默认调用 `use_system_theme()`（这就是被系统 dark mode 覆盖的原因）

```python
import gradio as gr

with gr.Blocks() as demo:
    gr.Markdown("# Hello World")

demo.launch(
    theme=gr.themes.Soft(),
    js="""
    () => {
        const params = new URLSearchParams(window.location.search);
        if (!params.has('__theme')) {
            params.set('__theme', 'light');
            window.location.search = params.toString();
        }
    }
    """
)
```

**备选方案 A**：通过 `head=` 参数注入 CSS，设置 `color-scheme: light only`（防止浏览器强制深色模式）：

```python
import gradio as gr

with gr.Blocks() as demo:
    gr.Markdown("# Hello World")

demo.launch(
    theme=gr.themes.Soft(),
    head="""<style>:root { color-scheme: light only; }</style>"""
)
```

**备选方案 B**：组合使用（最鲁棒）：

```python
import gradio as gr

with gr.Blocks() as demo:
    gr.Markdown("# Hello World")

demo.launch(
    theme=gr.themes.Soft(),
    head="""<style>:root { color-scheme: light only; }</style>""",
    js="""
    () => {
        const params = new URLSearchParams(window.location.search);
        if (!params.has('__theme')) {
            params.set('__theme', 'light');
            window.location.search = params.toString();
        }
    }
    """
)
```

### Q2: `gr.themes.Soft()` 或任何内置主题能强制 light mode 吗？

**不能。** 所有内置主题（`Base`、`Default`、`Soft`、`Glass`、`Monochrome`、`Ocean`、`Citrus`、`Origin`）都只是颜色变量定义，不控制 dark/light 切换逻辑。主题有 `_dark` 后缀的变量（如 `button_primary_background_fill_dark`）是因为 Gradio 主题系统同时定义了 light 和 dark 两套变量，但切换哪一套是由前端的 `handle_darkmode()` + `use_system_theme()` 决定的，与主题对象本身无关。

### Q3: Gradio 官方有没有锁定 light-only 的 API？

**没有。** 截至 Gradio 6.x（以及此前所有版本），没有 `force_light=True` 或 `color_mode="light"` 这样的参数。官方的 theme 参数只控制颜色变量，不控制 dark/light 模式切换。

社区中已有长期讨论（见 Issues #7384、#7631、#10628），官方尚未提供此功能。

### Q4: 社区对 "Gradio 即便设了 light theme 仍然显示 dark mode" 的解决方案

社区（Hugging Face Forums、GitHub Issues）共识方案：

1. **URL 参数法**（最广泛使用）：在 URL 后追加 `?__theme=light`
2. **JS 注入法**：通过 `launch(js=...)` 或 `launch(head=...)` 注入脚本
3. **Gradio Lite**：`<gradio-lite theme="dark">` 标签支持 `theme` 属性

在 Hugging Face Forums 的讨论中（2023-11，4 条回复，19644 次浏览），用户报告的唯一可靠方法是 URL 参数。

### Q5: `gr.Blocks()` 或 `launch()` 是否有 `js=` 或 `head=` 参数注入 CSS/JS？

**Gradio 6.x（最新）**：
- `launch(js=...)`：接收一个 JS 函数字符串，页面加载时自动执行
- `launch(head=...)`：接收 HTML 字符串，注入到页面 `<head>` 中（可放 `<style>`、`<script>`、`<meta>` 等）
- `launch(css=...)`：接收 CSS 字符串
- `launch(css_paths=...)`：接收 CSS 文件路径

**注意 Gradio 6 迁移**：这些参数在 Gradio 5.x 中位于 `gr.Blocks(theme=..., css=...)` 构造函数，在 Gradio 6.x 中全部移到了 `demo.launch(theme=..., css=...)`。

### Q6: Gradio 6 中 `launch()` 是否有 `theme` 参数？

**有。** Gradio 6 中 `theme` 参数在 `launch()` 中：

```python
# Gradio 6.x 正确用法
with gr.Blocks() as demo:
    ...
demo.launch(theme=gr.themes.Soft())
```

对比 Gradio 5.x 旧用法：
```python
# Gradio 5.x 旧用法
with gr.Blocks(theme=gr.themes.Soft()) as demo:  # Gradio 6 不再支持
    ...
demo.launch()
```

### Q7: Gradio 主题系统是否使用 CSS 自定义属性控制 `color-scheme` 或 `prefers-color-scheme`？

**间接使用。** Gradio 的主题系统完全基于 CSS 自定义属性（`--color-scheme`、`--primary-*`、`--button-*` 等），但 **不设置** `prefers-color-scheme` 媒体查询或 `color-scheme` 属性。dark/light 切换是由前端的 `handle_darkmode()` JavaScript 函数控制的：

1. 页面加载 → `handle_darkmode()` 执行
2. 无 `__theme` 参数 → 调用 `use_system_theme()`
3. `use_system_theme()` 监听 `window.matchMedia("(prefers-color-scheme: dark)")`
4. 如果系统是 dark mode → 往 DOM 中添加 `.dark` 类
5. Gradio 的 CSS 变量在 `.dark` 选择器下引用 `_dark` 后缀的值

因此要彻底锁定 light mode，必须在前端层面（通过 URL 参数或 JS）阻止第 3-4 步发生。仅设置 CSS 不够。

---

## 关键来源

| 来源 | URL | 可信度 |
|------|-----|--------|
| Gradio 6 Migration Guide (官方) | https://gradio.app/guides/gradio-6-migration-guide | 高 — 官方文档 |
| Gradio Custom CSS and JS (官方) | https://gradio.app/guides/custom-CSS-and-JS | 高 — 官方文档 |
| Gradio Theming Guide (官方) | https://gradio.app/guides/theming-guide | 高 — 官方文档 |
| GitHub Issue #7384 — Force dark mode | https://github.com/gradio-app/gradio/issues/7384 | 中 — 社区但含源码引用 |
| GitHub Issue #10628 — Theme stuck dark | https://github.com/gradio-app/gradio/issues/10628 | 中 — 用户报告 |
| Hugging Face Forum #22314 | https://discuss.huggingface.co/t/is-there-a-way-to-force-the-dark-mode-theme-in-gradio/22314 | 中 — 含 Blocks.svelte 源码片段 |
| Gradio Lite 文档 | https://gradio.app/4.44.1/guides/gradio-lite | 中 — 旧版文档但 `<gradio-lite theme>` 属性有效 |
| Stack Overflow — force light mode | https://stackoverflow.com/questions/76533608/force-light-mode-when-browser-is-set-to-dark-mode | 高 — 通用 Web 技术 |

---

## 完整工作代码示例

```python
import gradio as gr

# 注入到 <head> 的 CSS — 防止浏览器本身强制深色模式
head_css = """
<style>
  :root { color-scheme: light only; }
</style>
"""

# 注入的 JS — 阻止 Gradio 调用 use_system_theme()
theme_js = """
() => {
    const params = new URLSearchParams(window.location.search);
    if (!params.has('__theme')) {
        params.set('__theme', 'light');
        window.location.search = params.toString();
    }
}
"""

with gr.Blocks() as demo:
    gr.Markdown("""
    # 我的应用
    无论系统是 light 还是 dark，这里始终显示 light 主题。
    """)
    inp = gr.Textbox(label="输入")
    out = gr.Textbox(label="输出")
    inp.change(fn=lambda x: f"你输入了: {x}", inputs=inp, outputs=out)

demo.launch(
    theme=gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="gray",
        neutral_hue="gray",
    ),
    head=head_css,
    js=theme_js,
)
```

---

## 注意事项与版本说明

| 注意点 | 详情 |
|--------|------|
| **Gradio 版本** | 以上方案适用于 Gradio 5.x 和 6.x。Gradio 6 中参数从 `Blocks()` 移到了 `launch()`，逻辑不变 |
| **URL 重载** | `js=` 方案中 `window.location.search = ...` 会触发页面重载（一次闪白）。如果接受闪白则用此方案；不能接受则用纯 CSS 方案或改用手动 DOM 操作 |
| **CSS 局限性** | `color-scheme: light only` 只阻止浏览器自动深色模式（如 Chrome/Samsung 强制深色），**不阻止 Gradio 自身的深色切换**。必须配合 URL 参数方案 |
| **嵌入式 Spaces** | Hugging Face Spaces 嵌入的 `<gradio-app>` 标签支持 `theme_mode="light"` 属性 |
| **Gradio Lite** | `<gradio-lite>` 标签支持 `theme="dark"` / `theme="light"` 属性直接控制 |
| **CSS 选择器风险** | 官方警告：自定义 CSS/JS 中使用的查询选择器可能跨版本失效，因为 Gradio HTML DOM 可能变化 |

---

## 未验证/存疑点

- Gradio 6.x 更高版本（如 6.1+）是否已添加官方 `force_light` 参数？截至 2026-07-06 未见相关公告
- 部分浏览器（如 Samsung Internet）有激进的强制深色模式，`color-scheme: light only` 可能不够，需更强的 CSS `!important` 覆盖
- 如果 Gradio 未来修改 `handle_darkmode()` 的 URL 参数检查逻辑，JS 注入方案可能失效（但该逻辑自 Gradio 4.x 以来未变）
