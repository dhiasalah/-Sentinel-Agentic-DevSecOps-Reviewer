FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# git: checkout.py clones PR heads with the git command
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first: this layer is reused when only code changes (layer cache, step 1.3)
COPY agents/requirements.txt agents/requirements.txt
COPY mcp-servers/scanners/requirements.txt mcp-servers/scanners/requirements.txt
RUN pip install --no-cache-dir -r agents/requirements.txt -r mcp-servers/scanners/requirements.txt \
 && pip uninstall -y pip

RUN useradd --create-home --uid 1000 appuser

COPY --chown=appuser:appuser agents/sentinel/ ./agents/sentinel/
COPY --chown=appuser:appuser mcp-servers/scanners/ ./mcp-servers/scanners/

USER appuser
WORKDIR /app/agents

CMD ["python", "-m", "sentinel.worker"]
