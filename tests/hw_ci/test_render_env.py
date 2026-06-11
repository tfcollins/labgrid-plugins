"""Tests for adi_lg_plugins.hw_ci.render_env."""

from __future__ import annotations

import pytest
import yaml

from adi_lg_plugins.hw_ci.render_env import (
    RenderError,
    list_strategy_templates,
    render_env,
    render_env_to,
)
from adi_lg_plugins.hw_ci.schema import KNOWN_STRATEGIES, Place


def _place(strat, place="mini2"):
    return Place(
        name=place,
        carrier="zcu102",
        daughter_board="ad9081",
        boot_strategy=strat,
        hdl_config="m8_l4",
    )


def test_every_known_strategy_has_a_template():
    """Discoverable strategies and discoverable templates must match.

    If this fails it means someone added a Boot* class under
    adi_lg_plugins.strategies/ without a matching .yaml template
    under adi_lg_plugins/hw_ci/templates/, OR vice versa.
    """
    templates = set(list_strategy_templates())
    strategies = set(KNOWN_STRATEGIES)
    # SoftwareProvisioningStrategy isn't a boot strategy; it shouldn't be
    # in either set, but defend explicitly.
    missing_templates = strategies - templates
    assert not missing_templates, (
        f"strategies missing render templates: {sorted(missing_templates)}"
    )


def test_render_substitutes_place_name():
    out = render_env(_place("BootFPGASoC"))
    assert "name: mini2" in out
    assert "${place_name}" not in out
    assert "${carrier}" not in out


def test_render_includes_strategy_driver():
    """Every template should mention its own strategy class name."""
    for strat in KNOWN_STRATEGIES:
        out = render_env(_place(strat))
        assert strat in out, f"template for {strat} doesn't reference it"


def test_render_unknown_strategy_raises():
    p = Place(
        name="x",
        carrier="zcu102",
        daughter_board="ad9081",
        boot_strategy="BootMadeUp",
    )
    with pytest.raises(RenderError, match="no env-yaml template"):
        render_env(p)


def test_render_env_to_writes_file(tmp_path):
    out = tmp_path / "env" / "mini2.yaml"
    written = render_env_to(_place("BootFPGASoC"), out)
    assert written == out
    text = out.read_text()
    assert "RemotePlace" in text
    assert "mini2" in text


def test_extra_subs_override_builtins(tmp_path):
    out = render_env(
        _place("BootFPGASoC"),
        extra_subs={"place_name": "override"},
    )
    assert "name: override" in out
    assert "name: mini2" not in out


def test_power_driver_defaults_to_vesync():
    """Places with no power-driver tag default to VesyncPowerDriver."""
    out = render_env(_place("BootFPGASoC"))
    assert "VesyncPowerDriver:" in out
    assert "HomeAssistantDriver:" not in out


def test_power_driver_tag_overrides():
    """A `power-driver=HomeAssistantDriver` tag swaps the power driver."""
    p = Place(
        name="bq",
        carrier="zc706",
        daughter_board="adrv9371",
        boot_strategy="BootFPGASoC",
        extra_tags={"power-driver": "HomeAssistantDriver"},
    )
    out = render_env(p)
    assert "HomeAssistantDriver:" in out
    assert "VesyncPowerDriver:" not in out


def test_bootfpgasoctftp_uses_named_local_tftp_resource():
    """The BootFPGASoCTFTP template must give the local TFTPServerResource
    an explicit name and bind TFTPServerDriver to it, so we don't conflict
    with a TFTPServerResource published by the coordinator exporter."""
    out = render_env(_place("BootFPGASoCTFTP"))
    # named local resource
    assert "TFTPServerResource:" in out
    assert "name: local-tftp" in out
    # driver pins to the named resource via bindings
    assert "TFTPServerDriver:" in out
    assert "resource: local-tftp" in out


def test_bootfpgasoctftp_tftp_root_default_is_per_place():
    """Default tftp_root is unique per place to avoid parallel-run collisions."""
    out = render_env(_place("BootFPGASoCTFTP"))  # default place is 'mini2'
    assert "root: /tmp/labgrid-tftp-mini2" in out


