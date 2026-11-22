# WebForge in one container: Python (the agents and the Streamlit UI),
# Node (the html-validate / stylelint / eslint linters the developer agents
# call through npx) and Playwright's Chromium (Test Execution).
#
#   docker compose up webforge      # the real app, reads OPENAI_API_KEY from .env
#   docker compose up demo          # the same UI on a scripted backend, no API key, no cost
#
# Then open http://localhost:8501

FROM node:22-bookworm-slim AS node

FROM python:3.13-slim-bookworm

# libatomic1: the Node binary bundled with Playwright (used by
# `playwright install`) fails to start without it on the slim image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libatomic1 \
 && rm -rf /var/lib/apt/lists/*

# Node and npm from the official image, so the linters get the Node version
# they require (eslint 10 and stylelint 17 need Node 20.19 or newer).
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY requirements.txt ./
RUN pip install -r requirements.txt \
 && playwright install --with-deps chromium

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

EXPOSE 8501
CMD ["streamlit", "run", "stream_lit.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
