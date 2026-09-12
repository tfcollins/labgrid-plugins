"""Stateful, stdlib-only TFTP service loaded by labgrid AgentWrapper."""

import atexit
import base64
import hashlib
import ipaddress
import os
import posixpath
import select
import socket
import struct
import tempfile
import threading
import uuid

OP_RRQ = 1
OP_WRQ = 2
OP_DATA = 3
OP_ACK = 4
OP_ERROR = 5


class TFTPServer:
    def __init__(self, address, port, root):
        self.address = address
        self.port = port
        self.root = os.path.realpath(root)
        self.socket = None
        self.running = False
        self.thread = None

    def start(self):
        os.makedirs(self.root, exist_ok=True)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Exclusive ownership is required: concurrent roots on one endpoint
        # must fail instead of receiving an arbitrary subset of requests.
        try:
            sock.bind((self.address, self.port))
        except Exception:
            sock.close()
            raise
        self.socket = sock
        self.port = sock.getsockname()[1]
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        sock = self.socket
        if sock is not None:
            sock.close()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
            self.thread = None
        self.socket = None

    def _run(self):
        while self.running:
            sock = self.socket
            if sock is None:
                return
            try:
                ready, _, _ = select.select([sock], [], [], 0.2)
                if not ready:
                    continue
                data, peer = sock.recvfrom(1024)
                threading.Thread(
                    target=self._handle_request, args=(data, peer), daemon=True
                ).start()
            except (OSError, ValueError):
                if self.running:
                    raise
                return

    @staticmethod
    def _send_error(sock, peer, code, message):
        packet = struct.pack("!HH", OP_ERROR, code) + message.encode("ascii") + b"\x00"
        try:
            sock.sendto(packet, peer)
        except OSError:
            pass

    def _handle_request(self, data, peer):
        if len(data) < 2:
            return
        opcode = struct.unpack("!H", data[:2])[0]
        if opcode == OP_RRQ:
            self._handle_rrq(data, peer)
        elif opcode == OP_WRQ:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                self._send_error(sock, peer, 2, "Access violation (writes not supported)")

    def _handle_rrq(self, data, peer):
        try:
            parts = data[2:].split(b"\x00")
            filename = parts[0].decode("ascii")
            if len(parts) < 3 or not parts[1]:
                raise ValueError("missing transfer mode")
            relative = _normalize_destination(filename)
            path = _path_in_root(self.root, relative)
        except (UnicodeDecodeError, ValueError):
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                self._send_error(sock, peer, 2, "Access violation")
            return

        if not os.path.isfile(path):
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                self._send_error(sock, peer, 1, "File not found")
            return

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client_sock:
            try:
                with open(path, "rb") as source:
                    block = 1
                    while True:
                        chunk = source.read(512)
                        packet = struct.pack("!HH", OP_DATA, block) + chunk
                        if not self._send_block(client_sock, peer, packet, block):
                            return
                        if len(chunk) < 512:
                            return
                        block = (block + 1) % 65536
            except OSError:
                return

    @staticmethod
    def _send_block(sock, peer, packet, block):
        for _attempt in range(5):
            sock.sendto(packet, peer)
            ready, _, _ = select.select([sock], [], [], 2.0)
            if not ready:
                continue
            try:
                response, response_peer = sock.recvfrom(1024)
            except ConnectionRefusedError:
                return False
            if response_peer != peer or len(response) < 4:
                continue
            opcode, response_block = struct.unpack("!HH", response[:4])
            if opcode == OP_ACK and response_block == block:
                return True
            if opcode == OP_ERROR:
                return False
        return False


def _normalize_destination(destination):
    if not isinstance(destination, str) or not destination or "\x00" in destination:
        raise ValueError("destination must be a non-empty relative path")
    if "\\" in destination or destination.startswith("/"):
        raise ValueError("destination must be a relative POSIX path")
    parts = destination.split("/")
    if ".." in parts:
        raise ValueError("destination traversal is not allowed")
    normalized = posixpath.normpath(destination)
    if normalized in ("", ".") or normalized.startswith("../"):
        raise ValueError("destination must name a file")
    return normalized


