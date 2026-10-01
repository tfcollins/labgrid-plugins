import glob
import logging
import os
import shutil
import time

import click
from labgrid import Environment
from rich.console import Console
from rich.logging import RichHandler

from adi_lg_plugins.hw_ci.coordinator import (
    list_live_places,
    resolve_coordinator,
    warn_if_rest_port,
)
from adi_lg_plugins.tools.cloudsmithdl import download_cloudsmith_boot_file
from adi_lg_plugins.tools.config_gen import generate_config
from adi_lg_plugins.tools.request_cli import request_cmd

console = Console()


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging")
def cli(debug):
    """ADI Labgrid Plugins CLI for managing FPGA boot strategies."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, console=console)],
    )
    # Silence some verbose loggers
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


cli.add_command(generate_config)
cli.add_command(request_cmd)


@cli.command()
@click.option(
    "--config", "-c", required=True, type=click.Path(exists=True), help="Labgrid configuration file"
)
@click.option(
    "--bitstream", type=click.Path(exists=True), help="Path to FPGA bitstream file (.bit)"
)
@click.option("--kernel", type=click.Path(exists=True), help="Path to Linux kernel image (.strip)")
@click.option("--target", "-t", default="main", help="Target name in config (default: main)")
@click.option("--state", default="shell", help="Target state to transition to (default: shell)")
def boot_fabric(config, bitstream, kernel, target, state):
    """Boot FPGA Fabric strategy (Microblaze via JTAG).

    This command uses the BootFabric strategy to power on an FPGA,
    flash a bitstream, download a kernel via JTAG, and boot Linux.
    """
    env = Environment(config)
    tg = env.get_target(target)

    # Get resource and override paths if provided
    try:
        resource = tg.get_resource("XilinxDeviceJTAG")
        if bitstream:
            resource.bitstream_path = os.path.abspath(bitstream)
            logging.info(f"Overriding bitstream path: {resource.bitstream_path}")
        if kernel:
            resource.kernel_path = os.path.abspath(kernel)
            logging.info(f"Overriding kernel path: {resource.kernel_path}")
    except Exception as e:
        logging.warning(f"Could not find XilinxDeviceJTAG resource: {e}")

    strategy = tg.get_driver("BootFabric")
    with console.status(f"[bold green]Transitioning {target} to {state} using BootFabric..."):
        try:
            strategy.transition(state)
            console.print(f"[bold green]Successfully reached {state}![/bold green]")
        except Exception as e:
            console.print(f"[bold red]Transition failed: {e}[/bold red]")
            raise click.ClickException(str(e)) from e


@cli.command()
@click.option(
    "--config", "-c", required=True, type=click.Path(exists=True), help="Labgrid configuration file"
)
@click.option("--release", help="Kuiper release version (e.g., 2023_R2_P1)")
@click.option("--kernel", type=click.Path(exists=True), help="Path to kernel file")
@click.option("--bootbin", type=click.Path(exists=True), help="Path to BOOT.BIN file")
@click.option("--devicetree", type=click.Path(exists=True), help="Path to devicetree file")
@click.option("--target", "-t", default="main", help="Target name in config (default: main)")
@click.option("--state", default="shell", help="Target state to transition to (default: shell)")
@click.option("--update-image", is_flag=True, help="Update full SD card image")
def boot_soc(config, release, kernel, bootbin, devicetree, target, state, update_image):
    """Boot FPGA SoC strategy (Zynq/ZynqMP via SD Mux).

    This command uses the BootFPGASoC strategy to flash boot files
    to an SD card via SD Mux and boot the SoC into Linux.
    """
    env = Environment(config)
    tg = env.get_target(target)

    # Get resource and override paths if provided
    try:
        resource = tg.get_resource("KuiperRelease")
        if release:
            resource.release_version = release
            logging.info(f"Overriding release version: {resource.release_version}")
        if kernel:
            resource.kernel_path = os.path.abspath(kernel)
            logging.info(f"Overriding kernel path: {resource.kernel_path}")
        if bootbin:
            resource.BOOTBIN_path = os.path.abspath(bootbin)
            logging.info(f"Overriding BOOTBIN path: {resource.BOOTBIN_path}")
        if devicetree:
            resource.device_tree_path = os.path.abspath(devicetree)
            logging.info(f"Overriding devicetree path: {resource.device_tree_path}")
    except Exception as e:
        logging.warning(f"Could not find KuiperRelease resource: {e}")

    strategy = tg.get_driver("BootFPGASoC")
    if update_image:
        strategy.update_image = True

    with console.status(f"[bold green]Transitioning {target} to {state} using BootFPGASoC..."):
        try:
            strategy.transition(state)
            console.print(f"[bold green]Successfully reached {state}![/bold green]")
        except Exception as e:
            console.print(f"[bold red]Transition failed: {e}[/bold red]")
            raise click.ClickException(str(e)) from e


@cli.command()
@click.option(
    "--config", "-c", required=True, type=click.Path(exists=True), help="Labgrid configuration file"
)
@click.option("--release", help="Kuiper release version (e.g., 2023_R2_P1)")
@click.option("--kernel", type=click.Path(exists=True), help="Path to kernel file")
@click.option("--bootbin", type=click.Path(exists=True), help="Path to BOOT.BIN file")
@click.option("--devicetree", type=click.Path(exists=True), help="Path to devicetree file")
@click.option("--target", "-t", default="main", help="Target name in config (default: main)")
@click.option("--state", default="shell", help="Target state to transition to (default: shell)")
def boot_soc_ssh(config, release, kernel, bootbin, devicetree, target, state):
    """Boot FPGA SoC strategy via SSH (Zynq/ZynqMP).

    This command uses the BootFPGASoCSSH strategy to upload boot files
    to an already running system via SSH, then reboots into the new files.
    """
    env = Environment(config)
    tg = env.get_target(target)

    # Get resource and override paths if provided
    try:
        resource = tg.get_resource("KuiperRelease")
        if release:
            resource.release_version = release
            logging.info(f"Overriding release version: {resource.release_version}")
        if kernel:
            resource.kernel_path = os.path.abspath(kernel)
            logging.info(f"Overriding kernel path: {resource.kernel_path}")
        if bootbin:
            resource.BOOTBIN_path = os.path.abspath(bootbin)
            logging.info(f"Overriding BOOTBIN path: {resource.BOOTBIN_path}")
        if devicetree:
            resource.device_tree_path = os.path.abspath(devicetree)
            logging.info(f"Overriding devicetree path: {resource.device_tree_path}")
    except Exception as e:
        logging.warning(f"Could not find KuiperRelease resource: {e}")

    strategy = tg.get_driver("BootFPGASoCSSH")
    with console.status(f"[bold green]Transitioning {target} to {state} using BootFPGASoCSSH..."):
        try:
            strategy.transition(state)
            console.print(f"[bold green]Successfully reached {state}![/bold green]")
        except Exception as e:
            console.print(f"[bold red]Transition failed: {e}[/bold red]")
            raise click.ClickException(str(e)) from e


@cli.command()
@click.option(
    "--config", "-c", required=True, type=click.Path(exists=True), help="Labgrid configuration file"
)
@click.option("--release", help="Kuiper release version (e.g., 2023_R2_P1)")
@click.option(
    "--sd-image",
    type=click.Path(exists=True),
    help="Path to an SD card image to flash (overrides the strategy default)",
)
@click.option("--target", "-t", default="main", help="Target name in config (default: main)")
@click.option(
    "--state",
    default="sd_flash_done",
    help="Target state to transition to (default: sd_flash_done)",
)
def recover(config, release, sd_image, target, state):
    """Recover a Zynq-7000 board via JTAG (BootZynq7000JTAGRecovery).

    Bootstraps U-Boot over JTAG, TFTP-boots a RAM-rooted recovery Linux, then
    reflashes the SD card. DESTRUCTIVE: wipes /dev/mmcblk0.
    """
    env = Environment(config)
    tg = env.get_target(target)

    try:
        resource = tg.get_resource("KuiperRelease")
        if release:
            resource.release_version = release
            logging.info(f"Overriding release version: {resource.release_version}")
    except Exception as e:
        logging.warning(f"Could not find KuiperRelease resource: {e}")

    strategy = tg.get_driver("BootZynq7000JTAGRecovery")
    if sd_image:
        strategy.sd_image_path = os.path.abspath(sd_image)
        logging.info(f"Overriding SD image path: {strategy.sd_image_path}")

    with console.status(
        f"[bold green]Recovering {target} to {state} using BootZynq7000JTAGRecovery..."
    ):
        try:
            strategy.transition(state)
            console.print(f"[bold green]Successfully reached {state}![/bold green]")
        except Exception as e:
            console.print(f"[bold red]Recovery failed: {e}[/bold red]")
            raise click.ClickException(str(e)) from e


# The FAT boot partition label set by adi-kuiper-gen (mkdosfs -n BOOT). Suggested to
# operators after a flash because every image carries a freshly generated MBR
# signature, so any by-partuuid pin in an env yaml stops resolving.
KUIPER_BOOT_LABEL = "BOOT"


def _image_partuuids(img_path):
    """Return (boot, root) PARTUUIDs for an MBR image.

    Read from the source image, not read back from the card: this reports what a
    successful write puts there, it does not verify what the card now holds.

    adi-kuiper-gen runs ``parted --script mklabel msdos``, which generates a new
    disk signature per build, then derives the PARTUUIDs from the four bytes at
    offset 440. Reproduce that here so a flash can report what the card now has.
    """
    with open(img_path, "rb") as f:
        f.seek(440)
        sig = f.read(4)
    if len(sig) != 4:
        return None, None
    imgid = int.from_bytes(sig, "little")
    if imgid == 0:
        return None, None
    return f"{imgid:08x}-01", f"{imgid:08x}-02"


def _free_gb(path):
    """Free space in GiB on the filesystem holding ``path``."""
    return shutil.disk_usage(path).free / (1024**3)


def _resolve_flash_image(image, release, cache_path, min_free_gb):
    """Resolve --image/--release down to a single uncompressed .img path.

    A .zip (what adi-kuiper-gen emits) is extracted into ``cache_path``; a bare
    .img is used as-is. Returns the .img path.
    """
    if release:
        from adi_lg_plugins.drivers.kuiperdldriver import download_release_image

        os.makedirs(cache_path, exist_ok=True)
        if _free_gb(cache_path) < min_free_gb:
            raise click.ClickException(
                f"Only {_free_gb(cache_path):.1f} GiB free on {cache_path}, "
                f"need at least {min_free_gb} GiB to download and extract a Kuiper release. "
                "Free space or pass --cache-path pointing at a larger filesystem."
            )
        return download_release_image(release, cache_path, logger=logging.getLogger(__name__))

    img = os.path.abspath(image)
    if not img.endswith(".zip"):
        return img

    from adi_lg_plugins.drivers.kuiperdldriver import Downloader

    os.makedirs(cache_path, exist_ok=True)
    if _free_gb(cache_path) < min_free_gb:
        raise click.ClickException(
            f"Only {_free_gb(cache_path):.1f} GiB free on {cache_path}, "
            f"need at least {min_free_gb} GiB to extract {os.path.basename(img)}. "
            "Free space or pass --cache-path pointing at a larger filesystem."
        )
    logging.info(f"Extracting {img} into {cache_path}")
    Downloader().extract_zip(img, cache_path)
    found = sorted(glob.glob(os.path.join(cache_path, "**", "*.img"), recursive=True))
    if len(found) != 1:
        raise click.ClickException(
            f"Expected exactly one .img after extracting {img}, found {len(found)}: {found}"
        )
    return found[0]


def _get_flash_drivers(tg, config):
    """Fetch the sdmux/writer/power drivers, with actionable errors when absent."""
    try:
        sdmux = tg.get_driver("USBSDMuxDriver")
    except Exception as e:
        raise click.ClickException(
            f"No USBSDMuxDriver in {config}. This board has no SD mux wired, or the "
            "env yaml is missing 'USBSDMuxDriver: {}' under drivers."
        ) from e

    try:
        writer = tg.get_driver("USBStorageDriver")
    except Exception as e:
        # No shipped config declares this driver, so it is the likeliest operator
        # error by a wide margin. Name the file and the exact line to add.
        raise click.ClickException(
            f"No USBStorageDriver in {config}. Add 'USBStorageDriver: {{}}' to the drivers "
            "block of that env yaml -- it binds the USBSDMuxDevice resource directly and is "
            "what performs the image write."
        ) from e

    try:
        # The protocol, never a concrete class: the power driver differs per rig
        # (VesyncPowerDriver, APCDriver, ...), which is why the hw_ci env templates
        # substitute ${power_driver}.
        power = tg.get_driver("PowerProtocol")
    except Exception as e:
        raise click.ClickException(
            f"No power driver in {config}. A PowerProtocol driver is required so the "
            "board can be powered down before the SD mux is switched away from it."
        ) from e

    return sdmux, writer, power


@cli.command(name="flash-sd")
@click.option(
    "--config", "-c", required=True, type=click.Path(exists=True), help="Labgrid configuration file"
)
@click.option(
    "--image",
    type=click.Path(exists=True),
    help="Path to an SD card image (.img, or the .zip adi-kuiper-gen emits)",
)
@click.option("--release", help="Kuiper release version to download and flash (e.g., 2023_R2_P1)")
@click.option(
    "--cache-path",
    default="/tmp/kuiper_cache",
    help="Where to download/extract images (default: /tmp/kuiper_cache)",
)
@click.option("--target", "-t", default="main", help="Target name in config (default: main)")
@click.option(
    "--mode",
    type=click.Choice(["dd", "bmaptool"]),
    default="dd",
    help=(
        "Write mode (default: dd). bmaptool is only faster with a .bmap alongside the "
        "image, which adi-kuiper-gen does not produce."
    ),
)
@click.option(
    "--sd-mode-after",
    type=click.Choice(["dut", "host", "off"]),
    default="dut",
    help="SD mux mode to leave set after writing (default: dut)",
)
@click.option(
    "--power-off/--no-power-off",
    default=True,
    help="Leave the board powered down after flashing (default: --power-off)",
)
@click.option(
    "--min-free-gb",
    type=float,
    default=24.0,
    help="Refuse to download/extract with less free space than this (default: 24)",
)
@click.option(
    "--dry-run", is_flag=True, help="Resolve the image and print the plan without writing anything"
)
def flash_sd(
    config,
    image,
    release,
    cache_path,
    target,
    mode,
    sd_mode_after,
    power_off,
    min_free_gb,
    dry_run,
):
    """Flash a full SD card image to a mux-attached card.

    Powers the board down, switches the SD mux to the host, writes the image to
    the card with labgrid's USBStorageDriver, then switches the mux back.

    DESTRUCTIVE: overwrites the entire card. The env yaml must declare a power
    driver, USBSDMuxDriver and USBStorageDriver.
    """
    if bool(image) == bool(release):
        raise click.ClickException("Pass exactly one of --image or --release")

    img = _resolve_flash_image(image, release, cache_path, min_free_gb)
    size_gb = os.path.getsize(img) / (1024**3)
    console.print(f"Image: [bold]{img}[/bold] ({size_gb:.2f} GiB)")

    if dry_run:
        # Deliberately before Environment()/get_target(): a RemotePlace env cannot
        # construct a target without an acquired place, and a dry run is most useful
        # exactly there.
        console.print("[bold yellow]Dry run[/bold yellow] -- nothing will be written. Plan:")
        console.print(f"  1. power off target '{target}' from {config}")
        console.print("  2. SD mux -> host")
        console.print(f"  3. write {img} with mode={mode}")
        console.print(f"  4. SD mux -> {sd_mode_after}")
        console.print(f"  5. {'leave powered off' if power_off else 'power cycle the board'}")
        return

    from labgrid.driver.usbstoragedriver import Mode

    env = Environment(config)
    tg = env.get_target(target)
    sdmux, writer, power = _get_flash_drivers(tg, config)

    try:
        power.off()
        tg.activate(sdmux)
        sdmux.set_mode("host")
        # The mux needs a moment for the card to re-enumerate on the host side.
        time.sleep(5)

        with console.status(
            f"[bold green]Writing {os.path.basename(img)} to the SD card "
            "(image is synced to the exporter first; this takes a while)..."
        ):
            tg.activate(writer)
            writer.write_image(filename=img, mode=Mode.DD if mode == "dd" else Mode.BMAPTOOL)
            tg.deactivate(writer)

        sdmux.set_mode(sd_mode_after)
        time.sleep(5)

        if not power_off:
            # Same workaround BootFPGASoC uses: after sdmux operations the board can
            # latch into a state where the first on() looks applied but emits no UART.
            power.off()
            time.sleep(5)
            power.on()
    except click.ClickException:
        raise
    except Exception as e:
        console.print(f"[bold red]Flash failed: {e}[/bold red]")
        raise click.ClickException(str(e)) from e

    console.print("[bold green]SD card flashed successfully![/bold green]")

    boot_partuuid, root_partuuid = _image_partuuids(img)
    if boot_partuuid:
        console.print(f"boot_partuuid={boot_partuuid}")
        console.print(f"root_partuuid={root_partuuid}")
        console.print(
            f"[yellow]Note:[/yellow] this image's PARTUUIDs differ from any previous image. "
            f"Env yamls pinning MassStorageDriver.partition by partuuid must be updated, or "
            f"switched to /dev/disk/by-label/{KUIPER_BOOT_LABEL}."
        )
        github_output = os.environ.get("GITHUB_OUTPUT")
        if github_output:
            with open(github_output, "a") as f:
                f.write(f"boot_partuuid={boot_partuuid}\n")
                f.write(f"root_partuuid={root_partuuid}\n")


@cli.command()
@click.option(
    "--config", "-c", required=True, type=click.Path(exists=True), help="Labgrid configuration file"
)
@click.option("--pre-boot-file", multiple=True, help="Format: local_path:remote_path")
@click.option("--post-boot-file", multiple=True, help="Format: local_path:remote_path")
@click.option("--target", "-t", default="main", help="Target name in config (default: main)")
@click.option("--state", default="shell", help="Target state to transition to (default: shell)")
def boot_selmap(config, pre_boot_file, post_boot_file, target, state):
    """Boot SelMap strategy (Dual FPGA design).

    This command uses the BootSelMap strategy to boot a primary Zynq SoC
    and then trigger a secondary Virtex FPGA boot via SelMap interface.
    """
    env = Environment(config)
    tg = env.get_target(target)

    strategy = tg.get_driver("BootSelMap")

    if pre_boot_file:
        pre_dict = {}
        for item in pre_boot_file:
            if ":" not in item:
                raise click.BadParameter("Format must be local_path:remote_path")
            local, remote = item.split(":", 1)
            pre_dict[os.path.abspath(local)] = remote
        strategy.pre_boot_boot_files = pre_dict
        logging.info(f"Set pre-boot files: {pre_dict}")

    if post_boot_file:
        post_dict = {}
        for item in post_boot_file:
            if ":" not in item:
                raise click.BadParameter("Format must be local_path:remote_path")
            local, remote = item.split(":", 1)
            post_dict[os.path.abspath(local)] = remote
        strategy.post_boot_boot_files = post_dict
        logging.info(f"Set post-boot files: {post_dict}")

    with console.status(f"[bold green]Transitioning {target} to {state} using BootSelMap..."):
        try:
            strategy.transition(state)
            console.print(f"[bold green]Successfully reached {state}![/bold green]")
        except Exception as e:
            console.print(f"[bold red]Transition failed: {e}[/bold red]")
            raise click.ClickException(str(e)) from e


@cli.command()
@click.option(
    "--config", "-c", required=True, type=click.Path(exists=True), help="Labgrid configuration file"
)
@click.option("--package", multiple=True, help="Package to install")
@click.option("--repo", multiple=True, help="Repo to clone (url,dest[,branch])")
@click.option("--build", multiple=True, help="Build command (cmd,dir)")
@click.option("--test", multiple=True, help="Test command (cmd,dir)")
@click.option("--target", "-t", default="main", help="Target name in config (default: main)")
@click.option("--state", default="tested", help="Target state to transition to (default: tested)")
def provision_software(config, package, repo, build, test, target, state):
    """Provision software on the target.

    This command installs packages, clones repos, builds software, and runs tests
    using the SoftwareProvisioningStrategy.
    """
    env = Environment(config)
    tg = env.get_target(target)

    strategy = tg.get_driver("SoftwareProvisioningStrategy")

    if package:
        strategy.packages = list(package)

    if repo:
        repos = []
        for item in repo:
            parts = item.split(",")
            if len(parts) < 2:
                raise click.BadParameter("Repo format must be url,dest[,branch]")
            url, dest = parts[0], parts[1]
            branch = parts[2] if len(parts) > 2 else None
            repos.append({"url": url, "dest": dest, "branch": branch})
        strategy.repos = repos

    if build:
        builds = []
        for item in build:
            if "," not in item:
                raise click.BadParameter("Build format must be cmd,dir")
            cmd, directory = item.split(",", 1)
            builds.append({"cmd": cmd, "dir": directory})
        strategy.build_steps = builds

    if test:
        tests = []
        for item in test:
            if "," not in item:
                raise click.BadParameter("Test format must be cmd,dir")
            cmd, directory = item.split(",", 1)
            tests.append({"cmd": cmd, "dir": directory})
        strategy.test_steps = tests

    with console.status(f"[bold green]Provisioning software on {target} to {state}..."):
        try:
            strategy.transition(state)
            console.print(f"[bold green]Successfully reached {state}![/bold green]")
        except Exception as e:
            console.print(f"[bold red]Provisioning failed: {e}[/bold red]")
            raise click.ClickException(str(e)) from e


@cli.command(name="download-cloudsmith")
@click.option("--fpga-carrier", required=False, help="FPGA carrier, e.g. zcu102")
@click.option("--daughter-card", required=False, help="Daughter card, e.g. adrv9009")
@click.option(
    "--vfilter",
    required=False,
    multiple=True,
    help="Generic version tag filter. Device info is all in the version flag. "
    "Repeatable; each value adds an AND-ed match clause.",
)
@click.option(
    "--vnot",
    multiple=True,
    help="Exclude packages whose version matches this term. "
    "Repeatable; each value adds an AND-ed exclusion clause.",
)
@click.option("--filename", default="BOOT.BIN", show_default=True, help="Artifact filename")
@click.option("--owner", default="adi", show_default=True, help="Cloudsmith owner/org")
@click.option(
    "--repo", default="sdg-boot-partition", show_default=True, help="Cloudsmith repository"
)
@click.option("--version", default=None, help="Pin an exact package version (default: latest)")
@click.option(
    "--cache-path",
    default="~/.labgrid/cloudsmith_releases/",
    show_default=True,
    help="Cache directory for downloaded artifacts",
)
@click.option(
    "--out",
    type=click.Path(),
    default=None,
    help="Copy the artifact here after download (file path or existing directory)",
)
def download_cloudsmith(
    fpga_carrier, daughter_card, vfilter, vnot, filename, owner, repo, version, cache_path, out
):
    """Download a boot artifact from Cloudsmith.

    Resolves the latest (or pinned) package matching the FPGA carrier and
    daughter card in the Cloudsmith repo, downloads it into the local cache
    (sha256-verified), and prints the cached path. Requires the
    CLOUDSMITH_API_TOKEN environment variable.
    """
    if not fpga_carrier and not daughter_card and not vfilter:
        raise click.ClickException(
            "Must have at least --fpga-carrier or --daughter-card or --vfilter set"
        )
    try:
        path = download_cloudsmith_boot_file(
            fpga_carrier=fpga_carrier,
            daughter_card=daughter_card,
            vfilter=vfilter,
            vnot=vnot,
            filename=filename,
            owner=owner,
            repo=repo,
            version=version,
            cache_path=cache_path,
        )
    except Exception as e:
        console.print(f"[bold red]Download failed: {e}[/bold red]")
        raise click.ClickException(str(e)) from e

    console.print(f"[bold green]Downloaded:[/bold green] {path}")
    if out:
        dest = os.path.join(out, os.path.basename(path)) if os.path.isdir(out) else out
        try:
            shutil.copy2(path, dest)
        except OSError as e:
            console.print(f"[bold red]Copy failed: {e}[/bold red]")
            raise click.ClickException(str(e)) from e
        console.print(f"[bold green]Copied to:[/bold green] {dest}")


@cli.command(name="build-recovery-initramfs")
@click.option(
    "--busybox",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the cross-compiled static busybox binary (ARM EABI for Zynq-7000).",
)
@click.option(
    "--out",
    "-o",
    "output",
    required=True,
    type=click.Path(dir_okay=False),
    help="Destination uImage path (e.g. /var/lib/tftpboot/uInitrd.recovery).",
)
@click.option(
    "--work-dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Directory for intermediate cpio + rootfs staging. Defaults to <out>.workdir.",
)
@click.option("--image-name", default="ZC706-recovery", help="uImage 'Image Name' field.")
@click.option(
    "--raw-cpio-gz/--uimage",
    default=False,
    help="Emit raw cpio.gz instead of a U-Boot uImage (skips the mkimage step).",
)
def build_recovery_initramfs_cmd(busybox, output, work_dir, image_name, raw_cpio_gz):
    """Build a recovery initramfs for ``BootZynq7000JTAGRecovery``.

    Bundles the ``/init`` + udhcpc hook + busybox applet symlinks defined
    in :mod:`adi_lg_plugins.recovery` and packages them as either a raw
    cpio.gz or a U-Boot uImage ready for ``bootm``.
    """
    from adi_lg_plugins.recovery import build_recovery_initramfs

    try:
        sizes = build_recovery_initramfs(
            busybox=busybox,
            output=output,
            work_dir=work_dir,
            image_name=image_name,
            wrap_uimage=not raw_cpio_gz,
        )
    except Exception as e:
        console.print(f"[bold red]Build failed: {e}[/bold red]")
        raise click.ClickException(str(e)) from e

    console.print(
        f"[bold green]Wrote {output}[/bold green]\n"
        f"  cpio:   {sizes['cpio']:>10} B\n"
        f"  cpio.gz: {sizes['gz']:>10} B"
        + (f"\n  uImage:  {sizes['uimage']:>10} B" if "uimage" in sizes else "")
    )


@cli.command(name="list-hardware")
@click.option("--coord", default=None, help="Coordinator host:port (default: $LG_COORDINATOR)")
@click.option("--carrier", default=None, help="Filter places by carrier")
@click.option(
    "--part",
    "--daughter-board",
    "part",
    default=None,
    help="Filter places by daughter board / part",
)
@click.option(
    "--available-only",
    "--only-available",
    "available_only",
    is_flag=True,
    help="Only list available (unacquired) places",
)
@click.option(
    "--force-cli",
    is_flag=True,
    help="Force using the labgrid-client CLI path instead of REST API",
)
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format")
def list_hardware(coord, carrier, part, available_only, force_cli, json_output):
    """List available places on the coordinator."""
    from dataclasses import asdict

    from rich import box
    from rich.table import Table

    try:
        coord_resolved = resolve_coordinator(coord)
        warn_if_rest_port(coord_resolved)
    except (RuntimeError, ValueError) as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise click.ClickException(str(e)) from e

    try:
        places, skipped = list_live_places(coord_resolved, force_cli=force_cli)
    except Exception as e:
        console.print(f"[bold red]Error querying coordinator {coord_resolved}:[/bold red] {e}")
        raise click.ClickException(f"Failed to list hardware: {e}") from e

    # Filter places
    filtered_places = []
    for p in places:
        if carrier and p.carrier.lower() != carrier.lower():
            continue
        if part and p.daughter_board.lower() != part.lower():
            continue
        if available_only and p.is_acquired:
            continue
        filtered_places.append(p)

    if json_output:
        serialized = [asdict(p) for p in filtered_places]
        console.print_json(data=serialized)
        return

    if skipped:
        from rich.console import Console as RichConsole

        console_err = RichConsole(stderr=True)
        console_err.print(
            f"[yellow]Warning: {len(skipped)} place(s) skipped due to validation errors:[/yellow]"
        )
        for name, reason in skipped:
            console_err.print(f"  - {name}: {reason}")

    if not filtered_places:
        console.print("No matching places found on the coordinator.")
        return

    table = Table(
        title=f"Live Places on Coordinator ({coord_resolved})",
        box=box.ROUNDED,
        header_style="bold magenta",
        title_style="bold cyan",
    )
    table.add_column("Place", style="bold white")
    table.add_column("Carrier")
    table.add_column("Daughter Board")
    table.add_column("Strategy")
    table.add_column("HDL Config")
    table.add_column("Status")
    table.add_column("Exporter")

    for p in filtered_places:
        if p.acquired:
            status_str = f"[bold red]Acquired ({p.acquired})[/bold red]"
        else:
            status_str = "[bold green]Available[/bold green]"

        hdl_cfg = p.hdl_config if p.hdl_config else "-"
        exporter_str = p.exporter if p.exporter else "-"

        table.add_row(
            p.name,
            p.carrier,
            p.daughter_board,
            p.boot_strategy,
            hdl_cfg,
            status_str,
            exporter_str,
        )

    console.print(table)


if __name__ == "__main__":
    cli()
