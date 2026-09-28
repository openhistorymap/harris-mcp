FROM python:3.11-slim AS base

RUN apt-get update \
 && apt-get install -y --no-install-recommends graphviz \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY harris_mcp ./harris_mcp

# docker build --target test -t harris-mcp:test . && docker run --rm harris-mcp:test
FROM base AS test
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
COPY sim ./sim
CMD ["python", "-m", "pytest", "-q", "tests"]

FROM base AS runtime
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
