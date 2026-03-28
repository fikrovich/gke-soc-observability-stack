FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY app /app/app
COPY config /app/config

RUN pip install --upgrade pip && pip install .

EXPOSE 8080

CMD ["python", "-m", "app.api.main"]

