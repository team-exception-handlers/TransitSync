# AI contribution: Below 50% AI-generated
# Pin the multi-platform manifest digest so rebuilds use the same image.
# The digest is python:3.12.13-slim; update both together when upgrading.
FROM python@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# requirements.lock pins every package, direct and transitive, with the hash of
# each published file (Sonar S8544). --require-hashes rejects any package that is
# missing from the lock or whose download does not match its hash.
# Wheels only, so no package can run a setup script during the build (Sonar S8541).
COPY requirements.lock .
RUN pip install --no-cache-dir --only-binary :all: --require-hashes \
    --requirement requirements.lock

COPY api ./api
COPY config ./config
COPY simulator ./simulator

# Numba caches compiled code next to the sources by default, but /app is
# read-only for the non-root user, so importing a compiled module would fail.
# Give it a cache folder that user owns, and fill it at build time so a
# container started on a machine with the same CPU features skips the
# compile. On other CPUs Numba recompiles into the same folder.
ENV NUMBA_CACHE_DIR=/var/cache/numba
RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p "$NUMBA_CACHE_DIR" && chown app:app "$NUMBA_CACHE_DIR"
USER app
RUN python -c "from simulator.control.compiled_prediction import warmup; warmup()"

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
