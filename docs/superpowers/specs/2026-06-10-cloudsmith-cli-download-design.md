# Cloudsmith artifact download in the `adi-lg` CLI — Design

**Date:** 2026-06-10
**Status:** Approved

## Problem

The repo has a complete Cloudsmith download stack — the `CloudsmithRelease`
resource, the `CloudsmithDLDriver` (Cloudsmith API search/resolve, streaming
download with retry, sha256 verification, version-keyed cache), and a
standalone `cloudsmithdl` argparse console script. But the main `adi-lg`
Click CLI (`adi_lg_plugins/tools/cli.py`) has no download command; users who
live in `adi-lg` must switch to the separate `cloudsmithdl` tool.

## Decision

Add an `adi-lg download-cloudsmith` subcommand that reuses the existing
driver machinery via the helper in `adi_lg_plugins/tools/cloudsmithdl.py`.
The standalone `cloudsmithdl` console script stays as-is (no deprecation).

Parameters come from CLI flags only — no labgrid YAML config is required.
The command builds a `Target` programmatically, exactly as the standalone
script does today.

## Design

### 1. Helper refactor (`tools/cloudsmithdl.py`)

`download_cloudsmith_boot_file()` currently prints the downloaded path and
returns `None`. Change it to **return the path**; the standalone script's
`main()` takes over the printing. Standalone CLI behavior is unchanged.

### 2. New Click command (`tools/cli.py`)

`download_cloudsmith`, registered on the `cli` group as
`download-cloudsmith`, with options:

| Option | Required | Default | Notes |
|---|---|---|---|
| `--fpga-carrier` | yes | — | e.g. `zcu102` |
| `--daughter-card` | yes | — | e.g. `adrv9009` |
| `--filename` | no | `BOOT.BIN` | artifact filename |
| `--owner` | no | `adi` | Cloudsmith owner/org |
| `--repo` | no | `sdg-boot-partition` | Cloudsmith repository |
| `--version` | no | latest | pin an exact package version |
| `--cache-path` | no | `~/.labgrid/cloudsmith_releases/` | matches the resource default, not the standalone script's `/tmp/cloudsmith_cache` |
| `--out` | no | — | copy the cached artifact here after download |

`--out` semantics: `shutil.copy2` the cached file to `PATH`; if `PATH` is an
existing directory, copy into it keeping the artifact filename. Print both
the cache path and the copied path.

Auth: `CLOUDSMITH_API_TOKEN` environment variable (the `CloudsmithRelease`
resource default). The driver already raises a clear error when the token is
missing; the command surfaces it.

Errors: wrapped in `click.ClickException` with the red `console.print`
message, matching the other `adi-lg` commands.

### 3. Tests (`tests/test_cli.py`)

This file is already exercised by CI. Add `CliRunner` tests with the
driver's network layer mocked:

- success path prints the downloaded path
- `--out` to a file path and to an existing directory
- missing `CLOUDSMITH_API_TOKEN` fails with a clear error

### 4. Docs (`docs/source/user-guide/cli.rst`)

Add a `download-cloudsmith` section alongside the existing command docs.

## Out of scope

- Deprecating or aliasing the standalone `cloudsmithdl` script.
- Labgrid-YAML-driven configuration (`--config`) for this command.
- A list/dry-run mode (query without download).
- `pyproject.toml` changes — the command rides the existing `adi-lg` entry
  point.
