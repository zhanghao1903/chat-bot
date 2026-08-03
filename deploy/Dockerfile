FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --uid 10001 app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir .
RUN mkdir -p /app/data && chown -R app:app /app

USER app

CMD ["group-llm-agent"]
