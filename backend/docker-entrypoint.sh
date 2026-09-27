#!/bin/sh
# Apply pending migrations, then hand PID 1 to the server.
set -eu
alembic upgrade head
exec "$@"
