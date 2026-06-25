# Web UI: Editable Place Tags + Manual Recovery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let operators (1) edit a place's tags/labels from the coordinator dashboard, and (2) trigger a manual board recovery from the dashboard.

**Architecture:** Feature 1 is **frontend-only** — the backend `PUT /places/{name}/tags` and web `api.setPlaceTags` already exist; we add a Tags display + edit modal to `PlaceDetail.tsx`. Feature 2 is **net-new end-to-end** — a new `adi-lg recover` CLI verb runs the `BootZynq7000JTAGRecovery` strategy; a new `recovery.py` API router mirrors `power.py` (ownership + `allow_place` + generated boot-tier env-yaml + a long `adi-lg recover` subprocess); the web adds `api.recoverPlace` + a destructive-confirm Recover button.

**Tech Stack:** FastAPI + pytest (coordinator/api), React/Vite/TS + Chakra UI v2 + react-query + vitest (coordinator/web), Click + labgrid (adi_lg_plugins CLI).

## Design grounding

Tags live on **places**, not resources — `ResourceModel` has no tags field and labgrid's only tag RPC is `SetPlaceTags` (place-level). So "editable resource tags" is implemented as **place-tag editing** (the only tag-bearing entity). Recovery = the `BootZynq7000JTAGRecovery` labgrid Strategy (`adi_lg_plugins/strategies/bootzynq7000recovery.py`); `labgrid-client` has no strategy-transition subcommand, so recovery needs a new `adi-lg recover` verb invoked as a subprocess (parallels `adi-lg boot-soc` + `routers/power.py`).

## Global Constraints (autonomously-resolved decisions — binding)

