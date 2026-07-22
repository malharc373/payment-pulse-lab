# Single image that can run any of: the pipeline, the API, or the dashboard.
FROM python:3.10-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Application code.
COPY src ./src
COPY scripts ./scripts
COPY dashboard ./dashboard
COPY pytest.ini ./

EXPOSE 8000 8501

# Default: serve the API. docker-compose overrides `command` per service.
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
