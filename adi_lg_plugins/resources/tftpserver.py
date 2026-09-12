import socket

import attr
from labgrid.factory import target_factory
from labgrid.resource.common import Resource


@target_factory.reg_resource
@attr.s(eq=False)
class TFTPServerResource(Resource):
    """Resource to configure or discover the TFTP server address."""

    address = attr.ib(default="auto", validator=attr.validators.instance_of(str))
    port = attr.ib(default=3069, validator=attr.validators.instance_of(int))
    root = attr.ib(default="/var/lib/tftpboot", validator=attr.validators.instance_of(str))

    def get_ip(self):
        """Return an explicit address or locally discover one for legacy users.

        An ``auto`` resource received through a RemotePlace must be resolved by
        the activated TFTPServerDriver's exporter-side agent. Deriving it here
        would inspect the labgrid client and advertise the wrong machine.
        """
        if self.address and self.address != "auto":
            return self.address

        extra = getattr(self, "extra", None) or {}
        if isinstance(extra, dict) and extra.get("proxy"):
            raise RuntimeError(
                "TFTP address='auto' must be resolved by the exporter-side "
                "TFTPServerDriver; activate the driver and call get_server_ip()"
            )

        # Auto-discovery logic (formerly get_local_ip)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # using Google's DNS server to determine local IP, no data sent
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
