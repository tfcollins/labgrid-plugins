"""Kuiper Downloader Driver for Labgrid."""

import attr
import time
import os
import shutil
import subprocess
import json
import requests
import hashlib
import pathlib
import lzma
import zipfile
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from tqdm import tqdm

from labgrid.driver.common import Driver
from labgrid.factory import target_factory

from labgrid.step import step

from .imageextractor import IMGFileExtractor

class Downloader(object):

    def releases(self, release="2019_R1"):
        rel = {}
        if release == "2018_R2":
            rel["imgname"] = "2018_R2-2019_05_23.img"
            rel["xzmd5"] = "c377ca95209f0f3d6901fd38ef2b4dfd"
            rel["imgmd5"] = "59c2fe68118c3b635617e36632f5db0b"
        elif release == "2019_R1":
            rel["imgname"] = "2019_R1-2020_02_04.img"
            rel["xzmd5"] = "49c121d5e7072ab84760fed78812999f"
            rel["imgmd5"] = "40aa0cd80144a205fc018f479eff5fce"
        elif release == "2023_R2_P1":
            # https://swdownloads.analog.com/cse/kuiper/image_2025-03-18-ADI-Kuiper-full.zip
            rel["imgname"] = "image_2025-03-18-ADI-Kuiper-full"
            # rel["imgname"] = "2023_R2_P1-2025_03_18.img"
            rel["zipmd5"] = "6c92259dd61520d08244012f6c92d7c6"
            rel["imgmd5"] = "873b4977617e40725025aa4958f3ca7e"
        else:
            raise Exception("Unknown release")
        if "xzmd5" in rel:
            rel["link"] = "http://swdownloads.analog.com/cse/" + rel["imgname"] + ".xz"
            rel["xzname"] = rel["imgname"] + ".xz"
        elif "zipmd5" in rel:
            rel["link"] = "https://swdownloads.analog.com/cse/kuiper/" + rel["imgname"] + ".zip"
            rel["zipname"] = rel["imgname"] + ".zip"
        return rel

    def retry_session(
        self,
        retries=3,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 504),
        session=None,
    ):
        session = session or requests.Session()
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def download(self, url, fname):
        resp = self.retry_session().get(url, stream=True)
        if not resp.ok:
            raise Exception(os.path.basename(fname) + " - File not found!")
        total = int(resp.headers.get("content-length", 0))
        sha256_hash = hashlib.sha256()
        with open(fname, "wb") as file, tqdm(
            desc=fname,
            total=total,
            unit="iB",
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for data in resp.iter_content(chunk_size=1024):
                size = file.write(data)
                sha256_hash.update(data)
                bar.update(size)
        hash = sha256_hash.hexdigest()
        with open(os.path.join(os.path.dirname(fname), "hashes.txt"), "a") as h:
            h.write(f"{os.path.basename(fname)},{hash}\n")

    def check(self, fname, ref, find_img=False):
        print("Checking " + fname + " against reference MD5: " + ref)
        hash_md5 = hashlib.md5()
        org_fname = fname
        if find_img and not os.path.isfile(fname):
            # Search for img file in same directory
            dirpath = os.path.abspath(fname)
            # dirpath = os.path.dirname(fname)
            for file in os.listdir(dirpath):
                if file.endswith(".img"):
                    fname = os.path.join(dirpath, file)
                    print(f"Found image file {fname} for MD5 check")
                    break
            if not os.path.isfile(fname):
                raise Exception("No image file found for MD5 check")
        else:
            print("Using file " + fname + " for MD5 check")
        tlfile = pathlib.Path(fname)
        total = os.path.getsize(tlfile)
        with open(fname, "rb") as f, tqdm(
            desc="Hashing: " + fname,
            total=total,
            unit="iB",
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
                size = len(chunk)
                bar.update(size)
        h = hash_md5.hexdigest()
        if h == ref:
            print("MD5 Check: PASSED")
        else:
            print("MD5 Check: FAILEDZz")
            raise Exception("MD5 hash check failed")

        return fname

    def extract(self, inname, outname):
        print("Extracting " + inname + " to " + outname)
        if inname.endswith(".xz"):
            self.extract_xz(inname, outname)
        elif inname.endswith(".zip"):
            self.extract_zip(inname, outname)
        else:
            raise Exception("Unknown compression format for " + inname)

    def extract_xz(self, inname, outname):
        tlfile = pathlib.Path(inname)

        decompressor = lzma.LZMADecompressor()
        with open(tlfile, "rb") as ifile:
            total = 0
            with open(outname, "wb") as file, tqdm(
                desc="Decompressing: " + outname,
                total=total,
                unit="iB",
                unit_scale=True,
                unit_divisor=1024,
            ) as bar:
                data = ifile.read(1024)
                while data:
                    result = decompressor.decompress(data)
                    if result != b"":
                        size = file.write(result)
                        bar.update(size)
                    data = ifile.read(1024)

    def extract_zip(self, inname, outdir):
        tlfile = pathlib.Path(inname)
        with zipfile.ZipFile(tlfile, 'r') as zip_ref:
            zip_ref.extractall(outdir)


@target_factory.reg_driver
@attr.s(eq=False)
class KuiperDLDriver(Driver):
    """KuiperDLDriver - Driver to download and manage Kuiper releases and provide
    files to the target device.
    """

    bindings = {"kuiper_resource": {"KuiperRelease"}}

    sw_downloads_template = "https://swdownloads.analog.com/cse/boot_partition_files/{release}/latest_boot_partition.tar.gz"

    cache_datafile = "cache_info.json"

    def __attrs_post_init__(self):
        super().__attrs_post_init__()    
        self._boot_files = []

    def check_cached(self, release_version=None):
        """Check if the specified Kuiper release version is cached locally.
        Args:
            release_version (str): Version of the Kuiper release to check. If None, uses the version from kuiper_resource.

        Returns:
            bool: True if the release is cached, False otherwise.
        """
        cache_path = self.kuiper_resource.cache_path
        if not os.path.exists(cache_path):
            os.makedirs(cache_path)

        cache_file_path = os.path.join(cache_path, self.cache_datafile)
        if not os.path.exists(cache_file_path):
            return False

        if release_version is None:
            release_version = self.kuiper_resource.release_version

        # Read cache file and check version
        with open(cache_file_path, 'r') as f:
            cache_data = json.load(f)
        
        for release in cache_data:
            if release == release_version:
                # Verify that the tarball path exists
                image_path = cache_data[release]["image_path"]
                if os.path.exists(image_path):
                    return True
        return False


    def download_release(self, release_version=None, get_boot_files=False):
        """Download the specified Kuiper release version if not already cached.
        Args:
            release_version (str): Version of the Kuiper release to download. If None, uses the version from kuiper_resource.
        """
        if release_version is None:
            release_version = self.kuiper_resource.release_version

        if self.check_cached(release_version):
            self.logger.info(f"Kuiper release {release_version} is already cached.")
            return

        if get_boot_files:
            url = self.sw_downloads_template.format(release=release_version)
            self.logger.info(f"Downloading Kuiper boot_files {release_version} from {url}")

            cache_path = self.kuiper_resource.cache_path
            if not os.path.exists(cache_path):
                os.makedirs(cache_path)

            tarball_path = os.path.join(cache_path, f"{release_version}_boot_partition.tar.gz")
            raise NotImplementedError("Boot files download not implemented yet.")
        else:
            downloader = Downloader()
            rel_info = downloader.releases(release_version)
            url = rel_info["link"]
            self.logger.info(f"Downloading Kuiper release {release_version} from {url}")

            cache_path = self.kuiper_resource.cache_path
            if not os.path.exists(cache_path):
                os.makedirs(cache_path)

            if "xzname" in rel_info:
                tarball_path = os.path.join(cache_path, rel_info["xzname"])
            elif "zipname" in rel_info:
                tarball_path = os.path.join(cache_path, rel_info["zipname"])
            else:
                raise Exception("Unknown file name for release " + release_version)

            name_archive = rel_info["xzname"] if "xzname" in rel_info else rel_info["zipname"]
            md5_archive = rel_info["xzmd5"] if "xzmd5" in rel_info else rel_info["zipmd5"]
            downloader.download(rel_info["link"], name_archive)
            downloader.check(name_archive, md5_archive)
            downloader.extract(name_archive, rel_info["imgname"])
            img_file = downloader.check(rel_info["imgname"], rel_info["imgmd5"], find_img=True)

            # Move img file to cache path
            self.logger.info(f"Caching Kuiper release {release_version} files to {cache_path}")
            img_filename = os.path.basename(img_file)
            target_path = os.path.join(cache_path, img_filename)
            shutil.move(img_file, target_path)

            # Cleanup
            self.logger.info("Cleaning up temporary files")
            if os.path.exists(tarball_path):
                os.remove(tarball_path)
                # shutil.move(tarball_path, cache_path)
            if os.path.isfile(name_archive):
                os.remove(name_archive)
            if os.path.isdir(rel_info["imgname"]):
                os.rmdir(rel_info["imgname"])

        # Update cache info
        cache_file_path = os.path.join(cache_path, self.cache_datafile)
        cache_data = {}
        if os.path.exists(cache_file_path):
            with open(cache_file_path, 'r') as f:
                cache_data = json.load(f)
        
        cache_data[release_version] = {
            # "tarball_path": tarball_path,
            "image_path": target_path,
            "download_time": time.ctime(),
            "download_date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        }

        with open(cache_file_path, 'w') as f:
            json.dump(cache_data, f, indent=4)

        self.logger.info(f"Kuiper release {release_version} cached successfully.")


    def __del__(self):
        ...
        # try:
        #     self.unmount_partition()
        # except Exception:
        #     pass

    def get_boot_files_from_release(self):
        if not self.check_cached():
            self.download_release(get_boot_files=True)

        with open(os.path.join(self.kuiper_resource.cache_path, self.cache_datafile), 'r') as f:
            cache_data = json.load(f)
        release_info = cache_data[self.kuiper_resource.release_version]

        img = IMGFileExtractor(release_info["image_path"])
        for i, part in enumerate(img.get_partitions()):
            self.logger.info(f"  {i}: {part['description']} - Offset: {part['start']} bytes")


        # List files in FAT partition
        partitions_info = img.get_partitions()
        fat_partition = None
        for part in partitions_info:
            if 'FAT' in part['description']:
                fat_partition = part
                break
        if fat_partition is None:
            raise Exception("No FAT partition found in Kuiper image")

        fs = img.open_filesystem(fat_partition['start'])
        files = img.list_files(fs, "/")
        files_str = ""
        for f in files:
            files_str += f"{f['type']}: {f['path']} ({f['size']} bytes)\n"

        # Extract boot files
        output_dir = os.path.join(self.kuiper_resource.cache_path, "boot_files")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        self.logger.info(f"\nExtracting boot files to {output_dir}")
        files_to_extract = [
            "/README.txt",
            "/zynqmp-common/Image",
            "/zynqmp-zcu102-rev10-ad9081/m8_l4/m8_l4_vcxo122p88/system.dtb",
            "/zynqmp-zcu102-rev10-ad9081/m8_l4/BOOT.BIN",
        ]
        copy_files = []
        for file_path in files_to_extract:
            if not img.extract_file(fs, file_path, os.path.join(output_dir, os.path.basename(file_path))):
                img.close()
                raise Exception(f"Available files {files_str}\n\nFailed to extract {file_path}")
            copy_files.append(os.path.join(output_dir, os.path.basename(file_path)))

        self.logger.info("Boot files extracted successfully:")
        self._boot_files  = copy_files

        img.close()

    