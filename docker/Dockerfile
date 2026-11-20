# syntax=docker/dockerfile:1

FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

FROM ubuntu:24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HERMES_MEMORY_DIR=/app/storage/memory \
    HERMES_SKILLS_DIR=/app/storage/skills \
    HERMES_PROFILE_DIR=/app/gateway \
    HERMES_PORT=8080

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin hermes

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY storage/skills /app/storage/skills
COPY gateway /app/gateway
RUN mkdir -p /app/storage/memory \
    && chown -R hermes:hermes /app

USER hermes
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"

ENTRYPOINT ["hermes-api"]

FROM runtime AS test

USER root
COPY tests /app/tests
COPY docker /app/docker
COPY docs /app/docs
COPY vector-db /app/vector-db
COPY .github /app/.github
COPY LICENSE README.md AGENTS.md /app/
RUN /opt/venv/bin/pip install --no-cache-dir "pytest>=8.3" "pyyaml>=6.0" "httpx>=0.27"
USER hermes
WORKDIR /app
ENTRYPOINT ["pytest"]
CMD ["-q", "-m", "not integration"]
