# ─────────────────────────────────────────────
# 物流风控系统 (Logistics Risk) - Dockerfile
# 多阶段构建: Python 3.11 + FastAPI + XGBoost
# ─────────────────────────────────────────────

# === 构建阶段 ===
FROM python:3.11-slim AS builder

WORKDIR /build

# 安装编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖声明
COPY requirements.txt .

# 安装 Python 依赖到 /install 目录 (用于最终阶段 copy)
RUN pip install --no-cache-dir --target=/install -r requirements.txt

# === 运行阶段 ===
FROM python:3.11-slim AS runtime

WORKDIR /app

# 安装运行时依赖 (aiomysql 需要 libmysqlclient)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmariadb3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制 Python 依赖
COPY --from=builder /install /usr/local/lib/python3.11/site-packages

# 复制项目代码
COPY . .

# 创建日志目录
RUN mkdir -p /app/logs

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

# 默认命令: gunicorn + uvicorn
CMD ["gunicorn", "scripts.main:app", "--bind", "0.0.0.0:8000",
     "--worker-class", "uvicorn.workers.UvicornWorker",
     "--workers", "2", "--timeout", "120",
     "--access-logfile", "logs/access.log",
     "--error-logfile", "logs/error.log"]