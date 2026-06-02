FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "labgrid>=25.0"

RUN mkdir -p /var/lib/labgrid
VOLUME /var/lib/labgrid

EXPOSE 20408

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
