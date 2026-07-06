# NAS 部署运维手册

> AiArmy Docker 部署的踩坑记录和操作 SOP
> 最后更新：2026-07-06 v6 部署

---

## 部署架构

```
本地 ──SCP/SSH──→ 服务器 ──docker compose──→ 容器 (python:3.12-slim)
                         │
                         └── 节点小宝内网穿透 → lisong.iepose.cn 公网域名
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

# 检查公网域名是否可访问
curl -s -o /dev/null -w "%{http_code}" https://lisong.iepose.cn
```

---

## 公网访问（节点小宝内网穿透）

域名 `lisong.iepose.cn` 通过节点小宝内网穿透指向 NAS `192.168.50.246:7860`。配置方法：

1. 节点小宝控制台 → 内网穿透 → 添加服务
2. 内网地址填 NAS 局域网 IP:端口，域名自定义前缀
3. 中转设备选 NAS（确保 7×24 在线）
4. 配置后约 20 秒生效

**注意**：内网穿透需要尊享版会员 + 实名认证。免费版不可用。

## 已知问题与修复

### 问题 1：scp 到服务器偶发 `No such file or directory`

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

- **lisong.iepose.cn**（节点小宝内网穿透）：需能访问节点小宝隧道服务器
- **api.deepseek.com**（LLM 调用）：需能访问 DeepSeek Anthropic 兼容端点
- Gradio share 首次启动时需下载 frpc（约 12MB），之后缓存于容器文件系统
