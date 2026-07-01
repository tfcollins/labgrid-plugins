FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Build context is the repo root (set in docker-compose.yml). We install
# the API package and the labgrid-plugins package so labgrid-client
# inside this container recognises plugin resource classes (KuiperRelease,
# VesyncOutlet, CyberPowerOutlet, etc.) used by exporters in this lab.

# 1. Install the API package
COPY coordinator/api/pyproject.toml ./api-pyproject.toml
RUN cp api-pyproject.toml pyproject.toml && pip install --no-cache-dir . && rm api-pyproject.toml pyproject.toml

# 2. Install labgrid-plugins for resource-class entry-point registration.
#    Use --no-deps to skip heavy/system-bound deps (pytsk3, pylibiio, usbsdmux,
#    fastmcp). Install only the runtime deps needed by power/outlet drivers
#    that the API actually invokes via labgrid-client.
COPY pyproject.toml /tmp/adi/pyproject.toml
COPY adi_lg_plugins /tmp/adi/adi_lg_plugins
RUN pip install --no-cache-dir --no-deps /tmp/adi \
    && pip install --no-cache-dir \
        "pyvesync>=1.1.5,<3.0.0" \
        pysnmp \
        requests \
        tqdm \
        attrs \
    && rm -rf /tmp/adi

# 3. Drop a sitecustomize.py that:
#    (a) auto-discovers labgrid plugins on every Python startup so labgrid-client
#        recognizes plugin resource classes (KuiperRelease, VesyncOutlet, ...).
#    (b) monkey-patches labgrid-client's `power` command with a plugin-aware
#        fallback that maps plugin resource classes to their PowerProtocol
#        drivers (Vesync/CyberPower/HomeAssistant).
COPY coordinator/api/sitecustomize.py /tmp/sitecustomize.py
RUN cp /tmp/sitecustomize.py "$(python -c 'import site; print(site.getsitepackages()[0])')/sitecustomize.py"

# 4. Copy the API application code
COPY coordinator/api/app/ app/
COPY coordinator/api/board_catalog.yaml ./board_catalog.yaml

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
