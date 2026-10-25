# The API's container image (S1.6, D4; deploy steps in doc/hosting.md). `fly deploy` builds
# it on Fly's remote builder, so nobody needs Docker installed. The data isn't in the
# image: DATA_DIR is a volume mounted at /data.

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
# The hosting spike, to time workloads on the host (fly ssh console).
COPY spikes/hosting.py ./spikes/hosting.py

ENV PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/data
EXPOSE 8080
CMD ["fastapi", "run", "--port", "8080"]
