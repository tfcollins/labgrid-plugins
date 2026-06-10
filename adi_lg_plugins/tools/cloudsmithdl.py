import argparse

from labgrid import Target

from adi_lg_plugins.drivers.cloudsmithdldriver import CloudsmithDLDriver
from adi_lg_plugins.resources.cloudsmithrelease import CloudsmithRelease


def download_cloudsmith_boot_file(
    fpga_carrier,
    daughter_card,
    filename,
    owner,
    repo,
    version,
    cache_path,
):
    """Resolve, download, and return the local path of the boot artifact."""
    target = Target("CloudsmithDownloader")
    CloudsmithRelease(
        target,
        name=None,
        fpga_carrier=fpga_carrier,
        daughter_card=daughter_card,
        filename=filename,
        owner=owner,
        repo=repo,
        version=version,
        cache_path=cache_path,
    )

    dl = CloudsmithDLDriver(target, name=None)

    target.activate(dl)
    return dl.get_boot_file_path()


def main():
    parser = argparse.ArgumentParser(description="Download a Cloudsmith boot artifact")
    parser.add_argument("--fpga-carrier", type=str, required=True, help="FPGA carrier, e.g. zcu102")
    parser.add_argument(
        "--daughter-card", type=str, required=True, help="Daughter card, e.g. adrv9009"
    )
    parser.add_argument("--filename", type=str, default="BOOT.BIN", help="Artifact filename")
    parser.add_argument("--owner", type=str, default="adi", help="Cloudsmith owner/org")
    parser.add_argument("--repo", type=str, default="sdg-boot-partition", help="Cloudsmith repo")
    parser.add_argument(
        "--version", type=str, default=None, help="Pin an exact package version (default: latest)"
    )
    parser.add_argument(
        "--cache-path",
        type=str,
        default="/tmp/cloudsmith_cache",
        help="Path to cache the downloaded artifact.",
    )

    args = parser.parse_args()
    path = download_cloudsmith_boot_file(
        args.fpga_carrier,
        args.daughter_card,
        args.filename,
        args.owner,
        args.repo,
        args.version,
        args.cache_path,
    )
    print(f"Downloaded boot file: {path}")
