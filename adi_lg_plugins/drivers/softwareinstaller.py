import os
import tarfile
import tempfile

import attr
from labgrid.driver.common import Driver
from labgrid.factory import target_factory
from labgrid.protocol import CommandProtocol, FileTransferProtocol
from labgrid.step import step


@target_factory.reg_driver
@attr.s(eq=False)
class SoftwareInstallerDriver(Driver):
    """
    SoftwareInstallerDriver - Driver to install software, clone repos, copy directories,
    and run builds/tests on a DUT.
    """

    bindings = {
        "command": CommandProtocol,
        "file_transfer": FileTransferProtocol,
    }

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self._package_manager = None

    def _detect_package_manager(self):
        if self._package_manager:
            return self._package_manager

        managers = {
            "apt-get": "apt-get install -y",
            "dnf": "dnf install -y",
            "opkg": "opkg install",
            "pacman": "pacman -S --noconfirm",
            "apk": "apk add",
        }

        for mgr, install_cmd in managers.items():
            stdout, _, exit_code = self.command.run(f"which {mgr}")
            if exit_code == 0:
                self._package_manager = (mgr, install_cmd)
                return self._package_manager

        raise Exception(
            "No supported package manager found on target (checked apt-get, dnf, opkg, pacman, apk)"
        )

    @step(args=["package_name"])
    def install_package(self, package_name, update=False):
        """
        Installs a package using the detected package manager.

        Args:
            package_name (str): Name of the package to install.
            update (bool): Whether to update package lists before installing.
        """
        mgr, install_cmd = self._detect_package_manager()

        if update:
            update_cmds = {
                "apt-get": "apt-get update",
                "dnf": "dnf check-update",
                "opkg": "opkg update",
                "pacman": "pacman -Sy",
                "apk": "apk update",
            }
            if mgr in update_cmds:
                self.command.run(update_cmds[mgr])

        cmd = f"{install_cmd} {package_name}"
        stdout, stderr, exit_code = self.command.run(cmd)
        if exit_code != 0:
            raise Exception(
                f"Failed to install package '{package_name}'. Exit code: {exit_code}. Stderr: {stderr}"
            )
        return stdout

    @step(args=["repo_url", "destination"])
    def clone_repo(self, repo_url, destination, branch=None):
        """
        Clones a git repository to the destination.

        Args:
            repo_url (str): URL of the git repository.
            destination (str): Remote path to clone into.
            branch (str): Optional branch or tag to checkout.
        """
        # Ensure git is installed
        stdout, _, exit_code = self.command.run("which git")
        if exit_code != 0:
            self.install_package("git")

        cmd = f"git clone {repo_url} {destination}"
        if branch:
            cmd += f" --branch {branch}"

        stdout, stderr, exit_code = self.command.run(cmd)
        if exit_code != 0:
            raise Exception(
                f"Failed to clone repo '{repo_url}'. Exit code: {exit_code}. Stderr: {stderr}"
            )
        return stdout

    @step(args=["local_path", "remote_path"])
    def copy_directory(self, local_path, remote_path):
        """
        Copies a local directory to the remote path.

        Args:
            local_path (str): Local directory path.
            remote_path (str): Remote directory path (parent directory must exist or be created).
        """
        if not os.path.isdir(local_path):
            raise ValueError(f"Local path '{local_path}' is not a directory.")

        # Create a temporary tarball of the local directory
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp_tar:
            tar_path = tmp_tar.name

        try:
            with tarfile.open(tar_path, "w:gz") as tar:
                tar.add(local_path, arcname=os.path.basename(local_path))

            # Transfer the tarball
            remote_tar_path = f"/tmp/{os.path.basename(tar_path)}"
            self.file_transfer.put(tar_path, remote_tar_path)

            # Ensure remote directory exists
            self.command.run(f"mkdir -p {remote_path}")

            # Extract on remote
            # tar -xzf archive.tar.gz -C /path/to/destination
            # Note: arcname included the directory name, so extracting it into remote_path
            # might create remote_path/dirname.
            # If user expects contents of local_path to be IN remote_path, we might need to adjust.
            # Let's assume standard cp -r behavior: cp -r dir dest -> dest/dir

            cmd = f"tar -xzf {remote_tar_path} -C {remote_path}"
            stdout, stderr, exit_code = self.command.run(cmd)

            # Cleanup remote tar
            self.command.run(f"rm {remote_tar_path}")

            if exit_code != 0:
                raise Exception(
                    f"Failed to extract directory. Exit code: {exit_code}. Stderr: {stderr}"
                )

        finally:
            if os.path.exists(tar_path):
                os.remove(tar_path)

    @step(args=["command", "directory"])
    def run_build(self, command, directory):
        """
        Runs a build command in a specific directory.

        Args:
            command (str): Build command (e.g., 'make', 'cargo build').
            directory (str): Directory to run the build in.
        """
        full_cmd = f"cd {directory} && {command}"
        stdout, stderr, exit_code = self.command.run(
            full_cmd, timeout=3600
        )  # Long timeout for builds
        if exit_code != 0:
            raise Exception(f"Build failed. Exit code: {exit_code}. Stderr: {stderr}")
        return stdout

    @step(args=["binary_path"])
    def run_binary(self, binary_path, args="", directory=None):
        """
        Runs a binary on the target.

        Args:
            binary_path (str): Path to the binary.
            args (str): Arguments for the binary.
            directory (str): Working directory.
        """
        cmd = f"{binary_path} {args}"
        if directory:
            cmd = f"cd {directory} && {cmd}"

        stdout, stderr, exit_code = self.command.run(cmd)
        if exit_code != 0:
            raise Exception(f"Binary execution failed. Exit code: {exit_code}. Stderr: {stderr}")
        return stdout

    @step(args=["test_command"])
    def run_test(self, test_command, directory=None):
        """
        Runs a test command.

        Args:
            test_command (str): Command to run tests.
            directory (str): Working directory.
        """
        cmd = test_command
        if directory:
            cmd = f"cd {directory} && {cmd}"

        stdout, stderr, exit_code = self.command.run(cmd)
        if exit_code != 0:
            raise Exception(f"Test failed. Exit code: {exit_code}. Stderr: {stderr}")
        return stdout
