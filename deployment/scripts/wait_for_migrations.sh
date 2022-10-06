#!/bin/sh
# Wait until the database is reachable and all Django migrations have completed.

waitForMigrations() {
    while ! CLOUDIGRADE_LOG_LEVEL=ERROR python3 ./manage.py migrate --check; do
        echo "$(date '+%Y-%m-%dT%H.%M.%S') WARNING Database migrations have not yet completed." >&2
        sleep 5
    done
}

waitForMigrations
