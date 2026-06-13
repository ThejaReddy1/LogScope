#!/bin/bash
# Wait for Doris FE MySQL port then run init.sql
set -e

DORIS_HOST="${DORIS_HOST:-doris-fe}"
DORIS_PORT="${DORIS_PORT:-9030}"
DORIS_USER="${DORIS_USER:-root}"

echo "[doris-init] Waiting for Doris FE at ${DORIS_HOST}:${DORIS_PORT} ..."

for i in $(seq 1 80); do
  if mysql -h "$DORIS_HOST" -P "$DORIS_PORT" -u "$DORIS_USER" \
       --connect-timeout=3 -e "SELECT 1;" > /dev/null 2>&1; then
    echo "[doris-init] Doris ready on attempt $i. Running init.sql ..."
    mysql -h "$DORIS_HOST" -P "$DORIS_PORT" -u "$DORIS_USER" < /init/init.sql
    echo "[doris-init] Schema created successfully."
    exit 0
  fi
  echo "[doris-init] Attempt $i/80 – not ready yet, retrying in 5s ..."
  sleep 5
done

echo "[doris-init] ERROR: Doris did not become ready in time."
exit 1
