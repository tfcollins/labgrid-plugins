# `adi-lg download-cloudsmith` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `download-cloudsmith` subcommand to the `adi-lg` Click CLI that downloads a boot artifact from Cloudsmith using the existing driver stack, with an optional `--out` copy destination.

**Architecture:** Refactor the existing helper `download_cloudsmith_boot_file()` in `adi_lg_plugins/tools/cloudsmithdl.py` to return the downloaded path (instead of printing it), then add a thin Click command in `adi_lg_plugins/tools/cli.py` that calls it. All Cloudsmith API/resolution/download/cache logic stays in the already-tested `CloudsmithDLDriver`; no driver or resource changes.

**Tech Stack:** Python 3.10+, Click, rich, attrs/labgrid, pytest with `click.testing.CliRunner` and `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-06-10-cloudsmith-cli-download-design.md`

---

## File Structure

- Modify: `adi_lg_plugins/tools/cloudsmithdl.py` — helper returns the path; `main()` keeps printing (standalone `cloudsmithdl` behavior unchanged).
- Modify: `adi_lg_plugins/tools/cli.py` — new `download-cloudsmith` command (imports `shutil` and the helper).
- Modify: `tests/test_cloudsmith_dl.py` — one test for the helper's return value.
- Modify: `tests/test_cli.py` — CLI tests (success, `--out` file, `--out` dir, failure wrap).
- Modify: `docs/source/user-guide/cli.rst` — new `download-cloudsmith` command section.

No `pyproject.toml` changes (command rides the existing `adi-lg` entry point).

---

### Task 1: Helper returns the downloaded path

**Files:**
- Modify: `adi_lg_plugins/tools/cloudsmithdl.py`
- Test: `tests/test_cloudsmith_dl.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cloudsmith_dl.py`:

```python
# --- tools/cloudsmithdl helper ------------------------------------------------


def test_download_cloudsmith_boot_file_returns_path(monkeypatch):
    from adi_lg_plugins.tools import cloudsmithdl

    monkeypatch.setattr(
        CloudsmithDLDriver,
        "get_boot_file_path",
        lambda self, version=None: "/tmp/cache/v1/BOOT.BIN",
    )
    path = cloudsmithdl.download_cloudsmith_boot_file(
        fpga_carrier="zcu102",
        daughter_card="adrv9009",
        filename="BOOT.BIN",
        owner="adi",
        repo="sdg-boot-partition",
        version=None,
        cache_path="/tmp/cloudsmith_cache",
    )
    assert path == "/tmp/cache/v1/BOOT.BIN"
```

