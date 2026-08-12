FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system bankrisk && useradd --system --gid bankrisk --home-dir /app bankrisk

COPY requirements.txt pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY templates ./templates
COPY static ./static
COPY artifacts ./artifacts
COPY run_app.py ./run_app.py

RUN mkdir -p /app/logs && chown -R bankrisk:bankrisk /app
USER bankrisk

EXPOSE 8000
CMD ["python", "scripts/main.py"]
