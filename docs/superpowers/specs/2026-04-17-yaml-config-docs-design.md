# YAML Configuration Documentation — Design

**Date:** 2026-04-17
**Topic:** Complete Sphinx documentation for YAML configuration of every resource, driver, and strategy in `adi-labgrid-plugins`.

## Problem

The Sphinx user-guide at `docs/source/user-guide/{drivers,resources,strategies}.rst` documents only a subset of the package's registered components. Users cannot look up a single authoritative place to find the YAML schema for any given resource, driver, or strategy.

## Current Coverage Gaps

Registered components missing from `docs/source/user-guide/`:

**Drivers (3 missing):**
- `HomeAssistantPowerDriver` (`adi_lg_plugins/drivers/homeassistantdriver.py`)
- `SoftwareInstallerDriver` (`adi_lg_plugins/drivers/softwareinstaller.py`)
- `XilinxJTAGDriver` (`adi_lg_plugins/drivers/xilinxjtagdriver.py`)

**Resources (4 missing):**
- `TFTPServerResource` (`adi_lg_plugins/resources/tftpserver.py`)
- `HomeAssistantOutlet` (`adi_lg_plugins/resources/homeassistant.py`)
- `XilinxVivadoTool` (`adi_lg_plugins/resources/xilinxtool.py`)
- `XilinxDeviceJTAG` (`adi_lg_plugins/resources/xilinxdevice.py`)

**Strategies (2 missing):**
- `BootFPGASoCTFTP` (`adi_lg_plugins/strategies/bootfpgasoctftp.py`)
- `SoftwareProvisioningStrategy` (`adi_lg_plugins/strategies/software_provisioning.py`)

## Design

### Part 1 — Fill gaps in existing user-guide files

Add one section per missing component to the matching existing file.

| File | New sections | Style |
|------|--------------|-------|
| `user-guide/drivers.rst` | `HomeAssistantPowerDriver`, `SoftwareInstallerDriver`, `XilinxJTAGDriver` | Heavy (matches existing drivers) |
| `user-guide/resources.rst` | `TFTPServerResource`, `HomeAssistantOutlet`, `XilinxVivadoTool`, `XilinxDeviceJTAG` | Lighter |
| `user-guide/strategies.rst` | `BootFPGASoCTFTP`, `SoftwareProvisioningStrategy` | Heavy (matches existing strategies) |

**Heavy style** (drivers, strategies) — match existing sections like `VesyncPowerDriver`:

- Purpose
- Required Resource / Bindings
- Configuration (YAML block)
- Key Parameters (with types, defaults, required/optional)
- Methods (Python API)
- Usage Example
- Troubleshooting (when applicable)
- For strategies: mermaid `stateDiagram-v2` of the state machine

**Lighter style** (resources) — resources are configuration bags and the driver-side doc carries the runtime detail:

- Purpose (one line)
- Use With (pairs with which driver)
- Required Parameters (list with types)
- Optional Parameters (list with types, defaults)
- YAML Example
- Notes (only when a non-obvious constraint exists)

All parameter lists, defaults, and bindings sourced by reading each component's `@attr.ib()` declarations and class docstring directly — not inferred.

### Part 2 — New top-level `yaml-reference/` section

Quick-lookup reference. Lives as a sibling of `user-guide/`, `api/`, etc.

```
docs/source/yaml-reference/
├── index.rst              # landing page + toctree
├── resources.rst          # table + minimal YAML per resource
├── drivers.rst            # table + minimal YAML per driver
└── strategies.rst         # table + minimal YAML per strategy
```

Each of `resources.rst` / `drivers.rst` / `strategies.rst` has the same shape:

1. **Schema table** at top:

   | Name | Required | Optional | Pairs with |
   |------|----------|----------|------------|

2. **Minimal YAML blocks** below the table — bare-minimum copy-paste config per component, grouped by purpose (e.g., "Power Control", "Storage", "Boot"). Grouping follows the ordering already used in the user-guide files.

3. **Cross-links** — the component name in both the table and the block heading links to the deep entry in the corresponding `user-guide/<kind>.rst` via `:ref:` targets (explicit labels added where missing).

`index.rst` — short landing page with:
- One-sentence explanation of the page purpose (copy-paste YAML schema lookup).
- Three grid cards or a toctree linking to `resources`, `drivers`, `strategies`.

### Part 3 — Root index wiring

1. Add `yaml-reference/index` to the hidden toctree in `docs/source/index.rst`.
2. Add a new `grid-item-card` to the landing grid titled "YAML Reference" with subtext along the lines of *Quick schema lookup for every resource, driver, and strategy*.

## Source of Truth

Every documented parameter, default value, binding, and state machine transition comes from reading the source. No guessing.

- Resources: `@attr.ib()` fields in `adi_lg_plugins/resources/*.py`
- Drivers: `bindings` dict + `@attr.ib()` in `adi_lg_plugins/drivers/*.py`
- Strategies: `bindings` dict + `transition()` state enum in `adi_lg_plugins/strategies/*.py`

For each component, read the module once, extract the schema, then write the section. If a parameter's semantics are not obvious from name/type alone, use the class docstring or inline comments — do not invent prose.

## Cross-Referencing Strategy

- User-guide sections get explicit `.. _<component-name>:` labels where they don't already.
- YAML-reference entries link back via `:ref:` so a reader who lands on the reference page can drill into the full guide entry in one click.

## Out of Scope

- Autogeneration of YAML schemas from the attrs classes (could be future work; this spec is pure prose).
- Changes to `docs/source/api/` autodoc pages.
- Edits to existing user-guide sections for components that are already documented (only *new* gap sections are added).
- Documenting the internal helper classes (`Downloader`, `SimpleTFTPServer`, `IMGFileExtractor`, etc.) that are not registered via `@target_factory.reg_*`.

## Acceptance Criteria

1. Every `@target_factory.reg_driver`, `@target_factory.reg_resource`, and registered strategy in `adi_lg_plugins/` has a section in the matching `user-guide/*.rst` file.
2. `docs/source/yaml-reference/{index,resources,drivers,strategies}.rst` exists and is reachable from the root landing page.
3. Every entry in the yaml-reference schema tables cross-links to its deep user-guide section.
4. `nox -s docs` builds without warnings introduced by the new files.
