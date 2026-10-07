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

FROM python:3.13-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=5000
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg \
       libglib2.0-0 \
       libgl1 \
       libnspr4 \
       libnss3 \
       libatk1.0-0t64 \
       libatk-bridge2.0-0t64 \
       libcups2t64 \
       libdrm2 \
       libxkbcommon0 \
       libxcomposite1 \
       libxdamage1 \
       libxfixes3 \
       libxrandr2 \
       libgbm1 \
       libasound2t64 \
       libpango-1.0-0 \
       libcairo2 \
       libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend-build /build/frontend/dist ./frontend/dist
RUN useradd --create-home --uid 10001 prepza && chown -R prepza:prepza /app
USER prepza
EXPOSE 5000
CMD ["gunicorn", "-k", "gthread", "-w", "1", "--threads", "100", "realtime_server:app"]
