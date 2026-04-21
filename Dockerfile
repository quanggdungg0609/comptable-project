# Development Dockerfile - uses volume mounts and auto-reload
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install poetry

# Copy only dependency files first (for better caching)
COPY pyproject.toml poetry.lock* ./

RUN poetry config virtualenvs.create false && \
    poetry lock && \
    poetry install --no-interaction --no-ansi --with dev --no-root

# App code is mounted as volume in docker-compose.yml
# Changes to local files will auto-reload

EXPOSE 8000

# Development mode with auto-reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
