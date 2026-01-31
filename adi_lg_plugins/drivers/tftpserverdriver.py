import logging
import os
import select
import socket
import struct
import threading

import attr
from labgrid.driver.common import Driver
from labgrid.factory import target_factory

from adi_lg_plugins.resources.tftpserver import TFTPServerResource

# TFTP Opcodes
OP_RRQ = 1
OP_WRQ = 2
OP_DATA = 3
OP_ACK = 4
OP_ERROR = 5

class SimpleTFTPServer:
    def __init__(self, address, port, root, logger=None):
        self.address = address
        self.port = port
        self.root = root
        self.logger = logger or logging.getLogger("SimpleTFTPServer")
        self.sock = None
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Allow reuse address to avoid "Address already in use" on restarts
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind((self.address, self.port))
            self.logger.info(f"TFTP Server started on {self.address}:{self.port}, root: {self.root}")
            self.running = True
            self.thread = threading.Thread(target=self._run_server, daemon=True)
            self.thread.start()
        except Exception as e:
            self.logger.error(f"Failed to bind TFTP server: {e}")
            raise

    def stop(self):
        self.running = False
        if self.sock:
            self.sock.close()
        if self.thread:
            self.thread.join()
        self.logger.info("TFTP Server stopped")

    def _run_server(self):
        while self.running:
            try:
                r, _, _ = select.select([self.sock], [], [], 0.5)
                if not r:
                    continue
                data, addr = self.sock.recvfrom(1024)
                threading.Thread(target=self._handle_request, args=(data, addr), daemon=True).start()
            except OSError:
                if self.running:
                   self.logger.error("Socket error in main loop")
                break
            except Exception as e:
                self.logger.exception(f"Error in TFTP server loop: {e}")

    def _send_error(self, sock, addr, code, message):
        # Opcode 5, ErrorCode, ErrMsg, 0
        pkt = struct.pack("!HH", OP_ERROR, code) + message.encode('ascii') + b'\x00'
        try:
            sock.sendto(pkt, addr)
        except Exception:
            pass

    def _handle_request(self, data, addr):
        if len(data) < 2:
            return
        opcode = struct.unpack("!H", data[:2])[0]
        if opcode == OP_RRQ:
            self._handle_rrq(data, addr)
        elif opcode == OP_WRQ:
            self.logger.warning(f"Write request from {addr} rejected")
            temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._send_error(temp_sock, addr, 2, "Access violation (Writes not supported)")
            temp_sock.close()
        else:
            # Ignore other opcodes on main port
            pass

    def _handle_rrq(self, data, addr):
        try:
            parts = data[2:].split(b'\x00')
            filename = parts[0].decode('ascii')
            # mode = parts[1].decode('ascii').lower() # mode is usually 'octet' or 'netascii'
        except Exception:
            self.logger.error(f"Malformed RRQ from {addr}")
            return

        # Security check: Prevent directory traversal
        if '..' in filename or filename.startswith('/'):
             # We treat filenames as relative to root.
             # Some clients send absolute paths (e.g. /boot/image).
             # We strip leading / to map to our root.
             clean_filename = filename.lstrip('/')
             if '..' in clean_filename:
                 s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                 self._send_error(s, addr, 2, "Access violation")
                 s.close()
                 return
             full_path = os.path.join(self.root, clean_filename)
        else:
             full_path = os.path.join(self.root, filename)

        full_path = os.path.abspath(full_path)
        if not full_path.startswith(os.path.abspath(self.root)):
             s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
             self._send_error(s, addr, 2, "Access violation")
             s.close()
             return

        if not os.path.exists(full_path):
            self.logger.warning(f"File not found: {full_path}")
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._send_error(s, addr, 1, "File not found")
            s.close()
            return

        self.logger.info(f"Sending {filename} to {addr}")

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            with open(full_path, 'rb') as f:
                block_num = 1
                while True:
                    chunk = f.read(512)
                    pkt = struct.pack("!HH", OP_DATA, block_num) + chunk

                    retries = 5
                    ack_received = False
                    while retries > 0:
                        client_sock.sendto(pkt, addr)

                        r, _, _ = select.select([client_sock], [], [], 2.0)
                        if r:
                            try:
                                ack_data, ack_addr = client_sock.recvfrom(1024)
                            except ConnectionRefusedError:
                                # Client closed port?
                                return

                            if ack_addr != addr:
                                continue

                            if len(ack_data) < 4:
                                continue

                            ack_op, ack_block = struct.unpack("!HH", ack_data[:4])
                            if ack_op == OP_ACK and ack_block == block_num:
                                ack_received = True
                                break
                            elif ack_op == OP_ERROR:
                                self.logger.error(f"Received error from client: {ack_data}")
                                return
                        retries -= 1

                    if not ack_received:
                        self.logger.error(f"Timeout waiting for ACK {block_num} from {addr}")
                        return

                    if len(chunk) < 512:
                        break # EOF

                    block_num = (block_num + 1) % 65536
                    if block_num == 0:
                        # RFC 1350 doesn't handle wrap-around, but some extensions do.
                        # For strictly RFC 1350, transfer fails after 32MB.
                        # Many u-boots handle wrap to 0 or 1. We'll wrap to 0.
                        pass
        except Exception as e:
            self.logger.error(f"Error during transfer: {e}")
        finally:
            client_sock.close()


@target_factory.reg_driver
@attr.s(eq=False)
class TFTPServerDriver(Driver):
    """
    TFTPServerDriver provides a pure Python TFTP server.
    """
    bindings = {
        "resource": TFTPServerResource,
    }

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.server = None

    def on_activate(self):
        ip = self.resource.get_ip()
        
        # Ensure root directory exists
        if not os.path.exists(self.resource.root):
            try:
                os.makedirs(self.resource.root)
            except OSError as e:
                self.logger.warning(f"Could not create TFTP root {self.resource.root}: {e}")

        # Bind to all interfaces to avoid issues with multi-homed setups
        self.server = SimpleTFTPServer(ip, self.resource.port, self.resource.root, logger=self.logger)
        self.server.start()
    def on_deactivate(self):
        if self.server:
            self.server.stop()
            self.server = None

    @Driver.check_active
    def get_server_address(self):
        if self.server:
            return f"{self.server.address}:{self.server.port}"
        return None
