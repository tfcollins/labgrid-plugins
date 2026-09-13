.. title:: labgrid-plugins Documentation

.. container:: homepage-hero

   .. container:: homepage-kicker

      HARDWARE AUTOMATION · FPGA SOC · LABGRID

   .. container:: homepage-headline

      Control the lab. Reproduce the result.

   .. container:: homepage-lede

      Drivers, resources, boot strategies, and hardware-CI orchestration for
      automated testing of Analog Devices FPGA SoC systems.

   .. container:: homepage-actions

      .. button-ref:: getting-started/index
         :color: primary
         :expand:

         Get started →

      .. button-ref:: user-guide/access-topology
         :color: secondary
         :expand:

         Explore the architecture

   .. container:: homepage-proof

      **15 drivers** · **13 strategies** · **Exporter-aware execution** · **Hardware CI**

Choose your path
----------------

.. grid:: 1 2 3 3
   :gutter: 3
   :class-container: homepage-card-grid

   .. grid-item-card:: Start building
      :link: getting-started/index
      :link-type: doc
      :class-card: homepage-card homepage-card--green

      Install the package, define a target, and run your first operation.

      +++
      **Getting started →**

   .. grid-item-card:: Configure hardware
      :link: yaml-reference/index
      :link-type: doc
      :class-card: homepage-card homepage-card--blue

      Look up every resource, driver, and strategy field in one place.

      +++
      **YAML reference →**

   .. grid-item-card:: Operate the lab
      :link: user-guide/index
      :link-type: doc
      :class-card: homepage-card homepage-card--orange

      Follow task-oriented guides for exporters, boot flows, and device control.

      +++
      **User guide →**

   .. grid-item-card:: Automate hardware CI
      :link: user-guide/onboarding-a-consumer-repo
      :link-type: doc
      :class-card: homepage-card homepage-card--purple

      Connect a consumer repository to bounded, repeatable hardware jobs.

      +++
      **CI onboarding →**

   .. grid-item-card:: Bring a lab online
      :link: user-guide/onboarding-a-lab-host
      :link-type: doc
      :class-card: homepage-card homepage-card--cyan

      Set up coordinators, exporters, places, and resource-safe runners.

      +++
      **Lab-host onboarding →**

   .. grid-item-card:: Extend the platform
      :link: developer-guide/index
      :link-type: doc
      :class-card: homepage-card homepage-card--pink

      Understand the architecture and implement new integrations safely.

      +++
      **Developer guide →**

From API call to physical hardware
----------------------------------

.. grid:: 1 1 2 2
   :gutter: 4
   :class-container: homepage-feature-grid

   .. grid-item::
      :class: homepage-feature-copy

      .. container:: homepage-kicker

         EXECUTION TOPOLOGY

      Keep control logic readable on the client while running network- and
      hardware-adjacent operations on the exporter. Location-aware artifacts
      cross boundaries only when their consumer requires it.

      .. button-ref:: user-guide/access-topology
         :color: primary

         See execution and access paths →

   .. grid-item::
      :class: homepage-flow-panel

      .. container:: homepage-flow

         .. container:: homepage-flow-step homepage-flow-step--client

            **1 · Client**

            Resolve target and strategy

         .. container:: homepage-flow-arrow

            ↓  narrow RPC / SSH

         .. container:: homepage-flow-step homepage-flow-step--exporter

            **2 · Exporter**

            Run tools near hardware

         .. container:: homepage-flow-arrow

            ↓  JTAG · TFTP · serial · LAN

         .. container:: homepage-flow-step homepage-flow-step--dut

            **3 · DUT**

            Boot, test, and report

Built for real lab workflows
----------------------------

.. grid:: 1 2 3 3
   :gutter: 3
   :class-container: homepage-capability-grid

   .. grid-item::
      :class: homepage-capability homepage-capability--power

      **Power and recovery**

      APC, CyberPower, Kasa, VeSync, and Home Assistant control with explicit
      lifecycle and exporter-local credentials.

   .. grid-item::
      :class: homepage-capability homepage-capability--boot

      **Repeatable boot paths**

      Stage bitstreams and software through JTAG, mass storage, TFTP, and
      recovery services without confusing client and exporter paths.

   .. grid-item::
      :class: homepage-capability homepage-capability--ci

      **Resource-safe hardware CI**

      Acquire named labgrid places, run bounded jobs, collect artifacts, and
      release hardware even when a test fails.

Try the API
-----------

.. container:: homepage-code-intro

   A target configuration and a few Python calls are enough to control a device.

.. code-block:: yaml
   :caption: target.yaml

   targets:
     my_device:
       resources:
         NetworkPowerPort:
           model: kasa
           host: 192.0.2.20
           index: 0
       drivers:
         KasaPowerDriver: {}

.. code-block:: python
   :caption: Power-cycle the target

   from labgrid import Environment

   env = Environment("target.yaml")
   target = env.get_target("my_device")
   power = target.get_driver("KasaPowerDriver")

   power.cycle()

.. container:: homepage-final-cta

   **Ready to automate a board?**

   Start with installation and a minimal target, or jump directly to the API.

   .. button-ref:: getting-started/installation
      :color: primary

      Install labgrid-plugins →

   .. button-ref:: api/index
      :color: secondary

      Browse the API

.. admonition:: Project status
   :class: note homepage-status

   Current version: **0.1.0**. This is early-stage software under active
   development; interfaces and architecture continue to evolve.

.. toctree::
   :maxdepth: 2
   :caption: Contents:
   :hidden:

   getting-started/index
   user-guide/index
   yaml-reference/index
   api/index
   developer-guide/index
   examples/index

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
