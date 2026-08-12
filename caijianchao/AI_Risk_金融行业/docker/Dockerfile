# =============================================================================
# AI_Risk Dockerfile (P4-L3 + P4-L4 2026-08-08)
# 位置: docker/Dockerfile
# 多阶段构建: builder 装依赖, runtime 只拷 wheel 过来
# 用 gunicorn + uvicorn worker 跑生产 (4 workers)
#
# 构建: docker build -t ai-risk -f docker/Dockerfile .
# =============================================================================

# ---- 阶段 1: builder ----
FROM python:3.11-slim AS builder

WORKDIR /app

# 系统依赖 (mysqlclient 编译需要 gcc; 我们用 pymysql/aiomysql 不需要)
# 2026-08-10: deb.debian.org 官方源在当前网络不可达(502), 切换到阿里云镜像
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 用 uv 安装依赖 (与项目 uv 工作流一致: uv/pyproject.toml + uv.lock 已本地 uv sync 验证)
# 替代 pip install -r requirements.txt
# 注意: 本地 uv sync 的是 Windows wheel, Linux 容器需重新下载 Linux wheel;
#       uv.lock 内 URL 指向 files.pythonhosted.org (当前网络不可达), 故先从锁文件
#       离线导出固定版本 (uv export --frozen), 再从阿里云镜像下载 (UV_DEFAULT_INDEX)
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ uv
ENV UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/
COPY uv/pyproject.toml uv/uv.lock ./
RUN uv export --frozen --no-hashes -o /tmp/requirements.lock.txt \
    && uv venv /app/.venv \
    && uv pip install --python /app/.venv/bin/python -r /tmp/requirements.lock.txt


# ---- 阶段 2: runtime ----
FROM python:3.11-slim

WORKDIR /app

# 创建非 root 用户跑应用
RUN useradd --create-home --shell /bin/bash app
USER app

# 从 builder 复制 uv 虚拟环境 (uv sync 生成于 /app/.venv)
COPY --from=builder --chown=app:app /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH

# 拷应用代码
COPY --chown=app:app . .

# 暴露端口
EXPOSE 8000

# 健康检查 (用 /docs 路径, 比 / 更快)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs').read()" || exit 1

# 启动: gunicorn + uvicorn worker (4 workers)
# 注: --reload 仅开发用, 生产要去掉
CMD ["gunicorn", "scripts.main:app", \
     "-w", "4", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-b", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--timeout", "120"]
