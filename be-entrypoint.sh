#!/bin/bash
# Wrapper for Doris BE entry_point.sh
# On first start: runs original entry_point.sh for registration
# On restart: starts BE directly — skips mysql checks (root password randomized by app)

DORIS_HOME="/opt/apache-doris"
BE_HOME="$DORIS_HOME/be"
STORAGE_DIR="$BE_HOME/storage"

if [ -d "$STORAGE_DIR/data" ] && [ "$(ls -A $STORAGE_DIR/data 2>/dev/null)" ]; then
    echo "$(date +'%Y-%m-%dT%H:%M:%S%z') [INFO] [Wrapper]: Existing data found — starting BE directly"

    # Clean duplicate priority_networks from be.conf
    if [ -f "$BE_HOME/conf/be.conf" ]; then
        awk '!/priority_networks/{print} /priority_networks/ && !seen[$0]++{print}' \
            "$BE_HOME/conf/be.conf" > /tmp/be.conf.clean
        cp /tmp/be.conf.clean "$BE_HOME/conf/be.conf"
    fi

    # Remove stale PID file from previous run
    rm -f "$BE_HOME/bin/be.pid"

    # Start BE in foreground (--console)
    # SKIP_CHECK_ULIMIT=true env var bypasses swap/ulimit/vm.max_map_count checks
    exec $BE_HOME/bin/start_be.sh --console
else
    echo "$(date +'%Y-%m-%dT%H:%M:%S%z') [INFO] [Wrapper]: First start — running original entry_point.sh"
    exec bash /usr/local/bin/entry_point.sh
fi