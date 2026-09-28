# Prepza VPS image
FROM node:22-bookworm AS frontend-build
WORKDIR /build
RUN corepack enable && corepack prepare pnpm@10.34.3 --activate \
    && apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*
COPY . .
WORKDIR /build/frontend
RUN pnpm install --frozen-lockfile && pnpm run build

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=5000
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend-build /build/frontend/dist ./frontend/dist
RUN useradd --create-home --uid 10001 prepza && chown -R prepza:prepza /app
USER prepza
EXPOSE 5000
CMD ["gunicorn", "app:app"]
