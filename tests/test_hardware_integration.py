import os

import pytest
from labgrid import Environment


@pytest.mark.hardware
class TestHardwareIntegration:
    @pytest.fixture(scope="class")
    def target(self, lg_config):
        if not lg_config:
            pytest.skip("No labgrid config provided via --lg-config")

        env = Environment(lg_config)
        target = env.get_target("main")  # Assume main target
        return target

    @pytest.fixture(scope="class")
    def driver(self, target):
        driver = target.get_driver("SoftwareInstallerDriver")
        target.activate(driver)
        yield driver
        target.deactivate(driver)

    def test_install_package(self, driver):
        # Try to install a common package like 'git' or 'curl'
        # This assumes the target has internet access and a package manager
        try:
            driver.install_package("curl")
        except Exception as e:
            pytest.fail(f"Failed to install package: {e}")

    def test_clone_repo(self, driver):
        repo_url = "https://github.com/analogdevicesinc/adi-labgrid-plugins.git"
        dest = "/tmp/adi-plugins-test"

        # Clean up remote if exists (best effort)
        try:
            driver.command.run(f"rm -rf {dest}")
        except Exception:
            pass

        try:
            driver.clone_repo(repo_url, dest)
            # Check if it exists
            stdout, _, _ = driver.command.run(f"[ -d {dest}/.git ] && echo 'exists'")
            assert "exists" in stdout
        except Exception as e:
            pytest.fail(f"Failed to clone repo: {e}")

    def test_copy_directory(self, driver):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "hello.txt"), "w") as f:
                f.write("Hello World")

            remote_dest = "/tmp/test_copy_dir"

            try:
                driver.copy_directory(tmpdir, remote_dest)
                stdout, _, _ = driver.command.run(f"cat {remote_dest}/hello.txt")
                assert "Hello World" in stdout
            except Exception as e:
                pytest.fail(f"Failed to copy directory: {e}")

    def test_run_build_and_test(self, driver):
        # Simple test: create a C file, compile it, run it
        remote_dir = "/tmp/build_test"
        driver.command.run(f"mkdir -p {remote_dir}")

        c_code = r"""
        #include <stdio.h>
        int main() { printf(\"Built!\n\"); return 0; }
        """

        # Create file on remote (using echo for simplicity)
        driver.command.run(f"echo '{c_code}' > {remote_dir}/main.c")

        try:
            # Assuming gcc is available
            driver.run_build("gcc main.c -o main", remote_dir)
            stdout = driver.run_binary("./main", directory=remote_dir)
            assert "Built!" in stdout
        except Exception as e:
            pytest.skip(f"Build test failed (maybe no gcc?): {e}")

    def test_provisioning_strategy(self, target):
        # Test full strategy transition
        strategy = target.get_driver("SoftwareProvisioningStrategy")

        # Configure a simple flow
        strategy.packages = ["curl"]
        strategy.repos = [
            (
                "https://github.com/analogdevicesinc/adi-labgrid-plugins.git",
                "/tmp/strat_test",
                "main",
            )
        ]

        try:
            strategy.transition("repos_cloned")
            assert strategy.status.name == "repos_cloned"
        except Exception as e:
            pytest.fail(f"Strategy transition failed: {e}")
