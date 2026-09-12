"""Narrow exporter helper for Kuiper and Cloudsmith artifact drivers.

This source is uploaded by labgrid's AgentWrapper.  Only methods listed in
``methods`` are callable; no arbitrary command or module dispatch is exposed.
"""

import hashlib
import logging
import os
from types import SimpleNamespace


def _exporter_secret(name):
    value = os.environ.get(name)
    if value:
        return value
    path = os.path.expanduser(
        os.environ.get("ADI_LG_CREDENTIAL_FILE", "~/.config/adi-lg/credentials.env")
    )
    try:
        if os.stat(path).st_mode & 0o077:
            raise RuntimeError(f"exporter credential file {path} must have mode 0600")
        with open(path) as stream:
            for line in stream:
                key, separator, candidate = line.rstrip("\n").partition("=")
                if separator and key == name:
                    return candidate
    except FileNotFoundError:
        pass
    return None


def _artifact(path):
    path = os.path.abspath(os.path.expanduser(path))
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": path, "host": None, "sha256": digest.hexdigest(), "size": os.path.getsize(path)}


def _driver(kind, config):
    if kind == "kuiper":
        from adi_lg_plugins.drivers.kuiperdldriver import KuiperDLDriver

        driver = KuiperDLDriver.__new__(KuiperDLDriver)
        driver.kuiper_resource = SimpleNamespace(**config)
    elif kind == "cloudsmith":
        from adi_lg_plugins.drivers.cloudsmithdldriver import CloudsmithDLDriver

        driver = CloudsmithDLDriver.__new__(CloudsmithDLDriver)
        config = {**config, "api_token": _exporter_secret("CLOUDSMITH_API_TOKEN")}
        driver.cloudsmith_resource = SimpleNamespace(**config)
    else:
        raise ValueError(f"unsupported downloader kind: {kind!r}")
    driver.logger = logging.getLogger(f"adi_lg_plugins.agent.{kind}")
    driver._boot_files = []
    return driver


def boot_artifacts(kind, config, get_all_files=False):
    driver = _driver(kind, config)
    if kind == "kuiper":
        paths = driver.get_boot_files_from_release(get_all_files=get_all_files)
        if get_all_files:
            return paths
    else:
        paths = driver.get_boot_files_from_release()
    return [_artifact(path) for path in paths]


def full_image_artifact(config, release_version=None):
    path = _driver("kuiper", config).get_full_image_path(release_version)
    return _artifact(path)


def check_cached(kind, config, version=None):
    driver = _driver(kind, config)
    value = driver.check_cached(version)
    if kind == "cloudsmith" and value:
        return _artifact(value)
    return value


def download_release(kind, config, version=None):
    path = _driver(kind, config).download_release(version)
    return _artifact(path) if path else None


methods = {
    "boot_artifacts": boot_artifacts,
    "check_cached": check_cached,
    "download_release": download_release,
    "full_image_artifact": full_image_artifact,
}
