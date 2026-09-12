"""Location-aware artifacts exchanged between exporter-capable drivers."""

import hashlib
import os
from dataclasses import asdict, dataclass

from labgrid.util.ssh import sshmanager


@dataclass(frozen=True)
class ArtifactRef:
    """A verified file path owned by either the client or one exporter."""

    path: str
    host: str | None
    sha256: str
    size: int

    @classmethod
    def from_dict(cls, value):
        return cls(**value)

    def to_dict(self):
        return asdict(self)

    def materialize_on_client(self, destination: str) -> str:
        """Return a client-valid path, downloading only when required."""
        if self.host is None:
            return self.path
        destination = os.path.abspath(os.path.expanduser(destination))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        if os.path.isfile(destination) and _sha256(destination) == self.sha256:
            return destination
        sshmanager.get(self.host).get_file(self.path, destination)
        if _sha256(destination) != self.sha256:
            os.unlink(destination)
            raise RuntimeError(f"Artifact digest mismatch while fetching {self.path}")
        return destination


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_artifact(path: str) -> ArtifactRef:
    path = os.path.abspath(os.path.expanduser(path))
    return ArtifactRef(path=path, host=None, sha256=_sha256(path), size=os.path.getsize(path))
