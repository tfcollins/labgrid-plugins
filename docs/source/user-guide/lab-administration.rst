Lab Administration
==================

Guides for lab administrators to deploy physical lab hosts, configure exporters, manage coordinators, and run health verification tests.

.. grid:: 1 2 2 2
   :gutter: 3
   :class-container: sd-mb-4

   .. grid-item-card:: Onboarding a Lab Host
      :link: onboarding-a-lab-host
      :link-type: doc

      Step-by-step procedure for provisioning coordinator catalog entries, places, and exporter services.

   .. grid-item-card:: Coordinator Setup
      :link: coordinator
      :link-type: doc

      Installing and operating the central labgrid coordinator with board catalogs and gRPC/REST APIs.

   .. grid-item-card:: Running Coordinator Tests
      :link: coordinator-testing
      :link-type: doc

      Executing smoke tiers and integration verification against a live coordinator.

   .. grid-item-card:: Exporter Setup
      :link: exporter-setup
      :link-type: doc

      Defining hardware resources, device paths, and YAML descriptors for an exporter host.

   .. grid-item-card:: Exporter Deployment
      :link: exporter-deployment
      :link-type: doc

      Deploying and running ``labgrid-exporter`` systemd services on physical machines.

.. toctree::
   :maxdepth: 2
   :hidden:

   onboarding-a-lab-host
   coordinator
   coordinator-testing
   exporter-setup
   exporter-deployment
