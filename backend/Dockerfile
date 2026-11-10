# The API's container image (S1.6, D4). Railway builds it from GitHub when a merge to
# main changes what goes into it, after CI passes; doc/reference/hosting.md has the settings. The
# data isn't in the image: DATA_DIR is /data, where Railway mounts the volume that holds
# the store (scripts/upload_store.sh puts it there).

# The same Python and uv versions as local development.
FROM python:3.14.7-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Dependencies first, in their own layer, so a code change rebuilds in seconds.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app
# The hosting spike, to time workloads from a shell on the host.
COPY spikes/hosting.py ./spikes/hosting.py
# Compiled now, because the server's user can't write __pycache__ at startup.
RUN python -m compileall -q app spikes

# The server runs as an unprivileged user. The code and packages stay root's, read-only
# to it, and the store on the volume only has to be readable, which it is (644 files).
RUN useradd --system --no-create-home --uid 10001 app
USER app

ENV PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/data
EXPOSE 8080
# Listen on $PORT, which Railway (and Cloud Run) set, or 8080 when it's unset, as with
# `docker run`. exec makes the server PID 1, so it gets the host's stop signal.
CMD ["sh", "-c", "exec fastapi run --port \"${PORT:-8080}\""]
