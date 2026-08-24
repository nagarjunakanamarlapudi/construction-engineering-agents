FROM python:3.12.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.8.14 /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY data ./data
COPY sql ./sql
RUN uv sync --frozen --no-dev

EXPOSE 8011
CMD ["uv", "run", "uvicorn", "civil_copilot.api.main:app", "--host", "0.0.0.0", "--port", "8011"]
