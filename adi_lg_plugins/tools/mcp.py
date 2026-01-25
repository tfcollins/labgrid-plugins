import os
import logging
from typing import Optional, Dict
from fastmcp import FastMCP
from labgrid import Environment

# Initialize FastMCP server
mcp = FastMCP("ADI Labgrid Plugins")

def _get_target_and_strategy(config_path: str, target_name: str, strategy_driver: str):
    """Helper to initialize Labgrid environment and get strategy."""
    env = Environment(config_path)
    tg = env.get_target(target_name)
    strategy = tg.get_driver(strategy_driver)
    return tg, strategy

def _boot_fabric(
    config_path: str,
    bitstream_path: Optional[str] = None,
    kernel_path: Optional[str] = None,
    target: str = "main",
    state: str = "shell"
) -> str:
    try:
        tg, strategy = _get_target_and_strategy(config_path, target, "BootFabric")
        
        try:
            resource = tg.get_resource("XilinxDeviceJTAG")
            if bitstream_path:
                resource.bitstream_path = os.path.abspath(bitstream_path)
            if kernel_path:
                resource.kernel_path = os.path.abspath(kernel_path)
        except Exception:
            pass

        strategy.transition(state)
        return f"Successfully reached state '{state}' for target '{target}' using BootFabric."
    except Exception as e:
        return f"Error during BootFabric transition: {str(e)}"

@mcp.tool()
def boot_fabric(
    config_path: str,
    bitstream_path: Optional[str] = None,
    kernel_path: Optional[str] = None,
    target: str = "main",
    state: str = "shell"
) -> str:
    """
    Boot an FPGA using the JTAG-based BootFabric strategy.
    
    Args:
        config_path: Path to the Labgrid configuration file (yaml).
        bitstream_path: Optional path to override the FPGA bitstream file (.bit).
        kernel_path: Optional path to override the Linux kernel image (.strip).
        target: Target name in the configuration (default: 'main').
        state: Target state to transition to (default: 'shell').
    """
    return _boot_fabric(config_path, bitstream_path, kernel_path, target, state)

def _boot_soc(
    config_path: str,
    release_version: Optional[str] = None,
    kernel_path: Optional[str] = None,
    bootbin_path: Optional[str] = None,
    devicetree_path: Optional[str] = None,
    target: str = "main",
    state: str = "shell",
    update_image: bool = False
) -> str:
    try:
        tg, strategy = _get_target_and_strategy(config_path, target, "BootFPGASoC")
        
        try:
            resource = tg.get_resource("KuiperRelease")
            if release_version:
                resource.release_version = release_version
            if kernel_path:
                resource.kernel_path = os.path.abspath(kernel_path)
            if bootbin_path:
                resource.BOOTBIN_path = os.path.abspath(bootbin_path)
            if devicetree_path:
                resource.device_tree_path = os.path.abspath(devicetree_path)
        except Exception:
            pass

        if update_image:
            strategy.update_image = True

        strategy.transition(state)
        return f"Successfully reached state '{state}' for target '{target}' using BootFPGASoC."
    except Exception as e:
        return f"Error during BootFPGASoC transition: {str(e)}"

@mcp.tool()
def boot_soc(
    config_path: str,
    release_version: Optional[str] = None,
    kernel_path: Optional[str] = None,
    bootbin_path: Optional[str] = None,
    devicetree_path: Optional[str] = None,
    target: str = "main",
    state: str = "shell",
    update_image: bool = False
) -> str:
    """
    Boot an FPGA SoC using the SD Mux-based BootFPGASoC strategy.
    
    Args:
        config_path: Path to the Labgrid configuration file (yaml).
        release_version: Optional Kuiper release version.
        kernel_path: Optional path to override the kernel file.
        bootbin_path: Optional path to override the BOOT.BIN file.
        devicetree_path: Optional path to override the devicetree file.
        target: Target name in the configuration (default: 'main').
        state: Target state to transition to (default: 'shell').
        update_image: Whether to update the full SD card image.
    """
    return _boot_soc(config_path, release_version, kernel_path, bootbin_path, devicetree_path, target, state, update_image)

