FROM debian:stable-slim
LABEL maintainer="Secunity LTD. (support@secunity.io)"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git wget curl ca-certificates nano iputils-ping \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1

WORKDIR /app
RUN git clone https://github.com/secunity/onpremagent.git .

RUN uv python install 3.8 \
    && uv venv --python 3.8 /app/.venv \
    && uv pip install --python /app/.venv/bin/python --no-cache-dir -r requirements.txt

ENV PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV=/app/.venv

RUN mkdir -p /etc/secunity
RUN mkdir -p /var/log/secunity

ENTRYPOINT ["/app/.venv/bin/python", "/app/bin/start.py", "--program", "stats_fetcher"]
