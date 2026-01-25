import logging
import os

import click
from labgrid import Environment
from rich.console import Console
from rich.logging import RichHandler

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


if __name__ == "__main__":
    cli()
