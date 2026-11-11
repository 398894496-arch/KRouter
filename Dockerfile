# KRouter team server: the read-only MCP server over HTTP, for one team vault mounted read-only.
#
#   docker run -d --name krouter-team -p 8787:8787 \
#     -v /srv/team-vault:/vault:ro -v /etc/krouter/token:/run/secrets/krouter_token:ro \
#     ghcr.io/398894496-arch/krouter:v2.0.0
#
# The vault is never written; the full-text index lives in the container's own cache. See docs/TEAM.md.
FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/398894496-arch/KRouter" \
      org.opencontainers.image.description="KRouter team server: read-only MCP over HTTP for one team vault" \
      org.opencontainers.image.licenses="MIT"

# Standard library only: no packages to install. (Without ripgrep the router's literal search uses Python.)
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin krouter

COPY --chown=root:root skill/krouter /app/skill/krouter

USER krouter
ENV PYTHONDONTWRITEBYTECODE=1 \
    KROUTER_NO_QUERY_LOG=1 \
    KROUTER_CACHE_DIR=/home/krouter/.cache/krouter \
    KROUTER_STATE_DIR=/home/krouter/.local/state/krouter
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
  CMD python -c "import sys,urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8787/healthz', timeout=4).status != 200)"
ENTRYPOINT ["python", "/app/skill/krouter/scripts/mcp_server.py", "--http", "0.0.0.0:8787", \
            "--vault", "/vault", "--token-file", "/run/secrets/krouter_token"]
CMD ["--label", "team"]
