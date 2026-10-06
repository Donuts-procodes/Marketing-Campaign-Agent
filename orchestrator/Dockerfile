FROM python:3.14-slim

# Install minimal build prerequisites
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv directly from the official Astral image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Configure isolated virtual environment inside container using uv
ENV VIRTUAL_ENV=/opt/venv
RUN uv venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
ENV UV_SYSTEM_PYTHON=0

# Install dependencies using uv pip into virtual environment
COPY orchestrator/pyproject.toml /app/orchestrator/
RUN uv pip install \
    "langgraph>=0.4.0" \
    "langchain-core>=0.3.0" \
    "langchain-openai>=0.3.0" \
    "pydantic>=2.0" \
    "pydantic-settings>=2.0" \
    "tavily-python>=0.5.0" \
    "ddgs>=9.0" \
    "pymongo>=4.9" \
    "redis>=5.0" \
    "httpx>=0.27.0" \
    "python-dotenv>=1.0.0" \
    "grandalf>=0.8" \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.30.0" \
    "python-multipart>=0.0.9" \
    "pypdf>=4.0" \
    "openpyxl>=3.1.0" \
    "pytest>=8.0" \
    "pytest-asyncio>=0.24.0"

# Copy orchestrator package code
COPY orchestrator /app/orchestrator

WORKDIR /app/orchestrator

# Run as an unprivileged user
RUN useradd --create-home --uid 10001 app
USER app

# Default entry point runs FastAPI server on port 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "log_config.json"]
