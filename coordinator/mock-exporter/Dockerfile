FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "labgrid @ git+https://github.com/tfcollins/labgrid.git@tfcollins/plugin-support" \
    pyyaml

WORKDIR /app
COPY mock_exporter.py resources.yaml ./

ENTRYPOINT ["python3", "mock_exporter.py"]
