FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache
COPY scraper.py ./
USER nobody
# ENTRYPOINT : `docker compose run --rm scraper enrich` (ou <tournoi_id>) passe l'argument au script.
ENTRYPOINT [".venv/bin/python", "scraper.py"]
