import os

import pytsk3


class IMGFileExtractor:
    """Extract files from disk image (.img) files using pytsk3.

    This utility class provides methods to inspect partitions, list files,
    and extract individual files or directories from disk image files without
    mounting them. It's primarily used by KuiperDLDriver to extract boot files
    from Kuiper Linux release images.

    Args:
        img_path (str): Path to the disk image file.
        logger (Logger, optional): Logger instance for debug output. If None,
            prints to stdout.

    Example:
        >>> extractor = IMGFileExtractor("kuiper.img")
        >>> partitions = extractor.get_partitions()
        >>> fs = extractor.open_filesystem(partitions[0]["start"])
        >>> extractor.extract_file(fs, "/Image", "./output/Image")
        >>> extractor.close()
    """

    def __init__(self, img_path, logger=None):
        self.img_path = img_path
        self.img_handle = pytsk3.Img_Info(img_path)
        self.logger = logger

    def log(self, message):
        if self.logger:
            self.logger.debug(message)
        else:
            print(message)

    def get_partitions(self):
        """List all partitions in the IMG file"""
        try:
            volume = pytsk3.Volume_Info(self.img_handle)
            partitions = []

            for partition in volume:
                if partition.len > 2048:  # Filter out small/empty partitions
                    partitions.append(
                        {
                            "tag": partition.tag,
                            "index": partition.addr,
                            "start": partition.start * 512,  # Convert sectors to bytes
                            "length": partition.len * 512,
                            "description": partition.desc.decode("utf-8")
                            if partition.desc
                            else "Unknown",
                        }
                    )

            return partitions
        except Exception as e:
            print(f"Error getting partitions: {e}")
            # If volume info fails, try to detect filesystem at offset 0
            return [{"index": 0, "start": 0, "length": 0, "description": "Single partition"}]

    def open_filesystem(self, partition_offset):
        """Open filesystem at a specific partition offset"""
        try:
            return pytsk3.FS_Info(self.img_handle, offset=partition_offset)
        except Exception as e:
            raise Exception(f"Could not open filesystem at offset {partition_offset}: {e}") from e

    def list_files(self, fs, path="/"):
        """Recursively list all files in a directory"""
        try:
            directory = fs.open_dir(path)
            files = []

            for entry in directory:
                name = entry.info.name.name.decode("utf-8")

                # Skip . and ..
                if name in [".", ".."]:
                    continue

                full_path = f"{path}/{name}".replace("//", "/")

                # Check if it's a directory
                if entry.info.meta and entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
                    files.append({"path": full_path, "type": "dir", "size": 0})
                    # Recursively list subdirectory
                    files.extend(self.list_files(fs, full_path))
                elif entry.info.meta:
                    files.append({"path": full_path, "type": "file", "size": entry.info.meta.size})

            return files
        except Exception as e:
            print(f"Error listing {path}: {e}")
            return []

    def extract_file(self, fs, file_path, output_path):
        """Extract a single file"""
        try:
            # Open the file in the filesystem
            file_entry = fs.open(file_path)

            # Read file data
            file_size = file_entry.info.meta.size
            data = file_entry.read_random(0, file_size)

            # Create output directory if needed
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Write to output file
            with open(output_path, "wb") as f:
                f.write(data)

            self.log(f"Extracted: {file_path} -> {output_path}")
            return True
        except Exception as e:
            self.log(f"Error extracting {file_path}: {e}")
            return False

    def extract_directory(self, fs, source_path, output_dir):
        """Extract an entire directory recursively"""
        files = self.list_files(fs, source_path)

        for file_info in files:
            if file_info["type"] == "file":
                # Create relative path for output
                rel_path = file_info["path"].lstrip("/")
                output_path = os.path.join(output_dir, rel_path)
                self.extract_file(fs, file_info["path"], output_path)

    def close(self):
        """Close the IMG file handle"""
        # pytsk3.Img_Info doesn't require explicit closing
        # The resources will be released when the object is garbage collected
        pass


# Example usage:
def main():
    extractor = IMGFileExtractor("disk.img")

    # 1. List all partitions
    print("Available partitions:")
    partitions = extractor.get_partitions()
    for i, part in enumerate(partitions):
        print(f"  {i}: {part['description']} - Offset: {part['start']} bytes")

    # 2. Choose a partition (e.g., partition 0)
    partition_index = 0
    partition_offset = partitions[partition_index]["start"]

    # 3. Open the filesystem
    fs = extractor.open_filesystem(partition_offset)

    # 4. List files in a specific directory
    print("\nFiles in root:")
    files = extractor.list_files(fs, "/")
    for f in files[:10]:  # Show first 10
        print(f"  {f['type']}: {f['path']} ({f['size']} bytes)")

    # 5. Extract specific file
    extractor.extract_file(fs, "/path/to/file.txt", "./output/file.txt")

    # 6. Or extract entire directory
    extractor.extract_directory(fs, "/etc", "./output/etc")

    extractor.close()


if __name__ == "__main__":
    main()