(`CloudsmithDLDriver` is already imported at the top of this test file. The real `Target`/`CloudsmithRelease`/driver wiring runs; only the network-touching method is stubbed.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cloudsmith_dl.py::test_download_cloudsmith_boot_file_returns_path -v`
Expected: FAIL with `assert None == '/tmp/cache/v1/BOOT.BIN'` (helper currently returns nothing).

- [ ] **Step 3: Make the helper return the path; print in `main()`**

In `adi_lg_plugins/tools/cloudsmithdl.py`, replace the tail of `download_cloudsmith_boot_file()`:

```python
    target.activate(dl)
    return dl.get_boot_file_path()
```

(delete the `path = ...` / `print(...)` lines), and in `main()` replace the final call with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cloudsmith_dl.py -v`
Expected: all PASS (existing tests plus the new one).

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/tools/cloudsmithdl.py tests/test_cloudsmith_dl.py
git commit -m "refactor(tools): cloudsmithdl helper returns downloaded path"
```

---

### Task 2: `download-cloudsmith` Click command

**Files:**
- Modify: `adi_lg_plugins/tools/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
@patch("adi_lg_plugins.tools.cli.download_cloudsmith_boot_file")
def test_download_cloudsmith_success(mock_dl, runner):
    mock_dl.return_value = "/cache/v1/BOOT.BIN"

    result = runner.invoke(
        cli,
        ["download-cloudsmith", "--fpga-carrier", "zcu102", "--daughter-card", "adrv9009"],
    )

    assert result.exit_code == 0
    assert "/cache/v1/BOOT.BIN" in result.output
    mock_dl.assert_called_once_with(
        fpga_carrier="zcu102",
        daughter_card="adrv9009",
        filename="BOOT.BIN",
        owner="adi",
        repo="sdg-boot-partition",
        version=None,
        cache_path="~/.labgrid/cloudsmith_releases/",
    )


@patch("adi_lg_plugins.tools.cli.download_cloudsmith_boot_file")
def test_download_cloudsmith_out_file(mock_dl, runner):
    with runner.isolated_filesystem():
        os.makedirs("cache")
        with open("cache/BOOT.BIN", "wb") as f:
            f.write(b"boot-bytes")
        mock_dl.return_value = os.path.abspath("cache/BOOT.BIN")

        result = runner.invoke(
            cli,
            [
                "download-cloudsmith",
                "--fpga-carrier", "zcu102",
                "--daughter-card", "adrv9009",
                "--out", "copy.bin",
            ],
        )

        assert result.exit_code == 0
        with open("copy.bin", "rb") as f:
            assert f.read() == b"boot-bytes"
        assert "copy.bin" in result.output


@patch("adi_lg_plugins.tools.cli.download_cloudsmith_boot_file")
def test_download_cloudsmith_out_directory(mock_dl, runner):
    with runner.isolated_filesystem():
        os.makedirs("cache")
        os.makedirs("dest")
        with open("cache/BOOT.BIN", "wb") as f:
            f.write(b"boot-bytes")
        mock_dl.return_value = os.path.abspath("cache/BOOT.BIN")

        result = runner.invoke(
            cli,
            [
                "download-cloudsmith",
                "--fpga-carrier", "zcu102",
                "--daughter-card", "adrv9009",
                "--out", "dest",
            ],
        )

        assert result.exit_code == 0
        with open(os.path.join("dest", "BOOT.BIN"), "rb") as f:
            assert f.read() == b"boot-bytes"


@patch("adi_lg_plugins.tools.cli.download_cloudsmith_boot_file")
def test_download_cloudsmith_failure(mock_dl, runner):
    mock_dl.side_effect = Exception("No Cloudsmith API token")

    result = runner.invoke(
        cli,
        ["download-cloudsmith", "--fpga-carrier", "zcu102", "--daughter-card", "adrv9009"],
    )

    assert result.exit_code != 0
    assert "No Cloudsmith API token" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v -k download_cloudsmith`
Expected: 4 FAIL/ERROR — `AttributeError: ... has no attribute 'download_cloudsmith_boot_file'` (patch target doesn't exist yet).

- [ ] **Step 3: Implement the command**

In `adi_lg_plugins/tools/cli.py`:

Add to the imports at the top (`shutil` goes in the stdlib group with `logging`/`os`; the helper import goes with the other `adi_lg_plugins` imports):

```python
import shutil
```

```python
from adi_lg_plugins.tools.cloudsmithdl import download_cloudsmith_boot_file
```

Add the command after `provision_software` (before `build_recovery_initramfs_cmd`):

```python
@cli.command(name="download-cloudsmith")
@click.option("--fpga-carrier", required=True, help="FPGA carrier, e.g. zcu102")
@click.option("--daughter-card", required=True, help="Daughter card, e.g. adrv9009")
@click.option("--filename", default="BOOT.BIN", show_default=True, help="Artifact filename")
@click.option("--owner", default="adi", show_default=True, help="Cloudsmith owner/org")
@click.option(
    "--repo", default="sdg-boot-partition", show_default=True, help="Cloudsmith repository"
)
@click.option("--version", default=None, help="Pin an exact package version (default: latest)")
@click.option(
    "--cache-path",
    default="~/.labgrid/cloudsmith_releases/",
    show_default=True,
    help="Cache directory for downloaded artifacts",
)
@click.option(
    "--out",
    type=click.Path(),
    default=None,
    help="Copy the artifact here after download (file path or existing directory)",
)
def download_cloudsmith(fpga_carrier, daughter_card, filename, owner, repo, version, cache_path, out):
    """Download a boot artifact from Cloudsmith.

    Resolves the latest (or pinned) package matching the FPGA carrier and
    daughter card in the Cloudsmith repo, downloads it into the local cache
    (sha256-verified), and prints the cached path. Requires the
    CLOUDSMITH_API_TOKEN environment variable.
    """
    try:
        path = download_cloudsmith_boot_file(
            fpga_carrier=fpga_carrier,
            daughter_card=daughter_card,
            filename=filename,
            owner=owner,
            repo=repo,
            version=version,
            cache_path=cache_path,
        )
    except Exception as e:
        console.print(f"[bold red]Download failed: {e}[/bold red]")
        raise click.ClickException(str(e)) from e

    console.print(f"[bold green]Downloaded:[/bold green] {path}")
    if out:
        dest = os.path.join(out, os.path.basename(path)) if os.path.isdir(out) else out
        shutil.copy2(path, dest)
        console.print(f"[bold green]Copied to:[/bold green] {dest}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: all PASS (existing tests plus the 4 new ones).

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/tools/cli.py tests/test_cli.py
git commit -m "feat(cli): add adi-lg download-cloudsmith subcommand"
```

---

### Task 3: Documentation

**Files:**
- Modify: `docs/source/user-guide/cli.rst`

- [ ] **Step 1: Add the command section**

In `docs/source/user-guide/cli.rst`, add a new subsection after the `provision-software` section (which ends just before the `Standalone download tools` heading):

```rst
download-cloudsmith
~~~~~~~~~~~~~~~~~~~

Download a boot artifact (e.g. ``BOOT.BIN``) from a Cloudsmith package
repository. Resolves the latest package matching the FPGA carrier and
daughter card (or an exact pinned version), downloads it into a local
cache with sha256 verification, and prints the cached path.

Requires the ``CLOUDSMITH_API_TOKEN`` environment variable.

.. code-block:: bash

   adi-lg download-cloudsmith --fpga-carrier zcu102 --daughter-card adrv9009

   # Pin an exact package version and copy the file next to your project
   adi-lg download-cloudsmith \
       --fpga-carrier zcu102 \
       --daughter-card adrv9009 \
       --version "boot_partition/main/2025_06_14-07_18_12/zynqmp-zcu102-rev10-adrv9009/" \
       --out ./BOOT.BIN

Options:

- ``--fpga-carrier`` (required): FPGA carrier, e.g. ``zcu102``.
- ``--daughter-card`` (required): Daughter card, e.g. ``adrv9009``.
- ``--filename``: Artifact filename (default ``BOOT.BIN``).
- ``--owner`` / ``--repo``: Cloudsmith owner and repository
  (default ``adi`` / ``sdg-boot-partition``).
- ``--version``: Pin an exact package version (default: latest).
- ``--cache-path``: Cache directory
  (default ``~/.labgrid/cloudsmith_releases/``).
- ``--out``: Copy the artifact here after download (file path or existing
  directory).

The standalone ``cloudsmithdl`` console script (below) exposes the same
download with a separate entry point.
```

- [ ] **Step 2: Build docs to verify**

Run: `nox -s docs`
Expected: build succeeds with no new warnings about `cli.rst`.

- [ ] **Step 3: Commit**

```bash
git add docs/source/user-guide/cli.rst
git commit -m "docs(cli): document adi-lg download-cloudsmith"
```

---

### Task 4: Lint and full verification

- [ ] **Step 1: Lint**

Run: `nox -s lint`
Expected: PASS. If ruff flags anything, fix with `ruff check . --fix && ruff format .` and re-run.

- [ ] **Step 2: Run the touched test files**

Run: `pytest tests/test_cli.py tests/test_cloudsmith_dl.py -v`
Expected: all PASS.

- [ ] **Step 3: Smoke the help text**

Run: `adi-lg download-cloudsmith --help`
Expected: exits 0 and shows the option list including `--out`.

- [ ] **Step 4: Commit any lint fixups**

```bash
git add -A
git commit -m "chore: lint fixups for download-cloudsmith" # only if Step 1 changed files
```