def test_bootfpgasoctftp_zynq7000_carrier_defaults():
    """Zynq-7000 carriers get ARM32 boot defaults (`bootm`/`uImage`/`Zynq>`)."""
    for carrier in ("zc706", "zc702", "zed"):
        p = Place(
            name="x",
            carrier=carrier,
            daughter_board="adrv9009",
            boot_strategy="BootFPGASoCTFTP",
        )
        out = render_env(p)
        assert "uboot_prompt: 'Zynq>.*'" in out, carrier
        assert "kernel_image_name: 'uImage'" in out, carrier
        assert "dtb_image_name: 'devicetree.dtb'" in out, carrier
        assert "boot_cmd: 'bootm'" in out, carrier


def test_bootfpgasoctftp_zynqmp_carrier_defaults():
    """ZynqMP carriers keep ARM64 defaults (`booti`/`Image`/`ZynqMP>`)."""
    p = Place(
        name="x",
        carrier="zcu102",
        daughter_board="ad9081",
        boot_strategy="BootFPGASoCTFTP",
    )
    out = render_env(p)
    assert "uboot_prompt: 'ZynqMP>.*'" in out
    assert "kernel_image_name: 'Image'" in out
    assert "boot_cmd: 'booti'" in out


def test_bootfpgasoctftp_uboot_attrs_overridable_via_tags():
    p = Place(
        name="x",
        carrier="zc706",
        daughter_board="adrv9371",
        boot_strategy="BootFPGASoCTFTP",
        extra_tags={
            "uboot-prompt": "MyBoot>.*",
            "kernel-image-name": "fitImage",
            "boot-cmd": "bootz",
        },
    )
    out = render_env(p)
    assert "uboot_prompt: 'MyBoot>.*'" in out
    assert "kernel_image_name: 'fitImage'" in out
    assert "boot_cmd: 'bootz'" in out


def test_bootfpgasoctftp_jtag_bootstrap_tags_render_into_strategy():
    """JTAG bootstrap tags on the place flow through the template."""
    p = Place(
        name="nemo",
        carrier="zc706",
        daughter_board="adrv9009",
        boot_strategy="BootFPGASoCTFTP",
        extra_tags={
            "ps7-init-tcl": "/srv/recovery/zc706/ps7_init.tcl",
            "uboot-elf": "/srv/recovery/zc706/u-boot.elf",
            "fsbl-elf": "/srv/recovery/zc706/fsbl.elf",
            "bitstream-path": "/srv/recovery/zc706/system_top.bit",
        },
    )
    out = render_env(p)
    assert "ps7_init_tcl: '/srv/recovery/zc706/ps7_init.tcl'" in out
    assert "uboot_elf: '/srv/recovery/zc706/u-boot.elf'" in out
    assert "fsbl_elf: '/srv/recovery/zc706/fsbl.elf'" in out
    assert "bitstream_path: '/srv/recovery/zc706/system_top.bit'" in out
    # JTAG driver always present in this template
    assert "XilinxJTAGDriver:" in out


def test_bootfpgasoctftp_no_bootstrap_tags_renders_empty_strings():
    """Without the tags the JTAG bootstrap attrs render as empty
    strings; the strategy's _jtag_bootstrap_enabled() treats those as
    falsy and falls through to the SD-bootable path."""
    out = render_env(_place("BootFPGASoCTFTP"))
    assert "ps7_init_tcl: ''" in out
    assert "uboot_elf: ''" in out
    # sd_autoboot defaults off (empty string -> _as_bool False)
    assert "sd_autoboot: ''" in out


def test_bootfpgasoctftp_sd_autoboot_tag_renders_into_strategy():
    """A `sd-autoboot=true` place tag flows through into the strategy so
    JTAG-recovery-class boards skip the TFTP-kernel boot and let the SD
    autoboot Kuiper."""
    p = Place(
        name="nemo",
        carrier="zc706",
        daughter_board="adrv9009",
        boot_strategy="BootFPGASoCTFTP",
        extra_tags={
            "ps7-init-tcl": "/srv/recovery/zc706/ps7_init.tcl",
            "uboot-elf": "/srv/recovery/zc706/u-boot.elf",
            "sd-autoboot": "true",
        },
    )
    out = render_env(p)
    assert "sd_autoboot: 'true'" in out


