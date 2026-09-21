FROM python:3.11-slim-bookworm

ARG DEBIAN_MIRROR=https://deb.debian.org
ARG PYTHON_INDEX=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    STUDIO_DATA_DIR=/var/lib/storm-studio \
    XDG_CACHE_HOME=/tmp/cache \
    NUMBA_CACHE_DIR=/tmp/numba \
    OMP_NUM_THREADS=2

RUN sed -i "s|http://deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::By-Hash=false update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /usr/local/bin/uv
RUN groupadd --gid 10001 studio \
    && useradd --uid 10001 --gid studio --create-home studio
WORKDIR /app
COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations
COPY scripts ./scripts
# Keep locked versions and hashes while allowing a regional mirror. Packages
# absent from that mirror fall back to PyPI, without changing their version.
RUN uv export --frozen --no-dev --no-emit-project --output-file /tmp/requirements.txt \
    && uv venv /app/.venv \
    && uv pip sync --python /app/.venv/bin/python --require-hashes --no-cache \
       --index "${PYTHON_INDEX}" --default-index https://pypi.org/simple \
       --index-strategy unsafe-first-match /tmp/requirements.txt \
    && uv pip install --python /app/.venv/bin/python --no-deps --no-cache \
       --index "${PYTHON_INDEX}" --default-index https://pypi.org/simple . \
    && rm /tmp/requirements.txt \
    && mkdir -p /var/lib/storm-studio \
    && chown studio:studio /var/lib/storm-studio
USER studio
CMD ["uvicorn", "studio.web.app:app", "--host", "0.0.0.0", "--port", "8765", "--no-access-log", "--no-proxy-headers"]
