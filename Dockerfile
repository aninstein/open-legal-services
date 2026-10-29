# syntax=docker/dockerfile:1.6
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_DATA_DIR=/app/data LEGAL_WEB_DIR=/app/web
WORKDIR /app
COPY pyproject.toml ./
COPY vendor/deerflow ./vendor/deerflow
RUN --mount=type=cache,target=/root/.cache/pip \
    python -c 'import tomllib; from pathlib import Path; p=tomllib.loads(Path("pyproject.toml").read_text()); Path("/tmp/requirements.txt").write_text("\n".join(p["project"]["dependencies"]) + "\n")' && \
    pip install -r /tmp/requirements.txt \
    ./vendor/deerflow/deerflow-extension-api-e9074b7.tar.gz \
    ./vendor/deerflow/deerflow-harness-e9074b7.tar.gz \
    'langchain-openai>=1.0,<2.0'
COPY src ./src
COPY web ./web
RUN pip install --no-deps .
RUN useradd --create-home --uid 10001 legal && mkdir -p /app/data && chown legal:legal /app/data
USER legal
EXPOSE 8787
CMD ["uvicorn", "legal_service.app:app", "--host", "0.0.0.0", "--port", "8787"]