def _boot_soc_ssh(
    config_path: str,
    release_version: Optional[str] = None,
    kernel_path: Optional[str] = None,
    bootbin_path: Optional[str] = None,
    devicetree_path: Optional[str] = None,
    target: str = "main",
    state: str = "shell"
) -> str:
    try:
        tg, strategy = _get_target_and_strategy(config_path, target, "BootFPGASoCSSH")
        
        try:
            resource = tg.get_resource("KuiperRelease")
            if release_version:
                resource.release_version = release_version
            if kernel_path:
                resource.kernel_path = os.path.abspath(kernel_path)
            if bootbin_path:
                resource.BOOTBIN_path = os.path.abspath(bootbin_path)
            if devicetree_path:
                resource.device_tree_path = os.path.abspath(devicetree_path)
        except Exception:
            pass

        strategy.transition(state)
        return f"Successfully reached state '{state}' for target '{target}' using BootFPGASoCSSH."
    except Exception as e:
        return f"Error during BootFPGASoCSSH transition: {str(e)}"

@mcp.tool()
def boot_soc_ssh(
    config_path: str,
    release_version: Optional[str] = None,
    kernel_path: Optional[str] = None,
    bootbin_path: Optional[str] = None,
    devicetree_path: Optional[str] = None,
    target: str = "main",
    state: str = "shell"
) -> str:
    """
    Boot an FPGA SoC via SSH using the BootFPGASoCSSH strategy.
    
    Args:
        config_path: Path to the Labgrid configuration file (yaml).
        release_version: Optional Kuiper release version.
        kernel_path: Optional path to override the kernel file.
        bootbin_path: Optional path to override the BOOT.BIN file.
        devicetree_path: Optional path to override the devicetree file.
        target: Target name in the configuration (default: 'main').
        state: Target state to transition to (default: 'shell').
    """
    return _boot_soc_ssh(config_path, release_version, kernel_path, bootbin_path, devicetree_path, target, state)

def _boot_selmap(
    config_path: str,
    pre_boot_files: Optional[Dict[str, str]] = None,
    post_boot_files: Optional[Dict[str, str]] = None,
    target: str = "main",
    state: str = "shell"
) -> str:
    try:
        tg, strategy = _get_target_and_strategy(config_path, target, "BootSelMap")
        
        if pre_boot_files:
            strategy.pre_boot_boot_files = {os.path.abspath(k): v for k, v in pre_boot_files.items()}
        if post_boot_files:
            strategy.post_boot_boot_files = {os.path.abspath(k): v for k, v in post_boot_files.items()}

        strategy.transition(state)
        return f"Successfully reached state '{state}' for target '{target}' using BootSelMap."
    except Exception as e:
        return f"Error during BootSelMap transition: {str(e)}"

@mcp.tool()
def boot_selmap(
    config_path: str,
    pre_boot_files: Optional[Dict[str, str]] = None,
    post_boot_files: Optional[Dict[str, str]] = None,
    target: str = "main",
    state: str = "shell"
) -> str:
    """
    Boot a dual-FPGA system using the BootSelMap strategy.
    
    Args:
        config_path: Path to the Labgrid configuration file (yaml).
        pre_boot_files: Optional dictionary mapping local paths to remote paths for pre-boot.
        post_boot_files: Optional dictionary mapping local paths to remote paths for post-boot.
        target: Target name in the configuration (default: 'main').
        state: Target state to transition to (default: 'shell').
    """
    return _boot_selmap(config_path, pre_boot_files, post_boot_files, target, state)

def main():
    """Main entry point for the MCP server."""
    mcp.run()

if __name__ == "__main__":
    main()