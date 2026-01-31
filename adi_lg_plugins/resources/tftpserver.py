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
        """Returns the configured IP or discovers it if set to 'auto'."""
        if self.address and self.address != "auto":
            return self.address

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