def _path_in_root(root, relative):
    root = os.path.realpath(root)
    path = os.path.realpath(os.path.join(root, relative))
    if os.path.commonpath((root, path)) != root:
        raise ValueError("destination escapes the TFTP root")
    return path


def _derive_address():
    candidates = []
    for destination in (("192.0.2.1", 9), ("198.51.100.1", 9)):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(destination)
            candidates.append(sock.getsockname()[0])
        except OSError:
            pass
        finally:
            sock.close()
    try:
        candidates.extend(
            info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        )
    except OSError:
        pass
    for candidate in candidates:
        address = ipaddress.ip_address(candidate)
        if not address.is_unspecified and not address.is_loopback and not address.is_link_local:
            return candidate
    raise RuntimeError(
        "cannot derive exporter address for TFTP address='auto'; configure a DUT-visible address"
    )


_server = None
_uploads = {}


def start(address, port, root):
    global _server
    if _server is not None:
        raise RuntimeError("TFTP server is already running")
    advertised_address = _derive_address() if address == "auto" else address
    parsed = ipaddress.ip_address(advertised_address)
    if parsed.version != 4 or parsed.is_unspecified:
        raise ValueError("TFTP address must be a specific IPv4 address or 'auto'")
    server = TFTPServer(advertised_address, int(port), root)
    server.start()
    _server = server
    return {"address": server.address, "port": server.port, "root": server.root}


def stop():
    global _server
    for token in list(_uploads):
        abort_upload(token)
    if _server is not None:
        _server.stop()
        _server = None


def begin_upload(destination):
    if _server is None:
        raise RuntimeError("TFTP server is not running")
    relative = _normalize_destination(destination)
    final_path = _path_in_root(_server.root, relative)
    parent = os.path.dirname(final_path)
    os.makedirs(parent, exist_ok=True)
    if os.path.commonpath((_server.root, os.path.realpath(parent))) != _server.root:
        raise ValueError("destination parent escapes the TFTP root")
    fd, temporary = tempfile.mkstemp(prefix=".tftp-upload-", dir=_server.root)
    token = uuid.uuid4().hex
    _uploads[token] = (fd, temporary, final_path, relative)
    return token


def write_upload(token, encoded):
    try:
        fd = _uploads[token][0]
    except KeyError as error:
        raise ValueError("unknown upload token") from error
    data = base64.b85decode(encoded.encode("ascii"))
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]
    return len(data)


def finish_upload(token):
    try:
        fd, temporary, final_path, relative = _uploads.pop(token)
    except KeyError as error:
        raise ValueError("unknown upload token") from error
    try:
        os.fsync(fd)
        os.close(fd)
        os.replace(temporary, final_path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return relative


def publish_existing(source, destination, sha256):
    """Atomically publish an exporter-local, digest-verified artifact."""
    if _server is None:
        raise RuntimeError("TFTP server is not running")
    source = os.path.realpath(os.path.expanduser(source))
    if not os.path.isfile(source):
        raise FileNotFoundError(source)
    digest = hashlib.sha256()
    with open(source, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != sha256:
        raise RuntimeError("artifact digest mismatch")
    relative = _normalize_destination(destination)
    token = begin_upload(relative)
    try:
        with open(source, "rb") as stream:
            for chunk in iter(lambda: stream.read(64 * 1024), b""):
                write_upload(token, base64.b85encode(chunk).decode("ascii"))
        return finish_upload(token)
    except Exception:
        abort_upload(token)
        raise


def abort_upload(token):
    upload = _uploads.pop(token, None)
    if upload is None:
        return
    fd, temporary, _final_path, _relative = upload
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.unlink(temporary)
    except OSError:
        pass


atexit.register(stop)

methods = {
    "start": start,
    "stop": stop,
    "begin_upload": begin_upload,
    "write_upload": write_upload,
    "finish_upload": finish_upload,
    "publish_existing": publish_existing,
    "abort_upload": abort_upload,
}
