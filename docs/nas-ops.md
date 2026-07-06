# NAS 部署运维手册

> AiArmy Docker 部署的踩坑记录和操作 SOP
> 最后更新：2026-07-06 v6 部署

---

## 部署架构

```
本地 ──SCP/SSH──→ 服务器 ──docker compose──→ 容器 (python:3.12-slim)
                         │
                         └── Gradio share=True → gradio.live 公网隧道
```

## 部署 SOP

### 1. 推送代码到服务器

```bash
# 用 SSH pipe 绕过 scp 权限问题（某些 NAS 上 scp dest open 偶发失败）
cat src/aiarmy/web.py | ssh <host> "cat > /path/to/project/src/aiarmy/web.py"
cat src/aiarmy/graph.py | ssh <host> "cat > /path/to/project/src/aiarmy/graph.py"
```

### 2. 重建并重启容器

```bash
ssh <host> "cd /path/to/project && docker compose up -d --build"
```

**为什么必须 `--build`**：源码在镜像内（Dockerfile `COPY src/ src/`），不是 volume 挂载。仅有 `./logs` 是 volume。只 `docker compose restart` 不生效——跑的仍是旧镜像。

### 3. 验证

```bash
# 检查版本（footer 应显示 v6 / 并发 3 / 翻页浏览）
curl -s http://<host>:7860 | grep "并发 3"

# 检查公网 URL
ssh <host> "docker logs aiarmy 2>&1 | grep gradio.live"
```

---

## 已知问题与修复

### 问题 1：Gradio share 隧道失败

**现象**：
```
Could not create share link. Missing file: /root/.cache/huggingface/gradio/frpc/frpc_linux_amd64_v0.3
```

**原因**：容器重建后 `/root/.cache/` 丢失。frpc 二进制不在镜像层，是 Gradio 首次 `share=True` 时从 `cdn-media.huggingface.co` 下载的。

**为什么自动下载失败**：容器直连 huggingface.co 可能超时或被墙。

**修复步骤**：
```bash
# 1. 本地下载 frpc
curl -L -o /tmp/frpc_linux_amd64_v0.3 \
  "https://cdn-media.huggingface.co/frpc-gradio-0.3/frpc_linux_amd64"

# 2. 传到服务器并注入容器
cat /tmp/frpc_linux_amd64_v0.3 | ssh <host> \
  "cat > /tmp/frpc_v0.3 && \
   docker cp /tmp/frpc_v0.3 aiarmy:/root/.cache/huggingface/gradio/frpc/frpc_linux_amd64_v0.3 && \
   docker exec aiarmy chmod +x /root/.cache/huggingface/gradio/frpc/frpc_linux_amd64_v0.3"

# 3. 重启容器触发 share
ssh <host> "docker restart aiarmy"
```

**根治方案（TODO）**：在 Dockerfile 中预置 frpc 二进制，避免每次 rebuild 后手动注入。

### 问题 2：scp 到服务器偶发 `No such file or directory`

即使 `ssh <host> "ls /path/"` 确认目录存在，scp 仍可能报 `dest open: No such file or directory`。

**绕过方法**：使用 `cat | ssh cat >` 管道传输替代 scp（见上方部署 SOP 第 1 步）。

---

## 容器信息

| 项目 | 值 |
|------|-----|
| 容器名 | `aiarmy` |
| 镜像 | `python:3.12-slim` |
| 端口 | `7860:7860` |
| 重启策略 | `unless-stopped` |
| Volume | `./logs:/app/logs`（仅日志持久化） |

## 环境变量

通过 `.env` 文件注入（不进 Git）：
- `DEEPSEEK_API_KEY`：DeepSeek API 密钥

## 网络要求

- **gradio.live**（公网隧道）：需能访问 Gradio 隧道服务器
- **api.deepseek.com**（LLM 调用）：需能访问 DeepSeek Anthropic 兼容端点
- Gradio share 首次启动时需下载 frpc（约 12MB），之后缓存于容器文件系统
