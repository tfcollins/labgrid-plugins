"""Tests for exporter-side downloader artifacts and handoffs."""

import logging
import types
from unittest import mock

from adi_lg_plugins.artifacts import ArtifactRef, local_artifact
from adi_lg_plugins.drivers import _exporter
from adi_lg_plugins.drivers.cloudsmithdldriver import CloudsmithDLDriver
from adi_lg_plugins.drivers.kuiperdldriver import KuiperDLDriver
from adi_lg_plugins.drivers.massstoragedriver import MassStorageDriver
from adi_lg_plugins.drivers.tftpserverdriver import TFTPServerDriver


def _remote_resource(**values):
    defaults = {
        "extra": {"proxy": "exporter.example.com"},
        "release_version": "2026_R1",
        "cache_path": "/var/cache/adi",
        "kernel_path": None,
        "BOOTBIN_path": None,
        "device_tree_path": None,
    }
    defaults.update(values)
    return types.SimpleNamespace(**defaults)


def _driver(cls, binding, resource):
    driver = cls.__new__(cls)
    setattr(driver, binding, resource)
    driver.logger = logging.getLogger("test_exporter_artifacts")
    driver._boot_files = []
    driver._exporter_agent_init()
    return driver


def test_exporter_agent_lifecycle_uses_resource_proxy(monkeypatch):
    driver = _driver(KuiperDLDriver, "kuiper_resource", _remote_resource())
    wrapper = mock.Mock()
    wrapper.load.return_value = mock.Mock()
    factory = mock.Mock(return_value=wrapper)
    monkeypatch.setattr(_exporter, "AgentWrapper", factory)

    driver.on_activate()
    factory.assert_called_once_with("exporter.example.com")
    wrapper.load.assert_called_once_with("download", mock.ANY)
    driver.on_deactivate()
    wrapper.close.assert_called_once_with()


def test_remote_kuiper_returns_location_aware_artifacts():
    driver = _driver(KuiperDLDriver, "kuiper_resource", _remote_resource())
    driver._agent_proxy = mock.Mock()
    driver._agent_proxy.boot_artifacts.return_value = [
        {"path": "/var/cache/adi/BOOT.BIN", "host": None, "sha256": "abc", "size": 3}
    ]

    artifacts = driver.get_boot_artifacts()

    assert artifacts == [
        ArtifactRef(
            path="/var/cache/adi/BOOT.BIN",
            host="exporter.example.com",
            sha256="abc",
            size=3,
        )
    ]
    driver._agent_proxy.boot_artifacts.assert_called_once_with(
        "kuiper", driver._agent_config(), False
    )


def test_remote_cloudsmith_returns_location_aware_artifacts():
    resource = _remote_resource(
        fpga_carrier="zcu102",
        daughter_card="ad9081",
        vfilter=None,
        vnot=None,
        owner="adi",
        repo="boot",
        filename="BOOT.BIN",
        version=None,
        api_token="secret",
        boot_file_path=None,
    )
    driver = _driver(CloudsmithDLDriver, "cloudsmith_resource", resource)
    driver._agent_proxy = mock.Mock()
    driver._agent_proxy.boot_artifacts.return_value = [
        {"path": "/var/cache/adi/BOOT.BIN", "host": None, "sha256": "abc", "size": 3}
    ]

    artifact = driver.get_boot_artifacts()[0]

    assert artifact.host == "exporter.example.com"
    assert artifact.path == "/var/cache/adi/BOOT.BIN"


def test_local_artifact_records_digest_and_size(tmp_path):
    path = tmp_path / "BOOT.BIN"
    path.write_bytes(b"abc")
    artifact = local_artifact(str(path))
    assert artifact.host is None
    assert artifact.size == 3
    assert artifact.sha256 == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_mass_storage_same_exporter_copy_is_zero_copy():
    driver = MassStorageDriver.__new__(MassStorageDriver)
    driver.mass_storage = types.SimpleNamespace(extra={"proxy": "exporter.example.com"})
    driver.mounted = True
    driver.mount_label = "test"
    driver.logger = mock.Mock()
    driver._remote_check = mock.Mock()
    artifact = ArtifactRef("/var/cache/BOOT.BIN", "exporter.example.com", "abc", 3)

    driver.copy_artifact(artifact, "/BOOT.BIN")

    assert driver._remote_check.call_args_list == [
        mock.call(["mkdir", "-p", "/media/test"]),
        mock.call(["cp", "/var/cache/BOOT.BIN", "/media/test/BOOT.BIN"]),
    ]


def test_tftp_same_exporter_publish_is_zero_copy():
    driver = TFTPServerDriver.__new__(TFTPServerDriver)
    driver.resource = types.SimpleNamespace(extra={"proxy": "exporter.example.com"})
    driver.proxy = mock.Mock()
    driver.proxy.publish_existing.return_value = "images/BOOT.BIN"
    driver.server = types.SimpleNamespace(address="10.0.0.20", port=69)
    artifact = ArtifactRef("/var/cache/BOOT.BIN", "exporter.example.com", "abc", 3)

    result = driver.publish_artifact(artifact, "images/BOOT.BIN")

    driver.proxy.publish_existing.assert_called_once_with(
        "/var/cache/BOOT.BIN", "images/BOOT.BIN", "abc"
    )
    assert result == {"filename": "images/BOOT.BIN", "address": "10.0.0.20:69"}
