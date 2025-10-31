# 使用 Python 3.11 官方镜像作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install uv

# 复制 requirements 文件
COPY requirements.txt .

# 使用 uv 安装 Python 依赖
# 同时安装 supervisor
RUN uv pip install --system -r requirements.txt supervisor

# 复制项目文件
COPY . .

# 复制 supervisord 配置文件和启动脚本(放在 COPY . . 之后以避免被覆盖)
COPY supervisord.conf /app/supervisord.conf
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# 创建必要的目录
RUN mkdir -p media static nltk_data /var/log

# 暴露端口
EXPOSE 8000

# 设置启动脚本为入口点
ENTRYPOINT ["/app/entrypoint.sh"]