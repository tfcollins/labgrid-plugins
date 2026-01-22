import argparse

from labgrid import Target

from adi_lg_plugins.drivers.kuiperdldriver import KuiperDLDriver
from adi_lg_plugins.resources.kuiperrelease import KuiperRelease


def list_kuiper_boot_files(release_version, cache_path):
    target = Target("KuiperDownloader")
    KuiperRelease(target, name=None, release_version=release_version, cache_path=cache_path)

    dl = KuiperDLDriver(target, name=None)

    target.activate(dl)
    out = dl.get_boot_files_from_release(get_all_files=True)

    print("Extracted files:")
    for f in out:
        print(f"{f['type']}: {f['path']} ({f['size']} bytes)")


# if __name__ == "__main__":
def main():
    parser = argparse.ArgumentParser(description="List Kuiper release boot files")
    parser.add_argument(
        "--release-version",
        type=str,
        required=True,
        help="Version of the Kuiper release to download and manage.",
    )
    parser.add_argument(
        "--cache-path",
        type=str,
        default="/tmp/kuiper_cache",
        help="Path to cache the downloaded Kuiper release.",
    )

    args = parser.parse_args()
    list_kuiper_boot_files(args.release_version, args.cache_path)
