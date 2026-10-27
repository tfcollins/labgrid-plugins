#!/bin/sh
set -e

if [ -d /etc/ssh-host-keys ]; then
    mkdir -p /root/.ssh
    cp -r /etc/ssh-host-keys/* /root/.ssh/ 2>/dev/null || true
    chown -R root:root /root/.ssh
    chmod 700 /root/.ssh
    chmod 600 /root/.ssh/* 2>/dev/null || true
    chmod 644 /root/.ssh/config /root/.ssh/known_hosts /root/.ssh/*.pub 2>/dev/null || true
fi

exec "$@"
