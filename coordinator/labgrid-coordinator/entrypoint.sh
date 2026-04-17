#!/bin/sh
set -e

cd /var/lib/labgrid

exec python3 -m labgrid.remote.coordinator -l "[::]:20408" "$@"
