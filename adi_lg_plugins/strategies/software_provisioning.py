import enum

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError


class Status(enum.Enum):
    """States for SoftwareProvisioningStrategy"""

    unknown = 0
    connected = 1
    software_installed = 2
    repos_cloned = 3
    built = 4
    tested = 5


@target_factory.reg_driver
@attr.s(eq=False)
class SoftwareProvisioningStrategy(Strategy):
    """
    Strategy to provision software on a target using SoftwareInstallerDriver.

    This strategy automates the process of installing packages, cloning repositories,
    building software, and running tests.

    Attributes:
        packages (list): List of package names to install.
        repos (list): List of repositories to clone. Each item can be a dictionary
                      {'url': ..., 'dest': ..., 'branch': ...} or a tuple (url, dest, [branch]).
        build_steps (list): List of build steps. Each item can be a dictionary
                            {'cmd': ..., 'dir': ...} or a tuple (cmd, dir).
        test_steps (list): List of test steps. Each item can be a dictionary
                           {'cmd': ..., 'dir': ...} or a tuple (cmd, dir).
    """

    bindings = {
        "installer": "SoftwareInstallerDriver",
    }

    status = attr.ib(default=Status.unknown)

    packages = attr.ib(default=attr.Factory(list))
    repos = attr.ib(default=attr.Factory(list))
    build_steps = attr.ib(default=attr.Factory(list))
    test_steps = attr.ib(default=attr.Factory(list))

    def __attrs_post_init__(self):
        super().__attrs_post_init__()

    @step()
    def transition(self, status, *, step):
        if not isinstance(status, Status):
            status = Status[status]

        if status == Status.unknown:
            raise StrategyError(f"can not transition to {status}")

        if status == self.status:
            step.skip("nothing to do")
            return

        if status == Status.connected:
            self.target.activate(self.installer)

        elif status == Status.software_installed:
            self.transition(Status.connected)
            for pkg in self.packages:
                self.installer.install_package(pkg)

        elif status == Status.repos_cloned:
            self.transition(Status.software_installed)
            for repo in self.repos:
                if isinstance(repo, dict):
                    self.installer.clone_repo(repo["url"], repo["dest"], repo.get("branch"))
                elif isinstance(repo, (list, tuple)):
                    self.installer.clone_repo(*repo)
                else:
                    raise ValueError(f"Invalid repo configuration: {repo}")

        elif status == Status.built:
            self.transition(Status.repos_cloned)
            for build in self.build_steps:
                if isinstance(build, dict):
                    self.installer.run_build(build["cmd"], build["dir"])
                elif isinstance(build, (list, tuple)):
                    self.installer.run_build(*build)
                else:
                    raise ValueError(f"Invalid build step configuration: {build}")

        elif status == Status.tested:
            self.transition(Status.built)
            for test in self.test_steps:
                if isinstance(test, dict):
                    self.installer.run_test(test["cmd"], test.get("dir"))
                elif isinstance(test, (list, tuple)):
                    self.installer.run_test(*test)
                else:
                    raise ValueError(f"Invalid test step configuration: {test}")

        self.status = status
