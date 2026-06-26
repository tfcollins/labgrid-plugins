Onboarding a Lab Host
=====================

This is the prescriptive, lab-admin counterpart to :doc:`onboarding-a-consumer-repo`. It is
the ordered procedure for bringing **hardware online** so that consumer repos can discover
and run on it: stand up a coordinator, deploy an exporter on each board host, publish places
and catalog entries, and register the self-hosted runners that execute the per-board CI legs.

.. admonition:: Who this is for
   :class: note

   Every "coordinator + lab prerequisites" item in the consumer guide ends with *"confirm
   with a lab admin."* **This page is that admin's side of the contract.** When these steps
   are done, a consumer's discovery preflight (:doc:`onboarding-a-consumer-repo`, Step 5)
   finds your boards with no further lab action.

How the pieces fit
------------------

Three roles cooperate. Each detailed page is linked from the step that uses it; this page is
the spine that orders them.

.. code-block:: text

    Coordinator  (one per lab — gRPC :20408, REST :8000, web :3000)
    │   source of truth for *which boards are live*; the consumer preflight queries it
    │
    ├─ Exporter host 1  ──ExporterStream──▶  registers resources (serial, JTAG, power, net)
    │     places: vcu118-lab1  (tagged daughter-board / carrier / boot-strategy)
    │
    ├─ Exporter host 2  ──ExporterStream──▶  …
    │
    └─ Self-hosted runners  (co-located with boards; run the per-board CI legs)

See :doc:`coordinator` and the :doc:`../developer-guide/architecture` "Coordinator
Infrastructure" section for the full data-flow picture.

Step 1 — stand up the coordinator (once per lab)
------------------------------------------------

The coordinator is a single Docker-compose stack serving the whole lab. From the repo's
``coordinator/`` directory:

.. code-block:: bash

   cd coordinator
   docker compose up -d

That brings up the gRPC coordinator (``:20408``), the FastAPI REST/WebSocket bridge
(``:8000``), and the web dashboard (``http://localhost:3000``). Exporters and runners point
at the gRPC port; consumer workflows derive REST from it. See :doc:`coordinator` for
configuration (auth, persistence, reverse proxy).

Step 2 — deploy an exporter on each board host
----------------------------------------------

Every host with physically attached hardware runs a labgrid **exporter** that registers its
resources with the coordinator. Per host:

#. Copy a template from ``exporter_configs/templates/`` (``vcu118_ad9081.yaml``, ``rpi.yaml``,
   ``zcu102.yaml``) to a ``resources.yaml`` and fill in serial ports, JTAG targets, power,
   and network for that host. Group names follow ``<BOARD>_<CHIP>`` (e.g. ``VCU118_AD9081``)
   so match patterns are host-independent.
#. Validate it: ``python exporter_configs/validate.py resources.yaml``.
#. Run it: ``labgrid-exporter -c <coordinator-host>:20408 -n <unique-host-name> resources.yaml``.

.. warning::

   The exporter needs **ser2net 4.6.1** on ``PATH`` — the 4.6.0 build shipped by most distros
   hangs on the RFC2217 ``purge`` option. :doc:`exporter-deployment` is the full host-setup
   procedure (ser2net build, install, run as a service, verify registration);
   :doc:`exporter-setup` is the resource-config reference.

Step 3 — publish a place per board and tag it
---------------------------------------------

A place binds an exporter's resource group to a name a client can acquire. Create one place
per board and **tag it with the keys the consumer preflight matches on**:

.. code-block:: bash

   labgrid-client -x <coordinator>:20408 create vcu118-lab1
   labgrid-client -x <coordinator>:20408 -p vcu118-lab1 add-match "<host>/VCU118_AD9081/*"
   labgrid-client -x <coordinator>:20408 -p vcu118-lab1 set-tags \
       daughter-board=ad9081 carrier=vcu118 boot-strategy=BootFPGASoCSSH runner=hw-lab

.. list-table:: Tags the hardware-CI preflight keys on
   :header-rows: 1
   :widths: 22 18 60

   * - Tag
     - Required
     - Meaning
   * - ``daughter-board``
     - yes
     - canonical part name — the same string used in ``@pytest.mark.iio_hardware(["…"])``
       and in the catalog (Step 4)
   * - ``carrier``
     - yes
     - FPGA carrier board (``vcu118``, ``zcu102``, …); lets a part on several carriers be
       narrowed
   * - ``boot-strategy``
     - yes
     - the ADI strategy that boots this place (e.g. ``BootFPGASoCSSH``, ``BootNoOSJTAG``)
   * - ``runner``
     - optional
     - self-hosted runner label co-located with the board; routes each CI leg to the right
       host (Step 5)

