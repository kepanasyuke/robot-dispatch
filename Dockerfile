FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install ".[postgres]"

COPY migrations ./migrations
COPY alembic.ini ./
COPY mock_ros2 ./mock_ros2

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "robot_dispatch.main:app", "--host", "0.0.0.0", "--port", "8000"]
