Hardware CI
===========

Automating on-hardware CI testing for consumer repositories using reusable workflows, matrix discovery, and self-hosted runners.

.. grid:: 1 2 2 2
   :gutter: 3
   :class-container: sd-mb-4

   .. grid-item-card:: Onboarding a Consumer Repo
      :link: onboarding-a-consumer-repo
      :link-type: doc

      Prescriptive, step-by-step recipe for connecting any repository to the hardware-CI flow.

   .. grid-item-card:: Hardware CI by Part (hw-request)
      :link: hw-request
      :link-type: doc

      Deep dive into the ``hw-request.yml`` reusable workflow, test discovery, and reservation modes.

   .. grid-item-card:: GitHub Actions Workflows
      :link: github-actions
      :link-type: doc

      Reference guide for reusable caller workflows, parameters, outputs, and Prism reporting.

   .. grid-item-card:: Runner Setup (no-os Flash Mode)
      :link: hardware-ci-runner-setup
      :link-type: doc

      Configuring bare-metal self-hosted runners with Vivado toolchains and Kuiper dependencies.

.. toctree::
   :maxdepth: 2
   :hidden:

   onboarding-a-consumer-repo
   hw-request
   github-actions
   hardware-ci-runner-setup
