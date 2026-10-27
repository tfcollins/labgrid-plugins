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

# Ensure common lab exporter hostnames are resolvable in network_mode: host
for host_entry in "10.0.0.95 lablp lablp.local" "10.0.0.156 bq" "10.0.0.97 nemo nemo.local" "10.0.0.183 tron" "10.0.0.86 mini2"; do
    h1=$(echo "$host_entry" | awk '{print $2}')
    if ! grep -q "$h1" /etc/hosts; then
        echo "$host_entry" >> /etc/hosts 2>/dev/null || true
    fi
done

exec "$@"
