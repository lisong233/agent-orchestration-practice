FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY src/ src/
COPY rules/ rules/
COPY design.md README.md ./

# 创建日志目录
RUN mkdir -p logs

# 暴露 Gradio 默认端口
EXPOSE 7860

# 启动 Web 服务
CMD ["python", "-m", "src.aiarmy.web"]
