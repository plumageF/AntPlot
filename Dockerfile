FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /app/frontend
RUN corepack enable && corepack prepare pnpm@9.15.9 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.11-slim AS runtime

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    ANTPLOT_HOST=0.0.0.0 \
    ANTPLOT_PORT=8765

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml README.md LICENSE config.yaml ./
COPY src ./src
COPY styles ./styles
COPY docs ./docs
COPY examples ./examples
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
COPY tools/docker_start.py ./tools/docker_start.py

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 4173 8765
CMD ["python", "tools/docker_start.py"]
