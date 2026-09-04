#!/bin/sh
# Cloud Run entrypoint: restore spine.db from the bucket if this instance has
# none, then run uvicorn under litestream so every write is replicated.
#
# `-if-db-not-exists`: a warm instance restarting for an unrelated reason
# keeps its own file, which is at least as new as the replica.
# `-if-replica-exists`: a brand-new bucket is not an error; the app starts
# empty exactly as before and the first write seeds the replica.
#
# litestream replicate -exec makes uvicorn its child: SIGTERM from Cloud Run
# reaches uvicorn, litestream waits for it to exit, flushes the last WAL
# segment, then exits with uvicorn's status.
set -eu

: "${CINESPINE_DB_PATH:=/app/spine.db}"
: "${PORT:=8080}"
export CINESPINE_DB_PATH

if [ "${CINESPINE_LITESTREAM:-1}" = "1" ]; then
    mkdir -p "$(dirname "$CINESPINE_DB_PATH")"
    litestream restore -if-db-not-exists -if-replica-exists \
        -config /app/deploy/litestream.yml "$CINESPINE_DB_PATH"
    exec litestream replicate -config /app/deploy/litestream.yml \
        -exec "/app/.venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"
fi

exec /app/.venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT}"
