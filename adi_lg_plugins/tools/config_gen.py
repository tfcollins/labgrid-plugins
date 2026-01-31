import glob
import socket

import click
import yaml
from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt

console = Console()


def scan_serial_ports():
    """Scan for available serial ports."""
    # simple glob for linux
    return glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")


def get_local_ip():
    """Get local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class ConfigGenerator:
    def __init__(self):
        self.config = {"targets": {"main": {"resources": {}, "drivers": {}}}}
        self.target_name = "main"

    def add_resource(self, name, params):
        self.config["targets"][self.target_name]["resources"][name] = params

    def add_driver(self, name, params=None):
        self.config["targets"][self.target_name]["drivers"][name] = params or {}

    def configure_power(self):
        console.print("[bold cyan]Configuring Power Protocol[/bold cyan]")
        driver_type = Prompt.ask(
            "Select Power Driver",
            choices=["VesyncPowerDriver", "CyberPowerDriver", "Skip"],
            default="VesyncPowerDriver",
        )

        if driver_type == "VesyncPowerDriver":
            outlet_names = Prompt.ask("Outlet Names (comma separated)")
            username = Prompt.ask("VeSync Username")
            password = Prompt.ask("VeSync Password", password=True)
            delay = IntPrompt.ask("Power Cycle Delay (seconds)", default=5)

            self.add_resource(
                "VesyncOutlet",
                {
                    "outlet_names": outlet_names,
                    "username": username,
                    "password": password,
                    "delay": delay,
                },
            )
            self.add_driver("VesyncPowerDriver")

        elif driver_type == "CyberPowerDriver":
            address = Prompt.ask("PDU IP Address")
            outlet = IntPrompt.ask("Outlet Number")
            delay = IntPrompt.ask("Power Cycle Delay (seconds)", default=5)

            self.add_resource(
                "CyberPowerOutlet", {"address": address, "outlet": outlet, "delay": delay}
            )
            self.add_driver("CyberPowerDriver")

    def configure_shell(self):
        console.print("[bold cyan]Configuring Shell / Console[/bold cyan]")

        # Configure underlying console (Serial)
        ports = scan_serial_ports()
        port_choices = ports + ["Manual Entry"]

        console.print(f"Detected Serial Ports: {', '.join(ports)}")
        selected_port = Prompt.ask(
            "Select Serial Port",
            choices=port_choices,
            default=ports[0] if ports else "Manual Entry",
        )

        if selected_port == "Manual Entry":
            selected_port = Prompt.ask("Enter Serial Port Path")

        speed = IntPrompt.ask("Baud Rate", default=115200)

        # Add SerialPort resource and SerialDriver
        self.add_resource("SerialPort", {"port": selected_port, "speed": speed})
        self.add_driver("SerialDriver")

        # Configure ADIShellDriver
        prompt_regex = Prompt.ask("Shell Prompt Regex", default="root@.*:.*#")
        login_prompt = Prompt.ask("Login Prompt Regex", default="login:")
        username = Prompt.ask("Username", default="root")
        password = Prompt.ask("Password", default="analog")

        self.add_driver(
            "ADIShellDriver",
            {
                "prompt": prompt_regex,
                "login_prompt": login_prompt,
                "username": username,
                "password": password,
            },
        )

    def configure_sdmux(self):
        console.print("[bold cyan]Configuring SD Mux[/bold cyan]")
        # Assuming USBSDMuxDriver
        # It needs a USBSDMux resource or SigrokUSBTool?
        # Labgrid USBSDMuxDriver typically uses USBSDMux resource which uses control_path (path to device file for mux)
        # or it uses a generic USB resource.
        # Let's assume standard Labgrid USBSDMux resource which needs a path like /dev/sd-mux or similar.

        mux_path = Prompt.ask(
            "SD Mux Device Path", default="/dev/disk/by-id/usb-Linux_Autobuild_SD_Mux_..."
        )
        self.add_resource("USBSDMux", {"control_path": mux_path})
        self.add_driver("USBSDMuxDriver")

    def configure_mass_storage(self):
        console.print("[bold cyan]Configuring Mass Storage (Host side SD access)[/bold cyan]")
        device = Prompt.ask(
            "Block Device Path (host)", default="/dev/disk/by-id/usb-Linux_Autobuild_SD_Mux_..."
        )
        partition = IntPrompt.ask("Partition Number", default=1)

        self.add_resource("MassStorageDevice", {"device": device, "partition": partition})
        self.add_driver("MassStorageDriver")

    def configure_kuiper(self):
        console.print("[bold cyan]Configuring Kuiper Release[/bold cyan]")
        release = Prompt.ask("Default Release Version", default="2023_R2_P1")
        cache_dir = Prompt.ask("Cache Directory", default="/var/cache/kuiper")

        self.add_resource("KuiperRelease", {"release": release, "cache_dir": cache_dir})
        self.add_driver("KuiperDLDriver")

    def configure_tftp(self):
        console.print("[bold cyan]Configuring TFTP[/bold cyan]")

        local_ip = get_local_ip()

        use_managed = Confirm.ask("Use Managed Python TFTP Server?", default=True)

        if use_managed:
            address = Prompt.ask("Bind Address", default=local_ip)
            port = IntPrompt.ask("Port", default=3069)
            root = Prompt.ask("TFTP Root Directory", default="/var/lib/tftpboot")

            self.add_resource(
                "TFTPServerResource", {"address": address, "port": port, "root": root}
            )
            self.add_driver("TFTPServerDriver")
        else:
            # External TFTP server
            address = Prompt.ask("Server IP Address", default=local_ip)
            self.add_resource("TFTPServerResource", {"address": address})
            # No driver needed if unmanaged, but strategy might expect one?
            # BootFPGASoCTFTP strategy binds "tftp_driver": "TFTPServerDriver".
            # So if we use that strategy, we MUST use the driver.
            # If the user wants external TFTP, they might need a different strategy or custom config.
            # We'll assume managed for now if using that strategy.
            console.print(
                "[yellow]Note: BootFPGASoCTFTP strategy expects a managed driver. Adding it anyway.[/yellow]"
            )
            self.add_driver("TFTPServerDriver")

    def configure_image_writer(self):
        if Confirm.ask("Enable Image Writer (USBStorageDriver)?", default=False):
            # USBStorageDriver usually binds to a generic USB resource or similar.
            # Labgrid's USBStorageDriver needs a path.
            path = Prompt.ask("USB Device Path", default="/dev/disk/by-id/...")
            self.add_resource("USBStorage", {"path": path})  # Standard labgrid resource?
            # Actually Labgrid USBStorageDriver uses 'USBStorage' resource.
            self.add_driver("USBStorageDriver")

    def run(self):
        strategies = ["BootFPGASoC", "BootFPGASoCTFTP", "BootFPGASoCSSH"]
        selected_strategy = Prompt.ask("Select Strategy", choices=strategies, default="BootFPGASoC")

        self.target_name = Prompt.ask("Target Name", default="main")

        # Common configurations
        self.configure_power()
        self.configure_shell()

        if selected_strategy == "BootFPGASoC":
            self.configure_sdmux()
            self.configure_mass_storage()
            self.configure_kuiper()
            self.configure_image_writer()
            self.add_driver("BootFPGASoC")

        elif selected_strategy == "BootFPGASoCTFTP":
            self.configure_tftp()
            self.configure_kuiper()
            # Optional SSH
            if Confirm.ask("Configure SSH Driver?", default=False):
                # SSHDriver needs Hostname/IP resource or similar.
                # BootFPGASoCTFTP bindings: "ssh": {"SSHDriver", None}
                # SSHDriver binds to 'NetworkService'? or just uses 'hostname' resource?
                # Usually 'NetworkService' resource.
                address = Prompt.ask(
                    "Target IP Address (or auto-discovered)", default="192.168.1.10"
                )
                self.add_resource("NetworkService", {"address": address})
                self.add_driver("SSHDriver")

            self.add_driver("BootFPGASoCTFTP")

        elif selected_strategy == "BootFPGASoCSSH":
            # Needs Network, SSH, Kuiper (for files)
            address = Prompt.ask("Target IP Address", default="192.168.1.10")
            self.add_resource("NetworkService", {"address": address})
            self.add_driver("SSHDriver")
            self.configure_kuiper()
            self.add_driver("BootFPGASoCSSH")

        output_file = Prompt.ask("Output Filename", default=f"config_{self.target_name}.yaml")

        with open(output_file, "w") as f:
            yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)

        console.print(f"[bold green]Configuration generated: {output_file}[/bold green]")


@click.command()
def generate_config():
    """Interactive tool to generate Labgrid YAML configuration."""
    gen = ConfigGenerator()
    gen.run()
