import glob
import socket

import click
import yaml
from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt

from adi_lg_plugins.tools._answers import Run, answers_dir, pick_run
from adi_lg_plugins.tools._choices import ask_choice

try:
    import serial.tools.list_ports

    HAS_PYSERIAL = True
except ImportError:
    HAS_PYSERIAL = False

console = Console()

# Saved runs live in answers_dir(_ANSWERS), one file per target name.
_ANSWERS = "generate-config"
_COMMAND = "adi-lg generate-config"
_STRATEGIES = [
    ("BootFPGASoC", "SD card through a USB SD mux"),
    ("BootFPGASoCTFTP", "kernel over TFTP from U-Boot"),
    ("BootFPGASoCSSH", "boot files copied over SSH"),
]
_POWER_DRIVERS = [
    ("VesyncPowerDriver", "VeSync smart plug"),
    ("CyberPowerDriver", "CyberPower PDU (SNMP)"),
    ("Skip", "no power control"),
]


def scan_serial_ports():
    """Scan for available serial ports with descriptions.

    Returns:
        List[Tuple[str, str]]: List of (device, description) tuples.
    """
    if HAS_PYSERIAL:
        ports = []
        for p in serial.tools.list_ports.comports():
            ports.append((p.device, p.description))
        return sorted(ports)
    else:
        # Fallback
        devs = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        return sorted([(d, "Unknown") for d in devs])


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
    """Asks for each part of the config; ``session`` saves the answers so a run can resume."""

    def __init__(self, session: Run | None = None):
        # labgrid has no plugin auto-discovery: this import is what lets it resolve
        # the ADI drivers and strategies the config names.
        self.config = {
            "imports": ["adi_lg_plugins"],
            "targets": {"main": {"resources": {}, "drivers": {}}},
        }
        self.target_name = "main"
        self.session = session or Run(_COMMAND, console)

    def ask(self, key, prompt, cls=Prompt, *, default=None, reask=False, **kwargs):
        """``cls.ask(prompt)``, or its saved answer when resuming."""
        return self.session.answer(
            key,
            prompt,
            lambda default: cls.ask(prompt, default=default, **kwargs),
            default=default,
            reask=reask,
        )

    def choose(self, key, prompt, options, *, default):
        """A numbered choice, or its saved answer when resuming."""
        return self.session.answer(
            key,
            prompt,
            lambda default: ask_choice(console, prompt, options, default=default),
            default=default,
            choices=[name for name, _ in options],
        )

    def add_resource(self, name, params):
        self.config["targets"][self.target_name]["resources"][name] = params

    def add_driver(self, name, params=None):
        self.config["targets"][self.target_name]["drivers"][name] = params or {}

    def configure_power(self):
        console.print("[bold cyan]Configuring Power Protocol[/bold cyan]")
        driver_type = self.choose(
            "power_driver", "Select Power Driver", _POWER_DRIVERS, default="VesyncPowerDriver"
        )

        if driver_type == "VesyncPowerDriver":
            outlet_names = self.ask("vesync.outlet_names", "Outlet Names (comma separated)")
            username = self.ask("vesync.username", "VeSync Username")
            # An account password: asked every run, never saved.
            password = Prompt.ask("VeSync Password", password=True)
            delay = self.ask("power.delay", "Power Cycle Delay (seconds)", IntPrompt, default=5)

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
            address = self.ask("cyberpower.address", "PDU IP Address")
            outlet = self.ask("cyberpower.outlet", "Outlet Number", IntPrompt)
            delay = self.ask("power.delay", "Power Cycle Delay (seconds)", IntPrompt, default=5)

            self.add_resource(
                "CyberPowerOutlet", {"address": address, "outlet": outlet, "delay": delay}
            )
            self.add_driver("CyberPowerDriver")

    def configure_shell(self):
        console.print("[bold cyan]Configuring Shell / Console[/bold cyan]")

        def ask_port(default):
            # Configure underlying console (Serial)
            ports_info = scan_serial_ports()

            if ports_info:
                console.print("Detected Serial Ports:")
                port_choices = [*ports_info, ("Manual Entry", "type a device path")]
                default_port = ports_info[0][0]
            else:
                console.print("No serial ports detected.")
                port_choices = [("Manual Entry", "type a device path")]
                default_port = "Manual Entry"
            # A saved port that is not plugged in now is still offered.
            if default and default not in [p for p, _ in port_choices]:
                port_choices.insert(0, (default, "saved answer"))

            port = ask_choice(
                console,
                "Select Serial Port",
                port_choices,
                headers=("Port", "Description"),
                default=default or default_port,
            )
            if port == "Manual Entry":
                port = Prompt.ask("Enter Serial Port Path")
            return port

        selected_port = self.session.answer("serial_port", "Serial port", ask_port)

        speed = self.ask("serial.speed", "Baud Rate", IntPrompt, default=115200)

        # Add SerialPort resource and SerialDriver
        self.add_resource("SerialPort", {"port": selected_port, "speed": speed})
        self.add_driver("SerialDriver")

        # Configure ADIShellDriver
        prompt_regex = self.ask("shell.prompt", "Shell Prompt Regex", default="root@.*:.*#")
        login_prompt = self.ask("shell.login_prompt", "Login Prompt Regex", default="login:")
        username = self.ask("shell.username", "Username", default="root")
        password = self.ask("shell.password", "Password", default="analog")

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
        mux_path = self.ask(
            "sdmux.path",
            "SD Mux Device Path",
            default="/dev/disk/by-id/usb-Linux_Autobuild_SD_Mux_...",
        )
        self.add_resource("USBSDMux", {"control_path": mux_path})
        self.add_driver("USBSDMuxDriver")

    def configure_mass_storage(self):
        console.print("[bold cyan]Configuring Mass Storage (Host side SD access)[/bold cyan]")
        device = self.ask(
            "mass_storage.device",
            "Block Device Path (host)",
            default="/dev/disk/by-id/usb-Linux_Autobuild_SD_Mux_...",
        )
        partition = self.ask("mass_storage.partition", "Partition Number", IntPrompt, default=1)

        self.add_resource("MassStorageDevice", {"device": device, "partition": partition})
        self.add_driver("MassStorageDriver")

    def configure_kuiper(self):
        console.print("[bold cyan]Configuring Kuiper Release[/bold cyan]")
        release = self.ask("kuiper.release", "Default Release Version", default="2023_R2_P1")
        cache_dir = self.ask("kuiper.cache_dir", "Cache Directory", default="/var/cache/kuiper")

        self.add_resource("KuiperRelease", {"release": release, "cache_dir": cache_dir})
        self.add_driver("KuiperDLDriver")

    def configure_tftp(self):
        console.print("[bold cyan]Configuring TFTP[/bold cyan]")

        local_ip = get_local_ip()

        use_managed = self.ask(
            "tftp.managed", "Use Managed Python TFTP Server?", Confirm, default=True
        )

        if use_managed:
            address = self.ask("tftp.address", "Bind Address", default=local_ip)
            port = self.ask("tftp.port", "Port", IntPrompt, default=3069)
            root = self.ask("tftp.root", "TFTP Root Directory", default="/var/lib/tftpboot")

            self.add_resource(
                "TFTPServerResource", {"address": address, "port": port, "root": root}
            )
            self.add_driver("TFTPServerDriver")
        else:
            # External TFTP server
            address = self.ask("tftp.address", "Server IP Address", default=local_ip)
            self.add_resource("TFTPServerResource", {"address": address})

            console.print(
                "[yellow]Note: BootFPGASoCTFTP strategy expects a managed driver. Adding it anyway.[/yellow]"
            )
            self.add_driver("TFTPServerDriver")

    def configure_image_writer(self):
        if self.ask(
            "image_writer", "Enable Image Writer (USBStorageDriver)?", Confirm, default=False
        ):
            # USBStorageDriver usually binds to a generic USB resource or similar.
            # Labgrid's USBStorageDriver needs a path.
            path = self.ask("image_writer.path", "USB Device Path", default="/dev/disk/by-id/...")
            self.add_resource("USBStorage", {"path": path})  # Standard labgrid resource?
            # Actually Labgrid USBStorageDriver uses 'USBStorage' resource.
            self.add_driver("USBStorageDriver")

    def run(self):
        selected_strategy = self.choose(
            "strategy", "Select Strategy", _STRATEGIES, default="BootFPGASoC"
        )

        self.target_name = self.ask("target", "Target Name", default="main")
        # From here on the answers are saved, in a file named after the target.
        self.session.save_as(self.target_name)
        if self.target_name != "main":
            self.config["targets"][self.target_name] = self.config["targets"].pop("main")

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
            if self.ask("ssh", "Configure SSH Driver?", Confirm, default=False):
                # SSHDriver needs Hostname/IP resource or similar.
                address = self.ask(
                    "ssh.address", "Target IP Address (or auto-discovered)", default="192.168.1.10"
                )
                self.add_resource("NetworkService", {"address": address})
                self.add_driver("SSHDriver")

            self.add_driver("BootFPGASoCTFTP")

        elif selected_strategy == "BootFPGASoCSSH":
            # Needs Network, SSH, Kuiper (for files)
            address = self.ask("ssh.address", "Target IP Address", default="192.168.1.10")
            self.add_resource("NetworkService", {"address": address})
            self.add_driver("SSHDriver")
            self.configure_kuiper()
            self.add_driver("BootFPGASoCSSH")

        # Asked again on resume (the saved name is the default): a path that
        # can't be written is what stops a run here.
        output_file = self.ask(
            "output", "Output Filename", default=f"config_{self.target_name}.yaml", reask=True
        )

        try:
            with open(output_file, "w") as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
        except OSError as e:
            raise click.ClickException(f"could not write {output_file}: {e.strerror}") from e

        console.print(f"[bold green]Configuration generated: {output_file}[/bold green]")
        # Written, so there is nothing left to resume.
        self.session.saved.delete()


@click.command()
def generate_config():
    """Interactive tool to generate Labgrid YAML configuration."""
    session = pick_run(
        console,
        command=_COMMAND,
        directory=answers_dir(_ANSWERS),
        headers=("Target", "Strategy", "Saved", "Answers"),
        describe=lambda r: (
            r.answers.get("strategy", ""),
            r.saved_at,
            f"{len(r.answers)} saved",
        ),
        new="start a new config",
    )
    with session.reporting():
        ConfigGenerator(session).run()
