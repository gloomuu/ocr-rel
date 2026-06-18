# ==============================================================================
# 阶段 1: 基础环境（安装系统底层依赖，两阶段共享）
# ==============================================================================
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# ==============================================================================
# 阶段 2: 构建阶段（创建虚拟环境并安装依赖）
# ==============================================================================
FROM base AS builder

# 创建虚拟环境
RUN python -m venv /opt/venv
# 激活虚拟环境（后续的 pip 都会安装到这里）
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md ./

# 使用 BuildKit 缓存，并升级 pip
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

# 这一步需要确保你的 pyproject.toml 里面确实写了 uvicorn 依赖。
# 如果写了，使用下面这种标准的、不会报错的离线依赖安装方式：
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install . -i https://pypi.tuna.tsinghua.edu.cn/simple || true

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e .

# ==============================================================================
# 阶段 3: 运行阶段
# ==============================================================================
FROM base AS runtime

RUN useradd --create-home --shell /usr/sbin/nologin appuser && \
    chown -R appuser:appuser /app

# [核心修改]：直接拷贝完整的虚拟环境，保证全套二进制文件完整
COPY --from=builder /opt/venv /opt/venv
COPY pyproject.toml README.md ./
COPY src ./src

# 将虚拟环境的 bin 目录加入环境，这样 appuser 就能完美调用 uvicorn
ENV PATH="/opt/venv/bin:$PATH"

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "ocr_rel.main:app", "--host", "0.0.0.0", "--port", "8000"]