def test_bootfpgasoctftp_tftp_root_overridable_via_tag():
    """A `tftp-root=...` tag on the place overrides the default."""
    p = Place(
        name="bq",
        carrier="zc706",
        daughter_board="adrv9371",
        boot_strategy="BootFPGASoCTFTP",
        extra_tags={"tftp-root": "/var/lib/labgrid-tftp"},
    )
    out = render_env(p)
    assert "root: /var/lib/labgrid-tftp" in out
    assert "/tmp/labgrid-tftp-bq" not in out


def test_bootfabric_login_config_matches_env_gen():
    """BootFabric's rendered env must mirror the proven coordinator env-gen
    config (coordinator/api/app/env_gen.py LOGIN/STRATEGY entries) that booted
    daq3/vcu118. ADIShellDriver REQUIRES prompt + login_prompt + username — a
    bare ``prompt`` raises labgrid InvalidConfigError on a real place (#81)."""
    p = Place(
        name="daq3-vcu118",
        carrier="vcu118",
        daughter_board="daq3",
        boot_strategy="BootFabric",
        # no power-driver tag: the documented default must apply
    )
    doc = yaml.safe_load(render_env(p))
    drivers = doc["targets"]["main"]["drivers"]
    shell = drivers["ADIShellDriver"]
    assert shell["prompt"] == "#.*"
    assert shell["login_prompt"] == "buildroot login: "
    assert shell["username"] == "root"
    assert "VesyncPowerDriver" in drivers  # documented default power driver
    strat = drivers["BootFabric"]
    assert strat["wait_for_boot_timeout"] == 700
    assert strat["reached_boot_marker"] == "login:"
    assert strat["trigger_dhcp_reset"] is True
    assert strat["power_off_delay"] == 30


def test_every_template_renders_parseable_yaml_for_minimal_place():
    """Drift guard: every shipped template must render to parseable YAML with
    a targets/main/drivers shape for a tag-minimal place."""
    for strat in list_strategy_templates():
        p = Place(
            name="x",
            carrier="zcu102",
            daughter_board="ad9081",
            boot_strategy=strat,
        )
        doc = yaml.safe_load(render_env(p))
        assert doc["targets"]["main"]["drivers"], strat


def test_bootnoosjtag_boot_marker_defaults_to_successfully_initialized():
    """Without a boot-marker tag, BootNoOSJTAG renders the unified default banner."""
    p = Place(
        name="noos1",
        carrier="zc706",
        daughter_board="ad9361",
        boot_strategy="BootNoOSJTAG",
    )
    out = render_env(p)
    assert "boot_marker: 'Successfully initialized'" in out
    assert "Running IIOD server" not in out


def test_bootnoosjtag_boot_marker_overridable_via_tag():
    """A boot-marker tag on the place overrides the default banner."""
    p = Place(
        name="noos2",
        carrier="zc706",
        daughter_board="ad9361",
        boot_strategy="BootNoOSJTAG",
        extra_tags={"boot-marker": "custom banner text"},
    )
    out = render_env(p)
    assert "boot_marker: 'custom banner text'" in out
    assert "Successfully initialized" not in out


def test_bootnoosjtag_a9_target_name_defaults_in_rendered_yaml():
    """BootNoOSJTAG renders a9_target_name with the default value when no override
    is supplied.  Prior to the fix, the placeholder was absent from the template
    so safe_substitute silently dropped the key and the literal
    ${a9_target_name} would have leaked."""
    p = Place(
        name="noos3",
        carrier="zc706",
        daughter_board="ad9361",
        boot_strategy="BootNoOSJTAG",
    )
    out = render_env(p)
    assert "a9_target_name:" in out
    assert "*Cortex-A9 MPCore #0" in out
    assert "${a9_target_name}" not in out


def test_bootnoosjtag_a9_target_name_override_via_extra_subs():
    """Passing extra_subs={"a9_target_name": ...} overrides the default, so a
    per-board JTAG target selection (e.g. dual-core index #1) reaches the
    rendered env yaml."""
    p = Place(
        name="noos4",
        carrier="zc706",
        daughter_board="ad9361",
        boot_strategy="BootNoOSJTAG",
    )
    out = render_env(p, extra_subs={"a9_target_name": "*Cortex-A9 MPCore #1"})
    assert "*Cortex-A9 MPCore #1" in out
    assert "*Cortex-A9 MPCore #0" not in out
    assert "${a9_target_name}" not in out
