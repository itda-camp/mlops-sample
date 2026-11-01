FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
# uv.lock 에 고정된 버전 그대로, 개발용(pytest 등) 없이 설치
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-cache
ENV PATH="/app/.venv/bin:$PATH"

COPY api/ api/

ARG MODEL_IMPL=rule
ENV MODEL_IMPL=${MODEL_IMPL}

EXPOSE 8080
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8080"]

