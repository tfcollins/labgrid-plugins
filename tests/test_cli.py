import os
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from adi_lg_plugins.tools.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


def test_cli_help(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "ADI Labgrid Plugins CLI" in result.output


def test_boot_fabric_help(runner):
    result = runner.invoke(cli, ["boot-fabric", "--help"])
    assert result.exit_code == 0
    assert "Boot FPGA Fabric strategy" in result.output


@patch("adi_lg_plugins.tools.cli.Environment")
def test_boot_fabric_success(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    mock_resource = MagicMock()
    mock_tg.get_resource.return_value = mock_resource
    mock_strat = MagicMock()
    mock_tg.get_driver.return_value = mock_strat

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        with open("test.bit", "w") as f:
            f.write("dummy")

        result = runner.invoke(cli, ["boot-fabric", "-c", "config.yaml", "--bitstream", "test.bit"])

        assert result.exit_code == 0
        assert "Successfully reached shell!" in result.output
        mock_env.assert_called_once_with("config.yaml")
        mock_resource.bitstream_path = os.path.abspath("test.bit")
        mock_strat.transition.assert_called_with("shell")


@patch("adi_lg_plugins.tools.cli.Environment")
def test_boot_soc_success(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    mock_resource = MagicMock()
    mock_tg.get_resource.return_value = mock_resource
    mock_strat = MagicMock()
    mock_tg.get_driver.return_value = mock_strat

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")

        result = runner.invoke(cli, ["boot-soc", "-c", "config.yaml", "--release", "2023_R2"])

        assert result.exit_code == 0
        assert "Successfully reached shell!" in result.output
        mock_resource.release_version = "2023_R2"
        mock_strat.transition.assert_called_with("shell")


@patch("adi_lg_plugins.tools.cli.Environment")
def test_boot_soc_ssh_success(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    mock_resource = MagicMock()
    mock_tg.get_resource.return_value = mock_resource
    mock_strat = MagicMock()
    mock_tg.get_driver.return_value = mock_strat

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")

        result = runner.invoke(cli, ["boot-soc-ssh", "-c", "config.yaml", "--release", "2023_R2"])

        assert result.exit_code == 0
        assert "Successfully reached shell!" in result.output
        mock_resource.release_version = "2023_R2"
        mock_strat.transition.assert_called_with("shell")


@patch("adi_lg_plugins.tools.cli.Environment")
def test_boot_selmap_success(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    mock_strat = MagicMock()
    mock_tg.get_driver.return_value = mock_strat

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        with open("local.bin", "w") as f:
            f.write("dummy")

        result = runner.invoke(
            cli,
            ["boot-selmap", "-c", "config.yaml", "--pre-boot-file", "local.bin:/boot/remote.bin"],
        )

        assert result.exit_code == 0
        assert "Successfully reached shell!" in result.output
        assert mock_strat.pre_boot_boot_files == {os.path.abspath("local.bin"): "/boot/remote.bin"}
        mock_strat.transition.assert_called_with("shell")


@patch("adi_lg_plugins.tools.cli.Environment")
def test_boot_fabric_failure(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    mock_strat = MagicMock()
    mock_tg.get_driver.return_value = mock_strat
    mock_strat.transition.side_effect = Exception("Hardware timeout")

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")

        result = runner.invoke(cli, ["boot-fabric", "-c", "config.yaml"])

        assert result.exit_code != 0
        assert "Transition failed: Hardware timeout" in result.output


@patch("adi_lg_plugins.tools.cli.download_cloudsmith_boot_file")
def test_download_cloudsmith_success(mock_dl, runner):
    mock_dl.return_value = "/cache/v1/BOOT.BIN"

    result = runner.invoke(
        cli,
        ["download-cloudsmith", "--fpga-carrier", "zcu102", "--daughter-card", "adrv9009"],
    )

    assert result.exit_code == 0
    assert "/cache/v1/BOOT.BIN" in result.output
    mock_dl.assert_called_once_with(
        fpga_carrier="zcu102",
        daughter_card="adrv9009",
        vfilter=(),
        vnot=(),
        filename="BOOT.BIN",
        owner="adi",
        repo="sdg-boot-partition",
        version=None,
        cache_path="~/.labgrid/cloudsmith_releases/",
    )


@patch("adi_lg_plugins.tools.cli.download_cloudsmith_boot_file")
def test_download_cloudsmith_repeated_vfilter_vnot(mock_dl, runner):
    mock_dl.return_value = "/cache/v1/BOOT.BIN"

    result = runner.invoke(
        cli,
        [
            "download-cloudsmith",
            "--fpga-carrier",
            "zcu102",
            "--vfilter",
            "LVDS",
            "--vfilter",
            "boot_bin",
            "--vnot",
            "debug",
            "--vnot",
            "test",
        ],
    )

    assert result.exit_code == 0
    _, kwargs = mock_dl.call_args
    assert kwargs["vfilter"] == ("LVDS", "boot_bin")
    assert kwargs["vnot"] == ("debug", "test")


@patch("adi_lg_plugins.tools.cli.download_cloudsmith_boot_file")
def test_download_cloudsmith_out_file(mock_dl, runner):
    with runner.isolated_filesystem():
        os.makedirs("cache")
        with open("cache/BOOT.BIN", "wb") as f:
            f.write(b"boot-bytes")
        mock_dl.return_value = os.path.abspath("cache/BOOT.BIN")

        result = runner.invoke(
            cli,
            [
                "download-cloudsmith",
                "--fpga-carrier",
                "zcu102",
                "--daughter-card",
                "adrv9009",
                "--out",
                "copy.bin",
            ],
        )

        assert result.exit_code == 0
        with open("copy.bin", "rb") as f:
            assert f.read() == b"boot-bytes"
        assert "copy.bin" in result.output


@patch("adi_lg_plugins.tools.cli.download_cloudsmith_boot_file")
def test_download_cloudsmith_out_directory(mock_dl, runner):
    with runner.isolated_filesystem():
        os.makedirs("cache")
        os.makedirs("dest")
        with open("cache/BOOT.BIN", "wb") as f:
            f.write(b"boot-bytes")
        mock_dl.return_value = os.path.abspath("cache/BOOT.BIN")

        result = runner.invoke(
            cli,
            [
                "download-cloudsmith",
                "--fpga-carrier",
                "zcu102",
                "--daughter-card",
                "adrv9009",
                "--out",
                "dest",
            ],
        )

        assert result.exit_code == 0
        with open(os.path.join("dest", "BOOT.BIN"), "rb") as f:
            assert f.read() == b"boot-bytes"


@patch("adi_lg_plugins.tools.cli.download_cloudsmith_boot_file")
def test_download_cloudsmith_failure(mock_dl, runner):
    mock_dl.side_effect = Exception("No Cloudsmith API token")

    result = runner.invoke(
        cli,
        ["download-cloudsmith", "--fpga-carrier", "zcu102", "--daughter-card", "adrv9009"],
    )

    assert result.exit_code != 0
    assert "No Cloudsmith API token" in result.output


@patch("adi_lg_plugins.tools.cli.download_cloudsmith_boot_file")
def test_download_cloudsmith_out_copy_failure(mock_dl, runner):
    with runner.isolated_filesystem():
        os.makedirs("cache")
        with open("cache/BOOT.BIN", "wb") as f:
            f.write(b"boot-bytes")
        mock_dl.return_value = os.path.abspath("cache/BOOT.BIN")

        result = runner.invoke(
            cli,
            [
                "download-cloudsmith",
                "--fpga-carrier",
                "zcu102",
                "--daughter-card",
                "adrv9009",
                "--out",
                "missing_dir/copy.bin",
            ],
        )

        assert result.exit_code != 0
        assert "Copy failed" in result.output


def test_recover_help():
    from click.testing import CliRunner

    from adi_lg_plugins.tools.cli import cli

    result = CliRunner().invoke(cli, ["recover", "--help"])
    assert result.exit_code == 0
    assert "sd_flash_done" in result.output


def test_recover_runs_strategy_transition(tmp_path, monkeypatch):
    from click.testing import CliRunner

    import adi_lg_plugins.tools.cli as cli_mod

    cfg = tmp_path / "env.yaml"
    cfg.write_text("targets: {}\n")
    calls = {}

    class FakeStrategy:
        def transition(self, state):
            calls["state"] = state

    class FakeTarget:
        def get_resource(self, _cls):
            raise Exception("no KuiperRelease")

        def get_driver(self, name):
            calls["driver"] = name
            return FakeStrategy()

    class FakeEnv:
        def __init__(self, _cfg):
            pass

        def get_target(self, _t):
            return FakeTarget()

    monkeypatch.setattr(cli_mod, "Environment", FakeEnv)
    result = CliRunner().invoke(cli_mod.cli, ["recover", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert calls == {"driver": "BootZynq7000JTAGRecovery", "state": "sd_flash_done"}


def test_list_hardware_help(runner):
    result = runner.invoke(cli, ["list-hardware", "--help"])
    assert result.exit_code == 0
    assert "List available places on the coordinator." in result.output


@patch("adi_lg_plugins.tools.cli.resolve_coordinator")
@patch("adi_lg_plugins.tools.cli.list_live_places")
def test_list_hardware_success(mock_list, mock_resolve, runner):
    from adi_lg_plugins.hw_ci.schema import Place

    mock_resolve.return_value = "localhost:20408"
    mock_list.return_value = (
        [
            Place(
                name="place-1",
                carrier="zcu102",
                daughter_board="adrv9002",
                boot_strategy="BootFPGASoC",
                hdl_config="dual",
                exporter="host-1",
            ),
            Place(
                name="place-2",
                carrier="zc706",
                daughter_board="adrv9009",
                boot_strategy="BootFPGASoC",
                acquired="user-a",
            ),
        ],
        [("place-bad", "missing carrier tag")],
    )

    result = runner.invoke(cli, ["list-hardware"])
    assert result.exit_code == 0
    assert "place-1" in result.output
    assert "place-2" in result.output
    assert "zcu102" in result.output
    assert "adrv9009" in result.output
    assert "Available" in result.output
    assert "Acquired" in result.output
    assert "user-a" in result.output
    assert "Warning: 1 place(s) skipped" in result.output
    assert "place-bad: missing carrier tag" in result.output


@patch("adi_lg_plugins.tools.cli.resolve_coordinator")
@patch("adi_lg_plugins.tools.cli.list_live_places")
def test_list_hardware_json(mock_list, mock_resolve, runner):
    import json

    from adi_lg_plugins.hw_ci.schema import Place

    mock_resolve.return_value = "localhost:20408"
    mock_list.return_value = (
        [
            Place(
                name="place-1",
                carrier="zcu102",
                daughter_board="adrv9002",
                boot_strategy="BootFPGASoC",
                hdl_config="dual",
                exporter="host-1",
            )
        ],
        [],
    )

    result = runner.invoke(cli, ["list-hardware", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["name"] == "place-1"
    assert data[0]["carrier"] == "zcu102"


@patch("adi_lg_plugins.tools.cli.resolve_coordinator")
@patch("adi_lg_plugins.tools.cli.list_live_places")
def test_list_hardware_filters(mock_list, mock_resolve, runner):
    from adi_lg_plugins.hw_ci.schema import Place

    mock_resolve.return_value = "localhost:20408"
    mock_list.return_value = (
        [
            Place(
                name="place-1",
                carrier="zcu102",
                daughter_board="adrv9002",
                boot_strategy="BootFPGASoC",
            ),
            Place(
                name="place-2",
                carrier="zc706",
                daughter_board="adrv9009",
                boot_strategy="BootFPGASoC",
                acquired="user-a",
            ),
        ],
        [],
    )

    # test --carrier zcu102
    result = runner.invoke(cli, ["list-hardware", "--carrier", "zcu102"])
    assert result.exit_code == 0
    assert "place-1" in result.output
    assert "place-2" not in result.output

    # test --part adrv9009
    result = runner.invoke(cli, ["list-hardware", "--part", "adrv9009"])
    assert result.exit_code == 0
    assert "place-1" not in result.output
    assert "place-2" in result.output

    # test --available-only
    result = runner.invoke(cli, ["list-hardware", "--available-only"])
    assert result.exit_code == 0
    assert "place-1" in result.output
    assert "place-2" not in result.output


@patch("adi_lg_plugins.tools.cli.resolve_coordinator")
def test_list_hardware_no_coordinator(mock_resolve, runner):
    mock_resolve.side_effect = RuntimeError("no coordinator URL")

    result = runner.invoke(cli, ["list-hardware"])
    assert result.exit_code != 0
    assert "Error: no coordinator URL" in result.output


# --- flash-sd -------------------------------------------------------------


def _make_img(path, size=1024, imgid=b"\xd2\x86\x22\xa2"):
    """Write a sparse file with an MBR disk signature at offset 440."""
    with open(path, "wb") as f:
        f.write(b"\0" * 440)
        f.write(imgid)
        f.write(b"\0" * max(0, size - 444))


def _flash_drivers(mock_tg):
    """Wire get_driver() to return distinct sdmux/writer/power mocks."""
    drivers = {
        "USBSDMuxDriver": MagicMock(),
        "USBStorageDriver": MagicMock(),
        "PowerProtocol": MagicMock(),
    }

    def _get_driver(name):
        if name not in drivers:
            raise Exception(f"no {name} driver found")
        return drivers[name]

    mock_tg.get_driver.side_effect = _get_driver
    return drivers


def test_flash_sd_help(runner):
    result = runner.invoke(cli, ["flash-sd", "--help"])
    assert result.exit_code == 0
    assert "Flash a full SD card image" in result.output


def test_flash_sd_requires_exactly_one_source(runner):
    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        _make_img("disk.img")

        result = runner.invoke(cli, ["flash-sd", "-c", "config.yaml"])
        assert result.exit_code != 0
        assert "exactly one of --image or --release" in result.output

        result = runner.invoke(
            cli,
            ["flash-sd", "-c", "config.yaml", "--image", "disk.img", "--release", "2023_R2_P1"],
        )
        assert result.exit_code != 0
        assert "exactly one of --image or --release" in result.output


@patch("adi_lg_plugins.tools.cli.Environment")
def test_flash_sd_dry_run_writes_nothing(mock_env, runner):
    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        _make_img("disk.img")

        result = runner.invoke(
            cli, ["flash-sd", "-c", "config.yaml", "--image", "disk.img", "--dry-run"]
        )

        assert result.exit_code == 0
        assert "Dry run" in result.output
        # A dry run must short-circuit before the target is built, so a RemotePlace
        # env (which cannot construct without an acquired place) can still be checked.
        mock_env.assert_not_called()


@patch("adi_lg_plugins.tools.cli.Environment")
def test_flash_sd_success(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    drivers = _flash_drivers(mock_tg)

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        _make_img("disk.img")

        result = runner.invoke(cli, ["flash-sd", "-c", "config.yaml", "--image", "disk.img"])

        assert result.exit_code == 0
        assert "flashed successfully" in result.output

        from labgrid.driver.usbstoragedriver import Mode

        drivers["USBStorageDriver"].write_image.assert_called_once_with(
            filename=os.path.abspath("disk.img"), mode=Mode.DD
        )
        # Board must be powered down before the card is switched away from it, and
        # the mux must end up back on the DUT.
        drivers["PowerProtocol"].off.assert_called()
        assert [c.args[0] for c in drivers["USBSDMuxDriver"].set_mode.call_args_list] == [
            "host",
            "dut",
        ]
        # --power-off is the default, so the board is left down.
        drivers["PowerProtocol"].on.assert_not_called()


@patch("adi_lg_plugins.tools.cli.Environment")
def test_flash_sd_reports_partuuids(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    _flash_drivers(mock_tg)

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        _make_img("disk.img", imgid=b"\xd2\x86\x22\xa2")

        result = runner.invoke(cli, ["flash-sd", "-c", "config.yaml", "--image", "disk.img"])

        assert result.exit_code == 0
        # Little-endian read of the four bytes at offset 440, as adi-kuiper-gen does.
        assert "boot_partuuid=a22286d2-01" in result.output
        assert "root_partuuid=a22286d2-02" in result.output


@patch("adi_lg_plugins.tools.cli.Environment")
def test_flash_sd_power_cycles_when_not_powering_off(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    drivers = _flash_drivers(mock_tg)

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        _make_img("disk.img")

        result = runner.invoke(
            cli, ["flash-sd", "-c", "config.yaml", "--image", "disk.img", "--no-power-off"]
        )

        assert result.exit_code == 0
        drivers["PowerProtocol"].on.assert_called_once()


@patch("adi_lg_plugins.tools.cli.Environment")
def test_flash_sd_missing_image_writer_is_actionable(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg

    def _get_driver(name):
        if name == "USBStorageDriver":
            raise Exception("no USBStorageDriver driver found in Target")
        return MagicMock()

    mock_tg.get_driver.side_effect = _get_driver

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        _make_img("disk.img")

        result = runner.invoke(cli, ["flash-sd", "-c", "config.yaml", "--image", "disk.img"])

        assert result.exit_code != 0
        # No shipped env yaml declares this driver, so the error has to name the fix.
        assert "USBStorageDriver: {}" in result.output
        assert "config.yaml" in result.output


@patch("adi_lg_plugins.tools.cli.Environment")
def test_flash_sd_extracts_zip(mock_env, runner):
    import zipfile

    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    drivers = _flash_drivers(mock_tg)

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        _make_img("inner.img")
        with zipfile.ZipFile("kuiper.zip", "w") as zf:
            zf.write("inner.img")
        os.remove("inner.img")
        os.makedirs("cache", exist_ok=True)

        result = runner.invoke(
            cli,
            [
                "flash-sd",
                "-c",
                "config.yaml",
                "--image",
                "kuiper.zip",
                "--cache-path",
                "cache",
                "--min-free-gb",
                "0",
            ],
        )

        assert result.exit_code == 0
        written = drivers["USBStorageDriver"].write_image.call_args.kwargs["filename"]
        assert written.endswith("inner.img")


def test_flash_sd_refuses_without_disk_space(runner):
    import zipfile

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        _make_img("inner.img")
        with zipfile.ZipFile("kuiper.zip", "w") as zf:
            zf.write("inner.img")

        result = runner.invoke(
            cli,
            [
                "flash-sd",
                "-c",
                "config.yaml",
                "--image",
                "kuiper.zip",
                "--min-free-gb",
                "999999",
            ],
        )

        assert result.exit_code != 0
        assert "free" in result.output.lower()