- **Branch:** `webui-tags-recovery` (already created off `main`). Do NOT create another branch.
- **Tag scope:** edit **place** tags only, on `PlaceDetail.tsx`. (No resource-tag model exists.)
- **Tag-edit auth:** leave the backend `PUT /places/{name}/tags` unchanged (gates on `current_user`); the UI gates the edit affordance on `canEdit` (admin OR owner OR unacquired — same gate the matches editor uses).
- **Required tags:** `REQUIRED_TAG_KEYS = ["board-location", "carrier", "daughter-board"]` (from `PlaceWizard.tsx`). In the editor, render these as non-deletable rows; **warn-only** (do NOT block save) if their values are empty, to tolerate pre-existing places.
- **Tag-save cache invalidation:** invalidate BOTH `["place", name]` (PlaceDetail's key) and `["places"]` (list).
- **Recovery mechanism:** a new `adi-lg recover` CLI verb invoked via `asyncio.create_subprocess_exec` (NOT in-process labgrid in the API).
- **Recovery execution model (MVP):** a single **blocking** request, timeout `RECOVER_TIMEOUT = 1800`s (matches the strategy's `wait_for_sd_flash_timeout`). A tracked background job + status polling is the right v2 but is explicitly **deferred**.
- **Recovery target state:** default `sd_flash_done`; accept `state` ∈ {`sd_flash_done`, `sd_boot_verified`} (400 otherwise).
- **Recovery eligibility:** 422 early if `resolve_strategy(place.tags, {r.cls})` != `"BootZynq7000JTAGRecovery"`.
- **Recovery auth:** owner-or-admin in the backend (exactly `power.py:67-71`); `isOwner` gate in the UI.
- **Confirm dialog:** the codebase has NO `AlertDialog`; use a Chakra `Modal` + `useDisclosure` (the established confirm pattern) for the destructive Recover confirm.
- **Env / commands:** coordinator/web — run from `coordinator/web`: `npm run test` (vitest), `npx tsc --noEmit`, `npm run build`. coordinator/api — run from `coordinator/api`: `python -m pytest tests/ -q` (CI runs ALL of `coordinator/api/tests/`, so new test files are auto-covered). adi_lg_plugins CLI — from repo root: `.venv/bin/python -m pytest tests/test_cli.py -q` and `.venv/bin/ruff check . && .venv/bin/ruff format --check .` (the top-level CI lint gate runs `ruff check .` AND `ruff format --check .`; run `ruff format` before committing).
- **Gates per task:** the touched test suite green; for Python changes, `ruff check` + `ruff format --check` clean; for web changes, vitest + `tsc --noEmit` clean.

## File structure

| File | Feature | Change |
|---|---|---|
| `coordinator/web/src/pages/PlaceDetail.tsx` | 1 & 2 | Tags section + edit modal + `setTagsM`; Recover button + confirm modal + `recoverM` |
| `coordinator/web/src/pages/__tests__/PlaceDetail.test.tsx` | 1 & 2 | tags display/edit/save; recover confirm/call |
| `coordinator/web/src/api/client.ts` | 2 | add `api.recoverPlace` |
| `adi_lg_plugins/tools/cli.py` | 2 | new `recover` Click command |
| `tests/test_cli.py` | 2 | `adi-lg recover` coverage |
| `coordinator/api/app/routers/recovery.py` | 2 | NEW router |
| `coordinator/api/app/main.py` | 2 | register the router |
| `coordinator/api/tests/test_recovery_router.py` | 2 | NEW tests |

---

### Task 1: Editable place tags on PlaceDetail (frontend-only)

**Files:** Modify `coordinator/web/src/pages/PlaceDetail.tsx`; Modify `coordinator/web/src/pages/__tests__/PlaceDetail.test.tsx`.

**Interfaces:** Consumes the existing `api.setPlaceTags(name, tags: Record<string,string>)` (`client.ts:145-149` → `PUT /places/{name}/tags`). Produces: a Tags display section + an Edit-tags modal on PlaceDetail.

Read `PlaceDetail.tsx` first to match its imports/structure. The patterns to clone are all in-file or in `PlaceWizard.tsx`; cited by line below.

- [ ] **Step 1: Write the failing tests.** In `PlaceDetail.test.tsx`, make the `api` mock's `getPlace` return non-empty `tags` (e.g. `tags: { "board-location": "rackA", carrier: "zcu102" }`) and ensure `setPlaceTags: vi.fn().mockResolvedValue({})` is in the `vi.mock("../../api/client", ...)` block. Add:

```tsx
it("renders place tags as chips", async () => {
  render(wrap(<PlaceDetail />));
  expect(await screen.findByText("board-location=rackA")).toBeInTheDocument();
  expect(screen.getByText("carrier=zcu102")).toBeInTheDocument();
});

it("edits and saves tags", async () => {
  const { api } = await import("../../api/client");
  render(wrap(<PlaceDetail />));
  fireEvent.click(await screen.findByRole("button", { name: /edit tags/i }));
  // add a new custom tag row
  fireEvent.click(await screen.findByRole("button", { name: /add tag/i }));
  const keyInputs = screen.getAllByLabelText(/tag \d+ key/i);
  const valInputs = screen.getAllByLabelText(/tag \d+ value/i);
  fireEvent.change(keyInputs[keyInputs.length - 1], { target: { value: "owner" } });
  fireEvent.change(valInputs[valInputs.length - 1], { target: { value: "alice" } });
  fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
  await waitFor(() =>
    expect(api.setPlaceTags).toHaveBeenCalledWith(
      "vcu118-lab1",
      expect.objectContaining({ "board-location": "rackA", carrier: "zcu102", owner: "alice" }),
    ),
  );
});
```

(Use the place name the existing test mock/route uses — match the file. `useAuth` must return the owner user so `canEdit` is true; mirror the existing auth mock.)

- [ ] **Step 2: Run them to verify they fail** — `cd coordinator/web && npm run test -- PlaceDetail` → FAIL (no "Edit tags" button / chips).

- [ ] **Step 3: Add the Tags section + edit modal to `PlaceDetail.tsx`.** Pattern (clone exact components/idioms cited):
  - Add `REQUIRED_TAG_KEYS = ["board-location", "carrier", "daughter-board"]` as a module const (mirror `PlaceWizard.tsx:41`).
  - Add a second `useDisclosure()` for the tags modal (the file already uses `useDisclosure` for the match modal ~`:87,269-318`).
  - **Display section** between the comment (`~:181`) and "Resource matches" (`~:183`): an `HStack` heading "Tags" + (when `canEdit`) a `Button size="xs" leftIcon={<MdEdit/>}` ("Edit tags") opening the modal; below it render `Object.entries(place.tags)` as Chakra `<Tag><TagLabel>{k}={v}</TagLabel></Tag>` chips (idiom `Places.tsx:103,109`; `Tag`/`TagLabel` are imported in `PlaceWizard`), `<Text color="gray.500">No tags</Text>` when empty.
  - **Edit modal** (clone the match `Modal` at `~:269-318`): local `useState` rows `{key, value}[]` seeded from `place.tags` via `useEffect` on modal open. Render rows as `HStack` of two `Input`s with `aria-label={`Tag ${i} key`}` / `aria-label={`Tag ${i} value`}` + an `MdDelete` `IconButton` per row (clone `PlaceWizard.tsx:353-377`). Rows whose key ∈ `REQUIRED_TAG_KEYS` render the key `Input` `isReadOnly` and omit the delete button. An "Add tag" `Button leftIcon={<MdAdd/>}` appends an empty row. Footer: Cancel + `Button isLoading={setTagsM.isPending}` "Save" → builds `tagsObj = Object.fromEntries(rows.filter(r => r.key.trim()).map(r => [r.key.trim(), r.value]))` and calls `setTagsM.mutate(tagsObj)`.
  - **Mutation** (clone `addMatchM` `~:73-81`): `const setTagsM = useMutation({ mutationFn: (tags: Record<string,string>) => api.setPlaceTags(name, tags), onSuccess: () => { qc.invalidateQueries({ queryKey: ["place", name] }); qc.invalidateQueries({ queryKey: ["places"] }); toast({ status: "success", title: "Tags updated" }); tagsModal.onClose(); }, onError: (e) => toast({ status: "error", title: "Update failed", description: e instanceof Error ? e.message : String(e) }) });`
  - Add any missing icon imports (`MdEdit`, `MdAdd`, `MdDelete` from `react-icons/md`) and `Tag, TagLabel` from `@chakra-ui/react`.

- [ ] **Step 4: Run the tests + typecheck** — `cd coordinator/web && npm run test -- PlaceDetail && npx tsc --noEmit` → PASS + clean.

- [ ] **Step 5: Commit** — `git add coordinator/web/src/pages/PlaceDetail.tsx coordinator/web/src/pages/__tests__/PlaceDetail.test.tsx && git commit -m "feat(web): edit place tags from PlaceDetail"`

---

### Task 2: `adi-lg recover` CLI command

**Files:** Modify `adi_lg_plugins/tools/cli.py`; Modify `tests/test_cli.py`.

**Interfaces:** Produces the Click command `adi-lg recover --config <yaml> [--release R] [--sd-image PATH] [--target main] [--state sd_flash_done]` that runs `BootZynq7000JTAGRecovery.transition(state)`. Consumed by the recovery router (Task 3) as a subprocess.

- [ ] **Step 1: Write the failing test.** In `tests/test_cli.py` (follow the file's existing CLI-test style — `CliRunner`, and how it monkeypatches `labgrid.Environment` / `adi_lg_plugins.tools.cli.Environment` for the boot commands):

```python
def test_recover_help():
    from click.testing import CliRunner

    from adi_lg_plugins.tools.cli import cli

    result = CliRunner().invoke(cli, ["recover", "--help"])
    assert result.exit_code == 0
    assert "sd_flash_done" in result.output


def test_recover_runs_strategy_transition(tmp_path, monkeypatch):
    from click.testing import CliRunner

    import adi_lg_plugins.tools.cli as cli_mod

    cfg = tmp_path / "env.yaml"
    cfg.write_text("targets: {}\n")
    calls = {}

    class FakeStrategy:
        def transition(self, state):
            calls["state"] = state

    class FakeTarget:
        def get_resource(self, _cls):
            raise Exception("no KuiperRelease")

        def get_driver(self, name):
            calls["driver"] = name
            return FakeStrategy()

    class FakeEnv:
        def __init__(self, _cfg):
            pass

        def get_target(self, _t):
            return FakeTarget()

    monkeypatch.setattr(cli_mod, "Environment", FakeEnv)
    result = CliRunner().invoke(cli_mod.cli, ["recover", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert calls == {"driver": "BootZynq7000JTAGRecovery", "state": "sd_flash_done"}
```

- [ ] **Step 2: Run it to verify it fails** — `.venv/bin/python -m pytest tests/test_cli.py -k recover -q` → FAIL (no `recover` command).

- [ ] **Step 3: Add the `recover` command** to `adi_lg_plugins/tools/cli.py` (after `boot_soc_ssh`, modeled verbatim on `boot_soc` at lines 78-126):

```python
@cli.command()
@click.option(
    "--config", "-c", required=True, type=click.Path(exists=True), help="Labgrid configuration file"
)
@click.option("--release", help="Kuiper release version (e.g., 2023_R2_P1)")
@click.option(
    "--sd-image",
    type=click.Path(exists=True),
    help="Path to an SD card image to flash (overrides the strategy default)",
)
@click.option("--target", "-t", default="main", help="Target name in config (default: main)")
@click.option(
    "--state", default="sd_flash_done", help="Target state to transition to (default: sd_flash_done)"
)
def recover(config, release, sd_image, target, state):
    """Recover a Zynq-7000 board via JTAG (BootZynq7000JTAGRecovery).

    Bootstraps U-Boot over JTAG, TFTP-boots a RAM-rooted recovery Linux, then
    reflashes the SD card. DESTRUCTIVE: wipes /dev/mmcblk0.
    """
    env = Environment(config)
    tg = env.get_target(target)

    try:
        resource = tg.get_resource("KuiperRelease")
        if release:
            resource.release_version = release
            logging.info(f"Overriding release version: {resource.release_version}")
    except Exception as e:
        logging.warning(f"Could not find KuiperRelease resource: {e}")

    strategy = tg.get_driver("BootZynq7000JTAGRecovery")
    if sd_image:
        strategy.sd_image_path = os.path.abspath(sd_image)
        logging.info(f"Overriding SD image path: {strategy.sd_image_path}")

    with console.status(
        f"[bold green]Recovering {target} to {state} using BootZynq7000JTAGRecovery..."
    ):
        try:
            strategy.transition(state)
            console.print(f"[bold green]Successfully reached {state}![/bold green]")
        except Exception as e:
            console.print(f"[bold red]Recovery failed: {e}[/bold red]")
            raise click.ClickException(str(e)) from e
```

- [ ] **Step 4: Run tests + lint** — `.venv/bin/ruff format adi_lg_plugins/tools/cli.py tests/test_cli.py && .venv/bin/python -m pytest tests/test_cli.py -k recover -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .` → PASS + clean.

- [ ] **Step 5: Commit** — `git add adi_lg_plugins/tools/cli.py tests/test_cli.py && git commit -m "feat(cli): adi-lg recover runs BootZynq7000JTAGRecovery"`

---

### Task 3: `POST /places/{name}/recover` API router

**Files:** Create `coordinator/api/app/routers/recovery.py`; Modify `coordinator/api/app/main.py`; Create `coordinator/api/tests/test_recovery_router.py`.

**Interfaces:** Consumes `env_gen.resolve_strategy` + `generate_env_yaml`, `places._matched_resources`, the `adi-lg recover` CLI (Task 2). Produces `POST /api/places/{name}/recover?state=sd_flash_done` → `RecoverResult{place,state,stdout,ok}`.

- [ ] **Step 1: Write the failing tests** — `coordinator/api/tests/test_recovery_router.py`, mirroring `tests/test_power_router.py` (same fixtures/auth helpers). The router calls `resolve_strategy`, `generate_env_yaml`, and shells `adi-lg`; isolate by monkeypatching the first two on the `recovery` module and putting a fake `adi-lg` on `PATH`:

```python
import os
import stat

import pytest

import app.routers.recovery as recovery


@pytest.fixture(autouse=True)
def _stub_strategy_and_env(monkeypatch, tmp_path):
    monkeypatch.setattr(recovery, "resolve_strategy", lambda tags, classes: recovery.RECOVERY_STRATEGY)
    monkeypatch.setattr(recovery, "generate_env_yaml", lambda place, resources, tier: "targets: {}\n")
    fake = tmp_path / "adi-lg"
    fake.write_text("#!/bin/sh\necho recovered \"$@\"\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
```

Then tests — mirror `test_power_router.py`'s fixtures EXACTLY: the `authed_lifespan_client` fixture, `c = authed_lifespan_client; c.login("alice")`, and acquire via the place_acq_store directly (NOT a POST), e.g.:
```python
import asyncio
alice = asyncio.new_event_loop().run_until_complete(c.app.state.auth_store.get_user_by_username("alice"))
asyncio.get_event_loop().run_until_complete(c.app.state.place_acq_store.acquire("vcu118-lab1", alice.id))
```
(copy the precise `loop.run_until_complete(...)` + user-lookup lines from `test_power_router.py:53-60,77` — don't reinvent them). The seeded place is `vcu118-lab1`. The `_stub_strategy_and_env` autouse fixture above already puts a fake `adi-lg` on PATH (same mechanism as `fake_labgrid_client`). Tests:
- `test_recover_requires_auth`: unauth `POST /api/places/vcu118-lab1/recover` → 401.
- `test_recover_not_acquired`: authed but place not acquired → 409.
- `test_recover_non_owner_forbidden`: alice acquires, bob (non-admin) recovers → 403.
- `test_recover_owner_ok`: alice acquires + recovers → 200, body `ok is True`, `state == "sd_flash_done"`.
- `test_recover_admin_ok`: alice acquires, admin recovers → 200.
- `test_recover_invalid_state`: owner with `?state=shell` → 400.
- `test_recover_wrong_strategy_422`: override `resolve_strategy` to return `None` (use `monkeypatch` inside the test), owner → 422.

(Mirror `test_power_router.py` exactly for the client/login/acquire fixtures and the `MockCoordinatorClient` — `allow_place` is already a no-op there; `get_place`/`get_resources` seed `vcu118-lab1`.)

- [ ] **Step 2: Run them to verify they fail** — `cd coordinator/api && python -m pytest tests/test_recovery_router.py -q` → FAIL (no router / 404).

- [ ] **Step 3: Create `coordinator/api/app/routers/recovery.py`:**

```python
"""Manual board recovery via the BootZynq7000JTAGRecovery strategy.

Mirrors routers/power.py: ownership-gated, authorizes our labgrid-client
subprocess identity via allow_place, then shells out — here to `adi-lg
recover`, which runs the recovery strategy's transition() against a boot-tier
env yaml we generate for the place. Recovery is DESTRUCTIVE (it reflashes the
SD card) and long-running, so the request blocks for up to RECOVER_TIMEOUT.
"""

from __future__ import annotations

import asyncio
import getpass
import logging
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth.dependencies import current_user
from ..auth.store import User
from ..config import settings
from ..env_gen import generate_env_yaml, resolve_strategy
from ..places.store import PlaceAcquisitionStore
from .places import _matched_resources

logger = logging.getLogger(__name__)
router = APIRouter(tags=["recover"])

RECOVERY_STRATEGY = "BootZynq7000JTAGRecovery"
RECOVER_TIMEOUT = 1800  # seconds; the SD reflash can take many minutes
_VALID_STATES = {"sd_flash_done", "sd_boot_verified"}


class RecoverResult(BaseModel):
    place: str
    state: str
    stdout: str
    ok: bool = True


def _place_store(request: Request) -> PlaceAcquisitionStore:
    return request.app.state.place_acq_store


@router.post("/places/{name}/recover", response_model=RecoverResult)
async def recover_place(
    name: str,
    request: Request,
    user: User = Depends(current_user),
    state: str = "sd_flash_done",
):
    if state not in _VALID_STATES:
        raise HTTPException(status_code=400, detail=f"invalid state: {state}")

    acq = await _place_store(request).get(name)
    if acq is None:
        raise HTTPException(status_code=409, detail="place not acquired")
    if acq.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="not the owner")

    client = request.app.state.coordinator
    place = client.get_place(name)
    if place is None:
        raise HTTPException(status_code=404, detail=f"Place '{name}' not found")

    resources = _matched_resources(client, place)
    if resolve_strategy(place.tags, {r.cls for r in resources}) != RECOVERY_STRATEGY:
        raise HTTPException(
            status_code=422, detail=f"place '{name}' does not resolve to {RECOVERY_STRATEGY}"
        )
    try:
        env_yaml = generate_env_yaml(place, resources, tier="boot")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # Authorize the labgrid-client subprocess identity (same trick as power.py).
    subprocess_identity = f"{settings.api_name}/{getpass.getuser()}"
    try:
        await client.allow_place(name, subprocess_identity)
    except Exception as e:
        logger.warning("allow_place(%s, %s) failed: %s", name, subprocess_identity, e)

    env = dict(os.environ)
    env["LG_HOSTNAME"] = settings.api_name
    env["LG_CROSSBAR"] = settings.coordinator_address

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(env_yaml)
        config_path = fh.name
    try:
        cmd = [
            "adi-lg", "recover", "--config", config_path,
            "--target", "main", "--state", state,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=RECOVER_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise HTTPException(status_code=504, detail="recovery timed out") from None
    finally:
        try:
            os.unlink(config_path)
        except OSError:
            pass

    stdout = stdout_b.decode("utf-8", errors="replace").strip()
    stderr = stderr_b.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        logger.warning("recover %s failed: %s", name, stderr or stdout)
        raise HTTPException(status_code=502, detail=stderr or stdout or "adi-lg recover failed")
    return RecoverResult(place=name, state=state, stdout=stdout)
```

- [ ] **Step 4: Register the router in `coordinator/api/app/main.py`** — add `recovery` to the `from .routers import (...)` block and add `app.include_router(recovery.router, prefix="/api")` next to the `power`/`sdmux` includes.

- [ ] **Step 5: Run the tests** — `cd coordinator/api && python -m pytest tests/test_recovery_router.py -q` → PASS. Then ruff: from repo root `.venv/bin/ruff format coordinator/api/app/routers/recovery.py coordinator/api/tests/test_recovery_router.py` then `.venv/bin/ruff check coordinator/api && .venv/bin/ruff format --check coordinator/api` (coordinator/api has its own ruff config — run from there if the root config doesn't apply: `cd coordinator/api && ruff check . && ruff format --check .`).

- [ ] **Step 6: Commit** — `git add coordinator/api/app/routers/recovery.py coordinator/api/app/main.py coordinator/api/tests/test_recovery_router.py && git commit -m "feat(api): POST /places/{name}/recover triggers manual recovery"`

---

### Task 4: Recover button + confirm modal on PlaceDetail

**Files:** Modify `coordinator/web/src/api/client.ts`; Modify `coordinator/web/src/pages/PlaceDetail.tsx`; Modify `coordinator/web/src/pages/__tests__/PlaceDetail.test.tsx`.

**Interfaces:** Consumes the new `POST /places/{name}/recover` (Task 3). Produces `api.recoverPlace(name)` + a gated Recover button + confirm modal.

- [ ] **Step 1: Add `api.recoverPlace` to `client.ts`** next to `acquirePlace`/`releasePlace` (`~:141-144`):

```ts
  recoverPlace: (name: string) =>
    request<{ place: string; state: string; stdout: string; ok: boolean }>(
      `/places/${name}/recover`,
      { method: "POST" },
    ),
```

- [ ] **Step 2: Write the failing test.** Add `recoverPlace: vi.fn().mockResolvedValue({ ok: true })` to the `api` mock in `PlaceDetail.test.tsx`, with `useAuth` returning the owner user (so `isOwner`). Add:

```tsx
it("recovers after confirm", async () => {
  const { api } = await import("../../api/client");
  render(wrap(<PlaceDetail />));
  fireEvent.click(await screen.findByRole("button", { name: /recover/i }));
  // confirm modal: the destructive confirm button
  fireEvent.click(await screen.findByRole("button", { name: /^recover board$/i }));
  await waitFor(() => expect(api.recoverPlace).toHaveBeenCalledWith("vcu118-lab1"));
});
```

(The place must be acquired by the owner for `isOwner` — match how the existing acquire/owner tests set `acquired_username` in the `getPlace` mock.)

- [ ] **Step 3: Run it to verify it fails** — `cd coordinator/web && npm run test -- PlaceDetail` → FAIL (no Recover button).

- [ ] **Step 4: Add the Recover button + confirm modal to `PlaceDetail.tsx`:**
  - In the header `HStack` (`~:164-178`, next to Acquire/Release), add `{isOwner && <Button colorScheme="orange" leftIcon={<MdHealing/>} onClick={recoverModal.onOpen}>Recover</Button>}`.
  - Add a third `useDisclosure()` (`recoverModal`).
  - `const recoverM = useMutation({ mutationFn: () => api.recoverPlace(name), onSuccess: () => { toast({ status: "success", title: "Recovery started" }); recoverModal.onClose(); }, onError: (e) => toast({ status: "error", title: "Recovery failed", description: e instanceof Error ? e.message : String(e) }) });`
  - A confirm `Modal` (clone the match modal structure) with `ModalHeader` "Recover board?", `ModalBody` warning text (e.g. "This reflashes the SD card (erasing it) and runs for several minutes. The place stays held for the duration."), `ModalFooter` Cancel + `Button colorScheme="red" isLoading={recoverM.isPending} onClick={() => recoverM.mutate()}` labelled **"Recover board"** (matches the test's `/^recover board$/i`).
  - Import `MdHealing` from `react-icons/md`.

- [ ] **Step 5: Run tests + typecheck + build** — `cd coordinator/web && npm run test -- PlaceDetail && npx tsc --noEmit && npm run build` → PASS + clean.

- [ ] **Step 6: Commit** — `git add coordinator/web/src/api/client.ts coordinator/web/src/pages/PlaceDetail.tsx coordinator/web/src/pages/__tests__/PlaceDetail.test.tsx && git commit -m "feat(web): manual recovery button on PlaceDetail"`

---

## Self-Review

**Spec coverage:** editable tags (Task 1) + manual recovery (Tasks 2-4) both covered. Backend recovery = CLI (T2) + router (T3); web = tags UI (T1) + recover UI (T4). The tags backend already exists (no task needed). ✓

**Decisions:** every Global Constraint is an autonomously-resolved default (tags=place-level, blocking 1800s recovery, owner/admin gate, Modal-confirm, etc.), stated explicitly since we work without a user to ask. ✓

**Ordering:** T1 (frontend-only, independent) → T2 (CLI, the recover subprocess T3 calls) → T3 (router, needs T2's `adi-lg recover`) → T4 (web, needs T3's endpoint). ✓

**Type/name consistency:** `RecoverResult{place,state,stdout,ok}`, `RECOVERY_STRATEGY="BootZynq7000JTAGRecovery"`, `_VALID_STATES`, `api.recoverPlace`, the test place `vcu118-lab1`, and the confirm button label "Recover board" are used identically across the router (T3), the web fn (T4 client.ts), and the tests. `REQUIRED_TAG_KEYS` matches PlaceWizard. ✓

**Risk note for the final review:** the recovery router shells `adi-lg recover` with a generated boot-tier env yaml; env_gen hardcodes `/srv/recovery/zc706/*` artifact paths, so a real recovery needs those on-host — a missing artifact surfaces as 502 (acceptable for MVP; documented). The blocking 1800s request is the deliberate MVP; background-job execution is deferred.
