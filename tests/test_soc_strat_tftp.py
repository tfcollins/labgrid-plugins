import pytest


@pytest.fixture(scope="module")
def in_shell(strategy):
    """
    Transitions the strategy to 'booted', delivering us to a shell prompt.
    The strategy will run U-Boot commands to TFTP load kernel/dtb and boot.
    """
    strategy.transition("booted")
    yield
    strategy.transition("soft_off")


def test_shell(target, in_shell):
    """
    Verifies that we have a working shell by running a simple command.
    """
    shell = target.get_driver("ADIShellDriver")

    # Run a simple command to verify shell responsiveness
    output = shell.run("uname -a")
    print(f"DEBUG: uname output: {output}")

    # output is (stdout_lines, stderr_lines, exitcode)
    stdout_lines = output[0]
    assert any("Linux" in line for line in stdout_lines), (
        f"Did not see 'Linux' in uname output: {stdout_lines}"
    )