.. note::

   These are the keys the discovery preflight matches — distinct from the illustrative
   ``board=…``/``chip=…`` tags in :doc:`exporter-setup`. Tags are also editable from the web
   dashboard (:doc:`web-dashboard`). See :doc:`onboarding-a-consumer-repo`, Step 4, for the
   consumer's view of the same tags.

Step 4 — add a board-catalog entry per part
-------------------------------------------

The coordinator resolves a part to a bootable image (and, for flash, a build recipe) from
``coordinator/api/board_catalog.yaml`` — one entry per part you publish:

- Template: ``adi_lg_plugins/hw_ci/onboarding_templates/board-catalog-entry.yaml``;
  schema: ``coordinator/api/app/catalog.py``.
- **uri** parts need an ``image:`` (Kuiper release the board boots).
- **flash** parts additionally need a ``flash:`` block (and ``flash.kuiper_xsa_dir`` when the
  Kuiper folder is a family name, e.g. ``zynq-zc706-adv7511-adrv937x`` for adrv9371).

.. important::

   After **any** catalog edit the coordinator host must be **redeployed** — a stale catalog
   surfaces downstream as ``Unknown release version`` (no ``image``) and the board is skipped.

Step 5 — register self-hosted runners
-------------------------------------

The per-board CI legs run on self-hosted runners co-located with (or able to reach) each
board. Register one physical host across one or more GitHub scopes with
``.github/scripts/register-hw-runners.sh``:

.. code-block:: bash

   ./.github/scripts/register-hw-runners.sh \
       --hosts-file ./hosts.tsv \
       --scopes org:analogdevicesinc,repo:tfcollins/labgrid-plugins

Each leg prefers the runner named by its place's ``runner`` tag (Step 3) and falls back to
the consumer's ``HW_REQUEST_RUNNER`` label; the preflight runs on ``HW_PREFLIGHT_RUNNER``.
**flash** legs additionally need Vivado/Vitis (+ ~10 GB disk for the Kuiper image) on the
runner. See :doc:`hardware-ci-runner-setup` and the "Registering self-hosted runners"
section of :doc:`github-actions`.

.. warning::

   The runners must be registered on **the consumer repo's (or org's) scope** — not this
   repo's — or that consumer's legs queue forever. ``--scopes`` registers one lab host across
   several scopes so it can serve both org and personal-account consumers.

Step 6 — verify the lab is consumable
-------------------------------------

Confirm the chain end-to-end before a consumer relies on it. From any host that can reach the
coordinator:

.. code-block:: bash

   export LG_COORDINATOR=<host>:20408

   # places exist and are matched to live resources
   labgrid-client -x "$LG_COORDINATOR" places
   labgrid-client -x "$LG_COORDINATOR" resources

   # run a consumer-style discovery preflight — no hardware needed
   adi-lg-hw-ci request-matrix --test-root test/hw --coord "$LG_COORDINATOR"   # uri
   adi-lg-hw-ci noos-matrix    --manifest tools/hw_ci/projects.yaml --coord "$LG_COORDINATOR"  # flash

**Success** is one matrix leg per board you expect, each with a non-empty ``runner``. A board
that does not appear is missing a place tag (Step 3), a catalog entry (Step 4), or a redeploy.
For a no-hardware smoke test of the coordinator itself, bring up the mock exporter — see
"Testing Without Hardware" in :doc:`coordinator`.

Troubleshooting
---------------

- **Exporter never registers** — wrong ser2net version, a duplicate ``-n`` name, or the
  coordinator host/port is unreachable. See :doc:`exporter-deployment` "Verify Registration".
- **A board is never discovered** — its place is untagged/mistagged (needs
  ``daughter-board`` + ``carrier`` + ``boot-strategy``), it has no ``board_catalog.yaml``
  entry, or the coordinator is stale (redeploy after catalog edits).
- **Consumer legs queue forever** — no runner with the requested label is registered on that
  consumer's scope; re-run ``register-hw-runners.sh --scopes``.
- **``Unknown release version``** — the catalog returns no ``image``; redeploy the coordinator
  after the catalog merge.

See also
--------

- :doc:`onboarding-a-consumer-repo` — the consumer side of this contract.
- :doc:`coordinator` — coordinator setup and configuration.
- :doc:`exporter-setup` / :doc:`exporter-deployment` — exporter config and host setup.
- :doc:`hardware-ci-runner-setup` — runner requirements and registration.
- :doc:`web-dashboard` — managing places and tags from the browser.
